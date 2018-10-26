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
Wrappers for Invite objects.

Invite objects are linked to a real channel and real guild, but Discord does not return the full
data for these objects. Therefore, a few "mini" objects are provided that represent the objects:

 - :class:`.InviteGuild`, which contains the ``name``, ``splash_url`` and ``icon_url`` of the
   Guild.
 - :class:`.InviteChannel`, which contains the ``name`` and ``type`` of the Channel.
 
These objects will be returned on :attr`.Invite.guild` and :attr:`.Invite.channel` respectively
if the data for each  is not cached by curious. Otherwise, full :class:`.Guild` and
:class:`.Channel` objects will be returned.

.. currentmodule:: curious.dataclasses.invite
"""
import datetime
from typing import List, Optional, Union

from curious import util
from curious.core import get_current_client
from curious.dataclasses import channel as dt_channel, guild as dt_guild, member as dt_member, \
    user as dt_user
from curious.dataclasses.bases import Snowflaked
from curious.exc import PermissionsError


class InviteGuild(Snowflaked):
    """
    Represents an InviteGuild - a subset of a guild.
    """

    def __init__(self, **kwargs):
        super().__init__(kwargs.get("id"))

        #: The name of this guild.
        self.name: str = kwargs.get("name", None)

        #: The splash hash of this guild.
        self.splash_hash: str = kwargs.get("splash")

        #: The icon hash of this guild.
        self._icon_hash: str = kwargs.get("icon")

        #: A list of features for this guild.
        self.features: List[str] = kwargs.get("features")

        #: The approximate member count for this guild.
        self.member_count: int = kwargs.get("approximate_member_count")

        #: The approximate presence count.
        self.presence_count: int = kwargs.get("approximate_presence_count")

        #: The number of text channels.
        self.text_channel_count: int = kwargs.get("text_channel_count")

        #: The number of voice channels.
        self.voice_channel_count: int = kwargs.get("voice_channel_count")

    def __repr__(self) -> str:
        return "<InviteGuild id={} name='{}'>".format(self.id, self.name)

    __str__ = __repr__

    @property
    def icon_url(self) -> str:
        """
        :return: The icon URL for this guild, or None if one isn't set.
        """
        if self._icon_hash:
            return "https://cdn.discordapp.com/icons/{}/{}.webp".format(self.id, self._icon_hash)

    @property
    def splash_url(self) -> str:
        """
        :return: The splash URL for this guild, or None if one isn't set.
        """
        if self.splash_hash:
            return "https://cdn.discordapp.com/splashes/{}/{}.webp".format(self.id,
                                                                           self.splash_hash)


class InviteChannel(Snowflaked):
    """
    Represents an InviteChannel - a subset of a channel.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(kwargs.get("id"))

        #: The name of this channel.
        self.name: str = kwargs.get("name")

        #: The :class:`.ChannelType` of this channel.
        self.type: dt_channel.ChannelType = dt_channel.ChannelType(kwargs.get("type"))

    def __repr__(self) -> str:
        return "<InviteChannel name={}>".format(self.name)


class InviteMetadata(object):
    """
    Represents metadata attached to an invite.
    """

    __slots__ = "uses", "max_uses", "max_age", "temporary", "created_at", "revoked",

    def __init__(self, **kwargs) -> None:
        #: The number of times this invite was used.
        self.uses: int = kwargs.get("uses", 0)

        #: The maximum number of uses this invite can use.
        self.max_uses: int = kwargs.get("max_uses", 0)

        #: The maximum age of this invite.
        self.max_age: int = kwargs.get("max_age", 0)

        #: Is this invite temporary?
        self.temporary: bool = kwargs.get("temporary", False)

        #: When was this invite created at?
        self.created_at: datetime.datetime = util.to_datetime(kwargs.get("created_at", None))

        #: Is this invite revoked?
        self.revoked: bool = kwargs.get("revoked", False)


class Invite(object):
    """
    Represents an invite object.
    """

    def __init__(self, **kwargs) -> None:
        #: The invite code.
        self.code: str = kwargs.get("code")

        #: The guild ID for this invite.
        self.guild_id: int = int(kwargs["guild"]["id"])

        #: The channel ID for this invite.
        self.channel_id: int = int(kwargs["channel"]["id"])

        #: The invite guild this is attached to.
        #: The actual guild object can be more easily fetched with `.guild`.
        self._invite_guild = InviteGuild(**kwargs.get("guild"))

        #: The invite channel this is attached to.
        #: The actual channel object can be more easily fetched with `.channel`.
        self._invite_channel = InviteChannel(**kwargs.get("channel"))

        #: The ID of the user that created this invite.
        #: This can be None for partnered invites.
        self.inviter_id: int = None

        if "inviter" in kwargs:
            self._inviter_data = kwargs["inviter"]
            self.inviter_id = int(self._inviter_data.get("id", 0))

        #: The invite metadata object associated with this invite.
        #: This can be None if the invite has no metadata.
        self._invite_metadata: Optional[InviteMetadata] = None

        if "uses" not in kwargs:
            self._invite_metadata = None
        else:
            self._invite_metadata = InviteMetadata(**kwargs)

    def __repr__(self) -> str:
        return "<Invite code={} guild={} channel={}>".format(self.code, self.guild, self.channel)

    def __del__(self) -> None:
        if self.inviter:
            try:
                client = get_current_client()
            except LookupError:  # GC winddown
                return
            client.state._check_decache_user(self.inviter_id)

    @property
    def inviter(self) -> 'Union[dt_member.Member, dt_user.User]':
        """
        :return: The :class:`.Member` or :class:`.User` that made this invite.
        """
        client = get_current_client()

        if isinstance(self._invite_guild, InviteGuild):
            u = client.state.make_user(self._inviter_data)
            client.state._check_decache_user(u.id)
            return u

        u = self.guild.members.get(self.inviter_id)
        if not u:
            u = client.state.make_user(self._inviter_data)
            client.state._check_decache_user(u.id)
            return u

        return u

    @property
    def guild(self) -> 'Union[dt_guild.Guild, InviteGuild]':
        """
        :return: The guild this invite is associated with.
        """
        return get_current_client().state.guilds.get(self.guild_id, self._invite_guild)

    @property
    def channel(self) -> 'Union[dt_channel.Channel, InviteChannel]':
        """
        :return: The channel this invite is associated with.
        """
        g = self.guild
        if g == self._invite_guild:
            return self._invite_channel

        return g.channels.get(self.channel_id, self._invite_channel)

    async def delete(self) -> None:
        """
        Deletes this invite.

        You must have MANAGE_CHANNELS permission in the guild to delete the invite.
        """
        guild = self.guild
        if guild != self._invite_guild:
            if not guild.me.guild_permissions.manage_channels:
                raise PermissionsError("manage_channels")

        await get_current_client().http.delete_invite(self.code)
