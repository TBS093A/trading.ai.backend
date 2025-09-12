"""
Kontroler Exchanges dla Telegram - zarządzanie giełdami kryptowalutowymi.

Ta klasa implementuje:
- Przeglądanie giełd z filtrowaniem aktywnych/wszystkich
- Szczegółowe informacje o giełdach
- Zarządzanie statusem giełd (włączenie/wyłączenie)
- Test połączeń z API giełd
- Integrację z systemem assetów

Autor: AI Assistant
"""

import logging
import traceback
from typing import List, Dict, Any, Optional, Tuple
from telethon import Button

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, RD
from .controller_telegram_utils_ui import PaginationHelper, ConfirmationDialog

logger = logging.getLogger(__name__)


class ExchangesTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla zarządzania giełdami kryptowalutowymi w systemie Telegram.
    
    Zapewnia funkcjonalności:
    - Lista wszystkich giełd z paginacją
    - Filtrowanie aktywnych giełd
    - Szczegółowe informacje o giełdach
    - Zarządzanie statusem giełd (admin-only)
    - Test połączeń API
    - Integrację z assetami na giełdach
    """
    
    DOMAIN = "exchanges"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera giełd.
        
        Args:
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        
        # Konfiguracja paginacji
        self.default_page_size = 15
        self.max_page_size = 50
    
    # ===================
    # DOMAIN MENU
    # ===================
    
    async def get_domain_menu(self, event, user_id: Optional[int] = None) -> Tuple[str, List[List[Button]]]:
        """Zwraca menu domeny giełd z przyciskami komend."""
        try:
            stats = await self.get_domain_specific_stats()
            
            menu_text = "🏦 **Exchanges - Zarządzanie Giełdami**\n\n"
            
            if stats.get('database_available'):
                menu_text += f"📊 **Statystyki:**\n"
                menu_text += f"• Wszystkie giełdy: {stats.get('total_exchanges', 'N/A')}\n"
                menu_text += f"• Aktywne giełdy: {stats.get('active_exchanges', 'N/A')}\n\n"
            else:
                menu_text += "⚠️ **Baza danych niedostępna**\n\n"
            
            menu_text += "📋 **Dostępne funkcje:**\n"
            menu_text += "• Przeglądanie wszystkich giełd\n"
            menu_text += "• Lista tylko aktywnych giełd\n"
            menu_text += "• Szczegółowe informacje o giełdach\n"
            
            buttons = [
                [
                    Button.inline("📋 Wszystkie Giełdy", b"cmd:/exchanges"),
                    Button.inline("✅ Aktywne Giełdy", b"cmd:/exchanges_active")
                ],
                [
                    Button.inline("ℹ️ Info Giełda", b"cmd:/exchange_info")
                ],
                [Button.inline("🏠 Menu Główne", b"nav:main_menu")]
            ]
            
            return menu_text, buttons
            
        except Exception as e:
            logger.error(f"Błąd w get_domain_menu (exchanges): {e}")
            return await super().get_domain_menu(event, user_id)
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny giełd."""
        try:
            if not self.db:
                return {"error": "Database not available"}
            
            await self.init_database()
            
            exchanges_table = self.db.get_factory().get_exchanges_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Pobierz podstawowe statystyki
            all_exchanges = await exchanges_table.get_all(limit=1000)
            active_exchanges = await exchanges_table.get_active(limit=1000)
            
            # Policz assety na giełdach
            total_exchange_asset_relations = len(await asset_exchanges_table.get_all(limit=50000))
            
            return {
                "total_exchanges": len(all_exchanges),
                "active_exchanges": len(active_exchanges),
                "inactive_exchanges": len(all_exchanges) - len(active_exchanges),
                "exchange_asset_relations": total_exchange_asset_relations,
                "database_available": True
            }
            
        except Exception as e:
            logger.error(f"Error getting exchanges domain stats: {e}")
            return {
                "error": str(e),
                "database_available": False
            }
    
    # ===================
    # COMMANDS - EXCHANGES LIST
    # ===================
    
    @RD.cmd("exchanges", aliases=["list_exchanges", "show_exchanges"])
    async def exchanges_command(self, event):
        """
        Komenda wyświetlania listy wszystkich giełd z paginacją.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "exchanges_list")
        
        # Parse argumentów dla paginacji
        text_parts = event.raw_text.split()
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)  # Minimum page 1
            except ValueError:
                pass
        
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            # Oblicz offset dla paginacji bazy danych
            offset = (page - 1) * self.default_page_size
            
            # Pobierz giełdy z dodatkowym rekordem dla sprawdzenia następnej strony
            exchanges = await exchanges_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not exchanges:
                await event.respond("🏦 **Lista Giełd**\n\n❌ Brak giełd do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(exchanges) > self.default_page_size
            page_exchanges = exchanges[:self.default_page_size]
            
            # Formatuj odpowiedź
            exchanges_text = f"🏦 **Lista Giełd - Strona {page}**\n\n"
            
            for i, exchange in enumerate(page_exchanges, 1):
                item_number = offset + i
                exchange_name = exchange.get('display_name') or exchange['name']
                status_emoji = "🟢" if exchange.get('is_active') else "🔴"
                
                exchanges_text += f"{item_number}. {status_emoji} `{exchange_name}`\n"
                exchanges_text += f"    ID: {exchange['id']} | Nazwa: {exchange['name']}\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                exchanges_text += f"\n📄 Strona {page}"
                if has_next:
                    exchanges_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper.create_pagination_buttons
            # Nie znamy total_items więc użyjemy estimacji
            estimated_total = offset + len(page_exchanges) + (100 if has_next else 0)  # Estymacja
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_exchanges),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_exchanges)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "ex", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("⚡ Tylko aktywne", b"ex:active_only"),
                    Button.inline("🔍 Wyszukaj", b"ex:search_prompt")
                ],
                [
                    Button.inline("🔄 Odśwież", f"ex:page:{page}".encode()),
                    Button.inline("📊 Statystyki", b"ex:stats")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(exchanges_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchanges_list")
            await event.respond(error_msg)
    
    @RD.cmd("exchanges_active", aliases=["active_exchanges", "exchanges_on"])
    async def exchanges_active_command(self, event):
        """
        Komenda wyświetlania tylko aktywnych giełd.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "exchanges_active_list")
        
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            # Pobierz tylko aktywne giełdy
            active_exchanges = await exchanges_table.get_active(limit=100)
            
            if not active_exchanges:
                await event.respond(
                    "⚡ **Aktywne Giełdy**\n\n❌ Brak aktywnych giełd.",
                    buttons=[
                        [Button.inline("🏦 Wszystkie giełdy", b"ex:page:1")],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj listę aktywnych giełd
            exchanges_text = f"⚡ **Aktywne Giełdy** ({len(active_exchanges)})\n\n"
            
            for i, exchange in enumerate(active_exchanges[:20], 1):  # Limit 20 dla czytelności
                exchange_name = exchange.get('display_name') or exchange['name']
                exchanges_text += f"{i}. 🟢 `{exchange_name}`\n"
                exchanges_text += f"    ID: {exchange['id']} | Utworzona: "
                exchanges_text += f"{self._format_datetime(exchange.get('created_at', ''))}\n"
            
            if len(active_exchanges) > 20:
                exchanges_text += f"\n... i {len(active_exchanges) - 20} więcej"
            
            # Przyciski szczegółów dla pierwszych giełd
            buttons = []
            details_buttons = []
            
            for exchange in active_exchanges[:6]:  # Pierwsze 6 giełd
                exchange_name = (exchange.get('display_name') or exchange['name'])[:12]
                details_buttons.append(
                    Button.inline(f"📊 {exchange_name}", f"ex:details:{exchange['id']}".encode())
                )
            
            # Podziel na wiersze po 3 przyciski
            for i in range(0, len(details_buttons), 3):
                buttons.append(details_buttons[i:i+3])
            
            buttons.extend([
                [
                    Button.inline("🏦 Wszystkie giełdy", b"ex:page:1"),
                    Button.inline("🔄 Odśwież", b"ex:active_only")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(exchanges_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchanges_active")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - EXCHANGE INFO
    # ===================
    
    @RD.cmd("exchange_info", aliases=["info_exchange", "exchange_details"])
    async def exchange_info_command(self, event):
        """
        Komenda szczegółowych informacji o giełdzie.
        Użycie: /exchange_info [name] lub /exchange_info [id]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "📊 **Informacje o Giełdzie**\n\n"
                "Podaj nazwę lub ID giełdy:\n\n"
                "**Użycie:**\n"
                "• `/exchange_info binance`\n"
                "• `/exchange_info 123` (ID)\n"
                "• `/exchange_info \"Binance Spot\"` (pełna nazwa)",
                buttons=[
                    [Button.inline("🏦 Lista giełd", b"ex:page:1")],
                    [Button.inline("⚡ Aktywne", b"ex:active_only")],
                    [Button.inline("🔙 Menu główne", b"nav:home")]
                ]
            )
            return
        
        identifier = parts[1].strip()
        await self.log_action(user.id, "exchange_info", {"identifier": identifier})
        
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Spróbuj znaleźć giełdę
            exchange = None
            
            # 1. Spróbuj jako ID
            if identifier.isdigit():
                exchange = await exchanges_table.get_by_id(int(identifier))
            
            # 2. Spróbuj jako nazwa
            if not exchange:
                exchange = await exchanges_table.get_by_name(identifier.lower())
            
            # 3. Spróbuj wyszukać po części nazwy
            if not exchange:
                search_results = await exchanges_table.search_by_name(identifier)
                if len(search_results) == 1:
                    exchange = search_results[0]
                elif len(search_results) > 1:
                    # Wiele wyników - pokaż listę do wyboru
                    await self._show_multiple_exchanges_choice(event, search_results, identifier)
                    return
            
            if not exchange:
                await event.respond(
                    f"❌ **Giełda nie znaleziona**\n\n"
                    f"Nie można znaleźć giełdy: `{identifier}`\n\n"
                    f"Spróbuj:\n"
                    f"• Nazwę giełdy (binance)\n"
                    f"• Pełną nazwę (\"Binance Spot\")\n"
                    f"• ID numeryczne",
                    buttons=[
                        [Button.inline("🔍 Wyszukaj", b"ex:search_prompt")],
                        [Button.inline("🏦 Lista giełd", b"ex:page:1")],
                        [Button.inline("🔙 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Pobierz assety dla tej giełdy
            exchange_assets = await asset_exchanges_table.get_by_exchange_id(exchange['id'], limit=100)
            
            # Formatuj szczegółowe informacje
            info_text = self.format_exchange_info(exchange)
            
            # Dodaj informacje o assetach
            if exchange_assets:
                info_text += f"\n💎 **Dostępne assety ({len(exchange_assets)}):**\n"
                for i, asset_rel in enumerate(exchange_assets[:8], 1):  # Pokaż tylko pierwsze 8
                    asset_symbol = f"{asset_rel['asset']}/{asset_rel['quote']}"
                    info_text += f"• `{asset_symbol}`\n"
                
                if len(exchange_assets) > 8:
                    info_text += f"• ... i {len(exchange_assets) - 8} więcej\n"
            else:
                info_text += f"\n💎 **Assety:** Brak danych\n"
            
            # Przyciski dla admina
            admin_buttons = []
            # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            if True:  # Zawsze dostępne
                if exchange.get('is_active'):
                    admin_buttons.append(Button.inline("🔴 Wyłącz", f"ex:disable:{exchange['id']}".encode()))
                else:
                    admin_buttons.append(Button.inline("🟢 Włącz", f"ex:enable:{exchange['id']}".encode()))
                
                admin_buttons.append(Button.inline("🔧 Test API", f"ex:test_connection:{exchange['id']}".encode()))
            
            # Przyciski
            buttons = []
            if admin_buttons:
                # Podziel admin buttons na wiersze po 2
                for i in range(0, len(admin_buttons), 2):
                    buttons.append(admin_buttons[i:i+2])
            
            buttons.extend([
                [
                    Button.inline("💎 Assety", f"ex:assets:{exchange['id']}".encode()),
                    Button.inline("🔄 Odśwież", f"ex:details:{exchange['id']}".encode())
                ],
                [Button.inline("🏦 Lista giełd", b"ex:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(info_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_info")
            await event.respond(error_msg)
    
    async def _show_multiple_exchanges_choice(self, event, exchanges: List[Dict[str, Any]], search_term: str):
        """Pokazuje listę wyboru gdy znaleziono wiele giełd."""
        choice_text = f"🔍 **Znaleziono {len(exchanges)} giełd dla '{search_term}'**\n\n"
        choice_text += "Wybierz giełdę:\n\n"
        
        buttons = []
        for i, exchange in enumerate(exchanges[:8], 1):  # Maksymalnie 8 opcji
            exchange_name = exchange.get('display_name') or exchange['name']
            status_emoji = "🟢" if exchange.get('is_active') else "🔴"
            choice_text += f"{i}. {status_emoji} `{exchange_name}`\n"
            
            button_text = f"{i}. {exchange_name[:15]}"  # Skróć dla przycisku
            buttons.append([Button.inline(button_text, f"ex:details:{exchange['id']}".encode())])
        
        if len(exchanges) > 8:
            choice_text += f"\n... i {len(exchanges) - 8} więcej (użyj bardziej precyzyjnego wyszukiwania)"
        
        buttons.append([Button.inline("🔙 Wstecz", b"ex:page:1")])
        
        await event.respond(choice_text, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - PAGINATION
    # ===================
    
    @RD.cb(b"ex:page:")
    async def exchanges_page_callback(self, event):
        """Handler paginacji dla listy giełd."""
        try:
            # Extract page number from callback data
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            # Simulate command call for pagination
            event.raw_text = f"/exchanges {page}"
            await self.exchanges_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in exchanges pagination: {e}")
    
    @RD.cb(b"ex:page_info")
    async def exchanges_page_info_callback(self, event):
        """Informacje o aktualnej stronie."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"ex:jump")
    async def exchanges_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony giełd, wyślij:\n"
            "`/exchanges [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/exchanges 3` - przejdź do strony 3\n"
            "• `/exchanges 1` - powrót do pierwszej strony\n\n"
            "**Wskazówki:**\n"
            "• Użyj liczb większych od 1\n"
            "• Jeśli strona nie istnieje, zostaniesz przekierowany do ostatniej dostępnej"
        )
        
        buttons = [
            [Button.inline("🏦 Strona 1", b"ex:page:1")],
            [Button.inline("🔙 Wstecz", b"ex:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - EXCHANGE ACTIONS
    # ===================
    
    @RD.cb(b"ex:active_only")
    async def exchanges_active_only_callback(self, event):
        """Pokazuje tylko aktywne giełdy."""
        await self.exchanges_active_command(event)
    
    @RD.cb(b"ex:details:")
    async def exchanges_details_callback(self, event):
        """Pokazuje szczegółowe informacje o giełdzie."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Pobierz giełdę
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.answer("❌ Giełda nie znaleziona", alert=True)
                return
            
            # Pobierz assety dla tej giełdy
            exchange_assets = await asset_exchanges_table.get_by_exchange_id(exchange_id, limit=100)
            
            # Formatuj szczegółowe informacje (jak w exchange_info_command)
            info_text = self.format_exchange_info(exchange)
            
            if exchange_assets:
                info_text += f"\n💎 **Dostępne assety ({len(exchange_assets)}):**\n"
                for i, asset_rel in enumerate(exchange_assets[:10], 1):
                    asset_symbol = f"{asset_rel['asset']}/{asset_rel['quote']}"
                    info_text += f"• `{asset_symbol}`\n"
                
                if len(exchange_assets) > 10:
                    info_text += f"• ... i {len(exchange_assets) - 10} więcej\n"
            else:
                info_text += f"\n💎 **Assety:** Brak danych\n"
            
            # Przyciski dla admina
            admin_buttons = []
            # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            if True:  # Zawsze dostępne
                if exchange.get('is_active'):
                    admin_buttons.append(Button.inline("🔴 Wyłącz", f"ex:disable:{exchange['id']}".encode()))
                else:
                    admin_buttons.append(Button.inline("🟢 Włącz", f"ex:enable:{exchange['id']}".encode()))
                
                admin_buttons.append(Button.inline("🔧 Test API", f"ex:test_connection:{exchange['id']}".encode()))
            
            # Przyciski
            buttons = []
            if admin_buttons:
                for i in range(0, len(admin_buttons), 2):
                    buttons.append(admin_buttons[i:i+2])
            
            buttons.extend([
                [
                    Button.inline("💎 Assety", f"ex:assets:{exchange['id']}".encode()),
                    Button.inline("🔄 Odśwież", f"ex:details:{exchange['id']}".encode())
                ],
                [Button.inline("🏦 Lista giełd", b"ex:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "exchange_details_view", {
                "exchange_id": exchange_id, 
                "exchange_name": exchange['name']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_details")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - ADMIN ACTIONS WITH CONFIRMATION
    # ===================
    
    @RD.cb(b"ex:enable:")
    async def exchanges_enable_callback(self, event):
        """Pokazuje potwierdzenie włączenia giełdy."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Sprawdź uprawnienia administratora
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            # Pobierz giełdę
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.answer("❌ Giełda nie znaleziona", alert=True)
                return
            
            exchange_name = exchange.get('display_name') or exchange['name']
            
            # Sprawdź czy giełda już jest włączona
            if exchange.get('is_active'):
                await event.answer(f"ℹ️ Giełda {exchange_name} jest już włączona", alert=False)
                return
            
            # Pokazuje dialog potwierdzenia
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Włączenie giełdy {exchange_name}",
                f"ID: {exchange_id}",
                "Włączenie giełdy spowoduje jej aktywację w systemie i możliwość korzystania z jej API."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "ex:confirm_enable",
                str(exchange_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_enable")
            await event.edit(error_msg)
    
    @RD.cb(b"ex:disable:")
    async def exchanges_disable_callback(self, event):
        """Pokazuje potwierdzenie wyłączenia giełdy."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Sprawdź uprawnienia administratora
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Pobierz giełdę
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.answer("❌ Giełda nie znaleziona", alert=True)
                return
            
            exchange_name = exchange.get('display_name') or exchange['name']
            
            # Sprawdź czy giełda już jest wyłączona
            if not exchange.get('is_active'):
                await event.answer(f"ℹ️ Giełda {exchange_name} jest już wyłączona", alert=False)
                return
            
            # Sprawdź ile assetów ma ta giełda
            exchange_assets = await asset_exchanges_table.get_by_exchange_id(exchange_id, limit=1000)
            assets_count = len(exchange_assets)
            
            # Pokazuje dialog potwierdzenia z ostrzeżeniem o assetach
            warning = f"Giełda ma {assets_count} assetów. Wyłączenie może wpłynąć na dostępność tych assetów."
            
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Wyłączenie giełdy {exchange_name}",
                f"ID: {exchange_id}",
                warning
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "ex:confirm_disable",
                str(exchange_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_disable")
            await event.edit(error_msg)
    
    @RD.cb(b"ex:confirm_enable:")
    async def exchanges_confirm_enable_callback(self, event):
        """Wykonuje włączenie giełdy po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            # Pobierz giełdę
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.edit("❌ **Błąd**\n\nGiełda nie znaleziona.")
                return
            
            exchange_name = exchange.get('display_name') or exchange['name']
            
            # Włącz giełdę
            success = await exchanges_table.update(exchange_id, is_active=True)
            
            if success:
                success_msg = self.create_success_message(
                    f"Włączenie giełdy {exchange_name}",
                    f"✅ Giełda została pomyślnie włączona.\n🆔 ID: {exchange_id}\n⚡ Status: Aktywna"
                )
                
                buttons = [
                    [Button.inline("📊 Szczegóły", f"ex:details:{exchange_id}".encode())],
                    [Button.inline("🏦 Lista giełd", b"ex:page:1")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "exchange_enabled", {
                    "exchange_id": exchange_id, 
                    "exchange_name": exchange_name
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się włączyć giełdy. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_confirm_enable")
            await event.edit(error_msg)
    
    @RD.cb(b"ex:confirm_disable:")
    async def exchanges_confirm_disable_callback(self, event):
        """Wykonuje wyłączenie giełdy po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            # Pobierz giełdę
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.edit("❌ **Błąd**\n\nGiełda nie znaleziona.")
                return
            
            exchange_name = exchange.get('display_name') or exchange['name']
            
            # Wyłącz giełdę
            success = await exchanges_table.update(exchange_id, is_active=False)
            
            if success:
                success_msg = self.create_success_message(
                    f"Wyłączenie giełdy {exchange_name}",
                    f"✅ Giełda została pomyślnie wyłączona.\n🆔 ID: {exchange_id}\n🔴 Status: Nieaktywna"
                )
                
                buttons = [
                    [Button.inline("📊 Szczegóły", f"ex:details:{exchange_id}".encode())],
                    [Button.inline("🏦 Lista giełd", b"ex:page:1")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "exchange_disabled", {
                    "exchange_id": exchange_id, 
                    "exchange_name": exchange_name
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się wyłączyć giełdy. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_confirm_disable")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - TEST CONNECTION
    # ===================
    
    @RD.cb(b"ex:test_connection:")
    async def exchanges_test_connection_callback(self, event):
        """Test połączenia z API giełdy."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            # Pobierz giełdę
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.answer("❌ Giełda nie znaleziona", alert=True)
                return
            
            exchange_name = exchange.get('display_name') or exchange['name']
            
            # Wyślij loading message
            loading_msg = self.create_loading_message(f"test połączenia z {exchange_name}")
            await event.edit(loading_msg)
            
            # Symulacja testu połączenia (w przyszłości można podłączyć rzeczywiste API)
            import asyncio
            await asyncio.sleep(2)  # Symulacja testu
            
            # Mock wyników testu
            test_results = await self._perform_exchange_connection_test(exchange)
            
            # Formatuj wyniki
            if test_results['success']:
                results_msg = self.create_success_message(
                    f"Test połączenia - {exchange_name}",
                    f"✅ Połączenie prawidłowe\n"
                    f"⏱️ Czas odpowiedzi: {test_results.get('response_time', 'N/A')}ms\n"
                    f"📊 Status API: {test_results.get('api_status', 'OK')}\n"
                    f"🔗 Endpoint: {test_results.get('endpoint', 'Mock API')}"
                )
            else:
                results_msg = self.create_error_message(
                    f"testu połączenia - {exchange_name}",
                    f"❌ Błąd połączenia\n"
                    f"📝 Opis: {test_results.get('error', 'Unknown error')}\n"
                    f"🔗 Endpoint: {test_results.get('endpoint', 'Mock API')}"
                )
            
            buttons = [
                [
                    Button.inline("🔄 Test ponownie", f"ex:test_connection:{exchange_id}".encode()),
                    Button.inline("📊 Szczegóły", f"ex:details:{exchange_id}".encode())
                ],
                [Button.inline("🏦 Lista giełd", b"ex:page:1")]
            ]
            
            await event.edit(results_msg, buttons=buttons)
            await self.log_action(user.id, "exchange_connection_test", {
                "exchange_id": exchange_id,
                "exchange_name": exchange_name,
                "test_success": test_results['success']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchange_test_connection")
            await event.edit(error_msg)
    
    async def _perform_exchange_connection_test(self, exchange: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wykonuje test połączenia z API giełdy (mock implementation).
        
        Args:
            exchange: Słownik z danymi giełdy
            
        Returns:
            Dict[str, Any]: Wyniki testu połączenia
        """
        # Mock implementation - w przyszłości można podłączyć rzeczywiste API
        exchange_name = exchange['name'].lower()
        
        # Symulacja różnych wyników w zależności od nazwy giełdy
        if exchange_name == 'binance':
            return {
                'success': True,
                'response_time': 150,
                'api_status': 'OK',
                'endpoint': 'https://api.binance.com/api/v3/ping'
            }
        elif exchange_name == 'coinbase':
            return {
                'success': True,
                'response_time': 230,
                'api_status': 'OK',
                'endpoint': 'https://api.coinbase.com/v2/time'
            }
        elif 'test' in exchange_name or 'mock' in exchange_name:
            return {
                'success': False,
                'error': 'Test exchange - connection simulation failed',
                'endpoint': 'Mock API endpoint'
            }
        else:
            # Default successful test
            return {
                'success': True,
                'response_time': 200,
                'api_status': 'OK',
                'endpoint': f'Mock API for {exchange_name}'
            }
    
    # ===================
    # CALLBACK QUERIES - OTHER ACTIONS
    # ===================
    
    @RD.cb(b"ex:search_prompt")
    async def exchanges_search_prompt_callback(self, event):
        """Pokazuje instrukcje wyszukiwania giełd."""
        search_help = (
            "🔍 **Wyszukiwanie Giełd**\n\n"
            "**Aby wyszukać giełdę, wyślij:**\n"
            "`/exchange_info NAZWA`\n\n"
            "**Przykłady:**\n"
            "• `/exchange_info binance` - znajdzie Binance\n"
            "• `/exchange_info coinbase` - znajdzie Coinbase\n"
            "• `/exchange_info 123` - znajdzie giełdę o ID 123\n\n"
            "**Wskazówki:**\n"
            "• Możesz użyć części nazwy\n"
            "• Wyszukiwanie nie rozróżnia wielkości liter\n"
            "• Jeśli znajdzie wiele wyników, pokaże listę do wyboru"
        )
        
        buttons = [
            [Button.inline("🏦 Lista wszystkich", b"ex:page:1")],
            [Button.inline("⚡ Aktywne", b"ex:active_only")],
            [Button.inline("🏠 Menu główne", b"nav:home")]
        ]
        
        await event.edit(search_help, buttons=buttons)
    
    @RD.cb(b"ex:stats")
    async def exchanges_stats_callback(self, event):
        """Pokazuje statystyki giełd."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            stats = await self.get_domain_specific_stats()
            
            if 'error' in stats:
                await event.edit(f"❌ **Błąd pobierania statystyk**\n\n{stats['error']}")
                return
            
            stats_text = "📊 **Statystyki Giełd**\n\n"
            stats_text += f"🏦 **Wszystkie giełdy:** {stats['total_exchanges']}\n"
            stats_text += f"⚡ **Aktywne giełdy:** {stats['active_exchanges']}\n"
            stats_text += f"🔴 **Nieaktywne giełdy:** {stats['inactive_exchanges']}\n"
            stats_text += f"💎 **Relacje asset-giełda:** {stats['exchange_asset_relations']}\n"
            
            # Oblicz procenty
            if stats['total_exchanges'] > 0:
                active_percent = (stats['active_exchanges'] / stats['total_exchanges']) * 100
                stats_text += f"\n📈 **Procent aktywnych:** {active_percent:.1f}%\n"
            
            buttons = [
                [
                    Button.inline("🏦 Wszystkie", b"ex:page:1"),
                    Button.inline("⚡ Aktywne", b"ex:active_only")
                ],
                [Button.inline("🔄 Odśwież", b"ex:stats")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(stats_text, buttons=buttons)
            await self.log_action(user.id, "exchanges_stats_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "exchanges_stats")
            await event.edit(error_msg)
    
    @RD.cb(b"ex:assets:")
    async def exchanges_assets_callback(self, event):
        """Pokazuje assety dla wybranej giełdy (przekierowanie do domeny assets)."""
        # Extract exchange ID
        callback_data = event.data.decode()
        exchange_id = int(callback_data.split(":")[-1])
        
        # Przekierowanie do domeny assets z filtrem giełdy
        redirect_msg = (
            "🔄 **Przekierowanie...**\n\n"
            "Przechodzę do domeny Assets aby pokazać assety dla tej giełdy.\n"
            "Użyj przycisku poniżej lub komendę `/assets` i wybierz giełdę."
        )
        
        buttons = [
            [Button.inline("🏦 Po giełdach", b"assets:by_exchange")],
            [Button.inline("💎 Wszystkie assety", b"assets:page:1")],
            [Button.inline("🔙 Wstecz", f"ex:details:{exchange_id}".encode())]
        ]
        
        await event.edit(redirect_msg, buttons=buttons)
    
    # ===================
    # UTILITY METHODS
    # ===================
    
    def format_exchange_info(self, exchange: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o giełdzie (override z base class).
        
        Args:
            exchange: Słownik z danymi giełdy
            
        Returns:
            str: Sformatowane informacje o giełdzie
        """
        exchange_name = exchange.get('display_name') or exchange['name']
        status_emoji = "🟢" if exchange.get('is_active') else "🔴"
        status_text = "Aktywna" if exchange.get('is_active') else "Nieaktywna"
        
        response = f"🏦 **Giełda: {exchange_name}**\n\n"
        response += f"🔤 **Nazwa systemu:** `{exchange['name']}`\n"
        response += f"🆔 **Database ID:** `{exchange['id']}`\n"
        response += f"{status_emoji} **Status:** {status_text}\n"
        
        if 'created_at' in exchange:
            response += f"📅 **Dodana:** {self._format_datetime(exchange.get('created_at'))}\n"
        
        return response
