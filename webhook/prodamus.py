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
    try:
        # Получаем данные
        data = await request.json()
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
        
        # Проверяем подпись (отключаем для отладки)
        secret_key = os.getenv("PRODAMUS_SECRET_KEY")
        skip_signature_check = os.getenv("SKIP_SIGNATURE_CHECK", "false").lower() == "true"
        
        if not skip_signature_check:
            if not verify_prodamus_signature(data, secret_key):
                logger.warning("Невалидная подпись webhook")
                raise HTTPException(status_code=403, detail="Invalid signature")
        else:
            logger.warning("⚠️ Проверка подписи ОТКЛЮЧЕНА (режим отладки)")
        
        # Парсим данные
        webhook_data = ProdamusWebhook(**data)
        
        # Определяем тип платежа
        is_autopayment = (
            webhook_data.payment_type == "Автоплатеж" or
            (webhook_data.subscription and webhook_data.subscription.autopayment == "1")
        )
        
        # Извлекаем user_id
        if not webhook_data.user_id:
            # Сначала пробуем customer_extra (для автоплатежей и новых платежей)
            if webhook_data.customer_extra:
                try:
                    webhook_data.user_id = int(webhook_data.customer_extra)
                    logger.info(f"User ID извлечён из customer_extra: {webhook_data.user_id}")
                except ValueError:
                    pass
            
            # Если не получилось - извлекаем из order_id (для старых платежей)
            if not webhook_data.user_id:
                try:
                    parts = webhook_data.order_id.split("_")
                    if len(parts) >= 3:
                        webhook_data.user_id = int(parts[1])
                        logger.info(f"User ID извлечён из order_id: {webhook_data.user_id}")
                except (ValueError, IndexError) as e:
                    logger.error(f"Не удалось извлечь user_id: {e}")
        
        if not webhook_data.user_id:
            logger.error(f"User ID не найден в платеже {webhook_data.order_id}")
            raise HTTPException(status_code=400, detail="Missing user_id")
        
        # Обрабатываем только успешные платежи
        if webhook_data.payment_status and webhook_data.payment_status != "success":
            logger.info(f"Платеж {webhook_data.order_id} не успешный: {webhook_data.payment_status}")
            return {"status": "ok", "message": "Payment not successful"}
        
        # ===== ОБРАБОТКА АВТОПЛАТЕЖЕЙ (РЕКУРРЕНТНЫХ) =====
        if is_autopayment:
            logger.info(f"🔄 Обработка автоплатежа для user_id: {webhook_data.user_id}")
            
            # Определяем сумму платежа
            amount = webhook_data.order_sum or webhook_data.sum or 0
            
            if db:
                # Сохраняем платёж
                await db.add_payment(
                    user_id=webhook_data.user_id,
                    order_id=webhook_data.order_id,
                    amount=amount,
                    subscription_plan="autopayment_1_month",
                    duration_months=1,
                    status="success"
                )
                
                # Продлеваем существующую подписку на 1 месяц (30 дней)
                user = await db.get_user(webhook_data.user_id)
                
                if user:
                    # Если подписка активна - продлеваем от текущей даты окончания
                    # Если истекла - продлеваем от текущего момента
                    from sqlalchemy import text
                    async with db.engine.begin() as conn:
                        result = await conn.execute(
                            text('SELECT expires_at FROM subscriptions WHERE user_id = :user_id ORDER BY started_at DESC LIMIT 1'),
                            {'user_id': webhook_data.user_id}
                        )
                        last_sub = result.fetchone()
                    
                    if last_sub and last_sub.expires_at > datetime.utcnow():
                        # Подписка активна - продлеваем от expires_at
                        new_expires = last_sub.expires_at + timedelta(days=30)
                    else:
                        # Подписка истекла или нет - продлеваем от сейчас
                        new_expires = datetime.utcnow() + timedelta(days=30)
                    
                    # Создаём новую подписку
                    await db.add_subscription(
                        user_id=webhook_data.user_id,
                        duration_months=1,
                        expires_at=new_expires,
                        activated_by="autopayment"
                    )
                    
                    logger.info(f"✅ Подписка продлена до {new_expires} для user_id: {webhook_data.user_id}")
                    
                    # Отправляем уведомление о продлении
                    if bot:
                        try:
                            await bot.send_message(
                                webhook_data.user_id,
                                f"✅ <b>Подписка автоматически продлена!</b>\n\n"
                                f"Списано: <b>{int(amount)} ₽</b>\n"
                                f"Подписка активна до: <b>{new_expires.strftime('%d.%m.%Y')}</b>\n\n"
                                f"💳 Следующее списание через месяц.\n\n"
                                f"Если хотите отменить подписку или изменить тариф, используйте кнопки ниже.",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logger.error(f"Ошибка отправки уведомления о продлении: {e}")
            
            return {
                "status": "ok",
                "order_id": webhook_data.order_id,
                "message": "Autopayment processed successfully"
            }
        
        # ===== ОБРАБОТКА ОБЫЧНЫХ ПЛАТЕЖЕЙ =====
        # Определяем тип платежа (обычная подписка или подарок)
        is_gift = webhook_data.order_id.startswith("gift_")
        
        # Получаем данные о подписке
        plan = webhook_data.subscription_plan or "1_month"
        # Убираем префикс gift_ из плана если есть
        if plan.startswith("gift_"):
            plan = plan.replace("gift_", "")
        
        plans = get_plan_config()
        
        if plan not in plans:
            logger.error(f"Неизвестный план: {plan}")
            raise HTTPException(status_code=400, detail="Invalid subscription plan")
        
        plan_info = plans[plan]
        
        # Определяем сумму платежа (может быть sum или order_sum)
        amount = webhook_data.order_sum or webhook_data.sum or plan_info["price"]
        
        # Сохраняем платеж в БД
        if db:
            await db.add_payment(
                user_id=webhook_data.user_id,
                order_id=webhook_data.order_id,
                amount=amount,
                subscription_plan=f"gift_{plan}" if is_gift else plan,
                duration_months=plan_info["months"],
                status="success"
            )
            
            if is_gift:
                # ===== ПОДАРОЧНАЯ ПОДПИСКА =====
                # Создаем уникальный промокод
                import random
                gift_code = f"GIFT_{random.randint(100000, 999999)}"
                
                await db.create_promocode(
                    code=gift_code,
                    discount_type="free",
                    discount_value=100,
                    duration_months=plan_info["months"],
                    max_uses=1,
                    created_by=webhook_data.user_id,
                    is_gift=True
                    # for_username не указываем - подарок для любого
                )
                
                logger.info(
                    f"🎁 Подарочная подписка создана. Buyer: {webhook_data.user_id}, "
                    f"Code: {gift_code}, Duration: {plan_info['months']} мес."
                )
                
                # Отправляем код дарителю
                if bot:
                    await bot.send_message(
                        webhook_data.user_id,
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
            else:
                # ===== ОБЫЧНАЯ ПОДПИСКА =====
                # Активируем подписку
                expires_at = datetime.utcnow() + timedelta(days=30 * plan_info["months"])
                
                await db.add_subscription(
                    user_id=webhook_data.user_id,
                    duration_months=plan_info["months"],
                    expires_at=expires_at,
                    activated_by="payment"
                )
                
                # Отправляем инвайт-ссылку пользователю
                logger.info(
                    f"✅ Платеж успешно обработан. User: {webhook_data.user_id}, "
                    f"Plan: {plan}, Expires: {expires_at}. Отправка инвайт-ссылки..."
                )
                
                # Отправляем инвайт-ссылку
                if bot:
                    channel_id = int(os.getenv("MAIN_CHANNEL_ID", 0))
                    await send_invite_to_user(bot, webhook_data.user_id, channel_id, expires_at)
        
        return {
            "status": "ok",
            "order_id": webhook_data.order_id,
            "message": "Payment processed successfully"
        }
        
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
