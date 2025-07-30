# api/onlypays.py
import aiohttp
import json
import logging
from typing import Dict, Optional, Union
from config import config

logger = logging.getLogger(__name__)

class OnlyPaysAPI:
    BASE_URL = "https://onlypays.net"
    
    def __init__(self):
        self.api_id = config.ONLYPAYS_API_ID
        self.secret_key = config.ONLYPAYS_SECRET_KEY
        self.payment_key = config.ONLYPAYS_PAYMENT_KEY

    async def _make_request(self, endpoint: str, data: Dict) -> Dict:
        """Заглушка для API запросов"""
        logger.info(f"API Request to {endpoint}: {data}")
        
        # Заглушки для разных эндпоинтов
        if endpoint == "/get_requisite":
            return await self._mock_create_order(data)
        elif endpoint == "/get_status":
            return await self._mock_get_status(data)
        elif endpoint == "/cancel_order":
            return await self._mock_cancel_order(data)
        elif endpoint == "/get_balance":
            return await self._mock_get_balance(data)
        elif endpoint == "/create_payout":
            return await self._mock_create_payout(data)
        elif endpoint == "/payout_status":
            return await self._mock_payout_status(data)
        
        return {"error": "Unknown endpoint"}

    async def _mock_create_order(self, data: Dict) -> Dict:
        """Заглушка для создания заявки"""
        import random
        import string
        
        order_id = ''.join(random.choices(string.digits, k=8))
        
        if data.get("payment_type") == "card":
            return {
                "id": order_id,
                "card_number": "1234 5678 9012 3456",
                "cardholder_name": "IVAN PETROV",
                "bank": "Сбербанк",
                "payment_type": "card"
            }
        else:  # sbp
            return {
                "id": order_id,
                "phone": "+79001234567",
                "recipient_name": "Иван Петров",
                "bank": "Сбербанк",
                "payment_type": "sbp"
            }

    async def _mock_get_status(self, data: Dict) -> Dict:
        """Заглушка для проверки статуса"""
        import random
        
        statuses = ["waiting", "finished"]
        status = random.choice(statuses)
        
        result = {
            "status": status,
            "personal_id": data.get("id", ""),
        }
        
        if status == "finished":
            result["received_amount"] = data.get("amount", 0)
        
        return result

    async def _mock_cancel_order(self, data: Dict) -> Dict:
        """Заглушка для отмены заявки"""
        return {"status": "cancelled"}

    async def _mock_get_balance(self, data: Dict) -> Dict:
        """Заглушка для получения баланса"""
        return {"balance": 150000.50}

    async def _mock_create_payout(self, data: Dict) -> Dict:
        """Заглушка для создания выплаты"""
        import random
        import string
        
        payout_id = ''.join(random.choices(string.digits, k=8))
        return {"id": payout_id, "status": "processing"}

    async def _mock_payout_status(self, data: Dict) -> Dict:
        """Заглушка для статуса выплаты"""
        import random
        
        statuses = ["processing", "completed", "failed"]
        return {"status": random.choice(statuses)}

    async def create_order(self, amount_rub: float, payment_type: str, 
                          personal_id: Optional[str] = None, trans: bool = False) -> Dict:
        """Создание заявки на оплату"""
        data = {
            "api_id": self.api_id,
            "secret_key": self.secret_key,
            "amount_rub": amount_rub,
            "payment_type": payment_type
        }
        
        if personal_id:
            data["personal_id"] = personal_id
        if trans:
            data["trans"] = "true"
            
        return await self._make_request("/get_requisite", data)

    async def get_order_status(self, order_id: str) -> Dict:
        """Получение статуса заявки"""
        data = {
            "api_id": self.api_id,
            "secret_key": self.secret_key,
            "id": order_id
        }
        
        return await self._make_request("/get_status", data)

    async def cancel_order(self, order_id: str) -> Dict:
        """Отмена заявки"""
        data = {
            "api_id": self.api_id,
            "secret_key": self.secret_key,
            "id": order_id
        }
        
        return await self._make_request("/cancel_order", data)

    async def get_balance(self) -> Dict:
        """Получение баланса"""
        data = {
            "api_id": self.api_id,
            "payment_key": self.payment_key
        }
        
        return await self._make_request("/get_balance", data)

    async def create_payout(self, payout_type: str, amount: float, 
                           requisite: str, bank: str, personal_id: str) -> Dict:
        """Создание выплаты"""
        data = {
            "api_id": self.api_id,
            "payment_key": self.payment_key,
            "type": payout_type,
            "amount": amount,
            "requisite": requisite,
            "bank": bank,
            "personal_id": personal_id
        }
        
        return await self._make_request("/create_payout", data)

    async def get_payout_status(self, payout_id: str) -> Dict:
        """Получение статуса выплаты"""
        data = {
            "api_id": self.api_id,
            "payment_key": self.payment_key,
            "id": payout_id
        }
        
        return await self._make_request("/payout_status", data)

# Глобальный экземпляр API
onlypays_api = OnlyPaysAPI()