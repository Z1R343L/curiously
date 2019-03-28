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
Magic proxy-variables that are used to automatically grab attributes from the current context.
"""
from typing import Union

from curious.commands.context import current_command_context as curr
from curious.dataclasses.channel import Channel
from curious.dataclasses.guild import Guild
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.user import User
from curious.util import ContextVarProxy

__all__ = [
    "author",
    "channel",
    "message",
    "guild",
]

uu = Union[User, Member]

#: The author magic-variable.
author: Union[uu, ContextVarProxy[uu]] = ContextVarProxy(curr, attrib="author")  # type: ignore

#: The channel magic-variable.
channel: Union[Channel, ContextVarProxy[Channel]] = ContextVarProxy(curr, attrib="channel")  # type: ignore

#: The message magic-variable.
message: Union[Message, ContextVarProxy[Message]] = ContextVarProxy(curr, attrib="message")  # type: ignore

#: The guild magic-variable.
guild: Union[Guild, ContextVarProxy[Guild]] = ContextVarProxy(curr, attrib="guild")  # type: ignore
