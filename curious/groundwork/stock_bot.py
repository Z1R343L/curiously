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
import logging
import os
from pathlib import Path

from curious.commands import CommandsManager
from curious.core.client import Client
from curious.core.event import event

logger = logging.getLogger(__name__)


class StockBot(Client):
    """
    The stock groundwork bot core.
    """
    def __init__(self, config: dict):
        """
        :param config: The loaded config.
        """
        self.config = config

        auth_section = config['bot']['auth']
        token_method = auth_section['token_method']
        if token_method == "inline":
            token = auth_section['token_inline']
        elif token_method == "file":
            token = Path(auth_section['token_file']).read_text(encoding='utf-8')
        elif token_method == "envvar":
            token = os.environ[auth_section['token_envvar']]
        else:
            raise ValueError(f"Invalid token method: '{token_method}'")

        super().__init__(token=token)

        self.groundwork_config = config['groundwork']

        # useful attribs
        self.manager = CommandsManager(
            client=self,
            command_prefix=self.groundwork_config['command_prefixes'],
        )
        self.manager.register_events()

    @event("starting")
    async def setup_groundwork(self):
        """
        Sets up the groundwork.
        """
        # todo: components
        plugins_to_scan = self.groundwork_config.get("plugin_directories", [])
        if plugins_to_scan:
            for package in plugins_to_scan:
                logger.info(f"Loading from {package}")
                try:
                    await self.manager.discover_plugins(package)
                except Exception:
                    logger.exception(f"Error loading from directory {package}!")
        else:
            plugins = self.groundwork_config.get("plugin_modules")
            for plugin in plugins:
                logger.info(f"Loading plugin {plugin}")
                try:
                    await self.manager.load_plugins_from(plugin)
                except Exception:
                    logger.exception(f"Error loading plugin {plugin}!")

        plugins_section = self.config.get("plugins", {})
        for plugin, _ in self.manager.plugins.values():
            plugin_name = getattr(plugin, "plugin_name", type(plugin).__name__)
            plugin.plugin_config = plugins_section.get(plugin_name.lower(), {})
            logger.info(f"Loaded configuration for plugin '{plugin_name}' with "
                        f"{len(plugin.plugin_config)} key(s)")
