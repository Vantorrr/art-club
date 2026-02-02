import os
import random
import string
import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import List

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from openpyxl import Workbook

from bot.database import Database
from bot.keyboards import admin as kb

logger = logging.getLogger(__name__)
router = Router()


def get_admin_ids() -> list:
    """Получить список админов из .env (динамически)"""
    return [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]


def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    admin_ids = get_admin_ids()
    logger.info(f"Проверка админа: user_id={user_id}, admin_ids={admin_ids}")
    return user_id in admin_ids


class BroadcastState(StatesGroup):
    """Состояния для рассылки"""
    waiting_for_content = State()
    waiting_for_confirmation = State()


class PromoCreationState(StatesGroup):
    """Состояния для создания промокода"""
    waiting_for_code = State()
    waiting_for_discount = State()
    waiting_for_duration = State()
    waiting_for_max_uses = State()


class GiftCreationState(StatesGroup):
    """Состояния для создания подарочной подписки"""
    waiting_for_recipient = State()
    waiting_for_duration = State()


class TextEditState(StatesGroup):
    """Состояния для редактирования текстов"""
    waiting_for_new_text = State()


@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Вход в админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    
    await message.answer(
        "👨‍💼 <b>Админ-панель Shmukler Art Club</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.admin_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin:menu")
async def back_to_admin_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в админ-панель (инлайн кнопка Назад)"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.clear()  # Очищаем состояние
    
    # Удаляем инлайн сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass  # Игнорируем если не удалось удалить
    
    # Отправляем новое сообщение с reply keyboard
    await callback.bot.send_message(
        callback.message.chat.id,
        "👨‍💼 <b>Админ-панель Shmukler Art Club</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.admin_menu_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin:promos")
async def back_to_promos_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в меню промокодов"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.clear()
    await callback.message.edit_text(
        "🎁 <b>Управление промокодами</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.promo_actions_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin:users_list")
async def back_to_users_list(callback: CallbackQuery, db: Database):
    """Возврат к списку пользователей"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    # Получаем пользователей и показываем список
    users = await db.get_all_users()
    
    if not users:
        await callback.message.edit_text("📭 Пользователей пока нет.")
        await callback.answer()
        return
    
    text = "👥 <b>Все пользователи:</b>\n\n"
    users_sorted = sorted(users, key=lambda u: (not u.is_subscribed, u.id))
    
    for i, user in enumerate(users_sorted[:30], 1):
        status = "✅" if user.is_subscribed else "❌"
        if user.username:
            name = f"@{user.username}"
        elif user.first_name:
            name = user.first_name
        else:
            name = "Без имени"
        
        if user.is_subscribed and user.subscription_until:
            days_left = (user.subscription_until - datetime.utcnow()).days
            name += f" ({days_left}д.)"
        
        text += f"{status} {name}\n"
    
    if len(users) > 30:
        text += f"\n... и еще {len(users) - 30} пользователей"
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


@router.message(Command("test_notifications"))
async def test_notifications(message: Message):
    """Тестирование уведомлений (только для админов)"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📬 <b>Примеры автоматических уведомлений:</b>\n\n"
        "Система отправляет 2 типа уведомлений:",
        parse_mode="HTML"
    )
    
    # Пример 1: Напоминание за 3 дня (с кнопками)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Изменить тариф", callback_data="change_plan")],
            [InlineKeyboardButton(text="❌ Отменить подписку", url="https://shmuklerartclub.payform.ru")],
            [InlineKeyboardButton(text="ℹ️ Подробнее", callback_data="auto_renewal_info")]
        ]
    )
    
    await message.answer(
        f"💳 <b>Напоминание о продлении подписки</b>\n\n"
        f"Через <b>3 дня</b> с вашей карты автоматически спишется оплата за следующий период.\n\n"
        f"🔄 <b>Подписка продлится автоматически</b>\n"
        f"Вам ничего не нужно делать.\n\n"
        f"⚠️ Пожалуйста, убедитесь, что на карте достаточно средств для списания.\n\n"
        f"<i>Если хотите отменить подписку или изменить тариф, используйте кнопки ниже.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    
    # Пример 2: Уведомление если автопродление не прошло
    await message.answer(
        "⏰ <b>Подписка не продлена</b>\n\n"
        "Автоматическое продление не прошло (возможно, недостаточно средств на карте).\n\n"
        "Доступ к закрытому каналу клуба отключен.\n\n"
        "Чтобы продолжить участие в клубе, оформите новую подписку:\n"
        "/start",
        parse_mode="HTML"
    )
    
    await message.answer(
        "ℹ️ <b>Как работает автопродление:</b>\n\n"
        "• <b>За 3 дня до истечения</b> — напоминание (в 18:00)\n"
        "• <b>В день истечения</b> — автоматическое списание с карты\n"
        "• <b>Через 2 дня после истечения</b> — если продление не прошло, удаление из канала (в 10:00)\n\n"
        "✅ Если автосписание прошло успешно — подписка продлевается автоматически, и пользователь остается в клубе.\n\n"
        "Система работает без вашего участия.",
        parse_mode="HTML"
    )


@router.message(F.text == "📊 Статистика")
async def stats_button(message: Message, db: Database):
    """Обработка кнопки Статистика"""
    if not is_admin(message.from_user.id):
        return
    await show_statistics(message, db)


@router.message(F.text == "👥 Пользователи")
async def users_button(message: Message, db: Database):
    """Обработка кнопки Пользователи"""
    if not is_admin(message.from_user.id):
        return
    await users_list(message, db)


@router.message(F.text == "🎁 Промокоды")
async def promos_button(message: Message):
    """Обработка кнопки Промокоды"""
    if not is_admin(message.from_user.id):
        return
    await promo_menu(message)


@router.message(F.text == "📢 Рассылка")
async def broadcast_button(message: Message):
    """Обработка кнопки Рассылка"""
    if not is_admin(message.from_user.id):
        return
    await broadcast_menu(message)


@router.message(F.text == "💰 Финансы")
async def finances_button(message: Message, db: Database):
    """Обработка кнопки Финансы"""
    if not is_admin(message.from_user.id):
        return
    await finances(message, db)


@router.message(F.text == "📥 Экспорт базы")
async def export_button(message: Message, db: Database):
    """Обработка кнопки Экспорт базы"""
    if not is_admin(message.from_user.id):
        return
    await export_database(message, db)


@router.message(F.text == "✏️ Редактировать тексты")
async def edit_texts_button(message: Message, db: Database):
    """Обработка кнопки Редактировать тексты"""
    if not is_admin(message.from_user.id):
        return
    await show_texts_list(message, db)


@router.message(F.text == "🔙 Выход из админ-панели")
async def exit_admin(message: Message, state: FSMContext):
    """Выход из админ-панели"""
    if not is_admin(message.from_user.id):
        return
    
    # Очищаем любые незавершенные действия (рассылка, промокоды и т.д.)
    await state.clear()
    
    from bot.keyboards import user as user_kb
    await message.answer(
        "Вы вышли из админ-панели.",
        reply_markup=user_kb.main_menu_kb(is_admin=True)  # Показываем кнопку админки
    )


# ============ РЕДАКТИРОВАНИЕ ТЕКСТОВ ============

async def show_texts_list(message: Message, db: Database):
    """Показать список редактируемых текстов"""
    texts = await db.get_all_texts()
    
    if not texts:
        await message.answer("📝 Тексты еще не инициализированы. Инициализирую...")
        await db.init_default_texts()
        texts = await db.get_all_texts()
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    for text_obj in texts:
        # Делаем короткое название для кнопки
        short_desc = text_obj.description[:40] + "..." if len(text_obj.description) > 40 else text_obj.description
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {short_desc}",
                callback_data=f"edit_text:{text_obj.key}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="admin:menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(
        "✏️ <b>Редактирование текстов бота</b>\n\n"
        "Выберите текст, который хотите изменить:\n\n"
        "<i>💡 Изменения применятся сразу для всех пользователей</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("edit_text:"))
async def show_text_editor(callback: CallbackQuery, db: Database, state: FSMContext):
    """Показать редактор конкретного текста"""
    if not is_admin(callback.from_user.id):
        return
    
    text_key = callback.data.split(":")[1]
    text_obj = await db.get_text(text_key)
    
    if not text_obj:
        await callback.answer("❌ Текст не найден", show_alert=True)
        return
    
    # Получаем полный объект для description
    all_texts = await db.get_all_texts()
    text_full = next((t for t in all_texts if t.key == text_key), None)
    
    await state.update_data(editing_text_key=text_key)
    await state.set_state(TextEditState.waiting_for_new_text)
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_text_edit")]
        ]
    )
    
    await callback.message.edit_text(
        f"✏️ <b>Редактирование текста</b>\n\n"
        f"📝 <b>{text_full.description if text_full else text_key}</b>\n\n"
        f"<b>Текущий текст:</b>\n"
        f"<code>{text_obj}</code>\n\n"
        f"Отправьте новый текст (можно использовать HTML форматирование):",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(TextEditState.waiting_for_new_text)
async def save_edited_text(message: Message, db: Database, state: FSMContext):
    """Сохранить отредактированный текст"""
    if not is_admin(message.from_user.id):
        return
    
    data = await state.get_data()
    text_key = data.get("editing_text_key")
    
    if not text_key:
        await message.answer("❌ Ошибка: не указан ключ текста")
        await state.clear()
        return
    
    new_text = message.text
    
    # Сохраняем новый текст
    await db.set_text(text_key, new_text, updated_by=message.from_user.id)
    
    await state.clear()
    
    await message.answer(
        f"✅ <b>Текст обновлен!</b>\n\n"
        f"Ключ: <code>{text_key}</code>\n\n"
        f"<b>Новый текст:</b>\n{new_text}",
        parse_mode="HTML"
    )
    
    # Возвращаем список текстов
    await show_texts_list(message, db)


@router.callback_query(F.data == "cancel_text_edit")
async def cancel_text_edit(callback: CallbackQuery, db: Database, state: FSMContext):
    """Отмена редактирования текста"""
    await state.clear()
    
    # Получаем список текстов
    texts = await db.get_all_texts()
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    for text_obj in texts:
        short_desc = text_obj.description[:40] + "..." if len(text_obj.description) > 40 else text_obj.description
        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {short_desc}",
                callback_data=f"edit_text:{text_obj.key}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="« Назад", callback_data="admin:menu")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(
        "✏️ <b>Редактирование текстов бота</b>\n\n"
        "Выберите текст, который хотите изменить:\n\n"
        "<i>💡 Изменения применятся сразу для всех пользователей</i>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer("❌ Редактирование отменено")


# ============ СТАТИСТИКА ============

@router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message, db: Database):
    """Показать статистику"""
    if not is_admin(message.from_user.id):
        return
    
    stats = await db.get_statistics()
    
    await message.answer(
        f"📊 <b>Статистика клуба</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"✅ Активных подписчиков: <b>{stats['active_subscribers']}</b>\n"
        f"💰 Общая выручка: <b>{stats['total_revenue']:,.0f} ₽</b>\n\n"
        f"📅 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
        parse_mode="HTML"
    )


# ============ УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ============

@router.message(F.text == "👥 Пользователи")
async def users_list(message: Message, db: Database):
    """Список пользователей"""
    if not is_admin(message.from_user.id):
        return
    
    users = await db.get_all_users()
    
    if not users:
        await message.answer("📭 Пользователей пока нет.")
        return
    
    # Показываем ВСЕХ пользователей (до 50 на странице)
    text = "👥 <b>Все пользователи:</b>\n\n"
    
    # Сортируем: сначала с активной подпиской
    users_sorted = sorted(users, key=lambda u: (not u.is_subscribed, u.id))
    
    per_page = 50
    total_shown = min(len(users_sorted), per_page)
    
    for i, user in enumerate(users_sorted[:per_page], 1):
        status = "✅" if user.is_subscribed else "❌"
        
        # Показываем username или имя
        if user.username:
            name = f"@{user.username}"
        elif user.first_name:
            name = user.first_name
            if user.last_name:
                name += f" {user.last_name}"
        else:
            name = "Без имени"
        
        # Добавляем дату окончания для активных подписок
        if user.is_subscribed and user.subscription_until:
            days_left = (user.subscription_until - datetime.utcnow()).days
            name += f" ({days_left}д.)"
        
        text += f"{i}. {status} <code>{user.id}</code> — {name}\n"
    
    text += f"\n<i>Показано {total_shown} из {len(users)} пользователей</i>"
    
    if len(users) > per_page:
        text += f"\n<i>Для просмотра остальных используйте команду /users_all</i>"
    
    await message.answer(text, parse_mode="HTML")


# ============ ПРОМОКОДЫ ============

@router.message(F.text == "🎁 Промокоды")
async def promo_menu(message: Message):
    """Меню промокодов"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "🎁 <b>Управление промокодами</b>\n\n"
        "Выберите действие:",
        reply_markup=kb.promo_actions_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin:create_gift")
async def create_gift_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания подарочной подписки"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(GiftCreationState.waiting_for_recipient)
    await callback.message.edit_text(
        "🎁 <b>Создание подарочной подписки</b>\n\n"
        "Введите @username или Telegram ID получателя:\n\n"
        "Примеры:\n"
        "• <code>@ivan_petrov</code> — для конкретного пользователя\n"
        "• <code>123456789</code> — по Telegram ID\n\n"
        "<i>💡 Если пользователя еще нет в базе, код активируется при его первом заходе в бота</i>",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(GiftCreationState.waiting_for_recipient)
async def receive_gift_recipient(message: Message, state: FSMContext, db: Database):
    """Получение @username или ID получателя подарка"""
    if not is_admin(message.from_user.id):
        return
    
    input_text = message.text.strip()
    recipient_id = None
    recipient_username = None
    user = None
    
    # Проверяем что это - @username или ID
    if input_text.startswith("@"):
        # Это username
        recipient_username = input_text[1:].lower()  # Убираем @ и делаем lowercase
        
        # Ищем в базе
        from sqlalchemy import select
        from bot.database.models import User
        async with db.session_maker() as session:
            result = await session.execute(
                select(User).where(User.username == recipient_username)
            )
            user = result.scalar_one_or_none()
        
        if user:
            recipient_id = user.id
            await state.update_data(recipient_id=recipient_id, recipient_username=recipient_username)
            user_info = f"@{recipient_username} (найден в базе)"
        else:
            await state.update_data(recipient_username=recipient_username)
            user_info = f"@{recipient_username} (код активируется при первом заходе)"
    else:
        # Пытаемся как ID
        try:
            recipient_id = int(input_text)
            user = await db.get_user(recipient_id)
            
            if user and user.username:
                recipient_username = user.username
                await state.update_data(recipient_id=recipient_id, recipient_username=recipient_username)
                user_info = f"@{user.username}"
            else:
                await state.update_data(recipient_id=recipient_id)
                user_info = f"ID {recipient_id}"
        except ValueError:
            await message.answer("❌ Введите @username или Telegram ID (число)")
            return
    
    await state.set_state(GiftCreationState.waiting_for_duration)
    
    await message.answer(
        f"✅ Получатель: {user_info}\n\n"
        "Выберите срок подарочной подписки (в месяцах):\n"
        "1, 3, 6, 9 или 12",
        parse_mode="HTML"
    )


@router.message(GiftCreationState.waiting_for_duration)
async def receive_gift_duration(message: Message, state: FSMContext, db: Database):
    """Получение срока подарочной подписки"""
    if not is_admin(message.from_user.id):
        return
    
    # Проверяем корректность срока
    try:
        duration = int(message.text)
        if duration not in [1, 3, 6, 9, 12]:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите один из доступных тарифов: 1, 3, 6, 9 или 12 месяцев")
        return
    
    data = await state.get_data()
    recipient_id = data.get('recipient_id')
    recipient_username = data.get('recipient_username')
    
    # Генерируем уникальный промокод
    gift_code = f"GIFT_{random.randint(100000, 999999)}"
    
    # Создаем подарочный промокод в БД
    await db.create_promocode(
        code=gift_code,
        discount_type="free",
        discount_value=100,
        duration_months=duration,
        max_uses=1,
        created_by=message.from_user.id,
        is_gift=True,
        for_user_id=recipient_id,
        for_username=recipient_username
    )
    
    await state.clear()
    
    # Формируем информацию о получателе
    if recipient_username:
        user_info = f"@{recipient_username}"
    elif recipient_id:
        user = await db.get_user(recipient_id)
        user_info = f"@{user.username}" if user and user.username else f"ID {recipient_id}"
    else:
        user_info = "Любой пользователь"
    
    await message.answer(
        f"✅ <b>Подарочная подписка создана!</b>\n\n"
        f"📝 Код: <code>{gift_code}</code>\n"
        f"👤 Получатель: {user_info}\n"
        f"📅 Срок: {duration} мес.\n\n"
        f"💡 Отправьте этот код получателю. Он сможет активировать его через бота в разделе \"🎁 Активировать промокод\"",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin:create_promo")
async def create_promo_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания промокода"""
    if not is_admin(callback.from_user.id):
        return
    
    await callback.message.edit_text(
        "🎁 <b>Создание промокода</b>\n\n"
        "Выберите тип промокода:",
        reply_markup=kb.promo_type_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("promo_type:"))
async def set_promo_type(callback: CallbackQuery, state: FSMContext):
    """Установка типа промокода"""
    if not is_admin(callback.from_user.id):
        return
    
    promo_type = callback.data.split(":")[1]
    await state.update_data(discount_type=promo_type)
    
    # Автогенерация кода
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    await state.update_data(code=code)
    
    if promo_type == "free":
        await state.update_data(discount_value=100)
        await state.set_state(PromoCreationState.waiting_for_duration)
        
        await callback.message.edit_text(
            f"🎁 <b>Создание промокода</b>\n\n"
            f"Тип: Бесплатная подписка\n"
            f"Код: <code>{code}</code>\n\n"
            f"На сколько месяцев дать подписку? (введите число)",
            parse_mode="HTML"
        )
    else:
        await state.set_state(PromoCreationState.waiting_for_discount)
        
        discount_unit = "%" if promo_type == "percent" else "₽"
        await callback.message.edit_text(
            f"🎁 <b>Создание промокода</b>\n\n"
            f"Тип: {'Процентная скидка' if promo_type == 'percent' else 'Фиксированная скидка'}\n"
            f"Код: <code>{code}</code>\n\n"
            f"Введите размер скидки ({discount_unit}):",
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.message(PromoCreationState.waiting_for_discount)
async def set_promo_discount(message: Message, state: FSMContext):
    """Установка размера скидки"""
    if not is_admin(message.from_user.id):
        return
    
    # Игнорируем кнопки меню - они обрабатываются своими хэндлерами
    menu_buttons = ["📊 Статистика", "👥 Пользователи", "🎁 Промокоды", "📢 Рассылка",
                    "💰 Финансы", "📤 Экспорт", "🔙 Выход из админ-панели",
                    "💳 Купить подписку", "🎁 Купить в подарок", "📊 Моя подписка", "🎫 Промокод",
                    "ℹ️ О клубе", "📞 Поддержка", "👨‍💼 Админ-панель"]
    
    if message.text in menu_buttons:
        return  # Пропускаем, пусть обработают другие хэндлеры
    
    try:
        discount = float(message.text)
        await state.update_data(discount_value=discount)
        await state.set_state(PromoCreationState.waiting_for_duration)
        
        data = await state.get_data()
        await message.answer(
            f"🎁 <b>Создание промокода</b>\n\n"
            f"Код: <code>{data['code']}</code>\n"
            f"Скидка: {discount}{'%' if data['discount_type'] == 'percent' else ' ₽'}\n\n"
            f"На сколько месяцев действует подписка? (введите число)",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Некорректное значение. Введите число.")


@router.message(PromoCreationState.waiting_for_duration)
async def set_promo_duration(message: Message, state: FSMContext):
    """Установка длительности подписки"""
    if not is_admin(message.from_user.id):
        return
    
    # Игнорируем кнопки меню - они обрабатываются своими хэндлерами
    menu_buttons = ["📊 Статистика", "👥 Пользователи", "🎁 Промокоды", "📢 Рассылка",
                    "💰 Финансы", "📤 Экспорт", "🔙 Выход из админ-панели",
                    "💳 Купить подписку", "🎁 Купить в подарок", "📊 Моя подписка", "🎫 Промокод",
                    "ℹ️ О клубе", "📞 Поддержка", "👨‍💼 Админ-панель"]
    
    if message.text in menu_buttons:
        return  # Пропускаем, пусть обработают другие хэндлеры
    
    try:
        duration = int(message.text)
        await state.update_data(duration_months=duration)
        await state.set_state(PromoCreationState.waiting_for_max_uses)
        
        data = await state.get_data()
        await message.answer(
            f"🎁 <b>Создание промокода</b>\n\n"
            f"Код: <code>{data['code']}</code>\n"
            f"Длительность: {duration} мес.\n\n"
            f"Максимальное количество использований?\n"
            f"(введите число или 0 для неограниченного)",
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Некорректное значение. Введите число.")


@router.message(PromoCreationState.waiting_for_max_uses)
async def finalize_promo_creation(message: Message, state: FSMContext, db: Database):
    """Финализация создания промокода"""
    if not is_admin(message.from_user.id):
        return
    
    # Игнорируем кнопки меню - они обрабатываются своими хэндлерами
    menu_buttons = ["📊 Статистика", "👥 Пользователи", "🎁 Промокоды", "📢 Рассылка",
                    "💰 Финансы", "📤 Экспорт", "🔙 Выход из админ-панели",
                    "💳 Купить подписку", "🎁 Купить в подарок", "📊 Моя подписка", "🎫 Промокод",
                    "ℹ️ О клубе", "📞 Поддержка", "👨‍💼 Админ-панель"]
    
    if message.text in menu_buttons:
        return  # Пропускаем, пусть обработают другие хэндлеры
    
    try:
        max_uses = int(message.text)
        max_uses = None if max_uses == 0 else max_uses
        
        data = await state.get_data()
        
        # Создаем промокод в БД
        promo = await db.create_promocode(
            code=data['code'],
            discount_type=data['discount_type'],
            discount_value=data['discount_value'],
            duration_months=data['duration_months'],
            max_uses=max_uses,
            created_by=message.from_user.id
        )
        
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"Код: <code>{promo.code}</code>\n"
            f"Тип: {promo.discount_type}\n"
            f"Скидка: {promo.discount_value}{'%' if promo.discount_type == 'percent' else ' ₽'}\n"
            f"Длительность: {promo.duration_months} мес.\n"
            f"Макс. использований: {promo.max_uses or 'без ограничений'}",
            parse_mode="HTML"
        )
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Некорректное значение. Введите число.")


@router.callback_query(F.data == "admin:list_promos")
async def list_promocodes(callback: CallbackQuery, db: Database):
    """Список промокодов"""
    if not is_admin(callback.from_user.id):
        return
    
    promos = await db.get_all_promocodes()
    
    if not promos:
        await callback.message.edit_text("📭 Промокодов пока нет.")
        return
    
    text = "🎁 <b>Список промокодов:</b>\n\n"
    
    for promo in promos:
        status = "✅" if promo.is_active else "❌"
        uses = f"{promo.used_count}/{promo.max_uses}" if promo.max_uses else f"{promo.used_count}"
        
        text += (
            f"{status} <code>{promo.code}</code>\n"
            f"Тип: {promo.discount_type} | Скидка: {promo.discount_value}\n"
            f"Использований: {uses}\n\n"
        )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await callback.answer()


# ============ РАССЫЛКА ============

@router.message(F.text == "📢 Рассылка")
async def broadcast_menu(message: Message):
    """Меню рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    await message.answer(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Выберите целевую аудиторию:",
        reply_markup=kb.broadcast_target_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("broadcast:"))
async def process_broadcast(callback: CallbackQuery, state: FSMContext, db: Database):
    """Обработка рассылки"""
    if not is_admin(callback.from_user.id):
        return
    
    action = callback.data.split(":")[1]
    
    if action in ["all", "active", "expired"]:
        await state.update_data(target=action)
        await state.set_state(BroadcastState.waiting_for_content)
        
        target_names = {
            "all": "всем пользователям",
            "active": "активным подписчикам",
            "expired": "пользователям с истекшей подпиской"
        }
        
        await callback.message.edit_text(
            f"📢 <b>Рассылка {target_names[action]}</b>\n\n"
            f"Отправьте сообщение для рассылки.\n"
            f"Можно отправить текст, фото, видео или документ с подписью.",
            parse_mode="HTML"
        )
        
    elif action == "confirm":
        # Отправляем рассылку
        data = await state.get_data()
        target = data.get("target")
        
        # Получаем список пользователей
        if target == "all":
            users = await db.get_all_users()
        elif target == "active":
            users = await db.get_active_subscribers()
        else:
            users = await db.get_expired_subscribers()
        
        sent_count = 0
        failed_count = 0
        
        for user in users:
            try:
                if data.get("media_type") == "photo":
                    await callback.bot.send_photo(
                        user.id,
                        data["media_file_id"],
                        caption=data.get("text")
                    )
                elif data.get("media_type") == "video":
                    await callback.bot.send_video(
                        user.id,
                        data["media_file_id"],
                        caption=data.get("text")
                    )
                else:
                    await callback.bot.send_message(user.id, data["text"])
                
                sent_count += 1
            except Exception:
                failed_count += 1
        
        # Сохраняем статистику в БД
        try:
            await db.add_broadcast(
                message_text=data.get("text", ""),
                target_audience=target or "unknown",
                created_by=callback.from_user.id,
                media_type=data.get("media_type"),
                media_file_id=data.get("media_file_id")
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения статистики рассылки: {e}")
        
        await callback.message.edit_text(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"✉️ Отправлено: {sent_count}\n"
            f"❌ Не удалось: {failed_count}",
            parse_mode="HTML"
        )
        
        await state.clear()
    
    elif action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Рассылка отменена.")
    
    await callback.answer()


@router.message(BroadcastState.waiting_for_content)
async def receive_broadcast_content(message: Message, state: FSMContext):
    """Прием содержимого рассылки"""
    if not is_admin(message.from_user.id):
        return
    
    # Игнорируем кнопки меню - они обрабатываются своими хэндлерами
    menu_buttons = ["📊 Статистика", "👥 Пользователи", "🎁 Промокоды", "📢 Рассылка",
                    "💰 Финансы", "📤 Экспорт", "🔙 Выход из админ-панели",
                    "💳 Купить подписку", "🎁 Купить в подарок", "📊 Моя подписка", "🎫 Промокод",
                    "ℹ️ О клубе", "📞 Поддержка", "👨‍💼 Админ-панель"]
    
    if message.text and message.text in menu_buttons:
        return  # Пропускаем, пусть обработают другие хэндлеры
    
    data = {}
    
    if message.photo:
        data["media_type"] = "photo"
        data["media_file_id"] = message.photo[-1].file_id
        data["text"] = message.caption or ""
    elif message.video:
        data["media_type"] = "video"
        data["media_file_id"] = message.video.file_id
        data["text"] = message.caption or ""
    else:
        data["text"] = message.text
    
    await state.update_data(**data)
    await state.set_state(BroadcastState.waiting_for_confirmation)
    
    # Превью сообщения
    await message.answer(
        f"📢 <b>Предпросмотр рассылки:</b>\n\n"
        f"Подтвердите отправку:",
        reply_markup=kb.confirm_broadcast_kb(),
        parse_mode="HTML"
    )
    
    # Отправляем копию сообщения как превью
    if data.get("media_type") == "photo":
        await message.bot.send_photo(
            message.chat.id,
            data["media_file_id"],
            caption=data.get("text")
        )
    elif data.get("media_type") == "video":
        await message.bot.send_video(
            message.chat.id,
            data["media_file_id"],
            caption=data.get("text")
        )
    else:
        await message.answer(data["text"])


# ============ ЭКСПОРТ БАЗЫ ============

@router.message(F.text == "📥 Экспорт базы")
async def export_database(message: Message, db: Database):
    """Экспорт базы пользователей в Excel"""
    if not is_admin(message.from_user.id):
        return
    
    users = await db.get_all_users()
    
    if not users:
        await message.answer("📭 База пользователей пуста.")
        return
    
    # Создаем Excel файл
    wb = Workbook()
    ws = wb.active
    ws.title = "Пользователи"
    
    # Заголовки
    ws.append(["ID", "Username", "Имя", "Фамилия", "Подписка", "Действует до", "Дата регистрации"])
    
    # Данные
    for user in users:
        ws.append([
            user.id,
            user.username or "-",
            user.first_name or "-",
            user.last_name or "-",
            "Активна" if user.is_subscribed else "Нет",
            user.subscription_until.strftime("%d.%m.%Y") if user.subscription_until else "-",
            user.joined_at.strftime("%d.%m.%Y %H:%M")
        ])
    
    # Сохраняем в BytesIO
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    # Отправляем файл
    file = BufferedInputFile(
        buffer.read(),
        filename=f"artclub_users_{datetime.now().strftime('%Y%m%d')}.xlsx"
    )
    
    await message.answer_document(
        file,
        caption=f"📊 Экспорт базы пользователей\n\nВсего: {len(users)} записей"
    )


# ============ ФИНАНСЫ ============

@router.message(F.text == "💰 Финансы")
async def finances(message: Message, db: Database):
    """Финансовая статистика"""
    if not is_admin(message.from_user.id):
        return
    
    stats = await db.get_statistics()
    
    await message.answer(
        f"💰 <b>Финансовая статистика</b>\n\n"
        f"Общая выручка: <b>{stats['total_revenue']:,.0f} ₽</b>\n\n"
        f"<i>Для детального отчета используйте экспорт базы</i>",
        parse_mode="HTML"
    )
