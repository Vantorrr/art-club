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


class ProdamusWebhook(BaseModel):
    """Модель данных от Prodamus"""
    order_id: str
    order_num: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    products: Optional[str] = None
    payment_type: Optional[str] = None
    payment_status: str  # success, fail, pending
    order_sum: float
    commission: Optional[float] = None
    user_id: Optional[int] = None  # Передаем через параметры при создании ссылки
    subscription_plan: Optional[str] = None
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
        logger.info(f"Получен webhook от Prodamus: {data}")
        
        # Проверяем подпись
        secret_key = os.getenv("PRODAMUS_SECRET_KEY")
        if not verify_prodamus_signature(data, secret_key):
            logger.warning("Невалидная подпись webhook")
            raise HTTPException(status_code=403, detail="Invalid signature")
        
        # Парсим данные
        webhook_data = ProdamusWebhook(**data)
        
        # Обрабатываем только успешные платежи
        if webhook_data.payment_status != "success":
            logger.info(f"Платеж {webhook_data.order_id} не успешный: {webhook_data.payment_status}")
            return {"status": "ok", "message": "Payment not successful"}
        
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
        
        # Сохраняем платеж в БД
        if db:
            await db.add_payment(
                user_id=webhook_data.user_id,
                order_id=webhook_data.order_id,
                amount=webhook_data.order_sum,
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
