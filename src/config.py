import os
from dotenv import load_dotenv
import logging
from typing import Optional, List

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Config:
    """Klasa konfiguracyjna dla telegram.pump.bot"""
    
    def __init__(self):
        # Załaduj zmienne środowiskowe z pliku .env
        dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        if os.path.exists(dotenv_path):
            load_dotenv(dotenv_path)
            logger.info(f"Załadowano zmienne środowiskowe z: {dotenv_path}")
        else:
            logger.warning(f"Nie znaleziono pliku .env w {dotenv_path}, korzystanie ze zmiennych systemowych.")
        
        # Telethon konfiguracja
        self.telethon_bot_name = os.getenv("TELETHON_BOT_NAME")
        self.telethon_bot_token = os.getenv("TELETHON_BOT_TOKEN")
        self.telethon_api_phone = os.getenv("TELETHON_API_PHONE")
        self.telethon_api_id = os.getenv("TELETHON_API_ID")
        self.telethon_api_hash = os.getenv("TELETHON_API_HASH")
        self.telethon_user_id = os.getenv("TELETHON_USER_ID")
        self.telethon_bot_id = os.getenv("TELETHON_BOT_ID")
        
        # Telethon Controller - dodatkowa konfiguracja
        # TELEGRAM_SESSION_NAME: Nazwa sesji Telethon (plik .session)
        # Domyślnie: "pump_bot_session" - używane do przechowywania stanu sesji klienta
        self.telegram_session_name = os.getenv("TELEGRAM_SESSION_NAME", "pump_bot_session")
        
        # TELEGRAM_ADMIN_USERS: Lista ID użytkowników z uprawnieniami administratorskimi
        # Format: "123456789,987654321,555666777" (oddzielone przecinkami)
        # Opcjonalne - jeśli nie ustawione, brak administratorów będzie dostępnych
        # Usunięto system admin users
        
        # ENABLE_ERROR_RESPONSES: Czy bot powinien wysyłać wiadomości o błędach użytkownikom
        # Wartości: "true"/"false" (domyślnie: "true")
        # true: Użytkownicy otrzymują komunikaty o błędach w wiadomościach
        # false: Błędy są tylko logowane, bez informowania użytkowników
        self.enable_error_responses = os.getenv("ENABLE_ERROR_RESPONSES", "true").lower() == "true"
        
        # ENABLE_HANDLER_LOGGING: Czy włączyć szczegółowe logowanie handlerów
        # Wartości: "true"/"false" (domyślnie: "true") 
        # true: Loguje każde wywołanie handlera z informacjami o użytkowniku
        # false: Podstawowe logowanie bez szczegółów handlerów
        self.enable_handler_logging = os.getenv("ENABLE_HANDLER_LOGGING", "true").lower() == "true"
        
        # KuCoin API konfiguracja
        self.kucoin_api_secret = os.getenv("KUCOIN_API_SECRET")
        self.kucoin_api_key = os.getenv("KUCOIN_API_KEY")
        self.kucoin_api_key_passphrase = os.getenv("KUCOIN_API_KEY_PASSPHRASE")
        
        # MEXC API konfiguracja
        self.mexc_api_key = os.getenv("MEXC_API_KEY")
        self.mexc_api_secret = os.getenv("MEXC_API_SECRET")

        # Binance API konfiguracja
        self.binance_api_key = os.getenv("BINANCE_API_KEY")
        self.binance_api_secret = os.getenv("BINANCE_API_SECRET")
        
        # CryptoPanic API konfiguracja
        self.crypto_panic_api_key = os.getenv("CRYPTO_PANIC_API_KEY")

        # GNews API konfiguracja
        self.gnews_api_key = os.getenv("GNEWS_API_KEY")

        # CoinDesk API konfiguracja
        self.coindesk_api_key = os.getenv("COINDESK_API_KEY")
        
        # OpenAI API konfiguracja
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        
        # Database konfiguracja
        self.database_url = os.getenv("DATABASE_URL")
        self.test_database_url = os.getenv("TEST_DATABASE_URL")

        # Minio Storage konfiguracja
        self.minio_access_key = os.getenv("MINIO_ACCESS_KEY")
        self.minio_secret_key = os.getenv("MINIO_SECRET_KEY")
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT")
        self.minio_secure = os.getenv("MINIO_SECURE")
        self.minio_bucket_name = os.getenv("MINIO_BUCKET_NAME")

        # Local Storage konfiguracja
        self.local_storage_is_enabled = os.getenv("LOCAL_STORAGE_IS_ENABLED", "false").lower() == "true"
        self.local_storage_path = os.getenv("LOCAL_STORAGE_PATH")

        # Celery konfiguracja
        self.celery_broker_url = os.getenv("CELERY_BROKER_URL")
        self.celery_result_backend = os.getenv("CELERY_RESULT_BACKEND")

        # Walidacja wymaganych zmiennych
        self._validate_required_config()
    
    def _validate_required_config(self):
        """Walidacja wymaganych zmiennych konfiguracyjnych"""
        required_vars = {
            "TELETHON_BOT_TOKEN": self.telethon_bot_token,
            "TELETHON_API_ID": self.telethon_api_id,
            "TELETHON_API_HASH": self.telethon_api_hash,
            "KUCOIN_API_SECRET": self.kucoin_api_secret,
            "KUCOIN_API_KEY": self.kucoin_api_key,
            "KUCOIN_API_KEY_PASSPHRASE": self.kucoin_api_key_passphrase,
            "MEXC_API_KEY": self.mexc_api_key,
            "MEXC_API_SECRET": self.mexc_api_secret,
            "OPENAI_API_KEY": self.openai_api_key,
            "DATABASE_URL": self.database_url,
        }
        
        missing_vars = []
        for var_name, var_value in required_vars.items():
            if not var_value:
                missing_vars.append(var_name)
                logger.error(f"Nie znaleziono {var_name} w zmiennych środowiskowych.")
        
        if missing_vars:
            raise ValueError(f"Brak wymaganych zmiennych środowiskowych: {', '.join(missing_vars)}")
        
        # Ostrzeżenia dla opcjonalnych zmiennych
        if not self.telethon_bot_name:
            logger.warning("Nie znaleziono TELETHON_BOT_NAME w zmiennych środowiskowych.")
        
        if not self.telethon_api_phone:
            logger.warning("Nie znaleziono TELETHON_API_PHONE w zmiennych środowiskowych.")
        
        if not self.telethon_user_id:
            logger.warning("Nie znaleziono TELETHON_USER_ID w zmiennych środowiskowych.")
        
        if not self.telethon_bot_id:
            logger.warning("Nie znaleziono TELETHON_BOT_ID w zmiennych środowiskowych.")
        
        if not self.test_database_url:
            logger.warning("Nie znaleziono TEST_DATABASE_URL w zmiennych środowiskowych.")
        
        # Informacje o opcjonalnych zmiennych Telethon Controller
        # Usunięto sprawdzanie admin users
        
        # Informacje o konfiguracji Celery
        logger.info(f"Konfiguracja Celery: broker={self.celery_broker_url}, backend={self.celery_result_backend}")
            
        logger.info(f"Konfiguracja Telegram Controller: error_responses={self.enable_error_responses}, handler_logging={self.enable_handler_logging}")
    
    def get_telegram_admin_users(self) -> List[int]:
        """
        Parsuje i zwraca listę ID administratorów Telegram.
        
        Returns:
            List[int]: Lista ID użytkowników-administratorów
            
        Raises:
            ValueError: Jeśli format ID jest nieprawidłowy
        """
        if not self.telegram_admin_users_str:
            return []
        
        try:
            admin_ids = []
            for user_id in self.telegram_admin_users_str.split(","):
                user_id = user_id.strip()
                if user_id:  # Pomijaj puste stringi
                    admin_ids.append(int(user_id))
            return admin_ids
        except ValueError as e:
            logger.error(f"Błąd parsowania TELEGRAM_ADMIN_USERS: {e}")
            logger.error(f"Oczekiwany format: '123456789,987654321' - otrzymano: '{self.telegram_admin_users_str}'")
            raise ValueError(f"Nieprawidłowy format TELEGRAM_ADMIN_USERS: {e}")
    
    @property
    def telethon_config(self) -> dict:
        """Konfiguracja Telethon jako słownik (podstawowa konfiguracja API)"""
        return {
            'bot_name': self.telethon_bot_name,
            'bot_token': self.telethon_bot_token,
            'api_phone': self.telethon_api_phone,
            'api_id': self.telethon_api_id,
            'api_hash': self.telethon_api_hash,
            'user_id': self.telethon_user_id,
            'bot_id': self.telethon_bot_id
        }
    
    @property
    def telegram_controller_config(self) -> dict:
        """Konfiguracja TelegramController jako słownik (rozszerzona konfiguracja)"""
        return {
            'session_name': self.telegram_session_name,
            # Usunięto admin_users
            'enable_error_responses': self.enable_error_responses,
            'enable_handler_logging': self.enable_handler_logging
        }
    
    @property
    def kucoin_config(self) -> dict:
        """Konfiguracja KuCoin API jako słownik"""
        return {
            'api_secret': self.kucoin_api_secret,
            'api_key': self.kucoin_api_key,
            'api_key_passphrase': self.kucoin_api_key_passphrase
        }
    
    @property
    def mexc_config(self) -> dict:
        """Konfiguracja MEXC API jako słownik"""
        return {
            'api_key': self.mexc_api_key,
            'api_secret': self.mexc_api_secret
        }
    
    @property
    def binance_config(self) -> dict:
        """Konfiguracja Binance API jako słownik"""
        return {
            'api_key': self.binance_api_key,
            'api_secret': self.binance_api_secret
        }

    @property
    def openai_config(self) -> dict:
        """Konfiguracja OpenAI API jako słownik"""
        return {
            'api_key': self.openai_api_key
        }
    
    @property
    def crypto_panic_config(self) -> dict:
        """Konfiguracja CryptoPanic API jako słownik"""
        return {
            'api_key': self.crypto_panic_api_key
        }

    @property
    def gnews_config(self) -> dict:
        """Konfiguracja GNews API jako słownik"""
        return {
            'api_key': self.gnews_api_key
        }
    
    @property
    def coindesk_config(self) -> dict:
        """Konfiguracja CoinDesk API jako słownik"""
        return {
            'api_key': self.coindesk_api_key
        }

    @property
    def minio_config(self) -> dict:
        """Konfiguracja Minio jako słownik"""
        # Sprawdź czy wszystkie wymagane parametry są dostępne
        required_params = [self.minio_access_key, self.minio_secret_key, self.minio_endpoint]
        is_enabled = all(param is not None and param.strip() != "" for param in required_params)
        
        return {
            'access_key': self.minio_access_key,
            'secret_key': self.minio_secret_key,
            'endpoint': self.minio_endpoint,
            'secure': self.minio_secure,
            'bucket_name': self.minio_bucket_name,
            'is_enabled': is_enabled
        }

    @property
    def local_storage_config(self) -> dict:
        """Konfiguracja Local Storage jako słownik"""
        return {
            'is_enabled': self.local_storage_is_enabled,
            'storage_path': self.local_storage_path
        }
    
    @property
    def celery_config(self) -> dict:
        """Konfiguracja Celery jako słownik"""
        return {
            'broker_url': self.celery_broker_url,
            'result_backend': self.celery_result_backend
        }
    
    def get_api_config(self, exchange: str) -> Optional[dict]:
        """Pobierz konfigurację API dla określonej giełdy"""
        exchange_configs = {
            'kucoin': self.kucoin_config,
            'mexc': self.mexc_config
        }
        return exchange_configs.get(exchange.lower())

    def is_exchange_configured(self, exchange: str) -> bool:
        """Sprawdź czy giełda jest skonfigurowana"""
        config = self.get_api_config(exchange)
        if not config:
            return False
        
        # Sprawdź czy wszystkie wymagane klucze są obecne
        if exchange.lower() == 'kucoin':
            return all([config.get('api_secret'), config.get('api_key'), config.get('api_key_passphrase')])
        elif exchange.lower() == 'mexc':
            return all([config.get('api_key'), config.get('api_secret')])
        
        return False

    def get_database_url(self) -> str:
        """Pobierz URL bazy danych"""
        return self.database_url
    
    def get_test_database_url(self) -> str:
        """Pobierz URL testowej bazy danych"""
        if not self.test_database_url:
            logger.warning("TEST_DATABASE_URL nie jest ustawiony! Testy mogą działać niestabilnie.")
        return self.test_database_url

# Instancja globalna konfiguracji
config = Config()
