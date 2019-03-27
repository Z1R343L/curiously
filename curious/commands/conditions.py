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
Commonly used conditions.

.. currentmodule:: curious.commands.conditions
"""

from curious.commands.context import Context
from curious.commands.decorators import condition
from curious.core import get_current_client


def is_owner():
    """
    A :func:`.condition` that ensures the author of the message is the owner of the bot.

    The owner is checked automatically by using the application info of the bot.

    Example::

        @command()
        @is_owner()
        async def kill(ctx: Context):
            await ctx.bot.kill()
    """

    def _condition(ctx: Context):
        bot = get_current_client()
        # If the application info request has not been completed
        # yet we cannot guarantee the command could be ran.
        if bot.application_info is None:
            return False, "No application info downloaded yet."

        owner = bot.application_info.owner
        return ctx.message.author_id == owner.id, "You are not the owner."

    return condition(_condition)


def author_has_permissions(bypass_owner: bool = True, **permissions):
    """
    A :func:`.condition` that ensures the author of the
    message has all of the specified permissions.

    Example::

        @command()
        @author_has_permissions(kick_members=True)
        async def kick(ctx: Context, member: Member):
            await member.kick()
            await ctx.channel.messages.send(':wave:')

    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    :param permissions: A mapping of permissions to check.
    """

    def _condition(ctx: Context):
        perms = ctx.channel.effective_permissions(ctx.author)

        for name, value in permissions.items():
            val = getattr(perms, name, None)
            if val is not value:
                return False, f"You do not have the required permission {name.upper()}."

        return True

    return condition(_condition, bypass_owner=bypass_owner)


def bot_has_permissions(bypass_owner: bool = False, **permissions):
    """
    A :func:`.condition` that ensures the bot
    has all of the specified permissions.

    Example::

        @command()
        @bot_has_permissions(send_messages=True)
        async def test(ctx: Context):
            await ctx.channel.messages.send('The bot can send messages.')

    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    :param permissions: A mapping of permissions to check.
    """

    def _condition(ctx: Context):
        perms = ctx.channel.me_permissions

        for name, value in permissions.items():
            val = getattr(perms, name, None)
            if val is not value:
                return False, f"I do not have the required permission {name.upper()}."

    return condition(_condition, bypass_owner=bypass_owner)


author_has_perms = author_has_permissions
bot_has_perms = bot_has_permissions


def author_has_roles(*roles: str, bypass_owner: bool = True):
    """
    A :func:`.condition` that ensures the author of the message has all of the specified roles.

    The role names must all be exact matches.

    Example::

        @command()
        @author_has_roles('Cool')
        async def cool(ctx: Context):
            await ctx.channel.messages.send('You are cool.')

    :param roles: A collection of role names.
    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    """

    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        author_roles = {role.name for role in ctx.author.roles}
        for role in roles:
            if role not in author_roles:
                return False, f"You do not have the required role '{role}'."

        return True

    return condition(_condition, bypass_owner=bypass_owner)


def bot_has_roles(*roles: str, bypass_owner: bool = False):
    """
    A :func:`.condition` that ensures the bot has all of the specified roles.

    The role names must all be exact matches.

    Example::

        @command()
        @bot_has_roles('Cool')
        async def cool(ctx: Context):
            await ctx.channel.messages.send('The bot is cool.')

    :param roles: A collection of role names.
    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    """

    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        bot_roles = {role.name for role in ctx.guild.me.roles}
        for role in roles:
            if role not in bot_roles:
                return False, f"You do not have the required role '{role}'."

        return True

    return condition(_condition, bypass_owner=bypass_owner)


def is_guild_owner(bypass_owner: bool = True):
    """
    A :func:`.condition` that ensures the author of the message is also the owner of the guild.

    Example::

        @command()
        @is_guild_owner()
        async def test(ctx: Context):
            await ctx.channel.messages.send('You are the owner of this guild.')

    :param bypass_owner:
        Determines if the owner of the bot can run the command
        regardless of if the condition failed or not.
    """

    def _condition(ctx: Context):
        if ctx.guild is None:
            return False

        return ctx.message.author_id == ctx.guild.owner_id, "You are not the owner of this guild."

    return condition(_condition, bypass_owner=bypass_owner)
