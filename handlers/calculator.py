import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards.reply import ReplyKeyboards
from keyboards.inline import InlineKeyboards
from utils.bitcoin import BitcoinAPI
from database.models import Database
from config import config

logger = logging.getLogger(__name__)
router = Router()

class CalculatorStates(StatesGroup):
    waiting_for_amount = State()

db = Database(config.DATABASE_URL)

@router.message(F.text == "Калькулятор валют")
async def calculator_main_handler(message: Message, state: FSMContext):
    await state.clear()
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    text = (
        f"<b>Выберите направление:</b>"
    )
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.currency_calculator(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "calc_main_menu")
async def calculator_back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    text = (
        f"<b>Выберите направление:</b>"
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboards.currency_calculator(),
            parse_mode="HTML"
        )
    except:
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            reply_markup=InlineKeyboards.currency_calculator(),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("calc_") & ~F.data.in_(["calc_main_menu", "calc_back"]))
async def calculator_pair_selected(callback: CallbackQuery, state: FSMContext):
    if "amount" in callback.data:
        return await calculator_amount_selected(callback, state)
    if "reverse" in callback.data:
        return await calculator_reverse(callback, state)
    if "refresh" in callback.data:
        return await calculator_refresh(callback, state)
    if "recalc" in callback.data:
        return await calculator_recalculate(callback, state)
    
    pair = callback.data.replace("calc_", "")
    from_currency, to_currency = pair.split("_")
    
    await state.update_data(
        pair=pair,
        from_currency=from_currency,
        to_currency=to_currency
    )
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if from_currency.upper() == 'RUB':
        rate_text = f"1 RUB = {1/btc_rate:.8f} BTC"
        currency_symbol = "₽"
        amounts = ["1000", "5000", "10000", "50000", "100000", "500000"]
    else:
        rate_text = f"1 BTC = {btc_rate:,.0f} RUB"
        currency_symbol = "BTC"
        amounts = ["0.001", "0.01", "0.1", "0.5", "1", "5"]
    
    text = (
        f"💱 <b>{from_currency.upper()}-{to_currency.upper()}</b>\n\n"
        f"📊 Курс: {rate_text}\n\n"
        f"💰 <b>Выберите сумму {currency_symbol}:</b>\n"
        f"Или введите произвольную сумму"
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboards.calculator_amount_input(pair),
            parse_mode="HTML"
        )
    except:
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            reply_markup=InlineKeyboards.calculator_amount_input(pair),
            parse_mode="HTML"
        )
    
    await state.set_state(CalculatorStates.waiting_for_amount)

async def calculator_amount_selected(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    pair = f"{parts[2]}_{parts[3]}"
    amount = float(parts[4])
    
    await calculate_and_show_result(callback, state, pair, amount)

@router.message(CalculatorStates.waiting_for_amount)
async def calculator_manual_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(' ', '').replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
        
        data = await state.get_data()
        pair = data.get('pair')
        
        await calculate_and_show_result_for_message(message, state, pair, amount)
        
    except ValueError:
        await message.answer("❌ Введите корректное число")

async def calculate_and_show_result(callback: CallbackQuery, state: FSMContext, pair: str, amount: float):
    from_currency, to_currency = pair.split("_")
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if from_currency.upper() == 'RUB':
        rub_amount = amount
        btc_amount = BitcoinAPI.calculate_btc_amount(rub_amount, btc_rate)
    else:
        btc_amount = amount
        rub_amount = btc_amount * btc_rate
    
    admin_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    
    processing_fee = rub_amount * 0.10
    admin_fee = (rub_amount + processing_fee) * (admin_percentage / 100)
    total_fee = processing_fee + admin_fee
    
    if from_currency.upper() == 'RUB':
        from_formatted = f"{rub_amount:,.0f} ₽"
        to_formatted = f"{btc_amount:.8f} BTC"
    else:
        from_formatted = f"{btc_amount:.8f} BTC"
        to_formatted = f"{rub_amount:,.0f} ₽"
    
    text = (
        f"🧮 <b>Результат расчета</b>\n\n"
        f"💱 <b>{from_currency.upper()} → {to_currency.upper()}</b>\n\n"
        f"📊 {from_formatted} = <b>{to_formatted}</b>\n\n"
        f"💡 <b>Для обмена потребуется:</b>\n"
        f"💳 Комиссия процессинга: {processing_fee:,.0f} ₽\n"
        f"🏛 Комиссия сервиса: {admin_fee:,.0f} ₽\n"
        f"💸 Итого доплата: <b>{total_fee:,.0f} ₽</b>"
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboards.calculator_result(pair, str(amount)),
            parse_mode="HTML"
        )
    except:
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            reply_markup=InlineKeyboards.calculator_result(pair, str(amount)),
            parse_mode="HTML"
        )

async def calculate_and_show_result_for_message(message: Message, state: FSMContext, pair: str, amount: float):
    from_currency, to_currency = pair.split("_")
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if from_currency.upper() == 'RUB':
        rub_amount = amount
        btc_amount = BitcoinAPI.calculate_btc_amount(rub_amount, btc_rate)
    else:
        btc_amount = amount
        rub_amount = btc_amount * btc_rate
    
    admin_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    
    processing_fee = rub_amount * 0.10
    admin_fee = (rub_amount + processing_fee) * (admin_percentage / 100)
    total_fee = processing_fee + admin_fee
    
    if from_currency.upper() == 'RUB':
        from_formatted = f"{rub_amount:,.0f} ₽"
        to_formatted = f"{btc_amount:.8f} BTC"
    else:
        from_formatted = f"{btc_amount:.8f} BTC"
        to_formatted = f"{rub_amount:,.0f} ₽"
    
    text = (
        f"🧮 <b>Результат расчета</b>\n\n"
        f"💱 <b>{from_currency.upper()} → {to_currency.upper()}</b>\n\n"
        f"📊 {from_formatted} = <b>{to_formatted}</b>\n\n"
        f"💡 <b>Для обмена потребуется:</b>\n"
        f"💳 Комиссия процессинга: {processing_fee:,.0f} ₽\n"
        f"🏛 Комиссия сервиса: {admin_fee:,.0f} ₽\n"
        f"💸 Итого доплата: <b>{total_fee:,.0f} ₽</b>"
    )
    
    await message.answer(
        text,
        reply_markup=InlineKeyboards.calculator_result(pair, str(amount)),
        parse_mode="HTML"
    )

async def calculator_reverse(callback: CallbackQuery, state: FSMContext):
    pair = callback.data.replace("calc_reverse_", "")
    from_currency, to_currency = pair.split("_")
    
    new_pair = f"{to_currency}_{from_currency}"
    
    await state.update_data(
        pair=new_pair,
        from_currency=to_currency,
        to_currency=from_currency
    )
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if to_currency.upper() == 'RUB':
        rate_text = f"1 RUB = {1/btc_rate:.8f} BTC"
        currency_symbol = "₽"
    else:
        rate_text = f"1 BTC = {btc_rate:,.0f} RUB"
        currency_symbol = "BTC"
    
    text = (
        f"💱 <b>{to_currency.upper()}-{from_currency.upper()}</b>\n\n"
        f"📊 Курс: {rate_text}\n\n"
        f"💰 <b>Выберите сумму {currency_symbol}:</b>\n"
        f"Или введите произвольную сумму"
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboards.calculator_amount_input(new_pair),
            parse_mode="HTML"
        )
    except:
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            reply_markup=InlineKeyboards.calculator_amount_input(new_pair),
            parse_mode="HTML"
        )
    
    await state.set_state(CalculatorStates.waiting_for_amount)

async def calculator_refresh(callback: CallbackQuery, state: FSMContext):
    await callback.answer("🔄 Курс обновлен!")
    await calculator_back_to_main(callback, state)

async def calculator_recalculate(callback: CallbackQuery, state: FSMContext):
    pair = callback.data.replace("calc_recalc_", "")
    from_currency, to_currency = pair.split("_")
    
    await state.update_data(
        pair=pair,
        from_currency=from_currency,
        to_currency=to_currency
    )
    
    btc_rate = await BitcoinAPI.get_btc_rate()
    
    if from_currency.upper() == 'RUB':
        rate_text = f"1 RUB = {1/btc_rate:.8f} BTC"
        currency_symbol = "₽"
    else:
        rate_text = f"1 BTC = {btc_rate:,.0f} RUB"
        currency_symbol = "BTC"
    
    text = (
        f"💱 <b>{from_currency.upper()}-{to_currency.upper()}</b>\n\n"
        f"📊 Курс: {rate_text}\n\n"
        f"💰 <b>Выберите сумму {currency_symbol}:</b>\n"
        f"Или введите произвольную сумму"
    )
    
    try:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboards.calculator_amount_input(pair),
            parse_mode="HTML"
        )
    except:
        await callback.message.delete()
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            reply_markup=InlineKeyboards.calculator_amount_input(pair),
            parse_mode="HTML"
        )
    
    await state.set_state(CalculatorStates.waiting_for_amount)

@router.callback_query(F.data == "calc_back")
async def calculator_back(callback: CallbackQuery, state: FSMContext):
    await calculator_back_to_main(callback, state)