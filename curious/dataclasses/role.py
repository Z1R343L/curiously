"""
Wrappers for Role objects.

.. currentmodule:: curious.dataclasses.role
"""

import functools

import curio

from curious.dataclasses import guild as dt_guild, member as dt_member, \
    permissions as dt_permissions
from curious.dataclasses.bases import Dataclass
from curious.exc import PermissionsError


class _MentionableRole(object):
    """
    A wrapper class that makes a role mentionable for a short time period.
    
    .. code-block:: python3
    
        async with role.allow_mentions():
            await ctx.channel.send(role.mention)
            
    """
    def __init__(self, r: 'Role'):
        self.role = r

    def allow_mentions(self):
        return self.role.edit(mentionable=True)

    def disallow_mentions(self):
        return self.role.edit(mentionable=False)

    def __aenter__(self):
        return self.allow_mentions()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disallow_mentions()
        return False


@functools.total_ordering
class Role(Dataclass):
    """
    Represents a role on a server.
    """
    __slots__ = "name", "colour", "hoisted", "mentionable", "permissions", "managed", "position", \
                "guild_id"

    def __init__(self, client, **kwargs):
        super().__init__(kwargs.get("id"), client)

        #: The name of this role.
        self.name = kwargs.get("name", None)

        #: The colour of this role.
        self.colour = kwargs.get("color", 0)

        #: Is this role hoisted?
        self.hoisted = kwargs.get("hoist", False)

        #: Is this role mentionable?
        self.mentionable = kwargs.get("mentionable", False)

        #: The permissions of this role.
        self.permissions = dt_permissions.Permissions(kwargs.get("permissions", 0))

        #: Is this role managed?
        self.managed = kwargs.get("managed", False)

        #: The position of this role.
        self.position = kwargs.get("position", 0)

        #: The ID of the guild associated with this Role.
        self.guild_id = int(kwargs.get("guild_id", 0))  # type: dt_guild.Guild

    def __lt__(self, other: 'Role'):
        if not isinstance(other, Role):
            return NotImplemented

        if other.guild != self.guild:
            raise ValueError("Cannot compare roles between guilds")

        return self.position < other.position \
            if self.position != other.position \
            else self.id < other.id

    def _copy(self):
        obb = object.__new__(self.__class__)

        obb.name = self.name
        obb.colour = self.colour
        obb.hoisted = self.hoisted
        obb.permissions = self.permissions
        obb.managed = self.managed
        obb.position = self.position
        obb.guild_id = self.guild_id

        return obb

    @property
    def guild(self) -> 'dt_guild.Guild':
        """
        :return: The :class:`.Guild` associated with this role. 
        """
        return self._bot.guilds[self.guild_id]

    @property
    def is_default_role(self) -> bool:
        """
        :return: If this role is the default role of the guild.
        """
        return self.guild.id == self.id

    def allow_mentions(self) -> _MentionableRole:
        """
        Temporarily allows this role to be mentioned during.
         
        .. code-block:: python3
    
            async with role.allow_mentions():
                await ctx.channel.send(role.mention)
        """
        return _MentionableRole(self)

    @property
    def mention(self) -> str:
        """
        Gets the string that can be used to mention this role. 
        
        .. warning::
        
            If :attr:`.Role.mentionable` is ``False``, this will not actually mention the role.
        
        """
        return "<@&{}>".format(self.id)

    async def assign_to(self, member: 'dt_member.Member') -> 'Role':
        """
        Assigns this role to a member.
        
        .. seealso::
        
            :meth:`.Guild.add_roles`

        :param member: The :class:`~.Member` to assign to.
        """
        await self.guild.add_roles(member, self)
        return self

    async def remove_from(self, member: 'dt_member.Member'):
        """
        Removes this role from a member.
        
        .. seealso::
        
            :meth:`.Guild.remove_roles`
        
        :param member: The :class:`~.Member` to assign to. 
        """
        await self.guild.remove_roles(member, self)
        return self

    async def delete(self) -> 'Role':
        """
        Deletes this role.
        """
        if not self.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        await self._bot.http.delete_role(self.guild.id, self.id)
        return self

    async def edit(self, *,
                   name: str = None, permissions: 'dt_permissions.Permissions' = None,
                   colour: int = None, position: int = None,
                   hoist: bool = None, mentionable: bool = None) -> 'Role':
        """
        Edits this role.

        :param name: The name of the role.
        :param permissions: The permissions that the role has.
        :param colour: The colour of the role.
        :param position: The position in the sorting list that the role has.
        :param hoist: Is this role hoisted (shows separately in the role list)?
        :param mentionable: Is this mentionable by everyone?
        """
        if not self.guild.me.guild_permissions.manage_roles:
            raise PermissionsError("manage_roles")

        if permissions is not None:
            if isinstance(permissions, dt_permissions.Permissions):
                permissions = permissions.bitfield

        listener = await curio.spawn(self._bot.wait_for("role_update",
                                                        lambda b, a: a.id == self.id))

        try:
            await self._bot.http.edit_role(self.guild.id, self.id,
                                           name=name, permissions=permissions, colour=colour,
                                           hoist=hoist,
                                           position=position, mentionable=mentionable)
        except:
            await listener.cancel()
            raise

        await listener.join()

        return self
