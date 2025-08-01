from asyncio.log import logger
import aiosqlite
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import config
import os



class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
    

        
    async def get_commission_percentage(self):
        return await self.get_setting("commission_percentage", float(os.getenv('COMMISSION_PERCENT', '20.0')))



    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone_number TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_blocked BOOLEAN DEFAULT FALSE,
                    referral_code TEXT,
                    referred_by INTEGER,
                    total_operations INTEGER DEFAULT 0,
                    total_amount REAL DEFAULT 0
                )
            ''')
            
            await self._migrate_users_table(db)
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    onlypays_id TEXT,
                    amount_rub REAL NOT NULL,
                    amount_btc REAL,
                    btc_address TEXT NOT NULL,
                    rate REAL NOT NULL,
                    total_amount REAL NOT NULL,
                    payment_type TEXT NOT NULL,
                    status TEXT DEFAULT 'waiting',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    requisites TEXT,
                    is_problematic BOOLEAN DEFAULT FALSE,
                    operator_notes TEXT,
                    personal_id TEXT
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS captcha_sessions (
                    user_id INTEGER PRIMARY KEY,
                    answer TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS referral_bonuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT DEFAULT 'pending'
                )
            ''')

            await db.commit()

    async def _migrate_users_table(self, db):
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'referral_count' not in column_names:
            await db.execute('ALTER TABLE users ADD COLUMN referral_count INTEGER DEFAULT 0')
        
        await db.commit()

    async def add_user(self, user_id: int, username: str = None, 
                      first_name: str = None, last_name: str = None) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        
        fields = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f'UPDATE users SET {fields} WHERE user_id = ?', values)
            await db.commit()






    async def create_order(self, user_id: int, amount_rub: float, amount_btc: float,
                        btc_address: str, rate: float, total_amount: float, payment_type: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute('''
                INSERT INTO orders (user_id, amount_rub, amount_btc, btc_address, rate, total_amount, payment_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, amount_rub, amount_btc, btc_address, rate, total_amount, payment_type))
            await db.commit()
            return cursor.lastrowid






    async def get_order(self, order_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM orders WHERE id = ?', (order_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def save_review(self, user_id: int, text: str):
        async with aiosqlite.connect(self.db_path) as db:
            current_time = datetime.now().isoformat()
            
            cursor = await db.execute(
                'INSERT INTO reviews (user_id, text, created_at, status) VALUES (?, ?, ?, ?)',
                (user_id, text, current_time, 'pending')
            )
            await db.commit()
            return cursor.lastrowid

    async def get_last_review_time(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                'SELECT created_at FROM reviews WHERE user_id = ? ORDER BY created_at DESC LIMIT 1',
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return datetime.fromisoformat(row[0])
                return None

    async def update_review_status(self, review_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                'UPDATE reviews SET status = ? WHERE id = ?',
                (status, review_id)
            )
            await db.commit()

    async def update_order(self, order_id: int, **kwargs):
        """Обновление заказа"""
        if not kwargs:
            return
        
        # Добавляем personal_id в список возможных полей для обновления
        allowed_fields = ['onlypays_id', 'status', 'requisites', 'personal_id']
        
        set_clause = []
        values = []
        
        for field, value in kwargs.items():
            if field in allowed_fields:
                set_clause.append(f"{field} = ?")
                values.append(value)
        
        if set_clause:
            values.append(order_id)
            query = f"UPDATE orders SET {', '.join(set_clause)} WHERE id = ?"
            await self.execute_query(query, tuple(values))

    async def get_user_orders(self, user_id: int, limit: int = 10) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM orders WHERE user_id = ? 
                ORDER BY created_at DESC LIMIT ?
            ''', (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_setting(self, key: str, default: Any = None) -> Any:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except:
                        return row[0]
                return default

    async def set_setting(self, key: str, value: Any):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        else:
            value = str(value)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
            ''', (key, value))
            await db.commit()

    async def get_all_users(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT user_id FROM users WHERE is_blocked = FALSE') as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    async def create_captcha_session(self, user_id: int, answer: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO captcha_sessions (user_id, answer, attempts)
                VALUES (?, ?, 0)
            ''', (user_id, answer))
            await db.commit()

    async def get_captcha_session(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM captcha_sessions WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def delete_captcha_session(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('DELETE FROM captcha_sessions WHERE user_id = ?', (user_id,))
            await db.commit()

    async def update_referral_count(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                async with db.execute(
                    'SELECT COUNT(*) FROM users WHERE referred_by = ?', 
                    (user_id,)
                ) as cursor:
                    count = (await cursor.fetchone())[0]
                    logger.info(f"Referral bonus for user {user_id}")
                
                await db.execute(
                    'UPDATE users SET referral_count = ? WHERE user_id = ?',
                    (count, user_id)
                )
                await db.commit()
                return count
            except:
                return 0

    async def get_referral_stats(self, user_id: int):
        """Получение статистики рефералов"""
        try:
            # Получаем количество рефералов
            query1 = "SELECT COUNT(*) as count FROM users WHERE referred_by = ?"
            result1 = await self.execute_query(query1, (user_id,))
            
            # execute_query возвращает список, берем первый элемент
            referral_count = 0
            if result1 and len(result1) > 0:
                referral_count = result1[0]['count'] if 'count' in result1[0] else result1[0][0]
            
            # Получаем баланс рефералов (можно добавить таблицу для этого)
            # Пока возвращаем 0, позже можно добавить логику расчета
            referral_balance = 0
            
            return {
                'referral_count': referral_count,
                'referral_balance': referral_balance
            }
        except Exception as e:
            logger.error(f"Get referral stats error: {e}")
            return {
                'referral_count': 0,
                'referral_balance': 0
            }

    async def add_referral_bonus(self, user_id: int, amount: float):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR IGNORE INTO referral_bonuses 
                (user_id, amount, created_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, amount))
            await db.commit()

    async def execute_query(self, query: str, params: tuple = ()):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params)
            await db.commit()

    async def get_statistics(self) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('SELECT COUNT(*) FROM users') as cursor:
                total_users = (await cursor.fetchone())[0]
            
            async with db.execute('SELECT COUNT(*) FROM orders') as cursor:
                total_orders = (await cursor.fetchone())[0]
            
            async with db.execute('SELECT COUNT(*) FROM orders WHERE status = "finished"') as cursor:
                completed_orders = (await cursor.fetchone())[0]
            
            async with db.execute('SELECT SUM(total_amount) FROM orders WHERE status = "finished"') as cursor:
                total_volume = (await cursor.fetchone())[0] or 0
            
            async with db.execute('''
                SELECT COUNT(*) FROM orders 
                WHERE DATE(created_at) = DATE('now')
            ''') as cursor:
                today_orders = (await cursor.fetchone())[0]
            
            async with db.execute('''
                SELECT SUM(total_amount) FROM orders 
                WHERE DATE(created_at) = DATE('now') AND status = "finished"
            ''') as cursor:
                today_volume = (await cursor.fetchone())[0] or 0
            
            return {
                'total_users': total_users,
                'total_orders': total_orders,
                'completed_orders': completed_orders,
                'total_volume': total_volume,
                'today_orders': today_orders,
                'today_volume': today_volume,
                'completion_rate': (completed_orders / total_orders * 100) if total_orders > 0 else 0
            }

    async def is_chat_admin(self, chat_id: int, user_id: int) -> bool:
        try:
            admin_chats = [config.ADMIN_CHAT_ID, config.OPERATOR_CHAT_ID]
            return chat_id in admin_chats and await self.has_admin_rights(user_id)
        except:
            return False

    async def has_admin_rights(self, user_id: int) -> bool:
        if user_id == config.ADMIN_CHAT_ID:
            return True
        
        admin_users = await self.get_setting("admin_users", [])
        operator_users = await self.get_setting("operator_users", [])
        
        return user_id in admin_users or user_id in operator_users

    async def add_admin_chat(self, chat_id: int, chat_title: str = ""):
        admin_chats = await self.get_setting("admin_chats", [])
        if chat_id not in admin_chats:
            admin_chats.append(chat_id)
            await self.set_setting("admin_chats", admin_chats)
            await self.set_setting(f"chat_{chat_id}_title", chat_title)




    async def get_review(self, review_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM reviews WHERE id = ?', (review_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None