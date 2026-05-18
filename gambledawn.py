import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import json
import random


load_dotenv()

token = os.getenv("bot_discord_token")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def load_balances():
    if not os.path.exists('balances.json'):
        return {}
    with open('balances.json', 'r') as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)



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
    await ctx.send(f"{member.display_name} has {current_bal} coins!")


@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    balances = load_balances()

    if user_id not in balances:
        balances[user_id] = 100
        save_balances(balances)

    balances[user_id] += 10
    save_balances(balances)
    await ctx.send(f"Your daily reward of 10 coins has been claimed! Your new balance is {balances[user_id]} coins.")

@bot.command()
async def bet(ctx, bet_amount: int):
    balances = load_balances()
    user_id = str(ctx.author.id)
    boosts = load_boosts()
    if user_id not in balances:
        balances[user_id] = 100

    if balances[user_id] < bet_amount:
        await ctx.send(f"You don't have enough coins! Balance: {balances[user_id]}")
        return

    win_chance = 0.2 if user_id in boosts else 0.1

    if random.random() <= win_chance:
        balances[user_id] += bet_amount
        await ctx.send(f"You won {bet_amount} coins! Your balance is now {balances[user_id]}.")
    else:
        balances[user_id] -= bet_amount
        await ctx.send(f"You lost {bet_amount} :/. Your new balance is {balances[user_id]}.")

def load_boosts():
    if not os.path.exists('boosts.json'):
        return {}
    with open('boosts.json', 'r') as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def save_boosts(boosts):
    with open('boosts.json', 'w') as f:
        json.dump(boosts, f, indent=4)

 
@bot.command()
async def daddy(ctx):
    await ctx.send("mrmariix")

@bot.command()
async def mommy(ctx):
    await ctx.send("dawnera")

@bot.command()
async def boost(ctx):
    balances = load_balances()
    boosts = load_boosts()
    user_id = str(ctx.author.id)
    if user_id not in balances:
        balances[user_id] = 100

    if user_id in boosts:
        await ctx.send("You have already purchased a booster!")
        return 
    if balances[user_id] < 5:
        await ctx.send("You need at least 5 coins to boost!")
        return
    balances[user_id] -= 5
    boosts[user_id] = True
    save_balances(balances)
    save_boosts(boosts)
    await ctx.send("Booster activated. You will now have a 20% win probability during bets.")





bot.run(token)