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
import typing
from dataclasses import dataclass

from curious.core import current_bot

T = typing.TypeVar("T")


@dataclass
class Token(object):
    """
    Represents a token that can be used to restore the previous state of a BotVar.
    """
    var: 'BotVar'
    previous: typing.Any
    consumed: bool = False


class BotVar(object):
    """
    Represents a variable that is local to one paticular bot running in the current thread.

    This is like a context variable, and exposes the same API - but instead of being task-local,
    it stores data on the current :class:`.Client` instance's "bot data".

    .. warning::

        This diverges from ContextVar behaviour slightly, in that the default is stored upon
        first access if it did not exist previously.

    """
    _NO_DEFAULT = object()

    def __init__(self, name: str, *, default: T = _NO_DEFAULT):
        """
        :param name: The name of this BotVar.
        :param default: The default value for this BotVar.
        """
        self._name = name
        self._default = default

    def __hash__(self):
        return hash(self._name)

    def __eq__(self, other):
        if not isinstance(other, BotVar):
            return NotImplemented

        return self._name == other._name

    def get(self) -> T:
        """
        Gets the value stored in this BotVar.

        :return: The value this BotVar was assigned to previously.
        """
        bot = current_bot.get()
        try:
            return bot._bot_locals[self]
        except KeyError:
            if self._default is not self._NO_DEFAULT:
                return self._default

            raise LookupError(self)

    def set(self, value: T) -> Token:
        """
        Sets the value of this BotVar.

        :param value: The BotVar to use.
        :return: A :class:`.Token` that can be used to reset this.
        """
        bot = current_bot.get()
        try:
            previous = self.get()
        except LookupError:
            previous = self._NO_DEFAULT

        bot._bot_locals[self] = value
        t = Token(var=self, previous=previous, consumed=False)
        return t

    def reset(self, token: Token) -> None:
        """
        Resets this BotVar to a previous state.

        :param token: The :class:`.Token` to reset. Must not be consumed.
        """
        if token.consumed:
            raise RuntimeError("This token is already consumed")

        if token.var is not self:
            raise RuntimeError("This token is not ours")

        bot = current_bot.get()
        if token.previous is self._NO_DEFAULT:
            bot._bot_locals.pop(self, None)
        else:
            bot._bot_locals[self] = token.previous

        token.consumed = True

