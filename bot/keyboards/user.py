from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню пользователя"""
    buttons = [
        [KeyboardButton(text="💳 Купить подписку"), KeyboardButton(text="🎁 Купить в подарок")],
        [KeyboardButton(text="📊 Моя подписка"), KeyboardButton(text="🎫 Промокод")],
        [KeyboardButton(text="ℹ️ О клубе"), KeyboardButton(text="📞 Поддержка")]
    ]
    
    # Добавляем кнопку админки для админов
    if is_admin:
        buttons.append([KeyboardButton(text="👨‍💼 Админ-панель")])
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard


def subscription_plans_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифа"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 месяц — 3 500 ₽", callback_data="buy:1_month")],
            [InlineKeyboardButton(text="3 месяца — 9 450 ₽ (-10%)", callback_data="buy:3_months")],
            [InlineKeyboardButton(text="6 месяцев — 17 850 ₽ (-15%)", callback_data="buy:6_months")],
            [InlineKeyboardButton(text="12 месяцев — 33 600 ₽ (-20%)", callback_data="buy:12_months")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def gift_plans_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора тарифа для подарка"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 1 месяц — 3 500 ₽", callback_data="gift:1_month")],
            [InlineKeyboardButton(text="🎁 3 месяца — 9 450 ₽ (-10%)", callback_data="gift:3_months")],
            [InlineKeyboardButton(text="🎁 6 месяцев — 17 850 ₽ (-15%)", callback_data="gift:6_months")],
            [InlineKeyboardButton(text="🎁 12 месяцев — 33 600 ₽ (-20%)", callback_data="gift:12_months")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard


def payment_kb(payment_url: str) -> InlineKeyboardMarkup:
    """Клавиатура оплаты"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_payment")],
            [InlineKeyboardButton(text="« Отменить", callback_data="cancel_payment")]
        ]
    )
    return keyboard


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="« Отмена", callback_data="cancel")]
        ]
    )
    return keyboard


def my_subscription_kb() -> InlineKeyboardMarkup:
    """Клавиатура для активной подписки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Сменить тариф", callback_data="change_plan")],
            [InlineKeyboardButton(text="❌ Отменить подписку", callback_data="cancel_subscription")],
        ]
    )
    return keyboard


def confirm_cancel_subscription_kb() -> InlineKeyboardMarkup:
    """Подтверждение отмены подписки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Да, отменить подписку", callback_data="confirm_cancel_subscription")],
            [InlineKeyboardButton(text="« Нет, оставить", callback_data="keep_subscription")],
        ]
    )
    return keyboard


def support_kb() -> InlineKeyboardMarkup:
    """Контакты поддержки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать в поддержку", url="https://t.me/artishokcenter_info")],
            [InlineKeyboardButton(text="🌐 Сайт клуба", url="https://artishokcenter.ru/shmuklerartclub")],
            [InlineKeyboardButton(text="« Назад", callback_data="back_to_menu")]
        ]
    )
    return keyboard
