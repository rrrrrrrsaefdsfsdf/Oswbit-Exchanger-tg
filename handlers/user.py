import logging
import aiohttp
import asyncio
from datetime import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import Database
from keyboards.reply import ReplyKeyboards
from keyboards.inline import InlineKeyboards
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.bitcoin import BitcoinAPI
from utils.captcha import CaptchaGenerator
from config import config
from handlers.operator import (
    process_onlypays_webhook,
    notify_operators_paid_order,
    notify_operators_error_order,
    notify_client_payment_received,
    notify_client_order_cancelled
)



logger = logging.getLogger(__name__)
router = Router()

class OnlyPaysAPI:
    def __init__(self, api_id: str, secret_key: str, payment_key: str = None):
        self.api_id = api_id
        self.secret_key = secret_key
        self.payment_key = payment_key
        self.base_url = "https://onlypays.net"
    
    async def create_order(self, amount: int, payment_type: str, personal_id: str = None, trans: bool = False):
        url = f"{self.base_url}/get_requisite"
        data = {
            "api_id": self.api_id,
            "secret_key": self.secret_key,
            "amount_rub": amount,
            "payment_type": payment_type
        }
        
        if personal_id:
            data["personal_id"] = personal_id
        
        if trans:
            data["trans"] = True
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    logger.info(f"OnlyPays create_order response: {result}")
                    return result
        except Exception as e:
            logger.error(f"OnlyPays create_order error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_order_status(self, order_id: str):
        url = f"{self.base_url}/get_status"
        data = {
            "api_id": self.api_id,
            "secret_key": self.secret_key,
            "id": order_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    logger.info(f"OnlyPays get_status response: {result}")
                    return result
        except Exception as e:
            logger.error(f"OnlyPays get_status error: {e}")
            return {"success": False, "error": str(e)}
    
    async def cancel_order(self, order_id: str):
        url = f"{self.base_url}/cancel_order"
        data = {
            "api_id": self.api_id,
            "secret_key": self.secret_key,
            "id": order_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    logger.info(f"OnlyPays cancel_order response: {result}")
                    return result
        except Exception as e:
            logger.error(f"OnlyPays cancel_order error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_balance(self):
        if not self.payment_key:
            return {"success": False, "error": "Payment key not provided"}
        
        url = f"{self.base_url}/get_balance"
        data = {
            "api_id": self.api_id,
            "payment_key": self.payment_key
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    logger.info(f"OnlyPays get_balance response: {result}")
                    return result
        except Exception as e:
            logger.error(f"OnlyPays get_balance error: {e}")
            return {"success": False, "error": str(e)}
    
    async def create_payout(self, payout_type: str, amount: int, requisite: str, bank: str, personal_id: str = None):
        if not self.payment_key:
            return {"success": False, "error": "Payment key not provided"}
        
        url = f"{self.base_url}/create_payout"
        data = {
            "api_id": self.api_id,
            "payment_key": self.payment_key,
            "type": payout_type,
            "amount": amount,
            "requisite": requisite,
            "bank": bank
        }
        
        if personal_id:
            data["personal_id"] = personal_id
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    logger.info(f"OnlyPays create_payout response: {result}")
                    return result
        except Exception as e:
            logger.error(f"OnlyPays create_payout error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_payout_status(self, payout_id: str):
        if not self.payment_key:
            return {"success": False, "error": "Payment key not provided"}
        
        url = f"{self.base_url}/payout_status"
        data = {
            "api_id": self.api_id,
            "payment_key": self.payment_key,
            "id": payout_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    logger.info(f"OnlyPays payout_status response: {result}")
                    return result
        except Exception as e:
            logger.error(f"OnlyPays payout_status error: {e}")
            return {"success": False, "error": str(e)}

onlypays_api = OnlyPaysAPI(
    api_id=config.ONLYPAYS_API_ID,
    secret_key=config.ONLYPAYS_SECRET_KEY,
    payment_key=getattr(config, 'ONLYPAYS_PAYMENT_KEY', None)
)




async def process_onlypays_webhook(webhook_data: dict):
    """Обработка webhook от OnlyPays"""
    try:
        order_id = webhook_data.get('personal_id')  # Наш внутренний ID заявки
        onlypays_id = webhook_data.get('id')
        status = webhook_data.get('status')
        received_sum = webhook_data.get('received_sum')
        
        if not order_id:
            logger.error(f"Webhook without personal_id: {webhook_data}")
            return
        
        # Получаем заявку из БД
        order = await db.get_order(int(order_id))
        if not order:
            logger.error(f"Order not found: {order_id}")
            return
        
        if status == 'finished':
            # Заявка оплачена клиентом
            await db.update_order(
                order['id'], 
                status='paid_by_client',
                received_sum=received_sum
            )
            
            # Уведомляем операторов
            await notify_operators_paid_order(order, received_sum)
            
            # Уведомляем клиента
            await notify_client_payment_received(order)
            
        elif status == 'cancelled':
            # Заявка отменена
            await db.update_order(order['id'], status='cancelled')
            
            # Можно уведомить клиента об отмене
            await notify_client_order_cancelled(order)
            
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")

async def notify_operators_paid_order(order: dict, received_sum: float):
    """Уведомление операторов об оплаченной заявке"""
    try:
        display_id = order.get('personal_id', order['id'])
        
        text = (
            f"💰 <b>ЗАЯВКА ОПЛАЧЕНА</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Клиент: {order.get('user_id', 'N/A')}\n"
            f"💵 Получено: {received_sum:,.0f} ₽\n"
            f"💰 Сумма заявки: {order['total_amount']:,.0f} ₽\n"
            f"₿ К отправке: {order['amount_btc']:.8f} BTC\n"
            f"📍 Адрес: <code>{order['btc_address']}</code>\n\n"
            f"⏰ Время: {order['created_at']}\n\n"
            f"🎯 <b>Требуется отправка Bitcoin!</b>"
        )
        
        # Кнопки для операторов
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ Отправил Bitcoin", 
                callback_data=f"op_sent_{order['id']}"
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="⚠️ Проблема", 
                callback_data=f"op_problem_{order['id']}"
            ),
            InlineKeyboardButton(
                text="📝 Заметка", 
                callback_data=f"op_note_{order['id']}"
            )
        )
        
        # Отправляем в операторский чат
        from main import bot  # Импортируем бот из главного файла
        await bot.send_message(
            config.OPERATOR_CHAT_ID,
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Notify operators error: {e}")

async def notify_operators_error_order(order: dict, error_message: str):
    """Уведомление операторов об ошибке в заявке"""
    try:
        display_id = order.get('personal_id', order['id'])
        
        text = (
            f"⚠️ <b>ОШИБКА В ЗАЯВКЕ</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Клиент: {order.get('user_id', 'N/A')}\n"
            f"💰 Сумма: {order['total_amount']:,.0f} ₽\n"
            f"❌ Ошибка: {error_message}\n\n"
            f"⏰ Время: {order['created_at']}\n\n"
            f"🔧 <b>Требуется вмешательство!</b>"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="🔧 Обработать", 
                callback_data=f"op_handle_{order['id']}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить", 
                callback_data=f"op_cancel_{order['id']}"
            )
        )
        
        from main import bot
        await bot.send_message(
            config.OPERATOR_CHAT_ID,
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Notify operators error: {e}")

async def notify_client_payment_received(order: dict):
    """Уведомление клиента о получении платежа"""
    try:
        display_id = order.get('personal_id', order['id'])
        
        text = (
            f"✅ <b>Платеж получен!</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"💰 Сумма: {order['total_amount']:,.0f} ₽\n"
            f"₿ К получению: {order['amount_btc']:.8f} BTC\n\n"
            f"🔄 <b>Обрабатываем заявку...</b>\n"
            f"Bitcoin будет отправлен на ваш адрес в течение 1 часа.\n\n"
            f"📱 Вы получите уведомление о завершении."
        )
        
        from main import bot
        await bot.send_message(
            order['user_id'],
            text,
            parse_mode="HTML",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
    except Exception as e:
        logger.error(f"Notify client error: {e}")

async def notify_client_order_cancelled(order: dict):
    """Уведомление клиента об отмене заявки"""
    try:
        display_id = order.get('personal_id', order['id'])
        
        text = (
            f"❌ <b>Заявка отменена</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"💰 Сумма: {order['total_amount']:,.0f} ₽\n\n"
            f"Причина: Превышено время ожидания оплаты\n\n"
            f"Создайте новую заявку для обмена."
        )
        
        from main import bot
        await bot.send_message(
            order['user_id'],
            text,
            parse_mode="HTML",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
    except Exception as e:
        logger.error(f"Notify client cancelled error: {e}")









class ExchangeStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_btc_address = State()
    waiting_for_captcha = State()
    waiting_for_contact = State()
    waiting_for_address = State()
    waiting_for_card_details = State()
    waiting_for_note = State() 

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

@router.callback_query(F.data.startswith("sell_"))
async def sell_crypto_selected(callback: CallbackQuery, state: FSMContext):
    if callback.data == "sell_main_menu":
        await show_main_menu(callback, is_callback=True)
        return
    
    crypto = callback.data.replace("sell_", "").upper()
    
    if crypto == "BTC":
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
            await buy_handler(callback.message, state)
        else:
            await sell_handler(callback.message, state)
        return
    
    if "main_menu" in callback.data:
        await show_main_menu(callback, is_callback=True)
        return
    
    parts = callback.data.split("_")
    crypto = parts[1].upper()
    direction = "_".join(parts[2:-1])
    amount = float(parts[-1])
    
    await process_amount_and_show_calculation(callback, state, crypto, direction, amount)

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

@router.message(ExchangeStates.waiting_for_amount)
async def manual_amount_input(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        await show_main_menu(message)
        return
    
    data = await state.get_data()
    
    if not data.get("direction"):
        min_amount = await db.get_setting("min_amount", config.MIN_AMOUNT)
        max_amount = await db.get_setting("max_amount", config.MAX_AMOUNT)
        
        try:
            exchange_type = data.get('exchange_type')
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
        return
    
    try:
        amount = float(message.text.replace(' ', '').replace(',', '.'))
        if amount <= 0:
            await message.answer("❌ Сумма должна быть больше 0")
            return
        
        crypto = data.get("crypto")
        direction = data.get("direction")
        
        await process_amount_and_show_calculation_for_message(
            message, state, crypto, direction, amount
        )
        
    except (ValueError, TypeError):
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
        await show_main_menu(callback, is_callback=True)
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
    
    # Получаем заявку из БД для получения personal_id
    order = await db.get_order(order_id)
    display_id = order.get('personal_id', order_id) if order else order_id
    
    operation_text = "Покупка" if data["direction"] == "rub_to_crypto" else "Продажа"
    
    text = (
        f"✅ <b>Заявка создана!</b>\n\n"  # Используем display_id
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
async def order_confirmation_handler(callback: CallbackQuery, state: FSMContext):
    action = "confirm" if callback.data.startswith("confirm") else "cancel"
    order_id = int(callback.data.split("_")[-1])
    
    if action == "confirm":
        order = await db.get_order(order_id)
        if not order:
            await callback.message.edit_text("❌ Заявка не найдена")
            return
        
        # Используем personal_id для отображения
        display_id = order.get('personal_id', order_id)
        
        if order['total_amount'] and order['payment_type']:
            api_response = await onlypays_api.create_order(
                amount=int(order['total_amount']),
                payment_type=order['payment_type'],
                personal_id=str(order_id)  # Передаем внутренний ID как personal_id
            )
            
            if not api_response.get('success'):
                await callback.message.edit_text(
                    f"❌ Ошибка создания заявки: {api_response.get('error', 'Неизвестная ошибка')}\n\n"
                    "Попробуйте позже или обратитесь в поддержку."
                )
                
                await asyncio.sleep(3)
                await callback.bot.send_message(
                    callback.message.chat.id,
                    "🎯 Главное меню:",
                    reply_markup=ReplyKeyboards.main_menu()
                )
                return
            
            payment_data = api_response['data']
            requisites_text = ""
            if order['payment_type'] == "card":
                requisites_text = (
                    f"💳 Карта: {payment_data['requisite']}\n"
                    f"👤 Получатель: {payment_data['owner']}\n"
                    f"🏛 Банк: {payment_data['bank']}"
                )
            else:
                requisites_text = (
                    f"📱 Телефон: {payment_data['requisite']}\n"
                    f"👤 Получатель: {payment_data['owner']}\n"
                    f"🏛 Банк: {payment_data['bank']}"
                )
            
            # Сохраняем OnlyPays ID как personal_id
            await db.update_order(
                order_id,
                onlypays_id=api_response['data']['id'],
                requisites=requisites_text,
                status='waiting',
                personal_id=api_response['data']['id']  # Добавляем эту строку
            )
            
            text = (
                f"💳 <b>Заявка #{api_response['data']['id']} подтверждена!</b>\n\n"
                f"💰 К оплате: <b>{order['total_amount']:,.0f} ₽</b>\n\n"
                f"📋 <b>Реквизиты для оплаты:</b>\n"
                f"{requisites_text}\n\n"
                f"⚠️ <b>Важно:</b>\n"
                f"• Переведите точную сумму\n"
                f"• После оплаты ожидайте подтверждения\n"
                f"• Bitcoin будет отправлен автоматически\n\n"
                f"⏰ Заявка действительна 30 минут"
            )
        else:
            text = (
                f"✅ <b>Заявка #{display_id} подтверждена!</b>\n\n"
                f"Ожидайте реквизиты для оплаты.\n"
                f"Время обработки: 5-15 минут."
            )
    else:
        await db.update_order(order_id, status='cancelled')
        order = await db.get_order(order_id)
        display_id = order.get('personal_id', order_id) if order else order_id
        text = f"❌ Заявка #{display_id} отменена."
    
    await callback.message.edit_text(text, parse_mode="HTML")
    
    await asyncio.sleep(3)
    await callback.bot.send_message(
        callback.message.chat.id,
        "🎯 Главное меню:",
        reply_markup=ReplyKeyboards.main_menu()
    )

@router.message(F.text.in_(["💳 Банковская карта", "📱 СБП"]))
async def payment_method_handler(message: Message, state: FSMContext):
    payment_type = "card" if "карта" in message.text else "sbp"
    data = await state.get_data()
    
    order_id = await db.create_order(
        user_id=message.from_user.id,
        amount_rub=data['rub_amount'],
        amount_btc=data['btc_amount'],
        btc_address=data.get('btc_address', data.get('address', '')),
        rate=data['btc_rate'],
        processing_fee=data['processing_fee'],
        admin_fee=data['admin_fee'],
        total_amount=data['total_amount'],
        payment_type=payment_type
    )
    
    api_response = await onlypays_api.create_order(
        amount=int(data['total_amount']),
        payment_type=payment_type,
        personal_id=str(order_id)
    )
    
    if not api_response.get('success'):
        await message.answer(
            f"❌ Ошибка создания заявки: {api_response.get('error', 'Неизвестная ошибка')}\n\n"
            "Попробуйте позже или обратитесь в поддержку.",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    payment_data = api_response['data']
    requisites_text = ""
    if payment_type == "card":
        requisites_text = (
            f"💳 Карта: {payment_data['requisite']}\n"
            f"👤 Получатель: {payment_data['owner']}\n"
            f"🏛 Банк: {payment_data['bank']}"
        )
    else:
        requisites_text = (
            f"📱 Телефон: {payment_data['requisite']}\n"
            f"👤 Получатель: {payment_data['owner']}\n"
            f"🏛 Банк: {payment_data['bank']}"
        )
    
    # Обновляем заявку с personal_id от OnlyPays
    await db.update_order(
        order_id,
        onlypays_id=api_response['data']['id'],
        requisites=requisites_text,
        personal_id=api_response['data']['id'] 
    )
    
    # Используем personal_id в тексте
    text = (
        f"💳 <b>Заявка #{api_response['data']['id']} создана!</b>\n\n"  # Используем OnlyPays ID
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
        
        if api_response.get('success'):
            status_data = api_response['data']
            if status_data['status'] == 'finished':
                # Обновляем статус и вызываем webhook обработчик
                await process_onlypays_webhook({
                    'id': order['onlypays_id'],
                    'status': 'finished',
                    'personal_id': str(order['id']),
                    'received_sum': status_data.get('received_sum', order['total_amount'])
                }, message.bot)  # Добавляем bot как параметр
                
                await message.answer(
                    f"✅ <b>Заявка #{order.get('personal_id', order['id'])} оплачена!</b>\n\n"
                    f"Платеж получен и обрабатывается.\n"
                    f"Bitcoin будет отправлен в течение 1 часа.",
                    reply_markup=ReplyKeyboards.main_menu(),
                    parse_mode="HTML"
                )
            elif status_data['status'] == 'cancelled':
                await db.update_order(order['id'], status='cancelled')
                await message.answer(
                    f"❌ Заявка #{order.get('personal_id', order['id'])} отменена.\n\n"
                    f"Создайте новую заявку для обмена.",
                    reply_markup=ReplyKeyboards.main_menu(),
                    parse_mode="HTML"
                )
            else:
                await message.answer(
                    f"⏳ Заявка #{order.get('personal_id', order['id'])} в обработке\n\n"
                    f"Ожидаем поступления платежа...\n"
                    f"Заявка действительна 30 минут.",
                    reply_markup=ReplyKeyboards.order_menu()
                )
        else:
            await message.answer(
                f"❌ Ошибка проверки статуса: {api_response.get('error', 'Неизвестная ошибка')}\n"
                f"Попробуйте позже или обратитесь в поддержку.",
                reply_markup=ReplyKeyboards.main_menu()
            )
    else:
        status_text = {
            'waiting': '⏳ В обработке',
            'paid_by_client': '💰 Оплачена, обрабатывается',
            'completed': '✅ Завершена',
            'cancelled': '❌ Отменена',
            'problem': '⚠️ Проблемная'
        }.get(order['status'], f"❓ {order['status']}")
        
        await message.answer(
            f"📋 Статус заявки #{order.get('personal_id', order['id'])}: {status_text}",
            reply_markup=ReplyKeyboards.main_menu()
        )

@router.message(F.text.in_(["✅ Подтвердить заявку", "❌ Отменить заявку"]))
async def confirm_cancel_order_handler(message: Message):
    orders = await db.get_user_orders(message.from_user.id, 1)
    
    if not orders:
        await message.answer(
            "У вас нет активных заявок",
            reply_markup=ReplyKeyboards.main_menu()
        )
        return
    
    order = orders[0]
    display_id = order.get('personal_id', order['id'])  # Получаем display_id
    
    if "Отменить" in message.text:
        if order['status'] == 'waiting' and order['onlypays_id']:
            api_response = await onlypays_api.cancel_order(order['onlypays_id'])
            
            if api_response.get('success'):
                await db.update_order(order['id'], status='cancelled')
                await message.answer(
                    f"❌ Заявка #{display_id} отменена.\n\n"  # Используем display_id
                    "Создайте новую заявку для обмена.",
                    reply_markup=ReplyKeyboards.main_menu()
                )
            else:
                await message.answer(
                    f"❌ Ошибка отмены заявки: {api_response.get('error', 'Неизвестная ошибка')}\n"
                    "Попробуйте позже или обратитесь в поддержку.",
                    reply_markup=ReplyKeyboards.main_menu()
                )
        else:
            await message.answer(
                "Невозможно отменить эту заявку",
                reply_markup=ReplyKeyboards.main_menu()
            )
    else:
        await message.answer(
            "⏳ Проверяю статус заявки...",
            reply_markup=ReplyKeyboards.order_menu()
        )
        await check_status_handler(message)

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
    try:
        user = await db.get_user(message.from_user.id)
        if not user:
            # Если пользователь не найден, создаем его
            await db.add_user(
                message.from_user.id,
                message.from_user.username,
                message.from_user.first_name,
                message.from_user.last_name
            )
            user = await db.get_user(message.from_user.id)
        
        if not user:
            await message.answer(
                "❌ Ошибка доступа к базе данных.\n"
                "Попробуйте выполнить /start",
                reply_markup=ReplyKeyboards.main_menu()
            )
            return
        
        # Получаем статистику рефералов
        try:
            stats = await db.get_referral_stats(message.from_user.id)
        except:
            # Если метод не работает, создаем базовую статистику
            stats = {
                'referral_count': 0,
                'referral_balance': 0
            }
        
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
            InlineKeyboardButton(
                text="🏠 Главная", 
                callback_data="referral_main_menu"
            )
        )
        
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Referral handler error: {e}")
        await message.answer(
            "❌ Произошла ошибка при загрузке реферальной программы.\n"
            "Попробуйте позже или выполните /start",
            reply_markup=ReplyKeyboards.main_menu()
        )









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
            
            # Используем personal_id если есть, иначе внутренний ID
            display_id = order.get('personal_id', order['id'])
            
            text += (
                f"{status_emoji} Заявка #{display_id}\n"
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

@router.message(ExchangeStates.waiting_for_contact)
async def contact_handler(message: Message, state: FSMContext):
    if message.text == "◀️ Главное меню":
        await state.clear()
        await show_main_menu(message)
        return
    
    user_id = message.from_user.id
    
    try:
        last_review = await db.get_last_review_time(user_id)
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








# Обработчики для операторов
@router.callback_query(F.data.startswith("op_sent_"))
async def operator_sent_handler(callback: CallbackQuery):
    """Оператор отправил Bitcoin"""
    order_id = int(callback.data.split("_")[-1])
    
    try:
        # Обновляем статус заявки
        await db.update_order(order_id, status='completed')
        
        # Получаем заявку
        order = await db.get_order(order_id)
        if not order:
            await callback.answer("Заявка не найдена")
            return
        
        display_id = order.get('personal_id', order_id)
        
        # Уведомляем клиента о завершении
        text_client = (
            f"🎉 <b>Заявка завершена!</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"₿ Отправлено: {order['amount_btc']:.8f} BTC\n"
            f"📍 На адрес: <code>{order['btc_address']}</code>\n\n"
            f"✅ <b>Bitcoin успешно отправлен!</b>\n"
            f"Проверьте ваш кошелек.\n\n"
            f"Спасибо за использование {config.EXCHANGE_NAME}!"
        )
        
        await callback.bot.send_message(
            order['user_id'],
            text_client,
            parse_mode="HTML",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
        # Обновляем сообщение оператора
        await callback.message.edit_text(
            f"✅ <b>ЗАЯВКА ЗАВЕРШЕНА</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Обработал: @{callback.from_user.username or callback.from_user.first_name}\n"
            f"⏰ Время завершения: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"💎 Bitcoin отправлен клиенту!",
            parse_mode="HTML"
        )
        
        await callback.answer("✅ Заявка отмечена как завершенная")
        
    except Exception as e:
        logger.error(f"Operator sent handler error: {e}")
        await callback.answer("❌ Ошибка обновления статуса")

@router.callback_query(F.data.startswith("op_problem_"))
async def operator_problem_handler(callback: CallbackQuery):
    """Оператор сообщает о проблеме"""
    order_id = int(callback.data.split("_")[-1])
    
    try:
        # Обновляем статус заявки
        await db.update_order(order_id, status='problem')
        
        order = await db.get_order(order_id)
        display_id = order.get('personal_id', order_id) if order else order_id
        
        # Уведомляем в админский чат
        admin_text = (
            f"⚠️ <b>ПРОБЛЕМНАЯ ЗАЯВКА</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Оператор: @{callback.from_user.username or callback.from_user.first_name}\n"
            f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"❗ Требуется вмешательство администратора"
        )
        
        await callback.bot.send_message(
            config.ADMIN_CHAT_ID,
            admin_text,
            parse_mode="HTML"
        )
        
        await callback.answer("⚠️ Заявка отмечена как проблемная")
        
    except Exception as e:
        logger.error(f"Operator problem handler error: {e}")
        await callback.answer("❌ Ошибка")

@router.callback_query(F.data.startswith("op_note_"))
async def operator_note_handler(callback: CallbackQuery, state: FSMContext):
    """Оператор добавляет заметку"""
    order_id = int(callback.data.split("_")[-1])
    
    await state.update_data(note_order_id=order_id)
    
    await callback.message.edit_text(
        f"📝 <b>Добавить заметку к заявке #{order_id}</b>\n\n"
        f"Напишите заметку в следующем сообщении:",
        parse_mode="HTML"
    )
    
    await state.set_state(ExchangeStates.waiting_for_note)
    await callback.answer()

@router.message(ExchangeStates.waiting_for_note)
async def note_input_handler(message: Message, state: FSMContext):
    """Обработка ввода заметки оператором"""
    data = await state.get_data()
    order_id = data.get('note_order_id')
    
    if not order_id:
        await message.answer("Ошибка: ID заявки не найден")
        await state.clear()
        return
    
    note_text = message.text
    
    try:
        # Сохраняем заметку в БД (можно добавить поле notes в таблицу orders)
        order = await db.get_order(order_id)
        display_id = order.get('personal_id', order_id) if order else order_id
        
        # Отправляем заметку в админский чат
        admin_text = (
            f"📝 <b>ЗАМЕТКА К ЗАЯВКЕ</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Оператор: @{message.from_user.username or message.from_user.first_name}\n"
            f"📝 Заметка: {note_text}\n"
            f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        
        await message.bot.send_message(
            config.ADMIN_CHAT_ID,
            admin_text,
            parse_mode="HTML"
        )
        
        await message.answer(
            f"✅ Заметка к заявке #{display_id} добавлена!",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
    except Exception as e:
        logger.error(f"Note handler error: {e}")
        await message.answer("❌ Ошибка сохранения заметки")
    
    await state.clear()
















@router.message()
async def unknown_handler(message: Message):
    await message.answer(
        "❓ Я не понимаю эту команду.\n\n"
        "Используйте кнопки меню для навигации.",
        reply_markup=ReplyKeyboards.main_menu()
    )