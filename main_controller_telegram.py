#!/usr/bin/env python3
"""
Główny kontroler Telegram Bot z systemem routingu domenowego.

Ten plik zawiera główną logikę uruchamiania bota Telegram
z wykorzystaniem nowego systemu routingu dla separacji logiki
handlerów w klasy domenowe.

Funkcjonalności:
- Inicjalizacja klienta Telethon
- Montowanie domen handlerów
- Zarządzanie cyklem życia aplikacji
- Obsługa błędów i logowanie

Autor: AI Assistant
"""

import asyncio
import logging
import traceback
import os
import sys
from typing import Dict, Optional, Any
from datetime import datetime

# Dodaj katalog src do ścieżki Python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from telethon import TelegramClient, events
    from telethon.errors import SessionPasswordNeededError, ApiIdInvalidError, PhoneCodeInvalidError
except ImportError as e:
    logging.error(f"Błąd importu Telethon: {e}")
    logging.error("Zainstaluj Telethon: pip install telethon")
    sys.exit(1)

# Import systemu routingu
from src.controller_telegram_utils_router import ClassRouter, DomainBase

# Import domen
from src.controller_telegram_domain_example import PumpBotExampleDomain
from src.controller_telegram_domain_sync_system import SystemTelegramControllerDomain
from src.controller_telegram_domain_assets import AssetsTelegramControllerDomain
from src.controller_telegram_domain_exchanges import ExchangesTelegramControllerDomain
from src.controller_telegram_domain_wallets import WalletsTelegramControllerDomain
from src.controller_telegram_domain_strategies import StrategiesTelegramControllerDomain
from src.controller_telegram_domain_transactions import TransactionsTelegramControllerDomain

# Import utilities
from src.controller_telegram_utils_ui import TelegramUIUtils
from src.controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, UserPermissionLevel

# Import istniejącej konfiguracji
from src.config import config

# Konfiguracja logowania
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("telegram_bot.log")
    ]
)
logger = logging.getLogger(__name__)

# Niestandardowe drukowanie z użyciem loggera
print = logger.info


class TelegramController:
    """
    Główny kontroler bota Telegram z systemem routingu domenowego.
    
    Odpowiada za:
    - Inicjalizację i konfigurację klienta Telethon
    - Montowanie i zarządzanie domenami handlerów
    - Obsługę cyklu życia aplikacji
    - Centralne logowanie i monitoring
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja kontrolera Telegram.
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.client: Optional[TelegramClient] = None
        self.router: Optional[ClassRouter] = None
        self.domains: Dict[str, BaseTelegramControllerDomain] = {}
        
        # UI Utils integration
        self.ui_utils = TelegramUIUtils()
        
        # Statistyki aplikacji
        self.stats = {
            "start_time": datetime.now(),
            "domains_loaded": 0,
            "routes_registered": 0,
            "uptime_seconds": 0
        }
        
        # Używamy istniejącej konfiguracji
        self.config = config
        
        # Pobieramy konfigurację TelegramController z Config
        controller_config = self.config.telegram_controller_config
        
        self.session_name = controller_config['session_name']
        self.admin_users = controller_config['admin_users']
        self.enable_error_responses = controller_config['enable_error_responses']
        self.enable_logging = controller_config['enable_handler_logging']
        
        logger.info(f"🚀 Inicjalizacja TelegramController (test_mode={test_mode})")
        logger.info(f"📋 Konfiguracja załadowana z klasy Config")
        logger.info(f"🗂️ Sesja: {self.session_name}")
        logger.info(f"👥 Administratorów: {len(self.admin_users)}")
        logger.info(f"🔧 Error responses: {self.enable_error_responses}")
        logger.info(f"📝 Handler logging: {self.enable_logging}")
    
    def _validate_telegram_config(self) -> None:
        """
        Waliduje konfigurację Telethon z klasy Config.
        """
        # Klasa Config już wykonuje podstawową walidację,
        # ale dodajemy dodatkowe sprawdzenia specyficzne dla TelegramController
        telethon_config = self.config.telethon_config
        
        # Sprawdź czy API ID jest liczbą
        if telethon_config['api_id']:
            try:
                int(telethon_config['api_id'])
            except (ValueError, TypeError):
                raise ValueError("TELETHON_API_ID musi być liczbą")
        
        logger.info("✅ Konfiguracja Telethon zwalidowana pomyślnie")
    
    async def _init_client(self) -> TelegramClient:
        """
        Inicjalizuje i konfiguruje klienta Telethon.
        
        Returns:
            Skonfigurowana instancja TelegramClient
            
        Raises:
            Exception: Jeśli nie można zainicjalizować klienta
        """
        try:
            logger.info("🔌 Inicjalizacja klienta Telethon...")
            
            # Walidacja konfiguracji przed utworzeniem klienta
            self._validate_telegram_config()
            
            telethon_config = self.config.telethon_config
            
            client = TelegramClient(
                session=self.session_name,
                api_id=int(telethon_config['api_id']),
                api_hash=telethon_config['api_hash']
            )
            
            # Uruchomienie jako bot
            logger.info("🤖 Logowanie jako bot...")
            await client.start(bot_token=telethon_config['bot_token'])
            
            # Sprawdzenie czy bot jest aktywny
            me = await client.get_me()
            logger.info(f"✅ Bot połączony: @{me.username} ({me.first_name})")
            
            return client
            
        except ApiIdInvalidError:
            logger.error("❌ Nieprawidłowe API ID lub API Hash")
            raise
        except Exception as e:
            logger.error(f"❌ Błąd inicjalizacji klienta: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def _init_router(self) -> ClassRouter:
        """
        Inicjalizuje system routingu.
        
        Returns:
            Skonfigurowana instancja ClassRouter
        """
        logger.info("🛤️ Inicjalizacja systemu routingu...")
        
        router = ClassRouter(
            enable_logging=self.enable_logging,
            enable_error_responses=self.enable_error_responses
        )
        
        logger.info("✅ System routingu zainicjalizowany")
        return router
    
    def _register_domains(self) -> None:
        """
        Rejestruje wszystkie domeny handlerów w routerze.
        """
        logger.info("📚 Rejestracja domen handlerów...")
        
        # Domena systemowa - SystemTelegramControllerDomain
        system_domain = SystemTelegramControllerDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(system_domain, "system")
        
        # Przykładowa domena - PumpBotExampleDomain
        example_domain = PumpBotExampleDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(example_domain, "pump_example")
        
        # Domena assetów - AssetsTelegramControllerDomain
        assets_domain = AssetsTelegramControllerDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(assets_domain, "assets")
        
        # Domena giełd - ExchangesTelegramControllerDomain
        exchanges_domain = ExchangesTelegramControllerDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(exchanges_domain, "exchanges")
        
        # Domena portfeli - WalletsTelegramControllerDomain
        wallets_domain = WalletsTelegramControllerDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(wallets_domain, "wallets")
        
        # Domena strategii - StrategiesTelegramControllerDomain
        strategies_domain = StrategiesTelegramControllerDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(strategies_domain, "strategies")
        
        # Domena transakcji - TransactionsTelegramControllerDomain
        transactions_domain = TransactionsTelegramControllerDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self._register_single_domain(transactions_domain, "transactions")
        
        # Tutaj można dodać kolejne domeny:
        # trading_domain = TradingDomain()
        # self._register_single_domain(trading_domain, "trading")
        
        # admin_domain = AdminDomain(admin_users=self.admin_users)
        # self._register_single_domain(admin_domain, "admin")
        
        self.stats["domains_loaded"] = len(self.domains)
        logger.info(f"📊 Zarejestrowano {self.stats['domains_loaded']} domen")
    
    def _register_single_domain(self, domain_instance: BaseTelegramControllerDomain, domain_name: str) -> bool:
        """
        Rejestruje pojedynczą domenę z proper error handling i database setup.
        
        Args:
            domain_instance: Instancja domeny do zarejestrowania
            domain_name: Nazwa domeny
            
        Returns:
            bool: True jeśli rejestracja się udała
        """
        try:
            # Inicjalizuj bazę danych dla domeny (jeśli ma taką możliwość)
            if hasattr(domain_instance, 'init_database'):
                try:
                    asyncio.create_task(domain_instance.init_database())
                    logger.info(f"🗃️ Baza danych dla domeny '{domain_name}' zostanie zainicjalizowana")
                except Exception as e:
                    logger.warning(f"⚠️ Nie można zainicjalizować bazy danych dla domeny '{domain_name}': {e}")
            
            # Zarejestruj w routerze
            self.router.mount(domain_instance)
            self.domains[domain_name] = domain_instance
            
            logger.info(f"✅ Domena '{domain_name}' zarejestrowana ({type(domain_instance).__name__})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Błąd rejestracji domeny '{domain_name}': {e}")
            return False
    
    def _attach_router(self) -> None:
        """Załącza router do klienta Telethon."""
        logger.info("🔗 Załączanie routera do klienta...")
        
        self.router.attach(self.client)
        self.stats["routes_registered"] = len(self.router.routes)
        
        logger.info(f"✅ Router załączony z {self.stats['routes_registered']} routami")
    
    def _log_routes_summary(self) -> None:
        """Wyświetla podsumowanie zarejestrowanych routów."""
        logger.info("📋 PODSUMOWANIE ZAREJESTROWANYCH ROUTÓW:")
        
        routes_summary = self.router.get_routes_summary()
        for domain, routes in routes_summary.items():
            logger.info(f"  📁 {domain.upper()}:")
            for route in routes:
                logger.info(f"    • {route}")
        
        logger.info(f"📊 Łącznie: {sum(len(routes) for routes in routes_summary.values())} routów")
    
    async def _setup_additional_handlers(self) -> None:
        """
        Konfiguruje dodatkowe handlery systemowe (opcjonalne).
        """
        @self.client.on(events.NewMessage(pattern='/system_info'))
        async def system_info_handler(event):
            """Handler informacji systemowych - tylko dla adminów."""
            user = await event.get_sender()
            if user.id not in self.admin_users:
                await event.respond("⛔️ Brak uprawnień")
                return
            
            try:
                # Pobierz comprehensive statistics
                stats = await self.get_user_statistics()
                health = await self.health_check_all_domains()
                
                uptime = datetime.now() - self.stats["start_time"]
                info = f"🖥️ **Informacje Systemowe**\n\n"
                info += f"⏱️ **Uptime:** {str(uptime).split('.')[0]}\n"
                info += f"🧪 **Test Mode:** {'✅ Tak' if self.test_mode else '❌ Nie'}\n"
                info += f"📚 **Domeny:** {stats['total_domains']}\n"
                info += f"🛤️ **Routy:** {stats['router_stats'].get('messages_processed', 0) + stats['router_stats'].get('callbacks_processed', 0)}\n\n"
                
                # Domain health summary
                info += f"🏥 **Health Check:**\n"
                healthy_domains = sum(1 for h in health.values() if h.get('healthy', False))
                info += f"   ✅ Healthy: {healthy_domains}/{len(health)}\n"
                
                for domain_name, health_info in health.items():
                    status_emoji = "✅" if health_info.get('healthy', False) else "❌"
                    info += f"   {status_emoji} {domain_name}: {health_info.get('domain_type', 'Unknown')}\n"
                
                info += f"\n📊 **Router Stats:**\n"
                router_stats = stats['router_stats']
                for key, value in router_stats.items():
                    info += f"   • {key}: {value}\n"
                
                # UI utility info
                info += f"\n🎨 **UI Utils:** ✅ Dostępne ({type(self.ui_utils).__name__})\n"
                
                await event.respond(info)
                
            except Exception as e:
                error_msg = f"❌ **Błąd pobierania informacji systemowych:**\n\n`{str(e)}`"
                await event.respond(error_msg)
                logger.error(f"Error in system_info_handler: {e}", exc_info=True)
        
        logger.info("✅ Dodatkowe handlery systemowe skonfigurowane")
    
    async def start(self) -> None:
        """
        Uruchamia aplikację Telegram Bot.
        
        Główna metoda startowa która:
        1. Inicjalizuje klienta Telethon
        2. Konfiguruje system routingu
        3. Rejestruje domeny handlerów
        4. Załącza router do klienta
        5. Uruchamia bot
        """
        try:
            logger.info("🎯 URUCHAMIANIE TELEGRAM CONTROLLER")
            logger.info("=" * 50)
            
            # 1. Inicjalizacja klienta
            self.client = await self._init_client()
            
            # 2. Inicjalizacja routera
            self.router = self._init_router()
            
            # 3. Rejestracja domen
            self._register_domains()
            
            # 4. Załączenie routera
            self._attach_router()
            
            # 5. Konfiguracja dodatkowych handlerów
            await self._setup_additional_handlers()
            
            # 6. Podsumowanie
            self._log_routes_summary()
            
            logger.info("=" * 50)
            logger.info("🚀 BOT URUCHOMIONY POMYŚLNIE!")
            logger.info("💡 Użyj /start aby przetestować funkcjonalność")
            logger.info("")
            logger.info("🔧 DOSTĘPNE KOMENDY SYSTEMOWE:")
            logger.info("   /status - status systemu i bota")
            logger.info("   /sync_all - pełna synchronizacja")
            logger.info("   /sync_exchanges - synchronizacja giełd")
            logger.info("   /health - health check komponentów")
            logger.info("   /logs [level] - logi systemu (admin)")
            logger.info("   /system_info - szczegółowe info systemowe (admin)")
            logger.info("")
            logger.info("💎 KOMENDY ASSETS:")
            logger.info("   /assets [page] - lista wszystkich assetów")
            logger.info("   /assets_search [nazwa] - wyszukiwanie assetu")
            logger.info("   /asset_info [symbol] - szczegóły assetu")
            logger.info("")
            logger.info("🏦 KOMENDY EXCHANGES:")
            logger.info("   /exchanges [page] - lista wszystkich giełd")
            logger.info("   /exchanges_active - tylko aktywne giełdy")
            logger.info("   /exchange_info [nazwa] - szczegóły giełdy")
            logger.info("")
            logger.info("💰 KOMENDY WALLETS:")
            logger.info("   /wallets [page] - lista wszystkich portfeli")
            logger.info("   /wallets_active - tylko aktywne portfele")
            logger.info("   /wallet_balance [giełda] - salda na konkretnej giełdzie")
            logger.info("")
            logger.info("📊 KOMENDY STRATEGIES:")
            logger.info("   /investment_strategies [page] - lista strategii inwestycyjnych")
            logger.info("   /buy_strategies [page] - lista strategii kupna")
            logger.info("   /sell_strategies [page] - lista strategii sprzedaży")
            logger.info("   /investment_strategy_search [nazwa] - wyszukiwanie strategii")
            logger.info("   /strategy_create - kreator nowej strategii (interactive)")
            logger.info("")
            logger.info("💸 KOMENDY TRANSACTIONS:")
            logger.info("   /transactions [limit] - lista ostatnich transakcji")
            logger.info("   /transactions_pending - transakcje bez interpretacji")
            logger.info("   /transaction_create - kreator nowej transakcji (interactive)")
            logger.info("   /transaction_info [id] - szczegóły transakcji")
            logger.info("")
            logger.info("🆕 NOWE FUNKCJE PRODUKCYJNE:")
            logger.info("   ✅ Domain Management - zarządzanie domenami")
            logger.info("   ✅ User Permissions - system uprawnień użytkowników") 
            logger.info("   ✅ Statistics & Health - monitorowanie i statystyki")
            logger.info("   ✅ UI Utils Integration - zaawansowane formatowanie")
            logger.info("")
            logger.info("📱 Bot nasłuchuje wiadomości...")
            logger.info("🛑 Naciśnij Ctrl+C aby zatrzymać")
            logger.info("=" * 50)
            
            # 7. Uruchomienie nasłuchiwania
            await self.client.run_until_disconnected()
            
        except KeyboardInterrupt:
            logger.info("🛑 Otrzymano sygnał przerwania (Ctrl+C)")
            
        except Exception as e:
            logger.error(f"❌ Krytyczny błąd aplikacji: {e}")
            logger.error(traceback.format_exc())
            raise
            
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """
        Zatrzymuje aplikację i czyści zasoby.
        """
        try:
            logger.info("🛑 ZATRZYMYWANIE TELEGRAM CONTROLLER")
            
            if self.client and self.client.is_connected():
                logger.info("🔌 Zamykanie połączenia klienta...")
                await self.client.disconnect()
                logger.info("✅ Klient rozłączony")
            
            # Uptime stats
            uptime = datetime.now() - self.stats["start_time"]
            logger.info(f"📊 Czas działania: {uptime}")
            logger.info(f"📚 Obsłużonych domen: {self.stats['domains_loaded']}")
            
            if self.router:
                router_stats = self.router.get_stats()
                logger.info(f"📈 Statystyki routera: {router_stats}")
            
            logger.info("✅ Telegram Controller zatrzymany pomyślnie")
            
        except Exception as e:
            logger.error(f"⚠️ Błąd podczas zatrzymywania: {e}")
    
    # ===================
    # DOMAIN MANAGEMENT
    # ===================
    
    async def setup_user_permissions(self, telegram_id: int, 
                                   permission_level: str = UserPermissionLevel.USER) -> bool:
        """
        Konfiguruje uprawnienia użytkownika.
        
        Args:
            telegram_id: ID Telegram użytkownika
            permission_level: Poziom uprawnień
            
        Returns:
            bool: True jeśli konfiguracja się udała
        """
        try:
            # Pobierz system domain dla operacji na bazie danych
            system_domain = self.domains.get('system')
            if not system_domain or not hasattr(system_domain, 'db') or not system_domain.db:
                logger.error("System domain lub baza danych niedostępna")
                return False
            
            # Inicjalizuj bazę danych jeśli trzeba
            await system_domain.init_database()
            
            # Utwórz/zaktualizuj użytkownika
            users_table = system_domain.db.get_factory().get_users_table()
            user_id = await users_table.create_telegram_user(
                telegram_id=telegram_id,
                permission_level=permission_level
            )
            
            if user_id:
                logger.info(f"✅ Skonfigurowano uprawnienia dla użytkownika {telegram_id}: {permission_level}")
                return True
            else:
                logger.error(f"❌ Błąd konfiguracji uprawnień dla użytkownika {telegram_id}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Błąd konfiguracji uprawnień: {e}")
            return False
    
    async def get_user_statistics(self) -> Dict[str, Any]:
        """
        Pobiera statystyki użytkowników ze wszystkich domen.
        
        Returns:
            Dict[str, Any]: Zagregowane statystyki
        """
        stats = {
            'total_domains': len(self.domains),
            'domain_stats': {},
            'controller_stats': self.stats.copy(),
            'router_stats': self.router.get_stats() if self.router else {}
        }
        
        for domain_name, domain in self.domains.items():
            try:
                if hasattr(domain, 'get_domain_specific_stats'):
                    domain_stats = await domain.get_domain_specific_stats()
                    stats['domain_stats'][domain_name] = domain_stats
                else:
                    # Podstawowe statystyki jeśli domena nie ma specyficznych
                    stats['domain_stats'][domain_name] = {
                        'domain_type': type(domain).__name__,
                        'has_database': hasattr(domain, 'db') and domain.db is not None,
                        'test_mode': getattr(domain, 'test_mode', None)
                    }
            except Exception as e:
                logger.error(f"Błąd pobierania statystyk domeny {domain_name}: {e}")
                stats['domain_stats'][domain_name] = {'error': str(e)}
        
        return stats
    
    async def health_check_all_domains(self) -> Dict[str, Dict[str, Any]]:
        """
        Przeprowadza health check wszystkich domen.
        
        Returns:
            Dict[str, Dict[str, Any]]: Wyniki health checku
        """
        results = {}
        
        for domain_name, domain in self.domains.items():
            try:
                # Sprawdź podstawowe funkcje domeny
                health_info = {
                    'healthy': True,
                    'domain_type': type(domain).__name__,
                    'checks': {}
                }
                
                # Database check
                if hasattr(domain, 'db') and domain.db:
                    try:
                        db_status = await domain.init_database()
                        health_info['checks']['database'] = 'OK' if db_status else 'ERROR'
                    except Exception as db_e:
                        health_info['checks']['database'] = f'ERROR: {str(db_e)}'
                        health_info['healthy'] = False
                else:
                    health_info['checks']['database'] = 'N/A'
                
                # Domain-specific health check
                if hasattr(domain, '_perform_health_check'):
                    try:
                        domain_health = await domain._perform_health_check()
                        health_info['checks']['domain_specific'] = domain_health
                    except Exception as health_e:
                        health_info['checks']['domain_specific'] = f'ERROR: {str(health_e)}'
                        health_info['healthy'] = False
                
                # Stats check
                if hasattr(domain, 'stats'):
                    health_info['stats'] = domain.stats
                
                results[domain_name] = health_info
                
            except Exception as e:
                results[domain_name] = {
                    'healthy': False,
                    'error': str(e),
                    'domain_type': type(domain).__name__ if domain else 'Unknown'
                }
        
        return results
    
    def get_domain(self, domain_name: str) -> Optional[BaseTelegramControllerDomain]:
        """
        Pobiera domenę po nazwie.
        
        Args:
            domain_name: Nazwa domeny
            
        Returns:
            Optional[BaseTelegramControllerDomain]: Instancja domeny lub None
        """
        return self.domains.get(domain_name)
    
    def list_domains(self) -> Dict[str, str]:
        """
        Zwraca listę wszystkich domen z ich typami.
        
        Returns:
            Dict[str, str]: Mapa nazwa_domeny -> typ_klasy
        """
        return {name: type(domain).__name__ for name, domain in self.domains.items()}


async def main():
    """
    Główna funkcja aplikacji.
    """
    try:
        # Sprawdzenie argumentów trybu testowego
        test_mode = "--test" in sys.argv or os.getenv("TEST_MODE", "").lower() == "true"
        
        if test_mode:
            logger.info("🧪 URUCHAMIANIE W TRYBIE TESTOWYM")
        
        # Utworzenie i uruchomienie kontrolera
        controller = TelegramController(test_mode=test_mode)
        await controller.start()
        
    except KeyboardInterrupt:
        logger.info("🛑 Aplikacja przerwana przez użytkownika")
        
    except Exception as e:
        logger.error(f"❌ Krytyczny błąd aplikacji: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
        
    finally:
        logger.info("👋 Aplikacja zakończona")


if __name__ == "__main__":
    """
    Punkt startowy aplikacji Telegram Bot.
    
    Zmienne środowiskowe wymagane (zarządzane przez src.config.Config):
    - TELETHON_API_ID: ID aplikacji z my.telegram.org
    - TELETHON_API_HASH: Hash aplikacji z my.telegram.org  
    - TELETHON_BOT_TOKEN: Token bota od @BotFather
    
    Zmienne środowiskowe opcjonalne:
    - TELEGRAM_ADMIN_USERS: Lista ID administratorów (przecinek jako separator)
    - TELEGRAM_SESSION_NAME: Nazwa sesji (domyślnie: pump_bot_session)
    - ENABLE_ERROR_RESPONSES: Czy wysyłać błędy użytkownikom (domyślnie: true)
    - ENABLE_HANDLER_LOGGING: Czy logować handlery (domyślnie: true)
    - TEST_MODE: Tryb testowy (domyślnie: false)
    
    Uwaga: Główna konfiguracja jest zarządzana przez klasę Config (src/config.py),
    która ładuje zmienne z pliku .env oraz waliduje wszystkie wymagane ustawienia.
    
    Użycie:
    python main_controller_telegram.py [--test]
    """
    
    # Uruchomienie aplikacji
    try:
        # Sprawdzenie czy asyncio loop już istnieje
        try:
            async_loop = asyncio.get_running_loop()
        except RuntimeError:
            async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(async_loop)
        
        # Uruchomienie głównej funkcji
        async_loop.run_until_complete(main())
        
    except asyncio.CancelledError:
        logger.warning("⚠️ Zadania asyncio zostały anulowane")
        
    except Exception as error:
        logger.error(f"💥 Nieoczekiwany błąd w pętli asyncio: {error}")
        logger.error(traceback.format_exc())
        
    finally:
        # Czyszczenie zadań asyncio
        try:
            pending_tasks = asyncio.all_tasks(async_loop)
            if pending_tasks:
                logger.info(f"🧹 Czyszczenie {len(pending_tasks)} zadań asyncio...")
                for task in pending_tasks:
                    task.cancel()
                async_loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
        except Exception as cleanup_error:
            logger.error(f"⚠️ Błąd podczas czyszczenia zadań: {cleanup_error}")
        
        # Zamknięcie pętli
        try:
            async_loop.close()
            logger.info("✅ Pętla asyncio zamknięta")
        except Exception as loop_error:
            logger.error(f"⚠️ Błąd podczas zamykania pętli: {loop_error}")
