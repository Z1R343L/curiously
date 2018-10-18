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
Classes for plugin objects.

.. currentmodule:: curious.commands.plugin
"""
from collections import OrderedDict

import inspect


class PluginMetacls(type):
    def __prepare__(*args, **kwargs):
        return OrderedDict()  # 3.6 compat


class Plugin(metaclass=PluginMetacls):
    """
    Represents a plugin (a collection of events and commands under one class).
    """

    async def plugin_load(self) -> None:
        """
        Called when this plugin is loaded.

        The manager **will** wait for this function to complete.
        """
        pass

    async def plugin_run(self) -> None:
        """
        Called to run any background tasks on this plugin.

        Open your task group here (or similar) for any background tasks. This will be
        automatically cancelled when the plugin is unloaded.
        """

    async def plugin_unload(self) -> None:
        """
        Called when this plugin is unloaded.

        The manager **will** wait for this function to complete. It can be used to, for example,
        cancel any running tasks.
        """

    def _get_commands(self) -> list:
        """
        Gets the commands for this plugin.
        """
        return [i[1] for i in inspect.getmembers(self, predicate=lambda i: hasattr(i, "is_cmd"))]
