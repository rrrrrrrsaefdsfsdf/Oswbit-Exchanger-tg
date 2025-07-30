# handlers/operator.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.models import Database
from keyboards.inline import Keyboards
from config import config

logger = logging.getLogger(__name__)
router = Router()

class OperatorStates(StatesGroup):
    waiting_for_note = State()

# Инициализация базы данных
db = Database(config.DATABASE_URL)

def is_operator(user_id: int) -> bool:
    """Проверка прав оператора (синхронная версия)"""
    return user_id == config.OPERATOR_CHAT_ID or user_id == config.ADMIN_CHAT_ID

async def notify_operators(bot, order_id: int, is_problematic: bool = False):
    """Уведомление операторов о новой заявке"""
    order = await db.get_order(order_id)
    if not order:
        return
    
    user = await db.get_user(order['user_id'])
    
    status_text = "⚠️ ПРОБЛЕМНАЯ ЗАЯВКА" if is_problematic else "💳 Новая заявка"
    
    text = (
        f"{status_text}\n\n"
        f"🆔 Заявка: #{order_id}\n"
        f"👤 Пользователь: {user['first_name']} (@{user['username']})\n"
        f"💰 Сумма: {order['total_amount']:,.2f} ₽\n"
        f"₿ Bitcoin: {order['amount_btc']:.8f} BTC\n"
        f"📱 Тип оплаты: {order['payment_type']}\n\n"
        f"📋 Реквизиты:\n{order['requisites']}\n\n"
        f"₿ BTC адрес: <code>{order['btc_address']}</code>"
    )
    
    try:
        await bot.send_message(
            config.OPERATOR_CHAT_ID,
            text,
            reply_markup=Keyboards.operator_panel(order_id),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify operators: {e}")

@router.callback_query(F.data.startswith("op_paid_"))
async def operator_paid_handler(callback: CallbackQuery):
    if not is_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    order_id = int(callback.data.split("_")[2])
    
    await db.update_order(order_id, status='finished')
    
    order = await db.get_order(order_id)
    user = await db.get_user(order['user_id'])
    
    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            order['user_id'],
            f"✅ <b>Заявка #{order_id} выполнена!</b>\n\n"
            f"Ваш платеж подтвержден.\n"
            f"Bitcoin отправлен на указанный адрес.\n"
            f"Время поступления: до 1 часа.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {order['user_id']}: {e}")
    
    # Обновляем статистику пользователя
    await db.update_user(
        order['user_id'],
        total_operations=user['total_operations'] + 1,
        total_amount=user['total_amount'] + order['total_amount']
    )
    
    await callback.message.edit_text(
        f"✅ Заявка #{order_id} отмечена как оплаченная\n\n"
        f"Пользователь уведомлен о завершении операции.",
        reply_markup=None
    )

@router.callback_query(F.data.startswith("op_not_paid_"))
async def operator_not_paid_handler(callback: CallbackQuery):
    if not is_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    order_id = int(callback.data.split("_")[3])
    
    await db.update_order(order_id, status='cancelled')
    
    order = await db.get_order(order_id)
    
    # Уведомляем пользователя
    try:
        await callback.bot.send_message(
            order['user_id'],
            f"❌ <b>Заявка #{order_id} отменена</b>\n\n"
            f"Платеж не был получен в установленное время.\n"
            f"Если вы считаете это ошибкой, обратитесь в поддержку.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user {order['user_id']}: {e}")
    
    await callback.message.edit_text(
        f"❌ Заявка #{order_id} отмечена как неоплаченная\n\n"
        f"Пользователь уведомлен об отмене.",
        reply_markup=None
    )

@router.callback_query(F.data.startswith("op_problem_"))
async def operator_problem_handler(callback: CallbackQuery):
    if not is_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    order_id = int(callback.data.split("_")[2])
    
    await db.update_order(order_id, is_problematic=True)
    
    await callback.message.edit_text(
        f"⚠️ Заявка #{order_id} отмечена как проблемная\n\n"
        f"Требуется ручная обработка.",
        reply_markup=Keyboards.operator_panel(order_id)
    )

@router.callback_query(F.data.startswith("op_note_"))
async def operator_note_handler(callback: CallbackQuery, state: FSMContext):
    if not is_operator(callback.from_user.id):
        await callback.answer("❌ Нет доступа")
        return
    
    order_id = int(callback.data.split("_")[2])
    
    await state.update_data(order_id=order_id)
    
    await callback.message.edit_text(
        f"📝 Добавление заметки к заявке #{order_id}\n\n"
        f"Введите текст заметки:",
    )
    await state.set_state(OperatorStates.waiting_for_note)

@router.message(OperatorStates.waiting_for_note)
async def process_note(message: Message, state: FSMContext):
    if not is_operator(message.from_user.id):
        return
    
    data = await state.get_data()
    order_id = data['order_id']
    
    await db.update_order(order_id, operator_notes=message.text)
    
    await message.answer(
        f"✅ Заметка к заявке #{order_id} добавлена:\n\n"
        f"{message.text}"
    )
    await state.clear()