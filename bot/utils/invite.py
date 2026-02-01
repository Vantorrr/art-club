"""
Модуль для работы с инвайт-ссылками в канал
"""

import logging
import os
from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


async def create_invite_link(bot: Bot, channel_id: int, user_id: int) -> str:
    """
    Создание одноразовой инвайт-ссылки для пользователя
    
    Args:
        bot: Экземпляр бота
        channel_id: ID канала
        user_id: ID пользователя (для логирования)
    
    Returns:
        Инвайт-ссылка
    """
    try:
        # Создаем инвайт-ссылку с ограничениями:
        # - 1 использование
        # - Действует 24 часа
        invite_link = await bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,  # Только для 1 человека
            expire_date=datetime.utcnow() + timedelta(hours=24)
        )
        
        logger.info(f"Создана инвайт-ссылка для пользователя {user_id}")
        return invite_link.invite_link
        
    except TelegramAPIError as e:
        logger.error(f"Ошибка создания инвайт-ссылки: {e}")
        raise


async def send_invite_to_user(bot: Bot, user_id: int, channel_id: int, subscription_until: datetime):
    """
    Отправка инвайт-ссылки пользователю после оплаты
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        channel_id: ID канала
        subscription_until: Дата окончания подписки
    """
    try:
        # Создаем инвайт-ссылку
        invite_link = await create_invite_link(bot, channel_id, user_id)
        
        # Отправляем пользователю
        await bot.send_message(
            user_id,
            f"🎉 <b>Оплата прошла успешно!</b>\n\n"
            f"Ваша подписка активирована до <b>{subscription_until.strftime('%d.%m.%Y')}</b>\n\n"
            f"🔗 <b>Ссылка для входа в канал клуба:</b>\n"
            f"{invite_link}\n\n"
            f"<i>Ссылка действительна 24 часа и работает только для вас.</i>\n\n"
            f"Добро пожаловать в Shmukler Art Club! 🎨",
            parse_mode="HTML"
        )
        
        logger.info(f"Инвайт-ссылка отправлена пользователю {user_id}")
        
    except TelegramAPIError as e:
        logger.error(f"Ошибка отправки инвайт-ссылки пользователю {user_id}: {e}")
        
        # Пытаемся уведомить админов
        admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Не удалось отправить инвайт-ссылку пользователю {user_id}\n"
                    f"Отправьте ссылку вручную!"
                )
            except:
                pass


async def check_user_in_channel(bot: Bot, channel_id: int, user_id: int) -> bool:
    """
    Проверка, состоит ли пользователь в канале
    
    Args:
        bot: Экземпляр бота
        channel_id: ID канала
        user_id: ID пользователя
    
    Returns:
        True если пользователь в канале
    """
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramAPIError:
        return False


async def remove_user_from_channel(bot: Bot, channel_id: int, user_id: int):
    """
    Удаление пользователя из канала (при истечении подписки)
    
    Args:
        bot: Экземпляр бота
        channel_id: ID канала
        user_id: ID пользователя
    """
    try:
        # Баним (удаляем из канала)
        await bot.ban_chat_member(channel_id, user_id)
        
        # Сразу разбаниваем (просто удаляем, не блокируем навсегда)
        await bot.unban_chat_member(channel_id, user_id)
        
        logger.info(f"Пользователь {user_id} удален из канала {channel_id}")
        
    except TelegramAPIError as e:
        logger.error(f"Ошибка удаления пользователя {user_id} из канала: {e}")
