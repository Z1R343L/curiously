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
Class for the commands context.

.. currentmodule:: curious.commands.context
"""
import inspect
import types
import typing_inspect
from dataclasses import dataclass
from typing import Any, Callable, List, Tuple, Type, Union

from curious.commands.converters import convert_channel, convert_float, convert_int, convert_list, \
    convert_member, convert_role, convert_union
from curious.commands.exc import CommandInvokeError, CommandNotFound, CommandsError, \
    ConditionFailedError
from curious.commands.plugin import Plugin
from curious.commands.utils import _convert
from curious.core import get_current_client
from curious.core.event import EventContext, current_event_context
from curious.dataclasses.channel import Channel
from curious.dataclasses.guild import Guild
from curious.dataclasses.member import Member
from curious.dataclasses.message import Message
from curious.dataclasses.role import Role
from curious.dataclasses.user import User


@dataclass()
class ConditionStatus:
    # I wish this was a sum type
    success: bool

    # non-None only if success is False
    message: str = "Unknown error."
    condition = None
    # non-None if an inner command re-raised
    inner: Exception = None


class Context(object):
    """
    A class that represents the context for a command.
    """
    _converters = {
        Channel: convert_channel,
        Member: convert_member,
        Role: convert_role,
        # Guild: _convert_guild,
        List: convert_list,
        Union: convert_union,
        str: lambda ann, ctx, arg: arg,
        int: convert_int,
        float: convert_float,
    }

    def __init__(self, message: Message):
        """
        :param message: The :class:`.Message` this command was invoked with.
        """
        #: The message for this context.
        self.message = message

        #: The extracted command name for this context.
        self.root_command_name: str = None

        #: The subcommand chain for this context.
        self.subcommand_chain: List[str] = []

        #: The argument tokens for this context.
        self.tokens = []  # type: List[str]

        #: The full tokens for this context.
        self.full_tokens: List[str] = []

        #: The command object that has been matched.
        self.command_object: 'Callable[[Context, ...], Any]' = None

        #: The plugin for this context.
        self.plugin: Plugin = None

        #: The manager for this context.
        self.manager = None

    @classmethod
    def add_converter(cls, type_: Type[Any], converter):
        """
        Adds a converter to the mapping of converters.

        :param type_: The type to convert to.
        :param converter: The converter callable.
        """
        cls._converters[type_] = converter

    @property
    def guild(self) -> Guild:
        """
        :return: The :class:`.Guild` for this context, or None.
        """
        return self.message.guild

    @property
    def channel(self) -> Channel:
        """
        :return: The :class:`.Channel` for this context.
        """
        return self.message.channel

    @property
    def author(self) -> Union[Member, User]:
        """
        :return: The :class:`.Member` or :class:`.User` for this context.
        """
        return self.message.author

    @property
    def command_name(self) -> str:
        """
        :return: In the case of subcommands, returns the true command name.
        """
        if self.subcommand_chain:
            return self.subcommand_chain[-1]

        return self.root_command_name

    async def can_run(self, cmd) -> ConditionStatus:
        """
        Checks if a command can be ran.

        :return: If it can be ran, the error message and the condition that failed (if any).
        """
        result = ConditionStatus(success=True)

        conditions = getattr(cmd, "cmd_conditions", [])
        for condition in conditions:
            if getattr(condition, "cmd_owner_bypass", False) is True:
                ainfo = get_current_client().application_info
                if ainfo is not None:
                    if ainfo.owner.id == self.message.author_id:
                        continue

            try:
                success = condition(self)
                if inspect.isawaitable(success):
                    success = await success
            except CommandsError:
                raise
            except Exception as e:
                result.success = False
                result.error = f"Condition raised exception: {repr(e)}"
                result.condition = condition
                result.inner = e
                break
            else:
                if isinstance(success, bool):
                    success = (success, "Condition failed.")

                if not success[0]:
                    result.success = False
                    result.message = success[1]
                    result.condition = condition
                    break

        return result

    async def run_contained_command(self) -> None:
        """
        Runs the command contained within this context.

        :return: If a command was successfully found.
        """
        # 1) Find the command object
        command_callable = await self.find_command()

        if command_callable is None:
            raise CommandNotFound(self, self.root_command_name)

        self.command_object = command_callable

        # 2) Check if we're ratelimited.
        # This can save any condition roundtrips.
        await self.manager.ratelimiter.ensure_ratelimits(self, command_callable)

        # 3) Check if the command can be ran.
        status = await self.can_run(command_callable)
        if not status.success:
            err = ConditionFailedError(self, status.condition, status.message)
            if status.inner:
                raise err from status.inner

            raise err

        # 4) Convert the arguments.
        converted_args, converted_kwargs = await self._get_converted_args(command_callable)

        # 5) Invoke the command.
        try:
            result = await self._run_command(command_callable, *converted_args, **converted_kwargs)
        except Exception as e:
            raise CommandInvokeError(self) from e

        # 6) Process the result of the command, if available.
        await self._process_result(result)

    async def _process_result(self, result: Any):
        """
        Processes the result of a command.

        By default, this does nothing.
        """

    async def find_command(self):
        """
        Attempts to find the specific command being called.

        This will alter :attr:`.Context.tokens`, consuming them all.
        """
        root_command = self.manager.lookup_command(self.root_command_name)

        if not root_command:
            return

        matched_command = root_command
        current_command = root_command
        # used for subcommands only
        self_ = None
        if hasattr(current_command, "__self__"):
            self_ = current_command.__self__

        self.plugin = self_

        while True:
            if not current_command.cmd_subcommands:
                break

            if not self.tokens:
                break

            token = self.tokens[0]
            for command in current_command.cmd_subcommands:
                if command.cmd_name == token or token in command.cmd_aliases:
                    matched_command = command
                    current_command = command
                    # update tokens so that they're consumed
                    self.tokens = self.tokens[1:]
                    self.subcommand_chain.append(token)
                    break
            else:
                # we didnt match any subcommand
                # so escape the loop now
                break

        # bind method, if appropriate
        if not hasattr(matched_command, "__self__") and self_ is not None:
            matched_command = types.MethodType(matched_command, self_)

        return matched_command

    def _lookup_converter(self, annotation: Type[Any]) -> 'Callable[[Any, Context, str], Any]':
        """
        Looks up a converter for the specified annotation.
        """
        origin = typing_inspect.get_origin(annotation)
        if origin is not None:
            annotation = origin

        if annotation in self._converters:
            return self._converters[annotation]

        if annotation is inspect.Parameter.empty:
            return lambda ann, ctx, i: i

        # str etc
        if callable(annotation):
            return annotation

        return lambda ann, ctx, i: i

    async def _get_converted_args(self, func) -> Tuple[tuple, dict]:
        """
        Gets the converted args and kwargs for this command, based on the tokens.
        """

        return await _convert(self, self.tokens, inspect.signature(func))

    def _make_reraise_ctx(self, new_name: str) -> EventContext:
        """
        Makes a new :class:`.EventContext` for re-dispatching.
        """
        old_ctx = current_event_context()
        new = EventContext(old_ctx.shard_id, new_name)
        new.original_context = old_ctx
        return new

    async def _run_command(self, cbl, *args, **kwargs):
        """
        Overridable method that allows doing something before running a command.
        """
        return await cbl(self, *args, **kwargs)
