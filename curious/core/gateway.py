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
Websocket gateway code.

.. currentmodule:: curious.core.gateway
"""
import sys
import time
import zlib
from collections import Counter

import anyio
import enum
import json
import logging
from anyio import TaskGroup
from async_generator import asynccontextmanager
from dataclasses import dataclass
from lomond.errors import WebSocketClosed, WebSocketClosing, WebSocketUnavailable
from lomond.events import Binary, Closing, Connected, Connecting, Text
from typing import Any, AsyncContextManager, AsyncGenerator, List, Union

from curious.core._ws_wrapper.universal_wrapper import UniversalWrapper
from curious.util import finalise, safe_generator


class GatewayOp(enum.IntEnum):
    """
    Represents the opcode mapping for the gateway.
    """
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE = 3
    VOICE_STATE = 4
    VOICE_PING = 5
    RESUME = 6
    RECONNECT = 7
    REQUEST_MEMBERS = 8
    INVALIDATE_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11
    GUILD_SYNC = 12


@dataclass
class _GatewayState:
    """
    Represents the gateway state for the current gateway.
    """
    #: The current token.
    token: str

    #: The current gateway URL.
    gateway_url: str

    #: The shard ID for this gateway.
    shard_id: int

    #: The shard count for this gateway.
    shard_count: int

    #: The current session ID.
    session_id: str = None

    #: The current sequence.
    sequence: int = 0

    #: If the session is currently authenticated (used for zombie logic on resumes).
    authenticated: bool = False


@dataclass
class HeartbeatStats:
    """
    Represents the statistics for the gateway's heartbeat counters.
    """
    #: The number of heartbeats sent.
    heartbeats: int = 0

    #: The number of heartbeat acks received.
    heartbeat_acks: int = 0

    #: Internal time when the last heartbeat was sent.
    last_heartbeat_time: float = 0

    #: Internal time when the last heartbeat_ack was received.
    last_ack_time: float = 0

    @property
    def gw_time(self) -> float:
        """
        :return: The time the most recent heartbeat and heartbeat_ack.
        """
        return self.last_ack_time - self.last_heartbeat_time


class GatewayHandler(object):
    """
    Represents a gateway handler - something that is connected to Discord's websocket and handles
    incoming events and parses them as appropriate.

    You don't want to create this class directly; use :meth:`.open_gateway` instead.

    .. code-block:: python3

        async with open_gateway("wss://gateway.discord.gg", token="token",
                                shard_id=0, shard_count=1) as gateway:
            async for event in gateway.events():
                ...
    """
    GATEWAY_VERSION = 6
    ZLIB_FLUSH_SUFFIX = b'\x00\x00\xff\xff'

    def __init__(self, session: _GatewayState):
        #: The current session being used for this gateway.
        self.session = session

        #: The current heartbeat stats being used for this gateway.
        self.heartbeat_stats = HeartbeatStats()

        #: The current :class:`.BasicWebsocketWrapper` connected to Discord.
        self.websocket: UniversalWrapper = None

        #: The current task group for this gateway.
        self.task_group: TaskGroup = None

        self._logger = None
        self._stop_heartbeating = anyio.create_event()
        self._dispatches_handled = Counter()

        # used for zlib-streaming
        self._databuffer = bytearray()
        self._decompressor = zlib.decompressobj()

    @property
    def logger(self) -> logging.Logger:
        """
        :return: The gateway-specific logger.
        """
        if self._logger:
            return self._logger

        self._logger = logging.getLogger("curious.gateway:shard-{}".format(self.session.shard_id))
        return self._logger

    async def close(self, code: int = 1000, reason: str = "Client closed connection", *,
                    reconnect: bool = False, clear_session_id: bool = True,
                    forceful: bool = False):
        """
        Close the current websocket connection.

        :param code: The close code.
        :param reason: The close reason.
        :param reconnect: If we should reconnect.
        :param clear_session_id: If we should clear the session ID.
        :param forceful: If the websocket should be forcefully closed.
        """
        if self.websocket is not None:
            await self.websocket.close(code=code, reason=reason, kill=not reconnect)
                                       # forceful=True)
        # this kills the websocket
        await self._stop_heartbeating.set()

        if clear_session_id:
            self.session.session_id = None
            # also clear heartbeats so we don't immediately HEARTBEAT with the wrong hb
            self.session.sequence = None
            self.heartbeat_stats.heartbeats = 0
            self.heartbeat_stats.heartbeat_acks = 0

    # send commands
    async def send(self, data: dict) -> None:
        """
        Sends data down the websocket.
        """
        dumped = json.dumps(data)
        return await self.websocket.send_text(dumped)

    async def send_identify(self) -> None:
        """
        Sends an IDENTIFY to Discord.
        """
        payload = {
            "op": GatewayOp.IDENTIFY,
            "d": {
                "token": self.session.token,
                "properties": {
                    "$os": sys.platform,
                    "$browser": "curious",
                    "$device": "curious",
                    "$referrer": "",
                    "$referring_domain": ""
                },
                "large_threshold": 250,
                "v": self.GATEWAY_VERSION,
                "shard": [self.session.shard_id, self.session.shard_count]
            }
        }
        return await self.send(payload)

    async def send_heartbeat(self) -> None:
        """
        Sends a heartbeat to Discord.
        """
        # increment the stats
        self.heartbeat_stats.heartbeats += 1
        self.heartbeat_stats.last_heartbeat_time = time.monotonic()

        if self.heartbeat_stats.heartbeats > self.heartbeat_stats.heartbeat_acks + 1\
                and self.session.session_id is not None and self.session.authenticated:
            self.logger.warning("Connection has zombied, reconnecting.")

            # Note: The 1006 close code signifies an error.
            # In my testing, closing with a 1006 will allow a resume once reconnected,
            # whereas other close codes won't.
            # The timeout mihgt be too high to RESUME, however.
            return await self.close(code=1006, reason="Zombied connection", reconnect=True,
                                    clear_session_id=False, forceful=True)

        self.logger.debug("Heartbeating with sequence {}".format(self.session.sequence))
        payload = {
            "op": GatewayOp.HEARTBEAT,
            "d": self.session.sequence
        }
        return await self.send(payload)

    async def send_resume(self) -> None:
        """
        Sends a RESUME to Discord, attempting to resume the connection from where we left off.
        """
        payload = {
            "op": GatewayOp.RESUME,
            "d": {
                "token": self.session.token,
                "session_id": self.session.session_id,
                "seq": self.session.sequence
            }
        }
        return await self.send(payload)

    async def send_guild_chunks(self, guild_ids: List[int]) -> None:
        """
        Sends GUILD_MEMBER_CHUNK packets to Discord.
        """
        payload = {
            "op": GatewayOp.REQUEST_MEMBERS,
            "d": {
                "guild_id": list(map(str, guild_ids)),
                "query": "",
                "limit": 0
            }
        }

        return await self.send(payload)

    async def send_status(self, *, status: int = None, name: str = None, url: str = None,
                          type_: int = None):
        """
        Sends a PRESENCE_UPDATE.

        :param status: The int status to send.
        :param name: The name of the status to send.
        :param url: The URL to include if applicable.
        :param type_: The type of the status to send.
        """
        payload = {
            "op": GatewayOp.PRESENCE,
            "d": {
                "afk": False,  # needed
                "since": 42069,  # also needed but is bullshit because discord gives 4001 if missing
            }
        }
        if status is not None:
            payload["d"]["status"] = status

        if name is not None:
            game = {
                "name": name,
                "type": type_
            }
            if url is not None:
                game["url"] = url

            payload["d"]["game"] = game

        return await self.send(payload)

    async def open(self) -> None:
        """
        Opens a new connection to Discord.

        .. warning::

            This only opens the websocket.
        """
        self.logger.info("Using universal wrapper for the gateway")

        # new websocket means zlib starts from scratch
        self._databuffer.clear()
        self._decompressor = zlib.decompressobj()

        self.websocket = UniversalWrapper(self.session.gateway_url, self.task_group)

    async def events(self) -> AsyncGenerator[None, Any]:
        """
        Returns an async generator used to iterate over the events received by this websocket.
        """
        async with finalise(self.websocket.run()) as agen:
            async for event in agen:
                if isinstance(event, Closing):
                    await self._stop_heartbeat_events()
                    self.logger.info("The websocket has closed")
                    yield "websocket_closed", event.code, event.reason

                elif isinstance(event, Connecting):
                    self.logger.info("The websocket is opening...")
                    # we need to reset the data buffer and zlib inflater
                    self._databuffer.clear()
                    self._decompressor = zlib.decompressobj()
                    yield "websocket_opened", event.url

                elif isinstance(event, Connected):
                    self.logger.info("The websocket has connected")
                    self.session.authenticated = False
                    yield "websocket_connected", event.url, event.proxy

                elif isinstance(event, (Text, Binary)):
                    gen = self.handle_data_event(event)
                    async with finalise(gen) as agen:
                        async for i in agen:
                            yield i

    async def _start_heatbeat_events(self, heartbeat_interval: float):
        """
        Starts heartbeating.

        :param heartbeat_interval: The number of seconds between each heartbeat.
        """
        if self._stop_heartbeating.is_set():
            self._stop_heartbeating.clear()

        async def heartbeater() -> None:
            while True:
                try:
                    async with anyio.fail_after(heartbeat_interval):
                        await self._stop_heartbeating.wait()
                except TimeoutError:
                    pass
                else:
                    break

                try:
                    await self.send_heartbeat()
                except (WebSocketClosing, WebSocketClosed, WebSocketUnavailable):
                    return

        await self.task_group.spawn(heartbeater)

    async def _stop_heartbeat_events(self, *, reset_counts: bool = False) -> None:
        """
        Cancels any current heartbeat events.
        """
        await self._stop_heartbeating.set()
        # reset our heartbeat count
        self.heartbeat_stats.heartbeats = 0
        self.heartbeat_stats.heartbeat_acks = 0

    async def handle_data_event(self, evt: Union[Text, Binary]):
        """
        Handles a data event.
        """
        if evt.name == "binary":
            self._databuffer.extend(evt.data)
            if not evt.data.endswith(self.ZLIB_FLUSH_SUFFIX):
                return
            else:
                data = self._decompressor.decompress(self._databuffer).decode('utf-8')
                self._databuffer.clear()
        else:
            data = evt.text

        # empty payloads
        if not data:
            return

        decoded = json.loads(data)
        opcode = decoded.get('op')
        sequence = decoded.get('s')
        event_data = decoded.get('d', {})

        # update sequence number for dispatches
        if sequence is not None:
            self.session.sequence = sequence

        # switch based on opcode
        if opcode == GatewayOp.HELLO:
            heartbeat_interval = event_data.get("heartbeat_interval", 45000) / 1000.0
            self.logger.debug("Heartbeating every {} seconds.".format(heartbeat_interval))
            await self._stop_heartbeat_events(reset_counts=False)
            await self.send_heartbeat()
            await self._start_heatbeat_events(heartbeat_interval)
            trace = ", ".join(event_data["_trace"])
            self.logger.info(f"Connected to Discord server(s) '{trace}'")

            try:
                if self.session.session_id is None:
                    self.logger.info("Sending IDENTIFY...")
                    await self.send_identify()
                else:
                    self.logger.info("We already have a session ID, Sending RESUME...")
                    await self.send_resume()
            except (WebSocketClosing, WebSocketClosed):
                # got killed during a reconnect, so we'll retry after the reconnect
                pass

            # give an event down here instead of above
            # this means that we're all done when we go to give off our event
            yield ("gateway_hello", event_data['_trace'])

        elif opcode == GatewayOp.HEARTBEAT:
            await self.send_heartbeat()
            yield "gateway_heartbeat_received",

        elif opcode == GatewayOp.HEARTBEAT_ACK:
            self.logger.debug("Received heartbeat_ack")
            self.heartbeat_stats.heartbeat_acks += 1
            self.heartbeat_stats.last_ack_time = time.monotonic()
            yield "gateway_heartbeat_ack",

        elif opcode == GatewayOp.INVALIDATE_SESSION:
            # the data sent is if we should resume
            # if it's non-existent, we assume it's False.
            should_resume = data or False

            if should_resume is True:
                self.logger.debug("Sending RESUME again")
                await self.send_resume()
            else:
                self.logger.warning("Received INVALIDATE_SESSION with d False, re-identifying.")
                self.session.sequence = 0
                self.heartbeat_stats = HeartbeatStats()
                self.session.session_id = None
                await self.send_identify()

            yield ("gateway_invalidate_session", should_resume,)

        elif opcode == GatewayOp.DISPATCH:
            event = decoded.get("t")
            if not event:
                return

            if event == "READY":
                self.session.authenticated = True
                # hijack the session id
                self.session.session_id = event_data["session_id"]

            self._dispatches_handled[event] += 1
            yield ("gateway_dispatch_received", event, event_data,)

        elif opcode == GatewayOp.RECONNECT:
            self.logger.info("Being asked to reconnect...")
            await self.close(code=1000, reason="Server asked to reconnect",
                             reconnect=True, clear_session_id=False)

        else:
            try:
                self.logger.warning("Unhandled opcode: {} ({})".format(opcode, GatewayOp(opcode)))
            except ValueError:
                self.logger.warning("Unknown opcode: {}".format(opcode))


@asynccontextmanager
@safe_generator
async def open_websocket(token: str, url: str, *,
                         shard_id: int = 0, shard_count: int = 1) \
        -> AsyncContextManager[GatewayHandler]:
    """
    Opens a new connection to Discord.

    This is an async context manager; for example, using Trio for nursery management:

    .. code-block:: python3

        async with trio.open_nursery() as nursery:
            async with open_websocket(token, url) as gateway:
                # example for changing presence
                nursery.start_soon(some_gw_handler, gateway)

                async for event in gateway.events():
                    # handle events, etc.
                    ...


    :param token: The token to connect to Discord with.
    :param url: The gateway URL to connect with.
    :param shard_id: The shard ID to connect with. Defaults to 0.
    :param shard_count: The number of shards to boot with.
    :return: An async context manager that yields a :class:`.GatewayHandler`.
    """
    params = f"/?v={GatewayHandler.GATEWAY_VERSION}&encoding=json&compress=zlib-stream"
    url = url + params
    state = _GatewayState(token=token, gateway_url=url, shard_id=shard_id, shard_count=shard_count)
    gw = GatewayHandler(session=state)

    logger = logging.getLogger(f"curious.gateway:shard-{shard_id}")

    async with anyio.create_task_group() as tg:
        gw.task_group = tg
        try:
            logger.info("Opening gateway connection to %s", url)
            await gw.open()
            yield gw
        finally:
            # make sure we don't die on closing the task group
            await gw._stop_heartbeating.set()
            await gw.close(code=1000, reason="Closing bot", reconnect=False)
            await tg.cancel_scope.cancel()
