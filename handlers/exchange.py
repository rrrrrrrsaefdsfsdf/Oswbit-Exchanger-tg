import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.reply import ReplyKeyboards
from keyboards.inline import InlineKeyboards
from utils.bitcoin import BitcoinAPI
from database.models import Database
from api.onlypays import onlypays_api
from config import config

logger = logging.getLogger(__name__)
router = Router()

class ExchangeStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_address = State()
    waiting_for_card_details = State()

db = Database(config.DATABASE_URL)

@router.message(F.text == "Купить")
async def buy_crypto_handler(message: Message, state: FSMContext):
    await state.clear()
    
    text = "Выберите что хотите купить."
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.buy_crypto_selection()
    )

@router.callback_query(F.data.startswith("buy_"))
async def buy_crypto_selected(callback: CallbackQuery, state: FSMContext):
    if callback.data == "buy_main_menu":
        await callback.bot.send_message(
            callback.message.chat.id,
            "🎯 Главное меню:",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    crypto = callback.data.replace("buy_", "").upper()
    
    await state.update_data(
        operation="buy",
        crypto=crypto,
        direction="rub_to_crypto"
    )
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    text = (
        f"💰 <b>Покупка Bitcoin</b>\n\n"
        f"📊 Текущий курс: {btc_rate:,.0f} ₽\n\n"
        f"Введите сумму в рублях или выберите из предложенных:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboards.amount_input_keyboard(crypto.lower(), "rub_to_crypto"),
        parse_mode="HTML"
    )
    
    await state.set_state(ExchangeStates.waiting_for_amount)

@router.message(F.text == "Продать")
async def sell_crypto_handler(message: Message, state: FSMContext):
    await state.clear()
    
    text = "Выберите что хотите продать."
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.sell_crypto_selection()
    )

@router.callback_query(F.data.startswith("sell_"))
async def sell_crypto_selected(callback: CallbackQuery, state: FSMContext):
    if callback.data == "sell_main_menu":
        await callback.bot.send_message(
            callback.message.chat.id,
            "🎯 Главное меню:",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    crypto = callback.data.replace("sell_", "").upper()
    
    await state.update_data(
        operation="sell",
        crypto=crypto,
        direction="crypto_to_rub"
    )
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    text = (
        f"💸 <b>Продажа Bitcoin</b>\n\n"
        f"📊 Текущий курс: {btc_rate:,.0f} ₽\n\n"
        f"Введите количество BTC или выберите из предложенных:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboards.amount_input_keyboard(crypto.lower(), "crypto_to_rub"),
        parse_mode="HTML"
    )
    
    await state.set_state(ExchangeStates.waiting_for_amount)

@router.callback_query(F.data.startswith("amount_"))
async def amount_selected(callback: CallbackQuery, state: FSMContext):
    if "back" in callback.data:
        data = await state.get_data()
        operation = data.get("operation", "buy")
        if operation == "buy":
            await buy_crypto_handler(callback.message, state)
        else:
            await sell_crypto_handler(callback.message, state)
        return
    
    if "main_menu" in callback.data:
        await callback.bot.send_message(
            callback.message.chat.id,
            "🎯 Главное меню:",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    parts = callback.data.split("_")
    crypto = parts[1].upper()
    direction = "_".join(parts[2:-1])
    amount = float(parts[-1])
    
    await process_amount_and_show_calculation(callback, state, crypto, direction, amount)

@router.message(ExchangeStates.waiting_for_amount)
async def manual_amount_input(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(' ', '').replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
        
        data = await state.get_data()
        crypto = data.get("crypto")
        direction = data.get("direction")
        
        await process_amount_and_show_calculation_for_message(
            message, state, crypto, direction, amount
        )
        
    except ValueError:
        await message.answer("❌ Введите корректное число")

async def process_amount_and_show_calculation(callback: CallbackQuery, state: FSMContext, 
                                            crypto: str, direction: str, amount: float):
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if direction == "rub_to_crypto":
        rub_amount = amount
        crypto_amount = BitcoinAPI.calculate_btc_amount(rub_amount, btc_rate)
    else:
        crypto_amount = amount
        rub_amount = crypto_amount * btc_rate
    
    admin_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    processing_fee = rub_amount * 0.10
    admin_fee = (rub_amount + processing_fee) * (admin_percentage / 100)
    total_amount = rub_amount + processing_fee + admin_fee
    
    await state.update_data(
        crypto=crypto,
        direction=direction,
        rub_amount=rub_amount,
        crypto_amount=crypto_amount,
        rate=btc_rate,
        processing_fee=processing_fee,
        admin_fee=admin_fee,
        total_amount=total_amount
    )
    
    operation_text = "Покупка" if direction == "rub_to_crypto" else "Продажа"
    
    text = (
        f"📊 <b>{operation_text} Bitcoin</b>\n\n"
        f"💱 Курс: {btc_rate:,.0f} ₽\n"
        f"💰 Сумма: {rub_amount:,.0f} ₽\n"
        f"₿ Получите: {crypto_amount:.8f} BTC\n\n"
        f"💳 Комиссия процессинга: {processing_fee:,.0f} ₽\n"
        f"🏛 Комиссия сервиса: {admin_fee:,.0f} ₽\n"
        f"💸 <b>Итого: {total_amount:,.0f} ₽</b>\n\n"
        f"Выберите способ {'оплаты' if direction == 'rub_to_crypto' else 'получения'}:"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboards.payment_methods_for_crypto(
            crypto.lower(), str(amount), direction
        ),
        parse_mode="HTML"
    )

async def process_amount_and_show_calculation_for_message(message: Message, state: FSMContext,
                                                        crypto: str, direction: str, amount: float):
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if direction == "rub_to_crypto":
        rub_amount = amount
        crypto_amount = BitcoinAPI.calculate_btc_amount(rub_amount, btc_rate)
    else:
        crypto_amount = amount
        rub_amount = crypto_amount * btc_rate
    
    admin_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    processing_fee = rub_amount * 0.10
    admin_fee = (rub_amount + processing_fee) * (admin_percentage / 100)
    total_amount = rub_amount + processing_fee + admin_fee
    
    await state.update_data(
        crypto=crypto,
        direction=direction,
        rub_amount=rub_amount,
        crypto_amount=crypto_amount,
        rate=btc_rate,
        processing_fee=processing_fee,
        admin_fee=admin_fee,
        total_amount=total_amount
    )
    
    operation_text = "Покупка" if direction == "rub_to_crypto" else "Продажа"
    
    text = (
        f"📊 <b>{operation_text} Bitcoin</b>\n\n"
        f"💱 Курс: {btc_rate:,.0f} ₽\n"
        f"💰 Сумма: {rub_amount:,.0f} ₽\n"
        f"₿ Получите: {crypto_amount:.8f} BTC\n\n"
        f"💳 Комиссия процессинга: {processing_fee:,.0f} ₽\n"
        f"🏛 Комиссия сервиса: {admin_fee:,.0f} ₽\n"
        f"💸 <b>Итого: {total_amount:,.0f} ₽</b>\n\n"
        f"Выберите способ {'оплаты' if direction == 'rub_to_crypto' else 'получения'}:"
    )
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.payment_methods_for_crypto(
            crypto.lower(), str(amount), direction
        ),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("payment_"))
async def payment_method_selected(callback: CallbackQuery, state: FSMContext):
    if "back" in callback.data:
        data = await state.get_data()
        crypto = data.get("crypto")
        direction = data.get("direction")
        
        await callback.message.edit_text(
            f"Введите {'сумму в рублях' if direction == 'rub_to_crypto' else 'количество BTC'}:",
            reply_markup=InlineKeyboards.amount_input_keyboard(crypto.lower(), direction)
        )
        return
    
    if "main_menu" in callback.data:
        await callback.bot.send_message(
            callback.message.chat.id,
            "🎯 Главное меню:",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    parts = callback.data.split("_")
    crypto = parts[1].upper()
    direction = "_".join(parts[2:-2])
    amount = parts[-2]
    payment_type = parts[-1]
    
    await state.update_data(payment_type=payment_type)
    
    if direction == "rub_to_crypto":
        text = (
            f"₿ <b>Введите ваш Bitcoin адрес</b>\n\n"
            f"Убедитесь, что адрес указан правильно!\n"
            f"Bitcoin будет отправлен именно на этот адрес."
        )
    else:
        text = (
            f"💳 <b>Введите реквизиты для получения</b>\n\n"
            f"{'Номер карты' if payment_type == 'card' else 'Номер телефона для СБП'}:"
        )
    
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.set_state(ExchangeStates.waiting_for_address)

@router.message(ExchangeStates.waiting_for_address)
async def address_input_handler(message: Message, state: FSMContext):
    address = message.text.strip()
    
    data = await state.get_data()
    direction = data.get("direction")
    crypto = data.get("crypto")
    
    if direction == "rub_to_crypto":
        if not BitcoinAPI.validate_btc_address(address):
            await message.answer("❌ Некорректный Bitcoin адрес. Попробуйте еще раз.")
            return
    else:
        if len(address) < 10:
            await message.answer("❌ Некорректные реквизиты. Попробуйте еще раз.")
            return
    
    await state.update_data(address=address)
    
    order_id = await create_exchange_order(message.from_user.id, state)
    
    await show_order_confirmation(message, state, order_id)

async def create_exchange_order(user_id: int, state: FSMContext) -> int:
    data = await state.get_data()
    
    order_id = await db.create_order(
        user_id=user_id,
        amount_rub=data["rub_amount"],
        amount_btc=data["crypto_amount"],
        btc_address=data["address"],
        rate=data["rate"],
        processing_fee=data["processing_fee"],
        admin_fee=data["admin_fee"],
        total_amount=data["total_amount"],
        payment_type=data["payment_type"]
    )
    
    return order_id

async def show_order_confirmation(message: Message, state: FSMContext, order_id: int):
    data = await state.get_data()
    
    operation_text = "Покупка" if data["direction"] == "rub_to_crypto" else "Продажа"
    
    text = (
        f"✅ <b>Заявка #{order_id} создана!</b>\n\n"
        f"📋 <b>{operation_text} Bitcoin</b>\n"
        f"💰 Сумма: {data['rub_amount']:,.0f} ₽\n"
        f"₿ Количество: {data['crypto_amount']:.8f} BTC\n"
        f"💸 К {'оплате' if data['direction'] == 'rub_to_crypto' else 'получению'}: {data['total_amount']:,.0f} ₽\n\n"
        f"📝 Адрес/Реквизиты:\n<code>{data['address']}</code>\n\n"
        f"Подтвердите создание заявки:"
    )
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.order_confirmation(order_id),
        parse_mode="HTML"
    )
    
    await state.clear()

@router.callback_query(F.data.startswith(("confirm_order_", "cancel_order_")))
async def order_confirmation_handler(callback: CallbackQuery):
    action = "confirm" if callback.data.startswith("confirm") else "cancel"
    order_id = int(callback.data.split("_")[-1])
    
    if action == "confirm":
        order = await db.get_order(order_id)
        
        text = (
            f"✅ <b>Заявка #{order_id} подтверждена!</b>\n\n"
            f"Ожидайте реквизиты для оплаты.\n"
            f"Время обработки: 5-15 минут."
        )
    else:
        await db.update_order(order_id, status='cancelled')
        text = f"❌ Заявка #{order_id} отменена."
    
    await callback.message.edit_text(text, parse_mode="HTML")
    
    import asyncio
    await asyncio.sleep(3)
    await callback.bot.send_message(
        callback.message.chat.id,
        "🎯 Главное меню:",
        reply_markup=ReplyKeyboards.main_menu()
    )