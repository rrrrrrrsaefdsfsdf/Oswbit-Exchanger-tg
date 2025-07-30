# handlers/operator.py
import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.models import Database
from keyboards.inline import Keyboards
from keyboards.reply import ReplyKeyboards
from config import config

logger = logging.getLogger(__name__)
router = Router()

class OperatorStates(StatesGroup):
    waiting_for_note = State()

# Инициализация базы данных
db = Database(config.DATABASE_URL)

# Список операторов (ID пользователей)
OPERATORS = [
    config.ADMIN_USER_ID
]

def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id == config.ADMIN_USER_ID

def is_operator(user_id: int) -> bool:
    """Проверка прав оператора (только для работы с заявками)"""
    return user_id in OPERATORS

def is_operator_chat(chat_id: int) -> bool:
    """Проверка операторского чата"""
    return chat_id == config.OPERATOR_CHAT_ID

def can_handle_orders(user_id: int, chat_id: int) -> bool:
    """Может ли пользователь обрабатывать заявки в этом чате"""
    return (is_operator(user_id) or is_admin(user_id)) and is_operator_chat(chat_id)

async def notify_operators_paid_order(bot, order: dict, received_sum: float = None):
    """Уведомление операторов об оплаченной заявке"""
    try:
        display_id = order.get('personal_id', order['id'])
        if not received_sum:
            received_sum = order.get('total_amount', 0)
        
        text = (
            f"💰 <b>ЗАЯВКА ОПЛАЧЕНА</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Клиент ID: {order.get('user_id', 'N/A')}\n"
            f"💵 Получено: {received_sum:,.0f} ₽\n"
            f"💰 Сумма заявки: {order['total_amount']:,.0f} ₽\n"
            f"₿ К отправке: {order['amount_btc']:.8f} BTC\n"
            f"📍 Адрес: <code>{order['btc_address']}</code>\n\n"
            f"⏰ Создана: {order.get('created_at', 'N/A')}\n"
            f"📱 Тип: {order.get('payment_type', 'N/A')}\n\n"
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
        builder.row(
            InlineKeyboardButton(
                text="📋 Детали заявки", 
                callback_data=f"op_details_{order['id']}"
            )
        )
        
        # Отправляем в операторский чат
        await bot.send_message(
            config.OPERATOR_CHAT_ID,
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Notify operators paid order error: {e}")

async def notify_operators_error_order(bot, order: dict, error_message: str):
    """Уведомление операторов об ошибке в заявке"""
    try:
        display_id = order.get('personal_id', order['id'])
        
        text = (
            f"⚠️ <b>ОШИБКА В ЗАЯВКЕ</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Клиент ID: {order.get('user_id', 'N/A')}\n"
            f"💰 Сумма: {order['total_amount']:,.0f} ₽\n"
            f"❌ Ошибка: {error_message}\n\n"
            f"⏰ Создана: {order.get('created_at', 'N/A')}\n\n"
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
        builder.row(
            InlineKeyboardButton(
                text="📝 Заметка", 
                callback_data=f"op_note_{order['id']}"
            )
        )
        
        await bot.send_message(
            config.OPERATOR_CHAT_ID,
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Notify operators error order error: {e}")

async def notify_client_payment_received(bot, order: dict):
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
        
        await bot.send_message(
            order['user_id'],
            text,
            parse_mode="HTML",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
    except Exception as e:
        logger.error(f"Notify client payment received error: {e}")

async def notify_client_order_cancelled(bot, order: dict):
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
        
        await bot.send_message(
            order['user_id'],
            text,
            parse_mode="HTML",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
    except Exception as e:
        logger.error(f"Notify client order cancelled error: {e}")

async def notify_client_order_completed(bot, order: dict):
    """Уведомление клиента о завершении заявки"""
    try:
        display_id = order.get('personal_id', order['id'])
        
        text = (
            f"🎉 <b>Заявка завершена!</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"₿ Отправлено: {order['amount_btc']:.8f} BTC\n"
            f"📍 На адрес: <code>{order['btc_address']}</code>\n\n"
            f"✅ <b>Bitcoin успешно отправлен!</b>\n"
            f"Проверьте ваш кошелек.\n\n"
            f"Спасибо за использование {config.EXCHANGE_NAME}!"
        )
        
        await bot.send_message(
            order['user_id'],
            text,
            parse_mode="HTML",
            reply_markup=ReplyKeyboards.main_menu()
        )
        
    except Exception as e:
        logger.error(f"Notify client order completed error: {e}")

# Webhook обработчик для OnlyPays
async def process_onlypays_webhook(webhook_data: dict, bot):
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
            await notify_operators_paid_order(bot, order, received_sum)
            
            # Уведомляем клиента
            await notify_client_payment_received(bot, order)
            
        elif status == 'cancelled':
            # Заявка отменена
            await db.update_order(order['id'], status='cancelled')
            
            # Уведомляем клиента об отмене
            await notify_client_order_cancelled(bot, order)
            
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")

# Обработчики для операторов (ТОЛЬКО для работы с заявками)
@router.callback_query(F.data.startswith("op_sent_"))
async def operator_sent_handler(callback: CallbackQuery):
    """Оператор отправил Bitcoin"""
    if not can_handle_orders(callback.from_user.id, callback.message.chat.id):
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return
    
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
        await notify_client_order_completed(callback.bot, order)
        
        # Обновляем сообщение оператора
        await callback.message.edit_text(
            f"✅ <b>ЗАЯВКА ЗАВЕРШЕНА</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Обработал: @{callback.from_user.username or callback.from_user.first_name}\n"
            f"⏰ Завершена: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
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
    if not can_handle_orders(callback.from_user.id, callback.message.chat.id):
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return
    
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
        
        # Обновляем сообщение
        await callback.message.edit_text(
            f"⚠️ <b>ЗАЯВКА ОТМЕЧЕНА КАК ПРОБЛЕМНАЯ</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Оператор: @{callback.from_user.username or callback.from_user.first_name}\n"
            f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📨 Администратор уведомлен",
            parse_mode="HTML"
        )
        
        await callback.answer("⚠️ Заявка отмечена как проблемная")
        
    except Exception as e:
        logger.error(f"Operator problem handler error: {e}")
        await callback.answer("❌ Ошибка")

@router.callback_query(F.data.startswith("op_note_"))
async def operator_note_handler(callback: CallbackQuery, state: FSMContext):
    """Оператор добавляет заметку"""
    if not can_handle_orders(callback.from_user.id, callback.message.chat.id):
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    
    await state.update_data(
        note_order_id=order_id, 
        note_message_id=callback.message.message_id,
        note_user_id=callback.from_user.id
    )
    
    await callback.bot.send_message(
        callback.message.chat.id,
        f"📝 <b>Добавить заметку к заявке #{order_id}</b>\n\n"
        f"Напишите заметку в следующем сообщении:",
        parse_mode="HTML"
    )
    
    await state.set_state(OperatorStates.waiting_for_note)
    await callback.answer()

@router.callback_query(F.data.startswith("op_details_"))
async def operator_details_handler(callback: CallbackQuery):
    """Показать детали заявки"""
    if not can_handle_orders(callback.from_user.id, callback.message.chat.id):
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    
    try:
        order = await db.get_order(order_id)
        if not order:
            await callback.answer("Заявка не найдена")
            return
        
        display_id = order.get('personal_id', order_id)
        
        text = (
            f"📋 <b>ДЕТАЛИ ЗАЯВКИ #{display_id}</b>\n\n"
            f"🆔 ID: {order['id']}\n"
            f"🔗 OnlyPays ID: {order.get('onlypays_id', 'N/A')}\n"
            f"👤 Пользователь: {order['user_id']}\n"
            f"💰 Сумма: {order['total_amount']:,.0f} ₽\n"
            f"₿ Bitcoin: {order['amount_btc']:.8f} BTC\n"
            f"💱 Курс: {order.get('rate', 0):,.0f} ₽\n"
            f"💳 Комиссия процессинга: {order.get('processing_fee', 0):,.0f} ₽\n"
            f"🏛 Комиссия сервиса: {order.get('admin_fee', 0):,.0f} ₽\n"
            f"📱 Тип оплаты: {order.get('payment_type', 'N/A')}\n"
            f"📊 Статус: {order.get('status', 'N/A')}\n"
            f"⏰ Создана: {order.get('created_at', 'N/A')}\n\n"
            f"₿ <b>BTC адрес:</b>\n<code>{order.get('btc_address', 'N/A')}</code>\n\n"
            f"💳 <b>Реквизиты:</b>\n{order.get('requisites', 'N/A')}"
        )
        
        await callback.answer()
        await callback.bot.send_message(
            callback.message.chat.id,
            text,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Operator details handler error: {e}")
        await callback.answer("❌ Ошибка получения деталей")

@router.callback_query(F.data.startswith("op_cancel_"))
async def operator_cancel_handler(callback: CallbackQuery):
    """Оператор отменяет заявку"""
    if not can_handle_orders(callback.from_user.id, callback.message.chat.id):
        await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    
    try:
        await db.update_order(order_id, status='cancelled')
        
        order = await db.get_order(order_id)
        if order:
            await notify_client_order_cancelled(callback.bot, order)
        
        display_id = order.get('personal_id', order_id) if order else order_id
        
        await callback.message.edit_text(
            f"❌ <b>ЗАЯВКА ОТМЕНЕНА</b>\n\n"
            f"🆔 Заявка: #{display_id}\n"
            f"👤 Отменил: @{callback.from_user.username or callback.from_user.first_name}\n"
            f"⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"📨 Клиент уведомлен",
            parse_mode="HTML"
        )
        
        await callback.answer("❌ Заявка отменена")
        
    except Exception as e:
        logger.error(f"Operator cancel handler error: {e}")
        await callback.answer("❌ Ошибка отмены заявки")

@router.message(OperatorStates.waiting_for_note)
async def note_input_handler(message: Message, state: FSMContext):
    """Обработка ввода заметки оператором"""
    data = await state.get_data()
    order_id = data.get('note_order_id')
    note_user_id = data.get('note_user_id')
    
    # Проверяем, что заметку пишет тот же пользователь
    if note_user_id != message.from_user.id or not can_handle_orders(message.from_user.id, message.chat.id):
        return
    
    if not order_id:
        await message.answer("Ошибка: ID заявки не найден")
        await state.clear()
        return
    
    note_text = message.text
    
    try:
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
        
        # Сохраняем заметку в БД (если есть такое поле)
        try:
            await db.update_order(order_id, operator_notes=note_text)
        except:
            pass  # Если поля нет в БД, просто пропускаем
        
        await message.answer(
            f"✅ Заметка к заявке #{display_id} добавлена!",
            parse_mode="HTML"
        )
        
        # Удаляем сообщение с заметкой для чистоты чата
        try:
            await message.delete()
        except:
            pass
        
    except Exception as e:
        logger.error(f"Note handler error: {e}")
        await message.answer("❌ Ошибка сохранения заметки")
    
    await state.clear()

# Функция для добавления оператора (только для админа)
async def add_operator(user_id: int) -> bool:
    """Добавить оператора (только админ может вызвать)"""
    if user_id not in OPERATORS:
        OPERATORS.append(user_id)
        logger.info(f"Added operator: {user_id}")
        return True
    return False

async def remove_operator(user_id: int) -> bool:
    """Удалить оператора (только админ может вызвать)"""
    if user_id in OPERATORS:
        OPERATORS.remove(user_id)
        logger.info(f"Removed operator: {user_id}")
        return True
    return False

def get_operators_list() -> list:
    """Получить список операторов"""
    return OPERATORS.copy()




