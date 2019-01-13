# This file is part of curious.
#
# curious is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# curious is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with curious.  If not, see <http://www.gnu.org/licenses/>.

"""
The main client class.

This contains a definition for :class:`.Client` which is used to interface primarily with Discord.

.. currentmodule:: curious.core.client
"""
import collections

import anyio
import enum
import logging
from os import PathLike
from types import MappingProxyType
from typing import Any, Iterable, Mapping, MutableMapping, Tuple, Union

from curious.core import chunker as md_chunker
from curious.core.event import EventManager, event as ev_dec, scan_events
from curious.core.gateway import GatewayHandler, open_websocket
from curious.core.httpclient import HTTPClient
from curious.dataclasses import channel as dt_channel, guild as dt_guild
from curious.dataclasses.appinfo import AppInfo
from curious.dataclasses.invite import Invite
from curious.dataclasses.message import CHANNEL_REGEX, EMOJI_REGEX, MENTION_REGEX
from curious.dataclasses.presence import Game, Status
from curious.dataclasses.user import BotUser, User
from curious.dataclasses.webhook import Webhook
from curious.dataclasses.widget import Widget
from curious.exc import Unauthorized
from curious.util import base64ify, coerce_agen, finalise

logger = logging.getLogger("curious.client")


class BotType(enum.IntEnum):
    """
    An enum that signifies what type of bot this bot is.
    
    This will tell the commands handling how to respond, as well as how to log in.
    """
    #: Regular bot. This signifies that the client should log in as a bot account.
    BOT = 1

    # 4 is reserved

    #: No bot responses. This signifies that the client should respond to ONLY USER messages.
    ONLY_USER = 8

    #: No DMs. This signifies the bot only works in guilds.
    NO_DMS = 16

    #: No guilds. This signifies the bot only works in DMs.
    NO_GUILDS = 32

    #: Self bot. This signifies the bot only responds to itself.
    SELF_BOT = 64


class InvalidTokenException(ValueError):
    """
    Raised when the bot's token is invalid.
    """

    def __init__(self, token: str):
        self.token = token


class ReshardingNeeded(Exception):
    """
    Raised when resharding is needed. This should not be caught.
    """

    def __repr__(self):
        return "Discord rejected the connection because the bot needs more shards. If you are " \
               "seeing this, autosharding is disabled and curious could not change shard count."


class Client(object):
    """
    The main client class. This is used to interact with Discord.

    To start, you can create an instance of the client by passing it the token you want to use:

    .. code-block:: python3

        cl = Client("my.token.string")

    Registering events can be done with the :meth:`.Client.event` decorator, or alternatively
    manual usage of the :class:`.EventHandler` on :attr:`.Client.events`.

    .. code-block:: python3

        @cl.event("ready")
        async def loaded(ctx: EventContext):
            print("Bot logged in.")

    """
    #: A list of events to ignore the READY status.
    IGNORE_READY = [
        "connect",
        "guild_streamed",
        "guild_chunk",
        "guild_available",
        "guild_sync"
    ]

    def __init__(self, token: str, *,
                 state_klass=None,
                 bot_type: int = (BotType.BOT | BotType.ONLY_USER)):
        """
        :param token: The current token for this bot.
        :param state_klass: The class to construct the connection state from.
        :param bot_type: A union of :class:`.BotType` that defines the type of this bot.
        """
        #: The mapping of `shard_id -> gateway` objects.
        self._gateways: MutableMapping[int, GatewayHandler] = {}

        #: The number of shards this client has.
        self.shard_count = 0

        #: The token for the bot.
        self._token = token

        if state_klass is None:
            from curious.core.state import State
            state_klass = State

        #: The current connection state for the bot.
        self.state = state_klass()

        #: The bot type for this bot.
        self.bot_type = bot_type

        #: The current :class:`.EventManager` for this bot.
        self.events = EventManager()
        #: The current :class:`.Chunker` for this bot.
        self.chunker = md_chunker.Chunker(self)
        self.chunker.register_events(self.events)

        self._ready_state = {}

        #: The :class:`.HTTPClient` used for this bot.
        self.http = HTTPClient(self._token)

        #: The cached gateway URL.
        self._gw_url = None  # type: str

        #: The application info for this bot. Instance of :class:`.AppInfo`.
        self.application_info = None  # type: AppInfo

        #: The task manager used for this bot.
        self.task_manager: anyio.TaskGroup = None

        for (name, event) in scan_events(self):
            self.events.add_event(event)

    @property
    def user(self) -> BotUser:
        """
        :return: The :class:`.User` that this client is logged in as.
        """
        return self.state._user

    @property
    def guilds(self) -> 'Mapping[int, dt_guild.Guild]':
        """
        :return: A mapping of int -> :class:`.Guild` that this client can see.
        """
        return self.state.guilds

    @property
    def invite_url(self) -> str:
        """
        :return: The invite URL for this bot.
        """
        return "https://discordapp.com/oauth2/authorize?client_id={}&scope=bot".format(
            self.application_info.client_id)

    @property
    def events_handled(self) -> collections.Counter:
        """
        A :class:`collections.Counter` of all events that have been handled since the bot's bootup.
        This can be used to track statistics for events.
         
        .. code-block:: python3
        
            @command()
            async def events(self, ctx: Context):
                '''
                Shows the most common events.
                '''
                
                ev = ctx.bot.events_handled.most_common(3)
                await ctx.channel.messages.send(", ".join("{}: {}".format(*x) for x in ev)
        
        """

        c = collections.Counter()
        for gw in self._gateways.values():
            c.update(gw._dispatches_handled)

        return c

    @property
    def gateways(self) -> 'Mapping[int, GatewayHandler]':
        """
        :return: A read-only view of the current gateways for this client. 
        """
        return MappingProxyType(self._gateways)

    async def _spawn_task_internal(self, cofunc):
        await self.task_manager.spawn(self.events._safety_wrapper, cofunc)

    def find_channel(self, channel_id: int) -> 'Union[None, dt_channel.Channel]':
        """
        Finds a channel by channel ID.
        """
        return self.state.find_channel(channel_id)

    async def get_gateway_url(self, get_shard_count: bool = True) \
            -> Union[str, Tuple[str, int]]:
        """
        :return: The gateway URL for this bot.
        """
        if get_shard_count:
            return await self.http.get_gateway_url_bot()
        else:
            return await self.http.get_gateway_url()

    def guilds_for(self, shard_id: int) -> 'Iterable[dt_guild.Guild]':
        """
        Gets the guilds for this shard.

        :param shard_id: The shard ID to get guilds from.
        :return: A list of :class:`Guild` that client can see on the specified shard.
        """
        return self.state.guilds_for_shard(shard_id)

    def event(self, name: str):
        """
        A convenience decorator to mark a function as an event.

        This will copy it to the events dictionary, where it will be used as an event later on.

        .. code-block:: python3
        
            @bot.event("message_create")
            async def something(ctx, message: Message):
                pass

        :param name: The name of the event.
        """

        def _inner(func):
            f = ev_dec(name)(func)
            self.events.add_event(func=f)
            return func

        return _inner

    # rip in peace old fire_event
    # 2016-2017
    # broke my pycharm
    async def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        This actually passes the arguments to :meth:`.EventManager.fire_event`.
        """
        gateway = kwargs.get("gateway")
        if not self.state.is_ready(gateway.gw_state.shard_id):
            if event_name not in self.IGNORE_READY and not event_name.startswith("gateway_"):
                return

        return await self.events.fire_event(event_name, *args, **kwargs)

    async def wait_for(self, *args, **kwargs) -> Any:
        """
        Shortcut for :meth:`.EventManager.wait_for`.
        """
        return await self.events.wait_for(*args, **kwargs)

    # Gateway functions
    async def change_status(self, game: Game = None, status: Status = Status.ONLINE,
                            afk: bool = False,
                            shard_id: int = 0):
        """
        Changes the bot's current status.

        :param game: The game object to use. None for no game.
        :param status: The new status. Must be a :class:`.Status` object.
        :param afk: Is the bot AFK? Only useful for userbots.
        :param shard_id: The shard to change your status on.
        """

        gateway = self._gateways[shard_id]
        return await gateway.send_status(
            name=game.name if game else None, type_=game.type if game else None,
            url=game.url if game else None,
            status=status.value,
        )

    # HTTP Functions
    async def edit_profile(self, *,
                           username: str = None,
                           avatar: bytes = None) -> None:
        """
        Edits the profile of this bot.

        The user is **not** edited in-place - instead, you must wait for the ``USER_UPDATE`` event
        to be fired on the websocket.

        :param username: The new username of the bot.
        :param avatar: The bytes-like object that represents the new avatar you wish to use.
        """
        if username:
            if any(x in username for x in ('@', ':', '```')):
                raise ValueError("Username must not contain banned characters")

            if username in ("discordtag", "everyone", "here"):
                raise ValueError("Username cannot be a banned username")

            if not 2 <= len(username) <= 32:
                raise ValueError("Username must be 2-32 characters")

        if avatar:
            avatar = base64ify(avatar)

        await self.http.edit_user(username, avatar)

    async def edit_avatar(self, path: Union[str, PathLike]) -> None:
        """
        A higher-level way to change your avatar.
        This allows you to provide a path to the avatar file instead of having to read it in 
        manually.

        :param path: The path-like object to the avatar file.
        """
        with open(path, 'rb') as f:
            await self.edit_profile(avatar=f.read())

    async def get_user(self, user_id: int) -> User:
        """
        Gets a user by ID.

        :param user_id: The ID of the user to get.
        :return: A new :class:`.User` object.
        """
        try:
            return self.state._users[user_id]
        except KeyError:
            u = self.state.make_user(await self.http.get_user(user_id))
            # decache it if we need to
            self.state._check_decache_user(u.id)
            return u

    async def get_application(self, application_id: int) -> AppInfo:
        """
        Gets an application by ID.

        :param application_id: The client ID of the application to fetch.
        :return: A new :class:`.AppInfo` object corresponding to the application.
        """
        data = await self.http.get_app_info(application_id=application_id)
        appinfo = AppInfo(**data)

        return appinfo

    async def get_webhook(self, webhook_id: int) -> Webhook:
        """
        Gets a webhook by ID.

        :param webhook_id: The ID of the webhook to get.
        :return: A new :class:`.Webhook` object.
        """
        return self.state.make_webhook(await self.http.get_webhook(webhook_id))

    async def get_invite(self, invite_code: str, *,
                         with_counts: bool = True) -> Invite:
        """
        Gets an invite by code.

        :param invite_code: The invite code to get.
        :param with_counts: Return the approximate counts for this invite?
        :return: A new :class:`.Invite` object.
        """
        return Invite(**(await self.http.get_invite(invite_code, with_counts=with_counts)))

    async def get_widget(self, guild_id: int) -> Widget:
        """
        Gets a widget from a guild.
        
        :param guild_id: The ID of the guild to get the widget of. 
        :return: A :class:`.Widget` object.
        """
        return Widget(**await self.http.get_widget_data(guild_id))

    async def clean_content(self, content: str) -> str:
        """
        Cleans the content of a message, using the bot's cache.

        :param content: The content to clean.
        :return: The cleaned up message.
        """
        final = []
        tokens = content.split(" ")
        # o(2n) loop
        for token in tokens:
            # try and find a channel from public channels
            channel_match = CHANNEL_REGEX.match(token)
            if channel_match is not None:
                channel_id = int(channel_match.groups()[0])
                channel = self.state.find_channel(channel_id)
                if channel is None or channel.type not in \
                        [dt_channel.ChannelType.TEXT, dt_channel.ChannelType.VOICE]:
                    final.append("#deleted-channel")
                else:
                    final.append(f"#{channel.name}")

                continue

            user_match = MENTION_REGEX.match(token)
            if user_match is not None:
                found_name = None
                user_id = int(user_match.groups()[0])
                member_or_user = self.state.find_member_or_user(user_id)
                if member_or_user:
                    found_name = member_or_user.name

                if found_name is None:
                    final.append(token)
                else:
                    final.append(f"@{found_name}")

                continue

            emoji_match = EMOJI_REGEX.match(token)
            if emoji_match is not None:
                final.append(f":{emoji_match.groups()[0]}:")
                continue

            # if we got here, matching failed
            # so just add the token
            final.append(token)

        return " ".join(final)

    @ev_dec(name="ready")
    async def handle_ready(self) -> None:
        """
        Handles a READY event, dispatching a ``shards_ready`` event when all shards are ready.
        """
        from curious.core.event import current_event_context
        ctx = current_event_context()

        self._ready_state[ctx.shard_id] = True

        if not all(self._ready_state.values()):
            return

        await self.events.fire_event("shards_ready", gateway=self._gateways[ctx.shard_id],
                                     client=self)

    async def run_shard(self, shard_id: int) -> None:
        """
        Runs a shard.
        """
        async with open_websocket(self._token, url=self._gw_url,
                                  shard_id=shard_id, shard_count=self.shard_count) as gw:
            # gw: GatewayHandler
            self._gateways[shard_id] = gw
            from curious.core import _current_shard
            _current_shard.set(shard_id)

            async with finalise(gw.events()) as agen:
                async for event in agen:
                    name, *params = event
                    to_dispatch = [event]

                    if name == "websocket_closed":
                        code: int = params[0]
                        reason: str = params[1]

                        logger.info(f"Shard {shard_id} closed - {code}: {reason}")
                        if code == 4004:
                            raise InvalidTokenException(self._token)
                        elif code == 4011:
                            raise ReshardingNeeded
                        # usually the rest can be handled appropriately

                    elif name == "gateway_dispatch_received":
                        handler = f"handle_{params[0].lower()}"
                        handler = getattr(self.state, handler)
                        subevents = await coerce_agen(handler(*params[1:]))
                        to_dispatch += subevents

                    for event in to_dispatch:
                        await self.events.fire_event(event[0], *event[1:], gateway=gw)

    async def manage_all_shards(self, shard_count: int) -> None:
        """
        Runs the bot's shards.
        """
        # update ready state
        for shard_id in range(shard_count):
            self._ready_state[shard_id] = False

        # boot up the gateway connections
        logger.info(f"Loading {shard_count} gateway connections.")
        async with anyio.create_task_group() as main_group:
            # tg: anyio.TaskGroup

            # copy the task manager into the global namespace
            self.task_manager = main_group
            self.events.task_manager = main_group

            for shard in range(0, shard_count):
                await main_group.spawn(self.run_shard, shard)

                if shard_count >= 2:
                    logger.info(f"Sleeping 5 seconds before connecting to shard {shard}")
                    await anyio.sleep(5)

    async def run_bot_in_sharded_mode(self, shard_count: int, *,
                                      allow_resharding: bool = True) -> None:
        """
        Starts the bot. This is an internal method - you want :meth:`.Client.run_async`.

        :param shard_count: The number of shards to boot.
        :param allow_resharding: If the bot can automatically be resharded.
        """
        from curious.core import _current_client
        _current_client.set(self)

        try:
            self.application_info = AppInfo(**(await self.http.get_app_info(None)))
        except Unauthorized:
            raise InvalidTokenException(self._token) from None

        while True:
            try:
                await self.manage_all_shards(shard_count)
            except ReshardingNeeded:
                if allow_resharding:
                    shard_count = await self.get_gateway_url(get_shard_count=True)
                    self.shard_count = shard_count
                    continue

                raise

    async def run_async(self, *, shard_count: int = 1, autoshard: bool = True,
                        allow_resharding: bool = True) -> None:
        """
        Runs the client asynchronously.

        :param shard_count: The number of shards to boot.
        :param autoshard: If the bot should be autosharded.
        :param allow_resharding: If the bot is allowed to recalculate it's shard count in the \
            event of a 4011 error.
        """
        if autoshard:
            url, shard_count = await self.get_gateway_url(get_shard_count=True)
        else:
            url, shard_count = await self.get_gateway_url(get_shard_count=False), shard_count

        self._gw_url = url
        self.shard_count = shard_count

        return await self.run_bot_in_sharded_mode(shard_count,
                                                  allow_resharding=autoshard or allow_resharding)
