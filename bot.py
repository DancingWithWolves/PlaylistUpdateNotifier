import asyncio
import os
import telebot
import logging
from collections import defaultdict
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv
from yandex_music import Client

logging.basicConfig(level=logging.INFO)
load_dotenv()  # take environment variables from .env.

token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = AsyncTeleBot(token)

users_playlists = defaultdict(set)
playlists_tracks = {}

client = Client().init()

print("ready!")
def extract_arg(arg):
    return arg.split()[1:]

def check_playlist_update(playlist):
    playlist_id = playlist.text.split('/')[-1]
    user = playlist.text.split('/')[-3]
    return

@bot.message_handler(commands=['add_playlist'])
async def add_playlist(message):
    playlist_id = message.text.split('/')[-1]
    user = message.text.split('/')[-3]
    playlist = str(extract_arg(message.text))
    logging.info(f"adding {message.chat.id}: {playlist}")
    
    users_playlists[message.chat.id].add(playlist)

    playlists_tracks[playlist] = client.users_playlists(playlist_id, user).track_count
    logging.info(f"added playlists_tracks: {playlist} : {playlists_tracks[playlist]}")

    await bot.reply_to(message, "success!")

@bot.message_handler(commands=['show'])
async def show_playlists(message):
    logging.info(f"showing {message.chat.id}")
    await bot.reply_to(message, str(users_playlists[message.chat.id]))

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


