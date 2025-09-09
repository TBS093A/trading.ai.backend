"""
Kontroler Strategies dla Telegram - zarządzanie strategiami inwestycyjnymi, kupna i sprzedaży.

Ta klasa implementuje:
- Przeglądanie strategii inwestycyjnych z paginacją
- Zarządzanie strategiami kupna i sprzedaży dla portfeli
- Wyszukiwanie strategii po nazwach
- Interactive wizard do tworzenia nowych strategii
- CRUD operacje z confirmation dialogami
- Integrację z wszystkimi typami strategii w systemie

Autor: AI Assistant
"""

import logging
import traceback
from typing import List, Dict, Any, Optional
from telethon import Button

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, UserPermissionLevel, RD
from .controller_telegram_utils_ui import PaginationHelper, ConfirmationDialog, InteractiveWizard, ValidationHelper, TelegramUIUtils

logger = logging.getLogger(__name__)


class StrategiesTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla zarządzania strategiami inwestycyjnymi, kupna i sprzedaży w systemie Telegram.
    
    Zapewnia funkcjonalności:
    - Lista strategii inwestycyjnych z paginacją i wyszukiwaniem
    - Lista strategii kupna i sprzedaży z filtrowaniem po portfelach
    - Interactive wizard do tworzenia nowych strategii
    - CRUD operacje z confirmation dialogami dla administracji
    - Integrację z wszystkimi typami strategii i portfelami
    """
    
    DOMAIN = "strategies"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera strategii.
        
        Args:
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        
        # Konfiguracja paginacji
        self.default_page_size = 15
        self.max_page_size = 50
        
        # Strategy creation wizard
        self.strategy_wizards = {}  # user_id -> wizard_state
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny strategii."""
        try:
            if not self.db:
                return {"error": "Database not available"}
            
            await self.init_database()
            
            investment_strategies_table = self.db.get_factory().get_investment_strategies_table()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Pobierz podstawowe statystyki
            all_investment_strategies = await investment_strategies_table.get_all(limit=10000)
            enabled_investment_strategies = await investment_strategies_table.get_all_enabled_strategies(limit=10000)
            all_buy_strategies = await buy_strategies_table.get_all(limit=10000)
            all_sell_strategies = await sell_strategies_table.get_all(limit=10000)
            
            # Policz strategie według typów
            market_buy_strategies = await buy_strategies_table.get_by_strategy_type("MARKET", limit=10000)
            limit_buy_strategies = await buy_strategies_table.get_by_strategy_type("LIMIT", limit=10000)
            market_sell_strategies = await sell_strategies_table.get_by_strategy_type("MARKET", limit=10000)
            limit_sell_strategies = await sell_strategies_table.get_by_strategy_type("LIMIT", limit=10000)
            
            # Policz strategie procentowe vs absolute
            percent_buy_strategies = await buy_strategies_table.get_percent_based_strategies(limit=10000)
            percent_sell_strategies = await sell_strategies_table.get_percent_based_strategies(limit=10000)
            
            return {
                "total_investment_strategies": len(all_investment_strategies),
                "enabled_investment_strategies": len(enabled_investment_strategies),
                "disabled_investment_strategies": len(all_investment_strategies) - len(enabled_investment_strategies),
                "total_buy_strategies": len(all_buy_strategies),
                "total_sell_strategies": len(all_sell_strategies),
                "market_buy_strategies": len(market_buy_strategies),
                "limit_buy_strategies": len(limit_buy_strategies),
                "market_sell_strategies": len(market_sell_strategies),
                "limit_sell_strategies": len(limit_sell_strategies),
                "percent_buy_strategies": len(percent_buy_strategies),
                "percent_sell_strategies": len(percent_sell_strategies),
                "absolute_buy_strategies": len(all_buy_strategies) - len(percent_buy_strategies),
                "absolute_sell_strategies": len(all_sell_strategies) - len(percent_sell_strategies),
                "database_available": True
            }
            
        except Exception as e:
            logger.error(f"Error getting strategies domain stats: {e}")
            return {
                "error": str(e),
                "database_available": False
            }
    
    # ===================
    # COMMANDS - INVESTMENT STRATEGIES
    # ===================
    
    @RD.cmd("investment_strategies", aliases=["list_investment_strategies", "show_investment_strategies"])
    async def investment_strategies_command(self, event):
        """
        Komenda wyświetlania listy strategii inwestycyjnych z paginacją.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "investment_strategies_list")
        
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
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Oblicz offset dla paginacji bazy danych
            offset = (page - 1) * self.default_page_size
            
            # Pobierz strategie z dodatkowym rekordem dla sprawdzenia następnej strony
            strategies = await strategies_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not strategies:
                await event.respond("📊 **Strategie Inwestycyjne**\n\n❌ Brak strategii do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(strategies) > self.default_page_size
            page_strategies = strategies[:self.default_page_size]
            
            # Formatuj odpowiedź
            strategies_text = f"📊 **Strategie Inwestycyjne - Strona {page}**\n\n"
            
            for i, strategy in enumerate(page_strategies, 1):
                item_number = offset + i
                status_emoji = "✅" if strategy.get('enabled') else "❌"
                
                strategies_text += f"{item_number}. {status_emoji} **{strategy['name']}**\n"
                strategies_text += f"    📝 {strategy['description'][:60]}{'...' if len(strategy['description']) > 60 else ''}\n"
                strategies_text += f"    ID: {strategy['id']} | Utworzona: {self._format_datetime(strategy.get('created_at', ''))}\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                strategies_text += f"\n📄 Strona {page}"
                if has_next:
                    strategies_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper.create_pagination_buttons
            estimated_total = offset + len(page_strategies) + (100 if has_next else 0)  # Estymacja
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_strategies),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_strategies)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "strat", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("✅ Tylko aktywne", b"strat:enabled_only"),
                    Button.inline("🔍 Wyszukaj", b"strat:search_prompt")
                ],
                [
                    Button.inline("➕ Nowa strategia", b"strat:create_wizard:start"),
                    Button.inline("📊 Statystyki", b"strat:stats")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(strategies_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "investment_strategies_list")
            await event.respond(error_msg)
    
    @RD.cmd("buy_strategies", aliases=["list_buy_strategies", "show_buy_strategies"])
    async def buy_strategies_command(self, event):
        """
        Komenda wyświetlania listy strategii kupna z paginacją.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "buy_strategies_list")
        
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
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Oblicz offset dla paginacji bazy danych
            offset = (page - 1) * self.default_page_size
            
            # Pobierz strategie z dodatkowym rekordem dla sprawdzenia następnej strony
            strategies = await buy_strategies_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not strategies:
                await event.respond("📈 **Strategie Kupna**\n\n❌ Brak strategii kupna do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(strategies) > self.default_page_size
            page_strategies = strategies[:self.default_page_size]
            
            # Formatuj odpowiedź
            strategies_text = f"📈 **Strategie Kupna - Strona {page}**\n\n"
            
            for i, strategy in enumerate(page_strategies, 1):
                item_number = offset + i
                exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
                type_emoji = "⚡" if strategy['type'] == "MARKET" else "📊"
                amount_type = "%" if strategy['is_percent'] else strategy['currency']
                
                strategies_text += f"{item_number}. {type_emoji} **{strategy['type']} {strategy['currency']}**\n"
                strategies_text += f"    🏦 {exchange_name} | {strategy['account_type']}\n"
                strategies_text += f"    💰 {strategy['movement_amount']} {amount_type}\n"
                strategies_text += f"    ID: {strategy['id']}\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                strategies_text += f"\n📄 Strona {page}"
                if has_next:
                    strategies_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper.create_pagination_buttons
            estimated_total = offset + len(page_strategies) + (100 if has_next else 0)  # Estymacja
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_strategies),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_strategies)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "buy_strat", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("⚡ MARKET", b"buy_strat:type:MARKET"),
                    Button.inline("📊 LIMIT", b"buy_strat:type:LIMIT")
                ],
                [
                    Button.inline("📈 Procent", b"buy_strat:percent_based"),
                    Button.inline("💰 Kwota", b"buy_strat:absolute_based")
                ],
                [
                    Button.inline("🏦 Po giełdach", b"buy_strat:by_exchange"),
                    Button.inline("📊 Statystyki", b"buy_strat:stats")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(strategies_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategies_list")
            await event.respond(error_msg)
    
    @RD.cmd("sell_strategies", aliases=["list_sell_strategies", "show_sell_strategies"])
    async def sell_strategies_command(self, event):
        """
        Komenda wyświetlania listy strategii sprzedaży z paginacją.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "sell_strategies_list")
        
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
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Oblicz offset dla paginacji bazy danych
            offset = (page - 1) * self.default_page_size
            
            # Pobierz strategie z dodatkowym rekordem dla sprawdzenia następnej strony
            strategies = await sell_strategies_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not strategies:
                await event.respond("📉 **Strategie Sprzedaży**\n\n❌ Brak strategii sprzedaży do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(strategies) > self.default_page_size
            page_strategies = strategies[:self.default_page_size]
            
            # Formatuj odpowiedź
            strategies_text = f"📉 **Strategie Sprzedaży - Strona {page}**\n\n"
            
            for i, strategy in enumerate(page_strategies, 1):
                item_number = offset + i
                exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
                type_emoji = "⚡" if strategy['type'] == "MARKET" else "📊"
                amount_type = "%" if strategy['is_percent'] else strategy['currency']
                
                strategies_text += f"{item_number}. {type_emoji} **{strategy['type']} {strategy['currency']}**\n"
                strategies_text += f"    🏦 {exchange_name} | {strategy['account_type']}\n"
                strategies_text += f"    💰 {strategy['movement_amount']} {amount_type}\n"
                strategies_text += f"    ID: {strategy['id']}\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                strategies_text += f"\n📄 Strona {page}"
                if has_next:
                    strategies_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper.create_pagination_buttons
            estimated_total = offset + len(page_strategies) + (100 if has_next else 0)  # Estymacja
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_strategies),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_strategies)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "sell_strat", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("⚡ MARKET", b"sell_strat:type:MARKET"),
                    Button.inline("📊 LIMIT", b"sell_strat:type:LIMIT")
                ],
                [
                    Button.inline("📉 Procent", b"sell_strat:percent_based"),
                    Button.inline("💰 Kwota", b"sell_strat:absolute_based")
                ],
                [
                    Button.inline("🏦 Po giełdach", b"sell_strat:by_exchange"),
                    Button.inline("📊 Statystyki", b"sell_strat:stats")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(strategies_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategies_list")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - SEARCH
    # ===================
    
    @RD.cmd("investment_strategy_search", aliases=["search_investment_strategies", "find_investment_strategies"])
    async def investment_strategy_search_command(self, event):
        """
        Komenda wyszukiwania strategii inwestycyjnych po nazwie.
        Użycie: /investment_strategy_search [nazwa]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "🔍 **Wyszukiwanie Strategii Inwestycyjnych**\n\n"
                "Podaj nazwę strategii do wyszukania:\n\n"
                "**Użycie:** `/investment_strategy_search NAZWA`\n"
                "**Przykład:** `/investment_strategy_search hodl`",
                buttons=[
                    [Button.inline("📋 Lista wszystkich", b"strat:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
            )
            return
        
        search_term = parts[1].strip()
        await self.log_action(user.id, "investment_strategy_search", {"search_term": search_term})
        
        try:
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Wyszukaj strategie
            strategies = await strategies_table.search_by_name(search_term)
            
            if not strategies:
                await event.respond(
                    f"🔍 **Wyniki wyszukiwania: '{search_term}'**\n\n"
                    f"❌ Nie znaleziono strategii pasujących do '{search_term}'.",
                    buttons=[
                        [Button.inline("📋 Lista wszystkich", b"strat:page:1")],
                        [Button.inline("🔙 Wstecz", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj wyniki
            results_text = f"🔍 **Wyniki wyszukiwania: '{search_term}'**\n\n"
            results_text += f"✅ Znaleziono {len(strategies)} strategię(i):\n\n"
            
            for i, strategy in enumerate(strategies[:10], 1):  # Limit 10 wyników
                status_emoji = "✅" if strategy.get('enabled') else "❌"
                results_text += f"{i}. {status_emoji} **{strategy['name']}**\n"
                results_text += f"   📝 {strategy['description'][:50]}{'...' if len(strategy['description']) > 50 else ''}\n"
            
            if len(strategies) > 10:
                results_text += f"\n... i {len(strategies) - 10} więcej"
            
            # Przyciski z szczegółami dla pierwszych kilku
            buttons = []
            details_buttons = []
            for strategy in strategies[:4]:
                strategy_name = strategy['name'][:15]  # Skróć nazwę dla przycisku
                details_buttons.append(
                    Button.inline(f"📊 {strategy_name}", f"strat:details:{strategy['id']}".encode())
                )
            
            # Podziel na wiersze po 2 przyciski
            for i in range(0, len(details_buttons), 2):
                buttons.append(details_buttons[i:i+2])
            
            # Dodatkowe opcje
            buttons.extend([
                [Button.inline("📋 Lista wszystkich", b"strat:page:1")],
                [Button.inline("🔙 Menu główne", b"nav:home")]
            ])
            
            await event.respond(results_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "investment_strategy_search")
            await event.respond(error_msg)
    
    @RD.cmd("buy_strategy_search", aliases=["search_buy_strategies", "find_buy_strategies"])
    async def buy_strategy_search_command(self, event):
        """
        Komenda wyszukiwania strategii kupna po giełdzie lub walucie.
        Użycie: /buy_strategy_search [nazwa_giełdy/waluta]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "🔍 **Wyszukiwanie Strategii Kupna**\n\n"
                "Podaj nazwę giełdy lub waluty:\n\n"
                "**Użycie:** `/buy_strategy_search NAZWA`\n"
                "**Przykłady:**\n"
                "• `/buy_strategy_search binance` - strategie na Binance\n"
                "• `/buy_strategy_search BTC` - strategie dla Bitcoin",
                buttons=[
                    [Button.inline("📈 Lista wszystkich", b"buy_strat:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
            )
            return
        
        search_term = parts[1].strip().upper()
        await self.log_action(user.id, "buy_strategy_search", {"search_term": search_term})
        
        try:
            await self.init_database()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Wyszukaj strategie (filtrowanie po walucie lub nazwie giełdy)
            all_strategies = await buy_strategies_table.get_all(limit=1000)
            matching_strategies = []
            
            for strategy in all_strategies:
                exchange_name = (strategy.get('exchange_display_name') or strategy['exchange_name']).upper()
                currency = strategy['currency'].upper()
                
                if search_term in exchange_name or search_term in currency:
                    matching_strategies.append(strategy)
            
            if not matching_strategies:
                await event.respond(
                    f"🔍 **Wyniki wyszukiwania: '{search_term}'**\n\n"
                    f"❌ Nie znaleziono strategii kupna pasujących do '{search_term}'.",
                    buttons=[
                        [Button.inline("📈 Lista wszystkich", b"buy_strat:page:1")],
                        [Button.inline("🔙 Wstecz", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj wyniki
            results_text = f"🔍 **Wyniki wyszukiwania strategii kupna: '{search_term}'**\n\n"
            results_text += f"✅ Znaleziono {len(matching_strategies)} strategię(i):\n\n"
            
            for i, strategy in enumerate(matching_strategies[:10], 1):  # Limit 10 wyników
                exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
                type_emoji = "⚡" if strategy['type'] == "MARKET" else "📊"
                amount_type = "%" if strategy['is_percent'] else strategy['currency']
                
                results_text += f"{i}. {type_emoji} **{strategy['currency']} {strategy['type']}**\n"
                results_text += f"   🏦 {exchange_name} | 💰 {strategy['movement_amount']} {amount_type}\n"
            
            if len(matching_strategies) > 10:
                results_text += f"\n... i {len(matching_strategies) - 10} więcej"
            
            # Przyciski z szczegółami
            buttons = []
            details_buttons = []
            for strategy in matching_strategies[:4]:
                currency = strategy['currency'][:4]
                exchange_short = (strategy.get('exchange_display_name') or strategy['exchange_name'])[:8]
                details_buttons.append(
                    Button.inline(f"📈 {currency}@{exchange_short}", f"buy_strat:details:{strategy['id']}".encode())
                )
            
            # Podziel na wiersze po 2 przyciski
            for i in range(0, len(details_buttons), 2):
                buttons.append(details_buttons[i:i+2])
            
            # Dodatkowe opcje
            buttons.extend([
                [Button.inline("📈 Lista wszystkich", b"buy_strat:page:1")],
                [Button.inline("🔙 Menu główne", b"nav:home")]
            ])
            
            await event.respond(results_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_search")
            await event.respond(error_msg)
    
    @RD.cmd("sell_strategy_search", aliases=["search_sell_strategies", "find_sell_strategies"])
    async def sell_strategy_search_command(self, event):
        """
        Komenda wyszukiwania strategii sprzedaży po giełdzie lub walucie.
        Użycie: /sell_strategy_search [nazwa_giełdy/waluta]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "🔍 **Wyszukiwanie Strategii Sprzedaży**\n\n"
                "Podaj nazwę giełdy lub waluty:\n\n"
                "**Użycie:** `/sell_strategy_search NAZWA`\n"
                "**Przykłady:**\n"
                "• `/sell_strategy_search coinbase` - strategie na Coinbase\n"
                "• `/sell_strategy_search ETH` - strategie dla Ethereum",
                buttons=[
                    [Button.inline("📉 Lista wszystkich", b"sell_strat:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
            )
            return
        
        search_term = parts[1].strip().upper()
        await self.log_action(user.id, "sell_strategy_search", {"search_term": search_term})
        
        try:
            await self.init_database()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Wyszukaj strategie (filtrowanie po walucie lub nazwie giełdy)
            all_strategies = await sell_strategies_table.get_all(limit=1000)
            matching_strategies = []
            
            for strategy in all_strategies:
                exchange_name = (strategy.get('exchange_display_name') or strategy['exchange_name']).upper()
                currency = strategy['currency'].upper()
                
                if search_term in exchange_name or search_term in currency:
                    matching_strategies.append(strategy)
            
            if not matching_strategies:
                await event.respond(
                    f"🔍 **Wyniki wyszukiwania: '{search_term}'**\n\n"
                    f"❌ Nie znaleziono strategii sprzedaży pasujących do '{search_term}'.",
                    buttons=[
                        [Button.inline("📉 Lista wszystkich", b"sell_strat:page:1")],
                        [Button.inline("🔙 Wstecz", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj wyniki
            results_text = f"🔍 **Wyniki wyszukiwania strategii sprzedaży: '{search_term}'**\n\n"
            results_text += f"✅ Znaleziono {len(matching_strategies)} strategię(i):\n\n"
            
            for i, strategy in enumerate(matching_strategies[:10], 1):  # Limit 10 wyników
                exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
                type_emoji = "⚡" if strategy['type'] == "MARKET" else "📊"
                amount_type = "%" if strategy['is_percent'] else strategy['currency']
                
                results_text += f"{i}. {type_emoji} **{strategy['currency']} {strategy['type']}**\n"
                results_text += f"   🏦 {exchange_name} | 💰 {strategy['movement_amount']} {amount_type}\n"
            
            if len(matching_strategies) > 10:
                results_text += f"\n... i {len(matching_strategies) - 10} więcej"
            
            # Przyciski z szczegółami
            buttons = []
            details_buttons = []
            for strategy in matching_strategies[:4]:
                currency = strategy['currency'][:4]
                exchange_short = (strategy.get('exchange_display_name') or strategy['exchange_name'])[:8]
                details_buttons.append(
                    Button.inline(f"📉 {currency}@{exchange_short}", f"sell_strat:details:{strategy['id']}".encode())
                )
            
            # Podziel na wiersze po 2 przyciski
            for i in range(0, len(details_buttons), 2):
                buttons.append(details_buttons[i:i+2])
            
            # Dodatkowe opcje
            buttons.extend([
                [Button.inline("📉 Lista wszystkich", b"sell_strat:page:1")],
                [Button.inline("🔙 Menu główne", b"nav:home")]
            ])
            
            await event.respond(results_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_search")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - STRATEGY CREATION
    # ===================
    
    @RD.cmd("strategy_create", aliases=["create_strategy", "new_strategy"])
    async def strategy_create_command(self, event):
        """
        Interactive wizard do tworzenia nowej strategii inwestycyjnej.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Sprawdź uprawnienia do tworzenia strategii
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.respond("🔒 **Brak uprawnień**\n\nTworzenie strategii wymaga uprawnień TRADER lub wyższych.")
            return
        
        await self.log_action(user.id, "strategy_create_start")
        
        # Inicjalizuj wizard dla użytkownika
        self.strategy_wizards[user.id] = {
            "step": "start",
            "data": {},
            "created_at": self._get_current_timestamp()
        }
        
        wizard_text = (
            "🧙‍♂️ **Kreator Nowej Strategii**\n\n"
            "Witaj w kreatorze strategii inwestycyjnych!\n\n"
            "**Możesz utworzyć:**\n"
            "📊 **Strategię Inwestycyjną** - ogólna strategia z nazwą i opisem\n"
            "📈 **Strategię Kupna** - strategia dla konkretnego portfela\n"
            "📉 **Strategię Sprzedaży** - strategia dla konkretnego portfela\n\n"
            "Wybierz typ strategii do utworzenia:"
        )
        
        buttons = [
            [Button.inline("📊 Strategia Inwestycyjna", b"strat:create_wizard:investment")],
            [
                Button.inline("📈 Strategia Kupna", b"strat:create_wizard:buy"),
                Button.inline("📉 Strategia Sprzedaży", b"strat:create_wizard:sell")
            ],
            [Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")]
        ]
        
        await event.respond(wizard_text, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - PAGINATION
    # ===================
    
    @RD.cb(b"strat:page:")
    async def strategies_page_callback(self, event):
        """Handler paginacji dla listy strategii inwestycyjnych."""
        try:
            # Extract page number from callback data
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            # Simulate command call for pagination
            event.raw_text = f"/investment_strategies {page}"
            await self.investment_strategies_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in strategies pagination: {e}")
    
    @RD.cb(b"buy_strat:page:")
    async def buy_strategies_page_callback(self, event):
        """Handler paginacji dla listy strategii kupna."""
        try:
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            event.raw_text = f"/buy_strategies {page}"
            await self.buy_strategies_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in buy strategies pagination: {e}")
    
    @RD.cb(b"sell_strat:page:")
    async def sell_strategies_page_callback(self, event):
        """Handler paginacji dla listy strategii sprzedaży."""
        try:
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            event.raw_text = f"/sell_strategies {page}"
            await self.sell_strategies_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in sell strategies pagination: {e}")
    
    @RD.cb(b"strat:page_info")
    async def strategies_page_info_callback(self, event):
        """Informacje o aktualnej stronie strategii."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"buy_strat:page_info")
    async def buy_strategies_page_info_callback(self, event):
        """Informacje o aktualnej stronie strategii kupna."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"sell_strat:page_info")
    async def sell_strategies_page_info_callback(self, event):
        """Informacje o aktualnej stronie strategii sprzedaży."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"strat:jump")
    async def strategies_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony strategii inwestycyjnych, wyślij:\n"
            "`/investment_strategies [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/investment_strategies 3` - przejdź do strony 3\n"
            "• `/investment_strategies 1` - powrót do pierwszej strony"
        )
        
        buttons = [
            [Button.inline("📊 Strona 1", b"strat:page:1")],
            [Button.inline("🔙 Wstecz", b"strat:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    @RD.cb(b"buy_strat:jump")
    async def buy_strategies_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper dla strategii kupna."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony strategii kupna, wyślij:\n"
            "`/buy_strategies [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/buy_strategies 2` - przejdź do strony 2\n"
            "• `/buy_strategies 1` - powrót do pierwszej strony"
        )
        
        buttons = [
            [Button.inline("📈 Strona 1", b"buy_strat:page:1")],
            [Button.inline("🔙 Wstecz", b"buy_strat:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    @RD.cb(b"sell_strat:jump")
    async def sell_strategies_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper dla strategii sprzedaży."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony strategii sprzedaży, wyślij:\n"
            "`/sell_strategies [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/sell_strategies 2` - przejdź do strony 2\n"
            "• `/sell_strategies 1` - powrót do pierwszej strony"
        )
        
        buttons = [
            [Button.inline("📉 Strona 1", b"sell_strat:page:1")],
            [Button.inline("🔙 Wstecz", b"sell_strat:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - FILTERING AND STATS
    # ===================
    
    @RD.cb(b"strat:enabled_only")
    async def strategies_enabled_only_callback(self, event):
        """Pokazuje tylko włączone strategie inwestycyjne."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            enabled_strategies = await strategies_table.get_all_enabled_strategies(limit=50)
            
            if not enabled_strategies:
                await event.edit(
                    "✅ **Aktywne Strategie**\n\n❌ Brak aktywnych strategii inwestycyjnych.",
                    buttons=[
                        [Button.inline("📊 Wszystkie strategie", b"strat:page:1")],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            strategies_text = f"✅ **Aktywne Strategie** ({len(enabled_strategies)})\n\n"
            
            for i, strategy in enumerate(enabled_strategies[:15], 1):  # Pokaż pierwsze 15
                strategies_text += f"{i}. ✅ **{strategy['name']}**\n"
                strategies_text += f"   📝 {strategy['description'][:50]}{'...' if len(strategy['description']) > 50 else ''}\n"
            
            if len(enabled_strategies) > 15:
                strategies_text += f"\n... i {len(enabled_strategies) - 15} więcej"
            
            # Przyciski szczegółów
            buttons = []
            details_buttons = []
            for strategy in enabled_strategies[:6]:
                strategy_name = strategy['name'][:12]
                details_buttons.append(
                    Button.inline(f"📊 {strategy_name}", f"strat:details:{strategy['id']}".encode())
                )
            
            # Podziel na wiersze po 3 przyciski
            for i in range(0, len(details_buttons), 3):
                buttons.append(details_buttons[i:i+3])
            
            buttons.extend([
                [
                    Button.inline("📊 Wszystkie strategie", b"strat:page:1"),
                    Button.inline("🔄 Odśwież", b"strat:enabled_only")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(strategies_text, buttons=buttons)
            await self.log_action(user.id, "strategies_enabled_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategies_enabled")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:stats")
    async def strategies_stats_callback(self, event):
        """Pokazuje statystyki strategii."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            stats = await self.get_domain_specific_stats()
            
            if 'error' in stats:
                await event.edit(f"❌ **Błąd pobierania statystyk**\n\n{stats['error']}")
                return
            
            stats_text = "📊 **Statystyki Strategii**\n\n"
            
            # Investment strategies
            stats_text += f"📊 **Strategie Inwestycyjne:**\n"
            stats_text += f"• Wszystkie: {stats['total_investment_strategies']}\n"
            stats_text += f"• Aktywne: {stats['enabled_investment_strategies']}\n"
            stats_text += f"• Nieaktywne: {stats['disabled_investment_strategies']}\n\n"
            
            # Buy strategies
            stats_text += f"📈 **Strategie Kupna:** {stats['total_buy_strategies']}\n"
            stats_text += f"• MARKET: {stats['market_buy_strategies']}\n"
            stats_text += f"• LIMIT: {stats['limit_buy_strategies']}\n"
            stats_text += f"• Procentowe: {stats['percent_buy_strategies']}\n"
            stats_text += f"• Kwotowe: {stats['absolute_buy_strategies']}\n\n"
            
            # Sell strategies
            stats_text += f"📉 **Strategie Sprzedaży:** {stats['total_sell_strategies']}\n"
            stats_text += f"• MARKET: {stats['market_sell_strategies']}\n"
            stats_text += f"• LIMIT: {stats['limit_sell_strategies']}\n"
            stats_text += f"• Procentowe: {stats['percent_sell_strategies']}\n"
            stats_text += f"• Kwotowe: {stats['absolute_sell_strategies']}\n"
            
            # Oblicz procenty
            if stats['total_investment_strategies'] > 0:
                enabled_percent = (stats['enabled_investment_strategies'] / stats['total_investment_strategies']) * 100
                stats_text += f"\n📈 **Procent aktywnych:** {enabled_percent:.1f}%\n"
            
            buttons = [
                [
                    Button.inline("📊 Investment", b"strat:page:1"),
                    Button.inline("📈 Kupna", b"buy_strat:page:1"),
                    Button.inline("📉 Sprzedaży", b"sell_strat:page:1")
                ],
                [Button.inline("🔄 Odśwież", b"strat:stats")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(stats_text, buttons=buttons)
            await self.log_action(user.id, "strategies_stats_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategies_stats")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - STRATEGY CREATION WIZARD
    # ===================
    
    @RD.cb(b"strat:create_wizard:")
    async def strategy_create_wizard_callback(self, event):
        """Handler kreatora strategii."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        callback_data = event.data.decode()
        wizard_step = callback_data.split(":")[-1]
        
        # Sprawdź uprawnienia
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do tworzenia strategii!", alert=True)
            return
        
        if wizard_step == "cancel":
            # Anuluj wizard
            if user.id in self.strategy_wizards:
                del self.strategy_wizards[user.id]
            
            await event.edit(
                "❌ **Kreator anulowany**\n\nTworzenie strategii zostało anulowane.",
                buttons=[[Button.inline("🔙 Powrót", b"strat:page:1")]]
            )
            return
        
        elif wizard_step == "start":
            # Rozpocznij wizard (to samo co komenda)
            await self.strategy_create_command(event)
            return
        
        elif wizard_step == "investment":
            # Kreator strategii inwestycyjnej
            await self._handle_investment_strategy_wizard(event, user)
        
        elif wizard_step == "buy":
            # Kreator strategii kupna
            await self._handle_buy_strategy_wizard(event, user)
        
        elif wizard_step == "sell":
            # Kreator strategii sprzedaży
            await self._handle_sell_strategy_wizard(event, user)
        
        else:
            await event.answer("❌ Nieprawidłowy krok kreatora", alert=True)
    
    async def _handle_investment_strategy_wizard(self, event, user):
        """Obsługa kreatora strategii inwestycyjnej."""
        wizard_text = (
            "📊 **Kreator Strategii Inwestycyjnej**\n\n"
            "Aby utworzyć strategię inwestycyjną, wyślij wiadomość w formacie:\n\n"
            "**Nazwa strategii**\n"
            "**Opis strategii (może być długi)**\n\n"
            "**Przykład:**\n"
            "`HODL Long Term`\n"
            "`Długoterminowa strategia trzymania kryptowalut z okazjonalnym DCA (Dollar Cost Averaging).`\n\n"
            "📝 **Wyślij swoją strategię jako następną wiadomość.**"
        )
        
        # Zapisz stan wizarda
        self.strategy_wizards[user.id] = {
            "step": "investment_waiting_input",
            "data": {"type": "investment"},
            "created_at": self._get_current_timestamp()
        }
        
        buttons = [
            [Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")]
        ]
        
        await event.edit(wizard_text, buttons=buttons)
    
    async def _handle_buy_strategy_wizard(self, event, user):
        """Obsługa kreatora strategii kupna."""
        try:
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz dostępne portfele użytkownika (tu używamy wszystkich dla admina)
            available_wallets = await wallets_table.get_enabled_accounts(limit=50)
            
            if not available_wallets:
                await event.edit(
                    "❌ **Brak dostępnych portfeli**\n\n"
                    "Nie znaleziono aktywnych portfeli do utworzenia strategii kupna.\n"
                    "Najpierw utwórz lub aktywuj portfele.",
                    buttons=[[Button.inline("🔙 Powrót", b"strat:page:1")]]
                )
                return
            
            wizard_text = f"📈 **Kreator Strategii Kupna**\n\n"
            wizard_text += f"Wybierz portfel dla strategii kupna ({len(available_wallets)} dostępnych):\n"
            
            buttons = []
            for wallet in available_wallets[:12]:  # Maksymalnie 12 portfeli
                exchange_name = (wallet.get('exchange_display_name') or wallet['exchange_name'])[:12]
                wallet_desc = f"{wallet['currency']} {wallet['type']}"
                button_text = f"{exchange_name} {wallet_desc}"
                
                buttons.append([Button.inline(
                    button_text, 
                    f"buy_strat:create:{wallet['id']}".encode()
                )])
            
            if len(available_wallets) > 12:
                wizard_text += f"\nPierwsze 12 z {len(available_wallets)} portfeli."
            
            buttons.append([Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")])
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_wizard")
            await event.edit(error_msg)
    
    async def _handle_sell_strategy_wizard(self, event, user):
        """Obsługa kreatora strategii sprzedaży."""
        try:
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz dostępne portfele użytkownika
            available_wallets = await wallets_table.get_enabled_accounts(limit=50)
            
            if not available_wallets:
                await event.edit(
                    "❌ **Brak dostępnych portfeli**\n\n"
                    "Nie znaleziono aktywnych portfeli do utworzenia strategii sprzedaży.\n"
                    "Najpierw utwórz lub aktywuj portfele.",
                    buttons=[[Button.inline("🔙 Powrót", b"strat:page:1")]]
                )
                return
            
            wizard_text = f"📉 **Kreator Strategii Sprzedaży**\n\n"
            wizard_text += f"Wybierz portfel dla strategii sprzedaży ({len(available_wallets)} dostępnych):\n"
            
            buttons = []
            for wallet in available_wallets[:12]:  # Maksymalnie 12 portfeli
                exchange_name = (wallet.get('exchange_display_name') or wallet['exchange_name'])[:12]
                wallet_desc = f"{wallet['currency']} {wallet['type']}"
                button_text = f"{exchange_name} {wallet_desc}"
                
                buttons.append([Button.inline(
                    button_text, 
                    f"sell_strat:create:{wallet['id']}".encode()
                )])
            
            if len(available_wallets) > 12:
                wizard_text += f"\nPierwsze 12 z {len(available_wallets)} portfeli."
            
            buttons.append([Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")])
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_wizard")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - ADMIN ACTIONS WITH CONFIRMATION
    # ===================
    
    @RD.cb(b"strat:enable:")
    async def strategy_enable_callback(self, event):
        """Pokazuje potwierdzenie włączenia strategii inwestycyjnej."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            # Sprawdź czy strategia już jest włączona
            if strategy.get('enabled'):
                await event.answer(f"ℹ️ Strategia {strategy['name']} jest już włączona", alert=False)
                return
            
            # Pokazuje dialog potwierdzenia
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Włączenie strategii {strategy['name']}",
                f"ID: {strategy_id}",
                "Włączenie strategii spowoduje jej aktywację w systemie."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "strat:confirm_enable",
                str(strategy_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_enable")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:disable:")
    async def strategy_disable_callback(self, event):
        """Pokazuje potwierdzenie wyłączenia strategii inwestycyjnej."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            # Sprawdź czy strategia już jest wyłączona
            if not strategy.get('enabled'):
                await event.answer(f"ℹ️ Strategia {strategy['name']} jest już wyłączona", alert=False)
                return
            
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Wyłączenie strategii {strategy['name']}",
                f"ID: {strategy_id}",
                "Wyłączenie strategii spowoduje jej dezaktywację w systemie."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "strat:confirm_disable",
                str(strategy_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_disable")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:delete:")
    async def strategy_delete_callback(self, event):
        """Pokazuje potwierdzenie usunięcia strategii inwestycyjnej."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Usunięcie strategii {strategy['name']}",
                f"ID: {strategy_id}",
                "⚠️ UWAGA: Ta akcja jest nieodwracalna! Strategia zostanie trwale usunięta z bazy danych."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "strat:confirm_delete",
                str(strategy_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_delete")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:confirm_enable:")
    async def strategy_confirm_enable_callback(self, event):
        """Wykonuje włączenie strategii po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.edit("❌ **Błąd**\n\nStrategia nie znaleziona.")
                return
            
            # Włącz strategię
            success = await strategies_table.enable_strategy(strategy_id)
            
            if success:
                success_msg = self.create_success_message(
                    f"Włączenie strategii {strategy['name']}",
                    f"✅ Strategia została pomyślnie włączona.\n🆔 ID: {strategy_id}\n⚡ Status: Aktywna"
                )
                
                buttons = [
                    [Button.inline("📊 Szczegóły", f"strat:details:{strategy_id}".encode())],
                    [Button.inline("📊 Lista strategii", b"strat:page:1")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "strategy_enabled", {
                    "strategy_id": strategy_id, 
                    "strategy_name": strategy['name']
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się włączyć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_confirm_enable")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:confirm_disable:")
    async def strategy_confirm_disable_callback(self, event):
        """Wykonuje wyłączenie strategii po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.edit("❌ **Błąd**\n\nStrategia nie znaleziona.")
                return
            
            # Wyłącz strategię
            success = await strategies_table.disable_strategy(strategy_id)
            
            if success:
                success_msg = self.create_success_message(
                    f"Wyłączenie strategii {strategy['name']}",
                    f"✅ Strategia została pomyślnie wyłączona.\n🆔 ID: {strategy_id}\n🔴 Status: Nieaktywna"
                )
                
                buttons = [
                    [Button.inline("📊 Szczegóły", f"strat:details:{strategy_id}".encode())],
                    [Button.inline("📊 Lista strategii", b"strat:page:1")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "strategy_disabled", {
                    "strategy_id": strategy_id, 
                    "strategy_name": strategy['name']
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się wyłączyć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_confirm_disable")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:confirm_delete:")
    async def strategy_confirm_delete_callback(self, event):
        """Wykonuje usunięcie strategii po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.edit("❌ **Błąd**\n\nStrategia nie znaleziona.")
                return
            
            strategy_name = strategy['name']
            
            # Usuń strategię
            success = await strategies_table.delete(strategy_id)
            
            if success:
                success_msg = self.create_success_message(
                    f"Usunięcie strategii {strategy_name}",
                    f"✅ Strategia została trwale usunięta z bazy danych.\n🆔 ID: {strategy_id}"
                )
                
                buttons = [
                    [Button.inline("📊 Lista strategii", b"strat:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "strategy_deleted", {
                    "strategy_id": strategy_id, 
                    "strategy_name": strategy_name
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się usunąć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_confirm_delete")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - DETAILS AND OTHER ACTIONS
    # ===================
    
    @RD.cb(b"strat:details:")
    async def strategy_details_callback(self, event):
        """Pokazuje szczegółowe informacje o strategii inwestycyjnej."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            # Formatuj szczegółowe informacje
            info_text = self.format_strategy_info(strategy)
            
            # Przyciski dla admina
            admin_buttons = []
            if await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
                if strategy.get('enabled'):
                    admin_buttons.append(Button.inline("🔴 Wyłącz", f"strat:disable:{strategy_id}".encode()))
                else:
                    admin_buttons.append(Button.inline("🟢 Włącz", f"strat:enable:{strategy_id}".encode()))
                
                admin_buttons.extend([
                    Button.inline("✏️ Edytuj nazwę", f"strat:edit:{strategy_id}:name".encode()),
                    Button.inline("📝 Edytuj opis", f"strat:edit:{strategy_id}:description".encode()),
                    Button.inline("🗑️ Usuń", f"strat:delete:{strategy_id}".encode())
                ])
            
            # Przyciski
            buttons = []
            if admin_buttons:
                # Podziel admin buttons na wiersze po 2
                for i in range(0, len(admin_buttons), 2):
                    buttons.append(admin_buttons[i:i+2])
            
            buttons.extend([
                [Button.inline("📊 Lista strategii", b"strat:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "strategy_details_view", {
                "strategy_id": strategy_id, 
                "strategy_name": strategy['name']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_details")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:search_prompt")
    async def strategy_search_prompt_callback(self, event):
        """Pokazuje instrukcje wyszukiwania strategii."""
        search_help = (
            "🔍 **Wyszukiwanie Strategii**\n\n"
            "**Aby wyszukać strategię, wyślij:**\n"
            "`/investment_strategy_search NAZWA`\n\n"
            "**Przykłady:**\n"
            "• `/investment_strategy_search hodl` - znajdzie strategie HODL\n"
            "• `/investment_strategy_search dca` - znajdzie strategie DCA\n"
            "• `/investment_strategy_search long` - znajdzie długoterminowe\n\n"
            "**Wskazówki:**\n"
            "• Możesz użyć części nazwy\n"
            "• Wyszukiwanie nie rozróżnia wielkości liter\n"
            "• Jeśli znajdzie wiele wyników, pokaże listę do wyboru"
        )
        
        buttons = [
            [Button.inline("📊 Lista wszystkich", b"strat:page:1")],
            [Button.inline("🏠 Menu główne", b"nav:home")]
        ]
        
        await event.edit(search_help, buttons=buttons)
    
    # ===================
    # UTILITY METHODS
    # ===================
    
    def format_strategy_info(self, strategy: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o strategii inwestycyjnej.
        
        Args:
            strategy: Słownik z danymi strategii
            
        Returns:
            str: Sformatowane informacje o strategii
        """
        status_emoji = "✅" if strategy.get('enabled') else "❌"
        status_text = "Aktywna" if strategy.get('enabled') else "Nieaktywna"
        
        response = f"📊 **Strategia: {strategy['name']}**\n\n"
        response += f"📝 **Opis:**\n{strategy['description']}\n\n"
        response += f"{status_emoji} **Status:** {status_text}\n"
        response += f"🆔 **Database ID:** `{strategy['id']}`\n"
        
        if 'created_at' in strategy:
            response += f"📅 **Utworzona:** {self._format_datetime(strategy.get('created_at'))}\n"
        
        return response
    
    def _get_current_timestamp(self) -> int:
        """Helper method do pobierania aktualnego timestamp."""
        from datetime import datetime
        return int(datetime.now().timestamp())
    
    # ===================
    # MESSAGE HANDLERS - WIZARD INPUT PROCESSING
    # ===================
    
    @RD.msg(r".*")
    async def process_wizard_input(self, event):
        """Przetwarza input użytkownika w trakcie kreatora strategii."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.strategy_wizards:
            return
        
        wizard_state = self.strategy_wizards[user.id]
        
        if wizard_state['step'] == 'investment_waiting_input':
            await self._process_investment_strategy_input(event, user, wizard_state)
        elif wizard_state['step'] == 'buy_strategy_waiting_input':
            await self._process_buy_strategy_input(event, user, wizard_state)
        elif wizard_state['step'] == 'sell_strategy_waiting_input':
            await self._process_sell_strategy_input(event, user, wizard_state)
        elif wizard_state['step'].startswith('investment_edit_'):
            await self._process_investment_strategy_edit_input(event, user, wizard_state)
        elif wizard_state['step'].startswith('buy_strategy_edit_'):
            await self._process_buy_strategy_edit_input(event, user, wizard_state)
        elif wizard_state['step'].startswith('sell_strategy_edit_'):
            await self._process_sell_strategy_edit_input(event, user, wizard_state)
    
    async def _process_investment_strategy_input(self, event, user, wizard_state):
        """Przetwarza input dla strategii inwestycyjnej."""
        try:
            message_text = event.raw_text.strip()
            lines = message_text.split('\n')
            
            if len(lines) < 2:
                await event.respond(
                    "❌ **Nieprawidłowy format**\n\n"
                    "Wyślij strategię w formacie:\n"
                    "**Nazwa strategii**\n"
                    "**Opis strategii**\n\n"
                    "Każda część w osobnej linii.",
                    buttons=[
                        [Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")]
                    ]
                )
                return
            
            strategy_name = lines[0].strip()
            strategy_description = '\n'.join(lines[1:]).strip()
            
            # Walidacja
            if not strategy_name or len(strategy_name) < 3:
                await event.respond("❌ **Nazwa strategii musi mieć co najmniej 3 znaki.**")
                return
            
            if not strategy_description or len(strategy_description) < 10:
                await event.respond("❌ **Opis strategii musi mieć co najmniej 10 znaków.**")
                return
            
            # Sprawdź czy strategia o takiej nazwie już istnieje
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            existing_strategy = await strategies_table.get_by_name(strategy_name)
            
            if existing_strategy:
                await event.respond(
                    f"❌ **Strategia o nazwie '{strategy_name}' już istnieje.**\n\n"
                    "Wybierz inną nazwę.",
                    buttons=[
                        [Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")]
                    ]
                )
                return
            
            # Utwórz strategię
            strategy_id = await strategies_table.create(
                name=strategy_name,
                description=strategy_description,
                enabled=True
            )
            
            if strategy_id:
                success_msg = self.create_success_message(
                    f"Utworzenie strategii '{strategy_name}'",
                    f"✅ Strategia została pomyślnie utworzona.\n"
                    f"🆔 ID: {strategy_id}\n"
                    f"⚡ Status: Aktywna\n\n"
                    f"📝 **Opis:** {strategy_description[:100]}{'...' if len(strategy_description) > 100 else ''}"
                )
                
                buttons = [
                    [Button.inline("📊 Zobacz szczegóły", f"strat:details:{strategy_id}".encode())],
                    [Button.inline("📊 Lista strategii", b"strat:page:1")],
                    [Button.inline("➕ Utwórz kolejną", b"strat:create_wizard:start")]
                ]
                
                await event.respond(success_msg, buttons=buttons)
                
                # Usuń wizard state
                del self.strategy_wizards[user.id]
                
                await self.log_action(user.id, "investment_strategy_created", {
                    "strategy_id": strategy_id,
                    "strategy_name": strategy_name
                })
            else:
                await event.respond("❌ **Błąd**\n\nNie udało się utworzyć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "investment_strategy_create")
            await event.respond(error_msg)
    
    async def _process_buy_strategy_input(self, event, user, wizard_state):
        """Przetwarza input dla strategii kupna."""
        try:
            message_text = event.raw_text.strip().upper()
            wallet = wizard_state['data']['wallet']
            
            # Parse input: "MARKET 50%" lub "LIMIT 100"
            parts = message_text.split()
            if len(parts) != 2:
                await event.respond(
                    "❌ **Nieprawidłowy format**\n\n"
                    "Wyślij strategię w formacie: `TYP KWOTA`\n"
                    "Przykład: `MARKET 50%` lub `LIMIT 100`"
                )
                return
            
            strategy_type = parts[0]
            amount_str = parts[1]
            
            # Walidacja typu
            if strategy_type not in ["MARKET", "LIMIT"]:
                await event.respond(
                    "❌ **Nieprawidłowy typ zlecenia**\n\n"
                    "Dostępne typy: MARKET, LIMIT"
                )
                return
            
            # Parse amount
            is_percent = amount_str.endswith('%')
            if is_percent:
                amount_value = float(amount_str[:-1])
                if amount_value <= 0 or amount_value > 100:
                    await event.respond("❌ **Procent musi być między 1-100%**")
                    return
            else:
                try:
                    amount_value = float(amount_str)
                    if amount_value <= 0:
                        await event.respond("❌ **Kwota musi być większa niż 0**")
                        return
                except ValueError:
                    await event.respond("❌ **Nieprawidłowa kwota**")
                    return
            
            # Utwórz strategię
            await self.init_database()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            strategy_id = await buy_strategies_table.create(
                exchange_account_state_id=wizard_state['data']['wallet_id'],
                is_percent=is_percent,
                type=strategy_type,
                movement_amount=amount_value
            )
            
            if strategy_id:
                exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
                amount_display = f"{amount_value}%" if is_percent else f"{amount_value} {wallet['currency']}"
                
                success_msg = self.create_success_message(
                    f"Utworzenie strategii kupna",
                    f"✅ Strategia kupna została utworzona.\n"
                    f"🏦 Giełda: {exchange_name}\n"
                    f"💎 Portfel: {wallet['currency']} {wallet['type']}\n"
                    f"⚡ Typ: {strategy_type}\n"
                    f"💰 Kwota: {amount_display}"
                )
                
                buttons = [
                    [Button.inline("📈 Zobacz szczegóły", f"buy_strat:details:{strategy_id}".encode())],
                    [Button.inline("📈 Lista strategii kupna", b"buy_strat:page:1")],
                    [Button.inline("➕ Utwórz kolejną", b"strat:create_wizard:buy")]
                ]
                
                await event.respond(success_msg, buttons=buttons)
                
                # Usuń wizard state
                del self.strategy_wizards[user.id]
                
                await self.log_action(user.id, "buy_strategy_created", {
                    "strategy_id": strategy_id,
                    "wallet_id": wizard_state['data']['wallet_id'],
                    "type": strategy_type,
                    "amount": amount_value,
                    "is_percent": is_percent
                })
            else:
                await event.respond("❌ **Błąd**\n\nNie udało się utworzyć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_create")
            await event.respond(error_msg)
    
    async def _process_sell_strategy_input(self, event, user, wizard_state):
        """Przetwarza input dla strategii sprzedaży."""
        try:
            message_text = event.raw_text.strip().upper()
            wallet = wizard_state['data']['wallet']
            
            # Parse input: "MARKET 75%" lub "LIMIT 0.5"
            parts = message_text.split()
            if len(parts) != 2:
                await event.respond(
                    "❌ **Nieprawidłowy format**\n\n"
                    "Wyślij strategię w formacie: `TYP KWOTA`\n"
                    "Przykład: `MARKET 75%` lub `LIMIT 0.5`"
                )
                return
            
            strategy_type = parts[0]
            amount_str = parts[1]
            
            # Walidacja typu
            if strategy_type not in ["MARKET", "LIMIT"]:
                await event.respond(
                    "❌ **Nieprawidłowy typ zlecenia**\n\n"
                    "Dostępne typy: MARKET, LIMIT"
                )
                return
            
            # Parse amount
            is_percent = amount_str.endswith('%')
            if is_percent:
                amount_value = float(amount_str[:-1])
                if amount_value <= 0 or amount_value > 100:
                    await event.respond("❌ **Procent musi być między 1-100%**")
                    return
            else:
                try:
                    amount_value = float(amount_str)
                    if amount_value <= 0:
                        await event.respond("❌ **Kwota musi być większa niż 0**")
                        return
                except ValueError:
                    await event.respond("❌ **Nieprawidłowa kwota**")
                    return
            
            # Utwórz strategię
            await self.init_database()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            strategy_id = await sell_strategies_table.create(
                exchange_account_state_id=wizard_state['data']['wallet_id'],
                is_percent=is_percent,
                type=strategy_type,
                movement_amount=amount_value
            )
            
            if strategy_id:
                exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
                amount_display = f"{amount_value}%" if is_percent else f"{amount_value} {wallet['currency']}"
                
                success_msg = self.create_success_message(
                    f"Utworzenie strategii sprzedaży",
                    f"✅ Strategia sprzedaży została utworzona.\n"
                    f"🏦 Giełda: {exchange_name}\n"
                    f"💎 Portfel: {wallet['currency']} {wallet['type']}\n"
                    f"⚡ Typ: {strategy_type}\n"
                    f"💰 Kwota: {amount_display}"
                )
                
                buttons = [
                    [Button.inline("📉 Zobacz szczegóły", f"sell_strat:details:{strategy_id}".encode())],
                    [Button.inline("📉 Lista strategii sprzedaży", b"sell_strat:page:1")],
                    [Button.inline("➕ Utwórz kolejną", b"strat:create_wizard:sell")]
                ]
                
                await event.respond(success_msg, buttons=buttons)
                
                # Usuń wizard state
                del self.strategy_wizards[user.id]
                
                await self.log_action(user.id, "sell_strategy_created", {
                    "strategy_id": strategy_id,
                    "wallet_id": wizard_state['data']['wallet_id'],
                    "type": strategy_type,
                    "amount": amount_value,
                    "is_percent": is_percent
                })
            else:
                await event.respond("❌ **Błąd**\n\nNie udało się utworzyć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_create")
            await event.respond(error_msg)
    
    async def _process_investment_strategy_edit_input(self, event, user, wizard_state):
        """Przetwarza input dla edycji strategii inwestycyjnej."""
        try:
            message_text = event.raw_text.strip()
            strategy_id = wizard_state['data']['strategy_id']
            field = wizard_state['data']['field']
            strategy = wizard_state['data']['strategy']
            
            if field == 'name':
                new_name = message_text
                
                # Walidacja
                if len(new_name) < 3:
                    await event.respond("❌ **Nazwa musi mieć co najmniej 3 znaki.**")
                    return
                
                # Sprawdź unikalność (jeśli nazwa się zmieniła)
                if new_name.lower() != strategy['name'].lower():
                    await self.init_database()
                    strategies_table = self.db.get_factory().get_investment_strategies_table()
                    existing_strategy = await strategies_table.get_by_name(new_name)
                    
                    if existing_strategy:
                        await event.respond(
                            f"❌ **Strategia o nazwie '{new_name}' już istnieje.**\n\n"
                            "Wybierz inną nazwę."
                        )
                        return
                
                # Aktualizuj nazwę
                success = await strategies_table.update(strategy_id, name=new_name)
                
            elif field == 'description':
                new_description = message_text
                
                # Walidacja
                if len(new_description) < 10:
                    await event.respond("❌ **Opis musi mieć co najmniej 10 znaków.**")
                    return
                
                # Aktualizuj opis
                await self.init_database()
                strategies_table = self.db.get_factory().get_investment_strategies_table()
                success = await strategies_table.update(strategy_id, description=new_description)
            
            else:
                await event.respond("❌ **Nieprawidłowe pole do edycji.**")
                return
            
            if success:
                field_name = "nazwa" if field == 'name' else "opis"
                success_msg = self.create_success_message(
                    f"Edycja {field_name} strategii",
                    f"✅ {field_name.capitalize()} strategii została zaktualizowana.\n"
                    f"📊 Strategia: {new_name if field == 'name' else strategy['name']}\n"
                    f"🆔 ID: {strategy_id}"
                )
                
                buttons = [
                    [Button.inline("📊 Zobacz szczegóły", f"strat:details:{strategy_id}".encode())],
                    [Button.inline("📊 Lista strategii", b"strat:page:1")]
                ]
                
                await event.respond(success_msg, buttons=buttons)
                
                # Usuń wizard state
                del self.strategy_wizards[user.id]
                
                await self.log_action(user.id, f"investment_strategy_{field}_updated", {
                    "strategy_id": strategy_id,
                    "field": field,
                    "new_value": new_name if field == 'name' else new_description
                })
            else:
                await event.respond("❌ **Błąd**\n\nNie udało się zaktualizować strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, f"investment_strategy_edit_{field}")
            await event.respond(error_msg)
    
    async def _process_buy_strategy_edit_input(self, event, user, wizard_state):
        """Przetwarza input dla edycji strategii kupna."""
        try:
            message_text = event.raw_text.strip()
            strategy_id = wizard_state['data']['strategy_id']
            field = wizard_state['data']['field']
            strategy = wizard_state['data']['strategy']
            
            if field == 'amount':
                amount_str = message_text.upper()
                
                # Parse amount
                is_percent = amount_str.endswith('%')
                if is_percent:
                    try:
                        amount_value = float(amount_str[:-1])
                        if amount_value <= 0 or amount_value > 100:
                            await event.respond("❌ **Procent musi być między 1-100%**")
                            return
                    except ValueError:
                        await event.respond("❌ **Nieprawidłowy procent**")
                        return
                else:
                    try:
                        amount_value = float(amount_str)
                        if amount_value <= 0:
                            await event.respond("❌ **Kwota musi być większa niż 0**")
                            return
                    except ValueError:
                        await event.respond("❌ **Nieprawidłowa kwota**")
                        return
                
                # Aktualizuj strategię
                await self.init_database()
                buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
                
                success = await buy_strategies_table.update(
                    strategy_id,
                    is_percent=is_percent,
                    movement_amount=amount_value
                )
                
                if success:
                    exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
                    old_amount_type = "%" if strategy['is_percent'] else strategy['currency']
                    new_amount_display = f"{amount_value}%" if is_percent else f"{amount_value} {strategy['currency']}"
                    
                    success_msg = self.create_success_message(
                        f"Edycja kwoty strategii kupna",
                        f"✅ Kwota strategii została zaktualizowana.\n"
                        f"🏦 Giełda: {exchange_name}\n"
                        f"💎 Portfel: {strategy['currency']} {strategy['account_type']}\n"
                        f"💰 Nowa kwota: {new_amount_display}\n"
                        f"🔄 Poprzednia: {strategy['movement_amount']} {old_amount_type}"
                    )
                    
                    buttons = [
                        [Button.inline("📈 Zobacz szczegóły", f"buy_strat:details:{strategy_id}".encode())],
                        [Button.inline("📈 Lista strategii kupna", b"buy_strat:page:1")]
                    ]
                    
                    await event.respond(success_msg, buttons=buttons)
                    
                    # Usuń wizard state
                    del self.strategy_wizards[user.id]
                    
                    await self.log_action(user.id, "buy_strategy_amount_updated", {
                        "strategy_id": strategy_id,
                        "old_amount": strategy['movement_amount'],
                        "old_is_percent": strategy['is_percent'],
                        "new_amount": amount_value,
                        "new_is_percent": is_percent
                    })
                else:
                    await event.respond("❌ **Błąd**\n\nNie udało się zaktualizować strategii. Spróbuj ponownie.")
                    
            else:
                await event.respond("❌ **Nieprawidłowe pole do edycji.**")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, f"buy_strategy_edit_{field}")
            await event.respond(error_msg)
    
    async def _process_sell_strategy_edit_input(self, event, user, wizard_state):
        """Przetwarza input dla edycji strategii sprzedaży."""
        try:
            message_text = event.raw_text.strip()
            strategy_id = wizard_state['data']['strategy_id']
            field = wizard_state['data']['field']
            strategy = wizard_state['data']['strategy']
            
            if field == 'amount':
                amount_str = message_text.upper()
                
                # Parse amount
                is_percent = amount_str.endswith('%')
                if is_percent:
                    try:
                        amount_value = float(amount_str[:-1])
                        if amount_value <= 0 or amount_value > 100:
                            await event.respond("❌ **Procent musi być między 1-100%**")
                            return
                    except ValueError:
                        await event.respond("❌ **Nieprawidłowy procent**")
                        return
                else:
                    try:
                        amount_value = float(amount_str)
                        if amount_value <= 0:
                            await event.respond("❌ **Kwota musi być większa niż 0**")
                            return
                    except ValueError:
                        await event.respond("❌ **Nieprawidłowa kwota**")
                        return
                
                # Aktualizuj strategię
                await self.init_database()
                sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
                
                success = await sell_strategies_table.update(
                    strategy_id,
                    is_percent=is_percent,
                    movement_amount=amount_value
                )
                
                if success:
                    exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
                    old_amount_type = "%" if strategy['is_percent'] else strategy['currency']
                    new_amount_display = f"{amount_value}%" if is_percent else f"{amount_value} {strategy['currency']}"
                    
                    success_msg = self.create_success_message(
                        f"Edycja kwoty strategii sprzedaży",
                        f"✅ Kwota strategii została zaktualizowana.\n"
                        f"🏦 Giełda: {exchange_name}\n"
                        f"💎 Portfel: {strategy['currency']} {strategy['account_type']}\n"
                        f"💰 Nowa kwota: {new_amount_display}\n"
                        f"🔄 Poprzednia: {strategy['movement_amount']} {old_amount_type}"
                    )
                    
                    buttons = [
                        [Button.inline("📉 Zobacz szczegóły", f"sell_strat:details:{strategy_id}".encode())],
                        [Button.inline("📉 Lista strategii sprzedaży", b"sell_strat:page:1")]
                    ]
                    
                    await event.respond(success_msg, buttons=buttons)
                    
                    # Usuń wizard state
                    del self.strategy_wizards[user.id]
                    
                    await self.log_action(user.id, "sell_strategy_amount_updated", {
                        "strategy_id": strategy_id,
                        "old_amount": strategy['movement_amount'],
                        "old_is_percent": strategy['is_percent'],
                        "new_amount": amount_value,
                        "new_is_percent": is_percent
                    })
                else:
                    await event.respond("❌ **Błąd**\n\nNie udało się zaktualizować strategii. Spróbuj ponownie.")
                    
            else:
                await event.respond("❌ **Nieprawidłowe pole do edycji.**")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, f"sell_strategy_edit_{field}")
            await event.respond(error_msg)
    
    # ===================
    # CALLBACK QUERIES - BUY/SELL STRATEGY ACTIONS
    # ===================
    
    @RD.cb(b"buy_strat:create:")
    async def buy_strategy_create_callback(self, event):
        """Tworzy strategię kupna dla wybranego portfela."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do tworzenia strategii!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            # Sprawdź czy strategia już istnieje
            existing_strategy = await buy_strategies_table.get_by_exchange_account_state_id(wallet_id)
            if existing_strategy:
                await event.edit(
                    f"ℹ️ **Strategia już istnieje**\n\n"
                    f"Portfel już ma przypisaną strategię kupna.\n"
                    f"Strategia: {existing_strategy['type']} {existing_strategy['movement_amount']} "
                    f"{'%' if existing_strategy['is_percent'] else existing_strategy['currency']}",
                    buttons=[
                        [Button.inline("✏️ Edytuj", f"buy_strat:edit:{existing_strategy['id']}:amount".encode())],
                        [Button.inline("🔙 Wstecz", b"strat:create_wizard:buy")]
                    ]
                )
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            wizard_text = (
                f"📈 **Nowa Strategia Kupna**\n\n"
                f"🏦 **Portfel:** {exchange_name}\n"
                f"💎 **Waluta:** {wallet_desc}\n"
                f"💰 **Saldo:** {TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])}\n\n"
                f"**Wyślij strategię w formacie:**\n"
                f"`TYP KWOTA [%]`\n\n"
                f"**Przykłady:**\n"
                f"• `MARKET 100` - zlecenie rynkowe, 100 {wallet['currency']}\n"
                f"• `LIMIT 50%` - zlecenie z limitem, 50% salda\n"
                f"• `MARKET 25%` - zlecenie rynkowe, 25% salda\n\n"
                f"📝 **Wyślij swoją strategię jako następną wiadomość.**"
            )
            
            # Zapisz stan wizarda
            self.strategy_wizards[user.id] = {
                "step": "buy_strategy_waiting_input",
                "data": {"wallet_id": wallet_id, "wallet": wallet},
                "created_at": self._get_current_timestamp()
            }
            
            buttons = [
                [Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")]
            ]
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_create")
            await event.edit(error_msg)
    
    @RD.cb(b"sell_strat:create:")
    async def sell_strategy_create_callback(self, event):
        """Tworzy strategię sprzedaży dla wybranego portfela."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do tworzenia strategii!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            # Sprawdź czy strategia już istnieje
            existing_strategy = await sell_strategies_table.get_by_exchange_account_state_id(wallet_id)
            if existing_strategy:
                await event.edit(
                    f"ℹ️ **Strategia już istnieje**\n\n"
                    f"Portfel już ma przypisaną strategię sprzedaży.\n"
                    f"Strategia: {existing_strategy['type']} {existing_strategy['movement_amount']} "
                    f"{'%' if existing_strategy['is_percent'] else existing_strategy['currency']}",
                    buttons=[
                        [Button.inline("✏️ Edytuj", f"sell_strat:edit:{existing_strategy['id']}:amount".encode())],
                        [Button.inline("🔙 Wstecz", b"strat:create_wizard:sell")]
                    ]
                )
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            wizard_text = (
                f"📉 **Nowa Strategia Sprzedaży**\n\n"
                f"🏦 **Portfel:** {exchange_name}\n"
                f"💎 **Waluta:** {wallet_desc}\n"
                f"💰 **Saldo:** {TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])}\n\n"
                f"**Wyślij strategię w formacie:**\n"
                f"`TYP KWOTA [%]`\n\n"
                f"**Przykłady:**\n"
                f"• `MARKET 0.5` - zlecenie rynkowe, 0.5 {wallet['currency']}\n"
                f"• `LIMIT 75%` - zlecenie z limitem, 75% salda\n"
                f"• `MARKET 100%` - zlecenie rynkowe, całe saldo\n\n"
                f"📝 **Wyślij swoją strategię jako następną wiadomość.**"
            )
            
            # Zapisz stan wizarda
            self.strategy_wizards[user.id] = {
                "step": "sell_strategy_waiting_input",
                "data": {"wallet_id": wallet_id, "wallet": wallet},
                "created_at": self._get_current_timestamp()
            }
            
            buttons = [
                [Button.inline("❌ Anuluj", b"strat:create_wizard:cancel")]
            ]
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_create")
            await event.edit(error_msg)
    
    @RD.cb(b"buy_strat:details:")
    async def buy_strategy_details_callback(self, event):
        """Pokazuje szczegóły strategii kupna."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Pobierz strategię
            strategy = await buy_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            # Formatuj szczegółowe informacje
            info_text = self.format_buy_strategy_info(strategy)
            
            # Oblicz przybliżoną kwotę do zakupu
            calculated_amount = await buy_strategies_table.calculate_buy_amount(strategy_id)
            if calculated_amount:
                info_text += f"\n💰 **Obliczona kwota:** {TelegramUIUtils.format_currency(calculated_amount, strategy['currency'])}"
            
            # Przyciski dla admina/trader
            action_buttons = []
            if await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
                action_buttons.extend([
                    Button.inline("✏️ Edytuj kwotę", f"buy_strat:edit:{strategy_id}:amount".encode()),
                    Button.inline("🔄 Edytuj typ", f"buy_strat:edit:{strategy_id}:type".encode())
                ])
            
            if await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
                action_buttons.append(Button.inline("🗑️ Usuń", f"buy_strat:delete:{strategy_id}".encode()))
            
            # Przyciski
            buttons = []
            if action_buttons:
                # Podziel action buttons na wiersze po 2
                for i in range(0, len(action_buttons), 2):
                    buttons.append(action_buttons[i:i+2])
            
            buttons.extend([
                [Button.inline("💰 Portfel", f"wallet:details:{strategy['exchange_account_state_id']}".encode())],
                [Button.inline("📈 Lista strategii kupna", b"buy_strat:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "buy_strategy_details_view", {
                "strategy_id": strategy_id,
                "exchange_name": strategy.get('exchange_display_name') or strategy['exchange_name'],
                "currency": strategy['currency']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_details")
            await event.edit(error_msg)
    
    @RD.cb(b"sell_strat:details:")
    async def sell_strategy_details_callback(self, event):
        """Pokazuje szczegóły strategii sprzedaży."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Pobierz strategię
            strategy = await sell_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            # Formatuj szczegółowe informacje
            info_text = self.format_sell_strategy_info(strategy)
            
            # Oblicz przybliżoną kwotę do sprzedaży
            calculated_amount = await sell_strategies_table.calculate_sell_amount(strategy_id)
            if calculated_amount:
                info_text += f"\n💰 **Obliczona kwota:** {TelegramUIUtils.format_currency(calculated_amount, strategy['currency'])}"
            
            # Przyciski dla admina/trader
            action_buttons = []
            if await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
                action_buttons.extend([
                    Button.inline("✏️ Edytuj kwotę", f"sell_strat:edit:{strategy_id}:amount".encode()),
                    Button.inline("🔄 Edytuj typ", f"sell_strat:edit:{strategy_id}:type".encode())
                ])
            
            if await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
                action_buttons.append(Button.inline("🗑️ Usuń", f"sell_strat:delete:{strategy_id}".encode()))
            
            # Przyciski
            buttons = []
            if action_buttons:
                # Podziel action buttons na wiersze po 2
                for i in range(0, len(action_buttons), 2):
                    buttons.append(action_buttons[i:i+2])
            
            buttons.extend([
                [Button.inline("💰 Portfel", f"wallet:details:{strategy['exchange_account_state_id']}".encode())],
                [Button.inline("📉 Lista strategii sprzedaży", b"sell_strat:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "sell_strategy_details_view", {
                "strategy_id": strategy_id,
                "exchange_name": strategy.get('exchange_display_name') or strategy['exchange_name'],
                "currency": strategy['currency']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_details")
            await event.edit(error_msg)
    
    def format_buy_strategy_info(self, strategy: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o strategii kupna.
        
        Args:
            strategy: Słownik z danymi strategii kupna
            
        Returns:
            str: Sformatowane informacje o strategii
        """
        exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
        type_emoji = "⚡" if strategy['type'] == "MARKET" else "📊"
        amount_type = "%" if strategy['is_percent'] else strategy['currency']
        
        response = f"📈 **Strategia Kupna: {strategy['currency']}**\n\n"
        response += f"🏦 **Giełda:** {exchange_name}\n"
        response += f"💎 **Portfel:** {strategy['currency']} {strategy['account_type']}\n"
        response += f"{type_emoji} **Typ zlecenia:** {strategy['type']}\n"
        response += f"💰 **Kwota:** {strategy['movement_amount']} {amount_type}\n"
        response += f"📊 **Saldo portfela:** {TelegramUIUtils.format_currency(float(strategy['account_amount']), strategy['currency'])}\n"
        response += f"🆔 **Database ID:** `{strategy['id']}`\n"
        
        if 'created_at' in strategy:
            response += f"📅 **Utworzona:** {self._format_datetime(strategy.get('created_at'))}\n"
        
        if 'updated_at' in strategy:
            response += f"🔄 **Ostatnia aktualizacja:** {self._format_datetime(strategy.get('updated_at'))}\n"
        
        return response
    
    def format_sell_strategy_info(self, strategy: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o strategii sprzedaży.
        
        Args:
            strategy: Słownik z danymi strategii sprzedaży
            
        Returns:
            str: Sformatowane informacje o strategii
        """
        exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
        type_emoji = "⚡" if strategy['type'] == "MARKET" else "📊"
        amount_type = "%" if strategy['is_percent'] else strategy['currency']
        
        response = f"📉 **Strategia Sprzedaży: {strategy['currency']}**\n\n"
        response += f"🏦 **Giełda:** {exchange_name}\n"
        response += f"💎 **Portfel:** {strategy['currency']} {strategy['account_type']}\n"
        response += f"{type_emoji} **Typ zlecenia:** {strategy['type']}\n"
        response += f"💰 **Kwota:** {strategy['movement_amount']} {amount_type}\n"
        response += f"📊 **Saldo portfela:** {TelegramUIUtils.format_currency(float(strategy['account_amount']), strategy['currency'])}\n"
        response += f"🆔 **Database ID:** `{strategy['id']}`\n"
        
        if 'created_at' in strategy:
            response += f"📅 **Utworzona:** {self._format_datetime(strategy.get('created_at'))}\n"
        
        if 'updated_at' in strategy:
            response += f"🔄 **Ostatnia aktualizacja:** {self._format_datetime(strategy.get('updated_at'))}\n"
        
        return response
    
    # ===================
    # CALLBACK QUERIES - EDIT STRATEGIES
    # ===================
    
    @RD.cb(b"strat:edit:")
    async def strategy_edit_callback(self, event):
        """Handler edycji strategii inwestycyjnej."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do edycji strategii!", alert=True)
            return
        
        try:
            # Parse callback data: strat:edit:ID:FIELD
            callback_data = event.data.decode()
            parts = callback_data.split(":")
            strategy_id = int(parts[2])
            field = parts[3]
            
            await self.init_database()
            strategies_table = self.db.get_factory().get_investment_strategies_table()
            
            # Pobierz strategię
            strategy = await strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            if field == "name":
                prompt_text = (
                    f"✏️ **Edycja nazwy strategii**\n\n"
                    f"📊 **Aktualna nazwa:** {strategy['name']}\n\n"
                    f"**Wyślij nową nazwę strategii:**\n"
                    f"• Nazwa musi mieć co najmniej 3 znaki\n"
                    f"• Nazwa musi być unikalna\n"
                    f"• Przykład: `HODL Plus Strategy`\n\n"
                    f"📝 **Wyślij nową nazwę jako następną wiadomość.**"
                )
            elif field == "description":
                prompt_text = (
                    f"✏️ **Edycja opisu strategii**\n\n"
                    f"📊 **Strategia:** {strategy['name']}\n"
                    f"📝 **Aktualny opis:**\n{strategy['description'][:200]}{'...' if len(strategy['description']) > 200 else ''}\n\n"
                    f"**Wyślij nowy opis strategii:**\n"
                    f"• Opis musi mieć co najmniej 10 znaków\n"
                    f"• Może zawierać wiele linii\n"
                    f"• Przykład: `Długoterminowa strategia...`\n\n"
                    f"📝 **Wyślij nowy opis jako następną wiadomość.**"
                )
            else:
                await event.answer("❌ Nieprawidłowe pole do edycji", alert=True)
                return
            
            # Zapisz stan edycji
            self.strategy_wizards[user.id] = {
                "step": f"investment_edit_{field}_waiting_input",
                "data": {
                    "strategy_id": strategy_id,
                    "field": field,
                    "strategy": strategy
                },
                "created_at": self._get_current_timestamp()
            }
            
            buttons = [
                [Button.inline("❌ Anuluj", b"strat:edit_cancel")]
            ]
            
            await event.edit(prompt_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "strategy_edit")
            await event.edit(error_msg)
    
    @RD.cb(b"buy_strat:edit:")
    async def buy_strategy_edit_callback(self, event):
        """Handler edycji strategii kupna."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do edycji strategii!", alert=True)
            return
        
        try:
            # Parse callback data: buy_strat:edit:ID:FIELD
            callback_data = event.data.decode()
            parts = callback_data.split(":")
            strategy_id = int(parts[2])
            field = parts[3]
            
            await self.init_database()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Pobierz strategię
            strategy = await buy_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
            amount_type = "%" if strategy['is_percent'] else strategy['currency']
            
            if field == "amount":
                prompt_text = (
                    f"✏️ **Edycja kwoty strategii kupna**\n\n"
                    f"🏦 **Giełda:** {exchange_name}\n"
                    f"💎 **Portfel:** {strategy['currency']} {strategy['account_type']}\n"
                    f"💰 **Aktualna kwota:** {strategy['movement_amount']} {amount_type}\n"
                    f"📊 **Saldo portfela:** {TelegramUIUtils.format_currency(float(strategy['account_amount']), strategy['currency'])}\n\n"
                    f"**Wyślij nową kwotę:**\n"
                    f"• Dla kwoty bezwzględnej: `100` (w {strategy['currency']})\n"
                    f"• Dla procentu: `50%` (procent salda)\n"
                    f"• Kwota musi być większa niż 0\n"
                    f"• Procent musi być między 1-100%\n\n"
                    f"📝 **Wyślij nową kwotę jako następną wiadomość.**"
                )
                
                # Zapisz stan edycji
                self.strategy_wizards[user.id] = {
                    "step": f"buy_strategy_edit_{field}_waiting_input",
                    "data": {
                        "strategy_id": strategy_id,
                        "field": field,
                        "strategy": strategy
                    },
                    "created_at": self._get_current_timestamp()
                }
                
                buttons = [
                    [Button.inline("❌ Anuluj", b"buy_strat:edit_cancel")]
                ]
                
                await event.edit(prompt_text, buttons=buttons)
                
            elif field == "type":
                current_type = strategy['type']
                new_type = "LIMIT" if current_type == "MARKET" else "MARKET"
                
                # Dla typu nie czekamy na input, od razu zmieniamy
                success = await buy_strategies_table.update(strategy_id, type=new_type)
                
                if success:
                    success_msg = self.create_success_message(
                        f"Zmiana typu strategii kupna",
                        f"✅ Typ zlecenia został zmieniony z {current_type} na {new_type}.\n"
                        f"🏦 Giełda: {exchange_name}\n"
                        f"💎 Portfel: {strategy['currency']} {strategy['account_type']}"
                    )
                    
                    buttons = [
                        [Button.inline("📈 Zobacz szczegóły", f"buy_strat:details:{strategy_id}".encode())],
                        [Button.inline("📈 Lista strategii kupna", b"buy_strat:page:1")]
                    ]
                    
                    await event.edit(success_msg, buttons=buttons)
                    await self.log_action(user.id, "buy_strategy_type_changed", {
                        "strategy_id": strategy_id,
                        "old_type": current_type,
                        "new_type": new_type
                    })
                else:
                    await event.edit("❌ **Błąd**\n\nNie udało się zmienić typu strategii. Spróbuj ponownie.")
            else:
                await event.answer("❌ Nieprawidłowe pole do edycji", alert=True)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_edit")
            await event.edit(error_msg)
    
    @RD.cb(b"sell_strat:edit:")
    async def sell_strategy_edit_callback(self, event):
        """Handler edycji strategii sprzedaży."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do edycji strategii!", alert=True)
            return
        
        try:
            # Parse callback data: sell_strat:edit:ID:FIELD
            callback_data = event.data.decode()
            parts = callback_data.split(":")
            strategy_id = int(parts[2])
            field = parts[3]
            
            await self.init_database()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Pobierz strategię
            strategy = await sell_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
            amount_type = "%" if strategy['is_percent'] else strategy['currency']
            
            if field == "amount":
                prompt_text = (
                    f"✏️ **Edycja kwoty strategii sprzedaży**\n\n"
                    f"🏦 **Giełda:** {exchange_name}\n"
                    f"💎 **Portfel:** {strategy['currency']} {strategy['account_type']}\n"
                    f"💰 **Aktualna kwota:** {strategy['movement_amount']} {amount_type}\n"
                    f"📊 **Saldo portfela:** {TelegramUIUtils.format_currency(float(strategy['account_amount']), strategy['currency'])}\n\n"
                    f"**Wyślij nową kwotę:**\n"
                    f"• Dla kwoty bezwzględnej: `0.5` (w {strategy['currency']})\n"
                    f"• Dla procentu: `75%` (procent salda)\n"
                    f"• Kwota musi być większa niż 0\n"
                    f"• Procent musi być między 1-100%\n\n"
                    f"📝 **Wyślij nową kwotę jako następną wiadomość.**"
                )
                
                # Zapisz stan edycji
                self.strategy_wizards[user.id] = {
                    "step": f"sell_strategy_edit_{field}_waiting_input",
                    "data": {
                        "strategy_id": strategy_id,
                        "field": field,
                        "strategy": strategy
                    },
                    "created_at": self._get_current_timestamp()
                }
                
                buttons = [
                    [Button.inline("❌ Anuluj", b"sell_strat:edit_cancel")]
                ]
                
                await event.edit(prompt_text, buttons=buttons)
                
            elif field == "type":
                current_type = strategy['type']
                new_type = "LIMIT" if current_type == "MARKET" else "MARKET"
                
                # Dla typu nie czekamy na input, od razu zmieniamy
                success = await sell_strategies_table.update(strategy_id, type=new_type)
                
                if success:
                    success_msg = self.create_success_message(
                        f"Zmiana typu strategii sprzedaży",
                        f"✅ Typ zlecenia został zmieniony z {current_type} na {new_type}.\n"
                        f"🏦 Giełda: {exchange_name}\n"
                        f"💎 Portfel: {strategy['currency']} {strategy['account_type']}"
                    )
                    
                    buttons = [
                        [Button.inline("📉 Zobacz szczegóły", f"sell_strat:details:{strategy_id}".encode())],
                        [Button.inline("📉 Lista strategii sprzedaży", b"sell_strat:page:1")]
                    ]
                    
                    await event.edit(success_msg, buttons=buttons)
                    await self.log_action(user.id, "sell_strategy_type_changed", {
                        "strategy_id": strategy_id,
                        "old_type": current_type,
                        "new_type": new_type
                    })
                else:
                    await event.edit("❌ **Błąd**\n\nNie udało się zmienić typu strategii. Spróbuj ponownie.")
            else:
                await event.answer("❌ Nieprawidłowe pole do edycji", alert=True)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_edit")
            await event.edit(error_msg)
    
    @RD.cb(b"strat:edit_cancel")
    async def strategy_edit_cancel_callback(self, event):
        """Anuluje edycję strategii inwestycyjnej."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if user.id in self.strategy_wizards:
            del self.strategy_wizards[user.id]
        
        await event.edit(
            "❌ **Edycja anulowana**\n\nEdycja strategii zostało anulowana.",
            buttons=[[Button.inline("📊 Lista strategii", b"strat:page:1")]]
        )
    
    @RD.cb(b"buy_strat:edit_cancel")
    async def buy_strategy_edit_cancel_callback(self, event):
        """Anuluje edycję strategii kupna."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if user.id in self.strategy_wizards:
            del self.strategy_wizards[user.id]
        
        await event.edit(
            "❌ **Edycja anulowana**\n\nEdycja strategii kupna zostało anulowana.",
            buttons=[[Button.inline("📈 Lista strategii kupna", b"buy_strat:page:1")]]
        )
    
    @RD.cb(b"sell_strat:edit_cancel")
    async def sell_strategy_edit_cancel_callback(self, event):
        """Anuluje edycję strategii sprzedaży."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if user.id in self.strategy_wizards:
            del self.strategy_wizards[user.id]
        
        await event.edit(
            "❌ **Edycja anulowana**\n\nEdycja strategii sprzedaży zostało anulowana.",
            buttons=[[Button.inline("📉 Lista strategii sprzedaży", b"sell_strat:page:1")]]
        )
    
    @RD.cb(b"buy_strat:delete:")
    async def buy_strategy_delete_callback(self, event):
        """Pokazuje potwierdzenie usunięcia strategii kupna."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Pobierz strategię
            strategy = await buy_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
            amount_type = "%" if strategy['is_percent'] else strategy['currency']
            
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Usunięcie strategii kupna",
                f"Giełda: {exchange_name} | Portfel: {strategy['currency']} {strategy['account_type']}",
                f"⚠️ UWAGA: Ta akcja jest nieodwracalna! Strategia {strategy['type']} {strategy['movement_amount']} {amount_type} zostanie trwale usunięta."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "buy_strat:confirm_delete",
                str(strategy_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_delete")
            await event.edit(error_msg)
    
    @RD.cb(b"sell_strat:delete:")
    async def sell_strategy_delete_callback(self, event):
        """Pokazuje potwierdzenie usunięcia strategii sprzedaży."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Pobierz strategię
            strategy = await sell_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.answer("❌ Strategia nie znaleziona", alert=True)
                return
            
            exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
            amount_type = "%" if strategy['is_percent'] else strategy['currency']
            
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Usunięcie strategii sprzedaży",
                f"Giełda: {exchange_name} | Portfel: {strategy['currency']} {strategy['account_type']}",
                f"⚠️ UWAGA: Ta akcja jest nieodwracalna! Strategia {strategy['type']} {strategy['movement_amount']} {amount_type} zostanie trwale usunięta."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "sell_strat:confirm_delete",
                str(strategy_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_delete")
            await event.edit(error_msg)
    
    @RD.cb(b"buy_strat:confirm_delete:")
    async def buy_strategy_confirm_delete_callback(self, event):
        """Wykonuje usunięcie strategii kupna po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            
            # Pobierz strategię przed usunięciem
            strategy = await buy_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.edit("❌ **Błąd**\n\nStrategia nie znaleziona.")
                return
            
            exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
            strategy_desc = f"{strategy['type']} {strategy['movement_amount']}{'%' if strategy['is_percent'] else strategy['currency']}"
            
            # Usuń strategię
            success = await buy_strategies_table.delete(strategy_id)
            
            if success:
                success_msg = self.create_success_message(
                    f"Usunięcie strategii kupna",
                    f"✅ Strategia kupna została trwale usunięta.\n"
                    f"🏦 Giełda: {exchange_name}\n"
                    f"💎 Portfel: {strategy['currency']} {strategy['account_type']}\n"
                    f"⚡ Strategia: {strategy_desc}"
                )
                
                buttons = [
                    [Button.inline("📈 Lista strategii kupna", b"buy_strat:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "buy_strategy_deleted", {
                    "strategy_id": strategy_id,
                    "exchange_name": exchange_name,
                    "wallet_id": strategy['exchange_account_state_id']
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się usunąć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "buy_strategy_confirm_delete")
            await event.edit(error_msg)
    
    @RD.cb(b"sell_strat:confirm_delete:")
    async def sell_strategy_confirm_delete_callback(self, event):
        """Wykonuje usunięcie strategii sprzedaży po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract strategy ID
            callback_data = event.data.decode()
            strategy_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            # Pobierz strategię przed usunięciem
            strategy = await sell_strategies_table.get_by_id(strategy_id)
            if not strategy:
                await event.edit("❌ **Błąd**\n\nStrategia nie znaleziona.")
                return
            
            exchange_name = strategy.get('exchange_display_name') or strategy['exchange_name']
            strategy_desc = f"{strategy['type']} {strategy['movement_amount']}{'%' if strategy['is_percent'] else strategy['currency']}"
            
            # Usuń strategię
            success = await sell_strategies_table.delete(strategy_id)
            
            if success:
                success_msg = self.create_success_message(
                    f"Usunięcie strategii sprzedaży",
                    f"✅ Strategia sprzedaży została trwale usunięta.\n"
                    f"🏦 Giełda: {exchange_name}\n"
                    f"💎 Portfel: {strategy['currency']} {strategy['account_type']}\n"
                    f"⚡ Strategia: {strategy_desc}"
                )
                
                buttons = [
                    [Button.inline("📉 Lista strategii sprzedaży", b"sell_strat:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "sell_strategy_deleted", {
                    "strategy_id": strategy_id,
                    "exchange_name": exchange_name,
                    "wallet_id": strategy['exchange_account_state_id']
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się usunąć strategii. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sell_strategy_confirm_delete")
            await event.edit(error_msg)
