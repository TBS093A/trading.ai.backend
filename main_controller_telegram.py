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
from typing import Dict, List, Optional, Any
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
from src.controller_router_telegram import ClassRouter, DomainBase

# Import przykładowej domeny
from src.controller_telegram_example import PumpBotExampleDomain

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
        self.domains: Dict[str, DomainBase] = {}
        
        # Statistyki aplikacji
        self.stats = {
            "start_time": datetime.now(),
            "domains_loaded": 0,
            "routes_registered": 0,
            "uptime_seconds": 0
        }
        
        # Używamy istniejącej konfiguracji
        self.config = config
        
        # Dodatkowe zmienne konfiguracyjne specyficzne dla TelegramController
        self.session_name = os.getenv("TELEGRAM_SESSION_NAME", "pump_bot_session")
        self.admin_users = self._parse_admin_users()
        self.enable_error_responses = os.getenv("ENABLE_ERROR_RESPONSES", "true").lower() == "true"
        self.enable_logging = os.getenv("ENABLE_HANDLER_LOGGING", "true").lower() == "true"
        
        logger.info(f"🚀 Inicjalizacja TelegramController (test_mode={test_mode})")
        logger.info(f"📋 Konfiguracja załadowana z klasy Config")
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
    
    def _parse_admin_users(self) -> List[int]:
        """
        Parsuje listę administratorów z zmiennej środowiskowej.
        
        Returns:
            Lista ID użytkowników-administratorów
        """
        admin_users_str = os.getenv("TELEGRAM_ADMIN_USERS", "")
        if not admin_users_str:
            return []
        
        try:
            return [int(user_id.strip()) for user_id in admin_users_str.split(",") if user_id.strip()]
        except ValueError as e:
            logger.warning(f"⚠️ Błąd parsowania administratorów: {e}")
            return []
    
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
        
        # Przykładowa domena - PumpBotExampleDomain
        example_domain = PumpBotExampleDomain(
            admin_users=self.admin_users,
            test_mode=self.test_mode
        )
        self.router.mount(example_domain)
        self.domains["pump_example"] = example_domain
        logger.info("✅ Domena 'pump_example' zarejestrowana")
        
        # Tutaj można dodać kolejne domeny:
        # trading_domain = TradingDomain()
        # self.router.mount(trading_domain)
        # self.domains["trading"] = trading_domain
        
        # admin_domain = AdminDomain(admin_users=self.admin_users)
        # self.router.mount(admin_domain)
        # self.domains["admin"] = admin_domain
        
        self.stats["domains_loaded"] = len(self.domains)
        logger.info(f"📊 Zarejestrowano {self.stats['domains_loaded']} domen")
    
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
            
            uptime = datetime.now() - self.stats["start_time"]
            info = f"🖥️ **Informacje Systemowe**\n\n"
            info += f"⏱️ **Uptime:** {uptime}\n"
            info += f"📚 **Domeny:** {self.stats['domains_loaded']}\n"
            info += f"🛤️ **Routy:** {self.stats['routes_registered']}\n"
            info += f"📊 **Statystyki Routera:**\n"
            
            router_stats = self.router.get_stats()
            for key, value in router_stats.items():
                info += f"   • {key}: {value}\n"
            
            await event.respond(info)
        
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
