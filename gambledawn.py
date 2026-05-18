import asyncio
import json
import os
import random
import tempfile
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands
from dotenv import load_dotenv


BALANCES_FILE = "balances.json"
LEGACY_BOOSTS_FILE = "boosts.json"
DEFAULT_BALANCE = 100
DAILY_REWARD = 50
DAILY_COOLDOWN = timedelta(hours=10)
SELL_REWARD = 1000
NAME_AUCTION_PRICE = 10000
SOLD_NAME = "NO NAME, THIS DUMBAH SELLED IT"
BOOST_COST = 50
BASE_GAMBLE_WIN_CHANCE = 0.50
BOOST_GAMBLE_BONUS = 0.20
LEADERBOARD_LIMIT = 10

# Small bot, but this keeps two commands from stepping on the same JSON save.
balances_lock = asyncio.Lock()


load_dotenv()
token = os.getenv("bot_discord_token")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def load_balances():
    if not os.path.exists(BALANCES_FILE):
        return {}

    with open(BALANCES_FILE, "r", encoding="utf-8") as file:
        content = file.read().strip()
        if not content:
            return {}
        return json.loads(content)


def save_balances(data):
    # Write to a temp file first, so a crash does not leave half a balance sheet behind.
    file_path = os.path.abspath(BALANCES_FILE)
    file_dir = os.path.dirname(file_path) or "."

    with tempfile.NamedTemporaryFile(
        "w",
        delete=False,
        dir=file_dir,
        encoding="utf-8",
    ) as temp_file:
        json.dump(data, temp_file, indent=4)
        temp_path = temp_file.name

    os.replace(temp_path, file_path)


def load_legacy_boosts():
    if not os.path.exists(LEGACY_BOOSTS_FILE):
        return {}

    with open(LEGACY_BOOSTS_FILE, "r", encoding="utf-8") as file:
        content = file.read().strip()
        if not content:
            return {}
        return json.loads(content)


def get_profile(balances, user_id):
    raw_profile = balances.get(user_id)

    if isinstance(raw_profile, int):
        profile = {
            "balance": raw_profile,
            "last_daily": None,
            "name_sold": False,
            "original_name": None,
            "boost_ready": False,
        }
    elif isinstance(raw_profile, dict):
        profile = {
            "balance": int(raw_profile.get("balance", DEFAULT_BALANCE)),
            "last_daily": raw_profile.get("last_daily"),
            "name_sold": bool(raw_profile.get("name_sold", False)),
            "original_name": raw_profile.get("original_name"),
            "boost_ready": bool(raw_profile.get("boost_ready", False)),
        }
    else:
        profile = {
            "balance": DEFAULT_BALANCE,
            "last_daily": None,
            "name_sold": False,
            "original_name": None,
            "boost_ready": False,
        }

    balances[user_id] = profile
    return profile


def parse_saved_time(saved_value):
    if not saved_value:
        return None

    try:
        parsed_time = datetime.fromisoformat(saved_value)
    except ValueError:
        return None

    if parsed_time.tzinfo is None:
        parsed_time = parsed_time.replace(tzinfo=timezone.utc)
    return parsed_time


def format_remaining_time(remaining):
    total_seconds = max(int(remaining.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes or not parts:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " and ".join(parts)


def build_help_message():
    return (
        "ugh fine, heres the command list, not cuz i wanna help u or anythin:\n"
        "`!help` - shows this thing again i guess.\n"
        "`!bal [member]` - checks ur coins, or someone elses coins.\n"
        "`!lb` - shows whos stupid rich rn.\n"
        "`!daily` - grab 50 coins every 10 hours.\n"
        "`!gamble <amount>` or `!bet <amount>` - bet ur coins if u wanna risk lookin dumb.\n"
        "`!boost` - spends 50 coins to give ur next gamble 20% more win chance.\n"
        "`!sell` - sells ur name for 1000 coins and throws it on auction for 10000.\n"
        "`!buy <member>` - buys a sold name for 10000 coins and gives it back.\n"
        "`!daddy` - says who daddy is.\n"
        "`!mommy` - says who mommy is."
    )


async def run_gamble(ctx, amount: int = None):
    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(ctx.author.id))

        if profile["balance"] <= 0:
            await ctx.send("you cant gamble with no coins, genius.")
            return

        if amount is None:
            await ctx.send("just say how much ur betting already.")
            return

        if amount <= 0:
            await ctx.send("pick a number over 0 maybe.")
            return

        if amount > profile["balance"]:
            await ctx.send("you cant bet more then what u got.")
            return

        win_chance = BASE_GAMBLE_WIN_CHANCE
        used_boost = profile["boost_ready"]
        if used_boost:
            win_chance += BOOST_GAMBLE_BONUS
            profile["boost_ready"] = False

        if random.random() < win_chance:
            profile["balance"] += amount
            result_text = (
                f"tch, u got lucky this time. u won {amount} coins and now u got {profile['balance']}."
            )
        else:
            profile["balance"] -= amount
            result_text = (
                f"see? the table clowned u. u lost {amount} coins and now u got {profile['balance']}."
            )

        save_balances(balances)

    if used_boost:
        result_text += " yeah, ur boost got used too."

    await ctx.send(result_text)


async def resolve_member_name(ctx, user_id):
    member = ctx.guild.get_member(int(user_id)) if ctx.guild else None
    if member is not None:
        return member.display_name

    try:
        user = await bot.fetch_user(int(user_id))
        return user.display_name
    except (discord.NotFound, discord.HTTPException, ValueError):
        return f"Unknown User ({user_id})"


def migrate_legacy_boosts():
    legacy_boosts = load_legacy_boosts()
    if not legacy_boosts:
        return

    balances = load_balances()
    migrated_any = False

    # Old boosts lived in their own file. Fold them into balances once, then retire that file.
    for user_id, has_boost in legacy_boosts.items():
        if not has_boost:
            continue

        profile = get_profile(balances, str(user_id))
        if not profile["boost_ready"]:
            profile["boost_ready"] = True
            migrated_any = True

    if migrated_any:
        save_balances(balances)

    os.remove(LEGACY_BOOSTS_FILE)


@bot.event
async def on_ready():
    migrate_legacy_boosts()
    print(f"Logged in as {bot.user}. not like i was waitin to be useful or anythin.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"slow down already. try again in {error.retry_after:.1f} seconds."
        )
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("u forgot part of the command. go read !help or whatever.")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("that argument looks wrong. type it better.")
        return

    print(f"Error in command {ctx.command}: {error}")
    await ctx.send("something broke on my side, ok. try again in a sec.")


@bot.command()
async def help(ctx):
    await ctx.send(build_help_message())


@bot.command()
async def bal(ctx, member: discord.Member = None):
    target = member or ctx.author

    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(target.id))
        save_balances(balances)

    await ctx.send(
        f"{target.display_name} got {profile['balance']} coins rn. dont waste em or whatever."
    )


@bot.command()
async def lb(ctx):
    async with balances_lock:
        balances = load_balances()
        if not balances:
            await ctx.send("nobody even got coins yet. kinda sad.")
            return

        leaderboard_entries = []
        for user_id in balances:
            profile = get_profile(balances, user_id)
            leaderboard_entries.append((user_id, profile["balance"]))

        sorted_balances = sorted(
            leaderboard_entries,
            key=lambda entry: entry[1],
            reverse=True,
        )
        save_balances(balances)

    leaderboard_lines = ["**Coin Leaderboard**", "dont get all smug if ur first.", ""]
    for index, (user_id, balance) in enumerate(
        sorted_balances[:LEADERBOARD_LIMIT],
        start=1,
    ):
        member_name = await resolve_member_name(ctx, user_id)
        leaderboard_lines.append(f"**{index}.** {member_name} - {balance} coins")

    await ctx.send("\n".join(leaderboard_lines))


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def daily(ctx):
    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(ctx.author.id))
        now = datetime.now(timezone.utc)
        last_daily = parse_saved_time(profile.get("last_daily"))

        if last_daily:
            next_claim = last_daily + DAILY_COOLDOWN
            if now < next_claim:
                remaining = format_remaining_time(next_claim - now)
                try:
                    await ctx.author.send(
                        "ur daily aint ready yet. "
                        f"just wait {remaining}. its 10 hours, not that hard."
                    )
                except discord.Forbidden:
                    await ctx.send(
                        "i cant dm u, but ur daily still got the 10 hour limit on it."
                    )
                return

        profile["balance"] += DAILY_REWARD
        profile["last_daily"] = now.isoformat()
        save_balances(balances)
        new_balance = profile["balance"]

    await ctx.send(
        f"fine, take ur {DAILY_REWARD} daily coins already. u got {new_balance} now, happy?"
    )


@bot.command(aliases=["bet"])
@commands.cooldown(1, 3, commands.BucketType.user)
async def gamble(ctx, amount: int = None):
    await run_gamble(ctx, amount)


@bot.command()
async def daddy(ctx):
    await ctx.send("mrmariix")


@bot.command()
async def mommy(ctx):
    await ctx.send("dawnera")


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def boost(ctx):
    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(ctx.author.id))

        if profile["boost_ready"]:
            await ctx.send("you already got a boost waitin, dont be greedy.")
            return

        if profile["balance"] < BOOST_COST:
            await ctx.send(f"you need {BOOST_COST} coins first, obviously.")
            return

        profile["balance"] -= BOOST_COST
        profile["boost_ready"] = True
        save_balances(balances)
        new_balance = profile["balance"]

    await ctx.send(
        f"fine, ur boost is ready now. it cost {BOOST_COST} coins, and ur next gamble got 20% more win chance. "
        f"u got {new_balance} left."
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def sell(ctx):
    if ctx.guild is None:
        await ctx.send("do that in a server, not here.")
        return

    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(ctx.author.id))

        if profile["name_sold"]:
            await ctx.send(
                f"ur name already got sold, so stop trying. its still on auction for {NAME_AUCTION_PRICE} coins."
            )
            return

        original_name = ctx.author.display_name

        try:
            await ctx.author.edit(
                nick=SOLD_NAME,
                reason="User sold their name with !sell",
            )
        except discord.Forbidden:
            await ctx.send(
                "i cant steal ur name cuz the perms are being annoying."
            )
            return
        except discord.HTTPException:
            await ctx.send(
                "the name sale bugged out. try again later or whatever."
            )
            return

        profile["balance"] += SELL_REWARD
        profile["name_sold"] = True
        profile["original_name"] = original_name
        save_balances(balances)
        new_balance = profile["balance"]

    await ctx.send(
        f"fine, ur name got sold for {SELL_REWARD} coins. "
        f"its on auction for {NAME_AUCTION_PRICE} now, and u got {new_balance} coins."
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def buy(ctx, member: discord.Member):
    if ctx.guild is None:
        await ctx.send("do that in a server, not here.")
        return

    if member.id == ctx.author.id:
        await ctx.send("you cant buy ur own name, thats dumb.")
        return

    async with balances_lock:
        balances = load_balances()
        buyer_profile = get_profile(balances, str(ctx.author.id))
        seller_profile = get_profile(balances, str(member.id))

        if not seller_profile["name_sold"]:
            await ctx.send("that persons name aint even on auction.")
            return

        if not seller_profile["original_name"]:
            await ctx.send("i cant find the old name, so no.")
            return

        if buyer_profile["balance"] < NAME_AUCTION_PRICE:
            await ctx.send(
                f"you need {NAME_AUCTION_PRICE} coins for that, obviously."
            )
            return

        restored_name = seller_profile["original_name"]

        # Only finish the purchase if the old name can really be restored.
        try:
            await member.edit(
                nick=restored_name,
                reason=f"Name restored after purchase by {ctx.author}",
            )
        except discord.Forbidden:
            await ctx.send(
                "i cant restore that nickname cuz perms are being annoying again."
            )
            return
        except discord.HTTPException:
            await ctx.send(
                "the auction thing bugged out. try again later."
            )
            return

        buyer_profile["balance"] -= NAME_AUCTION_PRICE
        seller_profile["balance"] += NAME_AUCTION_PRICE
        seller_profile["name_sold"] = False
        seller_profile["original_name"] = None
        save_balances(balances)
        buyer_balance = buyer_profile["balance"]

    await ctx.send(
        f"fine, you bought {member.display_name}'s name for {NAME_AUCTION_PRICE} coins. "
        f"the old name is back now, and u got {buyer_balance} coins left."
    )


if __name__ == "__main__":
    if not token:
        raise ValueError("Missing bot_discord_token in the environment.")

    bot.run(token)
