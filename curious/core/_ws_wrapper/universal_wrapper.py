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
import anyio
import threading
from lomond.persist import persist
from lomond.websocket import WebSocket

from curious import USER_AGENT


class UniversalWrapper:
    """
    Represents a universal websocket wrapper.
    """
    _DONE = object()

    def __init__(self, url: str, task_group: anyio.TaskGroup):
        self._url = url
        self._ws: WebSocket = None
        self._cancelled = threading.Event()

        self._queue = anyio.create_queue(5)
        self._task_group = task_group

    def _generator(self):
        """
        Runs the websocket generator. This is used by calling next() over it.
        """
        ws = WebSocket(self._url, agent=USER_AGENT)
        websocket = persist(ws, ping_rate=0, poll=1, exit_event=self._cancelled)
        self._ws = ws

        for item in websocket:
            # for some reason lomond doesn't exit the loop??
            if self._cancelled.is_set():
                break

            anyio.run_async_from_thread(self._queue.put, item)

        anyio.run_async_from_thread(self._queue.put, self._DONE)

    async def run(self):
        """
        Runs the websocket.

        This returns an async generator.
        """
        if self._cancelled.is_set():
            return

        await self._task_group.spawn(anyio.run_in_thread, self._generator)
        while True:
            item = await self._queue.get()
            if item is self._DONE:
                return

            yield item

            # this will work because if it's cancelled the persist will spew a cancelled
            if self._cancelled.is_set():
                break

    async def send_text(self, message: str):
        """
        Sends some text over the generator.
        """
        if self._ws is not None:
            await anyio.run_in_thread(self._ws.send_text, message)

    async def close(self, code: int = 1006, reason: str = "No reason", *,
                    kill: bool = False):
        """
        Closes the websocket.
        """
        if kill:
            self._cancelled.set()

        if self._ws is not None:
            # NB: This can't run in a thread because if we're cancelled (trio) this will never
            # happen
            # So we just pray this doesn't block!
            self._ws.close(code, reason)
