import os
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.database import Database
from bot.keyboards import user as kb
from bot.utils.invite import send_invite_to_user


router = Router()


class PromoState(StatesGroup):
    """Состояния для активации промокода"""
    waiting_for_code = State()


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, state: FSMContext):
    """Обработка команды /start"""
    # Очищаем состояние (на случай если пользователь был в процессе ввода промокода)
    await state.clear()
    
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
    
    # Получаем приветственный текст из БД
    welcome_text = await db.get_text("welcome_message", 
        f"👋 Привет, {user.first_name}!\n\n"
        f"Добро пожаловать в <b>Shmukler Art Club</b>!\n\n"
        f"Выберите действие:"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=kb.main_menu_kb(is_admin=is_admin),
        parse_mode="HTML"
    )


@router.message(F.text == "💳 Купить подписку")
async def buy_subscription(message: Message, state: FSMContext, db: Database):
    """Показать тарифы"""
    await state.clear()  # Очищаем состояние, если было
    
    # Получаем текст с тарифами из БД
    plans_text = await db.get_text("subscription_plans",
        "💳 <b>Выберите тариф подписки:</b>\n\n"
        "При подписке на 3+ месяца действуют скидки!"
    )
    
    await message.answer(
        plans_text,
        reply_markup=kb.subscription_plans_kb(),
        parse_mode="HTML"
    )


@router.message(F.text == "🎁 Купить в подарок")
async def buy_gift_subscription(message: Message, state: FSMContext):
    """Показать тарифы для подарочной подписки"""
    await state.clear()
    
    await message.answer(
        "🎁 <b>Подарочная подписка</b>\n\n"
        "Выберите срок подписки для подарка.\n\n"
        "После оплаты вы получите <b>уникальный код</b>, который сможете передать получателю.\n"
        "Код активируется через бота в разделе «🎫 Промокод».",
        reply_markup=kb.gift_plans_kb(),
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


@router.callback_query(F.data.startswith("gift:"))
async def process_gift_plan_selection(callback: CallbackQuery, db: Database):
    """Обработка выбора тарифа для подарка"""
    plan = callback.data.split(":")[1]
    
    # Маппинг тарифов (такой же как для обычной подписки)
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
    
    # Генерируем уникальный order_id с пометкой GIFT
    import time
    order_id = f"gift_{user_id}_{int(time.time())}"
    
    # Создаем запись о платеже в БД (статус pending, помечаем как подарок)
    await db.add_payment(
        user_id=user_id,
        order_id=order_id,
        amount=plan_info['price'],
        subscription_plan=f"gift_{plan}",  # Помечаем как подарок
        duration_months=plan_info['months'],
        status="pending"
    )
    
    # Генерируем ссылку на оплату Prodamus
    prodamus_base_url = os.getenv("PRODAMUS_BASE_URL", "https://artclub.pay.prodamus.ru")
    payment_url = (
        f"{prodamus_base_url}?"
        f"order_id={order_id}&"
        f"customer_extra={user_id}&"
        f"products[0][price]={plan_info['price']}&"
        f"products[0][name]=Подарочная подписка {plan_info['name']}&"
        f"products[0][quantity]=1&"
        f"do=pay"
    )
    
    await callback.message.edit_text(
        f"🎁 <b>Оплата подарочной подписки</b>\n\n"
        f"Тариф: <b>{plan_info['name']}</b>\n"
        f"Стоимость: <b>{plan_info['price']} ₽</b>\n\n"
        f"После оплаты вы получите <b>уникальный промокод</b>.\n"
        f"Передайте его получателю подарка — он активирует код в боте.",
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
async def my_subscription(message: Message, db: Database, state: FSMContext):
    """Информация о подписке"""
    await state.clear()  # Очищаем состояние, если было
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


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    """Отмена текущего действия и возврат в главное меню"""
    await state.clear()
    
    # Проверяем, является ли пользователь админом
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    is_admin = callback.from_user.id in admin_ids
    
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.message.answer(
        "Главное меню:",
        reply_markup=kb.main_menu_kb(is_admin=is_admin)
    )
    await callback.answer()


@router.message(F.text == "🎫 Промокод")
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
    # Игнорируем кнопки меню - они обрабатываются своими хэндлерами
    menu_buttons = ["💳 Купить подписку", "🎁 Купить в подарок", "📊 Моя подписка", "🎫 Промокод", 
                    "ℹ️ О клубе", "📞 Поддержка", "👨‍💼 Админ-панель"]
    
    if message.text in menu_buttons:
        return  # Пропускаем, пусть обработают другие хэндлеры
    
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
    
    # Проверка для подарочных промокодов
    if promo.is_gift:
        # Проверяем по username (приоритет)
        if promo.for_username:
            user_username = message.from_user.username.lower() if message.from_user.username else None
            if user_username != promo.for_username.lower():
                await message.answer(
                    f"❌ Этот промокод предназначен для @{promo.for_username}\n\n"
                    "Подарочные промокоды можно активировать только тому, кому они предназначены."
                )
                return
        # Проверяем по ID (если username не указан)
        elif promo.for_user_id:
            if promo.for_user_id != message.from_user.id:
                await message.answer(
                    "❌ Этот промокод предназначен для другого пользователя.\n\n"
                    "Подарочные промокоды можно активировать только тому, кому они предназначены."
                )
                return
    
    # Активируем промокод
    user = await db.get_user(message.from_user.id)
    
    # Проверяем, является ли промокод бесплатным
    # Бесплатные: discount_type="free" ИЛИ percent/fixed со 100% скидкой
    is_free_promo = (
        promo.discount_type == "free" or 
        (promo.discount_type == "percent" and promo.discount_value >= 100) or
        (promo.discount_type == "fixed" and promo.discount_value >= 99999)  # Очень большая фиксированная скидка
    )
    
    if is_free_promo:
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
        
        # Отправляем инвайт-ссылку пользователю
        channel_id = int(os.getenv("MAIN_CHANNEL_ID"))
        await send_invite_to_user(message.bot, user.id, channel_id, expires_at)
        
        gift_note = ""
        if promo.is_gift:
            gift_note = "\n🎁 <i>Это подарочная подписка!</i>"
        
        await message.answer(
            f"🎉 <b>Промокод активирован!</b>{gift_note}\n\n"
            f"Вам предоставлена бесплатная подписка на {promo.duration_months} мес.\n"
            f"Действует до: <b>{expires_at.strftime('%d.%m.%Y')}</b>\n\n"
            f"Инвайт-ссылка отправлена выше ⬆️",
            parse_mode="HTML"
        )
        
        # Очищаем состояние после активации бесплатного промокода
        await state.clear()
        
    else:
        # Скидка на покупку
        # Определяем единицу измерения скидки
        if promo.discount_type in ['free', 'percent']:
            discount_display = f"{int(promo.discount_value)}%"
        else:
            discount_display = f"{int(promo.discount_value)} ₽"
        
        await message.answer(
            f"✅ Промокод <b>{code}</b> применен!\n\n"
            f"Скидка: <b>{discount_display}</b>\n"
            f"Теперь выберите тариф для покупки со скидкой:",
            reply_markup=kb.subscription_plans_kb(),
            parse_mode="HTML"
        )
        
        # Сохраняем промокод в состоянии для применения при оплате
        # НЕ очищаем state! Промокод нужен при выборе тарифа
        await state.update_data(promo_code=code)


@router.message(F.text == "ℹ️ О клубе")
async def about_club(message: Message, state: FSMContext, db: Database):
    """Информация о клубе"""
    await state.clear()  # Очищаем состояние, если было
    
    # Получаем текст из БД
    about_text = await db.get_text("about_club", 
        "🎨 <b>О Shmukler Art Club</b>\n\n"
        "Наш клуб объединяет людей, увлеченных искусством.\n\n"
        "Присоединяйтесь к нашему сообществу!"
    )
    
    await message.answer(about_text, parse_mode="HTML")


@router.message(F.text == "📞 Поддержка")
async def support(message: Message, state: FSMContext):
    """Контакты поддержки"""
    await state.clear()  # Очищаем состояние, если было
    await message.answer(
        "📞 <b>Связаться с нами:</b>\n\n"
        "Если у вас возникли вопросы или проблемы, "
        "напишите нам — мы всегда на связи!",
        reply_markup=kb.support_kb(),
        parse_mode="HTML"
    )


@router.message(F.text == "👨‍💼 Админ-панель")
async def open_admin_panel(message: Message, state: FSMContext):
    """Открытие админ-панели по кнопке"""
    await state.clear()  # Очищаем состояние, если было
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


@router.callback_query(F.data == "change_plan")
async def change_subscription_plan(callback: CallbackQuery):
    """Изменение тарифа подписки"""
    await callback.message.edit_text(
        "💳 <b>Изменение тарифа</b>\n\n"
        "Выберите новый тариф подписки.\n"
        "Изменения вступят в силу после окончания текущего периода:",
        reply_markup=kb.subscription_plans_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "auto_renewal_info")
async def show_auto_renewal_info(callback: CallbackQuery):
    """Информация об автопродлении"""
    await callback.message.edit_text(
        "ℹ️ <b>Об автоматическом продлении</b>\n\n"
        "🔄 <b>Как это работает:</b>\n"
        "• За 3 дня до окончания подписки вы получите это уведомление\n"
        "• В день истечения с вашей карты автоматически спишется оплата\n"
        "• Подписка продлится без вашего участия\n\n"
        "❌ <b>Как отменить:</b>\n"
        "Нажмите кнопку «Отменить подписку» — откроется страница управления платежами, "
        "где вы сможете отменить автопродление.\n\n"
        "🔄 <b>Как изменить тариф:</b>\n"
        "Нажмите кнопку «Изменить тариф» — выберите новый план, который начнет действовать "
        "после окончания текущего периода.\n\n"
        "💡 Если ничего не делать — подписка продлится автоматически на текущем тарифе.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "change_plan")
async def change_subscription_plan(callback: CallbackQuery):
    """Изменение тарифа подписки"""
    await callback.message.edit_text(
        "💳 <b>Изменение тарифа</b>\n\n"
        "Выберите новый тариф подписки.\n"
        "Изменения вступят в силу после окончания текущего периода:",
        reply_markup=kb.subscription_plans_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "auto_renewal_info")
async def show_auto_renewal_info(callback: CallbackQuery):
    """Информация об автопродлении"""
    await callback.message.edit_text(
        "ℹ️ <b>Об автоматическом продлении</b>\n\n"
        "🔄 <b>Как это работает:</b>\n"
        "• За 3 дня до окончания подписки вы получите уведомление\n"
        "• В день истечения с вашей карты автоматически спишется оплата\n"
        "• Подписка продлится без вашего участия\n\n"
        "❌ <b>Как отменить:</b>\n"
        "Нажмите кнопку «Отменить подписку» — откроется страница управления платежами, "
        "где вы сможете отменить автопродление.\n\n"
        "🔄 <b>Как изменить тариф:</b>\n"
        "Нажмите кнопку «Изменить тариф» — выберите новый план, который начнет действовать "
        "после окончания текущего периода.\n\n"
        "💡 Если ничего не делать — подписка продлится автоматически на текущем тарифе.",
        parse_mode="HTML"
    )
    await callback.answer()


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


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery, state: FSMContext):
    """Отмена оплаты"""
    await state.clear()
    await callback.message.edit_text("❌ Оплата отменена.")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery):
    """Пустой обработчик для кнопок-заглушек"""
    await callback.answer()
