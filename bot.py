import asyncio
from hashlib import new
import os
import logging
from collections import defaultdict
from sqlite3 import DatabaseError
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv
from yandex_music import ClientAsync
from yandex_music import Playlist
import aiosqlite

logging.basicConfig(level=logging.INFO)
load_dotenv()

token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = AsyncTeleBot(token)

users_playlists = defaultdict(set)
playlists_users = defaultdict(set)
playlists_tracks = {}

client = ClientAsync()

# Возвращает аргумент из сообщения от телеграм-бота (/add_playlist <url> -- вернёт url)
def extract_arg(arg):
    return arg.split()[1:]


# Возвращает строку, в которой хранится собранный на коленке URL последнего добавленного трека
def get_last_added_track_url(playlist : Playlist):
    track = playlist.tracks[-1].track
    
    album_id = track.track_id.split(':')[1]
    track_id = track.track_id.split(':')[0]
    
    last_added_track_url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    
    return last_added_track_url


# Возвращает разность количества треков на сервере и последнего запомненного состояния, обновляет последнее запомненное состояние
def check_playlist_update(playlist_name : str, playlist : Playlist):

    old_track_count = playlists_tracks[playlist_name]

    logging.debug(f"for playlist {playlist_name} new track_count = {playlist.track_count}, stored = {old_track_count}")
    playlists_tracks[playlist_name] = playlist.track_count
    return playlist.track_count - old_track_count


# Обработка '/add_playlist', проверка на наличие ввода, добавление плейлиста в отслеживаемые.
@bot.message_handler(commands=['add_playlist'])
async def add_playlist(message):
    playlist_name = "/".join(extract_arg(message.text))
    reply = "Дайте минутку, сейчас сделаем 👻"
    
    await bot.reply_to(message, reply)

    if playlist_name is None:
        reply = "Укажите валидный URL через один пробел после команды \"/add_playlist\"!"
    else:
        # Начитка нужных для апи ямузыки полей
        playlist_id = message.text.split('/')[-1]
        user = message.text.split('/')[-3]

        logging.info(f"adding {message.chat.id}: {playlist_name}")
        # Ямузыка апи
        playlist = await client.users_playlists(playlist_id, user)
        playlists_tracks[playlist_name] = playlist.track_count
        # Локальное добавление
        users_playlists[message.chat.id].add(playlist_name)
        playlists_users[playlist_name].add(message.chat.id)
        
        logging.info(f"locally added playlists_tracks: {playlist_name}. Stored tracks count is {playlists_tracks[playlist_name]}")
        # Добавление в БД
        # 1) плейлист:
        try:
            query = "INSERT INTO Playlist (Title, TrackCount) VALUES (?, ?)"
            cursor = await bot.db.execute(query, (playlist_name, playlist.track_count))
            logging.info(f"DB: Added Playlist with Title = \"{playlist_name}\", TrackCount = {playlist.track_count}")
        except DatabaseError as error:
            logging.error(error)
            logging.info(f"DB: Seems there is a Playlist with Title = \"{playlist_name}\" already existing in db")
        await bot.db.commit()
        # 2) подписка пользователя на этот плейлист:
        try:
            query = "INSERT INTO Subscription (User_id, Playlist_id) VALUES (?, ?)"
            cursor = await bot.db.execute(query, (message.chat.id, playlist_name))
            logging.info(f"DB: added Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\"")
        except DatabaseError as error:
            logging.error(error)
            logging.info(f"DB: Seems there is a Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\" already existing in db")
        await bot.db.commit()

        reply = "Плейлист успешно добавлен в отслеживаемые! ✅"

    await bot.reply_to(message, reply)


# Обработка '/show', в ответном сообщении вывод списка отслеживаемых плейлистов
@bot.message_handler(commands=['show'])
async def show_playlists(message):
    logging.info(f"showing {message.chat.id}")
    reply = ""
    # TODO: SQL injection 
    cursor = await bot.db.execute(f"SELECT * FROM Subscription WHERE User_id = {message.chat.id}")
    rows = await cursor.fetchall()
    await cursor.close()
    print(type(rows))
    if len(rows) == 0:
        await bot.reply_to(message, "Вы не отслеживаете ни один плейлист ❌")
    else:
        await bot.reply_to(message, '📌' + '📌\n'.join(rows))

    # if message.chat.id in users_playlists.keys():
    #     await bot.reply_to(message, '📌' + '📌\n'.join(users_playlists[message.chat.id]))
    # else:
    #     await bot.reply_to(message, "Вы не отслеживаете ни один плейлист ❌")
            

# Обработка '/start' и '/help'
@bot.message_handler(commands=['help', 'start'])
async def send_welcome(message):
    try:
        # TODO: SQL injection 
        await bot.db.execute(f"INSERT INTO User VALUES ({message.chat.id})")
        logging.info(f"Added user with ID {message.chat.id}")
    except DatabaseError:
        logging.info(f"Seems there is a user with ID {message.chat.id} already existing in db")
    await bot.db.commit()

    await bot.reply_to(message, """\
Используй команду \"/add_playlist <URL плейлиста>\", чтобы отслеживать изменения в плейлисте. \
Когда в него добавится какой-то трек, в этот чат придёт \
ссылка на него!
Команда \"/show\" покажет текущие отслеживаемые плейлисты.
Остальные команды проигнорируются.
Подписывайтесь на боярхив vk.com/boyarchive""")

# Каждые 5 секунд проверяет все плейлисты, которые кем-то отслеживаются, 
# и рассылает сообщения об обновлениях, если такие имеются
async def polling():
    while True:
        for playlist_name in playlists_tracks:
            playlist_id = playlist_name.split('/')[-1]
            user = playlist_name.split('/')[-3]

            playlist = await client.users_playlists(playlist_id, user)
            
            if check_playlist_update(playlist_name, playlist) != 0:

                last_added_track_url = get_last_added_track_url(playlist)
                message = f"🎼 Новый трек в плейлисте \"{playlist.title}\", вот ссылка:\n{last_added_track_url}"

                logging.info(message)

                for user in playlists_users[playlist_name]:        
                    logging.info(f"Sending a message: <{message}> to user {user}")
                    await bot.send_message(user, message)

        await asyncio.sleep(5)


async def main():
    await client.init()
    async with aiosqlite.connect('PlaylistUpdateNotifier.db') as bot.db:
        await asyncio.gather(bot.infinity_polling(), polling())


# Запуск основого (за)лупа
asyncio.run(main())
