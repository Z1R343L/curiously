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
import contextlib
import enum
import json
import os
import struct
import uuid
from io import BytesIO
from typing import AsyncContextManager, Optional, Union

import anyio

from curious.dataclasses.presence import RichActivity


class IPCOpcode(enum.IntEnum):
    """
    Represents an IPC opcode.
    """

    HANDSHAKE = 0
    FRAME = 1
    CLOSE = 2
    PING = 3
    PONG = 4


class IPCError(Exception):
    """
    Represents a generic IPC error.
    """


class IPCClosed(IPCError):
    """
    Raised when the IPC socket sends a close frame.
    """

    def __init__(self, data):
        self.data = data


class IPCCommandError(IPCError):
    """
    Raised when an IPC command returns an error.
    """

    def __init__(self, code: int, message: str, nonce: str):
        self.code = code
        self.message = message
        self.nonce = nonce

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def __repr__(self) -> str:
        return self.__str__()


class IPCPacket(object):
    """
    Represents an IPC packet.
    """

    def __init__(self, opcode: IPCOpcode, data: dict):
        """
        :param opcode: The :class:`.IPCOpcode` for this packet.
        :param data: A dict of data enclosed in this packet.
        """
        self.opcode = opcode
        self._json_data = data

    @staticmethod
    def _pack_json(data: dict) -> str:
        """
        Packs JSON in a compact representation.
        :param data: The data to pack.
        """
        return json.dumps(data, indent=None, separators=(",", ":"))

    # properties
    @property
    def event(self) -> str:
        """
        Gets the event for this packet. Received packets only.
        """
        return self._json_data["evt"]

    @property
    def cmd(self) -> str:
        """
        Gets the command for this packet.
        """
        return self._json_data["cmd"]

    @property
    def nonce(self) -> uuid.UUID:
        """
        Gets the nonce for this packet.
        """
        return uuid.UUID(self._json_data["nonce"])

    @property
    def data(self) -> Union[str, dict]:
        """
        Gets the inner data for this packet.
        """
        return self._json_data["data"]

    def serialize(self) -> bytes:
        """
        Serializes this packet into a series of bytes.
        """
        buf = BytesIO()
        # Add opcode - little endian (why not network order?)
        buf.write(self.opcode.to_bytes(4, byteorder="little"))
        data = self._pack_json(self._json_data)
        # Add data length - little endian (why not network order?)
        buf.write(len(data).to_bytes(4, byteorder="little"))
        # Add data - string, obviously
        buf.write(data.encode("utf-8"))
        return buf.getvalue()

    @classmethod
    def deserialize(cls, data: bytes):
        """
        Deserializes a full packet.

        This method is not usually what you want.
        """
        opcode, length = struct.unpack("<ii", data[:8])
        raw_data = data[8:].decode("utf-8")

        if len(raw_data) != length:
            raise ValueError("Got invalid length.")

        return IPCPacket(IPCOpcode(opcode), json.loads(raw_data))


class IPCClient(object):
    """
    Represents an IPC client - used for interprocess communication with the Discord client.

    IPC is used for displaying Rich Presence on user accounts.
    """

    VERSION = 1

    @staticmethod
    def get_nonce() -> str:
        """
        Gets a random nonce.
        """
        return str(uuid.uuid4())

    def __init__(self, client_id: int, *, slot: int = 0, uid: Optional[int] = None):
        self._client_id = client_id
        self._slot = slot
        self._uid = uid

        if self._uid is None:
            self._uid = os.getuid()

        self._url = f"/run/user/{self._uid}/discord-ipc-{self._slot}"

        self._sock: anyio.SocketStream = None

    async def _write_packet(self, data: IPCPacket):
        """
        Writes an IPC packet to the stream.

        :param data: The packet to send.
        """
        data = data.serialize()
        await self._sock.send_all(data)

    async def read_packet(self) -> IPCPacket:
        """
        Reads a single packet off the IPC stream.

        :return: A :class:`.IPCPacket` representing the data that has been read.
        """
        size = await self._sock.receive_exactly(8)

        opcode, length = struct.unpack("<ii", size)
        body = await self._sock.receive_exactly(length)
        body_data = json.loads(body.decode("utf-8"))

        packet = IPCPacket(IPCOpcode(opcode), body_data)

        opcode = IPCOpcode(opcode)
        if opcode is IPCOpcode.CLOSE:
            await self.close()
            print(packet._json_data)
            raise IPCClosed(packet.data)

        return packet

    async def connect(self) -> None:
        """
        Connects this IPC client. For internal usage only.
        """
        # TODO: Windows named pipes. Needs lib-specific support.
        self._sock = await anyio.connect_unix(self._url)

    async def close(self) -> None:
        """
        Closes this IPC client.
        """
        if self._sock is not None:
            await self._sock.close()

    async def handshake(self) -> None:
        """
        Performs the opening IPC handshake.
        """
        handshake = {"v": self.VERSION, "client_id": str(self._client_id)}
        packet = IPCPacket(IPCOpcode.HANDSHAKE, handshake)
        await self._write_packet(packet)

        next_packet = await self.read_packet()
        if next_packet.event != "READY":
            await self.close()
            raise IPCError(f"Got {next_packet.event} instead of READY")

    async def send_rich_presence(self, presence: RichActivity) -> IPCPacket:
        """
        Sends a rich presence down this IPC channel.

        :param presence: The :class:`.RichActivity` to send.
        """
        data = {
            "cmd": "SET_ACTIVITY",
            "args": {"pid": os.getpid(), "activity": presence.to_dict()},
            "nonce": self.get_nonce(),
        }
        packet = IPCPacket(IPCOpcode.FRAME, data)
        await self._write_packet(packet)

        next_packet = await self.read_packet()
        if next_packet.event is not None and next_packet.event.lower() == "error":
            raise IPCCommandError(
                code=next_packet.data.get("code"),
                message=next_packet.data.get("message"),
                nonce=next_packet.data.get("nonce"),
            )

        return next_packet


@contextlib.asynccontextmanager
async def open_ipc_client(
    client_id: int, *, slot: int = 0, uid: Optional[int] = None
) -> AsyncContextManager[IPCClient]:
    """
    Opens a new IPC client. This is an async context manager; use it like so:

    .. code-block:: python3

        async with open_ipc_client() as client:
            ...

    :param client_id: The client ID of the application associated with this presence.
    :param slot: The client slot to use. Use 0 unless you have a good reason.
    :param uid: The UID to use. Can be used to override what UID should be passed in.
    """
    client = IPCClient(client_id=client_id, slot=slot, uid=uid)
    await client.connect()
    try:
        await client.handshake()
        yield client
    finally:
        await client.close()
