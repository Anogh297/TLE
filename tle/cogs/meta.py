import os
import subprocess
import ast
import time
import textwrap

import discord
from discord.ext import commands

from tle import constants
from tle.util.codeforces_common import pretty_time_format

RESTART = 42


# Adapted from numpy sources.
# https://github.com/numpy/numpy/blob/master/setup.py#L64-85
def git_history():
    def _minimal_ext_cmd(cmd):
        # construct minimal environment
        env = {}
        for k in ["SYSTEMROOT", "PATH"]:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env["LANGUAGE"] = "C"
        env["LANG"] = "C"
        env["LC_ALL"] = "C"
        out = subprocess.Popen(cmd, stdout=subprocess.PIPE, env=env).communicate()[0]
        return out

    try:
        out = _minimal_ext_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        branch = out.strip().decode("ascii")
        out = _minimal_ext_cmd(["git", "log", "--oneline", "-5"])
        history = out.strip().decode("ascii")
        return "Branch:\n" + textwrap.indent(branch, "  ") + "\nCommits:\n" + textwrap.indent(history, "  ")
    except OSError:
        return "Fetching git info failed"


def insert_returns(body):
    # insert return stmt if the last expression is a expression statement
    if isinstance(body[-1], ast.Expr):
        body[-1] = ast.Return(body[-1].value)
        ast.fix_missing_locations(body[-1])

    # for if statements, we insert returns into the body and the orelse
    if isinstance(body[-1], ast.If):
        insert_returns(body[-1].body)
        insert_returns(body[-1].orelse)

    # for with blocks, again we insert returns into the body
    if isinstance(body[-1], ast.With):
        insert_returns(body[-1].body)


class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.group(brief="Bot control", invoke_without_command=True)
    async def meta(self, ctx):
        """Command the bot or get information about the bot."""
        await ctx.send_help(ctx.command)

    @meta.command(brief="Restarts TLE")
    @commands.check_any(constants.is_me(), commands.has_any_role(constants.TLE_ADMIN))
    async def restart(self, ctx):
        """Restarts the bot."""
        # Really, we just exit with a special code
        # the magic is handled elsewhere
        await ctx.send("Restarting...")
        os._exit(RESTART)

    @meta.command(brief="Kill TLE")
    @commands.check_any(constants.is_me(), commands.has_any_role(constants.TLE_ADMIN))
    async def kill(self, ctx):
        """Restarts the bot."""
        await ctx.send("Dying...")
        os._exit(0)

    @meta.command(brief="Is TLE up?")
    async def ping(self, ctx):
        """Replies to a ping."""
        start = time.perf_counter()
        message = await ctx.send(":ping_pong: Pong!")
        end = time.perf_counter()
        duration = (end - start) * 1000
        await message.edit(content=f"REST API latency: {int(duration)}ms\n" f"Gateway API latency: {int(self.bot.latency * 1000)}ms")

    @meta.command(brief="Get git information")
    async def git(self, ctx):
        """Replies with git information."""
        await ctx.send("```yaml\n" + git_history() + "```")

    @meta.command(brief="Prints bot uptime")
    async def uptime(self, ctx):
        """Replies with how long TLE has been up."""
        await ctx.send("TLE has been running for " + pretty_time_format(time.time() - self.start_time))

    @meta.command(brief="Print bot guilds")
    @commands.check_any(constants.is_me(), commands.has_any_role(constants.TLE_ADMIN))
    async def guilds(self, ctx):
        "Replies with info on the bot's guilds"
        msg = [f"Guild ID: {guild.id} | Name: {guild.name} | Owner: {guild.owner.id} | Icon: {guild.icon}" for guild in self.bot.guilds]
        await ctx.send("```" + "\n".join(msg) + "```")

    @meta.command(brief="Replies with Pong")
    async def png(self, ctx):
        await ctx.send("Pong!")

    @commands.command(brief="Evaluate python expressions")
    @commands.check(constants.is_me())
    async def eval(self, ctx, *, cmd):
        """Evaluates input.
        Input is interpreted as newline seperated statements.
        If the last statement is an expression, that is the return value.
        Usable globals:
        - `bot`: the bot instance
        - `discord`: the discord module
        - `commands`: the discord.ext.commands module
        - `ctx`: the invokation context
        - `__import__`: the builtin `__import__` function
        Such that `>eval 1 + 1` gives `2` as the result.
        The following invokation will cause the bot to send the text '9'
        to the channel of invokation and return '3' as the result of evaluating
        >eval ```
        a = 1 + 2
        b = a * 2
        await ctx.send(a + b)
        a
        ```
        """
        fn_name = "_eval_expr"

        cmd = cmd.strip("` ")

        # add a layer of indentation
        cmd = "\n".join(f"    {i}" for i in cmd.splitlines())

        # wrap in async def body
        body = f"async def {fn_name}():\n{cmd}"

        parsed = ast.parse(body)
        body = parsed.body[0].body

        insert_returns(body)

        env = {
            "bot": ctx.bot,
            "discord": discord,
            "commands": commands,
            "ctx": ctx,
            "__import__": __import__,
        }
        exec(compile(parsed, filename="<ast>", mode="exec"), env)
        try:
            result = await eval(f"{fn_name}()", env)
            await ctx.send(f"```{result}```" or "None")
        except Exception as e:
            await ctx.send(f"Error: {e}")


async def setup(bot):
    await bot.add_cog(Meta(bot))
