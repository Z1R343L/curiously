"""
Contains the class for the commands manager for a client.
"""
import importlib
import inspect
import sys
import typing
from collections import defaultdict

from curious.commands.context import Context
from curious.commands.plugin import Plugin
from curious.commands.utils import prefix_check_factory
from curious.core import client as md_client
from curious.core.event import EventContext, event
from curious.dataclasses.message import Message


class CommandsManager(object):
    """
    A manager that handles commands for a client.

    First, you need to create the manager and attach it to a client:
    .. code-block:: python3

        # form 1, automatically register with the client
        manager = CommandsManager.with_client(bot)

        # form 2, manually register
        manager = CommandsManager(bot)
        manager.register_events()

    This is required to add the handler events to the client.

    Next, you need to register a message check handler. This is a callable that is called for
    every message to try and extract the command from a message, if it matches.
    By default, the manager provides an easy way to use a simple command prefix:
    .. code-block:: python3

        # at creation time
        manager = CommandsManager(bot, command_prefix="!")

        # or set it on the manager
        manager.command_prefix = "!"

    At this point, the command prefix will be available on the manager with either
    :attr:`.Manager.command_prefix` or :attr:`.Manager.message_check.prefix`.

    If you need more complex message checking, you can use ``message_check``:
    .. code-block:: python3

        manager = CommandsManager(bot, message_check=my_message_checker)
        # or
        manager.message_check = my_message_checker

    Finally, you can register plugins or modules containing plugins with the manager:
    .. code-block:: python3

        @bot.event("ready")
        async def load_plugins(ctx: EventContext):
            # load plugin explicitly
            await manager.load_plugin(PluginClass, arg1)
            # load plugins from a module
            await manager.load_plugins_from("my.plugin.module")

    You can also add free-standing commands that aren't bound to a plugin with
    :meth:`.CommandsManager.add_command`:
    .. code-block:: python3

        @command
        async def ping(ctx: CommandsContext):
            await ctx.channel.send(content="Pong!")

        manager.add_command(ping)

    These will then be available to the client.
    """

    def __init__(self, client: 'md_client.Client', *,
                 message_check=None, command_prefix: str = None):
        """
        :param client: The :class:`.Client` to use with this manager.
        :param message_check: The message check function for this manager.

            This should take two arguments, the client and message, and should return either None
            or a 2-item tuple:
              - The command word matched
              - The tokens after the command word
        """
        if message_check is None and command_prefix is None:
            raise ValueError("Must provide one of message_check or command_prefix")

        #: The client for this manager.
        self.client = client

        if message_check is None:
            message_check = prefix_check_factory(command_prefix)

        #: The message check function for this manager.
        self.message_check = message_check

        #: A dictionary mapping of <plugin name> -> <plugin> object.
        self.plugins = {}

        #: A dictionary of stand-alone commands, i.e. commands not associated with a plugin.
        self.commands = {}

        self._module_plugins = defaultdict(lambda: [])

    def register_events(self) -> None:
        """
        Copies the events to the client specified on this manager.
        """
        self.client.add_event(self.handle_message)

    async def load_plugin(self, klass: typing.Type[Plugin], *args,
                          module: str = None):
        """
        Loads a plugin.
        .. note::

            The client instance will automatically be provided to the Plugin's ``__init__``.

        :param klass: The plugin class to load.
        :param args: Any args to provide to the plugin.
        :param module: The module name provided with this plugin. Only used interally.
        """
        # get the name and create the plugin object
        plugin_name = getattr(klass, "name", klass.__name__)
        instance = klass(self.client, *args)

        # call load, of course
        await instance.load()

        self.plugins[plugin_name] = instance
        if module is not None:
            self._module_plugins[module].append(instance)

        return instance

    async def unload_plugin(self, klass: typing.Union[Plugin, str]):
        """
        Unloads a plugin.

        :param klass: The plugin class or name of plugin to unload.
        """
        p = None
        if isinstance(klass, str):
            p = self.plugins.pop(klass)

        for k, p in self.plugins.copy().items():
            if type(p) == klass:
                p = self.plugins.pop(k)
                break

        if p is not None:
            await p.unload()

        return p

    async def add_command(self, command):
        """
        Adds a command.

        :param command: A command function.
        """
        if not hasattr(command, "is_cmd"):
            raise ValueError("Commands must be decorated with the command decorator")

        self.commands[command.cmd_name] = command
        return command

    async def remove_command(self, command):
        """
        Removes a command.

        :param command: The name of the command, or the command function.
        """
        if isinstance(command, str):
            return self.commands.pop(command)
        else:
            for k, p in self.commands.copy().items():
                if p == command:
                    return self.commands.pop(k)

    async def load_plugins_from(self, import_path: str):
        """
        Loads plugins from the specified module.

        :param import_path: The import path to import.
        """
        mod = importlib.import_module(import_path)

        # define the predicate for the body scanner
        def predicate(item):
            # only accept plugin subclasses
            if not issubclass(item, Plugin):
                return False

            # ensure item is not actually Plugin
            if item == Plugin:
                return False

            # it is a plugin
            return True

        for plugin_name, plugin_class in inspect.getmembers(mod, predicate=predicate):
            await self.load_plugin(plugin_class, mod=mod)

    async def unload_plugins_from(self, import_path: str):
        """
        Unloads plugins from the specified module.
        This will delete the module from sys.path.

        :param import_path: The import path.
        """
        for plugin in self._module_plugins[import_path]:
            await plugin.unload()
            self.plugins.pop(getattr(plugin, "name", "__name__"))

        del sys.modules[import_path]
        del self._module_plugins[import_path]

    async def handle_commands(self, ctx: EventContext, message: Message):
        """
        Handles commands for a message.
        """
        # step 1, match the messages
        matched = self.message_check(self.client, message)
        if inspect.isawaitable(matched):
            matched = await matched

        if matched is None:
            return None

        # deconstruct the tuple returned into more useful variables than a single tuple
        command_word, tokens = matched

        # step 2, create the new commands context
        ctx = Context(event_context=ctx, message=message)
        ctx.command_name = command_word
        ctx.tokens = tokens
        ctx.manager = self

        # step 3, invoke the context to try and match the command and run it
        await ctx.try_invoke()

    @event("message_create")
    async def handle_message(self, ctx: EventContext, message: Message):
        """
        Registered as the event handler in a client for handling commands.
        """
        return await self.handle_commands(ctx, message)