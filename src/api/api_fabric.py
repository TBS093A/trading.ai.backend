from .comunication import TelegramAPI
from .llms import OpenaiAPI
from .exchanges import BinanceAPI, MexcAPI, KucoinAPI, YahooFinanceAPI
from .news_services import CryptoPanicService, GNewsService, CoinDeskService
from .storage import MinIOStorage, LocalStorage
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

    def get_yahoofinance_api(self):
        return YahooFinanceAPI()
    
    def get_crypto_panic_api(self):
        return CryptoPanicService(
            **self.config.crypto_panic_config,
        )
        
    def get_gnews_api(self):
        return GNewsService(
            **self.config.gnews_config,
        )

    def get_coindesk_api(self):
        return CoinDeskService(
            **self.config.coindesk_config,
        )

    def get_minio_storage(self):
        return MinIOStorage(
            **self.config.minio_config,
        )

    def get_local_storage(self):
        return LocalStorage(
            **self.config.local_storage_config,
        )

    def get_news_services_apis(self):
        return [
            #self.get_crypto_panic_api(),
            #self.get_gnews_api(),
            self.get_coindesk_api()
        ]

    def get_exchanges_apis(self):
        return [
            self.get_binance_api(),
            self.get_mexc_api(),
            # self.get_kucoin_api()
            self.get_yahoofinance_api(),
        ]

    def get_llm_apis(self):
        return [
            self.get_openai_api()
        ]

    def get_communication_apis(self):
        return [
            self.get_telegram_api()
        ]
    
    def get_storage_apis(self):
        return [
            self.get_minio_storage(),
            self.get_local_storage()
        ]
    