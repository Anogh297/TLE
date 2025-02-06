import aiohttp
import asyncio
import datetime
from discord import Embed, User
from discord.ext import commands
from datetime import timezone, timedelta
from tle.util import codeforces_common as cf_common, discord_common, tasks
from tle import constants

GYM_ID_THRESHOLD = 100000


class Solved(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    @discord_common.once
    async def on_ready(self):
        if constants.SOLVED_CHANNEL:
            print("Checking for solved updates...")
            self.check_for_updates.start()

    @staticmethod
    def convert_to_unix_time(time_str, date_str=None):  # Added date_str parameter
        """Converts military time (GMT+6) to a Unix timestamp (UTC)."""

        if date_str is None:
            date_str = datetime.date.today().strftime("%Y-%m-%d")  # Default to today's date

        try:
            dt_gmt6 = datetime.datetime.strptime(date_str + " " + time_str, "%Y-%m-%d %H%M")  # Parse with date
        except ValueError:
            raise ValueError("Invalid date or time format. Use YYYY-MM-DD HHMM")

        dt_utc = dt_gmt6.replace(tzinfo=timezone(timedelta(hours=6))).astimezone(timezone.utc)  # Correct timezone handling
        return int(dt_utc.timestamp())

    @staticmethod
    def convert_to_12h_format(time_str):
        """Converts military time (HHMM) to 12-hour format with AM/PM."""
        dt = datetime.datetime.strptime(time_str, "%H%M")
        return dt.strftime("%I:%M %p")

    # @tasks.loop(seconds=60)
    @tasks.task_spec(
        name="SolvedUpdate",
        waiter=tasks.Waiter.fixed_delay(60),
    )
    async def check_for_updates(self, _):
        for guild in self.bot.guilds:
            users = cf_common.user_db.get_cf_users_for_guild(guild.id)

            async with aiohttp.ClientSession() as session:
                for id, cf_user in users:
                    user: User = self.bot.get_user(id)
                    handle = cf_user.handle
                    async with session.get(f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=100") as res:
                        if res.status == 200:
                            data = await res.json()
                            prev_time = cf_common.user_db.get_last_solved_time(id)
                            curr_time = datetime.datetime.now()

                            embed = Embed()
                            problems = [
                                x
                                for x in data["result"]
                                if x["creationTimeSeconds"] > prev_time and (x["verdict"] == "OK" or x["verdict"] == "PARTIAL")
                            ]
                            for p in problems:
                                if p["verdict"] == "PARTIAL" and p["points"] <= 0:
                                    continue

                                problem = p.get("problem")
                                msg = (
                                    f"[{problem['name']}]"
                                    f"(https://codeforces.com/{'contest' if problem['contestId'] < GYM_ID_THRESHOLD else 'gym'}/"
                                    f"{problem['contestId']}/problem/{problem['index']})"
                                )

                                if p["verdict"] == "PARTIAL":
                                    msg += f" ({p['points']} points)"
                                embed.add_field(name="Solved", value=msg, inline=True)
                                embed.add_field(name="Rating", value=problem.get("rating", "XXXX"))

                                t = ", ".join(problem["tags"]) or "None"
                                embed.add_field(name="Tags", value=t, inline=True)

                            if problems:
                                embed.set_author(
                                    name=handle,
                                    url=f"https://codeforces.com/profile/{handle}",
                                    icon_url=user.display_avatar.url if user.display_avatar else None,
                                )
                                embed.timestamp = curr_time
                                await self.bot.get_channel(int("1276595437515833491")).send(embed=embed)
                                cf_common.user_db.update_last_solved_time(id, int(curr_time.timestamp()))

    @commands.command()
    async def solved(self, ctx, start_time: str = "0000", end_time: str = "2359"):
        start_unix = self.convert_to_unix_time(start_time)
        end_unix = self.convert_to_unix_time(end_time)

        res = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
        users = {}
        async with aiohttp.ClientSession() as session:
            for id, cf_user in res:
                handle = cf_user.handle
                async with session.get(f"https://codeforces.com/api/user.status?handle={handle}&from=1&count=100") as response:
                    if response.status == 200:
                        data = await response.json()
                        users[id] = {"handle": handle, "status": "OK", "data": data["result"]}
                    else:
                        users[id] = {"handle": handle, "status": "error", "data": None}
                await asyncio.sleep(0.1)

        users = {k: v for k, v in users.items() if v["data"] is not None and v["status"] == "OK"}
        for user_id, user_data in users.items():
            user_data["data"] = [x for x in user_data["data"] if start_unix <= x["creationTimeSeconds"] <= end_unix and x["verdict"] == "OK"]
            users[user_id]["points"] = len(user_data["data"])

        start_time_12h = self.convert_to_12h_format(start_time)
        end_time_12h = self.convert_to_12h_format(end_time)

        today_date = datetime.datetime.now(timezone(timedelta(hours=6))).strftime("%d %b")
        msg = f"**__Solved count for {today_date}: {start_time_12h} - {end_time_12h}__**\n\n"

        users = dict(sorted(users.items(), key=lambda item: -item[1]["points"]))
        for user_id, user_data in users.items():
            if user_data["points"] > 0:
                msg += f"{user_data['handle']} solved {user_data['points']} problems\n"
        await ctx.send(msg)


async def setup(bot):
    await bot.add_cog(Solved(bot))
