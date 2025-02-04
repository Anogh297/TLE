import asyncio
from discord.ext import commands
import datetime
from datetime import timezone, timedelta
from tle.util import codeforces_common as cf_common
import aiohttp


class Solved(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def solved(self, ctx, start_time: str = "0000", end_time: str = "2359"):
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

        def convert_to_12h_format(time_str):
            """Converts military time (HHMM) to 12-hour format with AM/PM."""
            dt = datetime.datetime.strptime(time_str, "%H%M")
            return dt.strftime("%I:%M %p")

        start_unix = convert_to_unix_time(start_time)
        end_unix = convert_to_unix_time(end_time)

        res = cf_common.user_db.get_cf_users_for_guild(ctx.guild.id)
        users = {}
        async with aiohttp.ClientSession() as session:
            # Iterate through the list directly
            for id, cf_user in res:  # Correct way to iterate
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
            users[user_id]["points"] = len(user_data["data"])  # Correct calculation

        start_time_12h = convert_to_12h_format(start_time)
        end_time_12h = convert_to_12h_format(end_time)

        today_date = datetime.datetime.now(timezone(timedelta(hours=6))).strftime("%d %b")
        msg = f"**__Solved count for {today_date}: {start_time_12h} - {end_time_12h}__**\n\n"

        users = dict(sorted(users.items(), key=lambda item: -item[1]["points"]))
        for user_id, user_data in users.items():
            if user_data["points"] > 0:
                msg += f"{user_data['handle']} solved {user_data['points']} problems\n"
        await ctx.send(msg)


async def setup(bot):
    await bot.add_cog(Solved(bot))
