# keyboards/reply.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

class ReplyKeyboards:
    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Основное меню"""
        builder = ReplyKeyboardBuilder()
        
        # Первая строка
        builder.row(
            KeyboardButton(text="Купить"),
            KeyboardButton(text="Продать")
        )
        
        # Вторая строка
        builder.row(
            KeyboardButton(text="О сервисе ℹ️"),
            KeyboardButton(text="Калькулятор валют"),
        )
        
        # Третья строка
        builder.row(
            KeyboardButton(text="Оставить отзыв"),
            KeyboardButton(text="Как сделать обмен?")
        )
        
        # Четвертая строка
        builder.row(
            KeyboardButton(text="Друзья"),
            KeyboardButton(text="📊 Мои заявки"),
        )
        
        return builder.as_markup(
            resize_keyboard=True,
            persistent=True
        )
    
    @staticmethod
    def back_to_main() -> ReplyKeyboardMarkup:
        """Кнопка возврата в главное меню"""
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="◀️ Главное меню"))
        
        return builder.as_markup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
    
    @staticmethod
    def exchange_menu() -> ReplyKeyboardMarkup:
        """Меню обмена"""
        builder = ReplyKeyboardBuilder()
        
        builder.row(
            KeyboardButton(text="₽ → ₿ Рубли в Bitcoin"),
            KeyboardButton(text="₿ → ₽ Bitcoin в рубли")
        )
        builder.row(
            KeyboardButton(text="📊 Мои заявки"),
            KeyboardButton(text="📈 Курсы валют")
        )
        builder.row(
            KeyboardButton(text="◀️ Главное меню")
        )
        
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def payment_methods() -> ReplyKeyboardMarkup:
        """Способы оплаты"""
        builder = ReplyKeyboardBuilder()
        
        builder.row(
            KeyboardButton(text="💳 Банковская карта"),
            KeyboardButton(text="📱 СБП")
        )
        builder.row(
            KeyboardButton(text="◀️ Назад"),
            KeyboardButton(text="◀️ Главное меню")
        )
        
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def order_menu() -> ReplyKeyboardMarkup:
        """Меню заявки"""
        builder = ReplyKeyboardBuilder()
        
        builder.row(
            KeyboardButton(text="✅ Подтвердить заявку"),
            KeyboardButton(text="❌ Отменить заявку")
        )
        builder.row(
            KeyboardButton(text="🔄 Проверить статус"),
            KeyboardButton(text="◀️ Главное меню")
        )
        
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def contact_menu() -> ReplyKeyboardMarkup:
        """Меню контактов"""
        builder = ReplyKeyboardBuilder()
        
        builder.row(
            KeyboardButton(text="📞 Связаться с поддержкой"),
            KeyboardButton(text="💬 Написать в чат")
        )
        builder.row(
            KeyboardButton(text="🎫 Создать тикет"),
            KeyboardButton(text="❓ FAQ")
        )
        builder.row(
            KeyboardButton(text="◀️ Главное меню")
        )
        
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def admin_menu() -> ReplyKeyboardMarkup:
        """Административное меню (для приватного чата)"""
        builder = ReplyKeyboardBuilder()
        
        builder.row(
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="⚙️ Настройки")
        )
        builder.row(
            KeyboardButton(text="📢 Рассылка"),
            KeyboardButton(text="💰 Баланс")
        )
        builder.row(
            KeyboardButton(text="👥 Пользователи"),
            KeyboardButton(text="📋 Заявки")
        )
        builder.row(
            KeyboardButton(text="◀️ Выйти из админки")
        )
        
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def admin_chat_menu() -> ReplyKeyboardMarkup:
        """Административное меню для групповых чатов"""
        builder = ReplyKeyboardBuilder()
        
        builder.row(
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="⚙️ Настройки")
        )
        builder.row(
            KeyboardButton(text="📋 Заявки"),
            KeyboardButton(text="💰 Баланс")
        )
        builder.row(
            KeyboardButton(text="👥 Персонал"),
            KeyboardButton(text="🔧 Управление")
        )
        builder.row(
            KeyboardButton(text="❌ Скрыть панель")
        )
        
        return builder.as_markup(
            resize_keyboard=True,
            persistent=True
        )
    
    @staticmethod
    def remove_keyboard() -> ReplyKeyboardMarkup:
        """Удаление клавиатуры"""
        from aiogram.types import ReplyKeyboardRemove
        return ReplyKeyboardRemove()


# Сохраняем inline клавиатуры для специальных случаев
class InlineKeyboards:
    @staticmethod
    def order_actions(order_id: int):
        """Действия с заявкой (для сообщений)"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_order_{order_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_order_{order_id}")
        )
        return builder.as_markup()
    
    @staticmethod
    def operator_panel(order_id: int):
        """Панель оператора (для уведомлений)"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Оплачено", callback_data=f"op_paid_{order_id}"),
            InlineKeyboardButton(text="❌ Не оплачено", callback_data=f"op_not_paid_{order_id}")
        )
        builder.row(
            InlineKeyboardButton(text="⚠️ Проблема", callback_data=f"op_problem_{order_id}"),
            InlineKeyboardButton(text="📝 Заметка", callback_data=f"op_note_{order_id}")
        )
        return builder.as_markup()
    
    @staticmethod
    def confirmation(action: str, data: str = ""):
        """Подтверждение действий"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_{action}_{data}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"cancel_{action}_{data}")
        )
        return builder.as_markup()
    
    @staticmethod
    def admin_chat_quick_menu():
        """Быстрое меню для групповых чатов"""
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
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
            InlineKeyboardButton(text="👥 Персонал", callback_data="admin_staff"),
            InlineKeyboardButton(text="🔧 Управление", callback_data="admin_management")
        )
        return builder.as_markup()