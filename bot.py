import asyncio
from hashlib import new
import os
import telebot
import logging
from collections import defaultdict
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv
from yandex_music import ClientAsync
from yandex_music import Playlist

logging.basicConfig(level=logging.INFO)
load_dotenv()  # take environment variables from .env.

token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = AsyncTeleBot(token)

users_playlists = defaultdict(set)
playlists_users = defaultdict(set)
playlists_tracks = {}

client = ClientAsync()

def extract_arg(arg):
    return arg.split()[1:]


def get_last_added_track_url(playlist):
    track = playlist.tracks[-1].track
    
    album_id = track.track_id.split(':')[1]
    track_id = track.track_id.split(':')[0]
    
    last_added_track_url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    
    return last_added_track_url

# Возвращает разность количества треков на сервере и последнего запомненного состояния, обновляет последнее запомненное состояние
def check_playlist_update(playlist_name, playlist):

    old_track_count = playlists_tracks[playlist_name]

    logging.debug(f"for playlist {playlist_name} new track_count = {playlist.track_count}, stored = {old_track_count}")
    playlists_tracks[playlist_name] = playlist.track_count
    return playlist.track_count - old_track_count

@bot.message_handler(commands=['add_playlist'])
async def add_playlist(message):
    playlist_name = "/".join(extract_arg(message.text))

    playlist_id = message.text.split('/')[-1]
    user = message.text.split('/')[-3]

    logging.info(f"adding {message.chat.id}: {playlist_name}")
    
    users_playlists[message.chat.id].add(playlist_name)
    playlists_users[playlist_name].add(message.chat.id)

    playlist = await client.users_playlists(playlist_id, user)
    playlists_tracks[playlist_name] = playlist.track_count

    logging.info(f"added playlists_tracks: {playlist_name}. Stored tracks count is {playlists_tracks[playlist_name]}")

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



async def polling():
    while True:
        for playlist_name in playlists_tracks:
            playlist_id = playlist_name.split('/')[-1]
            user = playlist_name.split('/')[-3]

            playlist = await client.users_playlists(playlist_id, user)
            
            if check_playlist_update(playlist_name, playlist) != 0:

                last_added_track_url = get_last_added_track_url(playlist)
                message = f"Новый трек в плейлисте \"{playlist.title}\", вот ссылка на добавленую песню: {last_added_track_url}!"

                logging.info(message)

                for user in playlists_users[playlist_name]:        
                    logging.info(f"trying to send message: <{message}> to user {user}")
                    await bot.send_message(user, message)

        await asyncio.sleep(5)


async def main():
    await client.init() 
    await asyncio.gather(bot.infinity_polling(), polling())


asyncio.run(main())


