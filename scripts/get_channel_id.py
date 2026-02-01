"""
Простой скрипт для получения ID канала

Использование:
1. Вставь токен бота
2. Запусти скрипт
3. Перешли любое сообщение из канала боту
4. ID появится в логах
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ВСТАВЬ ТОКЕН БОТА СЮДА
BOT_TOKEN = "8352044661:AAEqmks0vtfHWcNn8Q2hRzGrbjL_vifIkow"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Вставь токен бота в переменную BOT_TOKEN!")
        return
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    @dp.message(Command("start"))
    async def cmd_start(message: types.Message):
        await message.answer(
            f"👋 Привет!\n\n"
            f"Твой ID: <code>{message.from_user.id}</code>\n\n"
            f"Чтобы узнать ID канала:\n"
            f"1. Перешли любое сообщение из канала сюда\n"
            f"2. Я покажу тебе ID канала",
            parse_mode="HTML"
        )
    
    @dp.message()
    async def get_channel_id(message: types.Message):
        if message.forward_from_chat:
            chat = message.forward_from_chat
            
            await message.answer(
                f"🎯 <b>ID канала:</b>\n\n"
                f"<code>{chat.id}</code>\n\n"
                f"Название: {chat.title}\n"
                f"Тип: {chat.type}\n\n"
                f"Скопируй ID и вставь в .env файл:\n"
                f"<code>MAIN_CHANNEL_ID={chat.id}</code>",
                parse_mode="HTML"
            )
            
            logger.info(f"Канал '{chat.title}' ID: {chat.id}")
        else:
            await message.answer("Перешли сообщение из канала для получения ID")
    
    logger.info("Бот запущен! Напиши ему /start")
    logger.info("Перешли сообщение из канала для получения ID")
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
