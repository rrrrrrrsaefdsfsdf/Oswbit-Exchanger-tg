import logging
from datetime import datetime
import aiosqlite
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType
from database.models import Database
from keyboards.reply import ReplyKeyboards
from api.onlypays import onlypays_api
from config import config

logger = logging.getLogger(__name__)
router = Router()
db = Database(config.DATABASE_URL)

class AdminStates(StatesGroup):
    admin_mode = State()
    waiting_for_welcome_message = State()
    waiting_for_percentage = State()
    waiting_for_broadcast_message = State()
    waiting_for_limits = State()

def normalize_bool(value):
    if isinstance(value, str):
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    return bool(value) if value is not None else False

async def is_admin_extended(user_id: int) -> bool:
    if user_id == config.ADMIN_USER_ID:
        return True
    try:
        admin_users = await db.get_setting("admin_users", [])
        return user_id in admin_users
    except:
        return False

async def is_operator_extended(user_id: int) -> bool:
    if user_id in [config.ADMIN_USER_ID, config.OPERATOR_CHAT_ID]:
        return True
    try:
        admin_users = await db.get_setting("admin_users", [])
        operator_users = await db.get_setting("operator_users", [])
        return user_id in admin_users or user_id in operator_users
    except:
        return False

async def is_admin_in_chat(user_id: int, chat_id: int) -> bool:
    if user_id == config.ADMIN_USER_ID:
        return True
    admin_chats = [config.ADMIN_CHAT_ID, config.OPERATOR_CHAT_ID]
    admin_chats_setting = await db.get_setting("admin_chats", [])
    admin_chats.extend(admin_chats_setting)
    if chat_id not in admin_chats:
        return False
    admin_users = await db.get_setting("admin_users", [])
    operator_users = await db.get_setting("operator_users", [])
    return user_id in admin_users or user_id in operator_users

def create_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Заявки", callback_data="admin_orders"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="admin_balance")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="👥 стафф", callback_data="admin_staff")
    )
    return builder






async def update_settings_menu(callback: CallbackQuery):
    try:
        current_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
        captcha_status = normalize_bool(await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED))
        min_amount = await db.get_setting("min_amount", config.MIN_AMOUNT)
        max_amount = await db.get_setting("max_amount", config.MAX_AMOUNT)
        
        status_text = "включена ✅" if captcha_status else "отключена ❌"
        
        new_text = (
            f"⚙️ <b>Текущие настройки</b>\n\n"
            f"💸 Процент администратора: {current_percentage}%\n"
            f"🤖 Капча: {status_text}\n"
            f"💰 Лимиты: {min_amount:,} - {max_amount:,} ₽\n\n"
            f"Используйте кнопки ниже для изменения настроек:"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💸 Изменить процент", callback_data="admin_set_percentage"),
            InlineKeyboardButton(text="🤖 Переключить капчу", callback_data="admin_toggle_captcha")
        )
        builder.row(
            InlineKeyboardButton(text="💰 Изменить лимиты", callback_data="admin_set_limits"),
            InlineKeyboardButton(text="📝 Приветствие", callback_data="admin_set_welcome")
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
        
        if callback.message.text != new_text:
            await callback.message.edit_text(new_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        else:
            await callback.answer("⚙️ Настройки уже актуальны")
    except Exception as e:
        logger.error(f"Settings menu update error: {e}")
        await callback.answer("❌ Ошибка обновления настроек", show_alert=True)





@router.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext):
    if not await is_admin_in_chat(message.from_user.id, message.chat.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    await state.clear()
    
    if message.chat.type == ChatType.PRIVATE:
        await state.set_state(AdminStates.admin_mode)
        await message.answer(
            "👑 <b>Панель администратора</b>\n\nВыберите раздел для управления:",
            reply_markup=ReplyKeyboards.admin_menu(),
            parse_mode="HTML"
        )
    else:
        builder = create_admin_keyboard()
        await message.answer(
            f"👑 <b>Панель администратора</b>\n"
            f"Чат: {message.chat.title}\n"
            f"Администратор: {message.from_user.first_name}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )






@router.callback_query(F.data.startswith("admin_"))
async def admin_callback_handler(callback: CallbackQuery, state: FSMContext):
    if not await is_admin_in_chat(callback.from_user.id, callback.message.chat.id):
        await callback.answer("❌ У вас нет прав", show_alert=True)
        return
    
    action = callback.data.replace("admin_", "")
    builder = InlineKeyboardBuilder()
    
    try:
        if action == "stats":
            stats = await db.get_statistics()
            text = (
                f"📊 <b>Статистика</b>\n\n"
                f"👥 Пользователей: {stats['total_users']}\n"
                f"📋 Заявок: {stats['total_orders']}\n"
                f"✅ Завершено: {stats['completed_orders']}\n"
                f"💰 Оборот: {stats['total_volume']:,.0f} ₽\n\n"
                f"📈 Процент завершения: {stats['completion_rate']:.1f}%\n"
                f"📅 Сегодня заявок: {stats['today_orders']}\n"
                f"💵 Сегодня оборот: {stats['today_volume']:,.0f} ₽"
            )
            builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"))
            builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
            
            if callback.message.text != text:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await callback.answer("📊 Статистика уже актуальна")
        
        elif action == "balance":
            try:
                balance_data = await onlypays_api.get_balance()
                balance = balance_data.get('balance', 0)
                text = f"💰 <b>Баланс процессинга</b>\n\n💳 Доступно: {balance:,.2f} ₽"
            except Exception as e:
                text = f"❌ Ошибка получения баланса:\n{e}"
            
            builder.row(InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_balance"))
            builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
            
            if callback.message.text != text:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await callback.answer("💰 Баланс уже актуальный")
        
        elif action == "settings":
            await update_settings_menu(callback)
        
        elif action == "toggle_captcha":
            try:
                current_status = normalize_bool(await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED))
                new_status = not current_status
                await db.set_setting("captcha_enabled", new_status)
                status_text = "включена ✅" if new_status else "отключена ❌"
                await callback.answer(f"Капча {status_text}", show_alert=True)
                await update_settings_menu(callback)
            except Exception as e:
                await callback.answer(f"Ошибка: {e}", show_alert=True)
        
        elif action in ["set_percentage", "set_limits", "set_welcome"]:
            commands = {
                "set_percentage": "/set_percentage ЧИСЛО",
                "set_limits": "/set_limits МИН_СУММА МАКС_СУММА",
                "set_welcome": "/set_welcome"
            }
            await callback.answer(f"Используйте команду: {commands[action]}", show_alert=True)
        
        elif action == "broadcast":
            await callback.answer("Функция рассылки доступна только в приватном чате через команду /admin", show_alert=True)
        
        elif action == "orders":
            text = "📋 <b>Управление заявками</b>\n\nИспользуйте команды:\n/recent_orders - последние заявки\n/pending_orders - ожидающие заявки"
            builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
            
            if callback.message.text != text:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await callback.answer("📋 Меню заявок уже открыто")
        
        elif action == "staff":
            admin_users = await db.get_setting("admin_users", [])
            operator_users = await db.get_setting("operator_users", [])
            text = "👥 <b>Персонал системы</b>\n\n👑 <b>Администраторы:</b>\n"
            text += f"• {config.ADMIN_USER_ID} (супер-админ)\n"
            for user_id in admin_users:
                text += f"• {user_id}\n"
            text += "\n🔧 <b>Операторы:</b>\n"
            for user_id in operator_users:
                text += f"• {user_id}\n"
            if not admin_users and not operator_users:
                text += "Нет дополнительного персонала\n"
            text += "\n💡 Команды управления:\n• /grant_admin ID\n• /grant_operator ID\n• /revoke_admin ID\n• /revoke_operator ID"
            builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
            
            if callback.message.text != text:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            else:
                await callback.answer("👥 Меню персонала уже открыто")
        
        elif action == "panel":
            builder = create_admin_keyboard()
            new_text = (
                f"👑 <b>Панель администратора</b>\n"
                f"Чат: {callback.message.chat.title}\n"
                f"Администратор: {callback.from_user.first_name}"
            )
            
            if callback.message.text != new_text:
                await callback.message.edit_text(
                    new_text,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            else:
                await callback.answer("👑 Главное меню уже открыто")
        
        else:
            await callback.answer("❌ Неизвестная команда", show_alert=True)
    
    except Exception as e:
        logger.error(f"Admin callback error: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)








async def safe_edit_message(callback: CallbackQuery, text: str, markup=None, parse_mode="HTML"):
    try:
        if callback.message.text != text:
            await callback.message.edit_text(text, reply_markup=markup, parse_mode=parse_mode)
            return True
        else:
            await callback.answer("Содержимое не изменилось")
            return False
    except Exception as e:
        logger.error(f"Message edit error: {e}")
        await callback.answer("❌ Ошибка обновления", show_alert=True)
        return False







@router.message(Command("grant_admin"))
async def grant_admin_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    try:
        user_id = int(message.text.split()[1])
        admin_users = await db.get_setting("admin_users", [])
        if user_id not in admin_users:
            admin_users.append(user_id)
            await db.set_setting("admin_users", admin_users)
            await message.answer(f"✅ Пользователь {user_id} теперь администратор")
            try:
                await message.bot.send_message(user_id, "🎉 Вам выданы права администратора!\nТеперь вы можете использовать команду /admin")
            except:
                pass
        else:
            await message.answer(f"ℹ️ Пользователь {user_id} уже является администратором")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /grant_admin USER_ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("grant_operator"))
async def grant_operator_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    try:
        user_id = int(message.text.split()[1])
        operator_users = await db.get_setting("operator_users", [])
        if user_id not in operator_users:
            operator_users.append(user_id)
            await db.set_setting("operator_users", operator_users)
            await message.answer(f"✅ Пользователь {user_id} теперь оператор")
            try:
                await message.bot.send_message(user_id, "🎉 Вам выданы права оператора!\nТеперь вы можете использовать команду /admin")
            except:
                pass
        else:
            await message.answer(f"ℹ️ Пользователь {user_id} уже является оператором")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /grant_operator USER_ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("revoke_admin"))
async def revoke_admin_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    try:
        user_id = int(message.text.split()[1])
        admin_users = await db.get_setting("admin_users", [])
        if user_id in admin_users:
            admin_users.remove(user_id)
            await db.set_setting("admin_users", admin_users)
            await message.answer(f"✅ Права администратора отозваны у пользователя {user_id}")
            try:
                await message.bot.send_message(user_id, "❌ Ваши права администратора отозваны")
            except:
                pass
        else:
            await message.answer(f"ℹ️ Пользователь {user_id} не является администратором")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /revoke_admin USER_ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("revoke_operator"))
async def revoke_operator_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        await message.answer("❌ У вас нет прав для выполнения этой команды")
        return
    try:
        user_id = int(message.text.split()[1])
        operator_users = await db.get_setting("operator_users", [])
        if user_id in operator_users:
            operator_users.remove(user_id)
            await db.set_setting("operator_users", operator_users)
            await message.answer(f"✅ Права оператора отозваны у пользователя {user_id}")
            try:
                await message.bot.send_message(user_id, "❌ Ваши права оператора отозваны")
            except:
                pass
        else:
            await message.answer(f"ℹ️ Пользователь {user_id} не является оператором")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /revoke_operator USER_ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("list_staff"))
async def list_staff_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        await message.answer("❌ У вас нет прав для просмотра этой информации")
        return
    admin_users = await db.get_setting("admin_users", [])
    operator_users = await db.get_setting("operator_users", [])
    text = "👥 <b>стафф системы</b>\n\n👑 <b>Администраторы:</b>\n"
    text += f"• {config.ADMIN_USER_ID} (супер-админ)\n"
    for user_id in admin_users:
        text += f"• {user_id}\n"
    text += "\n🔧 <b>Операторы:</b>\n"
    for user_id in operator_users:
        text += f"• {user_id}\n"
    await message.answer(text, parse_mode="HTML")

@router.message(Command("my_id"))
async def my_id_handler(message: Message):
    role = "👤 Пользователь"
    if await is_admin_extended(message.from_user.id):
        role = "👑 Администратор"
    elif await is_operator_extended(message.from_user.id):
        role = "🔧 Оператор"
    await message.answer(
        f"🆔 <b>Ваша информация:</b>\n\n"
        f"ID: <code>{message.from_user.id}</code>\n"
        f"Роль: {role}\n"
        f"Имя: {message.from_user.first_name}\n"
        f"Username: @{message.from_user.username or 'не указан'}",
        parse_mode="HTML"
    )

@router.message(Command("setup_admin_chat"))
async def setup_admin_chat_handler(message: Message):
    if message.from_user.id != config.ADMIN_USER_ID:
        await message.answer("❌ Только супер-администратор может выполнить эту команду")
        return
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("❌ Эта команда работает только в групповых чатах")
        return
    admin_chats = await db.get_setting("admin_chats", [])
    if message.chat.id not in admin_chats:
        admin_chats.append(message.chat.id)
        await db.set_setting("admin_chats", admin_chats)
        await db.set_setting(f"chat_{message.chat.id}_title", message.chat.title)
    await message.answer(
        f"✅ <b>Чат настроен как административный</b>\n\n"
        f"Название: {message.chat.title}\n"
        f"ID: {message.chat.id}\n\n"
        f"Теперь в этом чате доступны административные команды.",
        parse_mode="HTML"
    )

@router.message(AdminStates.admin_mode, F.text == "📊 Статистика")
async def admin_stats_handler(message: Message):
    stats = await db.get_statistics()
    text = (
        f"📊 <b>Статистика системы</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📋 Всего заявок: {stats['total_orders']}\n"
        f"✅ Завершенных заявок: {stats['completed_orders']}\n"
        f"💰 Общий оборот: {stats['total_volume']:,.2f} ₽\n"
        f"📈 Процент завершения: {stats['completion_rate']:.1f}%\n\n"
        f"<b>Сегодня:</b>\n"
        f"📋 Заявок: {stats['today_orders']}\n"
        f"💰 Оборот: {stats['today_volume']:,.2f} ₽"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(AdminStates.admin_mode, F.text == "⚙️ Настройки")
async def admin_settings_handler(message: Message, state: FSMContext):
    current_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
    captcha_status = normalize_bool(await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED))
    min_amount = await db.get_setting("min_amount", config.MIN_AMOUNT)
    max_amount = await db.get_setting("max_amount", config.MAX_AMOUNT)
    text = (
        f"⚙️ <b>Текущие настройки</b>\n\n"
        f"💸 Процент администратора: {current_percentage}%\n"
        f"🤖 Капча: {'включена' if captcha_status else 'отключена'}\n"
        f"💰 Лимиты: {min_amount:,} - {max_amount:,} ₽\n\n"
        f"Для изменения настроек используйте команды:\n"
        f"• Процент: /set_percentage 5.5\n"
        f"• Капча: /toggle_captcha\n"
        f"• Лимиты: /set_limits 1000 500000\n"
        f"• Приветствие: /set_welcome"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(AdminStates.admin_mode, F.text == "📢 Рассылка")
async def admin_broadcast_handler(message: Message, state: FSMContext):
    await message.answer("📢 <b>Рассылка сообщений</b>\n\nОтправьте сообщение, которое будет разослано всем пользователям.", parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_broadcast_message)

@router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    if not await is_admin_extended(message.from_user.id):
        return
    users = await db.get_all_users()
    sent_count = failed_count = 0
    await message.answer(f"📤 Начинаю рассылку для {len(users)} пользователей...")
    for user_id in users:
        try:
            await message.bot.copy_message(chat_id=user_id, from_chat_id=message.chat.id, message_id=message.message_id)
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to send broadcast to {user_id}: {e}")
    await message.answer(f"✅ Рассылка завершена!\n\n📤 Отправлено: {sent_count}\n❌ Ошибок: {failed_count}")
    await state.set_state(AdminStates.admin_mode)

@router.message(AdminStates.admin_mode, F.text == "💰 Баланс")
async def admin_balance_handler(message: Message):
    try:
        balance_data = await onlypays_api.get_balance()
        balance = balance_data.get('balance', 0)
        text = f"💰 <b>Баланс процессинга</b>\n\n💳 Доступно: {balance:,.2f} ₽"
    except Exception as e:
        text = f"❌ Ошибка получения баланса:\n{e}"
    await message.answer(text, parse_mode="HTML")

@router.message(AdminStates.admin_mode, F.text == "👥 Пользователи")
async def admin_users_handler(message: Message):
    stats = await db.get_statistics()
    text = (
        f"👥 <b>Пользователи</b>\n\n"
        f"📊 Всего зарегистрировано: {stats['total_users']}\n"
        f"📈 Активных: данные обновляются\n"
        f"🔒 Заблокированных: 0\n\n"
        f"💡 Для управления пользователями используйте:\n"
        f"• /user_info ID - информация о пользователе\n"
        f"• /block_user ID - заблокировать\n"
        f"• /unblock_user ID - разблокировать"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(AdminStates.admin_mode, F.text == "📋 Заявки")
async def admin_orders_handler(message: Message):
    stats = await db.get_statistics()
    text = (
        f"📋 <b>Управление заявками</b>\n\n"
        f"📊 Всего заявок: {stats['total_orders']}\n"
        f"✅ Завершено: {stats['completed_orders']}\n"
        f"⏳ В ожидании: {stats['total_orders'] - stats['completed_orders']}\n\n"
        f"💡 Команды для управления:\n"
        f"• /order_info ID - информация о заявке\n"
        f"• /complete_order ID - завершить заявку\n"
        f"• /cancel_order ID - отменить заявку"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(AdminStates.admin_mode, F.text == "◀️ Выйти из админки")
async def exit_admin_handler(message: Message, state: FSMContext):
    await state.clear()
    from handlers.user import show_main_menu
    await show_main_menu(message)

@router.message(Command("set_percentage"))
async def set_percentage_command(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        percentage = float(message.text.split()[1])
        if not 0 <= percentage <= 50:
            await message.answer("❌ Процент должен быть от 0 до 50")
            return
        await db.set_setting("admin_percentage", percentage)
        await message.answer(f"✅ Процент администратора изменен на {percentage}%")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /set_percentage 5.5")

@router.message(Command("toggle_captcha"))
async def toggle_captcha_command(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        current_status = normalize_bool(await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED))
        new_status = not current_status
        await db.set_setting("captcha_enabled", new_status)
        status_text = "включена ✅" if new_status else "отключена ❌"
        await message.answer(f"🤖 Капча {status_text}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("user_info"))
async def user_info_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        orders = await db.get_user_orders(user_id, 5)
        text = (
            f"👤 <b>Информация о пользователе</b>\n\n"
            f"🆔 ID: <code>{user['user_id']}</code>\n"
            f"👨‍💼 Имя: {user['first_name'] or 'Не указано'}\n"
            f"📝 Username: @{user['username'] or 'Не указан'}\n"
            f"📅 Регистрация: {user['registration_date'][:16]}\n"
            f"🚫 Заблокирован: {'Да' if user.get('is_blocked') else 'Нет'}\n"
            f"📊 Операций: {user.get('total_operations', 0)}\n"
            f"💰 Общая сумма: {user.get('total_amount', 0):,.0f} ₽\n"
            f"👥 Рефералов: {user.get('referral_count', 0)}\n"
            f"🔗 Приглашен: {user.get('referred_by') or 'Нет'}\n\n"
            f"📋 <b>Последние заявки:</b>\n"
        )
        if orders:
            for order in orders:
                status_emoji = {"waiting": "⏳", "finished": "✅"}.get(order['status'], "❌")
                text += f"{status_emoji} #{order['id']} - {order['total_amount']:,.0f} ₽\n"
        else:
            text += "Заявок нет"
        await message.answer(text, parse_mode="HTML")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /user_info USER_ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("block_user"))
async def block_user_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        reason = " ".join(parts[2:]) if len(parts) > 2 else "Не указана"
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        if user.get('is_blocked'):
            await message.answer(f"ℹ️ Пользователь {user_id} уже заблокирован")
            return
        await db.update_user(user_id, is_blocked=True)
        await message.answer(
            f"✅ <b>Пользователь заблокирован</b>\n\n"
            f"🆔 ID: {user_id}\n"
            f"👤 Имя: {user['first_name']}\n"
            f"📝 Причина: {reason}\n"
            f"👨‍💼 Заблокировал: {message.from_user.first_name}",
            parse_mode="HTML"
        )
        try:
            await message.bot.send_message(
                user_id,
                f"🚫 <b>Ваш аккаунт заблокирован</b>\n\n"
                f"📝 Причина: {reason}\n"
                f"📞 Для разблокировки обратитесь в поддержку: {config.SUPPORT_MANAGER}",
                parse_mode="HTML"
            )
        except:
            pass
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /block_user USER_ID [причина]")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("unblock_user"))
async def unblock_user_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        user_id = int(message.text.split()[1])
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        if not user.get('is_blocked'):
            await message.answer(f"ℹ️ Пользователь {user_id} не заблокирован")
            return
        await db.update_user(user_id, is_blocked=False)
        await message.answer(
            f"✅ <b>Пользователь разблокирован</b>\n\n"
            f"🆔 ID: {user_id}\n"
            f"👤 Имя: {user['first_name']}\n"
            f"👨‍💼 Разблокировал: {message.from_user.first_name}",
            parse_mode="HTML"
        )
        try:
            await message.bot.send_message(
                user_id,
                f"✅ <b>Ваш аккаунт разблокирован</b>\n\nВы можете продолжить использование бота.\nСпасибо за понимание!",
                parse_mode="HTML"
            )
        except:
            pass
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /unblock_user USER_ID")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("search_user"))
async def search_user_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        username = message.text.split()[1].replace("@", "")
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute('SELECT * FROM users WHERE username = ? COLLATE NOCASE', (username,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    columns = [description[0] for description in cursor.description]
                    user = dict(zip(columns, row))
        if not row:
            await message.answer(f"❌ Пользователь @{username} не найден")
            return
        text = (
            f"👤 <b>Найденный пользователь</b>\n\n"
            f"🆔 ID: <code>{user['user_id']}</code>\n"
            f"📝 Username: @{user['username']}\n"
            f"👨‍💼 Имя: {user['first_name']}\n"
            f"📅 Регистрация: {user['registration_date'][:16]}\n"
            f"🚫 Заблокирован: {'Да' if user.get('is_blocked') else 'Нет'}"
        )
        await message.answer(text, parse_mode="HTML")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /search_user USERNAME")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("recent_users"))
async def recent_users_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        limit = min(int(message.text.split()[1]) if len(message.text.split()) > 1 else 10, 50)
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute('''
                SELECT user_id, username, first_name, registration_date, total_operations
                FROM users ORDER BY registration_date DESC LIMIT ?
            ''', (limit,)) as cursor:
                rows = await cursor.fetchall()
        if not rows:
            await message.answer("❌ Пользователи не найдены")
            return
        text = f"👥 <b>Последние {len(rows)} пользователей:</b>\n\n"
        for user_id, username, first_name, reg_date, operations in rows:
            text += f"🆔 {user_id} | @{username or 'нет'} | {first_name}\n📅 {reg_date[:16]} | 📊 {operations or 0} операций\n\n"
        await message.answer(text, parse_mode="HTML")
    except (IndexError, ValueError):
        await message.answer("❌ Укажите корректное число (1-50)")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("user_stats"))
async def user_stats_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute('SELECT COUNT(*) FROM users') as cursor:
                total_users = (await cursor.fetchone())[0]
            async with database.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1') as cursor:
                blocked_users = (await cursor.fetchone())[0]
            async with database.execute('SELECT COUNT(*) FROM users WHERE DATE(registration_date) = DATE("now")') as cursor:
                today_registrations = (await cursor.fetchone())[0]
            async with database.execute('SELECT COUNT(*) FROM users WHERE total_operations > 0') as cursor:
                active_users = (await cursor.fetchone())[0]
        text = (
            f"📊 <b>Статистика пользователей</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🚫 Заблокированных: {blocked_users}\n"
            f"⚡ Активных: {active_users}\n"
            f"📅 Регистраций сегодня: {today_registrations}\n"
            f"📈 Процент активности: {(active_users/total_users*100):.1f}%"
        )
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("send_message"))
async def send_message_to_user_handler(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        parts = message.text.split(None, 2)
        user_id = int(parts[1])
        text_to_send = parts[2]
        user = await db.get_user(user_id)
        if not user:
            await message.answer(f"❌ Пользователь {user_id} не найден")
            return
        full_message = (
            f"📨 <b>Сообщение от администрации</b>\n\n"
            f"{text_to_send}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📞 Поддержка: {config.SUPPORT_MANAGER}"
        )
        await message.bot.send_message(user_id, full_message, parse_mode="HTML")
        await message.answer(f"✅ Сообщение отправлено пользователю {user_id} ({user['first_name']})", parse_mode="HTML")
    except (IndexError, ValueError):
        await message.answer("❌ Использование: /send_message USER_ID текст сообщения")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(Command("check_captcha"))
async def check_captcha_status(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    try:
        current_status = await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED)
        normalized_status = normalize_bool(current_status)
        await message.answer(
            f"🔍 <b>Статус капчи:</b>\n\n"
            f"📊 Сырое значение: {current_status} ({type(current_status).__name__})\n"
            f"🔄 Нормализованное: {normalized_status}\n"
            f"⚙️ По умолчанию: {config.CAPTCHA_ENABLED}\n"
            f"🤖 Отображение: {'включена' if normalized_status else 'отключена'}",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")





@router.callback_query(F.data.startswith("review_"))
async def review_moderation(callback: CallbackQuery):
    if not await is_admin_extended(callback.from_user.id):
        await callback.answer("❌ Нет прав", show_alert=True)
        return
    
    action, review_id = callback.data.split("_")[1:]
    
    try:
        if action == "approve":
            await db.update_review_status(review_id, "approved")
            await callback.answer("✅ Отзыв одобрен")
            
            review_data = await db.get_review(review_id)
            if review_data:
                user = await db.get_user(review_data['user_id'])
                
                from datetime import datetime
                
                channel_text = (
                    f"⭐️ <b>Отзыв о работе {config.EXCHANGE_NAME}</b>\n\n"
                    f"👤 От: {user['first_name']} (@{user['username'] or 'скрыт'})\n"
                    f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"💬 <b>Текст отзыва:</b>\n"
                    f"{review_data['text']}\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 {config.EXCHANGE_NAME} - надежный обмен криптовалют\n"
                    f"🤖 @{config.BOT_USERNAME}"
                )
                
                try:
                    await callback.bot.send_message(
                        config.REVIEWS_CHANNEL_ID,
                        channel_text,
                        parse_mode="HTML"
                    )
                    logger.info(f"Approved review {review_id} sent to reviews channel")
                except Exception as e:
                    logger.error(f"Failed to send review to channel: {e}")
            
            await callback.message.edit_text(
                f"{callback.message.text}\n\n✅ <b>ОДОБРЕН И ОПУБЛИКОВАН</b>",
                parse_mode="HTML"
            )
        
        elif action == "reject":
            await db.update_review_status(review_id, "rejected")
            await callback.answer("❌ Отзыв отклонен")
            await callback.message.edit_text(
                f"{callback.message.text}\n\n❌ <b>ОТКЛОНЕН</b>",
                parse_mode="HTML"
            )
        
    except Exception as e:
        logger.error(f"Review moderation error: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)