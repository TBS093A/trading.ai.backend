"""
Przykład integracji wszystkich komponentów Telegram z systemem pump bot.

Ten plik demonstruje:
- Inicjalizację kontrolerów
- Montowanie domen w routerze
- Konfigurację uprawnień
- Przykłady użycia workflow

Autor: AI Assistant
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional

from .controller_router_telegram import ClassRouter
from .controller_base_telegram import BaseTelegramControllerDomain, UserPermissionLevel
from .controller_telegram_system import SystemTelegramControllerDomain
from .telegram_ui_utils import TelegramUIUtils, PaginationHelper, InteractiveWizard, ValidationHelper
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class TelegramIntegrationManager:
    """
    Główna klasa zarządzająca integracją Telegram z systemem pump bot.
    
    Odpowiada za:
    - Inicjalizację wszystkich kontrolerów
    - Konfigurację routingu
    - Zarządzanie uprawnieniami
    - Koordynację między domenami
    """
    
    def __init__(self, test_mode: bool = False, admin_users: List[int] = None):
        """
        Inicjalizacja managera integracji.
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
            admin_users: Lista ID administratorów
        """
        self.test_mode = test_mode
        self.admin_users = admin_users or []
        
        # Router dla wszystkich domen
        self.router = ClassRouter(
            enable_logging=True,
            enable_error_responses=True
        )
        
        # Słownik wszystkich domen
        self.domains: Dict[str, BaseTelegramControllerDomain] = {}
        
        # UI Utils
        self.ui_utils = TelegramUIUtils()
        
        logger.info(f"🚀 Inicjalizacja TelegramIntegrationManager (test_mode={test_mode})")
    
    async def initialize_domains(self) -> None:
        """
        Inicjalizuje wszystkie domeny kontrolerów.
        """
        try:
            logger.info("📋 Inicjalizacja domen kontrolerów...")
            
            # System Domain - zarządzanie synchronizacją
            system_domain = SystemTelegramControllerDomain(
                test_mode=self.test_mode,
                admin_users=self.admin_users
            )
            await system_domain.init_database()
            self.domains['system'] = system_domain
            
            # Montuj domeny w routerze
            self.router.mount(system_domain, 'system')
            
            logger.info(f"✅ Zainicjalizowano {len(self.domains)} domen")
            
        except Exception as e:
            logger.error(f"❌ Błąd inicjalizacji domen: {e}")
            raise
    
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
            if not system_domain or not system_domain.db:
                logger.error("System domain lub baza danych niedostępna")
                return False
            
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
    
    def get_router(self) -> ClassRouter:
        """Zwraca skonfigurowany router."""
        return self.router
    
    async def get_user_statistics(self) -> Dict[str, Any]:
        """
        Pobiera statystyki użytkowników ze wszystkich domen.
        
        Returns:
            Dict[str, Any]: Zagregowane statystyki
        """
        stats = {
            'total_domains': len(self.domains),
            'domain_stats': {}
        }
        
        for domain_name, domain in self.domains.items():
            try:
                domain_stats = await domain.get_domain_specific_stats()
                stats['domain_stats'][domain_name] = domain_stats
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
                db_status = await domain.init_database()
                
                results[domain_name] = {
                    'healthy': db_status,
                    'database': 'OK' if db_status else 'ERROR',
                    'stats': domain.stats
                }
                
            except Exception as e:
                results[domain_name] = {
                    'healthy': False,
                    'error': str(e),
                    'database': 'ERROR'
                }
        
        return results


class ExampleUsageDemo:
    """
    Klasa demonstracyjna pokazująca przykłady użycia systemu.
    """
    
    @staticmethod
    def demonstrate_ui_utils():
        """Demonstruje użycie UI utilities."""
        print("🎨 Demonstracja UI Utils:")
        
        # Formatowanie walut
        price = 43250.67
        formatted_price = TelegramUIUtils.format_currency(price, "USD")
        print(f"Cena: {formatted_price}")
        
        # Formatowanie procentów
        change = 2.34
        formatted_change = TelegramUIUtils.format_percentage(change)
        print(f"Zmiana: {formatted_change}")
        
        # Progress bar
        progress = TelegramUIUtils.create_progress_bar(7, 10)
        print(f"Postęp: {progress}")
        
        # Status messages
        success_msg = TelegramUIUtils.create_status_message(
            'success', 'Operacja zakończona', 'Wszystko poszło zgodnie z planem'
        )
        print(f"Sukces: {success_msg}")
    
    @staticmethod
    def demonstrate_pagination():
        """Demonstruje system paginacji."""
        print("\n📄 Demonstracja Paginacji:")
        
        # Przykładowe dane
        sample_data = [{'id': i, 'name': f'Item {i}'} for i in range(1, 26)]
        
        # Paginacja
        page_data, pagination_info = PaginationHelper.get_page_data(sample_data, 2, 10)
        
        print(f"Strona {pagination_info['current_page']} z {pagination_info['total_pages']}")
        print(f"Elementy na stronie: {pagination_info['items_on_page']}")
        print(f"Dane strony: {[item['name'] for item in page_data]}")
        
        # Przyciski paginacji
        buttons = PaginationHelper.create_pagination_buttons(pagination_info, "demo")
        print(f"Przyciski: {len(buttons)} wierszy")
    
    @staticmethod
    def demonstrate_table_formatting():
        """Demonstruje formatowanie tabel."""
        print("\n📊 Demonstracja Formatowania Tabel:")
        
        # Przykładowe dane
        assets_data = [
            {'asset': 'BTC', 'quote': 'USDT', 'price': 43250.67, 'change': 2.34},
            {'asset': 'ETH', 'quote': 'USDT', 'price': 2678.91, 'change': -1.23},
            {'asset': 'ADA', 'quote': 'USDT', 'price': 0.4567, 'change': 5.67}
        ]
        
        # Definicje kolumn
        columns = [
            {'key': 'asset', 'title': 'Asset', 'width': 8},
            {'key': 'quote', 'title': 'Quote', 'width': 8},
            {'key': 'price', 'title': 'Price', 'width': 12, 'type': 'currency'},
            {'key': 'change', 'title': 'Change', 'width': 10, 'type': 'percentage'}
        ]
        
        table = TelegramUIUtils.create_data_table(
            assets_data, columns, "Crypto Assets", max_rows=5
        )
        
        print(table)
    
    @staticmethod
    def demonstrate_validation():
        """Demonstruje walidację danych."""
        print("\n✅ Demonstracja Walidacji:")
        
        # Walidacja email
        email_valid = ValidationHelper.validate_email("test@example.com")
        print(f"Email test@example.com: {'✅ Valid' if email_valid else '❌ Invalid'}")
        
        # Walidacja liczby
        num_valid, num_value = ValidationHelper.validate_number("123.45", min_val=0, max_val=1000)
        print(f"Liczba 123.45: {'✅ Valid' if num_valid else '❌ Invalid'} (wartość: {num_value})")
        
        # Walidacja symbolu assetu
        symbol_valid = ValidationHelper.validate_asset_symbol("BTCUSDT")
        print(f"Symbol BTCUSDT: {'✅ Valid' if symbol_valid else '❌ Invalid'}")
        
        # Sanityzacja inputu
        dirty_input = "<script>alert('xss')</script>Hello World!"
        clean_input = ValidationHelper.sanitize_input(dirty_input)
        print(f"Wyczyszczony input: '{clean_input}'")


async def integration_example():
    """Główny przykład integracji."""
    print("🚀 Przykład integracji Telegram z Pump Bot System")
    
    # Konfiguracja administratorów
    admin_users = [12345678, 87654321]  # Przykładowe ID administratorów
    
    # Inicjalizacja managera
    manager = TelegramIntegrationManager(
        test_mode=True,  # Tryb testowy
        admin_users=admin_users
    )
    
    try:
        # Inicjalizacja domen
        await manager.initialize_domains()
        
        # Konfiguracja uprawnień przykładowych użytkowników
        await manager.setup_user_permissions(12345678, UserPermissionLevel.ADMIN)
        await manager.setup_user_permissions(11111111, UserPermissionLevel.USER)
        await manager.setup_user_permissions(22222222, UserPermissionLevel.TRADER)
        
        # Pobierz router dla integracji z aplikacją Telegram
        router = manager.get_router()
        print(f"✅ Router skonfigurowany z {len(router.routes)} routami")
        
        # Statystyki
        stats = await manager.get_user_statistics()
        print(f"📊 Statystyki: {stats}")
        
        # Health check
        health = await manager.health_check_all_domains()
        print(f"🏥 Health check: {health}")
        
        # Demonstracje UI
        ExampleUsageDemo.demonstrate_ui_utils()
        ExampleUsageDemo.demonstrate_pagination()
        ExampleUsageDemo.demonstrate_table_formatting()
        ExampleUsageDemo.demonstrate_validation()
        
        print("\n✅ Integracja zakończona pomyślnie!")
        
    except Exception as e:
        print(f"❌ Błąd integracji: {e}")
        logger.error(f"Integration error: {e}", exc_info=True)


if __name__ == "__main__":
    """Uruchom przykład integracji."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(integration_example())
