import asyncio
import os
import telebot

from telebot.async_telebot import AsyncTeleBot
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.
token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = AsyncTeleBot(token)



@bot.message_handler()
async def on_message(message):
    await bot.send_message(message.chat.id, message.text)
      

async def polling():
    while True:
        await asyncio.sleep(3600)

async def main():
    await asyncio.gather(bot.infinity_polling(), polling())


asyncio.run(main())




