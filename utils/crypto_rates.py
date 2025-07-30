from asyncio.log import logger
import datetime
from typing import Dict

import aiohttp


@classmethod
async def get_crypto_rates(cls) -> Dict[str, float]:
    # Оставляем только BTC
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': 'bitcoin',
                'vs_currencies': 'rub'
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    cls._rates_cache = {
                        'BTC': data.get('bitcoin', {}).get('rub', 2800000)
                    }
                    cls._cache_time = datetime.now()
                    
                    return cls._rates_cache
    
    except Exception as e:
        logger.error(f"Error fetching crypto rates: {e}")
    
    return {'BTC': 2800000.0}