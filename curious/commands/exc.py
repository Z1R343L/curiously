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
Defines commands-specific exceptions.

.. currentmodule:: curious.commands.exc
"""
import abc
import time
from math import ceil
from typing import Tuple

from curious.exc import CuriousError


class CommandsError(CuriousError, metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def event_name(self) -> str:
        """
        :return: The event name that should be dispatched when this command is received.
        """


class ConditionFailedError(CommandsError):
    """
    Raised when a condition has failed.
    """

    event_name = "command_condition_failed"

    def __init__(self, ctx, condition, message: str):
        self.ctx = ctx
        self.condition = condition
        self.message = message

    def __repr__(self):
        return self.message

    __str__ = __repr__


class MissingArgumentError(CommandsError):
    """
    Raised when a command is missing an argument.
    """

    event_name = "command_missing_argument"

    def __init__(self, ctx, arg):
        self.ctx = ctx
        self.arg = arg

    def __repr__(self) -> str:
        return f"Missing required argument `{self.arg}` in `{self.ctx.command_name}`."

    __str__ = __repr__


class CommandInvokeError(CommandsError):
    """
    Raised when a command has an error during invokation.
    """

    event_name = "command_invoke_failed"

    def __init__(self, ctx):
        self.ctx = ctx

    def __repr__(self) -> str:
        return f"Command {self.ctx.command_name} failed to invoke with error `{self.__cause__}`."

    __str__ = __repr__


class ConversionFailedError(CommandsError):
    """
    Raised when conversion fails.
    """

    event_name = "command_conversion_failed"

    def __init__(self, ctx, arg: str, to_type: type, message: str = "Unknown error"):
        self.ctx = ctx
        self.arg = arg
        self.to_type = to_type
        self.message = message

    def __repr__(self) -> str:
        try:
            name = getattr(self.to_type, "__name__")
        except AttributeError:
            name = repr(self.to_type)

        return f"Cannot convert `{self.arg}` to type `{name}`: {self.message}."

    __str__ = __repr__


class CommandRateLimited(CommandsError):
    """
    Raised when a command is ratelimited.
    """

    event_name = "command_rate_limited"

    def __init__(self, context, func, limit, bucket: Tuple[int, float]):
        self.ctx = context
        self.func = func
        self.limit = limit
        self.bucket = bucket

    def __repr__(self) -> str:
        left = int(ceil(self.bucket[1] - time.monotonic()))
        return (
            f"The command {self.ctx.command_name} is currently rate limited for "
            f"{left} second(s)."
        )

    __str__ = __repr__


class CommandNotFound(CommandsError):
    """
    Raised when a command is not found.
    """

    event_name = "command_not_found"

    def __init__(self, context, name: str):
        self.ctx = context
        self.name = name

    def __repr__(self):
        return f"Command not found: {self.name}"
