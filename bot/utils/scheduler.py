import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.database import Database
from bot.utils.invite import remove_user_from_channel

logger = logging.getLogger(__name__)


class SubscriptionChecker:
    """Класс для проверки и отключения истекших подписок"""
    
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.channel_id = int(os.getenv("MAIN_CHANNEL_ID", "0"))
        self.scheduler = AsyncIOScheduler()
    
    async def check_expired_subscriptions(self):
        """Проверка и отключение истекших подписок"""
        logger.info("Проверка истекших подписок...")
        
        try:
            # Emergency safe mode: prevent accidental removals while recurring
            # webhooks are being stabilized on provider side.
            disable_removal = os.getenv("DISABLE_EXPIRED_REMOVAL", "true").lower() == "true"
            if disable_removal:
                logger.warning("Удаление истекших подписок отключено (DISABLE_EXPIRED_REMOVAL=true)")
                return

            expired_users = await self.db.get_expired_subscribers()
            
            if not expired_users:
                logger.info("Нет пользователей с истекшей подпиской")
                return
            
            removed_count = 0
            
            for user in expired_users:
                try:
                    # Проверяем, сколько дней прошло с истечения
                    days_expired = (datetime.utcnow() - user.subscription_until).days
                    
                    # Даем 2 дня на автопродление, потом удаляем
                    if days_expired < 2:
                        logger.info(f"Пользователь {user.id} - подписка истекла, ждем автопродление ({days_expired} дней)")
                        continue
                    
                    # Удаляем пользователя из канала
                    await remove_user_from_channel(self.bot, self.channel_id, user.id)
                    
                    # Обновляем статус в БД
                    await self.db.update_subscription_status(
                        user_id=user.id,
                        is_subscribed=False
                    )
                    
                    # Уведомляем пользователя
                    try:
                        # Получаем текст из БД
                        expired_text = await self.db.get_text("subscription_expired",
                            "⏰ <b>Подписка не продлена</b>\n\n"
                            "Автоматическое продление не прошло (возможно, недостаточно средств на карте).\n\n"
                            "Доступ к закрытому каналу клуба отключен.\n\n"
                            "Чтобы продолжить участие в клубе, оформите новую подписку:\n"
                            "/start"
                        )
                        
                        await self.bot.send_message(
                            user.id,
                            expired_text,
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Не удалось отправить уведомление пользователю {user.id}: {e}")
                    
                    removed_count += 1
                    logger.info(f"Удален пользователь {user.id} (@{user.username}) - подписка не продлена")
                    
                except Exception as e:
                    logger.error(f"Ошибка при удалении пользователя {user.id}: {e}")
            
            logger.info(f"Удалено пользователей: {removed_count}")
            
        except Exception as e:
            logger.error(f"Ошибка при проверке подписок: {e}")
    
    async def send_expiration_reminders(self):
        """Отправка напоминаний о скором истечении подписки"""
        logger.info("Отправка напоминаний об истечении подписок...")
        
        try:
            active_users = await self.db.get_active_subscribers()
            
            reminder_count = 0
            
            for user in active_users:
                if not user.subscription_until:
                    continue
                
                days_left = (user.subscription_until - datetime.utcnow()).days
                
                # Напоминаем за 3 дня до истечения
                if days_left == 3:
                    try:
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="🔄 Изменить тариф", callback_data="change_plan")],
                                [InlineKeyboardButton(text="❌ Отменить подписку", url="https://shmuklerartclub.payform.ru")],
                                [InlineKeyboardButton(text="ℹ️ Подробнее", callback_data="auto_renewal_info")]
                            ]
                        )
                        
                        # Получаем текст напоминания из БД
                        reminder_text = await self.db.get_text("reminder_3days",
                            f"💳 <b>Напоминание о продлении подписки</b>\n\n"
                            f"Через <b>3 дня</b> с вашей карты автоматически спишется оплата за следующий период.\n\n"
                            f"🔄 <b>Подписка продлится автоматически</b>\n"
                            f"Вам ничего не нужно делать.\n\n"
                            f"⚠️ Пожалуйста, убедитесь, что на карте достаточно средств для списания.\n\n"
                            f"<i>Если хотите отменить подписку или изменить тариф, используйте кнопки ниже.</i>"
                        )
                        
                        await self.bot.send_message(
                            user.id,
                            reminder_text,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                        reminder_count += 1
                    except Exception as e:
                        logger.warning(f"Не удалось отправить напоминание пользователю {user.id}: {e}")
            
            logger.info(f"Отправлено напоминаний: {reminder_count}")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке напоминаний: {e}")
    
    def start(self):
        """Запуск планировщика"""
        # Проверка истекших подписок каждый день в 10:00
        self.scheduler.add_job(
            self.check_expired_subscriptions,
            CronTrigger(hour=10, minute=0),
            id="check_expired",
            name="Проверка истекших подписок",
            replace_existing=True
        )
        
        # Отправка напоминаний каждый день в 18:00
        self.scheduler.add_job(
            self.send_expiration_reminders,
            CronTrigger(hour=18, minute=0),
            id="send_reminders",
            name="Отправка напоминаний",
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Планировщик запущен")
    
    def stop(self):
        """Остановка планировщика"""
        self.scheduler.shutdown()
        logger.info("Планировщик остановлен")
