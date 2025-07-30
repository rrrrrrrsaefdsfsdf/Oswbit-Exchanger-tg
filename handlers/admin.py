import logging
from datetime import datetime, timedelta
import aiosqlite
import os
import psutil
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType
from database.models import Database
from keyboards.reply import ReplyKeyboards
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
    waiting_for_user_id = State()
    waiting_for_message_to_user = State()
    waiting_for_block_reason = State()
    waiting_for_order_id = State()

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
    if user_id == config.ADMIN_USER_ID:
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

def create_main_admin_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Заявки", callback_data="admin_orders_menu"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="admin_balance")
    )
    builder.row(
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users_menu"),
        InlineKeyboardButton(text="🔧 Персонал", callback_data="admin_staff_menu")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast_menu"),
        InlineKeyboardButton(text="🛠 Система", callback_data="admin_system_menu")
    )
    return builder

def create_settings_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💸 Изменить процент", callback_data="admin_change_percentage"),
        InlineKeyboardButton(text="🤖 Капча", callback_data="admin_toggle_captcha")
    )
    builder.row(
        InlineKeyboardButton(text="💰 Лимиты сумм", callback_data="admin_change_limits"),
        InlineKeyboardButton(text="📝 Приветствие", callback_data="admin_change_welcome")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
    )
    return builder

def create_users_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin_find_user"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_user_stats")
    )
    builder.row(
        InlineKeyboardButton(text="📝 Последние", callback_data="admin_recent_users"),
        InlineKeyboardButton(text="💬 Написать", callback_data="admin_message_user")
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Заблокировать", callback_data="admin_block_user"),
        InlineKeyboardButton(text="✅ Разблокировать", callback_data="admin_unblock_user")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
    )
    return builder

def create_staff_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin"),
        InlineKeyboardButton(text="➖ Убрать админа", callback_data="admin_remove_admin")
    )
    builder.row(
        InlineKeyboardButton(text="🔧 Добавить оператора", callback_data="admin_add_operator"),
        InlineKeyboardButton(text="❌ Убрать оператора", callback_data="admin_remove_operator")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Список персонала", callback_data="admin_staff_list")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
    )
    return builder

def create_orders_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Последние заявки", callback_data="admin_recent_orders"),
        InlineKeyboardButton(text="⏳ Ожидающие", callback_data="admin_pending_orders")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Завершенные", callback_data="admin_completed_orders"),
        InlineKeyboardButton(text="❌ Отмененные", callback_data="admin_cancelled_orders")
    )
    builder.row(
        InlineKeyboardButton(text="🔍 Найти заявку", callback_data="admin_find_order"),
        InlineKeyboardButton(text="⚠️ Проблемные", callback_data="admin_problem_orders")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
    )
    return builder

def create_system_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Системная информация", callback_data="admin_system_info"),
        InlineKeyboardButton(text="📋 Логи", callback_data="admin_view_logs")
    )
    builder.row(
        InlineKeyboardButton(text="🧹 Очистить БД", callback_data="admin_cleanup_db"),
        InlineKeyboardButton(text="🔄 Обновить статистику", callback_data="admin_refresh_stats")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
    )
    return builder

def create_broadcast_panel():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Отправить всем", callback_data="admin_broadcast_all"),
        InlineKeyboardButton(text="👥 Активным", callback_data="admin_broadcast_active")
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новым (за неделю)", callback_data="admin_broadcast_new"),
        InlineKeyboardButton(text="🎯 С операциями", callback_data="admin_broadcast_traders")
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
    )
    return builder

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
        builder = create_main_admin_panel()
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
    
    try:
        if action == "main_panel":
            builder = create_main_admin_panel()
            text = (
                f"👑 <b>Панель администратора</b>\n"
                f"Администратор: {callback.from_user.first_name}"
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

        elif action == "stats":
            stats = await db.get_statistics()
            text = (
                f"📊 <b>Статистика системы</b>\n\n"
                f"👥 Пользователей: {stats['total_users']}\n"
                f"📋 Заявок: {stats['total_orders']}\n"
                f"✅ Завершено: {stats['completed_orders']}\n"
                f"💰 Оборот: {stats['total_volume']:,.0f} ₽\n\n"
                f"📈 Процент завершения: {stats['completion_rate']:.1f}%\n"
                f"📅 Сегодня заявок: {stats['today_orders']}\n"
                f"💵 Сегодня оборот: {stats['today_volume']:,.0f} ₽"
            )
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_stats"),
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

        elif action == "balance":
            try:
                if not hasattr(config, 'ONLYPAYS_PAYMENT_KEY') or not config.ONLYPAYS_PAYMENT_KEY:
                    text = "❌ <b>Ошибка получения баланса</b>\n\nPayment Key не настроен"
                else:
                    from handlers.user import onlypays_api
                    balance_response = await onlypays_api.get_balance()
                    if balance_response.get('success'):
                        balance = balance_response.get('balance', 0)
                        text = f"💰 <b>Баланс процессинга</b>\n\n💳 Доступно: {balance:,.2f} ₽"
                    else:
                        error_msg = balance_response.get('error', 'Неизвестная ошибка')
                        text = f"❌ Ошибка получения баланса:\n{error_msg}"
            except Exception as e:
                text = f"❌ Ошибка получения баланса:\n{e}"
            
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_balance"),
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main_panel")
            )
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

        elif action == "settings":
            current_percentage = await db.get_setting("admin_percentage", config.ADMIN_PERCENTAGE)
            captcha_status = normalize_bool(await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED))
            min_amount = await db.get_setting("min_amount", config.MIN_AMOUNT)
            max_amount = await db.get_setting("max_amount", config.MAX_AMOUNT)
            
            status_text = "✅ Включена" if captcha_status else "❌ Отключена"
            
            text = (
                f"⚙️ <b>Настройки системы</b>\n\n"
                f"💸 Процент администратора: {current_percentage}%\n"
                f"🤖 Капча: {status_text}\n"
                f"💰 Лимиты: {min_amount:,} - {max_amount:,} ₽"
            )
            await callback.message.edit_text(text, reply_markup=create_settings_panel().as_markup(), parse_mode="HTML")

        elif action == "users_menu":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('SELECT COUNT(*) FROM users') as cursor:
                        total_users = (await cursor.fetchone())[0]
                    async with database.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1') as cursor:
                        blocked_users = (await cursor.fetchone())[0]
                    async with database.execute('SELECT COUNT(*) FROM users WHERE total_operations > 0') as cursor:
                        active_users = (await cursor.fetchone())[0]
                
                text = (
                    f"👥 <b>Управление пользователями</b>\n\n"
                    f"📊 Всего: {total_users}\n"
                    f"⚡ Активных: {active_users}\n"
                    f"🚫 Заблокированных: {blocked_users}"
                )
            except:
                text = "👥 <b>Управление пользователями</b>\n\n❌ Ошибка загрузки статистики"
            
            await callback.message.edit_text(text, reply_markup=create_users_panel().as_markup(), parse_mode="HTML")

        elif action == "staff_menu":
            admin_users = await db.get_setting("admin_users", [])
            operator_users = await db.get_setting("operator_users", [])
            
            try:
                from handlers.operator import get_operators_list
                operator_file_list = get_operators_list()
            except:
                operator_file_list = []
            
            text = (
                f"🔧 <b>Персонал системы</b>\n\n"
                f"👑 Администраторов: {len(admin_users) + 1}\n"
                f"🔧 Операторов (БД): {len(operator_users)}\n"
                f"🔧 Операторов (файл): {len(operator_file_list)}"
            )
            await callback.message.edit_text(text, reply_markup=create_staff_panel().as_markup(), parse_mode="HTML")

        elif action == "orders_menu":
            stats = await db.get_statistics()
            text = (
                f"📋 <b>Управление заявками</b>\n\n"
                f"📊 Всего: {stats['total_orders']}\n"
                f"✅ Завершено: {stats['completed_orders']}\n"
                f"⏳ В ожидании: {stats['total_orders'] - stats['completed_orders']}\n"
                f"💰 Общий оборот: {stats['total_volume']:,.0f} ₽"
            )
            await callback.message.edit_text(text, reply_markup=create_orders_panel().as_markup(), parse_mode="HTML")

        elif action == "broadcast_menu":
            text = "📢 <b>Рассылка сообщений</b>\n\nВыберите тип рассылки:"
            await callback.message.edit_text(text, reply_markup=create_broadcast_panel().as_markup(), parse_mode="HTML")

        elif action == "system_menu":
            text = "🛠 <b>Системные функции</b>\n\nВыберите действие:"
            await callback.message.edit_text(text, reply_markup=create_system_panel().as_markup(), parse_mode="HTML")

        elif action == "system_info":
            try:
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                cpu_percent = process.cpu_percent()
                
                db_size = os.path.getsize(db.db_path) if os.path.exists(db.db_path) else 0
                
                text = (
                    f"📊 <b>Системная информация</b>\n\n"
                    f"💾 Использование памяти: {memory_info.rss / 1024 / 1024:.1f} MB\n"
                    f"🖥 Нагрузка CPU: {cpu_percent:.1f}%\n"
                    f"💾 Размер БД: {db_size / 1024 / 1024:.1f} MB\n"
                    f"🕐 Время работы: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                    f"🔄 Обновлено: {datetime.now().strftime('%H:%M:%S')}"
                )
                
                builder = InlineKeyboardBuilder()
                builder.row(
                    InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_system_info"),
                    InlineKeyboardButton(text="◀️ Назад", callback_data="admin_system_menu")
                )
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "view_logs":
            try:
                log_files = []
                for file in os.listdir('.'):
                    if file.endswith('.log'):
                        log_files.append(file)
                
                if log_files:
                    text = "📋 <b>Доступные лог-файлы:</b>\n\n"
                    for log_file in log_files:
                        size = os.path.getsize(log_file) / 1024
                        text += f"📄 {log_file} ({size:.1f} KB)\n"
                    text += "\n💡 Используйте команду /get_log filename для просмотра"
                else:
                    text = "📋 <b>Логи</b>\n\n❌ Лог-файлы не найдены"
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_system_menu"))
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "cleanup_db":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    await database.execute('DELETE FROM orders WHERE status = "cancelled" AND created_at < datetime("now", "-30 days")')
                    await database.execute('DELETE FROM captcha_sessions WHERE created_at < datetime("now", "-1 day")')
                    await database.execute('VACUUM')
                    await database.commit()
                
                await callback.answer("✅ База данных очищена", show_alert=True)
                await admin_callback_handler(callback.model_copy(update={"data": "admin_system_menu"}), state)
            except Exception as e:
                await callback.answer(f"❌ Ошибка очистки БД: {e}", show_alert=True)

        elif action == "recent_orders":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('''
                        SELECT id, user_id, total_amount, status, created_at, personal_id
                        FROM orders ORDER BY created_at DESC LIMIT 10
                    ''') as cursor:
                        orders = await cursor.fetchall()
                
                if orders:
                    text = "📋 <b>Последние 10 заявок:</b>\n\n"
                    for order in orders:
                        order_id, user_id, amount, status, created_at, personal_id = order
                        status_emoji = {"waiting": "⏳", "finished": "✅", "cancelled": "❌", "paid_by_client": "💰"}.get(status, "❓")
                        display_id = personal_id or order_id
                        text += f"{status_emoji} #{display_id} | {amount:,.0f}₽ | {user_id}\n{created_at[:16]}\n\n"
                else:
                    text = "📋 <b>Заявки</b>\n\n❌ Заявки не найдены"
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_orders_menu"))
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "pending_orders":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('''
                        SELECT id, user_id, total_amount, created_at, personal_id
                        FROM orders WHERE status IN ("waiting", "paid_by_client") ORDER BY created_at DESC
                    ''') as cursor:
                        orders = await cursor.fetchall()
                
                if orders:
                    text = f"⏳ <b>Ожидающие заявки ({len(orders)}):</b>\n\n"
                    for order in orders[:10]:
                        order_id, user_id, amount, created_at, personal_id = order
                        display_id = personal_id or order_id
                        text += f"📋 #{display_id} | {amount:,.0f}₽ | {user_id}\n{created_at[:16]}\n\n"
                    
                    if len(orders) > 10:
                        text += f"... и еще {len(orders) - 10} заявок"
                else:
                    text = "⏳ <b>Ожидающие заявки</b>\n\n✅ Нет ожидающих заявок"
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_orders_menu"))
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "completed_orders":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('''
                        SELECT id, user_id, total_amount, created_at, personal_id
                        FROM orders WHERE status = "completed" ORDER BY created_at DESC LIMIT 10
                    ''') as cursor:
                        orders = await cursor.fetchall()
                
                if orders:
                    text = "✅ <b>Завершенные заявки (последние 10):</b>\n\n"
                    for order in orders:
                        order_id, user_id, amount, created_at, personal_id = order
                        display_id = personal_id or order_id
                        text += f"✅ #{display_id} | {amount:,.0f}₽ | {user_id}\n{created_at[:16]}\n\n"
                else:
                    text = "✅ <b>Завершенные заявки</b>\n\n❌ Завершенных заявок нет"
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_orders_menu"))
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "cancelled_orders":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('''
                        SELECT id, user_id, total_amount, created_at, personal_id
                        FROM orders WHERE status = "cancelled" ORDER BY created_at DESC LIMIT 10
                    ''') as cursor:
                        orders = await cursor.fetchall()
                
                if orders:
                    text = "❌ <b>Отмененные заявки (последние 10):</b>\n\n"
                    for order in orders:
                        order_id, user_id, amount, created_at, personal_id = order
                        display_id = personal_id or order_id
                        text += f"❌ #{display_id} | {amount:,.0f}₽ | {user_id}\n{created_at[:16]}\n\n"
                else:
                    text = "❌ <b>Отмененные заявки</b>\n\n✅ Отмененных заявок нет"
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_orders_menu"))
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "problem_orders":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('''
                        SELECT id, user_id, total_amount, created_at, personal_id
                        FROM orders WHERE status = "problem" ORDER BY created_at DESC
                    ''') as cursor:
                        orders = await cursor.fetchall()
                
                if orders:
                    text = f"⚠️ <b>Проблемные заявки ({len(orders)}):</b>\n\n"
                    for order in orders:
                        order_id, user_id, amount, created_at, personal_id = order
                        display_id = personal_id or order_id
                        text += f"⚠️ #{display_id} | {amount:,.0f}₽ | {user_id}\n{created_at[:16]}\n\n"
                else:
                    text = "⚠️ <b>Проблемные заявки</b>\n\n✅ Проблемных заявок нет"
                
                builder = InlineKeyboardBuilder()
                builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_orders_menu"))
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "find_order":
            await callback.message.edit_text(
                "🔍 <b>Поиск заявки</b>\n\n"
                "Введите ID заявки:",
                parse_mode="HTML"
            )
            await state.update_data(action="find_order")
            await state.set_state(AdminStates.waiting_for_order_id)

        elif action == "broadcast_active":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('SELECT user_id FROM users WHERE total_operations > 0') as cursor:
                        users = [row[0] for row in await cursor.fetchall()]
                
                await callback.message.edit_text(
                    f"📤 <b>Рассылка активным пользователям</b>\n\n"
                    f"Найдено активных пользователей: {len(users)}\n\n"
                    "Отправьте сообщение для рассылки:",
                    parse_mode="HTML"
                )
                await state.update_data(action="broadcast_active", target_users=users)
                await state.set_state(AdminStates.waiting_for_broadcast_message)
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "broadcast_new":
            try:
                week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('SELECT user_id FROM users WHERE registration_date > ?', (week_ago,)) as cursor:
                        users = [row[0] for row in await cursor.fetchall()]
                
                await callback.message.edit_text(
                    f"📤 <b>Рассылка новым пользователям</b>\n\n"
                    f"Найдено новых пользователей (за неделю): {len(users)}\n\n"
                    "Отправьте сообщение для рассылки:",
                    parse_mode="HTML"
                )
                await state.update_data(action="broadcast_new", target_users=users)
                await state.set_state(AdminStates.waiting_for_broadcast_message)
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action == "broadcast_traders":
            try:
                async with aiosqlite.connect(db.db_path) as database:
                    async with database.execute('SELECT user_id FROM users WHERE total_operations >= 1') as cursor:
                        users = [row[0] for row in await cursor.fetchall()]
                
                await callback.message.edit_text(
                    f"📤 <b>Рассылка пользователям с операциями</b>\n\n"
                    f"Найдено пользователей с операциями: {len(users)}\n\n"
                    "Отправьте сообщение для рассылки:",
                    parse_mode="HTML"
                )
                await state.update_data(action="broadcast_traders", target_users=users)
                await state.set_state(AdminStates.waiting_for_broadcast_message)
            except Exception as e:
                await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

        elif action in ["toggle_captcha", "change_percentage", "change_limits", "change_welcome",
                        "find_user", "message_user", "block_user", "unblock_user",
                        "add_admin", "remove_admin", "add_operator", "remove_operator",
                        "staff_list", "broadcast_all", "user_stats", "recent_users"]:
            await handle_settings_and_management(callback, state, action)

        else:
            await callback.answer("❌ Неизвестная команда", show_alert=True)
    
    except Exception as e:
        logger.error(f"Admin callback error: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

async def handle_settings_and_management(callback: CallbackQuery, state: FSMContext, action: str):
    if action == "toggle_captcha":
        current_status = normalize_bool(await db.get_setting("captcha_enabled", config.CAPTCHA_ENABLED))
        new_status = not current_status
        await db.set_setting("captcha_enabled", new_status)
        status_text = "✅ Включена" if new_status else "❌ Отключена"
        await callback.answer(f"Капча: {status_text}")
        await admin_callback_handler(callback.model_copy(update={"data": "admin_settings"}), state)

    elif action == "change_percentage":
        await callback.message.edit_text(
            "💸 <b>Изменение процента администратора</b>\n\n"
            "Введите новый процент (от 0 до 50):\n"
            "Например: 5.5",
            parse_mode="HTML"
        )
        await state.update_data(action="change_percentage")
        await state.set_state(AdminStates.waiting_for_percentage)

    elif action == "change_limits":
        await callback.message.edit_text(
            "💰 <b>Изменение лимитов</b>\n\n"
            "Введите новые лимиты через пробел:\n"
            "Например: 1000 500000",
            parse_mode="HTML"
        )
        await state.update_data(action="change_limits")
        await state.set_state(AdminStates.waiting_for_limits)

    elif action == "change_welcome":
        await callback.message.edit_text(
            "📝 <b>Изменение приветственного сообщения</b>\n\n"
            "Отправьте новое приветственное сообщение:",
            parse_mode="HTML"
        )
        await state.update_data(action="change_welcome")
        await state.set_state(AdminStates.waiting_for_welcome_message)

    elif action in ["find_user", "message_user", "block_user", "unblock_user",
                    "add_admin", "remove_admin", "add_operator", "remove_operator"]:
        await callback.message.edit_text(
            f"👤 <b>{get_action_title(action)}</b>\n\n"
            "Введите ID или @username пользователя:",
            parse_mode="HTML"
        )
        await state.update_data(action=action)
        await state.set_state(AdminStates.waiting_for_user_id)

    elif action == "staff_list":
        await show_staff_list(callback)

    elif action == "broadcast_all":
        users = await db.get_all_users()
        await callback.message.edit_text(
            f"📤 <b>Рассылка всем пользователям</b>\n\n"
            f"Найдено пользователей: {len(users)}\n\n"
            "Отправьте сообщение для рассылки:",
            parse_mode="HTML"
        )
        await state.update_data(action="broadcast_all", target_users=users)
        await state.set_state(AdminStates.waiting_for_broadcast_message)

    elif action == "user_stats":
        await show_detailed_user_stats(callback)

    elif action == "recent_users":
        await show_recent_users(callback)

def get_action_title(action: str) -> str:
    titles = {
        "find_user": "Поиск пользователя",
        "message_user": "Отправка сообщения пользователю",
        "block_user": "Блокировка пользователя",
        "unblock_user": "Разблокировка пользователя",
        "add_admin": "Добавление администратора",
        "remove_admin": "Удаление администратора",
        "add_operator": "Добавление оператора",
        "remove_operator": "Удаление оператора"
    }
    return titles.get(action, action)

async def show_staff_list(callback: CallbackQuery):
    admin_users = await db.get_setting("admin_users", [])
    operator_users = await db.get_setting("operator_users", [])
    
    try:
        from handlers.operator import get_operators_list
        operator_file_list = get_operators_list()
    except:
        operator_file_list = []
    
    text = "👥 <b>Список персонала</b>\n\n"
    text += "👑 <b>Администраторы:</b>\n"
    text += f"• {config.ADMIN_USER_ID} (супер-админ)\n"
    for user_id in admin_users:
        text += f"• {user_id}\n"
    
    text += "\n🔧 <b>Операторы (БД):</b>\n"
    for user_id in operator_users:
        text += f"• {user_id}\n"
    
    text += "\n🔧 <b>Операторы (файл):</b>\n"
    for user_id in operator_file_list:
        text += f"• {user_id}\n"
    
    if not admin_users and not operator_users and not operator_file_list:
        text += "\nНет дополнительного персонала"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_staff_menu"))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

async def show_detailed_user_stats(callback: CallbackQuery):
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
            async with database.execute('SELECT COUNT(*) FROM users WHERE DATE(registration_date) >= DATE("now", "-7 days")') as cursor:
                week_registrations = (await cursor.fetchone())[0]
                
        activity_rate = (active_users/total_users*100) if total_users > 0 else 0
        
        text = (
            f"📊 <b>Детальная статистика пользователей</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🚫 Заблокированных: {blocked_users}\n"
            f"⚡ Активных: {active_users}\n"
            f"📅 Регистраций сегодня: {today_registrations}\n"
            f"📅 Регистраций за неделю: {week_registrations}\n"
            f"📈 Процент активности: {activity_rate:.1f}%"
        )
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_user_stats"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="admin_users_menu")
        )
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

async def show_recent_users(callback: CallbackQuery):
    try:
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute('''
                SELECT user_id, username, first_name, registration_date, total_operations
                FROM users ORDER BY registration_date DESC LIMIT 10
            ''') as cursor:
                rows = await cursor.fetchall()
        
        if not rows:
            text = "❌ Пользователи не найдены"
        else:
            text = f"👥 <b>Последние 10 пользователей:</b>\n\n"
            for user_id, username, first_name, reg_date, operations in rows:
                text += f"🆔 {user_id} | @{username or 'нет'}\n{first_name} | {reg_date[:16]} | {operations or 0} операций\n\n"
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_users_menu"))
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)

@router.message(AdminStates.waiting_for_percentage)
async def process_percentage_change(message: Message, state: FSMContext):
    try:
        percentage = float(message.text)
        if not 0 <= percentage <= 50:
            await message.answer("❌ Процент должен быть от 0 до 50")
            return
        
        await db.set_setting("admin_percentage", percentage)
        await message.answer(f"✅ Процент администратора изменен на {percentage}%")
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректное число")

@router.message(AdminStates.waiting_for_limits)
async def process_limits_change(message: Message, state: FSMContext):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Введите два числа через пробел")
            return
        
        min_amount = int(parts[0])
        max_amount = int(parts[1])
        
        if min_amount >= max_amount or min_amount < 100:
            await message.answer("❌ Минимальная сумма должна быть меньше максимальной и больше 100")
            return
        
        await db.set_setting("min_amount", min_amount)
        await db.set_setting("max_amount", max_amount)
        await message.answer(f"✅ Лимиты изменены: {min_amount:,} - {max_amount:,} ₽")
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите корректные числа")

@router.message(AdminStates.waiting_for_welcome_message)
async def process_welcome_change(message: Message, state: FSMContext):
    try:
        await db.set_setting("welcome_message", message.text)
        await message.answer("✅ Приветственное сообщение обновлено")
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(AdminStates.waiting_for_order_id)
async def process_order_search(message: Message, state: FSMContext):
    try:
        order_id = message.text.strip()
        
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute('''
                SELECT id, user_id, amount_rub, amount_btc, btc_address, total_amount, status, 
                       created_at, personal_id, payment_type, rate, processing_fee, admin_fee
                FROM orders 
                WHERE id = ? OR personal_id = ?
            ''', (order_id, order_id)) as cursor:
                order = await cursor.fetchone()
        
        if not order:
            await message.answer("❌ Заявка не найдена")
            return
        
        (internal_id, user_id, amount_rub, amount_btc, btc_address, total_amount, 
         status, created_at, personal_id, payment_type, rate, processing_fee, admin_fee) = order
        
        display_id = personal_id or internal_id
        status_text = {
            "waiting": "⏳ Ожидание",
            "paid_by_client": "💰 Оплачена клиентом",
            "completed": "✅ Завершена", 
            "cancelled": "❌ Отменена",
            "problem": "⚠️ Проблемная"
        }.get(status, status)
        
        text = (
            f"🔍 <b>Заявка #{display_id}</b>\n\n"
            f"🆔 Внутренний ID: {internal_id}\n"
            f"👤 Пользователь: {user_id}\n"
            f"💰 Сумма: {amount_rub:,.0f} ₽\n"
            f"₿ Bitcoin: {amount_btc:.8f} BTC\n"
            f"💸 К оплате: {total_amount:,.0f} ₽\n"
            f"💱 Курс: {rate:,.0f} ₽\n"
            f"💳 Комиссия процессинга: {processing_fee:,.0f} ₽\n"
            f"🏛 Комиссия сервиса: {admin_fee:,.0f} ₽\n"
            f"📱 Тип оплаты: {payment_type or 'Не указан'}\n"
            f"📊 Статус: {status_text}\n"
            f"📅 Создана: {created_at}\n\n"
            f"₿ <b>Bitcoin адрес:</b>\n<code>{btc_address}</code>"
        )
        
        await message.answer(text, parse_mode="HTML")
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
        
    except Exception as e:
        await message.answer(f"❌ Ошибка поиска: {e}")

@router.message(AdminStates.waiting_for_user_id)
async def process_user_id_input(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    
    try:
        user_input = message.text.strip()
        if user_input.startswith("@"):
            user_id = await find_user_by_username(user_input[1:])
            if not user_id:
                await message.answer("❌ Пользователь с таким username не найден")
                return
        else:
            user_id = int(user_input)
        
        if action == "find_user":
            await show_user_info(message, user_id)
        elif action == "message_user":
            await state.update_data(target_user_id=user_id, action="message_user_step2")
            await message.answer(
                f"💬 <b>Отправка сообщения пользователю {user_id}</b>\n\n"
                "Введите текст сообщения:",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_message_to_user)
            return
        elif action == "block_user":
            await state.update_data(target_user_id=user_id, action="block_user_step2")
            await message.answer(
                f"🚫 <b>Блокировка пользователя {user_id}</b>\n\n"
                "Введите причину блокировки:",
                parse_mode="HTML"
            )
            await state.set_state(AdminStates.waiting_for_block_reason)
            return
        else:
            await handle_user_management(message, user_id, action)
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите корректный ID пользователя")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def show_user_info(message: Message, user_id: int):
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден")
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
        f"👥 Рефералов: {user.get('referral_count', 0)}"
    )
    
    if orders:
        text += "\n\n📋 <b>Последние заявки:</b>\n"
        for order in orders:
            status_emoji = {"waiting": "⏳", "finished": "✅", "completed": "✅"}.get(order['status'], "❌")
            text += f"{status_emoji} #{order['id']} - {order['total_amount']:,.0f} ₽\n"
    
    await message.answer(text, parse_mode="HTML")

async def handle_user_management(message: Message, user_id: int, action: str):
    if action == "unblock_user":
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        if not user.get('is_blocked'):
            await message.answer("❌ Пользователь не заблокирован")
            return
        
        await db.update_user(user_id, is_blocked=False)
        await message.answer(f"✅ Пользователь {user_id} разблокирован")
        
        try:
            await message.bot.send_message(
                user_id,
                "✅ <b>Ваш аккаунт разблокирован</b>\n\n"
                "Вы можете продолжить использование бота.",
                parse_mode="HTML"
            )
        except:
            pass

    elif action == "add_admin":
        admin_users = await db.get_setting("admin_users", [])
        if user_id not in admin_users:
            admin_users.append(user_id)
            await db.set_setting("admin_users", admin_users)
            await message.answer(f"✅ Пользователь {user_id} назначен администратором")
            try:
                await message.bot.send_message(user_id, "🎉 Вам выданы права администратора!")
            except:
                pass
        else:
            await message.answer("❌ Пользователь уже является администратором")

    elif action == "remove_admin":
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
            await message.answer("❌ Пользователь не является администратором")

    elif action == "add_operator":
        operator_users = await db.get_setting("operator_users", [])
        if user_id not in operator_users:
            operator_users.append(user_id)
            await db.set_setting("operator_users", operator_users)
            await message.answer(f"✅ Пользователь {user_id} назначен оператором")
            try:
                await message.bot.send_message(
                    user_id,
                    f"🎉 Вам выданы права оператора!\n"
                    f"Операторский чат: {config.OPERATOR_CHAT_ID}"
                )
            except:
                pass
        else:
            await message.answer("❌ Пользователь уже является оператором")

    elif action == "remove_operator":
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
            await message.answer("❌ Пользователь не является оператором")

@router.message(AdminStates.waiting_for_message_to_user)
async def process_user_message(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("target_user_id")
    
    try:
        full_message = (
            f"📨 <b>Сообщение от администрации</b>\n\n"
            f"{message.text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📞 Поддержка: {config.SUPPORT_MANAGER}"
        )
        
        await message.bot.send_message(user_id, full_message, parse_mode="HTML")
        await message.answer(f"✅ Сообщение отправлено пользователю {user_id}")
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки: {e}")

@router.message(AdminStates.waiting_for_block_reason)
async def process_block_reason(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("target_user_id")
    reason = message.text
    
    try:
        user = await db.get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден")
            return
        
        if user.get('is_blocked'):
            await message.answer("❌ Пользователь уже заблокирован")
            return
        
        await db.update_user(user_id, is_blocked=True)
        await message.answer(f"✅ Пользователь {user_id} заблокирован\nПричина: {reason}")
        
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
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast_message(message: Message, state: FSMContext):
    data = await state.get_data()
    action = data.get("action")
    target_users = data.get("target_users", [])
    
    if not target_users and action == "broadcast_all":
        target_users = await db.get_all_users()
    
    try:
        sent_count = failed_count = 0
        
        await message.answer(f"📤 Начинаю рассылку для {len(target_users)} пользователей...")
        
        for user_id in target_users:
            try:
                await message.bot.copy_message(
                    chat_id=user_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                sent_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to send broadcast to {user_id}: {e}")
        
        await message.answer(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📤 Отправлено: {sent_count}\n"
            f"❌ Ошибок: {failed_count}",
            parse_mode="HTML"
        )
        
        builder = create_main_admin_panel()
        await message.answer("👑 <b>Панель администратора</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка рассылки: {e}")

async def find_user_by_username(username: str) -> int:
    try:
        async with aiosqlite.connect(db.db_path) as database:
            async with database.execute(
                'SELECT user_id FROM users WHERE username = ? COLLATE NOCASE',
                (username,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    except:
        return None

@router.message(Command("get_log"))
async def get_log_command(message: Message):
    if not await is_admin_extended(message.from_user.id):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Использование: /get_log filename.log")
            return
        
        filename = parts[1]
        if not filename.endswith('.log'):
            filename += '.log'
        
        if not os.path.exists(filename):
            await message.answer("❌ Файл не найден")
            return
        
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Берем последие 4000 символов (лимит Telegram)
        if len(content) > 4000:
            content = "...\n" + content[-4000:]
        
        await message.answer(f"📋 <b>Лог файл: {filename}</b>\n\n<code>{content}</code>", parse_mode="HTML")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения лога: {e}")

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
                channel_text = (
                    f"⭐️ <b>Отзыв о работе {config.EXCHANGE_NAME}</b>\n\n"
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