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
import importlib
import logging
import sys
from pathlib import Path

import anyio
import coloredlogs
import toml

stock_config = """
### Initial config for a groundwork bot.
### Edit as appropriate.

[groundwork]

## The bot class to load.
## Don't change from stock bot without a good reason.
## This class should extend from StockBot, but if it doesn't, it must take a config for __init__
## and set up everything from there.
bot_class = "curious.groundwork.stock_bot:StockBot"

## A list of component directories to load from.
## This can be empty.
component_directories = [
    "{bot_name}.components"
]

## A list of component modules to load.
## This is only used if component_directories is empty.
component_modules = []

## A list of plugin directories to load from.
## This can be empty.
plugin_directories = [
    # This is used for the core plugin by default.
    "curious.groundwork.stock_plugins",

    "{bot_name}.plugins"
]

## A list of plugin modules to load.
## This is only used if plugin_directories is empty.
plugin_modules = []

## The list of valid command prefixes for this bot.
command_prefixes = [
    "%%"
]

[bot.auth]
## The token method to use. There are four options:
## 1) inline - use the token var in this file. Only use for private bots.
## 2) file - use the token file specified in this file.
## 3) envvar - use the environment variable specified in this file.
token_method = "inline"

## The inline token, if any.
token_inline = ""

## The token file, if any.
token_file = "token.txt"

## The token environment variable, if any.
token_envvar = "BOT_TOKEN"


[plugins.core]
## A list of IDs of additional admins for this bot.
## These people will override the owner check provided by the core plugin.
extra_admins = [
    523533684935098388
]

[plugins.myplugin]
## Add any settings for your plugins here. They can be accessed with the plugin_config class 
## variable of the plugin.
"""

logger = logging.getLogger(__name__)


def init(name: str, path: str):
    """
    Initialises a new bot.
    """
    path = Path(path)
    path.mkdir(exist_ok=True)

    main_package = path / name
    main_package.mkdir(exist_ok=True)

    # easiest way of just making the file
    init = main_package / "__init__.py"
    init.touch(exist_ok=True)

    (main_package / "plugins").mkdir(exist_ok=True)
    (main_package / "components").mkdir(exist_ok=True)

    (path / "config.toml").write_text(stock_config.format(bot_name=name), encoding='utf-8')
    print(f"Written config to {(path / 'config.toml').resolve()}")

    return 0


def run(file: str):
    """
    Runs the bot.
    """
    config = toml.loads(Path(file).read_text(encoding='utf-8'))
    groundwork_section = config['groundwork']
    bot_class = groundwork_section['bot_class']
    backend = groundwork_section.get('backend', 'trio')

    # format: pkg.mod:BotClass
    # we split it out then getattr() it
    module, kls = bot_class.split(":")
    mod = importlib.import_module(module)
    bot_klass = getattr(mod, kls)

    async def async_runner():
        new_bot = bot_klass(config)
        return await new_bot.run_async()

    anyio.run(async_runner, backend=backend)


def main():
    logging.basicConfig(level=logging.DEBUG)
    coloredlogs.install(level="DEBUG", isatty=True,
                        stream=sys.stderr)

    try:
        command = sys.argv[1]
    except IndexError:
        print("Command needed")
        return 1

    if command == "run":
        if len(sys.argv) < 3:
            config_file = "config.toml"
        else:
            config_file = ' '.join(sys.argv[2:])

        return run(config_file)

    if command == "init":
        if len(sys.argv) < 5:
            print("Usage: init <botname> <path>")
            return 1

        bot_name = sys.argv[2]
        path = ' '.join(sys.argv[3:])
        return init(bot_name, path)


if __name__ == "__main__":
    sys.exit(main())
