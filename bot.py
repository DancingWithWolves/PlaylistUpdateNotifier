import asyncio
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

client = ClientAsync()

# Возвращает аргумент из сообщения от телеграм-бота (/add_playlist <url> -- вернёт url)
def extract_arg(arg):
    if len(arg.split()) > 1:
        return arg.split()[1:]
    else:
        raise Exception

# Возвращает строку, в которой хранится собранный на коленке URL последнего добавленного трека
def get_last_added_track_url(playlist : Playlist):
    track = playlist.tracks[-1].track
    
    album_id = track.track_id.split(':')[1]
    track_id = track.track_id.split(':')[0]
    
    last_added_track_url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    
    return last_added_track_url

async def reply_to_message(message, reply):
    try:
        await bot.reply_to(message, reply)
    except Exception as error:
        logging.error(error)
        logging.error(f"WEB: could not send message to user {message.chat.id}")


# Обработка '/delete_playlist', проверка на наличие ввода, удаление подписки.
@bot.message_handler(commands=['delete_playlist'])
async def delete_playlist(message):
    # Мгновенный ответ
    await reply_to_message(message, "Дайте минутку, сейчас сделаем 👻")
    
    # Проверка корректности ввода
    try:
        playlist_name = "/".join(extract_arg(message.text))
    except Exception as error:
        logging.info("User {message.chat.id} entered non-valid URL: {message.text}")
        await reply_to_message(message, "Укажите какой-нибудь URL, вы чо 🐷\nПосмотреть плейлисты можно командой \"/show\"")
        return
    try:
        query = "DELETE FROM Subscription WHERE User_id = ? AND Playlist_id = ?"
        await bot.db.execute(query, (message.chat.id, playlist_name))
        await bot.db.commit()
        logging.info(f"DB: Deleted Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\"")
        
    except DatabaseError as error:
        logging.error(error)
        logging.info(f"DB: Seems there were no Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\" already existing in db")
    
    await reply_to_message(message, "Подписка на плейлист успешно удалена! ✅")
    return

# Обработка '/add_playlist', проверка на наличие ввода, добавление плейлиста в отслеживаемые.
@bot.message_handler(commands=['add_playlist'])
async def add_playlist(message):
    # Мгновенный ответ
    await reply_to_message(message, "Дайте минутку, сейчас сделаем 👻")
    
    # Проверка корректности ввода
    try:
        playlist_name = "/".join(extract_arg(message.text))
        # Начитка нужных для апи ямузыки полей, если не получается, то шляпа какая-то
        playlist_id = message.text.split('/')[-1]
        user = message.text.split('/')[-3]
    except Exception as error:
        logging.info("User {message.chat.id} entered non-valid URL: {message.text}")
        await reply_to_message(message, "Укажите валидный URL через один пробел после команды \"/add_playlist\" 🐳")
        return
    
    # Ямузыка апи
    try:
        playlist = await client.users_playlists(playlist_id, user)
    except YandexMusicError as error:
        logging.error(error)
        logging.info(f"WEB: Seems there is no Playlist with Title = \"{playlist_name}\"")
        await reply_to_message(message, "Или такого плейлиста не существует, или мы неправильно смотрим 👀")
        return

    # Добавление в БД
    # 1) плейлист:
    try:
        last_added_track = get_last_added_track_url(playlist)
        query = "INSERT INTO Playlist (Title, LastAddedTrack, Snapshot) VALUES (?, ?, ?)"
        await bot.db.execute(query, (playlist_name, last_added_track, playlist.snapshot))
        await bot.db.commit()
        logging.info(f"DB: Added Playlist with Title = \"{playlist_name}\", LastAddedTrack = {last_added_track}, Snapshot = {playlist.snapshot}")
    except DatabaseError as error:
        logging.error(error)
        logging.info(f"DB: Seems there is a Playlist with Title = \"{playlist_name}\" already existing in db")
        
    # 2) подписка пользователя на этот плейлист:
    try:
        query = "INSERT INTO Subscription (User_id, Playlist_id) VALUES (?, ?)"
        cursor = await bot.db.execute(query, (message.chat.id, playlist_name))
        await bot.db.commit()
        await cursor.close()
        logging.info(f"DB: Added Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\"")
    except DatabaseError as error:
        logging.error(error)
        logging.info(f"DB: Seems there is a Subscription with User_id = {message.chat.id}, Playlist_id = \"{playlist_name}\" already existing in db")
    
    await reply_to_message(message, "Плейлист успешно добавлен в отслеживаемые! ✅")
    return

# Обработка '/show', в ответном сообщении вывод списка отслеживаемых плейлистов
@bot.message_handler(commands=['show'])
async def show_playlists(message):
    logging.info(f"Showing subscriptions to user {message.chat.id}")
    try:
        query = "SELECT * FROM Subscription WHERE User_id = ?"
        cursor = await bot.db.execute(query, (message.chat.id,))
        rows = await cursor.fetchall()
        await cursor.close()
    except DatabaseError as error:
        logging.error(error)
        logging.error(f"DB: Could not read Subscription for user {message.chat.id}")
        

    if len(rows) == 0:
        await reply_to_message(message, "Вы не отслеживаете ни один плейлист ❌")            
    else:
        playlists_list = []
        for (playlist, user) in rows:
            playlists_list.append(playlist)
        await reply_to_message(message, "📌" + "📌\n".join(playlists_list))

# Обработка '/start' и '/help'
@bot.message_handler(commands=['help', 'start'])
async def send_welcome(message):
    try:
        query = "INSERT INTO User (ID) VALUES (?)"
        await bot.db.execute(query, (message.chat.id,))
        await bot.db.commit()
        logging.info(f"DB: Added user with ID {message.chat.id}")
    except DatabaseError:
        logging.info(f"DB: Seems there is a user with ID {message.chat.id} already existing in db")
    
    await reply_to_message(message, """\
📌Используй команду \"/add_playlist <URL плейлиста>\", чтобы отслеживать изменения в плейлисте. \
Когда в него добавится какой-то трек, в этот чат придёт \
ссылка на него!
📌Добавленные плейлисты можно удалить командой \"delete_playlist\"
📌Команда \"/show\" покажет текущие отслеживаемые плейлисты.
Остальные команды проигнорируются.
Подписывайтесь на боярхив vk.com/boyarchive""")

# Каждые 5 секунд проверяет все плейлисты, которые кем-то отслеживаются, 
# и рассылает сообщения об обновлениях, если такие имеются
async def polling():
    while True:
        # Начитаем все плейлисты, на которые кто-то подписан
        try:
            query = "SELECT * FROM Playlist"
            cursor = await bot.db.execute(query)
            rows = await cursor.fetchall()
            await cursor.close()
        except DatabaseError as error:
            logging.error(error)
            logging.error("DB: Could not read Playlists")
            continue
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
                logging.info(f"WEB: Seems there is a no Playlist with Title = \"{playlist_name}\"")
                continue # Если _на этом_ этапе что-то не так, просто скипаем этот плейлист UwU
            
            last_added_track = get_last_added_track_url(playlist)

            if last_added_track_db != last_added_track:
                message = f"🎼 Новый трек в плейлисте \"{playlist.title}\", вот ссылка:\n{last_added_track}"
                logging.info(message)
                # Начитаем подписчиков плейлиста
                try:
                    query = "SELECT User_id FROM Subscription where Playlist_id = ?"
                    cursor = await bot.db.execute(query, (playlist_name,))
                    rows = await cursor.fetchall()
                    await cursor.close()
                except DatabaseError as error:
                    logging.error(error)
                    logging.error(f"DB: Could not read Users subscriped to {playlist_name} from db")
                    continue
                # Оповестим подписанных пользователей
                for (user,) in rows:
                    logging.info(f"WEB: Sending a message: <{message}> to user {user}")
                    try:
                        await bot.send_message(user, message)
                    except Exception as error:
                        logging.error(error)
                        logging.error(f"WEB: Could not send message to user {user}")
                        continue

                # Обновим БД:
                try:
                    query = "UPDATE Playlist SET LastAddedTrack = ? WHERE Title = ?"
                    await bot.db.execute(query, (last_added_track, playlist_name))
                    await bot.db.commit()
                    logging.info(f"DB: Updated playlist {playlist_name}: LastAddedTrack was {last_added_track_db}, now {last_added_track}")
                except DatabaseError as error:
                    logging.error(error)
                    logging.error(f"DB: Could not update playlist {playlist_name} in db")

        await asyncio.sleep(5)


async def main():
    await client.init()
    async with aiosqlite.connect('PlaylistUpdateNotifier.db') as bot.db:
        await asyncio.gather(bot.infinity_polling(), polling())

# Запуск основого лупа
asyncio.run(main())
