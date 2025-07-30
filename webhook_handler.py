# webhook_handler.py
from aiohttp import web
import json
import logging
from database.models import Database
from handlers.operator import notify_operators
from config import config

logger = logging.getLogger(__name__)

db = Database(config.DATABASE_URL)

async def webhook_handler(request):
    """Обработчик webhook от OnlyPays"""
    try:
        data = await request.json()
        logger.info(f"Webhook received: {data}")
        
        # Проверка подписи (в реальном проекте)
        # if not verify_signature(request, data):
        #     return web.Response(status=403)
        
        order_id = data.get('personal_id')
        status = data.get('status')
        received_amount = data.get('received_amount')
        
        if not order_id:
            return web.Response(status=400, text="Missing order_id")
        
        order = await db.get_order(int(order_id))
        if not order:
            return web.Response(status=404, text="Order not found")
        
        # Обновляем статус заявки
        await db.update_order(int(order_id), status=status)
        
        # Определяем, проблемная ли заявка
        is_problematic = False
        if received_amount and abs(received_amount - order['total_amount']) > 1:
            is_problematic = True
            await db.update_order(int(order_id), is_problematic=True)
        
        # Уведомляем операторов
        from main import bot
        await notify_operators(bot, int(order_id), is_problematic)
        
        return web.Response(status=200, text="OK")
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500, text="Internal error")

# Добавить в main.py:
# app.router.add_post('/webhook/onlypays', webhook_handler)