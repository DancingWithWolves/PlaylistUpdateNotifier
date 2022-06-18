import asyncio
import os
import telebot
from collections import defaultdict
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.
token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = AsyncTeleBot(token)

def extract_arg(arg):
    return arg.split()[1:]
    
users_playlists = defaultdict(list)

# Handle '/start' and '/help'
@bot.message_handler(commands=['add_playlist'])
async def add_playlist(message):
    users_playlists[message.chat.id].append(extract_arg(message.text))
    await bot.reply_to(message, "success!")

# Handle '/start' and '/help'
@bot.message_handler(commands=['help', 'start'])
async def send_welcome(message):
    await bot.reply_to(message, """\
Hi there, I am EchoBot.
I am here to echo your kind words back to you. Just say anything nice and I'll say the exact same thing to you!\
""")


@bot.message_handler()
async def echo_message(message):
    await bot.reply_to(message, message.text)

asyncio.run(bot.polling())


