import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional


def generate_invite_link(bot_username: str, channel_id: int) -> str:
    """
    Генерация инвайт-ссылки в канал
    
    ВНИМАНИЕ: Это заглушка! В реальности нужно использовать:
    await bot.create_chat_invite_link(channel_id, member_limit=1)
    """
    return f"https://t.me/{bot_username}?start=invite_{abs(channel_id)}"


def calculate_subscription_end(months: int) -> datetime:
    """Рассчитать дату окончания подписки"""
    return datetime.utcnow() + timedelta(days=30 * months)


def format_price(price: float) -> str:
    """Форматировать цену"""
    return f"{price:,.0f} ₽".replace(",", " ")


def verify_prodamus_signature(data: dict, secret_key: str) -> bool:
    """
    Проверка подписи Prodamus webhook
    
    Args:
        data: Данные от Prodamus
        secret_key: Секретный ключ
    
    Returns:
        True если подпись валидна
    """
    # Получаем подпись из данных
    received_signature = data.get('sign')
    if not received_signature:
        return False
    
    # Создаем строку для подписи (по документации Prodamus)
    # Обычно это конкатенация полей в определенном порядке
    sign_string = f"{data.get('order_id')}{data.get('amount')}{secret_key}"
    
    # Вычисляем хеш
    calculated_signature = hashlib.md5(sign_string.encode()).hexdigest()
    
    return hmac.compare_digest(received_signature, calculated_signature)


def get_plan_config() -> dict:
    """Получить конфигурацию тарифных планов"""
    import os
    
    return {
        "1_month": {
            "months": 1,
            "price": int(os.getenv("PRICE_1_MONTH", 3500)),
            "name": "1 месяц"
        },
        "3_months": {
            "months": 3,
            "price": int(os.getenv("PRICE_3_MONTHS", 9450)),
            "name": "3 месяца",
            "discount": 10
        },
        "6_months": {
            "months": 6,
            "price": int(os.getenv("PRICE_6_MONTHS", 17850)),
            "name": "6 месяцев",
            "discount": 15
        },
        "12_months": {
            "months": 12,
            "price": int(os.getenv("PRICE_12_MONTHS", 33600)),
            "name": "12 месяцев",
            "discount": 20
        }
    }


def apply_promo_discount(price: float, promo_type: str, promo_value: float) -> float:
    """Применить скидку промокода"""
    if promo_type == "percent":
        return price * (1 - promo_value / 100)
    elif promo_type == "fixed":
        return max(0, price - promo_value)
    else:  # free
        return 0


def format_subscription_status(is_active: bool, expires_at: Optional[datetime]) -> str:
    """Форматировать статус подписки"""
    if not is_active:
        return "❌ Неактивна"
    
    if not expires_at:
        return "⚠️ Дата не указана"
    
    days_left = (expires_at - datetime.utcnow()).days
    
    if days_left < 0:
        return "❌ Истекла"
    elif days_left == 0:
        return "⚠️ Истекает сегодня"
    elif days_left <= 3:
        return f"⚠️ Осталось {days_left} дн."
    else:
        return f"✅ Активна ({days_left} дн.)"
