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
    print(f"Logged in as {bot.user} and ready to keep the coin book tidy.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"Please slow down a little and try again in {error.retry_after:.1f} seconds."
        )
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You are missing an argument. Please use !help to see the command.")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("That argument did not look right. Please check it and try again.")
        return

    print(f"Error in command {ctx.command}: {error}")
    await ctx.send("Something went wrong on my side. Please try again in a moment.")


@bot.command()
async def help(ctx):
    help_message = (
        "Hello dear, here is my command list:\n"
        "`!help` - Show this help message.\n"
        "`!bal [member]` - Check your coins, or someone else's coins.\n"
        "`!daily` - Claim 50 coins once every 10 hours.\n"
        "`!gamble <amount>` - Bet some of your coins in a simple coin toss.\n"
        "`!boost` - Spend 50 coins to raise your next gamble win chance by 20%.\n"
        "`!sell` - Sell your name for 1000 coins and place it at auction for 10000 coins.\n"
        "`!buy <member>` - Buy a sold name for 10000 coins and restore it.\n"
        "`!daddy` - Reveal who daddy is.\n"
        "`!mommy` - Reveal who mommy is."
    )
    await ctx.send(help_message)


@bot.command()
async def bal(ctx, member: discord.Member = None):
    target = member or ctx.author

    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(target.id))
        save_balances(balances)

    await ctx.send(
        f"{target.display_name} is currently holding {profile['balance']} coins."
    )


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
                        "Your daily reward is still resting. "
                        f"Please wait {remaining}. The limit is once every 10 hours."
                    )
                except discord.Forbidden:
                    await ctx.send(
                        "I could not send you a private reminder, but your daily reward is still on its 10 hour limit."
                    )
                return

        profile["balance"] += DAILY_REWARD
        profile["last_daily"] = now.isoformat()
        save_balances(balances)
        new_balance = profile["balance"]

    await ctx.send(
        "Your daily reward has been tucked safely into your hands. "
        f"You received {DAILY_REWARD} coins and now have {new_balance} coins."
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def gamble(ctx, amount: int = None):
    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(ctx.author.id))

        if profile["balance"] <= 0:
            await ctx.send("You cannot gamble without any coins.")
            return

        if amount is None:
            await ctx.send("Please tell me how many coins you want to gamble.")
            return

        if amount <= 0:
            await ctx.send("Please choose a bet greater than 0.")
            return

        if amount > profile["balance"]:
            await ctx.send("You cannot bet more coins than you have.")
            return

        win_chance = BASE_GAMBLE_WIN_CHANCE
        used_boost = profile["boost_ready"]
        if used_boost:
            win_chance += BOOST_GAMBLE_BONUS
            profile["boost_ready"] = False

        if random.random() < win_chance:
            profile["balance"] += amount
            result_text = (
                f"Fortune stayed beside you this time. You won {amount} coins and now have {profile['balance']} coins."
            )
        else:
            profile["balance"] -= amount
            result_text = (
                f"The table turned cold this time. You lost {amount} coins and now have {profile['balance']} coins."
            )

        save_balances(balances)

    if used_boost:
        result_text += " Your boost was used for this gamble."

    await ctx.send(result_text)


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
            await ctx.send("You already have a boost waiting for your next gamble.")
            return

        if profile["balance"] < BOOST_COST:
            await ctx.send(f"You need {BOOST_COST} coins to buy a boost.")
            return

        profile["balance"] -= BOOST_COST
        profile["boost_ready"] = True
        save_balances(balances)
        new_balance = profile["balance"]

    await ctx.send(
        f"Your boost is ready. It cost {BOOST_COST} coins, and your next gamble now has 20% more win chance. "
        f"You now have {new_balance} coins."
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def sell(ctx):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return

    async with balances_lock:
        balances = load_balances()
        profile = get_profile(balances, str(ctx.author.id))

        if profile["name_sold"]:
            await ctx.send(
                f"Your name has already been sold. It is still sitting at auction for {NAME_AUCTION_PRICE} coins."
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
                "I could not take your name away because I do not have permission to change your nickname."
            )
            return
        except discord.HTTPException:
            await ctx.send(
                "Something interrupted the name sale. Please try again in a moment."
            )
            return

        profile["balance"] += SELL_REWARD
        profile["name_sold"] = True
        profile["original_name"] = original_name
        save_balances(balances)
        new_balance = profile["balance"]

    await ctx.send(
        f"Your name has been sold for {SELL_REWARD} coins. "
        f"It is now listed at auction for {NAME_AUCTION_PRICE} coins, and your balance is {new_balance} coins."
    )

@bot.command()
async def lb(ctx):
    balances = load_balances()
    if not balances:
        await ctx.send("No one has a balance yet")
        return
    sorted_balances = sorted(balances.items(), key=lambda x: x[1], reverse=True)
    leaderboard_text = "**Coin Leaderboard**\n\n"
    for i, (user_id, balance) in enumerate(sorted_balances[:10], start=1):
        user = await bot.fetch_user(int(user_id))
        leaderboard_text += f"**{i}.** {user.display_name} — {balance} coins\n"

    await ctx.send(leaderboard_text)

@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def buy(ctx, member: discord.Member):
    if ctx.guild is None:
        await ctx.send("This command can only be used inside a server.")
        return

    if member.id == ctx.author.id:
        await ctx.send("You cannot buy your own name.")
        return

    async with balances_lock:
        balances = load_balances()
        buyer_profile = get_profile(balances, str(ctx.author.id))
        seller_profile = get_profile(balances, str(member.id))

        if not seller_profile["name_sold"]:
            await ctx.send("That person's name is not up for auction.")
            return

        if not seller_profile["original_name"]:
            await ctx.send("I could not find the original name for that sale.")
            return

        if buyer_profile["balance"] < NAME_AUCTION_PRICE:
            await ctx.send(
                f"You need {NAME_AUCTION_PRICE} coins to buy that name."
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
                "I could not restore that nickname because I do not have permission."
            )
            return
        except discord.HTTPException:
            await ctx.send(
                "Something interrupted the auction purchase. Please try again in a moment."
            )
            return

        buyer_profile["balance"] -= NAME_AUCTION_PRICE
        seller_profile["balance"] += NAME_AUCTION_PRICE
        seller_profile["name_sold"] = False
        seller_profile["original_name"] = None
        save_balances(balances)
        buyer_balance = buyer_profile["balance"]

    await ctx.send(
        f"You bought {member.display_name}'s name for {NAME_AUCTION_PRICE} coins. "
        f"The original name has been restored, and you now have {buyer_balance} coins."
    )


if __name__ == "__main__":
    if not token:
        raise ValueError("Missing bot_discord_token in the environment.")

    bot.run(token)
