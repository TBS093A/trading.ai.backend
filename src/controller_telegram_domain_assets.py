"""
Kontroler Assets dla Telegram - zarządzanie assetami i giełdami.

Ta klasa implementuje:
- Przeglądanie assetów z paginacją
- Wyszukiwanie assetów po nazwie
- Szczegółowe informacje o assetach
- Filtrowanie po giełdach
- Dwustopniowy wybór giełdy

Autor: AI Assistant
"""

import logging
import traceback
from typing import List, Dict, Any, Optional
from telethon import Button

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, RD
from .controller_telegram_utils_ui import PaginationHelper

logger = logging.getLogger(__name__)


class AssetsTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla zarządzania assetami w systemie Telegram.
    
    Zapewnia funkcjonalności:
    - Lista wszystkich assetów z paginacją
    - Wyszukiwanie assetów po nazwie
    - Szczegółowe informacje o assetach
    - Filtrowanie po giełdach (aktywnych i wszystkich)
    - Integrację z systemem exchange-asset relationships
    """
    
    DOMAIN = "assets"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera assetów.
        
        Args:
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        
        # Konfiguracja paginacji
        self.default_page_size = 10
        self.max_page_size = 50
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny assetów."""
        try:
            if not self.db:
                return {"error": "Database not available"}
            
            await self.init_database()
            
            assets_table = self.db.get_factory().get_assets_table()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Pobierz podstawowe statystyki
            assets_count = len(await assets_table.get_all(limit=10000))  # Quick count approximation
            exchanges_count = len(await exchanges_table.get_all(limit=1000))
            active_exchanges_count = len(await exchanges_table.get_active(limit=1000))
            
            return {
                "total_assets": assets_count,
                "total_exchanges": exchanges_count,
                "active_exchanges": active_exchanges_count,
                "database_available": True
            }
            
        except Exception as e:
            logger.error(f"Error getting assets domain stats: {e}")
            return {
                "error": str(e),
                "database_available": False
            }
    
    # ===================
    # COMMANDS - ASSETS LIST
    # ===================
    
    @RD.cmd("assets", aliases=["list_assets", "show_assets"])
    async def assets_command(self, event):
        """
        Komenda wyświetlania listy wszystkich assetów z paginacją.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "assets_list")
        
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
            assets_table = self.db.get_factory().get_assets_table()
            
            # Oblicz offset dla paginacji bazy danych
            offset = (page - 1) * self.default_page_size
            
            # Pobierz assety z dodatkowym rekordem dla sprawdzenia następnej strony
            assets = await assets_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not assets:
                await event.respond("💎 **Lista Assets**\n\n❌ Brak assetów do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(assets) > self.default_page_size
            page_assets = assets[:self.default_page_size]
            
            # Formatuj odpowiedź
            assets_text = f"💎 **Lista Assets - Strona {page}**\n\n"
            
            for i, asset in enumerate(page_assets, 1):
                asset_symbol = f"{asset['asset']}/{asset['quote']}"
                item_number = offset + i
                assets_text += f"{item_number}. `{asset_symbol}` (ID: {asset['id']})\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                assets_text += f"\n📄 Strona {page}"
                if has_next:
                    assets_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper.create_pagination_buttons
            # Nie znamy total_items więc użyjemy estimacji
            estimated_total = offset + len(page_assets) + (100 if has_next else 0)  # Estymacja
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_assets),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_assets)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "assets", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Wyszukaj", b"assets:search_prompt"),
                    Button.inline("🏦 Po giełdach", b"assets:by_exchange")
                ],
                [
                    Button.inline("⚡ Aktywne giełdy", b"assets:by_active_exchange"),
                    Button.inline("🔄 Odśwież", f"assets:page:{page}".encode())
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(assets_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "assets_list")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - ASSET SEARCH
    # ===================
    
    @RD.cmd("assets_search", aliases=["search_assets", "find_assets"])
    async def assets_search_command(self, event):
        """
        Komenda wyszukiwania assetów po nazwie.
        Użycie: /assets_search [nazwa]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "🔍 **Wyszukiwanie Assets**\n\n"
                "Podaj nazwę assetu do wyszukania:\n\n"
                "**Użycie:** `/assets_search NAZWA`\n"
                "**Przykład:** `/assets_search BTC`",
                buttons=[
                    [Button.inline("📋 Lista wszystkich", b"assets:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
            )
            return
        
        search_term = parts[1].strip()
        await self.log_action(user.id, "assets_search", {"search_term": search_term})
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Wyszukaj assety
            assets = await assets_table.search_by_asset(search_term)
            
            if not assets:
                await event.respond(
                    f"🔍 **Wyniki wyszukiwania: '{search_term}'**\n\n"
                    f"❌ Nie znaleziono assetów pasujących do '{search_term}'.",
                    buttons=[
                        [Button.inline("📋 Lista wszystkich", b"assets:page:1")],
                        [Button.inline("🔙 Wstecz", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj wyniki
            results_text = f"🔍 **Wyniki wyszukiwania: '{search_term}'**\n\n"
            results_text += f"✅ Znaleziono {len(assets)} asset(ów):\n\n"
            
            for i, asset in enumerate(assets[:15], 1):  # Limit 15 wyników
                asset_symbol = f"{asset['asset']}/{asset['quote']}"
                results_text += f"{i}. `{asset_symbol}` "
                results_text += f"[📊]({f'assets:details:{asset["id"]}'.encode()})\n"
            
            if len(assets) > 15:
                results_text += f"\n... i {len(assets) - 15} więcej"
            
            # Przyciski z szczegółami dla pierwszych kilku
            buttons = []
            
            # Przyciski szczegółów dla pierwszych 4 assetów
            details_buttons = []
            for asset in assets[:4]:
                asset_symbol = f"{asset['asset']}/{asset['quote']}"[:8]  # Skróć nazwę dla przycisku
                details_buttons.append(
                    Button.inline(f"📊 {asset_symbol}", f"assets:details:{asset['id']}".encode())
                )
            
            # Podziel na wiersze po 2 przyciski
            for i in range(0, len(details_buttons), 2):
                buttons.append(details_buttons[i:i+2])
            
            # Dodatkowe opcje
            buttons.extend([
                [Button.inline("📋 Lista wszystkich", b"assets:page:1")],
                [Button.inline("🔙 Menu główne", b"nav:home")]
            ])
            
            await event.respond(results_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "assets_search")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - ASSET INFO
    # ===================
    
    @RD.cmd("asset_info", aliases=["info_asset", "asset_details"])
    async def asset_info_command(self, event):
        """
        Komenda szczegółowych informacji o assecie.
        Użycie: /asset_info [symbol] lub /asset_info [id]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "📊 **Informacje o Asset**\n\n"
                "Podaj symbol lub ID assetu:\n\n"
                "**Użycie:**\n"
                "• `/asset_info BTCUSDT`\n"
                "• `/asset_info 123` (ID)\n"
                "• `/asset_info BTC` (nazwa assetu)",
                buttons=[
                    [Button.inline("📋 Lista assetów", b"assets:page:1")],
                    [Button.inline("🔙 Menu główne", b"nav:home")]
                ]
            )
            return
        
        identifier = parts[1].strip().upper()
        await self.log_action(user.id, "asset_info", {"identifier": identifier})
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Spróbuj znaleźć asset
            asset = None
            
            # 1. Spróbuj jako ID
            if identifier.isdigit():
                asset = await assets_table.get_by_id(int(identifier))
            
            # 2. Spróbuj jako symbol (BTCUSDT)
            if not asset and "/" not in identifier and len(identifier) >= 6:
                # Heurystyka: szukaj popularnych quote currencies
                for quote in ["USDT", "USD", "BTC", "ETH", "BNB"]:
                    if identifier.endswith(quote):
                        asset_part = identifier[:-len(quote)]
                        asset = await assets_table.get_by_asset_quote(asset_part, quote)
                        if asset:
                            break
            
            # 3. Spróbuj jako asset name
            if not asset:
                asset = await assets_table.get_by_asset(identifier)
            
            # 4. Spróbuj wyszukać po części nazwy
            if not asset:
                search_results = await assets_table.search_by_asset(identifier)
                if len(search_results) == 1:
                    asset = search_results[0]
                elif len(search_results) > 1:
                    # Wiele wyników - pokaż listę do wyboru
                    await self._show_multiple_assets_choice(event, search_results, identifier)
                    return
            
            if not asset:
                await event.respond(
                    f"❌ **Asset nie znaleziony**\n\n"
                    f"Nie można znaleźć assetu: `{identifier}`\n\n"
                    f"Spróbuj:\n"
                    f"• Pełny symbol (BTCUSDT)\n"
                    f"• Nazwę assetu (BTC)\n"
                    f"• ID numeryczne",
                    buttons=[
                        [Button.inline("🔍 Wyszukaj", b"assets:search_prompt")],
                        [Button.inline("📋 Lista assetów", b"assets:page:1")],
                        [Button.inline("🔙 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Pobierz informacje o giełdach dla tego assetu
            exchanges = await asset_exchanges_table.get_by_asset_id(asset['id'])
            
            # Formatuj szczegółowe informacje
            info_text = self.format_asset_info(asset)
            
            # Dodaj informacje o giełdach
            if exchanges:
                info_text += f"\n🏦 **Dostępne giełdy ({len(exchanges)}):**\n"
                for exchange in exchanges[:5]:  # Pokaż tylko pierwsze 5
                    exchange_name = exchange.get('display_name') or exchange.get('exchange_name')
                    info_text += f"• {exchange_name}\n"
                
                if len(exchanges) > 5:
                    info_text += f"• ... i {len(exchanges) - 5} więcej\n"
            else:
                info_text += f"\n🏦 **Giełdy:** Brak danych\n"
            
            # Przyciski
            buttons = [
                [
                    Button.inline("🏦 Giełdy", f"assets:exchanges:{asset['id']}".encode()),
                    Button.inline("📊 Analiza", f"assets:analysis:{asset['id']}".encode())
                ],
                [Button.inline("🔙 Lista assetów", b"assets:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.respond(info_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "asset_info")
            await event.respond(error_msg)
    
    async def _show_multiple_assets_choice(self, event, assets: List[Dict[str, Any]], search_term: str):
        """Pokazuje listę wyboru gdy znaleziono wiele assetów."""
        choice_text = f"🔍 **Znaleziono {len(assets)} assetów dla '{search_term}'**\n\n"
        choice_text += "Wybierz asset:\n\n"
        
        buttons = []
        for i, asset in enumerate(assets[:8], 1):  # Maksymalnie 8 opcji
            asset_symbol = f"{asset['asset']}/{asset['quote']}"
            choice_text += f"{i}. `{asset_symbol}`\n"
            
            button_text = asset_symbol[:15]  # Skróć dla przycisku
            buttons.append([Button.inline(f"{i}. {button_text}", f"assets:details:{asset['id']}".encode())])
        
        if len(assets) > 8:
            choice_text += f"\n... i {len(assets) - 8} więcej (użyj bardziej precyzyjnego wyszukiwania)"
        
        buttons.append([Button.inline("🔙 Wstecz", b"assets:page:1")])
        
        await event.respond(choice_text, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - PAGINATION
    # ===================
    
    @RD.cb(b"assets:page:")
    async def assets_page_callback(self, event):
        """Handler paginacji dla listy assetów."""
        try:
            # Extract page number from callback data
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            # Simulate command call for pagination
            event.raw_text = f"/assets {page}"
            await self.assets_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in assets pagination: {e}")
    
    @RD.cb(b"assets:page_info")
    async def assets_page_info_callback(self, event):
        """Informacje o aktualnej stronie."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"assets:jump")
    async def assets_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony, wyślij:\n"
            "`/assets [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/assets 5` - przejdź do strony 5\n"
            "• `/assets 1` - powrót do pierwszej strony\n\n"
            "**Wskazówki:**\n"
            "• Użyj liczb większych od 1\n"
            "• Jeśli strona nie istnieje, zostaniesz przekierowany do ostatniej dostępnej"
        )
        
        buttons = [
            [Button.inline("📋 Strona 1", b"assets:page:1")],
            [Button.inline("🔙 Wstecz", b"assets:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - EXCHANGE FILTERING
    # ===================
    
    @RD.cb(b"assets:by_exchange")
    async def assets_by_exchange_callback(self, event):
        """Pokazuje listę wszystkich giełd do wyboru."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            exchanges = await exchanges_table.get_all(limit=50)
            
            if not exchanges:
                await event.edit("🏦 **Wybór giełdy**\n\n❌ Brak dostępnych giełd.")
                return
            
            exchange_text = f"🏦 **Wybierz giełdę** ({len(exchanges)})\n\n"
            exchange_text += "Kliknij aby zobaczyć assety na konkretnej giełdzie:\n"
            
            # Przyciski giełd (maksymalnie 20)
            buttons = []
            for exchange in exchanges[:20]:
                exchange_name = exchange.get('display_name') or exchange['name']
                status_emoji = "🟢" if exchange.get('is_active') else "🔴"
                
                button_text = f"{status_emoji} {exchange_name[:18]}"
                callback_data = f"assets:exchange:{exchange['id']}".encode()
                buttons.append([Button.inline(button_text, callback_data)])
            
            if len(exchanges) > 20:
                exchange_text += f"\nPierwsze 20 z {len(exchanges)} giełd."
            
            buttons.extend([
                [Button.inline("⚡ Tylko aktywne", b"assets:by_active_exchange")],
                [Button.inline("🔙 Wstecz", b"assets:page:1")]
            ])
            
            await event.edit(exchange_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "assets_by_exchange")
            await event.edit(error_msg)
    
    @RD.cb(b"assets:by_active_exchange")
    async def assets_by_active_exchange_callback(self, event):
        """Pokazuje listę tylko aktywnych giełd do wyboru."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            
            exchanges = await exchanges_table.get_active(limit=30)
            
            if not exchanges:
                await event.edit(
                    "⚡ **Aktywne giełdy**\n\n❌ Brak aktywnych giełd.",
                    buttons=[[Button.inline("🔙 Wszystkie giełdy", b"assets:by_exchange")]]
                )
                return
            
            exchange_text = f"⚡ **Aktywne giełdy** ({len(exchanges)})\n\n"
            exchange_text += "Kliknij aby zobaczyć assety na konkretnej giełdzie:\n"
            
            # Przyciski giełd
            buttons = []
            for exchange in exchanges:
                exchange_name = exchange.get('display_name') or exchange['name']
                button_text = f"🟢 {exchange_name[:18]}"
                callback_data = f"assets:active_exchange:{exchange['id']}".encode()
                buttons.append([Button.inline(button_text, callback_data)])
            
            buttons.extend([
                [Button.inline("🏦 Wszystkie giełdy", b"assets:by_exchange")],
                [Button.inline("🔙 Wstecz", b"assets:page:1")]
            ])
            
            await event.edit(exchange_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "assets_by_active_exchange")
            await event.edit(error_msg)
    
    @RD.cb(b"assets:exchange:")
    async def assets_exchange_callback(self, event):
        """Pokazuje assety dla wybranej giełdy."""
        await self._show_assets_for_exchange(event, "exchange")
    
    @RD.cb(b"assets:active_exchange:")
    async def assets_active_exchange_callback(self, event):
        """Pokazuje assety dla wybranej aktywnej giełdy."""
        await self._show_assets_for_exchange(event, "active_exchange")
    
    async def _show_assets_for_exchange(self, event, exchange_type: str):
        """Helper method do wyświetlania assetów dla giełdy."""
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
            
            # Pobierz informacje o giełdzie
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.answer("❌ Giełda nie znaleziona", alert=True)
                return
            
            # Pobierz assety dla tej giełdy
            assets = await asset_exchanges_table.get_by_exchange_id(exchange_id, limit=50)
            
            exchange_name = exchange.get('display_name') or exchange['name']
            status_emoji = "🟢" if exchange.get('is_active') else "🔴"
            
            if not assets:
                await event.edit(
                    f"{status_emoji} **{exchange_name}**\n\n"
                    f"❌ Brak assetów na tej giełdzie.",
                    buttons=[
                        [Button.inline("🔙 Wybór giełdy", f"assets:by_{exchange_type}".encode())],
                        [Button.inline("📋 Wszystkie assety", b"assets:page:1")]
                    ]
                )
                return
            
            # Formatuj listę assetów
            assets_text = f"{status_emoji} **{exchange_name}**\n\n"
            assets_text += f"💎 **Assety ({len(assets)}):**\n\n"
            
            for i, asset_exchange in enumerate(assets[:20], 1):
                asset_symbol = f"{asset_exchange['asset']}/{asset_exchange['quote']}"
                assets_text += f"{i}. `{asset_symbol}`\n"
            
            if len(assets) > 20:
                assets_text += f"\n... i {len(assets) - 20} więcej"
            
            # Przyciski szczegółów dla pierwszych assetów
            buttons = []
            details_buttons = []
            
            for asset_exchange in assets[:6]:  # Pierwsze 6 assetów
                asset_symbol = f"{asset_exchange['asset']}/{asset_exchange['quote']}"[:8]
                details_buttons.append(
                    Button.inline(f"📊 {asset_symbol}", f"assets:details:{asset_exchange['asset_id']}".encode())
                )
            
            # Podziel na wiersze po 3 przyciski
            for i in range(0, len(details_buttons), 3):
                buttons.append(details_buttons[i:i+3])
            
            buttons.extend([
                [Button.inline("🔙 Wybór giełdy", f"assets:by_{exchange_type}".encode())],
                [Button.inline("📋 Wszystkie assety", b"assets:page:1")]
            ])
            
            await event.edit(assets_text, buttons=buttons)
            await self.log_action(user.id, "assets_for_exchange", {"exchange_id": exchange_id, "exchange_name": exchange_name})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "assets_for_exchange")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - ASSET DETAILS
    # ===================
    
    @RD.cb(b"assets:details:")
    async def assets_details_callback(self, event):
        """Pokazuje szczegółowe informacje o assecie."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract asset ID
            callback_data = event.data.decode()
            asset_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Pobierz asset
            asset = await assets_table.get_by_id(asset_id)
            if not asset:
                await event.answer("❌ Asset nie znaleziony", alert=True)
                return
            
            # Pobierz giełdy dla tego assetu
            exchanges = await asset_exchanges_table.get_by_asset_id(asset_id)
            
            # Formatuj szczegółowe informacje
            info_text = self.format_asset_info(asset)
            
            # Dodaj szczegółowe informacje o giełdach
            if exchanges:
                info_text += f"\n🏦 **Giełdy ({len(exchanges)}):**\n"
                for exchange in exchanges:
                    exchange_name = exchange.get('display_name') or exchange.get('exchange_name')
                    info_text += f"• {exchange_name}\n"
                
                # Dodaj statystyki
                active_exchanges = [e for e in exchanges if e.get('is_active', True)]
                if len(active_exchanges) != len(exchanges):
                    info_text += f"\n⚡ Aktywnych: {len(active_exchanges)}/{len(exchanges)}\n"
            else:
                info_text += f"\n🏦 **Giełdy:** Brak danych\n"
            
            # Przyciski
            buttons = [
                [Button.inline("🔄 Odśwież", f"assets:details:{asset_id}".encode())],
                [
                    Button.inline("📋 Lista assetów", b"assets:page:1"),
                    Button.inline("🔍 Wyszukaj inne", b"assets:search_prompt")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "asset_details_view", {"asset_id": asset_id, "asset": asset['asset'], "quote": asset['quote']})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "asset_details")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - SEARCH PROMPT
    # ===================
    
    @RD.cb(b"assets:search_prompt")
    async def assets_search_prompt_callback(self, event):
        """Pokazuje instrukcje wyszukiwania."""
        search_help = (
            "🔍 **Wyszukiwanie Assets**\n\n"
            "**Aby wyszukać asset, wyślij:**\n"
            "`/assets_search NAZWA`\n\n"
            "**Przykłady:**\n"
            "• `/assets_search BTC` - znajdzie Bitcoin\n"
            "• `/assets_search USDT` - znajdzie Tether\n"
            "• `/assets_search ETH` - znajdzie Ethereum\n\n"
            "**Wskazówki:**\n"
            "• Możesz użyć części nazwy\n"
            "• Wyszukiwanie nie rozróżnia wielkości liter\n"
            "• Jeśli znajdzie wiele wyników, pokaże listę do wyboru"
        )
        
        buttons = [
            [Button.inline("📋 Lista wszystkich", b"assets:page:1")],
            [Button.inline("🏠 Menu główne", b"nav:home")]
        ]
        
        await event.edit(search_help, buttons=buttons)
    
    # ===================
    # UTILITY METHODS
    # ===================
    
    def format_asset_info(self, asset: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o assecie (override z base class).
        
        Args:
            asset: Słownik z danymi assetu
            
        Returns:
            str: Sformatowane informacje o assecie
        """
        asset_symbol = f"{asset['asset']}/{asset['quote']}"
        
        response = f"💎 **Asset: {asset_symbol}**\n\n"
        response += f"🔤 **Base Asset:** `{asset['asset']}`\n"
        response += f"💰 **Quote Currency:** `{asset['quote']}`\n"
        response += f"🆔 **Database ID:** `{asset['id']}`\n"
        
        if 'created_at' in asset:
            response += f"📅 **Dodany:** {self._format_datetime(asset.get('created_at'))}\n"
        
        return response
