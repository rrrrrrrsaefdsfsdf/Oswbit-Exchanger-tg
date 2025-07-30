from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatType
from config import config

class PrivateChatMiddleware(BaseMiddleware):
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        
        if isinstance(event, Message):
            chat = event.chat
            user_id = event.from_user.id
            message_text = event.text or ""
        elif isinstance(event, CallbackQuery) and event.message:
            chat = event.message.chat
            user_id = event.from_user.id
            message_text = event.data or ""
        else:
            return await handler(event, data)
        
        super_admins = [config.ADMIN_USER_ID]
        if user_id in super_admins:
            return await handler(event, data)
        
        from database.models import Database
        db = Database(config.DATABASE_URL)
        
        try:
            admin_users = await db.get_setting("admin_users", [])
            operator_users = await db.get_setting("operator_users", [])
            is_staff = user_id in admin_users or user_id in operator_users
        except:
            is_staff = False
        
        if is_staff:
            return await handler(event, data)
        
        admin_commands = [
            "/admin", "/grant_admin", "/grant_operator", "/revoke_admin", 
            "/revoke_operator", "/my_id", "/list_staff", "/get_my_id",
            "/setup_admin_chat", "/set_percentage", "/toggle_captcha",
            "/user_info", "/block_user", "/unblock_user", "/search_user",
            "/recent_users", "/user_stats", "/send_message", "/check_captcha",
            "/recent_orders", "/pending_orders", "/order_info", 
            "/complete_order", "/cancel_order", "/set_limits", "/set_welcome"
        ]
        
        admin_buttons = [
            "📊 Статистика", "⚙️ Настройки", "📋 Заявки", 
            "💰 Баланс", "👥 Персонал", "🔧 Управление",
            "❌ Скрыть панель", "📢 Рассылка", "👥 Пользователи",
            "◀️ Выйти из админки"
        ]
        
        admin_callbacks = [
            "admin_", "order_", "user_", "staff_", "settings_",
            "op_", "confirm_", "cancel_"
        ]
        
        if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
            if isinstance(event, CallbackQuery):
                if any(event.data.startswith(prefix) for prefix in admin_callbacks):
                    await event.answer("❌ У вас нет прав", show_alert=True)
                    return
                else:
                    await event.answer("❌ Кнопки недоступны в групповых чатах", show_alert=True)
                    return
            
            if isinstance(event, Message):
                if message_text.startswith("/"):
                    if any(message_text.startswith(cmd) for cmd in admin_commands):
                        await event.answer("❌ У вас нет прав для выполнения этой команды")
                        return
                    else:
                        await event.answer("❌ В групповых чатах доступны только административные команды")
                        return
                elif message_text in admin_buttons:
                    await event.answer("❌ У вас нет прав администратора")
                    return
                else:
                    return
            
            return
        
        if isinstance(event, Message):
            if message_text.startswith("/"):
                if any(message_text.startswith(cmd) for cmd in admin_commands):
                    await event.answer("❌ У вас нет прав для выполнения этой команды")
                    return
                
                allowed_user_commands = ["/start", "/help"]
                if any(message_text.startswith(cmd) for cmd in allowed_user_commands):
                    return await handler(event, data)
                
                await event.answer("❌ Команда недоступна")
                return
            
            if chat.type == ChatType.PRIVATE:
                if message_text in admin_buttons:
                    await event.answer("❌ У вас нет доступа к админ-панели")
                    return
                
                return await handler(event, data)
        
        elif isinstance(event, CallbackQuery):
            if any(event.data.startswith(prefix) for prefix in admin_callbacks):
                await event.answer("❌ У вас нет прав", show_alert=True)
                return
            
            if chat.type == ChatType.PRIVATE:
                return await handler(event, data)
        
        return await handler(event, data)