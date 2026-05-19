import asyncio
import json
import logging
import os
import random
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive

keep_alive()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
LEGACY_ENV_FILE = os.path.join(BASE_DIR, "env")
LEGACY_BALANCES_FILE = os.path.join(BASE_DIR, "balances.json")
DATABASE_FILE = os.path.join(BASE_DIR, "gambledawn.sqlite3")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "gambledawn.log")

DEFAULT_BALANCE = 100
DAILY_COOLDOWN = timedelta(hours=10)
DAILY_BASE_REWARD = 50
DAILY_STREAK_BONUS = 10
DAILY_STREAK_CAP = 7
WORK_COOLDOWN = timedelta(hours=1)
WORK_MIN_REWARD = 90
WORK_MAX_REWARD = 180
ROB_COOLDOWN = timedelta(hours=2)
ROB_TARGET_PROTECTION = timedelta(minutes=45)
ROB_MIN_BALANCE = 80
ROB_TARGET_MIN_BALANCE = 120
ROBBERY_SUCCESS_BASE = 0.35
ROBBERY_SUCCESS_STEP = 0.10
SELL_REWARD = 1000
NAME_AUCTION_PRICE = 10000
SOLD_NAME = "NO NAME, THIS DUMBAH SELLED IT"
BOOST_COST = 50
BOOST_GAMBLE_BONUS = 0.40
BASE_GAMBLE_WIN_CHANCE = 0.50
UPGRADE_GAMBLE_BONUS = 0.05
MAX_GAMBLE_WIN_CHANCE = 0.85
LEADERBOARD_LIMIT = 10
DB_BACKUP_INTERVAL = timedelta(minutes=30)
EMBED_COLOR = discord.Color.from_rgb(255, 173, 214)
SUCCESS_COLOR = discord.Color.from_rgb(157, 224, 173)
WARNING_COLOR = discord.Color.from_rgb(255, 214, 165)
ERROR_COLOR = discord.Color.from_rgb(255, 120, 120)

SHIP_OPENERS = [
    "those two got enough tension to fog up the whole place",
    "one glance between em and the room starts feelin indecent",
    "yeah, those two look like a bad idea in the best way",
    "im not sayin they want each other bad, but im also not blind",
    "put those two close for five minutes and somethin shameless is happenin",
    "that pair got heat drippin off em and everybody can see it",
]

SHIP_SPICE = [
    "the eye contact alone is doin way too much work",
    "the kinda vibe between em could make a saint blush",
    "they got that handsy little energy just waitin for an excuse",
    "the chemistry is pushin past cute and into dangerous real fast",
    "it feels like theyd ruin each others sleep schedule on purpose",
    "the tension is loud enough to hear from across the server",
]

SHIP_PAYOFFS = [
    "somebody better chaperone that mess before it gets worse",
    "if the lights get lower, their self control is gone",
    "im givin that ship my full filthy approval",
    "thats the sorta pairing that starts with teasing and ends with trouble",
    "call it what u want, i call it loaded",
    "yeah, that ship got no business actin that hot in public",
]

SHIP_ENDINGS = [
    "and no, im not apologizin for sayin what everybody else was thinkin",
    "somebody keep em apart or dont, depends how messy u want tonight",
    "if they act innocent after this, theyre both terrible liars",
    "dont look at me like that, im just readin the filth in the air",
]

SHIP_SECRET_CODE = "heatwave"

SHOP_ITEMS = {
    "boost": {
        "type": "consumable",
        "cost": BOOST_COST,
        "description": "One use gives ur next gamble +40% win chance~",
    },
    "shield": {
        "type": "consumable",
        "cost": 160,
        "description": "Blocks one rob attempt against u~",
    },
    "lucky_charm": {
        "type": "upgrade",
        "base_cost": 260,
        "cost_step": 200,
        "max_level": 3,
        "column": "luck_level",
        "description": "+5% gamble win chance each level~",
    },
    "work_gloves": {
        "type": "upgrade",
        "base_cost": 220,
        "cost_step": 170,
        "max_level": 5,
        "column": "work_level",
        "description": "+15 max work coins each level~",
    },
    "lock": {
        "type": "upgrade",
        "base_cost": 280,
        "cost_step": 210,
        "max_level": 3,
        "column": "defense_level",
        "description": "-10% rob success against u each level~",
    },
    "crowbar": {
        "type": "upgrade",
        "base_cost": 300,
        "cost_step": 230,
        "max_level": 3,
        "column": "rob_level",
        "description": "+10% rob success each level~",
    },
}

db_lock = asyncio.Lock()


def ensure_runtime_dirs():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)


def configure_logging():
    logger = logging.getLogger("gambledawn")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


ensure_runtime_dirs()
logger = configure_logging()


if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)
elif os.path.exists(LEGACY_ENV_FILE):
    load_dotenv(LEGACY_ENV_FILE)

token = os.getenv("bot_discord_token")


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


def speak(text):
    raw_text = str(text).strip()
    if not raw_text:
        return "~"
    if raw_text.endswith("~"):
        return raw_text
    return f"{raw_text}~"


def style_block(text):
    lines = []
    for line in str(text).splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        lines.append(speak(stripped))
    return "\n".join(lines)


def make_embed(title, description, color=EMBED_COLOR):
    embed = discord.Embed(
        title=speak(title),
        description=style_block(description),
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="quit starin already, i know u like the way i talk~")
    return embed


def add_field(embed, name, value, inline=False):
    embed.add_field(
        name=speak(name),
        value=style_block(value),
        inline=inline,
    )


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


def parse_saved_date(saved_value):
    if not saved_value:
        return None

    try:
        return date.fromisoformat(saved_value)
    except ValueError:
        return None


def format_remaining_time(remaining):
    total_seconds = max(int(remaining.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
    return " and ".join(parts)


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def get_connection():
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA foreign_keys=ON;")
    return connection


def set_setting(connection, key, value):
    connection.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def get_setting(connection, key, default=None):
    row = connection.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return default
    return row["value"]


def init_database():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 100,
                last_daily TEXT,
                daily_streak INTEGER NOT NULL DEFAULT 0,
                last_daily_date TEXT,
                last_work TEXT,
                last_rob TEXT,
                last_robbed_at TEXT,
                gamble_wins INTEGER NOT NULL DEFAULT 0,
                gamble_losses INTEGER NOT NULL DEFAULT 0,
                total_work_earnings INTEGER NOT NULL DEFAULT 0,
                total_rob_earnings INTEGER NOT NULL DEFAULT 0,
                total_rob_losses INTEGER NOT NULL DEFAULT 0,
                rob_successes INTEGER NOT NULL DEFAULT 0,
                rob_failures INTEGER NOT NULL DEFAULT 0,
                name_sold INTEGER NOT NULL DEFAULT 0,
                original_name TEXT,
                boost_ready INTEGER NOT NULL DEFAULT 0,
                luck_level INTEGER NOT NULL DEFAULT 0,
                work_level INTEGER NOT NULL DEFAULT 0,
                defense_level INTEGER NOT NULL DEFAULT 0,
                rob_level INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS inventory (
                user_id TEXT NOT NULL,
                item_key TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, item_key)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS economy_mods (
                user_id TEXT PRIMARY KEY,
                added_by TEXT NOT NULL,
                added_at TEXT NOT NULL
            );
            """
        )

        if get_setting(connection, "legacy_json_migrated") is None:
            set_setting(connection, "legacy_json_migrated", "0")

        connection.commit()


def backup_legacy_balances_json():
    if not os.path.exists(LEGACY_BALANCES_FILE):
        return None

    if os.path.getsize(LEGACY_BALANCES_FILE) == 0:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"balances-{timestamp}.json")
    shutil.copy2(LEGACY_BALANCES_FILE, backup_path)
    logger.info("Legacy balances.json backup created at %s", backup_path)
    return backup_path


def create_database_backup(connection=None, force=False):
    now = datetime.now(timezone.utc)

    if not os.path.exists(DATABASE_FILE):
        return None

    if connection is not None:
        try:
            connection.commit()
        except sqlite3.Error:
            logger.exception("Could not commit before database backup")

    latest_backup_time = None
    for file_name in os.listdir(BACKUP_DIR):
        if not file_name.startswith("gambledawn-") or not file_name.endswith(".sqlite3"):
            continue

        backup_path = os.path.join(BACKUP_DIR, file_name)
        backup_mtime = datetime.fromtimestamp(os.path.getmtime(backup_path), tz=timezone.utc)
        if latest_backup_time is None or backup_mtime > latest_backup_time:
            latest_backup_time = backup_mtime

    if not force and latest_backup_time and now - latest_backup_time < DB_BACKUP_INTERVAL:
        return None

    timestamp = now.strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"gambledawn-{timestamp}.sqlite3")

    try:
        with sqlite3.connect(DATABASE_FILE, timeout=30) as source_connection:
            with sqlite3.connect(backup_path, timeout=30) as backup_connection:
                source_connection.backup(backup_connection)
    except sqlite3.Error:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        logger.exception("SQLite backup failed")
        return None

    logger.info("SQLite backup created at %s", backup_path)
    return backup_path


def ensure_user(connection, user_id):
    connection.execute(
        """
        INSERT OR IGNORE INTO users (
            user_id,
            balance
        ) VALUES (?, ?)
        """,
        (str(user_id), DEFAULT_BALANCE),
    )


def get_user_record(connection, user_id):
    ensure_user(connection, user_id)
    row = connection.execute(
        "SELECT * FROM users WHERE user_id = ?",
        (str(user_id),),
    ).fetchone()
    return dict(row)


def update_user_columns(connection, user_id, **columns):
    if not columns:
        return

    assignments = ", ".join(f"{column} = ?" for column in columns)
    values = list(columns.values()) + [str(user_id)]
    connection.execute(
        f"UPDATE users SET {assignments} WHERE user_id = ?",
        values,
    )


def get_inventory_quantity(connection, user_id, item_key):
    row = connection.execute(
        """
        SELECT quantity
        FROM inventory
        WHERE user_id = ? AND item_key = ?
        """,
        (str(user_id), item_key),
    ).fetchone()
    if row is None:
        return 0
    return int(row["quantity"])


def add_inventory_item(connection, user_id, item_key, quantity):
    current_quantity = get_inventory_quantity(connection, user_id, item_key)
    new_quantity = max(0, current_quantity + quantity)

    connection.execute(
        """
        INSERT INTO inventory (user_id, item_key, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, item_key) DO UPDATE SET quantity = excluded.quantity
        """,
        (str(user_id), item_key, new_quantity),
    )

    if new_quantity == 0:
        connection.execute(
            "DELETE FROM inventory WHERE user_id = ? AND item_key = ?",
            (str(user_id), item_key),
        )


def get_inventory_map(connection, user_id):
    rows = connection.execute(
        """
        SELECT item_key, quantity
        FROM inventory
        WHERE user_id = ? AND quantity > 0
        ORDER BY item_key
        """,
        (str(user_id),),
    ).fetchall()
    return {row["item_key"]: int(row["quantity"]) for row in rows}


def get_upgrade_cost(user_record, item_key):
    item = SHOP_ITEMS[item_key]
    current_level = int(user_record[item["column"]])
    return item["base_cost"] + (current_level * item["cost_step"])


def normalize_shop_key(raw_key):
    if not raw_key:
        return None

    normalized = raw_key.lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in SHOP_ITEMS else None


def is_admin(member):
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild


def is_bot_mod(user_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM economy_mods WHERE user_id = ? LIMIT 1",
            (str(user_id),),
        ).fetchone()
    return row is not None


def can_grant_mod_access(ctx):
    if ctx.guild is None:
        return False

    if ctx.author.id == ctx.guild.owner_id:
        return True

    return is_admin(ctx.author)


def can_manage_economy(ctx):
    if ctx.guild is None:
        return False

    if ctx.author.id == ctx.guild.owner_id:
        return True

    if is_admin(ctx.author):
        return True

    return is_bot_mod(ctx.author.id)


def migrate_legacy_json_if_needed():
    with get_connection() as connection:
        if get_setting(connection, "legacy_json_migrated", "0") == "1":
            return

        if not os.path.exists(LEGACY_BALANCES_FILE):
            set_setting(connection, "legacy_json_migrated", "1")
            connection.commit()
            return

        backup_legacy_balances_json()

        try:
            with open(LEGACY_BALANCES_FILE, "r", encoding="utf-8") as file:
                content = file.read().strip()
                legacy_data = json.loads(content) if content else {}
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Legacy balances migration skipped: %s", error)
            set_setting(connection, "legacy_json_migrated", "1")
            connection.commit()
            return

        migrated_users = 0
        for user_id, raw_profile in legacy_data.items():
            ensure_user(connection, user_id)
            if isinstance(raw_profile, int):
                update_user_columns(
                    connection,
                    user_id,
                    balance=raw_profile,
                )
                migrated_users += 1
                continue

            if isinstance(raw_profile, dict):
                update_user_columns(
                    connection,
                    user_id,
                    balance=int(raw_profile.get("balance", DEFAULT_BALANCE)),
                    last_daily=raw_profile.get("last_daily"),
                    name_sold=int(bool(raw_profile.get("name_sold", False))),
                    original_name=raw_profile.get("original_name"),
                    boost_ready=int(bool(raw_profile.get("boost_ready", False))),
                )
                migrated_users += 1

        set_setting(connection, "legacy_json_migrated", "1")
        connection.commit()
        logger.info("Legacy JSON migration finished for %s users", migrated_users)

    create_database_backup(force=True)


init_database()
migrate_legacy_json_if_needed()


async def send_embed_message(ctx, title, description, color=EMBED_COLOR, fields=None):
    embed = make_embed(title, description, color=color)
    for field in fields or []:
        add_field(
            embed,
            field["name"],
            field["value"],
            inline=field.get("inline", False),
        )
    await ctx.send(embed=embed)


async def send_dm_message(user, title, description, color=WARNING_COLOR, fields=None):
    embed = make_embed(title, description, color=color)
    for field in fields or []:
        add_field(
            embed,
            field["name"],
            field["value"],
            inline=field.get("inline", False),
        )
    await user.send(embed=embed)


async def resolve_member_name(ctx, user_id):
    if ctx.guild is not None:
        member = ctx.guild.get_member(int(user_id))
        if member is not None:
            return member.display_name

    try:
        user = await bot.fetch_user(int(user_id))
        return user.display_name
    except (discord.NotFound, discord.HTTPException, ValueError):
        return f"Unknown User {user_id}"


async def run_gamble(ctx, amount):
    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, ctx.author.id)

            if user_record["balance"] <= 0:
                await send_embed_message(
                    ctx,
                    "No Coins Left",
                    "y-you cant gamble with no coins, genius~",
                    color=ERROR_COLOR,
                )
                return

            if amount is None:
                await send_embed_message(
                    ctx,
                    "Say The Bet",
                    "just say how much ur betting already, baka~",
                    color=WARNING_COLOR,
                )
                return

            if amount <= 0:
                await send_embed_message(
                    ctx,
                    "Bad Bet",
                    "pick a number over 0 maybe, this isnt hard~",
                    color=WARNING_COLOR,
                )
                return

            if amount > user_record["balance"]:
                await send_embed_message(
                    ctx,
                    "Too Broke",
                    "you cant bet more then what u got, stop dreamin~",
                    color=ERROR_COLOR,
                )
                return

            win_chance = BASE_GAMBLE_WIN_CHANCE + (user_record["luck_level"] * UPGRADE_GAMBLE_BONUS)
            used_boost = bool(user_record["boost_ready"])
            if used_boost:
                win_chance += BOOST_GAMBLE_BONUS

            win_chance = clamp(win_chance, 0.10, MAX_GAMBLE_WIN_CHANCE)
            if random.random() < win_chance:
                new_balance = user_record["balance"] + amount
                new_wins = user_record["gamble_wins"] + 1
                new_losses = user_record["gamble_losses"]
                result_title = "Lucky Brat"
                result_text = f"tch, u got lucky this time and won {amount} coins~"
                color = SUCCESS_COLOR
            else:
                new_balance = user_record["balance"] - amount
                new_wins = user_record["gamble_wins"]
                new_losses = user_record["gamble_losses"] + 1
                result_title = "Table Said No"
                result_text = f"see, the table clowned u and took {amount} coins~"
                color = ERROR_COLOR

            update_user_columns(
                connection,
                ctx.author.id,
                balance=new_balance,
                gamble_wins=new_wins,
                gamble_losses=new_losses,
                boost_ready=0 if used_boost else int(user_record["boost_ready"]),
            )
            create_database_backup(connection)
            connection.commit()

            win_rate_total = new_wins + new_losses
            win_rate = (new_wins / win_rate_total * 100) if win_rate_total else 0

    fields = [
        {"name": "Balance", "value": f"{new_balance} coins"},
        {"name": "Win Chance", "value": f"{int(win_chance * 100)} percent"},
        {"name": "Stats", "value": f"{new_wins} wins / {new_losses} losses ({win_rate:.1f}% win rate)"},
    ]
    if used_boost:
        fields.append({"name": "Boost", "value": "ur saved boost got used up just now"})

    logger.info(
        "gamble user=%s amount=%s balance=%s",
        ctx.author.id,
        amount,
        new_balance,
    )
    await send_embed_message(ctx, result_title, result_text, color=color, fields=fields)


@bot.event
async def on_ready():
    logger.info("Bot ready as %s", bot.user)
    print(f"Logged in as {bot.user}~")


@bot.event
async def on_command(ctx):
    logger.info(
        "command user=%s guild=%s command=%s",
        ctx.author.id,
        getattr(ctx.guild, "id", "dm"),
        ctx.message.content,
    )


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandOnCooldown):
        await send_embed_message(
            ctx,
            "Too Fast",
            f"slow down already and try again in {error.retry_after:.1f} seconds~",
            color=WARNING_COLOR,
        )
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await send_embed_message(
            ctx,
            "Missing Stuff",
            "u forgot part of the command, so go read !help or somethin~",
            color=WARNING_COLOR,
        )
        return

    if isinstance(error, commands.BadArgument):
        await send_embed_message(
            ctx,
            "Bad Input",
            "that argument looks wrong, type it better next time~",
            color=WARNING_COLOR,
        )
        return

    if isinstance(error, commands.MissingPermissions):
        await send_embed_message(
            ctx,
            "No Admin Powers",
            "you aint allowed to do that, so dont act shocked now~",
            color=ERROR_COLOR,
        )
        return

    if isinstance(error, commands.NoPrivateMessage):
        await send_embed_message(
            ctx,
            "Server Only",
            "that one only works inside a server, not in dms~",
            color=WARNING_COLOR,
        )
        return

    if isinstance(error, commands.CheckFailure):
        await send_embed_message(
            ctx,
            "No Admin Powers",
            "u need to be the server owner, a real admin, or a bot mod for that one~",
            color=ERROR_COLOR,
        )
        return

    logger.exception("Unhandled command error in %s", ctx.command, exc_info=error)
    await send_embed_message(
        ctx,
        "Bot Tripped",
        "s-something broke on my side, ok? try again in a sec~",
        color=ERROR_COLOR,
    )


@bot.command()
async def help(ctx):
    fields = [
        {"name": "Economy", "value": "`!bal [user]`, `!leaderboard`, `!work`, `!daily`, `!stats [user]`"},
        {"name": "Risky Stuff", "value": "`!gamble <amount>`, `!rob <user>`"},
        {"name": "Items", "value": "`!inventory`, `!shop`, `!boost`"},
        {"name": "Name Market", "value": "`!sell`, `!buy <user>`"},
        {"name": "Admin", "value": "`!addcoins`, `!takecoins`, `!setcoins`, `!addmod <user>`, `!removemod <user>`"},
        {"name": "Silly", "value": "`!daddy`, `!mommy`, `!ship`"},
    ]
    await send_embed_message(
        ctx,
        "Fine Heres Help",
        "this is a whole economy game now, so read it nice n slow with those hungry eyes of urs~",
        fields=fields,
    )


@bot.command(aliases=["balance"])
async def bal(ctx, member: discord.Member = None):
    target = member or ctx.author

    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, target.id)

    total_gambles = user_record["gamble_wins"] + user_record["gamble_losses"]
    win_rate = (user_record["gamble_wins"] / total_gambles * 100) if total_gambles else 0

    fields = [
        {"name": "Coins", "value": f"{user_record['balance']}"},
        {"name": "Daily Streak", "value": f"{user_record['daily_streak']}"},
        {"name": "Gamble Stats", "value": f"{user_record['gamble_wins']} wins / {user_record['gamble_losses']} losses ({win_rate:.1f}% win rate)"},
    ]
    await send_embed_message(
        ctx,
        "Coin Bag",
        f"{target.display_name} got coins and stats right here, so dont pretend u cant read em~",
        fields=fields,
    )


@bot.command(aliases=["leaderboard", "top"])
async def lb(ctx):
    async with db_lock:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT user_id, balance
                FROM users
                ORDER BY balance DESC, user_id ASC
                LIMIT ?
                """,
                (LEADERBOARD_LIMIT,),
            ).fetchall()

    if not rows:
        await send_embed_message(
            ctx,
            "Empty Board",
            "nobody even got coins yet, thats kinda pathetic honestly~",
            color=WARNING_COLOR,
        )
        return

    embed = make_embed(
        "Coin Leaderboard",
        "dont get all smug if ur first, its embarassin to watch~",
        color=SUCCESS_COLOR,
    )
    for index, row in enumerate(rows, start=1):
        member_name = await resolve_member_name(ctx, row["user_id"])
        add_field(embed, f"#{index}", f"{member_name} - {row['balance']} coins")
    await ctx.send(embed=embed)


@bot.command()
async def stats(ctx, member: discord.Member = None):
    target = member or ctx.author

    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, target.id)
            inventory = get_inventory_map(connection, target.id)

    total_gambles = user_record["gamble_wins"] + user_record["gamble_losses"]
    win_rate = (user_record["gamble_wins"] / total_gambles * 100) if total_gambles else 0
    items_text = ", ".join(
        f"{item_key} x{quantity}" for item_key, quantity in inventory.items()
    ) or "nothing at all"
    fields = [
        {"name": "Gamble", "value": f"{user_record['gamble_wins']} wins / {user_record['gamble_losses']} losses ({win_rate:.1f}% rate)"},
        {"name": "Work Earnings", "value": f"{user_record['total_work_earnings']} coins"},
        {"name": "Robbery", "value": f"{user_record['rob_successes']} wins / {user_record['rob_failures']} fails"},
        {"name": "Rob Totals", "value": f"stole {user_record['total_rob_earnings']} / lost {user_record['total_rob_losses']}"},
        {"name": "Upgrades", "value": f"luck {user_record['luck_level']}, work {user_record['work_level']}, lock {user_record['defense_level']}, crowbar {user_record['rob_level']}"},
        {"name": "Items", "value": items_text},
    ]
    await send_embed_message(
        ctx,
        "Stats Page",
        f"these are {target.display_name}'s numbers, so dont cry if they look bad~",
        fields=fields,
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def daily(ctx):
    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, ctx.author.id)
            now = datetime.now(timezone.utc)
            last_daily = parse_saved_time(user_record["last_daily"])

            if last_daily:
                next_claim = last_daily + DAILY_COOLDOWN
                if now < next_claim:
                    remaining = format_remaining_time(next_claim - now)
                    try:
                        await send_dm_message(
                            ctx.author,
                            "Daily Not Ready",
                            f"ur daily still aint ready, so just wait {remaining} ok~",
                        )
                    except discord.Forbidden:
                        await send_embed_message(
                            ctx,
                            "Daily Not Ready",
                            f"i cant dm u, but ur daily still needs {remaining} more~",
                            color=WARNING_COLOR,
                        )
                    return

            today = now.date()
            last_daily_date = parse_saved_date(user_record["last_daily_date"])
            if last_daily_date is None:
                streak = 1
            elif today - last_daily_date == timedelta(days=1):
                streak = min(user_record["daily_streak"] + 1, DAILY_STREAK_CAP)
            elif today == last_daily_date:
                streak = max(user_record["daily_streak"], 1)
            else:
                streak = 1

            streak_bonus = min((streak - 1) * DAILY_STREAK_BONUS, (DAILY_STREAK_CAP - 1) * DAILY_STREAK_BONUS)
            reward = DAILY_BASE_REWARD + streak_bonus
            new_balance = user_record["balance"] + reward

            update_user_columns(
                connection,
                ctx.author.id,
                balance=new_balance,
                last_daily=now.isoformat(),
                last_daily_date=today.isoformat(),
                daily_streak=streak,
            )
            create_database_backup(connection)
            connection.commit()

    fields = [
        {"name": "Base Reward", "value": f"{DAILY_BASE_REWARD} coins"},
        {"name": "Streak Bonus", "value": f"{streak_bonus} coins"},
        {"name": "Streak", "value": f"{streak} day{'s' if streak != 1 else ''}"},
        {"name": "Balance", "value": f"{new_balance} coins"},
    ]
    logger.info("daily user=%s reward=%s streak=%s", ctx.author.id, reward, streak)
    await send_embed_message(
        ctx,
        "Daily Claimed",
        f"fine, take ur {reward} daily coins already and dont get all clingy about it~",
        color=SUCCESS_COLOR,
        fields=fields,
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def work(ctx):
    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, ctx.author.id)
            now = datetime.now(timezone.utc)
            last_work = parse_saved_time(user_record["last_work"])

            if last_work:
                next_work = last_work + WORK_COOLDOWN
                if now < next_work:
                    remaining = format_remaining_time(next_work - now)
                    await send_embed_message(
                        ctx,
                        "Still Busy",
                        f"u literally just worked, so sit pretty and wait {remaining} before beggin me again~",
                        color=WARNING_COLOR,
                    )
                    return

            reward = random.randint(
                WORK_MIN_REWARD,
                WORK_MAX_REWARD + (user_record["work_level"] * 15),
            )
            new_balance = user_record["balance"] + reward

            update_user_columns(
                connection,
                ctx.author.id,
                balance=new_balance,
                last_work=now.isoformat(),
                total_work_earnings=user_record["total_work_earnings"] + reward,
            )
            create_database_backup(connection)
            connection.commit()

    jobs = [
        "worked the late shift and made every room feel warmer",
        "sold sweet little lies to clueless customers",
        "delivered snacks while lookin way too distractin for the job",
        "talked a rich fool into tipping extra hard",
        "made a boring shift feel way less innocent then it shoulda been",
    ]
    fields = [
        {"name": "Work Reward", "value": f"{reward} coins"},
        {"name": "Work Level", "value": f"{user_record['work_level']}"},
        {"name": "Balance", "value": f"{new_balance} coins"},
    ]
    logger.info("work user=%s reward=%s", ctx.author.id, reward)
    await send_embed_message(
        ctx,
        "Work Done",
        f"you {random.choice(jobs)} and came back with {reward} coins clingin to ur hands~",
        color=SUCCESS_COLOR,
        fields=fields,
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def gamble(ctx, amount: int = None):
    await run_gamble(ctx, amount)


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def boost(ctx):
    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, ctx.author.id)
            if user_record["boost_ready"]:
                await send_embed_message(
                    ctx,
                    "Boost Already Armed",
                    "you already got a boost ready, so stop hoardin drama~",
                    color=WARNING_COLOR,
                )
                return

            inventory_boosts = get_inventory_quantity(connection, ctx.author.id, "boost")
            balance = user_record["balance"]
            source_text = ""

            if inventory_boosts > 0:
                add_inventory_item(connection, ctx.author.id, "boost", -1)
                source_text = "used one stored boost item"
            elif balance >= BOOST_COST:
                balance -= BOOST_COST
                update_user_columns(connection, ctx.author.id, balance=balance)
                source_text = f"bought one on the spot for {BOOST_COST} coins"
            else:
                await send_embed_message(
                    ctx,
                    "Too Broke For Boost",
                    f"you need a stored boost or at least {BOOST_COST} coins first, obviously~",
                    color=ERROR_COLOR,
                )
                return

            update_user_columns(connection, ctx.author.id, boost_ready=1)
            refreshed = get_user_record(connection, ctx.author.id)
            stored_boosts_left = get_inventory_quantity(connection, ctx.author.id, "boost")
            create_database_backup(connection)
            connection.commit()

    fields = [
        {"name": "What Happened", "value": source_text},
        {"name": "Next Gamble", "value": "gets +40% win chance"},
        {"name": "Balance", "value": f"{refreshed['balance']} coins"},
        {"name": "Stored Boosts Left", "value": f"{stored_boosts_left}"},
    ]
    await send_embed_message(
        ctx,
        "Boost Armed",
        "fine, ur boost is ready now, so make the next bet worth watchin for me ok~",
        color=SUCCESS_COLOR,
        fields=fields,
    )


@bot.command(aliases=["inv"])
async def inventory(ctx, member: discord.Member = None):
    target = member or ctx.author

    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, target.id)
            inventory_map = get_inventory_map(connection, target.id)

    consumables = []
    for item_key, quantity in inventory_map.items():
        item_data = SHOP_ITEMS.get(item_key)
        if item_data is not None:
            consumables.append(f"{item_key} x{quantity} - {item_data['description']}")

    if not consumables:
        consumables_text = "nothing in there but dust"
    else:
        consumables_text = "\n".join(consumables)

    upgrade_lines = [
        f"lucky_charm lvl {user_record['luck_level']}",
        f"work_gloves lvl {user_record['work_level']}",
        f"lock lvl {user_record['defense_level']}",
        f"crowbar lvl {user_record['rob_level']}",
    ]
    fields = [
        {"name": "Consumables", "value": consumables_text},
        {"name": "Upgrades", "value": "\n".join(upgrade_lines)},
        {"name": "Boost Armed", "value": "yes" if user_record["boost_ready"] else "no"},
    ]
    await send_embed_message(
        ctx,
        "Inventory Bag",
        f"heres what {target.display_name} is carryin around, not that i care much~",
        fields=fields,
    )


@bot.command()
async def shop(ctx, action: str = None, item_name: str = None, amount: int = 1):
    if action is None:
        async with db_lock:
            with get_connection() as connection:
                user_record = get_user_record(connection, ctx.author.id)

        embed = make_embed(
            "Shop Shelf",
            "buy stuff with `!shop buy <item> [amount]`, and dont make a mess in here~",
            color=SUCCESS_COLOR,
        )
        for item_key, item in SHOP_ITEMS.items():
            if item["type"] == "consumable":
                price_text = f"{item['cost']} coins each"
            else:
                price_text = (
                    f"next cost {get_upgrade_cost(user_record, item_key)} coins"
                    f" / max lvl {item['max_level']}"
                )
            add_field(embed, item_key, f"{item['description']}\n{price_text}")
        await ctx.send(embed=embed)
        return

    lowered_action = action.lower()
    if lowered_action not in {"buy", "info", "list"}:
        item_name = action
        lowered_action = "buy"

    if lowered_action == "list":
        await shop(ctx)
        return

    shop_key = normalize_shop_key(item_name)
    if shop_key is None:
        await send_embed_message(
            ctx,
            "Bad Shop Item",
            "that item aint in the shop, so maybe try reading the list first~",
            color=WARNING_COLOR,
        )
        return

    item = SHOP_ITEMS[shop_key]

    if lowered_action == "info":
        fields = [{"name": "Description", "value": item["description"]}]
        if item["type"] == "consumable":
            fields.append({"name": "Cost", "value": f"{item['cost']} coins each"})
        else:
            fields.append({"name": "Max Level", "value": f"{item['max_level']}"})
        await send_embed_message(
            ctx,
            "Shop Info",
            f"here, read the item info and stop pokin random buttons~",
            fields=fields,
        )
        return

    if amount <= 0:
        await send_embed_message(
            ctx,
            "Bad Amount",
            "buying zero or minus stuff is not how shops work, baka~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, ctx.author.id)

            if item["type"] == "consumable":
                total_cost = item["cost"] * amount
                if user_record["balance"] < total_cost:
                    await send_embed_message(
                        ctx,
                        "Too Broke",
                        f"you need {total_cost} coins for that and u dont got it~",
                        color=ERROR_COLOR,
                    )
                    return

                add_inventory_item(connection, ctx.author.id, shop_key, amount)
                update_user_columns(
                    connection,
                    ctx.author.id,
                    balance=user_record["balance"] - total_cost,
                )
                new_balance = user_record["balance"] - total_cost
                new_qty = get_inventory_quantity(connection, ctx.author.id, shop_key)
                fields = [
                    {"name": "Bought", "value": f"{shop_key} x{amount}"},
                    {"name": "Cost", "value": f"{total_cost} coins"},
                    {"name": "Inventory Now", "value": f"{new_qty}"},
                    {"name": "Balance", "value": f"{new_balance} coins"},
                ]
                logger.info("shop consumable user=%s item=%s amount=%s", ctx.author.id, shop_key, amount)
            else:
                level_column = item["column"]
                current_level = user_record[level_column]
                if current_level >= item["max_level"]:
                    await send_embed_message(
                        ctx,
                        "Maxed Out",
                        "that upgrade is already maxed, so calm down maybe~",
                        color=WARNING_COLOR,
                    )
                    return

                cost = get_upgrade_cost(user_record, shop_key)
                if user_record["balance"] < cost:
                    await send_embed_message(
                        ctx,
                        "Too Broke",
                        f"you need {cost} coins for that upgrade, duh~",
                        color=ERROR_COLOR,
                    )
                    return

                new_level = current_level + 1
                new_balance = user_record["balance"] - cost
                update_user_columns(
                    connection,
                    ctx.author.id,
                    balance=new_balance,
                    **{level_column: new_level},
                )
                fields = [
                    {"name": "Upgrade", "value": shop_key},
                    {"name": "New Level", "value": f"{new_level}"},
                    {"name": "Cost", "value": f"{cost} coins"},
                    {"name": "Balance", "value": f"{new_balance} coins"},
                ]
                logger.info("shop upgrade user=%s item=%s new_level=%s", ctx.author.id, shop_key, new_level)

            create_database_backup(connection)
            connection.commit()

    await send_embed_message(
        ctx,
        "Shop Bought",
        f"fine, ur purchase went through, so dont stand there starin at me now~",
        color=SUCCESS_COLOR,
        fields=fields,
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def rob(ctx, member: discord.Member):
    if ctx.guild is None:
        await send_embed_message(
            ctx,
            "No Robbing Here",
            "do that in a server maybe, not in my dms like a weirdo~",
            color=ERROR_COLOR,
        )
        return

    if member.id == ctx.author.id:
        await send_embed_message(
            ctx,
            "Self Rob",
            "you cant rob urself, thats just sad even for u~",
            color=WARNING_COLOR,
        )
        return

    if member.bot:
        await send_embed_message(
            ctx,
            "Bot Target",
            "leave the bots alone, go bother a real person instead~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            robber = get_user_record(connection, ctx.author.id)
            target = get_user_record(connection, member.id)
            now = datetime.now(timezone.utc)

            last_rob = parse_saved_time(robber["last_rob"])
            if last_rob and now < last_rob + ROB_COOLDOWN:
                remaining = format_remaining_time((last_rob + ROB_COOLDOWN) - now)
                await send_embed_message(
                    ctx,
                    "Rob Cooldown",
                    f"u gotta lay low for {remaining} before robbing again~",
                    color=WARNING_COLOR,
                )
                return

            last_robbed_at = parse_saved_time(target["last_robbed_at"])
            if last_robbed_at and now < last_robbed_at + ROB_TARGET_PROTECTION:
                remaining = format_remaining_time((last_robbed_at + ROB_TARGET_PROTECTION) - now)
                await send_embed_message(
                    ctx,
                    "Target Protected",
                    f"that target got hit too recently, so wait {remaining} and quit spammin~",
                    color=WARNING_COLOR,
                )
                return

            if robber["balance"] < ROB_MIN_BALANCE:
                await send_embed_message(
                    ctx,
                    "Need More Coins",
                    f"u need at least {ROB_MIN_BALANCE} coins before trying shady stuff like this~",
                    color=ERROR_COLOR,
                )
                return

            if target["balance"] < ROB_TARGET_MIN_BALANCE:
                await send_embed_message(
                    ctx,
                    "Target Too Broke",
                    f"{member.display_name} aint got enough coins to even be worth robbing~",
                    color=WARNING_COLOR,
                )
                return

            shield_count = get_inventory_quantity(connection, member.id, "shield")
            success_chance = clamp(
                ROBBERY_SUCCESS_BASE
                + (robber["rob_level"] * ROBBERY_SUCCESS_STEP)
                - (target["defense_level"] * ROBBERY_SUCCESS_STEP),
                0.15,
                0.75,
            )

            if shield_count > 0:
                add_inventory_item(connection, member.id, "shield", -1)
                update_user_columns(
                    connection,
                    ctx.author.id,
                    last_rob=now.isoformat(),
                    rob_failures=robber["rob_failures"] + 1,
                )
                update_user_columns(
                    connection,
                    member.id,
                    last_robbed_at=now.isoformat(),
                )
                create_database_backup(connection)
                connection.commit()
                await send_embed_message(
                    ctx,
                    "Blocked By Shield",
                    f"tch, {member.display_name} had a shield and ur rob just bounced off it~",
                    color=ERROR_COLOR,
                    fields=[
                        {"name": "Their Shield", "value": f"{shield_count - 1} left now"},
                        {"name": "Your Cooldown", "value": f"{int(ROB_COOLDOWN.total_seconds() // 60)} minutes"},
                    ],
                )
                return

            if random.random() < success_chance:
                steal_cap = 350 + (robber["rob_level"] * 100)
                raw_amount = random.randint(
                    max(25, target["balance"] // 10),
                    max(40, target["balance"] // 4),
                )
                stolen_amount = clamp(raw_amount, 25, min(target["balance"], steal_cap))
                robber_balance = robber["balance"] + stolen_amount
                target_balance = target["balance"] - stolen_amount

                update_user_columns(
                    connection,
                    ctx.author.id,
                    balance=robber_balance,
                    last_rob=now.isoformat(),
                    rob_successes=robber["rob_successes"] + 1,
                    total_rob_earnings=robber["total_rob_earnings"] + stolen_amount,
                )
                update_user_columns(
                    connection,
                    member.id,
                    balance=target_balance,
                    last_robbed_at=now.isoformat(),
                    total_rob_losses=target["total_rob_losses"] + stolen_amount,
                )
                create_database_backup(connection)
                connection.commit()

                logger.info("rob success robber=%s target=%s amount=%s", ctx.author.id, member.id, stolen_amount)
                await send_embed_message(
                    ctx,
                    "Rob Pulled Off",
                    f"ugh fine, u actually robbed {member.display_name} for {stolen_amount} coins somehow~",
                    color=SUCCESS_COLOR,
                    fields=[
                        {"name": "Your Balance", "value": f"{robber_balance}"},
                        {"name": "Their Balance", "value": f"{target_balance}"},
                        {"name": "Success Chance", "value": f"{int(success_chance * 100)} percent"},
                    ],
                )
                return

            fine = clamp(random.randint(25, 90), 10, robber["balance"])
            compensation = min(fine, max(10, fine // 2))
            robber_balance = robber["balance"] - fine
            target_balance = target["balance"] + compensation

            update_user_columns(
                connection,
                ctx.author.id,
                balance=robber_balance,
                last_rob=now.isoformat(),
                rob_failures=robber["rob_failures"] + 1,
                total_rob_losses=robber["total_rob_losses"] + fine,
            )
            update_user_columns(
                connection,
                member.id,
                balance=target_balance,
                last_robbed_at=now.isoformat(),
            )
            create_database_backup(connection)
            connection.commit()

    logger.info("rob fail robber=%s target=%s fine=%s", ctx.author.id, member.id, fine)
    await send_embed_message(
        ctx,
        "Rob Backfired",
        f"wow, u failed the rob and dropped {fine} coins while running away like a clown~",
        color=ERROR_COLOR,
        fields=[
            {"name": "Compensation To Them", "value": f"{compensation} coins"},
            {"name": "Your Balance", "value": f"{robber_balance}"},
            {"name": "Their Balance", "value": f"{target_balance}"},
        ],
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def sell(ctx):
    if ctx.guild is None:
        await send_embed_message(
            ctx,
            "Server Only",
            "do that in a server, not here, gosh~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            user_record = get_user_record(connection, ctx.author.id)

            if user_record["name_sold"]:
                await send_embed_message(
                    ctx,
                    "Already Sold",
                    f"ur name already got sold and its still on auction for {NAME_AUCTION_PRICE} coins~",
                    color=WARNING_COLOR,
                )
                return

            original_name = ctx.author.display_name

            try:
                await ctx.author.edit(
                    nick=SOLD_NAME,
                    reason="User sold their name with !sell",
                )
            except discord.Forbidden:
                await send_embed_message(
                    ctx,
                    "No Nickname Perms",
                    "i cant steal ur name cuz the perms are bein annoying again~",
                    color=ERROR_COLOR,
                )
                return
            except discord.HTTPException:
                await send_embed_message(
                    ctx,
                    "Sale Failed",
                    "the name sale glitched out, so try again later or whatever~",
                    color=ERROR_COLOR,
                )
                return

            new_balance = user_record["balance"] + SELL_REWARD
            update_user_columns(
                connection,
                ctx.author.id,
                balance=new_balance,
                name_sold=1,
                original_name=original_name,
            )
            create_database_backup(connection)
            connection.commit()

    logger.info("sell user=%s reward=%s", ctx.author.id, SELL_REWARD)
    await send_embed_message(
        ctx,
        "Name Sold",
        f"fine, ur name got sold for {SELL_REWARD} coins and now its stuck on auction like some dumb trophy~",
        color=SUCCESS_COLOR,
        fields=[
            {"name": "Auction Price", "value": f"{NAME_AUCTION_PRICE} coins"},
            {"name": "New Balance", "value": f"{new_balance} coins"},
        ],
    )


@bot.command()
@commands.cooldown(1, 3, commands.BucketType.user)
async def buy(ctx, member: discord.Member):
    if ctx.guild is None:
        await send_embed_message(
            ctx,
            "Server Only",
            "do that in a server, not here, baka~",
            color=WARNING_COLOR,
        )
        return

    if member.id == ctx.author.id:
        await send_embed_message(
            ctx,
            "No Self Buy",
            "you cant buy ur own name back with this command, thats dumb~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            buyer = get_user_record(connection, ctx.author.id)
            seller = get_user_record(connection, member.id)

            if not seller["name_sold"]:
                await send_embed_message(
                    ctx,
                    "Name Not For Sale",
                    "that persons name aint on auction right now, so stop reaching~",
                    color=WARNING_COLOR,
                )
                return

            if not seller["original_name"]:
                await send_embed_message(
                    ctx,
                    "Old Name Missing",
                    "i cant find the old name, so the sale cant finish now~",
                    color=ERROR_COLOR,
                )
                return

            if buyer["balance"] < NAME_AUCTION_PRICE:
                await send_embed_message(
                    ctx,
                    "Too Broke",
                    f"you need {NAME_AUCTION_PRICE} coins for that and ur wallet is cryin~",
                    color=ERROR_COLOR,
                )
                return

            restored_name = seller["original_name"]

            try:
                await member.edit(
                    nick=restored_name,
                    reason=f"Name restored after purchase by {ctx.author}",
                )
            except discord.Forbidden:
                await send_embed_message(
                    ctx,
                    "No Nickname Perms",
                    "i cant restore that nickname cuz the perms are being annoying again~",
                    color=ERROR_COLOR,
                )
                return
            except discord.HTTPException:
                await send_embed_message(
                    ctx,
                    "Auction Failed",
                    "the auction thing bugged out, so try again later maybe~",
                    color=ERROR_COLOR,
                )
                return

            buyer_balance = buyer["balance"] - NAME_AUCTION_PRICE
            seller_balance = seller["balance"] + NAME_AUCTION_PRICE
            update_user_columns(connection, ctx.author.id, balance=buyer_balance)
            update_user_columns(
                connection,
                member.id,
                balance=seller_balance,
                name_sold=0,
                original_name=None,
            )
            create_database_backup(connection)
            connection.commit()

    logger.info("buy-name buyer=%s seller=%s", ctx.author.id, member.id)
    await send_embed_message(
        ctx,
        "Auction Finished",
        f"fine, u bought {member.display_name}'s name and the old one is back now~",
        color=SUCCESS_COLOR,
        fields=[
            {"name": "Cost", "value": f"{NAME_AUCTION_PRICE} coins"},
            {"name": "Your Balance", "value": f"{buyer_balance} coins"},
            {"name": "Their Balance", "value": f"{seller_balance} coins"},
        ],
    )


@bot.command()
async def daddy(ctx):
    await send_embed_message(
        ctx,
        "Daddy",
        "its mrmariix ok, dont make it weird now~",
    )


@bot.command()
async def mommy(ctx):
    await send_embed_message(
        ctx,
        "Mommy",
        "its dawnera, obviously~",
    )


@bot.command()
async def ship(ctx, cheat_code: str = None):
    if ctx.guild is None:
        await send_embed_message(
            ctx,
            "No Server",
            "use this in a real server, not tucked away in dms like that~",
            color=WARNING_COLOR,
        )
        return

    candidates = [
        member for member in ctx.guild.members
        if not member.bot and member.id != bot.user.id
    ]

    if len(candidates) < 2:
        await send_embed_message(
            ctx,
            "No Pair To Tease",
            "i need at least two real people in here before i start stirrin trouble~",
            color=WARNING_COLOR,
        )
        return

    first, second = random.sample(candidates, 2)
    forced_ship = (cheat_code or "").strip().lower() == SHIP_SECRET_CODE
    chemistry = 100 if forced_ship else random.randint(35, 100)
    ship_text = " ".join(
        [
            random.choice(SHIP_OPENERS),
            random.choice(SHIP_SPICE),
            random.choice(SHIP_PAYOFFS),
            random.choice(SHIP_ENDINGS),
        ]
    )
    if forced_ship:
        ship_text += " fine, u found the dirty little cheat, so this one is burnin at full heat"
    fields = [
        {"name": "Pair", "value": f"{first.display_name} x {second.display_name}"},
        {"name": "Heat", "value": f"{chemistry} percent"},
    ]
    logger.info(
        "ship guild=%s first=%s second=%s chemistry=%s forced=%s",
        ctx.guild.id,
        first.id,
        second.id,
        chemistry,
        forced_ship,
    )
    await send_embed_message(
        ctx,
        "Ship Meter",
        ship_text,
        color=SUCCESS_COLOR if chemistry >= 70 else EMBED_COLOR,
        fields=fields,
    )


@bot.command()
@commands.guild_only()
@commands.check(can_manage_economy)
async def addcoins(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await send_embed_message(
            ctx,
            "Bad Amount",
            "add a real positive amount, dont test me with weird numbers~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            target = get_user_record(connection, member.id)
            new_balance = target["balance"] + amount
            update_user_columns(connection, member.id, balance=new_balance)
            create_database_backup(connection)
            connection.commit()

    logger.info("admin addcoins admin=%s target=%s amount=%s", ctx.author.id, member.id, amount)
    await send_embed_message(
        ctx,
        "Coins Added",
        f"fine, {amount} coins got added to {member.display_name} now~",
        color=SUCCESS_COLOR,
        fields=[{"name": "New Balance", "value": f"{new_balance} coins"}],
    )


@bot.command()
@commands.guild_only()
@commands.check(can_grant_mod_access)
async def addmod(ctx, member: discord.Member):
    if member.bot:
        await send_embed_message(
            ctx,
            "No Bot Mods",
            "im not addin bots as mods for this, thats just askin for a mess~",
            color=WARNING_COLOR,
        )
        return

    if member.id == ctx.guild.owner_id or is_admin(member):
        await send_embed_message(
            ctx,
            "Already Staff",
            f"{member.display_name} already got server level power, so they dont need bot mod access too~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            already_mod = connection.execute(
                "SELECT 1 FROM economy_mods WHERE user_id = ? LIMIT 1",
                (str(member.id),),
            ).fetchone()
            if already_mod:
                await send_embed_message(
                    ctx,
                    "Already Added",
                    f"{member.display_name} is already one of my bot mods~",
                    color=WARNING_COLOR,
                )
                return

            connection.execute(
                """
                INSERT INTO economy_mods (user_id, added_by, added_at)
                VALUES (?, ?, ?)
                """,
                (str(member.id), str(ctx.author.id), datetime.now(timezone.utc).isoformat()),
            )
            create_database_backup(connection)
            connection.commit()

    logger.info("addmod actor=%s target=%s", ctx.author.id, member.id)
    await send_embed_message(
        ctx,
        "Bot Mod Added",
        f"fine, {member.display_name} can use the bot economy staff commands now~",
        color=SUCCESS_COLOR,
    )


@bot.command()
@commands.guild_only()
@commands.check(can_grant_mod_access)
async def removemod(ctx, member: discord.Member):
    if member.id == ctx.guild.owner_id or is_admin(member):
        await send_embed_message(
            ctx,
            "Cant Strip Server Power",
            f"{member.display_name} still has real server perms, so this command cant take those away~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            removed = connection.execute(
                "DELETE FROM economy_mods WHERE user_id = ?",
                (str(member.id),),
            ).rowcount
            if removed == 0:
                await send_embed_message(
                    ctx,
                    "Not A Bot Mod",
                    f"{member.display_name} wasnt even in the bot mod list~",
                    color=WARNING_COLOR,
                )
                return

            create_database_backup(connection)
            connection.commit()

    logger.info("removemod actor=%s target=%s", ctx.author.id, member.id)
    await send_embed_message(
        ctx,
        "Bot Mod Removed",
        f"there, {member.display_name} lost bot mod access now~",
        color=SUCCESS_COLOR,
    )


@bot.command()
@commands.guild_only()
@commands.check(can_manage_economy)
async def takecoins(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await send_embed_message(
            ctx,
            "Bad Amount",
            "take a real positive amount maybe, wow~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            target = get_user_record(connection, member.id)
            new_balance = max(0, target["balance"] - amount)
            update_user_columns(connection, member.id, balance=new_balance)
            create_database_backup(connection)
            connection.commit()

    logger.info("admin takecoins admin=%s target=%s amount=%s", ctx.author.id, member.id, amount)
    await send_embed_message(
        ctx,
        "Coins Removed",
        f"there, i took coins from {member.display_name}, so dont ask twice~",
        color=WARNING_COLOR,
        fields=[{"name": "New Balance", "value": f"{new_balance} coins"}],
    )


@bot.command()
@commands.guild_only()
@commands.check(can_manage_economy)
async def setcoins(ctx, member: discord.Member, amount: int):
    if amount < 0:
        await send_embed_message(
            ctx,
            "Bad Amount",
            "negative coins would be cursed, so no~",
            color=WARNING_COLOR,
        )
        return

    async with db_lock:
        with get_connection() as connection:
            update_user_columns(connection, member.id, balance=amount)
            create_database_backup(connection)
            connection.commit()

    logger.info("admin setcoins admin=%s target=%s amount=%s", ctx.author.id, member.id, amount)
    await send_embed_message(
        ctx,
        "Coins Set",
        f"fine, {member.display_name}'s balance is {amount} now~",
        color=SUCCESS_COLOR,
    )


if __name__ == "__main__":
    if not token:
        raise ValueError("Missing bot_discord_token in the environment.")

    bot.run(token)
