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
Wrappers for User objects.

.. currentmodule:: curious.dataclasses.user
"""

import datetime
from enum import Enum, IntEnum
from typing import Optional

from curious.core import get_current_client
from curious.dataclasses import channel as dt_channel, guild as dt_guild, message as dt_message
from curious.dataclasses.bases import Dataclass
from curious.exc import CuriousError


class AvatarUrl(object):
    """
    Represents a user's avatar URL.

    To get the actual URL, do str(avatar_url).
    """

    def __init__(self, user: 'User') -> None:
        """
        :param user: The :class:`.User` for this URL.
        """
        self._user = user
        self._format = "webp"
        self._size = 256

    def __str__(self) -> str:
        """
        :return: The string URL for this avatar URL.
        """
        if not self._user.avatar_hash:
            base_url = f"https://cdn.discordapp.com/embed/avatars/" \
                f"{int(self._user.discriminator) % 5}"
        else:
            base_url = f"https://cdn.discordapp.com/avatars/" \
                f"{self._user.id}/{self._user.avatar_hash}"

        return f"{base_url}.{self._format}?size={self._size}"

    def as_format(self, format: str) -> 'AvatarUrl':
        """
        Gets the URL in the specified format.

        :param format: The format to use. Usually ``png``, ``webp`` or ``gif``.
        :return: A new :class:`.AvatarUrl` with the specified format.
        """
        obb = AvatarUrl(self._user)
        obb._format = format
        obb._size = self._size
        return obb

    def with_size(self, size: int) -> 'AvatarUrl':
        """
        Gets the URL in the specified size.

        :param size: The size for the URL.
        :return: A new :class:`.AvatarUrl` with the specified size.
        """
        obb = AvatarUrl(self._user)
        obb._format = self._format
        obb._size = size
        return obb

    def __eq__(self, other: 'AvatarUrl'):
        if not isinstance(other, AvatarUrl):
            return NotImplemented

        return str(self) == str(other)

    def __lt__(self, other):
        if not isinstance(other, AvatarUrl):
            return NotImplemented

        return str(self) < str(other)


class PremiumType(IntEnum):
    """
    Represents the premium types.
    """
    NONE = 0
    NITRO_CLASSIC = 1
    NITRO = 2


class HypesquadHouse(Enum):
    """
    Represents the hypesquad houses.
    """
    BRAVERY = 0
    BRILLIANCE = 1
    BALANCE = 2
    UNKNOWN = 3


class UserFlags(object):
    """
    Represents the flags for a user.
    """
    __slots__ = "_flags",

    FLAG_NONE = 0
    FLAG_DISCORD_EMPLOYEE = 1 << 0
    FLAG_DISCORD_PARTNER = 1 << 1
    FLAG_HYPESQUAD_EVENTS = 1 << 2
    FLAG_BUG_HUNTER = 1 << 3
    FLAG_HOUSE_BRAVERY = 1 << 6
    FLAG_HOUSE_BRILLIANCE = 1 << 7
    FLAG_HOUSE_BALANCE = 1 << 8
    FLAG_EARLY_SUPPORTER = 1 << 9

    def __init__(self, flag_int: int):
        self._flags = flag_int

    @property
    def raw(self) -> int:
        """
        :return: The raw flag integer for this set of flags.
        """
        return self._flags

    def __repr__(self) -> str:
        return repr(self._flags)

    def __str__(self) -> str:
        return str(self._flags)

    def __and__(self, other) -> int:
        return self._flags & other

    def __or__(self, other) -> int:
        return self._flags & other

    @property
    def is_hypesquad(self) -> bool:
        """
        :return: If this user has the hypesquad flag.
        """
        return (self._flags & self.FLAG_HYPESQUAD_EVENTS) != 0

    @property
    def house(self) -> Optional[HypesquadHouse]:
        """
        :return: What hypesquad house this user is in.
        """
        if not self.is_hypesquad:
            return None

        if self._flags & self.FLAG_HOUSE_BALANCE:
            return HypesquadHouse.BALANCE
        elif self._flags & self.FLAG_HOUSE_BRAVERY:
            return HypesquadHouse.BALANCE
        elif self._flags & self.FLAG_HOUSE_BRILLIANCE:
            return HypesquadHouse.BRILLIANCE
        else:
            return HypesquadHouse.UNKNOWN


class User(Dataclass):
    """
    This represents a bare user - i.e, somebody without a guild attached.
    This is used in DMs and similar. All member objects have a reference to their user on ``.user``.

    :ivar id: The ID of this user.
    """

    __slots__ = ("username", "discriminator", "avatar_hash", "verified", "mfa_enabled", "bot",
                 "flags", "_flags_raw", "premium_type")

    def __init__(self, **kwargs):
        super().__init__(kwargs.get("id"))

        #: The username of this user.
        self.username: str = kwargs["username"]

        #: The discriminator of this user.
        #: Note: This is a string, not an integer.
        self.discriminator: str = kwargs.get("discriminator", "0000")

        #: The avatar hash of this user.
        self.avatar_hash: Optional[str] = kwargs.get("avatar", None)

        #: If this user is verified or not.
        self.verified: Optional[bool] = kwargs.get("verified", None)

        #: If this user has MFA enabled or not.
        self.mfa_enabled: Optional[bool] = kwargs.get("mfa_enabled", None)

        #: If this user is a bot.
        self.bot: bool = kwargs.get("bot", False)

        #: The premium type for this user.
        self.premium_type = PremiumType(kwargs.get("premium_type", 0))

        #: The raw flags int for this user.
        self._flags_raw: int = kwargs.get("flags", 0)

        #: The user flags object for this user.
        self.flags = UserFlags(self._flags_raw)

    @property
    def user(self) -> 'User':
        """
        Compatability propertly with :class:`.Member`.
        """
        return self

    def _copy(self):
        new_object = object.__new__(self.__class__)
        new_object.id = self.id
        new_object.username = self.username
        new_object.discriminator = self.discriminator
        new_object.avatar_hash = self.avatar_hash
        new_object.verified = self.verified
        new_object.mfa_enabled = self.mfa_enabled
        new_object.bot = self.bot

        return new_object

    @property
    def avatar_url(self) -> 'AvatarUrl':
        """
        :return: The avatar URL of this user.
        """
        return AvatarUrl(self)

    @property
    def static_avatar_url(self) -> str:
        """
        :return: The avatar URL of this user, but static.
        """
        return str(self.avatar_url.as_format('png'))

    @property
    def name(self) -> str:
        return self.username

    @property
    def mention(self) -> str:
        """
        :return: A string that mentions this user.
        """
        return "<@{}>".format(self.id)

    @property
    def created_at(self) -> datetime.datetime:
        """
        :return: The :class:`.datetime.datetime` this user was created at.
        """
        return self.snowflake_timestamp

    def __repr__(self) -> str:
        return "<{} id={} name={} discrim={}>".format(type(self).__name__, self.id, self.name,
                                                      self.discriminator)

    def __str__(self) -> str:
        return f"{self.username}#{self.discriminator}"

    async def open_private_channel(self) -> 'dt_channel.Channel':
        """
        Opens a private channel with a user.

        .. note::

            You probably won't need this to just send messages to a user.

        :return: The newly created private channel.
        """
        if self.discriminator == "0000":
            raise CuriousError("Cannot open a private channel with a webhook")

        # First, try and access the channel from the channel cache.
        client = get_current_client()
        original_channel = client.state.find_channel(self.id)
        if original_channel:
            return original_channel

        # Failing that, open a new private channel.
        channel_data = await client.http.create_private_channel(self.id)
        channel = client.state.make_private_channel(channel_data)
        return channel

    async def send(self, content: str = None, *args, **kwargs) -> 'dt_message.Message':
        """
        Sends a message to the user over a private channel.

        :param content: The contet of the message to send.
        :return: A new :class:`.Message` representing the sent message.
        """
        channel = await self.open_private_channel()
        message = await channel.messages.send(content, *args, **kwargs)

        return message

    async def unban_from(self, guild: 'dt_guild.Guild'):
        """
        Unbans this user from a guild.

        :param guild: The :class:`.Guild` to unban in.
        """
        return await guild.bans.remove(self)


class BotUser(User):
    """
    A special type of user that represents ourselves.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        #: The email for this user.
        self.email = kwargs.get("email", None)

        #: Does this user use mobile?
        self.mobile = kwargs.get("mobile", False)

        #: Is this user premium?
        self.premium = kwargs.get("premium", False)

    async def open_private_channel(self):
        raise NotImplementedError("Cannot open a private channel with yourself")

    async def send(self, *args, **kwargs):
        raise NotImplementedError("Cannot send messages to your own user")

    async def edit(self, *args, **kwargs):
        """
        Edits the bot's current profile.
        """
        return await get_current_client().edit_profile(*args, **kwargs)

    async def upload_avatar(self, path: str):
        """
        A higher level interface to editing the bot's avatar.
        """
        return await get_current_client().edit_avatar(path)
