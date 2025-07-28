from .comunication import TelegramAPI
from .llms import OpenaiAPI
from .exchanges import BinanceAPI, MexcAPI, KucoinAPI
from .news_services import CryptoPanicService

from ..config import config

class ApiFabric:

    def __init__(self):
        self.config = config

    def get_telegram_api(self):
        return TelegramAPI(
            *self.config.telethon_config()
        )
    
    def get_openai_api(self):
        return OpenaiAPI(
            *self.config.openai_config()
        )
    
    def get_binance_api(self):
        return BinanceAPI(
            *self.config.binance_config()
        )

    def get_mexc_api(self):
        return MexcAPI(
            *self.config.mexc_config()
        )

    def get_kucoin_api(self):
        return KucoinAPI(
            *self.config.kucoin_config()
        )
    
    def get_crypto_panic_api(self, currencies: List[str] = None):
        config = self.config.crypto_panic_config()
        if currencies is not None:
            config['currencies'] = currencies
        return CryptoPanicService(
            *config,
        )

    def get_news_services_apis(self, currencies: List[str] = None):
        return [
            self.get_crypto_panic_api(currencies)
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
    
    
    