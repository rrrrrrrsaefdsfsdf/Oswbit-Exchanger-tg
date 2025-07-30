# webhook.py
import logging
from aiohttp import web
from database.models import Database
from config import config

async def handle_payment_notification(request):
    try:
        data = await request.json()
        order_id = data.get("id")
        status = data.get("status")
        personal_id = data.get("personal_id")
        received_sum = data.get("received_sum")

        db = Database(config.DATABASE_URL)
        if status == "finished":
            await db.update_order(personal_id, status="finished", received_sum=received_sum)
            order = await db.get_order(personal_id)
            if order:
                await bot.send_message(
                    order["user_id"],
                    f"✅ Заявка #{personal_id} выполнена!\n"
                    f"Получено: {received_sum:,.0f} ₽\n"
                    f"Bitcoin {'отправлен на адрес' if order['direction'] == 'rub_to_crypto' else 'получен'}.",
                    parse_mode="HTML"
                )
        return web.json_response({"success": True})
    except Exception as e:
        logging.error(f"Notification error: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=400)

app = web.Application()
app.add_routes([web.post("/onlypays/notification", handle_payment_notification)])

async def start_webhook():
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()