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
import functools
import inspect
import logging
from typing import Any, AsyncContextManager

import anyio
import outcome
from async_generator import asynccontextmanager
from multidict import MultiDict

from curious.core.event.context import EventContext, event_context
from curious.util import Promise, remove_from_multidict, safe_generator

logger = logging.getLogger(__name__)


class ListenerExit(Exception):
    """
    Raised when a temporary listener is to be exited.

    .. code-block:: python3

        def listener(ctx, message):
            if message.author.id == message.guild.owner_id:
                raise ListenerExit

    """


@asynccontextmanager
@safe_generator
async def _wait_for_manager(manager, name: str, predicate):
    """
    Helper class for managing a wait_for.
    """
    async with anyio.create_task_group() as tg:
        tg: anyio.TaskGroup
        try:
            partial = functools.partial(manager.wait_for, name, predicate)
            await tg.spawn(partial)
            yield
        except:
            await tg.cancel_scope.cancel()
            raise


class EventManager(object):
    """
    A manager for events.

    This deals with firing of events and temporary listeners.
    """

    def __init__(self):
        #: The task manager used to spawn events.
        self.task_manager: anyio.TaskGroup = None

        #: A list of event hooks.
        self.event_hooks = set()

        #: A MultiDict of event listeners.
        self.event_listeners = MultiDict()

        #: A MultiDict of temporary listeners.
        self.temporary_listeners = MultiDict()

    # add or removal functions
    # Events
    def add_event(self, func, name: str = None):
        """
        Add an event to the internal registry of events.

        :param name: The event name to register under.
        :param func: The function to add.
        """
        if not inspect.iscoroutinefunction(func):
            raise TypeError("Event must be an async function")

        if name is None:
            evs = func.events
        else:
            evs = [name]

        for ev_name in evs:
            logger.debug("Registered event `{}` handling `{}`".format(func, ev_name))
            self.event_listeners.add(ev_name, func)

    def remove_event(self, name: str, func):
        """
        Removes a function event.

        :param name: The name the event is registered under.
        :param func: The function to remove.
        """
        self.event_listeners = remove_from_multidict(self.event_listeners, key=name, item=func)

    # listeners
    def add_temporary_listener(self, name: str, listener):
        """
        Adds a new temporary listener.

        To remove the listener, you can raise ListenerExit which will exit it and remove the
        listener from the list.

        :param name: The name of the event to listen to.
        :param listener: The listener function.
        """
        self.temporary_listeners.add(name, listener)

    def remove_listener_early(self, name: str, listener):
        """
        Removes a temporary listener early.

        :param name: The name of the event the listener is registered under.
        :param listener: The listener function.
        """
        self.event_listeners = remove_from_multidict(self.event_listeners, key=name, item=listener)

    def add_event_hook(self, listener):
        """
        Adds an event hook.

        :param listener: The event hook callable to use.
        """
        logger.warning("Adding event hook '%s'", listener)
        self.event_hooks.add(listener)

    def remove_event_hook(self, listener):
        """
        Removes an event hook.
        """
        self.event_hooks.remove(listener)

    # wrapper functions
    async def _safety_wrapper(self, func, *args, **kwargs):
        """
        Ensures a coro's error is caught and doesn't balloon out.
        """
        try:
            await func(*args, **kwargs)
        except Exception as e:
            logger.exception("Unhandled exception in {}!".format(func.__name__), exc_info=True)

    async def _listener_wrapper(self, key: str, func, *args, **kwargs):
        """
        Wraps a listener, ensuring ListenerExit is handled properly.
        """
        try:
            await func(*args, **kwargs)
        except ListenerExit:
            # remove the function
            self.temporary_listeners = remove_from_multidict(self.temporary_listeners, key, func)
        except Exception:
            logger.exception("Unhandled exception in listener {}!".format(func.__name__),
                             exc_info=True)
            self.temporary_listeners = remove_from_multidict(self.temporary_listeners, key, func)

    async def wait_for(self, event_name: str, predicate=None):
        """
        Waits for an event.

        Returning a truthy value from the predicate will cause it to exit and return.

        :param event_name: The name of the event.
        :param predicate: The predicate to use to check for the event.
        """
        p = Promise()

        async def listener(*args):
            # exit immediately if the predicate is none
            if predicate is None:
                await p.set(outcome.Value(None))
                raise ListenerExit

            try:
                res = predicate(*args)
                if inspect.isawaitable(res):
                    res = await res
            except ListenerExit:
                # ???
                await p.set(outcome.Value(args))
                raise
            except Exception as e:
                # something bad happened, set exception and exit
                logger.exception("Exception in wait_for predicate!")
                # signal that an error happened
                await p.set(outcome.Error(e))
                raise ListenerExit
            else:
                # exit now if result is true
                if res is True:
                    await p.set(outcome.Value(args))
                    raise ListenerExit

        self.add_temporary_listener(name=event_name, listener=listener)
        try:
            output: outcome.Outcome = await p.wait()
        except Exception:  # cancellations or timeouts
            self.remove_listener_early(event_name, listener=listener)
            raise

        result = output.unwrap()

        # unwrap tuples, if applicable
        if len(result) == 1:
            return result[0]
        return result

    def wait_for_manager(self, event_name: str, predicate) -> 'AsyncContextManager[None]':
        """
        Returns a context manager that can be used to run some steps whilst waiting for a
        temporary listener.

        .. code-block:: python

            async with client.events.wait_for_manager("member_update", predicate=...):
                await member.nickname.set("Test")

        This probably won't be needed outside of internal library functions.
        """
        return _wait_for_manager(self, event_name, predicate)

    async def spawn(self, cofunc, *args) -> Any:
        """
        Spawns a new async function using our task manager.

        Usage::

            async def myfn(a, b):
                await do_some_operation(a + b)

            await events.spawn(myfn, 1, 2)

        :param cofunc: The async function to spawn.
        :param args: Args to provide to the async function.
        """
        return await self.task_manager.spawn(cofunc, *args)

    async def fire_event(self, event_name: str, *args, **kwargs):
        """
        Fires an event.

        :param event_name: The name of the event to fire.
        """
        if "ctx" not in kwargs:
            gateway = kwargs.pop("gateway")
            ctx = EventContext(gateway.session.shard_id, event_name)
        else:
            ctx = kwargs.pop("ctx")

        # clobber event name
        ctx.event_name = event_name
        # update current event context
        event_context.set(ctx)

        # always ensure hooks are ran first
        for hook in self.event_hooks:
            cofunc = functools.partial(hook, *args, **kwargs)
            await self.spawn(cofunc)

        for handler in self.event_listeners.getall(event_name, []):
            coro = functools.partial(handler, *args, **kwargs)
            coro.__name__ = handler.__name__
            await self.spawn(self._safety_wrapper, coro)

        for listener in self.temporary_listeners.getall(event_name, []):
            coro = functools.partial(self._listener_wrapper, event_name, listener,
                                     *args, **kwargs)
            await self.spawn(coro)
