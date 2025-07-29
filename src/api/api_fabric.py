from .comunication import TelegramAPI
from .llms import OpenaiAPI
from .exchanges import BinanceAPI, MexcAPI, KucoinAPI
from .news_services import CryptoPanicService, GNewsService
from typing import List

from ..config import config

class ApiFabric:

    def __init__(self):
        self.config = config

    def get_telegram_api(self):
        return TelegramAPI(
            **self.config.telethon_config
        )
    
    def get_openai_api(self):
        return OpenaiAPI(
            **self.config.openai_config
        )
    
    def get_binance_api(self):
        return BinanceAPI(
            **self.config.binance_config
        )

    def get_mexc_api(self):
        return MexcAPI(
            **self.config.mexc_config
        )

    def get_kucoin_api(self):
        return KucoinAPI(
            **self.config.kucoin_config
        )
    
    def get_crypto_panic_api(self):
        return CryptoPanicService(
            **self.config.crypto_panic_config,
        )
        
    def get_gnews_api(self):
        return GNewsService(
            **self.config.gnews_config,
        )

    def get_news_services_apis(self):
        return [
            self.get_crypto_panic_api(),
            self.get_gnews_api()
        ]

    def get_exchanges_apis(self):
        return [
            self.get_binance_api(),
            self.get_mexc_api(),
            self.get_kucoin_api()
        ]

    def get_communication_apis(self):
        return [
            self.get_telegram_api()
        ]
    
    
    