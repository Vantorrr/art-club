"""
Миграция: Добавление поля for_username в таблицу promocodes
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def migrate():
    # Получаем DATABASE_URL из окружения
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./artclub.db")
    
    # Railway дает postgresql://, но нужен postgresql+asyncpg://
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Подключение к БД: {db_url.split('@')[0]}@***")
    
    engine = create_async_engine(db_url, echo=True)
    
    async with engine.begin() as conn:
        # Проверяем существует ли уже поле
        try:
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='promocodes' AND column_name='for_username'"
            ))
            exists = result.fetchone()
            
            if exists:
                print("✅ Поле for_username уже существует")
            else:
                print("➕ Добавляем поле for_username...")
                await conn.execute(text(
                    "ALTER TABLE promocodes ADD COLUMN for_username VARCHAR(100)"
                ))
                print("✅ Поле for_username добавлено!")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            raise
    
    await engine.dispose()
    print("✅ Миграция завершена!")

if __name__ == "__main__":
    asyncio.run(migrate())
