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
Classes for the audit log.

.. currentmodule:: curious.dataclasses.auditlog
"""
import enum
from typing import Any, List, Optional, Union

from curious.dataclasses import channel as md_channel, guild as md_guild, member as md_member, \
    permissions as dt_permissions, role as md_role
from curious.dataclasses.bases import Dataclass
from curious.dataclasses.user import User


class AuditLogEvent(enum.IntEnum):
    """
    Represents an audit log event.
    """
    GUILD_UPDATE = 1

    CHANNEL_CREATE = 10
    CHANNEL_UPDATE = 11
    CHANNEL_DELETE = 12

    CHANNEL_OVERWRITE_CREATE = 13
    CHANNEL_OVERWRITE_UPDATE = 14
    CHANNEL_OVERWRITE_DELETE = 15

    MEMBER_KICK = 20
    MEMBER_PRUNE = 21
    MEMBER_BAN_ADD = 22
    MEMBER_BAN_REMOVE = 23
    MEMBER_UPDATE = 24
    MEMBER_ROLE_UPDATE = 25

    ROLE_CREATE = 30
    ROLE_UPDATE = 31
    ROLE_DELETE = 32

    INVITE_CREATE = 40
    INVITE_UPDATE = 41
    INVITE_DELETE = 42

    WEBHOOK_CREATE = 50
    WEBHOOK_UPDATE = 51
    WEBHOOK_DELETE = 52

    EMOJI_CREATE = 60
    EMOJI_UPDATE = 61
    EMOJI_DELETE = 62

    MESSAGE_DELETE = 72


# wish this could be a dataclass, but it needs casting for some stuff...
class AuditLogExtra:
    """
    Represents any extra information for this audit log entry.
    """

    @staticmethod
    def _maybe_int(val: str):
        if val is None:
            return None

        return int(val)

    def __init__(self, entry: 'AuditLogEntry', **kwargs):
        self._entry = entry

        #: The ID of an overwritten entity.
        self.id: Optional[int] = self._maybe_int(kwargs.get("id"))

        #: The number of members removed by a prune.
        _members_removed = kwargs.get
        self.members_removed: Optional[int] = self._maybe_int(kwargs.get("members_removed"))

        #: The number of messages deleted by a mass delete.
        self.count: Optional[int] = self._maybe_int(kwargs.get("count"))

        #: The type of an overwritten entity ("member" or "role").
        self.type: Optional[str] = kwargs.get("type")

        #: The name of a role if type is "role".
        self.role_name: Optional[str] = kwargs.get("role_name")

        _channel_id = kwargs.get("channel_id")
        if _channel_id is not None:
            _channel_id = int(_channel_id)

        #: The channel ID in which messages are deleted.
        self.channel_id: Optional[int] = _channel_id

    @property
    def channel(self) -> 'Optional[md_channel.Channel]':
        """
        :return: The :class:`.Channel` if this extras has a channel_id.
        """
        return self._entry._bot.state.find_channel(self.channel_id)

    @property
    def member(self) -> 'Optional[md_member.Member]':
        """
        :return: The :class:`.Member` if this extras has a member.
        """
        if self.type == "member":
            return self._entry._guild.members[self.id]

    @property
    def role(self) -> 'Optional[md_role.Role]':
        """
        :return: The :class:`.Role` if this extras has a role.
        """
        if self.type == "role":
            return self._entry._guild.roles[self.id]


class AuditLogChange(object):
    """
    Represents an audit log change.
    """

    def __init__(self, entry: 'AuditLogEntry', **data):
        # have to init here due to circular imports
        self.basic_converters = {
            "mfa_level": md_guild.MFALevel,
            "verification_level": md_guild.VerificationLevel,
            "explicit_content_filter": md_guild.ContentFilterLevel,
            "application_id": int,
            "allow": dt_permissions.Permissions,
            "deny": dt_permissions.Permissions,
            "permissions": dt_permissions.Permissions,
            "id": int  # this is functionally useless to us
        }

        self._entry = entry
        self._data = data

    @property
    def old_value(self) -> Any:
        """
        The old value of this change, if any.

        .. note::

            This will attempt to automatically unmap ID objects, but will return the ID if that
            fails.

        """
        return self._unmap("old_value")

    @property
    def new_value(self) -> Any:
        """
        The new value of this change, if any.

        .. note::

            This will attempt to automatically unmap ID objects, but will return the ID if that
            fails.
        """
        return self._unmap("new_value")

    @property
    def key(self) -> str:
        """
        The key for this change.
        """
        return self._data.get("key")

    def _unmap(self, item: str):
        """
        Unmaps the Discord JSON into a real object.
        """
        item = self._data.get(item)
        key = self._data.get("key")

        # switch on key
        if key in self.basic_converters:
            return self.basic_converters[item]

        if key == "permissions_overwrites":
            overwrites = []
            for i in item:
                object_id = int(i["id"])
                if i["type"] == "role":
                    obb = self._entry._guild.roles.get(object_id)
                else:
                    obb = self._entry._view._try_unwrap_member(object_id)

                overwrites.append(dt_permissions.Overwrite(
                    allow=i["allow"], deny=i["deny"],
                    channel_id=self._entry.target_id,
                    obb=obb
                ))

            return overwrites

        if key in ["$add", "$remove"]:
            roles = []
            for i in item:
                role = self._entry._guild.roles[int(i["id"])]
                if role is None:
                    roles.append(i["name"])  # TODO: Make this better?

            return roles

        if key in ["owner_id", "inviter_id"]:
            return self._entry._view._try_unwrap_member(int(item))

        if key in ["widget_channel_id", "afk_channel_id", "channel_id"]:
            return self._entry._guild.channels.get(item)

        # just pass-through the item directly
        return item


class AuditLogEntry(Dataclass):
    """
    Represents an audit log entry.
    """

    def __init__(self, view: 'AuditLogView', **kwargs):
        super().__init__(kwargs['id'], view._guild._bot)
        self._view = view
        self._guild = view._guild

        #: The ID of the user who made the change.
        self.user_id: int = int(kwargs.get("user_id"))

        #: The reason for the change, if any.
        self.reason: str = kwargs.get("reason")

        _target_id = kwargs.get("target_id")
        if _target_id is not None:
            _target_id = int(_target_id)
        #: The ID of the user targeted, if any.
        self.target_id: int = _target_id

        #: The audit log event for this entry.
        self.event = AuditLogEvent(kwargs.get("action_type"))

        #: The "extra" options for this entry.
        self.extra_options = AuditLogExtra(view._guild._bot, **kwargs.get("options", {}))

        #: The changes for this entry.
        self.changes: List[AuditLogChange] = \
            [AuditLogChange(self, **i) for i in kwargs.get("changes", [])]

    def __repr__(self):
        return f"<AuditLogEntry guild='{self._guild!r} author={self.author!r} event={self.event}>"

    __str__ = __repr__

    @property
    def author(self) -> 'Union[User, md_member.Member]':
        """
        The author of this log entry.
        """
        return self._view._try_unwrap_member(self.user_id)


class AuditLogView(object):
    """
    Represents a view into an audit log.
    """

    def __init__(self, guild, **kwargs):
        self._guild = guild

        #: The list of audit log entries for this view.
        self.entries: List[AuditLogEntry] \
            = [AuditLogEntry(self, **x) for x in kwargs.get("audit_log_entries")]

        #: The list of users for this view.
        self._users = [User(guild._bot, **data) for data in kwargs.get("users")]

    def __repr__(self):
        return f"<AuditLogView entries={self.entries!r}>"

    __str__ = __repr__

    def _try_unwrap_member(self, id: int) -> 'Union[User, md_member.Member]':
        """
        Tries to unwrap an ID into a member or user.
        """
        try:
            return self._guild.members[id]
        except KeyError:
            member = self._guild._bot.state._users.get(id)
            if member is None:
                return next(filter(lambda user: user.id == id, self._users))
            else:
                return member
