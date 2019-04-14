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
import contextlib
import inspect
import sys
import time
import traceback
from io import StringIO

from curious.commands import Plugin, command, ctx, send_message
from curious.commands.conditions import is_owner
from curious.core import get_current_client


class Core(Plugin):
    """
    Core plugin - useful commands.
    """

    @command()
    async def ping(self):
        """
        Ping!
        """
        client = get_current_client()

        gw_latency = "{:.2f}".format(
            client.gateways[ctx.guild.shard_id].heartbeat_stats.gw_time * 1000
        )
        fmt = f":ping_pong: Pong! | Gateway latency: {gw_latency}ms"

        before = time.monotonic()
        initial = await send_message(fmt)
        after = time.monotonic()
        fmt = fmt + f" | HTTP latency: {(after - before) * 1000:.2f}ms"
        await initial.edit(fmt)

    @command()
    @is_owner()
    async def exec(self, *, code: str):
        """
        exec()s code.
        """
        code = code.lstrip("`").rstrip("`")
        lines = code.split("\n")
        lines = ["    " + i for i in lines]
        lines = '\n'.join(lines)

        _no_return = object()

        f_code = f"async def _():\n{lines}\n    return _no_return"
        stdout = StringIO()

        try:
            namespace = {
                "ctx": ctx.unwrap(),
                "message": ctx.message,
                "guild": ctx.message.guild,
                "channel": ctx.message.channel,
                "author": ctx.message.author,
                "bot": ctx.bot,
                "_no_return": _no_return,
                **sys.modules
            }
            exec(f_code, namespace, namespace)
            func = namespace["_"]

            with contextlib.redirect_stdout(stdout):
                result = await func()

        except Exception as e:
            result = ''.join(traceback.format_exception(None, e, e.__traceback__))
        finally:
            stdout.seek(0)

        if result is _no_return:
            result = "(Eval returned nothing)"

        fmt = f"```py\n{stdout.read()}\n{result}\n```"
        await send_message(fmt)

    @command()
    @is_owner()
    async def eval(self, *, code: str):
        """
        eval()s some code.
        """
        namespace = {
            "ctx": ctx.unwrap(),
            "message": ctx.message,
            "guild": ctx.message.guild,
            "channel": ctx.message.channel,
            "author": ctx.message.author,
            "bot": get_current_client(),
            **sys.modules
        }
        result = eval(code, namespace, namespace)
        if inspect.isawaitable(result):
            result = await result

        await send_message(f"`{result}`")

