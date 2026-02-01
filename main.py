import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.database import Database
from bot.handlers import user, admin
from bot.utils.scheduler import SubscriptionChecker

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot, db: Database):
    """Действия при запуске бота"""
    logger.info("Бот запускается...")
    
    # Инициализация БД
    await db.init_db()
    logger.info("База данных инициализирована")
    
    # Получаем информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"Бот запущен: @{bot_info.username}")


async def on_shutdown(bot: Bot, scheduler: SubscriptionChecker):
    """Действия при остановке бота"""
    logger.info("Бот останавливается...")
    scheduler.stop()
    await bot.session.close()


async def main():
    """Главная функция запуска бота"""
    
    # Проверка обязательных переменных окружения
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN не установлен в .env файле!")
        return
    
    # Инициализация бота
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Инициализация диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Инициализация базы данных
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./artclub.db")
    # Railway дает postgresql://, но нужен postgresql+asyncpg://
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    db = Database(db_url)
    
    # Регистрация роутеров (admin первым, чтобы команды не перехватывались)
    dp.include_router(admin.router)
    dp.include_router(user.router)
    
    # Middleware для передачи БД в хэндлеры
    @dp.update.outer_middleware()
    async def database_middleware(handler, event, data):
        data["db"] = db
        return await handler(event, data)
    
    # Инициализация планировщика проверки подписок
    scheduler = SubscriptionChecker(bot, db)
    scheduler.start()
    
    # Запуск бота
    await on_startup(bot, db)
    
    try:
        logger.info("Начинаем polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}", exc_info=True)
    finally:
        await on_shutdown(bot, scheduler)


def run_webhook_server():
    """
    Запуск FastAPI webhook сервера
    
    Для production рекомендуется запускать отдельным процессом:
    uvicorn webhook.prodamus:app --host 0.0.0.0 --port 8000
    """
    import uvicorn
    from webhook import app, set_database, set_bot
    
    # Инициализация БД для webhook
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./artclub.db")
    # Railway дает postgresql://, но нужен postgresql+asyncpg://
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    db = Database(db_url)
    set_database(db)
    
    # Инициализация бота для webhook
    bot_token = os.getenv("BOT_TOKEN")
    bot = Bot(token=bot_token)
    set_bot(bot)
    
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    # Railway использует переменную PORT, fallback на WEBHOOK_PORT или 8000
    port = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8000")))
    
    logger.info(f"Запуск webhook сервера на {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    """
    Запуск бота.
    
    Для запуска ТОЛЬКО бота:
        python main.py
    
    Для запуска ТОЛЬКО webhook сервера:
        python main.py webhook
    
    Для production рекомендуется запускать в отдельных процессах:
        # Терминал 1 - Бот
        python main.py
        
        # Терминал 2 - Webhook
        python main.py webhook
    """
    
    if len(sys.argv) > 1 and sys.argv[1] == "webhook":
        run_webhook_server()
    else:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("Бот остановлен пользователем")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}", exc_info=True)
