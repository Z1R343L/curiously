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
import inspect
from typing import Any, Generator, Tuple

from curious.core.event.context import EventContext, current_event_context
from curious.core.event.manager import EventManager


def event(name, scan: bool = True):
    """
    Marks a function as an event.

    :param name: The name of the event.
    :param scan: Should this event be handled in scans too?
    """

    def __innr(f):
        if not hasattr(f, "events"):
            f.events = {name}

        f.is_event = True
        f.events.add(name)
        f.scan = scan
        return f

    return __innr


def scan_events(obb) -> Generator[None, Tuple[str, Any], None]:
    """
    Scans an object for any items marked as an event and yields them.
    """

    def _pred(f):
        is_event = getattr(f, "is_event", False)
        if not is_event:
            return False

        if not f.scan:
            return False

        return True

    for _, item in inspect.getmembers(obb, predicate=_pred):
        yield (_, item)
