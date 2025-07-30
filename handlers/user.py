import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import ReplyKeyboards
from keyboards.inline import InlineKeyboards
from utils.bitcoin import BitcoinAPI
from utils.captcha import CaptchaGenerator
from api.onlypays import onlypays_api
from config import config

logger = logging.getLogger(__name__)
router = Router()

class ExchangeStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_btc_address = State()
    waiting_for_captcha = State()
    waiting_for_contact = State()

db = Database(config.DATABASE_URL)

async def show_main_menu(message_or_callback, is_callback=False):
    default_welcome = (
        f"🎉 Приветствуем вас, дорогие друзья 🎉\n"
        f"💰 {config.EXCHANGE_NAME} 💰\n\n"
        f"🟡 BTC - BITCOIN\n\n"
        f"🔥 НАДЁЖНЫЙ, КАЧЕСТВЕННЫЙ И МОМЕНТАЛЬНЫЙ ОБМЕН КРИПТОВАЛЮТ 🔥\n\n"
        f"⚡️ САМАЯ НИЗКАЯ КОМИССИЯ\n"
        f"🤖 Моментальный автоматический обмен 24/7\n"
        f"✅ Быстро / Надёжно / Качественно\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤝 По вопросам сотрудничества:\n"
        f"💬 НАШ ЧАТ ➖ {config.SUPPORT_CHAT}\n\n"
        f"🆘 Наша тех.поддержка:\n"
        f"👤 Менеджер ➖ {config.SUPPORT_MANAGER}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📢 НОВОСТНОЙ КАНАЛ ➖ {config.NEWS_CHANNEL}\n"
        f"📝 КАНАЛ ОТЗЫВЫ ➖ {config.REVIEWS_CHANNEL}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎁 БОНУСЫ\n"
        f"💎 Каждый 10 обмен до 6000₽ в боте БЕЗ КОМИССИИ\n\n"
        f"Выберите действие в меню:"
    )
    
    welcome_msg = await db.get_setting("welcome_message", default_welcome)
    
    if is_callback:
        await message_or_callback.bot.send_message(
            message_or_callback.message.chat.id,
            welcome_msg,
            reply_markup=ReplyKeyboards.main_menu()
        )
    else:
        await message_or_callback.answer(welcome_msg, reply_markup=ReplyKeyboards.main_menu())

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    
    user = await db.get_user(message.from_user.id)
    if not user:
        captcha_enabled = await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED)
        if captcha_enabled:
            image_buffer, answer = CaptchaGenerator.generate_image_captcha()
            await db.create_captcha_session(message.from_user.id, answer.upper())
            
            captcha_photo = BufferedInputFile(
                image_buffer.read(),
                filename="captcha.png"
            )
            
            await message.answer_photo(
                photo=captcha_photo,
                caption="🤖 Добро пожаловать! Введите код с картинки:",
                reply_markup=ReplyKeyboards.back_to_main()
            )
            await state.set_state(ExchangeStates.waiting_for_captcha)
            return
        else:
            await db.add_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name
            )
    
    await show_main_menu(message)



@router.message(ExchangeStates.waiting_for_captcha)
async def captcha_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        await message.answer("Для использования бота пройдите проверку через /start")
        return
        
    session = await db.get_captcha_session(message.from_user.id)
    if not session:
        await message.answer("Ошибка сессии. Попробуйте /start")
        return
    
    user_answer = message.text.upper().strip()
    correct_answer = session['answer'].upper().strip()
    
    if user_answer == correct_answer:
        await db.delete_captcha_session(message.from_user.id)
        
        await db.add_user(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name,
            message.from_user.last_name
        )
        
        data = await state.get_data()
        referral_user_id = data.get('referral_user_id')
        
        if referral_user_id and referral_user_id != message.from_user.id:
            await db.update_user(message.from_user.id, referred_by=referral_user_id)
            await db.update_referral_count(referral_user_id)
            
            try:
                await message.bot.send_message(
                    referral_user_id,
                    f"🎉 По вашей ссылке зарегистрировался новый пользователь!\n"
                    f"👤 {message.from_user.first_name}\n"
                    f"💰 Вам начислен бонус за приглашение!"
                )
            except:
                pass
        
        await message.answer("✅ Верно! Регистрация завершена.")
        await show_main_menu(message)
        await state.clear()
    else:
        attempts = session['attempts'] + 1
        if attempts >= 3:
            await db.delete_captcha_session(message.from_user.id)
            await message.answer("❌ Превышено количество попыток. Попробуйте /start снова.")
            await state.clear()
        else:
            await db.execute_query(
                'UPDATE captcha_sessions SET attempts = ? WHERE user_id = ?',
                (attempts, message.from_user.id)
            )
            
            try:
                image_buffer, answer = CaptchaGenerator.generate_simple_image_captcha()
                await db.execute_query(
                    'UPDATE captcha_sessions SET answer = ? WHERE user_id = ?',
                    (answer.upper(), message.from_user.id)
                )
                
                captcha_photo = BufferedInputFile(
                    image_buffer.read(),
                    filename="captcha.png"
                )
                
                await message.answer_photo(
                    photo=captcha_photo,
                    caption=f"❌ Неверно. Попыток осталось: {3-attempts}\nВведите код с новой картинки:"
                )
            except:
                await message.answer(f"❌ Неверно. Попыток осталось: {3-attempts}")

@router.message(F.text == "Купить")
async def buy_handler(message: Message, state: FSMContext):
    await state.clear()
    
    text = "Выберите что хотите купить."
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.buy_crypto_selection()
    )

@router.message(F.text == "Продать")
async def sell_handler(message: Message, state: FSMContext):
    await state.clear()
    
    text = "Выберите что хотите продать."
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.sell_crypto_selection()
    )




@router.callback_query(F.data.startswith("buy_"))
async def buy_crypto_selected(callback: CallbackQuery, state: FSMContext):
    if callback.data == "buy_main_menu":
        await show_main_menu(callback, is_callback=True)
        return
    
    crypto = callback.data.replace("buy_", "").upper()
    
    if crypto == "BTC":
        text = (
            f"💰 <b>Покупка Bitcoin</b>\n\n"
            f"🚧 Данная функция находится в разработке.\n"
        )
    
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад к выбору", callback_data="back_to_buy_selection"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="buy_main_menu")
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )




@router.callback_query(F.data.startswith("sell_"))
async def sell_crypto_selected(callback: CallbackQuery, state: FSMContext):
    if callback.data == "sell_main_menu":
        await show_main_menu(callback, is_callback=True)
        return
    
    crypto = callback.data.replace("sell_", "").upper()
    
    if crypto == "BTC":
        text = (
            f"💸 <b>Продажа Bitcoin</b>\n\n"
            f"🚧 Данная функция находится в разработке.\n"
        )
    
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад к выбору", callback_data="back_to_sell_selection"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="sell_main_menu")
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_buy_selection")
async def back_to_buy_selection(callback: CallbackQuery, state: FSMContext):
    text = "Выберите что хотите купить."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboards.buy_crypto_selection()
    )

@router.callback_query(F.data == "back_to_sell_selection")
async def back_to_sell_selection(callback: CallbackQuery, state: FSMContext):
    text = "Выберите что хотите продать."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboards.sell_crypto_selection()
    )

@router.message(F.text == "О сервисе ℹ️")
async def about_handler(message: Message):
    btc_rate = await BitcoinAPI.get_btc_rate()
    admin_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    
    text = (
        f"👑 {config.EXCHANGE_NAME} 👑\n\n"
        f"🔷 НАШИ ПРИОРИТЕТЫ 🔷\n"
        f"🔸 100% ГАРАНТИИ\n"
        f"🔸 БЫСТРЫЙ ОБМЕН\n"
        f"🔸 НАДЕЖНЫЙ СЕРВИС\n"
        f"🔸 КАЧЕСТВЕННАЯ РАБОТА\n"
        f"🔸 АНОНИМНЫЙ ОБМЕН\n\n"
        f"🔷 НАШИ КОНТАКТЫ 🔷\n"
        f"⚙️ ОПЕРАТОР Тех.поддержка ➖ {config.SUPPORT_MANAGER}\n"
        f"📣 НОВОСТНОЙ КАНАЛ ➖ {config.NEWS_CHANNEL}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💱 Текущий курс BTC: {btc_rate:,.0f} ₽\n"
        f"💳 Комиссия процессинга: 10%\n"
        f"🏛 Комиссия сервиса: {admin_percentage}%\n\n"
        f"💰 Лимиты: {config.MIN_AMOUNT:,} - {config.MAX_AMOUNT:,} ₽"
    )
    
    await message.answer(text, reply_markup=ReplyKeyboards.main_menu(), parse_mode="HTML")

@router.message(F.text == "Калькулятор валют")
async def calculator_handler(message: Message, state: FSMContext):
    await state.clear()
    
    text = "<b>Выберите направление:</b>"
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.currency_calculator(),
        parse_mode="HTML"
    )

@router.message(F.text == "Оставить отзыв")
async def review_handler(message: Message, state: FSMContext):
    await message.answer(
        "📝 <b>Оставить отзыв</b>\n\n"
        "Напишите ваш отзыв о работе сервиса.\n"
        "Мы ценим любую обратную связь!",
        reply_markup=ReplyKeyboards.back_to_main(),
        parse_mode="HTML"
    )
    await state.set_state(ExchangeStates.waiting_for_contact)

@router.message(F.text == "Как сделать обмен?")
async def how_to_exchange_handler(message: Message):
    text = (
        "📘 <b>Как сделать обмен?</b>\n\n"
        "📹 Видео-инструкция: \n\n"
    )
    
    await message.answer(text, reply_markup=ReplyKeyboards.main_menu(), parse_mode="HTML")

@router.message(F.text == "Друзья")
async def referral_handler(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден")
        return
    
    stats = await db.get_referral_stats(message.from_user.id)
    
    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"🎁 <b>Ваши бонусы:</b>\n"
        f"• За каждого друга: 100 ₽\n"
        f"• От каждой сделки друга: 2%\n\n"
        f"📊 <b>Ваша статистика:</b>\n"
        f"👤 Приглашено друзей: {stats['referral_count']} чел.\n"
        f"💰 Заработано бонусов: {stats['referral_balance']} ₽\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>https://t.me/{config.BOT_USERNAME}?start=r-{message.from_user.id}</code>\n\n"
        f"📤 <b>Отправьте эту ссылку друзьям!</b>\n"
        f"Когда они зарегистрируются и сделают обмен, "
        f"вы получите бонусы!"
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📤 Поделиться ссылкой", 
            url=f"https://t.me/share/url?url=https://t.me/{config.BOT_USERNAME}?start=r-{message.from_user.id}&text=Присоединяйся к лучшему криптообменнику {config.EXCHANGE_NAME}!"
        )
    )
    builder.row(
        # InlineKeyboardButton(
        #     text="💰 История бонусов", 
        #     callback_data="referral_history"
        # )
    )
    builder.row(
        InlineKeyboardButton(
            text="🏠 Главная", 
            callback_data="referral_main_menu"
        )
    )
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "referral_history")
async def referral_history_handler(callback: CallbackQuery):
    await callback.answer("История бонусов пока пуста")

@router.callback_query(F.data == "referral_main_menu")
async def referral_main_menu_handler(callback: CallbackQuery):
    await show_main_menu(callback, is_callback=True)

@router.message(F.text == "₽ → ₿ Рубли в Bitcoin")
async def rub_to_btc_handler(message: Message, state: FSMContext):
    await state.update_data(exchange_type="rub")
    
    min_amount = await db.get_setting("min_amount", config.MIN_AMOUNT)
    max_amount = await db.get_setting("max_amount", config.MAX_AMOUNT)
    
    text = (
        f"💰 <b>Обмен рублей на Bitcoin</b>\n\n"
        f"Введите сумму в рублях:\n\n"
        f"Минимум: {min_amount:,} ₽\n"
        f"Максимум: {max_amount:,} ₽"
    )
    
    await message.answer(text, reply_markup=ReplyKeyboards.back_to_main(), parse_mode="HTML")
    await state.set_state(ExchangeStates.waiting_for_amount)

@router.message(F.text == "₿ → ₽ Bitcoin в рубли")
async def btc_to_rub_handler(message: Message, state: FSMContext):
    text = (
        f"₿ <b>Обмен Bitcoin на рубли</b>\n\n"
    )
    
    await message.answer(text, reply_markup=ReplyKeyboards.main_menu(), parse_mode="HTML")

@router.message(F.text == "📊 Мои заявки")
async def my_orders_handler(message: Message):
    orders = await db.get_user_orders(message.from_user.id, 5)
    
    if not orders:
        text = (
            "📋 <b>Ваши заявки</b>\n\n"
            "У вас пока нет заявок.\n"
            "Создайте новую заявку на обмен!"
        )
    else:
        text = "📋 <b>Ваши последние заявки:</b>\n\n"
        for order in orders:
            status_emoji = "⏳" if order['status'] == 'waiting' else "✅" if order['status'] == 'finished' else "❌"
            text += (
                f"{status_emoji} Заявка #{order['id']}\n"
                f"💰 {order['total_amount']:,.0f} ₽ → {order['amount_btc']:.6f} BTC\n"
                f"📅 {order['created_at'][:16]}\n\n"
            )
    
    await message.answer(text, reply_markup=ReplyKeyboards.main_menu(), parse_mode="HTML")

@router.message(F.text == "📈 Курсы валют")
async def rates_handler(message: Message):
    try:
        btc_rate = await BitcoinAPI.get_btc_rate()
        
        text = (
            f"📈 <b>Актуальные курсы</b>\n\n"
            f"₿ Bitcoin: {btc_rate:,.0f} ₽\n\n"
            f"💡 Курсы обновляются каждые 5 минут"
        )
    except:
        text = (
            f"📈 <b>Актуальные курсы</b>\n\n"
            f"❌ Ошибка получения курса\n\n"
            f"💡 Попробуйте позже"
        )
    
    await message.answer(text, reply_markup=ReplyKeyboards.main_menu(), parse_mode="HTML")

@router.message(F.text == "◀️ Главное меню")
async def main_menu_handler(message: Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)

@router.message(F.text == "◀️ Назад")
async def back_handler(message: Message, state: FSMContext):
    await message.answer(
        "💰 <b>Покупка криптовалюты</b>\n\n"
        "Выберите направление обмена:",
        reply_markup=ReplyKeyboards.exchange_menu(),
        parse_mode="HTML"
    )

@router.message(ExchangeStates.waiting_for_amount)
async def amount_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        await show_main_menu(message)
        return
    
    data = await state.get_data()
    exchange_type = data.get('exchange_type')
    
    min_amount = await db.get_setting("min_amount", config.MIN_AMOUNT)
    max_amount = await db.get_setting("max_amount", config.MAX_AMOUNT)
    
    try:
        if exchange_type == "rub":
            amount = float(message.text.replace(' ', '').replace(',', '.'))
            if amount < min_amount or amount > max_amount:
                await message.answer(
                    f"❌ Сумма должна быть от {min_amount:,} до {max_amount:,} рублей"
                )
                return
            await state.update_data(rub_amount=amount)
        else:
            btc_amount = float(message.text.replace(',', '.'))
            if btc_amount <= 0 or btc_amount > 10:
                await message.answer("❌ Некорректное количество Bitcoin")
                return
            await state.update_data(btc_amount=btc_amount)
    except ValueError:
        await message.answer("❌ Некорректная сумма. Введите число.")
        return
    
    await message.answer(
        "₿ <b>Введите ваш Bitcoin адрес</b>\n\n"
        "Убедитесь, что адрес указан правильно!\n"
        "Bitcoin будет отправлен именно на этот адрес.",
        reply_markup=ReplyKeyboards.back_to_main(),
        parse_mode="HTML"
    )
    await state.set_state(ExchangeStates.waiting_for_btc_address)

@router.message(ExchangeStates.waiting_for_btc_address)
async def btc_address_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        await show_main_menu(message)
        return
    
    btc_address = message.text.strip()
    
    if not BitcoinAPI.validate_btc_address(btc_address):
        await message.answer("❌ Некорректный Bitcoin адрес. Попробуйте еще раз.")
        return
    
    data = await state.get_data()
    exchange_type = data['exchange_type']
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    if not btc_rate:
        await message.answer("❌ Ошибка получения курса. Попробуйте позже.")
        return
    
    if exchange_type == "rub":
        rub_amount = data['rub_amount']
        btc_amount = BitcoinAPI.calculate_btc_amount(rub_amount, btc_rate)
    else:
        btc_amount = data['btc_amount']
        rub_amount = btc_amount * btc_rate
    
    processing_percentage = 10.0
    admin_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    
    processing_fee, admin_fee, total_amount = BitcoinAPI.calculate_fees(
        rub_amount, processing_percentage, admin_percentage
    )
    
    text = (
        f"📊 <b>Предварительный расчет:</b>\n\n"
        f"💱 Курс BTC: {btc_rate:,.0f} ₽\n"
        f"💰 Сумма к обмену: {rub_amount:,.0f} ₽\n"
        f"₿ Получите Bitcoin: {btc_amount:.8f} BTC\n\n"
        f"💳 Комиссия процессинга: {processing_fee:,.0f} ₽\n"
        f"🏛 Комиссия сервиса: {admin_fee:,.0f} ₽\n"
        f"💸 <b>К оплате: {total_amount:,.0f} ₽</b>\n\n"
        f"₿ Bitcoin адрес:\n<code>{btc_address}</code>\n\n"
        f"Выберите способ оплаты:"
    )
    
    await state.update_data(
        btc_address=btc_address,
        rub_amount=rub_amount,
        btc_amount=btc_amount,
        btc_rate=btc_rate,
        processing_fee=processing_fee,
        admin_fee=admin_fee,
        total_amount=total_amount
    )
    
    await message.answer(text, reply_markup=ReplyKeyboards.payment_methods(), parse_mode="HTML")

@router.message(F.text.in_(["💳 Банковская карта", "📱 СБП"]))
async def payment_method_handler(message: Message, state: FSMContext):
    payment_type = "card" if "карта" in message.text else "sbp"
    data = await state.get_data()
    
    order_id = await db.create_order(
        user_id=message.from_user.id,
        amount_rub=data['rub_amount'],
        amount_btc=data['btc_amount'],
        btc_address=data['btc_address'],
        rate=data['btc_rate'],
        processing_fee=data['processing_fee'],
        admin_fee=data['admin_fee'],
        total_amount=data['total_amount'],
        payment_type=payment_type
    )
    
    api_response = await onlypays_api.create_order(
        amount_rub=data['total_amount'],
        payment_type=payment_type,
        personal_id=str(order_id)
    )
    
    if "error" in api_response:
        await message.answer(
            f"❌ Ошибка создания заявки: {api_response['error']}\n\n"
            "Попробуйте позже или обратитесь в поддержку.",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    requisites_text = ""
    if payment_type == "card":
        requisites_text = (
            f"💳 Карта: {api_response['card_number']}\n"
            f"👤 Получатель: {api_response['cardholder_name']}\n"
            f"🏛 Банк: {api_response['bank']}"
        )
    else:
        requisites_text = (
            f"📱 Телефон: {api_response['phone']}\n"
            f"👤 Получатель: {api_response['recipient_name']}\n"
            f"🏛 Банк: {api_response['bank']}"
        )
    
    await db.update_order(
        order_id,
        onlypays_id=api_response['id'],
        requisites=requisites_text
    )
    
    text = (
        f"💳 <b>Заявка #{order_id} создана!</b>\n\n"
        f"💰 К оплате: <b>{data['total_amount']:,.0f} ₽</b>\n\n"
        f"📋 <b>Реквизиты для оплаты:</b>\n"
        f"{requisites_text}\n\n"
        f"⚠️ <b>Важно:</b>\n"
        f"• Переведите точную сумму\n"
        f"• После оплаты ожидайте подтверждения\n"
        f"• Bitcoin будет отправлен автоматически\n\n"
        f"⏰ Заявка действительна 30 минут"
    )
    
    await message.answer(
        text, 
        reply_markup=ReplyKeyboards.order_menu(),
        parse_mode="HTML"
    )
    
    await state.clear()

@router.message(F.text == "🔄 Проверить статус")
async def check_status_handler(message: Message):
    orders = await db.get_user_orders(message.from_user.id, 1)
    
    if not orders:
        await message.answer(
            "У вас нет активных заявок",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    order = orders[0]
    
    if order['onlypays_id'] and order['status'] == 'waiting':
        api_response = await onlypays_api.get_order_status(order['onlypays_id'])
        
        if api_response.get('status') == 'finished':
            await db.update_order(order['id'], status='finished')
            await message.answer(
                f"✅ <b>Заявка #{order['id']} выполнена!</b>\n\n"
                f"Платеж получен, Bitcoin отправлен на указанный адрес.\n"
                f"Время обработки может составлять до 1 часа.",
                reply_markup=ReplyKeyboards.main_menu(),
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"⏳ Заявка #{order['id']} в обработке\n\n"
                f"Ожидаем поступления платежа...",
                reply_markup=ReplyKeyboards.order_menu()
            )
    else:
        status_text = "✅ Завершена" if order['status'] == 'finished' else "❌ Отменена" if order['status'] == 'cancelled' else "⏳ В обработке"
        await message.answer(
            f"📋 Статус заявки #{order['id']}: {status_text}",
            reply_markup=ReplyKeyboards.main_menu()
        )

@router.message(F.text.in_(["✅ Подтвердить заявку", "❌ Отменить заявку"]))
async def confirm_cancel_order_handler(message: Message):
    action = "подтверждена" if "Подтвердить" in message.text else "отменена" 
    
    await message.answer(
        f"Заявка {action}",
        reply_markup=ReplyKeyboards.main_menu()
    )










@router.message(ExchangeStates.waiting_for_contact)
async def contact_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        await show_main_menu(message)
        return
    
    user_id = message.from_user.id
    
    try:
        last_review = await db.get_last_review_time(user_id)
        # Преобразуем message.date в naive datetime
        current_time = message.date.replace(tzinfo=None)
        
        if last_review:
            time_diff = current_time - last_review
            cooldown_hours = 24
            
            if time_diff.total_seconds() < cooldown_hours * 3600:
                remaining = cooldown_hours * 3600 - time_diff.total_seconds()
                hours_left = int(remaining // 3600)
                minutes_left = int((remaining % 3600) // 60)
                
                await message.answer(
                    f"⏰ <b>Отзыв можно оставить раз в сутки</b>\n\n"
                    f"Время до следующего отзыва: {hours_left}ч {minutes_left}м",
                    reply_markup=ReplyKeyboards.main_menu(),
                    parse_mode="HTML"
                )
                await state.clear()
                return
        
        if len(message.text) < 10:
            await message.answer(
                f"📝 <b>Отзыв слишком короткий</b>\n\n"
                f"Минимум 10 символов, у вас: {len(message.text)}",
                parse_mode="HTML"
            )
            return
        
        if len(message.text) > 1000:
            await message.answer(
                f"📝 <b>Отзыв слишком длинный</b>\n\n"
                f"Максимум 1000 символов, у вас: {len(message.text)}",
                parse_mode="HTML"
            )
            return
        
        user = await db.get_user(user_id)
        review_text = (
            f"📝 <b>Новый отзыв</b>\n\n"
            f"👤 {user['first_name']} (@{user['username'] or 'нет'})\n"
            f"🆔 ID: {user_id}\n"
            f"📅 {current_time.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"💬 <b>Текст:</b>\n{message.text}"
        )
        
        review_id = await db.save_review(user_id, message.text)
        
        if config.ADMIN_CHAT_ID:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InlineKeyboardButton
            
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"review_approve_{review_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"review_reject_{review_id}")
            )
            
            await message.bot.send_message(
                config.ADMIN_CHAT_ID,
                review_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        
        await message.answer(
            "✅ <b>Спасибо за отзыв!</b>\n\n"
            "Отзыв отправлен на модерацию.",
            reply_markup=ReplyKeyboards.main_menu(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Review error: {e}")
        await message.answer(
            "❌ Ошибка отправки отзыва. Попробуйте позже.",
            reply_markup=ReplyKeyboards.main_menu()
        )
    
    await state.clear()










@router.message()
async def unknown_handler(message: Message):
    await message.answer(
        "❓ Я не понимаю эту команду.\n\n"
        "Используйте кнопки меню для навигации.",
        reply_markup=ReplyKeyboards.main_menu()
    )