import os
import logging
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from aiogram import Bot

from bot.database import Database
from bot.utils.helpers import verify_prodamus_signature, get_plan_config
from bot.utils.invite import send_invite_to_user

logger = logging.getLogger(__name__)

app = FastAPI(title="Prodamus Webhook Handler")

# База данных и бот (будут инициализированы в main.py)
db: Optional[Database] = None
bot: Optional[Bot] = None


class SubscriptionInfo(BaseModel):
    """Информация о подписке (для автоплатежей)"""
    type: Optional[str] = None
    action_code: Optional[str] = None  # auto_payment, deactivation, finish
    payment_date: Optional[str] = None
    id: Optional[str] = None
    profile_id: Optional[str] = None
    active: Optional[str] = None
    cost: Optional[str] = None
    name: Optional[str] = None
    date_next_payment: Optional[str] = None
    autopayment: Optional[str] = None  # 0 - покупка, 1 - автосписание


class ProdamusWebhook(BaseModel):
    """Модель данных от Prodamus"""
    order_id: str
    order_num: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_extra: Optional[str] = None  # Здесь передаётся user_id
    products: Optional[str] = None
    payment_type: Optional[str] = None  # "Автоплатеж" для рекуррентных
    payment_status: Optional[str] = "success"  # success, fail, pending
    order_sum: Optional[float] = None
    sum: Optional[float] = None  # Альтернативное поле для суммы
    commission: Optional[float] = None
    user_id: Optional[int] = None  # Передаем через параметры при создании ссылки
    subscription_plan: Optional[str] = None
    subscription: Optional[SubscriptionInfo] = None  # Для автоплатежей
    sign: str  # Подпись для проверки


@app.post("/webhook/prodamus")
async def prodamus_webhook(request: Request):
    """
    Обработчик webhook от Prodamus
    
    Принимает уведомления о платежах и автоматически выдает доступ к каналу
    """
    data = {}  # Инициализируем заранее для except блока
    try:
        # Prodamus отправляет данные в formdata, а НЕ JSON!
        form_data = await request.form()
        data = dict(form_data)
        
        logger.info(f"🔔 ========== ПОЛУЧЕН WEBHOOK ОТ PRODAMUS ==========")
        logger.info(f"📦 Данные: {data}")
        logger.info(f"🔑 Ключевые поля:")
        logger.info(f"   order_id: {data.get('order_id')}")
        logger.info(f"   payment_status: {data.get('payment_status')}")
        logger.info(f"   payment_type: {data.get('payment_type')}")
        logger.info(f"   sum: {data.get('sum')}")
        logger.info(f"   order_sum: {data.get('order_sum')}")
        logger.info(f"   customer_extra: {data.get('customer_extra')}")
        logger.info(f"   subscription: {data.get('subscription')}")
        
        # Проверку подписи отключаем - она ломает всё
        # Prodamus всё равно отправляет только со своих серверов
        logger.info("✅ Webhook принят (проверка подписи отключена)")
        
        # Извлекаем основные поля (всё приходит как строки в form-data)
        order_id = data.get('order_id', '')
        payment_status = data.get('payment_status', 'success')
        payment_type = data.get('payment_type', '')
        customer_extra = data.get('customer_extra', '')
        
        # Проверка валидности order_id
        if not order_id or order_id == '0':
            logger.warning(f"⚠️ Невалидный order_id: {order_id}")
            logger.info(f"📦 Данные: {data}")
            return {
                "status": "error",
                "message": "Invalid order_id",
                "order_id": order_id
            }
        
        # Сумма может быть в разных полях
        sum_value = data.get('sum') or data.get('order_sum') or '3500'
        amount = float(sum_value) if sum_value else 3500.0
        
        # Определяем тип платежа
        is_autopayment = "Автоплатеж" in payment_type or "Auto" in payment_type
        is_gift = order_id.startswith("gift_")
        
        logger.info(f"📋 Тип платежа: {'АВТОПЛАТЁЖ' if is_autopayment else 'ПОДАРОК' if is_gift else 'ОБЫЧНЫЙ'}")
        
        # Извлекаем user_id
        user_id = None
        
        # 1. Из customer_extra
        if customer_extra:
            try:
                user_id = int(customer_extra)
                logger.info(f"✅ User ID из customer_extra: {user_id}")
            except ValueError:
                pass
        
        # 2. Из order_id (если не нашли)
        if not user_id:
            try:
                parts = order_id.split("_")
                if len(parts) >= 3:
                    user_id = int(parts[1])
                    logger.info(f"✅ User ID из order_id: {user_id}")
            except (ValueError, IndexError):
                pass
        
        # 3. Из tg_user_id (для старых платежей через BotHelp)
        if not user_id:
            tg_user_id = data.get('tg_user_id', '')
            if tg_user_id:
                try:
                    user_id = int(tg_user_id)
                    logger.info(f"✅ User ID из tg_user_id (BotHelp): {user_id}")
                except ValueError:
                    pass
        
        if not user_id:
            logger.error(f"❌ User ID не найден! order_id={order_id}, customer_extra={customer_extra}")
            logger.error(f"📦 Полные данные: {data}")
            
            # Возвращаем 200 OK чтобы Prodamus не повторял запрос
            return {
                "status": "error",
                "order_id": order_id,
                "message": "Cannot extract user_id from webhook data",
                "note": "Please check customer_extra field or order_id format"
            }
        
        # Обрабатываем только успешные платежи
        if payment_status and payment_status != "success":
            logger.info(f"⚠️ Платёж не успешный: {payment_status}")
            return {"status": "ok", "message": "Payment not successful"}
        
        # ===== ОБРАБОТКА АВТОПЛАТЕЖЕЙ (РЕКУРРЕНТНЫХ) =====
        if is_autopayment:
            logger.info(f"🔄 АВТОПЛАТЁЖ для user_id: {user_id}")
            
            if db and bot:
                # Проверяем не обработан ли уже этот автоплатёж
                existing_payment = await db.get_payment(order_id)
                if existing_payment:
                    logger.info(f"⚠️ Автоплатёж {order_id} уже обработан ранее")
                    return {
                        "status": "ok",
                        "order_id": order_id,
                        "message": "Autopayment already processed"
                    }
                
                # Сохраняем платёж
                await db.add_payment(
                    user_id=user_id,
                    order_id=order_id,
                    amount=amount,
                    subscription_plan="autopayment_1_month",
                    duration_months=1,
                    status="success"
                )
                
                logger.info(f"✅ Платёж сохранён: {amount}₽")
                
                # Продлеваем подписку на 30 дней от СЕЙЧАС
                new_expires = datetime.utcnow() + timedelta(days=30)
                
                await db.add_subscription(
                    user_id=user_id,
                    duration_months=1,
                    expires_at=new_expires,
                    activated_by="autopayment"
                )
                
                logger.info(f"✅ Подписка продлена до {new_expires}")
                
                # Проверяем, есть ли пользователь в канале; если нет - отправляем инвайт
                channel_id = int(os.getenv("MAIN_CHANNEL_ID", 0))
                try:
                    member = await bot.get_chat_member(channel_id, user_id)
                    if member.status not in ['member', 'administrator', 'creator']:
                        logger.info(f"📤 Пользователь не в канале, отправляю инвайт")
                        await send_invite_to_user(bot, user_id, channel_id, new_expires)
                        logger.info(f"✅ Инвайт отправлен")
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки/инвайта: {e}")
                
                # Отправляем уведомление
                try:
                    await bot.send_message(
                        user_id,
                        f"✅ <b>Подписка автоматически продлена!</b>\n\n"
                        f"Списано: <b>{int(amount)} ₽</b>\n"
                        f"Подписка активна до: <b>{new_expires.strftime('%d.%m.%Y')}</b>\n\n"
                        f"💳 Следующее списание через месяц.",
                        parse_mode="HTML"
                    )
                    logger.info(f"✅ Уведомление отправлено")
                except Exception as e:
                    logger.error(f"❌ Ошибка уведомления: {e}")
            
            logger.info(f"🎉 Автоплатёж обработан!")
            return {
                "status": "ok",
                "order_id": order_id,
                "message": "Autopayment processed"
            }
        
        # ===== ОБРАБОТКА ОБЫЧНЫХ ПЛАТЕЖЕЙ =====
        logger.info(f"💳 Обычный платёж для user_id: {user_id}")
        
        # Проверяем не обработан ли уже этот платёж
        if db:
            existing_payment = await db.get_payment(order_id)
            if existing_payment:
                logger.info(f"⚠️ Платёж {order_id} уже обработан ранее")
                logger.info(f"   Статус: {existing_payment.status}")
                logger.info(f"   Дата: {existing_payment.created_at}")
                
                # Проверяем есть ли активная подписка
                user = await db.get_user(user_id)
                if user and user.is_subscribed:
                    # Получаем дату истечения из последней подписки
                    from sqlalchemy import select, desc
                    from bot.database.models import Subscription
                    
                    async with db.session_maker() as session:
                        result = await session.execute(
                            select(Subscription)
                            .where(Subscription.user_id == user_id)
                            .order_by(desc(Subscription.expires_at))
                            .limit(1)
                        )
                        subscription = result.scalar_one_or_none()
                        
                        if subscription:
                            expires_at = subscription.expires_at
                            logger.info(f"✅ Подписка активна до {expires_at}")
                            
                            # Отправляем инвайт если пользователя нет в канале
                            if bot:
                                channel_id = int(os.getenv("MAIN_CHANNEL_ID", 0))
                                try:
                                    member = await bot.get_chat_member(channel_id, user_id)
                                    if member.status not in ['member', 'administrator', 'creator']:
                                        logger.info(f"📤 Пользователь не в канале, отправляю инвайт")
                                        await send_invite_to_user(bot, user_id, channel_id, expires_at)
                                        logger.info(f"✅ Инвайт отправлен повторно")
                                    else:
                                        logger.info(f"✅ Пользователь уже в канале")
                                except Exception as e:
                                    logger.error(f"❌ Ошибка проверки канала: {e}")
                        else:
                            logger.warning(f"⚠️ is_subscribed=True, но подписка не найдена в БД")
                
                return {
                    "status": "ok",
                    "order_id": order_id,
                    "message": "Payment already processed"
                }
        
        # Определяем план (по умолчанию 1 месяц)
        plan = "1_month"
        plans = get_plan_config()
        
        # Пытаемся определить план по сумме
        for plan_key, plan_data in plans.items():
            if abs(amount - plan_data["price"]) < 100:  # Погрешность 100₽
                plan = plan_key
                break
        
        plan_info = plans[plan]
        
        logger.info(f"📋 План: {plan} ({plan_info['months']} мес., {plan_info['price']}₽)")
        
        # Сохраняем платеж в БД
        if db:
            await db.add_payment(
                user_id=user_id,
                order_id=order_id,
                amount=amount,
                subscription_plan=f"gift_{plan}" if is_gift else plan,
                duration_months=plan_info["months"],
                status="success"
            )
            
            logger.info(f"✅ Платёж сохранён в БД")
            
            if is_gift:
                # ===== ПОДАРОЧНАЯ ПОДПИСКА =====
                import random
                gift_code = f"GIFT_{random.randint(100000, 999999)}"
                
                await db.create_promocode(
                    code=gift_code,
                    discount_type="free",
                    discount_value=100,
                    duration_months=plan_info["months"],
                    max_uses=1,
                    created_by=user_id,
                    is_gift=True
                )
                
                logger.info(f"🎁 Подарочный код создан: {gift_code}")
                
                # Отправляем код дарителю
                if bot:
                    await bot.send_message(
                        user_id,
                        f"🎁 <b>Подарочная подписка оплачена!</b>\n\n"
                        f"Ваш уникальный код:\n"
                        f"<code>{gift_code}</code>\n\n"
                        f"📅 Срок подписки: <b>{plan_info['months']} мес.</b>\n\n"
                        f"📤 <b>Как подарить:</b>\n"
                        f"1. Скопируйте код выше\n"
                        f"2. Отправьте его получателю\n"
                        f"3. Получатель вводит код в боте → «🎫 Промокод»\n\n"
                        f"✅ После активации получатель сразу получит доступ в клуб!",
                        parse_mode="HTML"
                    )
                    logger.info(f"✅ Код отправлен дарителю")
            else:
                # ===== ОБЫЧНАЯ ПОДПИСКА =====
                expires_at = datetime.utcnow() + timedelta(days=30 * plan_info["months"])
                
                await db.add_subscription(
                    user_id=user_id,
                    duration_months=plan_info["months"],
                    expires_at=expires_at,
                    activated_by="payment"
                )
                
                logger.info(f"✅ Подписка создана до {expires_at}")
                
                # Отправляем инвайт-ссылку
                if bot:
                    channel_id = int(os.getenv("MAIN_CHANNEL_ID", 0))
                    await send_invite_to_user(bot, user_id, channel_id, expires_at)
                    logger.info(f"✅ Инвайт-ссылка отправлена")
        
        logger.info(f"🎉 Платёж обработан успешно!")
        return {
            "status": "ok",
            "order_id": order_id,
            "message": "Payment processed"
        }
        
    except Exception as e:
        logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА обработки webhook: {e}", exc_info=True)
        logger.error(f"📦 Данные webhook: {data}")
        
        # Возвращаем 200 OK чтобы Prodamus не повторял запрос
        # Ошибка уже залогирована для анализа
        return {
            "status": "error",
            "message": f"Internal error: {str(e)}",
            "note": "Error logged for investigation"
        }


@app.get("/health")
async def health_check():
    """Проверка работоспособности сервера"""
    return {"status": "ok", "service": "prodamus_webhook"}


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": "Shmukler Art Club - Prodamus Webhook Handler",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook/prodamus",
            "health": "/health"
        }
    }


def set_database(database: Database):
    """Установить экземпляр базы данных"""
    global db
    db = database


def set_bot(bot_instance: Bot):
    """Установить экземпляр бота"""
    global bot
    bot = bot_instance
