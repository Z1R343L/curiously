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
import contextvars
from typing import Callable, List

from curious.core.gateway import GatewayHandler

#: A context variable holding the current :class:`.EventContext`.
event_context = contextvars.ContextVar("event_context")


def current_event_context() -> "EventContext":
    """
    :return: The current :class:`.EventContext` that is being processed.
    """
    return event_context.get()


class EventContext(object):
    """
    Represents a special context that are passed to events.
    """

    def __init__(self, shard_id: int, event_name: str):
        """
        :param shard_id: The shard ID this event is for.
        :param event_name: The event name for this event.
        """
        from curious.core import get_current_client

        #: The shard this event was received on.
        self.shard_id = shard_id  # type: int
        #: The shard for this bot.
        self.shard_count = get_current_client().shard_count  # type: int

        #: The event name for this event.
        self.event_name = event_name  # type: str

        #: The original context, if this event was dispatched inside an event.
        self.original_context: EventContext = None

    @property
    def handlers(self) -> List[Callable[["EventContext"], None]]:
        """
        :return: A list of handlers registered for this event.
        """
        from curious.core import get_current_client

        return get_current_client().events.getall(self.event_name, [])

    async def change_status(self, *args, **kwargs) -> None:
        """
        Changes the current status for this shard.

        This takes the same arguments as :class:`.Client.change_status`, but ignoring the shard ID.
        """
        kwargs["shard_id"] = self.shard_id

        from curious.core import get_current_client

        return await get_current_client().change_status(*args, **kwargs)

    @property
    def gateway(self) -> GatewayHandler:
        """
        :return: The :class:`.Gateway` that produced this event.
        """
        from curious.core import get_current_client

        return get_current_client().gateways[self.shard_id]
