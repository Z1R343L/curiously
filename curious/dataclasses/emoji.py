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
Wrappers for custom emojis in guilds.

.. currentmodule:: curious.dataclasses.emoji
"""
from typing import List, Optional

from curious.core import get_current_client
from curious.dataclasses import guild as dt_guild, role as dt_role
from curious.dataclasses.bases import Dataclass


class PartialEmoji(Dataclass):
    """
    Represents a partial emoji - an emoji with data missing. Used for reactions if the emoji no
    longer exists, or for :attr:`.Message.emoji` for nitro/removed emojis.
    """

    __slots__ = ("id", "name", "guild_id", "animated")

    def __init__(self, **kwargs) -> None:
        super().__init__(int(kwargs["id"]))

        #: The name of this emoji.
        self.name: str = kwargs.get("name")

        #: The guild ID of this emoji, if any.
        self.guild_id: Optional[int] = kwargs.get("guild_id")

        #: If this emoji is animated.
        self.animated: bool = kwargs.get("animated", False)

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return False

        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self.id} name={self.name}>"

    def __str__(self) -> str:
        animated = ["", "a"][self.animated]
        return f"<:{animated}:{self.name}:{self.id}:>"

    @property
    def guild(self) -> "dt_guild.Guild":
        """
        :return: The :class:`.Guild` this emoji object is associated with.
        """
        return get_current_client().guilds.get(self.guild_id)

    @property
    def url(self) -> str:
        """
        :return: The URL to this emoji.
        """
        cdn_url = f"https://cdn.discordapp.com/emojis/{self.id}"
        if not self.animated:
            return f"{cdn_url}.png"

        return f"{cdn_url}.gif"


class Emoji(PartialEmoji):
    """
    Represents a custom emoji uploaded to a guild.
    """

    @classmethod
    def find(cls, emoji_id: int) -> "Optional[Emoji]":
        """
        Attempts to find an emoji on the current client.
        """
        client = get_current_client()
        for guild in client.guilds.values():
            try:
                return guild.emojis[emoji_id]
            except KeyError:
                continue

        return None

    __slots__ = ("id", "name", "role_ids", "require_colons", "managed", "guild_id", "animated")

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        #: A list of role IDs that this emoji can be used by.
        self.role_ids: List[int] = kwargs.get("roles", [])

        #: If this emoji requires colons to use.
        self.require_colons: bool = kwargs.get("require_colons", False)

        #: If this emoji is managed or not.
        self.managed: bool = kwargs.get("managed", False)

        #: If this emoji is animated or not.
        self.animated: bool = kwargs.get("animated", False)

    async def edit(self, *, name: str = None, roles: "List[dt_role.Role]" = None) -> "Emoji":
        """
        Edits this emoji.

        :param name: The new name of the emoji.
        :param roles: The new list of roles that can use this emoji.
        :return: This emoji.
        """
        if roles is not None:
            roles = [r.id for r in roles]

        await get_current_client().http.edit_guild_emoji(
            guild_id=self.guild_id, emoji_id=self.id, name=name, roles=roles
        )
        return self

    async def delete(self) -> None:
        """
        Deletes this emoji.
        """
        await get_current_client().http.delete_guild_emoji(self.guild_id, emoji_id=self.id)

    @property
    def roles(self) -> "List[dt_role.Role]":
        """
        :return: A list of :class:`.Role` this emoji can be used by.
        """
        if len(self.role_ids) <= 0:
            return [self.guild.default_role]

        return [self.guild.roles[r_id] for r_id in self.role_ids]
