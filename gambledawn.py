import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import json

load_dotenv()
token = os.getenv('discord_token')

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_balances():
    if not os.path.exists('balances.json'):
        return {}
    with open('balances.json', 'r') as f:
        return json.load(f) 


def save_balances(dict_balances):
    with open('balances.json', 'w') as f:
        json.dump(dict_balances, f, indent=4)


@bot.command()
async def bal(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author
    
    balances = load_balances()
    user_id = str(member.id)

    if user_id not in balances:
        balances[user_id] = 100
        save_balances(balances)

    current_bal = balances[user_id]
    await ctx.send(f"{member.display_name} has ${current_bal}!")


@bot.command()
async def daily(ctx, member: discord.Member = None):
    if member is None:
        member = ctx.author

    balances = load_balances()
    user_id = str(member.id)

    if user_id not in balances:
        balances[user_id] = 100
        save_balances(balances)

    balances[user_id] += 10
    save_balances(balances)
    await ctx.send(f"Your daily reward of 10 coins has been claimed! Your new balance is {balances[user_id]} coins.")


@bot.command
async def bet10(ctx, bet_amount: int, member: discord.Member = None):
    




bot.run(token)