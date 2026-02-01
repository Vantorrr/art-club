import os
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database import Database
from bot.keyboards import user as kb


router = Router()


class PromoState(StatesGroup):
    """Состояния для активации промокода"""
    waiting_for_code = State()


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database):
    """Обработка команды /start"""
    user = message.from_user
    
    # Добавляем пользователя в БД
    await db.add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Проверяем, админ ли это
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    is_admin = user.id in admin_ids
    
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Добро пожаловать в <b>Shmukler Art Club</b> — закрытое сообщество для тех, "
        f"кто хочет глубже понимать искусство и быть в курсе главных культурных событий.\n\n"
        f"🎨 <b>Что входит в клуб:</b>\n"
        f"• Частные экскурсии и арт-туры\n"
        f"• Посещение мастерских художников\n"
        f"• Онлайн-лекции от Оли Шмуклер\n"
        f"• Подборки выставок и культурных событий\n"
        f"• Бесплатный арт-консалтинг\n"
        f"• Скидка 15% на покупку произведений искусства\n\n"
        f"Выберите действие:",
        reply_markup=kb.main_menu_kb(is_admin=is_admin),
        parse_mode="HTML"
    )


@router.message(F.text == "💳 Купить подписку")
async def buy_subscription(message: Message):
    """Показать тарифы"""
    await message.answer(
        "💳 <b>Выберите тариф подписки:</b>\n\n"
        "При подписке на 3+ месяца действуют скидки!\n"
        "Все новые участники получают скидку 15% на покупку произведений искусства.",
        reply_markup=kb.subscription_plans_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("buy:"))
async def process_plan_selection(callback: CallbackQuery, db: Database):
    """Обработка выбора тарифа"""
    plan = callback.data.split(":")[1]
    
    # Маппинг тарифов
    plans_config = {
        "1_month": {"months": 1, "price": int(os.getenv("PRICE_1_MONTH", 3500)), "name": "1 месяц"},
        "3_months": {"months": 3, "price": int(os.getenv("PRICE_3_MONTHS", 9450)), "name": "3 месяца"},
        "6_months": {"months": 6, "price": int(os.getenv("PRICE_6_MONTHS", 17850)), "name": "6 месяцев"},
        "12_months": {"months": 12, "price": int(os.getenv("PRICE_12_MONTHS", 33600)), "name": "12 месяцев"}
    }
    
    if plan not in plans_config:
        await callback.answer("❌ Неверный тариф", show_alert=True)
        return
    
    plan_info = plans_config[plan]
    user_id = callback.from_user.id
    
    # Генерируем уникальный order_id
    import time
    order_id = f"artclub_{user_id}_{int(time.time())}"
    
    # Создаем запись о платеже в БД (статус pending)
    await db.add_payment(
        user_id=user_id,
        order_id=order_id,
        amount=plan_info['price'],
        subscription_plan=plan,
        duration_months=plan_info['months'],
        status="pending"
    )
    
    # Генерируем ссылку на оплату Prodamus
    # ВАЖНО: Нужно настроить в Prodamus передачу этих параметров
    prodamus_base_url = os.getenv("PRODAMUS_BASE_URL", "https://artclub.pay.prodamus.ru")
    payment_url = (
        f"{prodamus_base_url}?"
        f"order_id={order_id}&"
        f"customer_extra={user_id}&"
        f"products[0][price]={plan_info['price']}&"
        f"products[0][name]=Подписка {plan_info['name']}&"
        f"products[0][quantity]=1&"
        f"do=pay"
    )
    
    await callback.message.edit_text(
        f"💳 <b>Оплата подписки</b>\n\n"
        f"Тариф: <b>{plan_info['name']}</b>\n"
        f"Стоимость: <b>{plan_info['price']} ₽</b>\n\n"
        f"Нажмите кнопку ниже для перехода к оплате.\n"
        f"После успешной оплаты вам автоматически придет инвайт-ссылка в канал клуба.",
        reply_markup=kb.payment_kb(payment_url),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "check_payment")
async def check_payment_status(callback: CallbackQuery, db: Database):
    """Проверка статуса оплаты (пока заглушка)"""
    user = await db.get_user(callback.from_user.id)
    
    if user and user.is_subscribed:
        await callback.answer("✅ Ваша подписка активна!", show_alert=True)
    else:
        await callback.answer(
            "⏳ Платеж еще не поступил. Подождите несколько минут после оплаты.",
            show_alert=True
        )


@router.message(F.text == "📊 Моя подписка")
async def my_subscription(message: Message, db: Database):
    """Информация о подписке"""
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Пользователь не найден. Используйте /start")
        return
    
    if user.is_subscribed and user.subscription_until:
        days_left = (user.subscription_until - datetime.utcnow()).days
        
        status_emoji = "✅" if days_left > 7 else "⚠️"
        
        await message.answer(
            f"{status_emoji} <b>Ваша подписка активна</b>\n\n"
            f"Действует до: <b>{user.subscription_until.strftime('%d.%m.%Y')}</b>\n"
            f"Осталось дней: <b>{days_left}</b>\n\n"
            f"После истечения срока подписки доступ к каналу будет автоматически закрыт.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ <b>У вас нет активной подписки</b>\n\n"
            "Оформите подписку, чтобы получить доступ к эксклюзивному контенту клуба!",
            reply_markup=kb.subscription_plans_kb(),
            parse_mode="HTML"
        )


@router.message(F.text == "🎁 Промокод")
async def activate_promo_start(message: Message, state: FSMContext):
    """Начало активации промокода"""
    await state.set_state(PromoState.waiting_for_code)
    await message.answer(
        "🎁 <b>Активация промокода</b>\n\n"
        "Введите промокод для получения скидки или бесплатного доступа:",
        reply_markup=kb.cancel_kb(),
        parse_mode="HTML"
    )


@router.message(PromoState.waiting_for_code)
async def process_promo_code(message: Message, state: FSMContext, db: Database):
    """Обработка введенного промокода"""
    code = message.text.strip().upper()
    
    # Получаем промокод из БД
    promo = await db.get_promocode(code)
    
    if not promo:
        await message.answer("❌ Промокод не найден. Проверьте правильность ввода.")
        return
    
    # Проверки
    if not promo.is_active:
        await message.answer("❌ Этот промокод больше не активен.")
        return
    
    if promo.valid_until and promo.valid_until < datetime.utcnow():
        await message.answer("❌ Срок действия промокода истек.")
        return
    
    if promo.max_uses and promo.used_count >= promo.max_uses:
        await message.answer("❌ Достигнут лимит использований промокода.")
        return
    
    # Активируем промокод
    user = await db.get_user(message.from_user.id)
    
    if promo.discount_type == "free":
        # Бесплатная подписка
        expires_at = datetime.utcnow() + timedelta(days=30 * promo.duration_months)
        
        await db.add_subscription(
            user_id=user.id,
            duration_months=promo.duration_months,
            expires_at=expires_at,
            activated_by="promo",
            promocode=code
        )
        
        await db.use_promocode(code)
        
        # Генерируем инвайт-ссылку (TODO: реальная генерация)
        invite_link = "https://t.me/+EXAMPLE_INVITE_LINK"
        
        await message.answer(
            f"🎉 <b>Промокод активирован!</b>\n\n"
            f"Вам предоставлена бесплатная подписка на {promo.duration_months} мес.\n"
            f"Действует до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n\n"
            f"🔗 Ссылка для входа в канал:\n{invite_link}",
            parse_mode="HTML"
        )
        
    else:
        # Скидка на покупку
        await message.answer(
            f"✅ Промокод <b>{code}</b> применен!\n\n"
            f"Скидка: <b>{promo.discount_value}{'%' if promo.discount_type == 'percent' else ' ₽'}</b>\n"
            f"Теперь выберите тариф для покупки со скидкой:",
            reply_markup=kb.subscription_plans_kb(),
            parse_mode="HTML"
        )
        
        # Сохраняем промокод в состоянии для применения при оплате
        await state.update_data(promo_code=code)
    
    await state.clear()


@router.message(F.text == "ℹ️ О клубе")
async def about_club(message: Message):
    """Информация о клубе"""
    await message.answer(
        "🎨 <b>О Shmukler Art Club</b>\n\n"
        "Shmukler art club — это закрытое сообщество, созданное Олей Шмуклер "
        "и командой культурного центра Артишок.\n\n"
        "<b>Наша миссия:</b>\n"
        "Объединить людей, которые хотят видеть, понимать, чувствовать искусство глубже, "
        "стремиться к новым визуальным и смысловым открытиям.\n\n"
        "<b>Основательница:</b>\n"
        "Оля Шмуклер — искусствовед, куратор, лектор с многолетним опытом в арт-индустрии.\n\n"
        "Подробнее: https://artishokcenter.ru/shmuklerartclub",
        parse_mode="HTML"
    )


@router.message(F.text == "📞 Поддержка")
async def support(message: Message):
    """Контакты поддержки"""
    await message.answer(
        "📞 <b>Связаться с нами:</b>\n\n"
        "Если у вас возникли вопросы или проблемы, "
        "напишите нам — мы всегда на связи!",
        reply_markup=kb.support_kb(),
        parse_mode="HTML"
    )


@router.message(F.text == "👨‍💼 Админ-панель")
async def open_admin_panel(message: Message):
    """Открытие админ-панели по кнопке"""
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    
    if message.from_user.id not in admin_ids:
        await message.answer("❌ У вас нет доступа к админ-панели.")
        return
    
    from bot.keyboards import admin as admin_kb
    await message.answer(
        "👨‍💼 <b>Админ-панель Shmukler Art Club</b>\n\n"
        "Выберите действие:",
        reply_markup=admin_kb.admin_menu_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    is_admin = callback.from_user.id in admin_ids
    
    await callback.message.delete()
    await callback.message.answer(
        "Главное меню:",
        reply_markup=kb.main_menu_kb(is_admin=is_admin)
    )
    await callback.answer()


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена действия"""
    await state.clear()
    await callback.message.delete()
    await callback.answer("Действие отменено")
