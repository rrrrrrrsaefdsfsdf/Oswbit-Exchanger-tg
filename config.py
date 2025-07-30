import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    BOT_MODE = os.getenv("BOT_MODE", 'polling')
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
    WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
    WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", 8080))
    
    ONLYPAYS_API_ID = os.getenv("ONLYPAYS_API_ID")
    ONLYPAYS_SECRET_KEY = os.getenv("ONLYPAYS_SECRET_KEY")
    ONLYPAYS_PAYMENT_KEY = os.getenv("ONLYPAYS_PAYMENT_KEY")
    
    DATABASE_URL = os.getenv("DATABASE_URL", "oswbit.db")
    
    ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", 0))
    ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", 0))
    OPERATOR_CHAT_ID = int(os.getenv("OPERATOR_CHAT_ID", 0))
    
    REVIEWS_CHANNEL_ID = -1002675929051
    
    CAPTCHA_ENABLED = os.getenv("CAPTCHA_ENABLED", "true").lower() == "true"
    ADMIN_PERCENTAGE = float(os.getenv("ADMIN_PERCENTAGE", 5.0))
    MIN_AMOUNT = int(os.getenv("MIN_AMOUNT", 1000))
    MAX_AMOUNT = int(os.getenv("MAX_AMOUNT", 500000))
    
    BOT_USERNAME = os.getenv("BOT_USERNAME", "OswbitExchanger_bot")
    
    EXCHANGE_NAME = os.getenv("EXCHANGE_NAME", "Oswbit Exchanger")
    SUPPORT_CHAT = os.getenv("SUPPORT_CHAT", "@")
    SUPPORT_MANAGER = os.getenv("SUPPORT_MANAGER", "@")
    NEWS_CHANNEL = os.getenv("NEWS_CHANNEL", "@")
    REVIEWS_CHANNEL = os.getenv("REVIEWS_CHANNEL", "@")

config = Config()