import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from config import config
from database.models import Database
from handlers import user, admin, operator, calculator
from middlewares.chat_type import PrivateChatMiddleware

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

dp.include_router(admin.router)
dp.include_router(user.router)
dp.include_router(operator.router)
dp.include_router(calculator.router)

dp.message.middleware(PrivateChatMiddleware())
dp.callback_query.middleware(PrivateChatMiddleware())

async def init_database():
    db = Database(config.DATABASE_URL)
    await db.init_db()
    logger.info("Database initialized")

async def on_startup():
    await init_database()
    await bot.set_webhook(url=config.WEBHOOK_URL + config.WEBHOOK_PATH, drop_pending_updates=True)
    logger.info("Webhook set successfully")

async def on_shutdown():
    await bot.delete_webhook()
    logger.info("Webhook deleted")

def create_app() -> web.Application:
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app



async def run_polling():
    logger.info("Starting bot in polling mode")
    try:
        await init_database()
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.session.close()

async def main():
    mode = os.getenv('BOT_MODE', 'polling').lower()
    # if mode == 'webhook':
    #     await run_webhook()
    # else:
    await run_polling()

if __name__ == "__main__":
    asyncio.run(main())