"""
Скрипт миграции пользователей с BotHelp в новую систему

Использование:
    python scripts/migrate_from_bothelp.py users_export.csv

Формат CSV:
    user_id,username,first_name,last_name,subscription_until
    123456789,johndoe,John,Doe,2026-03-15
"""

import asyncio
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.database import Database
import os
from dotenv import load_dotenv

load_dotenv()


async def parse_csv_file(csv_path: str) -> list:
    """Парсинг CSV файла с пользователями из BotHelp"""
    users = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as file:  # utf-8-sig убирает BOM
            # BotHelp экспортирует с разделителем ";" и кавычками
            reader = csv.DictReader(file, delimiter=';', quotechar='"')
            
            for row in reader:
                try:
                    # Парсим ID (может быть с кавычками и BOM)
                    user_id_str = None
                    for key in row.keys():
                        if 'id' in key.lower() and 'user_id' not in key.lower():
                            user_id_str = row[key].strip('"').strip()
                            break
                    
                    if not user_id_str:
                        continue
                    
                    user_id = int(user_id_str)
                    
                    # Парсим имена
                    first_name = row.get('first_name', '').strip('"')
                    last_name = row.get('last_name', '').strip('"')
                    
                    # Парсим подписку
                    subscription_days_str = row.get('Подписка Клуб', '').strip('"')
                    tags = row.get('User tags', '').strip('"')
                    
                    # Определяем дату окончания подписки
                    subscription_until = None
                    
                    if subscription_days_str and subscription_days_str.isdigit():
                        days = int(subscription_days_str)
                        if days > 0:
                            # Добавляем дни от текущей даты
                            subscription_until = datetime.utcnow() + timedelta(days=days)
                    
                    # Если в тегах есть активная подписка, но нет дней - ставим 30 дней
                    if not subscription_until and tags:
                        if 'подписка_оформлена' in tags and 'подписка_отменена' not in tags:
                            # Определяем длительность по тегам
                            if '12_месяцев' in tags:
                                subscription_until = datetime.utcnow() + timedelta(days=365)
                            elif '6_месяцев' in tags:
                                subscription_until = datetime.utcnow() + timedelta(days=180)
                            elif '3_месяца' in tags:
                                subscription_until = datetime.utcnow() + timedelta(days=90)
                            elif 'месяц' in tags:
                                subscription_until = datetime.utcnow() + timedelta(days=30)
                    
                    user_data = {
                        'user_id': user_id,
                        'username': None,  # BotHelp не экспортирует username
                        'first_name': first_name or None,
                        'last_name': last_name or None,
                        'subscription_until': subscription_until,
                        'tags': tags
                    }
                    
                    users.append(user_data)
                        
                except Exception as e:
                    print(f"⚠️  Ошибка парсинга строки: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        return users
        
    except FileNotFoundError:
        print(f"❌ Файл не найден: {csv_path}")
        return []
    except Exception as e:
        print(f"❌ Ошибка чтения файла: {e}")
        import traceback
        traceback.print_exc()
        return []


async def migrate_users(db: Database, users: list):
    """Миграция пользователей в новую БД"""
    print(f"\n📊 Начинаем миграцию {len(users)} пользователей...\n")
    
    success_count = 0
    error_count = 0
    subscribed_count = 0
    
    for i, user_data in enumerate(users, 1):
        try:
            # Добавляем пользователя
            user = await db.add_user(
                user_id=user_data['user_id'],
                username=user_data['username'] or None,
                first_name=user_data['first_name'] or None,
                last_name=user_data['last_name'] or None
            )
            
            # Если есть активная подписка
            if user_data['subscription_until']:
                expires_at = user_data['subscription_until']
                
                # Проверяем, не истекла ли подписка
                if expires_at > datetime.utcnow():
                    # Вычисляем длительность подписки
                    days_left = (expires_at - datetime.utcnow()).days
                    months = max(1, days_left // 30)
                    
                    # Создаем подписку
                    await db.add_subscription(
                        user_id=user_data['user_id'],
                        duration_months=months,
                        expires_at=expires_at,
                        activated_by="migration"
                    )
                    
                    subscribed_count += 1
                    status = "✅ + подписка"
                else:
                    status = "⚠️  (подписка истекла)"
            else:
                status = "✅"
            
            success_count += 1
            
            username_display = f"@{user_data['username']}" if user_data['username'] else user_data['first_name'] or "NoName"
            print(f"{i}/{len(users)} {status} {user_data['user_id']} {username_display}")
            
        except Exception as e:
            error_count += 1
            print(f"{i}/{len(users)} ❌ Ошибка для {user_data['user_id']}: {e}")
    
    print(f"\n{'='*60}")
    print(f"✅ Успешно мигрировано: {success_count}")
    print(f"   Из них с активной подпиской: {subscribed_count}")
    print(f"❌ Ошибок: {error_count}")
    print(f"{'='*60}\n")


async def create_sample_csv():
    """Создать пример CSV файла"""
    sample_data = [
        ["user_id", "username", "first_name", "last_name", "subscription_until"],
        ["123456789", "johndoe", "John", "Doe", "2026-06-15"],
        ["987654321", "janedoe", "Jane", "Doe", "2026-03-20"],
        ["555555555", "testuser", "Test", "User", ""],
    ]
    
    sample_file = "sample_users_export.csv"
    
    with open(sample_file, 'w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerows(sample_data)
    
    print(f"✅ Создан пример файла: {sample_file}")
    print("   Отредактируйте его и запустите миграцию заново.\n")


async def main():
    """Главная функция"""
    print("\n" + "="*60)
    print("🔄 МИГРАЦИЯ ПОЛЬЗОВАТЕЛЕЙ С BOTHELP")
    print("="*60 + "\n")
    
    # Проверка аргументов
    if len(sys.argv) < 2:
        print("❌ Не указан файл с пользователями!\n")
        print("Использование:")
        print("    python scripts/migrate_from_bothelp.py users_export.csv\n")
        
        # Предложить создать пример
        response = input("Создать пример CSV файла? (y/n): ")
        if response.lower() == 'y':
            await create_sample_csv()
        return
    
    csv_path = sys.argv[1]
    
    # Парсинг CSV
    print(f"📂 Читаем файл: {csv_path}\n")
    users = await parse_csv_file(csv_path)
    
    if not users:
        print("❌ Не удалось загрузить пользователей из файла.")
        return
    
    print(f"✅ Загружено {len(users)} пользователей\n")
    
    # Автоматическое продолжение (без подтверждения)
    print("⚠️  Начинаем миграцию...")
    
    # Инициализация БД
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./artclub.db")
    db = Database(db_url)
    await db.init_db()
    
    # Миграция
    await migrate_users(db, users)
    
    print("🎉 Миграция завершена!\n")
    print("Следующие шаги:")
    print("1. Запустите бота: python main.py")
    print("2. Отправьте рассылку с инструкциями для перехода в нового бота")
    print("3. Вручную создайте инвайт-ссылки для активных подписчиков\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Миграция прервана пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
