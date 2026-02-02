from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def admin_menu_kb() -> ReplyKeyboardMarkup:
    """Главное меню админа"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="🎁 Промокоды"), KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="💰 Финансы"), KeyboardButton(text="📥 Экспорт базы")],
            [KeyboardButton(text="🔙 Выход из админ-панели")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Админ-панель"
    )
    return keyboard


def user_management_kb(user_id: int) -> InlineKeyboardMarkup:
    """Управление конкретным пользователем"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Продлить подписку", callback_data=f"admin:extend:{user_id}")],
            [InlineKeyboardButton(text="🎁 Выдать промокод", callback_data=f"admin:give_promo:{user_id}")],
            [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"admin:ban:{user_id}")],
            [InlineKeyboardButton(text="« Назад", callback_data="admin:users_list")]
        ]
    )
    return keyboard


def promo_actions_kb() -> InlineKeyboardMarkup:
    """Действия с промокодами"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Создать подарочную подписку", callback_data="admin:create_gift")],
            [InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin:create_promo")],
            [InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin:list_promos")],
            [InlineKeyboardButton(text="« Назад", callback_data="admin:menu")]
        ]
    )
    return keyboard


def promo_type_kb() -> InlineKeyboardMarkup:
    """Выбор типа промокода"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Бесплатная подписка", callback_data="promo_type:free")],
            [InlineKeyboardButton(text="💰 Скидка в процентах", callback_data="promo_type:percent")],
            [InlineKeyboardButton(text="💵 Фиксированная скидка", callback_data="promo_type:fixed")],
            [InlineKeyboardButton(text="« Отмена", callback_data="admin:promos")]
        ]
    )
    return keyboard


def broadcast_target_kb() -> InlineKeyboardMarkup:
    """Выбор аудитории для рассылки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Все пользователи", callback_data="broadcast:all")],
            [InlineKeyboardButton(text="✅ Только активные подписчики", callback_data="broadcast:active")],
            [InlineKeyboardButton(text="❌ Только с истекшей подпиской", callback_data="broadcast:expired")],
            [InlineKeyboardButton(text="« Отмена", callback_data="admin:menu")]
        ]
    )
    return keyboard


def confirm_broadcast_kb() -> InlineKeyboardMarkup:
    """Подтверждение рассылки"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast:confirm")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="broadcast:cancel")]
        ]
    )
    return keyboard


def pagination_kb(page: int, total_pages: int, prefix: str) -> InlineKeyboardMarkup:
    """Пагинация для списков"""
    buttons = []
    
    if page > 1:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:page:{page-1}"))
    
    buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:page:{page+1}"))
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            buttons,
            [InlineKeyboardButton(text="« Назад", callback_data="admin:menu")]
        ]
    )
    return keyboard
