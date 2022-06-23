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
from yandex_music.exceptions import YandexMusicError
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
async def get_last_added_track_url(playlist : Playlist):
    track = playlist.tracks[-1].track
    
    album_id = track.track_id.split(':')[1]
    track_id = track.track_id.split(':')[0]
    
    last_added_track_url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    
    return last_added_track_url


# Возвращает разность количества треков на сервере и последнего запомненного состояния, обновляет последнее запомненное состояние
async def check_playlist_update(playlist_name : str, playlist : Playlist):
    last_added_track = await get_last_added_track_url(playlist)
    try:
        query = "SELECT LastAddedTrack FROM Playlist WHERE Title = ?"
        cursor = await bot.db.execute(query, (playlist_name,))
        db_last_added_tracks = await cursor.fetchall()
        await cursor.close()
    except DatabaseError as error:
        logging.error(error)

    if len(db_last_added_tracks) != 1:
        logging.error(f"There is no playlist {playlist_name} in db!")
        return False

    db_last_added_track = db_last_added_tracks[0]
    if db_last_added_track != last_added_track:
        try:
            query = "UPDATE Playlist SET LastAddedTrack = ? WHERE Title = ?"
            await bot.db.execute(query, (last_added_track, playlist_name))
            await bot.db.commit()
            logging.info(f"Found an update in playlist {playlist_name}; \n LastAddedTrack was {db_last_added_track}, now {last_added_track}")
        except DatabaseError as error:
            logging.error(error)
        return True
    return False




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
        try:
            playlist = await client.users_playlists(playlist_id, user)
            playlists_tracks[playlist_name] = playlist.track_count
        except YandexMusicError as error:
            reply = "Или такого плейлиста не существует, или мы неправильно смотрим 👀"
            logging.error(error)
            logging.info(f"DB: Seems there is a no Playlist with Title = \"{playlist_name}\"")
            await bot.reply_to(message, reply)

            return

        # Добавление в БД
        # 1) плейлист:
        try:
            last_added_track = await get_last_added_track_url(playlist)
            query = "INSERT INTO Playlist (Title, LastAddedTrack, Snapshot) VALUES (?, ?, ?)"
            cursor = await bot.db.execute(query, (playlist_name, last_added_track, playlist.snapshot))
            logging.info(f"DB: Added Playlist with Title = \"{playlist_name}\", LastAddedTrack = {last_added_track}, Snapshot = {playlist.snapshot}")       
            await bot.db.commit()
            await cursor.close()
        except DatabaseError as error:
            logging.error(error)
            logging.info(f"DB: Seems there is a Playlist with Title = \"{playlist_name}\" already existing in db")
        
            
        # 2) подписка пользователя на этот плейлист:
        try:
            query = "INSERT INTO Subscription (User_id, Playlist_id) VALUES (?, ?)"
            cursor = await bot.db.execute(query, (message.chat.id, playlist_name))
            logging.info(f"DB: Added Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\"")
            await bot.db.commit()
            await cursor.close()
        except DatabaseError as error:
            logging.error(error)
            logging.info(f"DB: Seems there is a Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\" already existing in db")

        reply = "Плейлист успешно добавлен в отслеживаемые! ✅"

    await bot.reply_to(message, reply)
    return


# Обработка '/show', в ответном сообщении вывод списка отслеживаемых плейлистов
@bot.message_handler(commands=['show'])
async def show_playlists(message):
    logging.info(f"showing {message.chat.id}")
    
    query = "SELECT * FROM Subscription WHERE User_id = ?"
    cursor = await bot.db.execute(query, (message.chat.id,))
    rows = await cursor.fetchall()
    await cursor.close()
    # logging.info(type(rows))

    if len(rows) == 0:
        await bot.reply_to(message, "Вы не отслеживаете ни один плейлист ❌")
    else:
        playlists_list = []
        for (playlist, user) in rows:
            playlists_list.append(playlist)
        await bot.reply_to(message, "📌" + "📌\n".join(playlists_list))

            

# Обработка '/start' и '/help'
@bot.message_handler(commands=['help', 'start'])
async def send_welcome(message):
    try:
        query = "INSERT INTO User (ID) VALUES (?)"
        cursor = await bot.db.execute(query, (message.chat.id,))
        await bot.db.commit()
        await cursor.close()
        logging.info(f"Added user with ID {message.chat.id}")
    except DatabaseError:
        logging.info(f"Seems there is a user with ID {message.chat.id} already existing in db")

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
        # Начитаем все плейлисты, на которые кто-то подписан
        query = "SELECT * FROM Playlist"
        cursor = await bot.db.execute(query)
        rows = await cursor.fetchall()
        await cursor.close()
        # Для каждого плейлиста:
        for (playlist_name, last_added_track_db, snapshot) in rows:
            # Начитаем идентификатор для апишки
            playlist_id = playlist_name.split('/')[-1] 
            user = playlist_name.split('/')[-3]
            # Дёрнем апишку
            try:
                playlist = await client.users_playlists(playlist_id, user)
            except YandexMusicError as error:
                logging.error(error)
                logging.info(f"DB: Seems there is a no Playlist with Title = \"{playlist_name}\"")
                continue # Если _на этом_ этапе что-то не так, просто скипаем этот плейлист UwU
            
            last_added_track = await get_last_added_track_url(playlist)

            if last_added_track_db != last_added_track:
                message = f"🎼 Новый трек в плейлисте \"{playlist_name}\", вот ссылка:\n{last_added_track}"
                logging.info(message)
                # Начитаем подписчиков плейлиста
                try:
                    query = "SELECT User_id FROM Subscription where Playlist_id = ?"
                    cursor = await bot.db.execute(query, (playlist_name,))
                    rows = await cursor.fetchall()
                    await cursor.close()
                except DatabaseError as error:
                    logging.error(error)
                    logging.error(f"Could not read Users subscriped to {playlist_name} from db")
                    continue

                # Оповестим подписанных пользователей
                for (user, playlist) in rows:
                    logging.info(f"Sending a message: <{message}> to user {user}")
                    try:
                        await bot.send_message(user, message)
                    except Exception as error:
                        logging.error(error)
                        logging.error(f"Could not send message to user {user}")
                        continue

                # Обновим БД:
                try:
                    query = "UPDATE Playlist SET LastAddedTrack = ? WHERE Title = ?"
                    await bot.db.execute(query, (last_added_track, playlist_name))
                    await bot.db.commit()
                    logging.info(f"Found an update in playlist {playlist_name}; \n LastAddedTrack was {last_added_track_db}, now {last_added_track}")
                except DatabaseError as error:
                    logging.error(error)
                    logging.error(f"Could not update playlist {playlist_name} in db")


        await asyncio.sleep(5)


async def main():
    await client.init()
    async with aiosqlite.connect('PlaylistUpdateNotifier.db') as bot.db:
        await asyncio.gather(bot.infinity_polling(), polling())


# Запуск основого (за)лупа
asyncio.run(main())
