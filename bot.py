import asyncio
import os
import logging
from posixpath import split
from sqlite3 import DatabaseError
from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv
from yandex_music import ClientAsync
from yandex_music import Playlist
from yandex_music.exceptions import YandexMusicError
import aiosqlite

logging.basicConfig(filename="Log.log", 
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    level=logging.INFO)
                    
logging.info(f"Started an app with PID = {os.getpid()}")
load_dotenv()

token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = AsyncTeleBot(token)

ym_token = os.getenv('YANDEX_MUSIC_TOKEN')
client = ClientAsync(ym_token)

# Возвращает аргумент из сообщения от телеграм-бота (/add_playlist <url> -- вернёт url)
def extract_arg(arg):
    if len(arg.split()) > 1:
        return arg.split()[1:]
    else:
        raise Exception

#Крч я наделала кучу ненужных методов, но мне не стыдно

#Возвращает айди плейлиста из сущности
def get_id_from_playlist(playlist : Playlist):
    return playlist.playlistId.split(':')[1]

#Возвращает имя пользователя из сущности
def get_login_from_playlist(playlist : Playlist):
    return playlist.owner.login

#Ссылка на плейлист из сущности
def get_url_from_playlist(playlist : Playlist):
    return f"https://music.yandex.ru/users/{get_login_from_playlist(playlist)}/playlists/{get_id_from_playlist(playlist)}"

#Тырим id плейлиста из ссылки
def get_playlist_id_from_url(str):
    if (str.find('?') != -1):
        return str[str.find('/playlists/')+len('/playlists/'):str.rfind('?')]
    else:
        return str.split('/')[-1]

#Тырим логин пользователя из ссылки
def get_login_from_url(str):
    return str[str.find('/users/')+len('/users/'):str.rfind('/playlists/')] #str.split('/')[-3]

#Получаем сущность плейлиста из ссылки
async def get_playlist_from_url(str):
    x : Playlist = await client.users_playlists(get_playlist_id_from_url(str), get_login_from_url(str))
    return x

#Данные плейлиста для сохранения в базу данных ИмяПользователя:АйдиПлейлиста
def playlist_to_db(playlist : Playlist):
    return f"{get_login_from_playlist(playlist)}:{get_id_from_playlist(playlist)}"

#Имя пользователя и айди плейлиста из базы данных
async def playlist_from_db(str):
    login = str.split(':')[0]
    playlist_id = str.split(':')[1]
    return await client.users_playlists(playlist_id,login)

# Возвращает строку, в которой хранится собранный на коленке URL последнего добавленного трека
async def last_added_track_url_title(playlist : Playlist):
    if playlist.track_count == 0 or playlist is None:
        return "https://music.yandex.ru/album/9046986/track/609676", "You got rickrolled OwO"

    short_track = playlist.tracks[-1]  
    try:
        track = await short_track.fetch_track_async()
    except Exception as error:
        logging.error(error)
        logging.error(f"WEB: could not fetch track {short_track.id} from Playlist {playlist.title}")

    album_id = track.track_id.split(':')[1] 
    track_id = track.track_id.split(':')[0]
    title = track.title

    last_added_track_url = f"https://music.yandex.ru/album/{album_id}/track/{track_id}"
    
    return last_added_track_url, title

#reply_to но с логированием
async def reply_to_message(message, reply):
    try:
        await bot.reply_to(message, reply)
    except Exception as error:
        logging.error(error)
        logging.error(f"WEB: could not send message to user {message.chat.id}")

# #swap_playlists из ссылок в ИмяПользователя:АйдиПлейлиста
# @bot.message_handler(commands=['swap_playlists'])
# async def swap_playlists(message):
#     await reply_to_message(message, "Я работаю!")
#     try:
#         query = "SELECT * FROM Playlist"
#         cursor = await bot.db.execute(query)
#         rows = await cursor.fetchall()
#         await cursor.close()
#     except DatabaseError as error:
#         logging.error(error)
#         logging.error("DB: Could not read Playlists")
#     # Для каждого плейлиста:
#     for (playlist_name, last_added_track_db, snapshot) in rows:
#         # Начитаем идентификатор для апишки
#         if (playlist_name.find('music.yandex') != -1):
#             playlist_id = playlist_name.split('/')[-1] 
#             user_log = playlist_name.split('/')[-3]
#             playlist_db_id = f"{user_log}:{playlist_id}"
#             try:
#                 query = "INSERT INTO Playlist (Title, LastAddedTrack, Snapshot) VALUES (?, ?, ?)"
#                 await bot.db.execute(query, (playlist_db_id, last_added_track_db, snapshot))
#                 await bot.db.commit()
#                 logging.info(f"DB: Added playlist {playlist_name}: New id is {playlist_db_id}")
#             except DatabaseError as error:
#                 logging.error(error)
#                 logging.error(f"DB: Could not update playlist {playlist_name} in db")
#             try:
#                 query = "UPDATE Subscription SET playlist_id = ? WHERE playlist_id = ?"
#                 await bot.db.execute(query, (playlist_db_id, playlist_name))
#                 await bot.db.commit()
#                 logging.info(f"DB: Changed subscription for {playlist_name}: New id is {playlist_db_id}")
#             except DatabaseError as error:
#                 logging.error(error)
#                 logging.error(f"DB: Could not update subscription for {playlist_name} in db")
#             try:
#                 query = "DELETE FROM Playlist WHERE Title = ?"
#                 await bot.db.execute(query, (playlist_name,))
#                 await bot.db.commit()
#                 logging.info(f"DB: Deleted playlist {playlist_name}: New id is {playlist_db_id}")
#             except DatabaseError as error:
#                 logging.error(error)
#                 logging.error(f"DB: Could not update playlist {playlist_name} in db")
            

# Обработка '/delete_playlist', проверка на наличие ввода, удаление подписки.
@bot.message_handler(commands=['delete_playlist'])
async def delete_playlist(message):
    # Мгновенный ответ
    await reply_to_message(message, "Дайте минутку, сейчас сделаем 👻")
    
    # Проверка корректности ввода
    try:
        playlist_link = "/".join(extract_arg(message.text))
        playlist : Playlist = await get_playlist_from_url(playlist_link)
        playlist_name = playlist_to_db(playlist)
    except Exception as error:
        logging.error(error)
        logging.info(f"User {message.chat.id} entered non-valid URL: {message.text}")
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
        # playlist_id = message.text.split('/')[-1]
        # user = message.text.split('/')[-3]
    except Exception as error:
        logging.info(f"Пользователь {message.chat.id} ввёл невалидный URL: {message.text}")
        await reply_to_message(message, "Укажите валидный URL через один пробел после команды \"/add_playlist\" 🐳")
        return
    
    # Ямузыка апи
    try:
        playlist : Playlist = await get_playlist_from_url(playlist_name)
        p_id = playlist_to_db(playlist)
    except YandexMusicError as error:
        logging.error(error)
        logging.info(f"WEB: Seems there is no Playlist with Title = \"{p_id}\"")
        await reply_to_message(message, "Или такого плейлиста не существует, или мы неправильно смотрим 👀")
        return

    # Добавление в БД
    # 1) плейлист:
    try:
        last_added_track_url, title = await last_added_track_url_title(playlist)
        query = "INSERT INTO Playlist (Title, LastAddedTrack, Snapshot) VALUES (?, ?, ?)"
        await bot.db.execute(query, (p_id, last_added_track_url, playlist.snapshot))
        await bot.db.commit()
        logging.info(f"DB: Added Playlist with Title = \"{p_id}\", LastAddedTrack = {last_added_track_url}, Snapshot = {playlist.snapshot}")
    except DatabaseError as error:
        logging.error(error)
        logging.info(f"DB: Seems there is a Playlist with Title = \"{p_id}\" already existing in db")
        
    # 2) подписка пользователя на этот плейлист:
    try:
        query = "INSERT INTO Subscription (User_id, Playlist_id) VALUES (?, ?)"
        cursor = await bot.db.execute(query, (message.chat.id, p_id))
        await bot.db.commit()
        await cursor.close()
        logging.info(f"DB: Added Subscription with User_id = {message.chat.id}, Playlist_id = \"{p_id}\"")
    except DatabaseError as error:
        logging.error(error)
        logging.info(f"DB: Seems there is a Subscription with User_id = {message.chat.id}, Playlist_id = \"{p_id}\" already existing in db")
    
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
            if (playlist.find('music.yandex') != -1):
                playlists_list.append(playlist)
            else:
                #вот тут плохо
                playlists_list.append(get_url_from_playlist(await playlist_from_db(playlist)))
        await reply_to_message(message, "📌\n" + "\n📌\n".join(playlists_list))


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
📌Добавленные плейлисты можно удалить командой \"/delete_playlist\"
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
            if (playlist_name.find('music.yandex') != -1):
                playlist_id = playlist_name.split('/')[-1] 
                user_log = playlist_name.split('/')[-3]
            # Дёрнем апишку
            try:
                if (playlist_name.find('music.yandex') != -1):
                    playlist = await client.users_playlists(playlist_id, user_log)
                else:
                    playlist = await playlist_from_db(playlist_name)
            except YandexMusicError as error:
                logging.error(error)
                logging.info(f"WEB: Seems there is no Playlist with Title = \"{playlist_name}\"")
                continue # Если _на этом_ этапе что-то не так, просто скипаем этот плейлист UwU
            
            last_added_track_url, title = await last_added_track_url_title(playlist)

            if last_added_track_db != last_added_track_url:
                message = f"🎼 Новый трек \"{title}\" в плейлисте \"{playlist.title}\", вот ссылка:\n{last_added_track_url}"
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
                    logging.info(f"WEB: Sending an update message: to user {user}")
                    try:
                        await bot.send_message(user, message)
                    except Exception as error:
                        logging.error(error)
                        logging.error(f"WEB: Could not send message to user {user}")
                        continue

                # Обновим БД:
                try:
                    query = "UPDATE Playlist SET LastAddedTrack = ? WHERE Title = ?"
                    await bot.db.execute(query, (last_added_track_url, playlist_name))
                    await bot.db.commit()
                    logging.info(f"DB: Updated playlist {playlist_name}: LastAddedTrack was {last_added_track_db}, now {last_added_track_url}")
                except DatabaseError as error:
                    logging.error(error)
                    logging.error(f"DB: Could not update playlist {playlist_name} in db")

        await asyncio.sleep(5)


async def main():
    client = ClientAsync(ym_token)
    await client.init()
    async with aiosqlite.connect('PlaylistUpdateNotifier.db') as bot.db:
        await asyncio.gather(bot.infinity_polling(non_stop=True), polling())


# Запуск основого лупа
while 1:
    try:
        logging.info("starting an app!")        
        asyncio.run(main())
    except Exception as error:
        logging.error(error)
        logging.error(f"Gonna restart the app!")
