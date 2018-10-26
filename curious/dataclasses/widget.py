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
Wrappers for Widget objects.

.. currentmodule:: curious.dataclasses.widget
"""
from types import MappingProxyType
from typing import Mapping, MutableMapping, Union

from curious.core import get_current_client
from curious.dataclasses import channel as dt_channel, guild as dt_guild
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.presence import Game, Status


class WidgetChannel(Dataclass):
    """
    Represents a limited subsection of a channel.
    """

    def __init__(self, guild: 'WidgetGuild', **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)))

        #: The name of this channel.
        self.name = kwargs.get("name")

        #: The position of this channel.
        self.position = kwargs.get("position", -1)

        #: The guild ID for this channel.
        self.guild_id = guild.id

        #: The :class:`.WidgetGuild` for this channel.
        self.guild = guild


class WidgetMember(Dataclass):
    """
    Represents a limited subsection of a member.
    """

    def __init__(self, guild: 'WidgetGuild', kwargs):
        super().__init__(id=int(kwargs.get("id", 0)))

        # construct a superficial user dict
        user_dict = {
            "id": self.id,
            "name": kwargs.get("name", None),
            "avatar": kwargs.get("avatar", None),
            "discriminator": kwargs.get("discriminator", None),
            "bot": kwargs.get("bot", False)
        }
        #: The :class:`.User` object associated with this member.
        bot = get_current_client()
        self.user = bot.state.make_user(user_dict)
        bot.state._check_decache_user(user_dict["id"])

        #: The :class:`.WidgetGuild` object associated with this member.
        self.guild = guild

        #: The game associated with this member.
        game = kwargs.get("game")
        if game is None:
            game = {}
        self.game = Game(**game) if game else None

        #: The :class:`.Status` associated with this member.
        self.status = Status(kwargs.get("status"))


class WidgetGuild(Dataclass):
    """
    Represents a limited subsection of a guild.
    """

    def __init__(self, **kwargs):
        super().__init__(id=int(kwargs.get("id", 0)))

        #: The name of this guild.
        self.name: str = kwargs.get("name", "")

        #: A mapping of :class:`.WidgetChannel` in this widget guild.
        self._channels: MutableMapping[int, WidgetChannel] = {}
        for channel in kwargs.get("channels", []):
            c = WidgetChannel(bot=get_current_client(), guild=self, **channel)
            self._channels[c.id] = c

        #: A mapping of :class:`.WidgetMember` in this widget guild.
        self._members: MutableMapping[int, WidgetMember] = {}
        for member in kwargs.get("members", []):
            m = WidgetMember(bot=get_current_client(), guild=self, kwargs=member)
            self._members[m.id] = m

    @property
    def channels(self) -> 'Mapping[int, WidgetChannel]':
        """
        :return: A read-only mapping of :class:`.WidgetChannel` representing the channels for \
            this guild. 
        """
        return MappingProxyType(self._channels)

    @property
    def members(self) -> 'Mapping[int, WidgetMember]':
        """
        :return: A read-only mapping of :class:`.WidgetMember` representing the channels for \
            this guild. 
        """
        return MappingProxyType(self._members)

    def __repr__(self) -> str:
        return "<WidgetGuild id={} members={} name='{}'>".format(self.id, len(self.members),
                                                                 self.name)

    __str__ = __repr__


class Widget(object):
    """
    Represents the embed widget for a guild.
    """

    def __init__(self, **kwargs):

        #: The guild ID for this widget.
        self.guild_id = int(kwargs.get("id", 0))

        #: The widget guild for this widget.
        self._widget_guild = WidgetGuild(get_current_client(), **kwargs)

        #: The invite URL that this widget represents.
        self.invite_url = kwargs.get("instant_invite", None)

    @property
    def guild(self) -> 'Union[dt_guild.Guild, WidgetGuild]':
        """
        :return: The guild object associated with this widget.
            If the guild was cached, a :class:`.Guild`. Otherwise, a :class:`.WidgetGuild`.
        """
        try:
            return get_current_client().guilds[self.guild_id]
        except KeyError:
            return self._widget_guild

    @property
    def channels(self) -> 'Mapping[int, Union[dt_channel.Channel, WidgetChannel]]':
        """
        :return: A mapping of channels associated with this widget.
        """
        return self.guild.channels

    def __repr__(self) -> str:
        return "<Widget guild={}>".format(self.guild)
