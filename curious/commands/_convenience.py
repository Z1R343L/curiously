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
Convenience functions that are shortcuts for various context variable actions.
"""
from os import PathLike
from typing import IO, Union

from curious.commands.context import Context, current_command_context
from curious.dataclasses.message import Message

__all__ = [
    "send_message",
    "upload",
]


async def send_message(content: str, **kwargs) -> Message:
    """
    Sends a message to the channel this command is running in.

    This passes arguments straight through to :meth:`.ChannelMessageWrapper.send`.

    :return: A :class:`.Message` that was sent to the channel.
    """
    ctx: Context = current_command_context.get()
    return await ctx.channel.messages.send(content=content, **kwargs)


async def upload(fp: 'Union[bytes, str, PathLike, IO]', **kwargs) -> Message:
    """
    Uploads a message to the channel this command is running in.

    This passes arguments straight through to :meth:`.ChannelMessageWrapper.upload`.

    :return: A :class:`.Message` that was sent to the channel.
    """
    ctx: Context = current_command_context.get()
    return await ctx.channel.messages.upload(fp=fp, **kwargs)
