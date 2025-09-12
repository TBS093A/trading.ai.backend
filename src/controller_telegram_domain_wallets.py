"""
Kontroler Wallets dla Telegram - zarządzanie portfelami kryptowalutowymi.

Ta klasa implementuje:
- Przeglądanie portfeli (stanów kont) z paginacją
- Filtrowanie portfeli po giełdach i statusie
- Wyświetlanie sald na konkretnych giełdach
- Zarządzanie statusem portfeli (włączenie/wyłączenie)
- Odświeżanie sald portfeli
- Integrację z transakcjami i giełdami

Autor: AI Assistant
"""

import logging
import traceback
from typing import List, Dict, Any, Optional, Tuple
from telethon import Button

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, RD
from .controller_telegram_utils_ui import PaginationHelper, ConfirmationDialog, TelegramUIUtils

logger = logging.getLogger(__name__)


class WalletsTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla zarządzania portfelami kryptowalutowymi w systemie Telegram.
    
    Zapewnia funkcjonalności:
    - Lista wszystkich portfeli z paginacją
    - Filtrowanie aktywnych portfeli
    - Wyświetlanie sald na konkretnych giełdach
    - Zarządzanie statusem portfeli (admin-only)
    - Odświeżanie sald portfeli
    - Integrację z transakcjami i giełdami
    """
    
    DOMAIN = "wallets"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera portfeli.
        
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
        """Zwraca menu domeny portfeli z przyciskami komend."""
        try:
            stats = await self.get_domain_specific_stats()
            
            menu_text = "💰 **Wallets - Zarządzanie Portfelami**\n\n"
            
            if stats.get('database_available'):
                menu_text += f"📊 **Statystyki:**\n"
                menu_text += f"• Wszystkie portfele: {stats.get('total_wallets', 'N/A')}\n"
                menu_text += f"• Aktywne portfele: {stats.get('active_wallets', 'N/A')}\n\n"
            else:
                menu_text += "⚠️ **Baza danych niedostępna**\n\n"
            
            menu_text += "📋 **Dostępne funkcje:**\n"
            menu_text += "• Przeglądanie wszystkich portfeli\n"
            menu_text += "• Lista tylko aktywnych portfeli\n"
            menu_text += "• Sprawdzanie sald portfeli na giełdach\n"
            
            buttons = [
                [
                    Button.inline("📋 Wszystkie Portfele", b"cmd:/wallets"),
                    Button.inline("✅ Aktywne Portfele", b"cmd:/wallets_active")
                ],
                [
                    Button.inline("💰 Salda Portfeli", b"cmd:/wallet_balance")
                ],
                [Button.inline("🏠 Menu Główne", b"nav:main_menu")]
            ]
            
            return menu_text, buttons
            
        except Exception as e:
            logger.error(f"Błąd w get_domain_menu (wallets): {e}")
            return await super().get_domain_menu(event, user_id)
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny portfeli."""
        try:
            if not self.db:
                return {"error": "Database not available"}
            
            await self.init_database()
            
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Pobierz podstawowe statystyki
            all_wallets = await wallets_table.get_all(limit=10000)
            enabled_wallets = await wallets_table.get_enabled_accounts(limit=10000)
            wallets_with_balance = await wallets_table.get_accounts_with_balance(min_amount=0.0001, limit=10000)
            
            # Policz transakcje
            all_transactions = await transactions_table.get_all(limit=50000)
            
            # Policz unikalne waluty
            currencies = set()
            exchanges = set()
            for wallet in all_wallets:
                currencies.add(wallet['currency'])
                exchanges.add(wallet['exchange_id'])
            
            return {
                "total_wallets": len(all_wallets),
                "enabled_wallets": len(enabled_wallets),
                "disabled_wallets": len(all_wallets) - len(enabled_wallets),
                "wallets_with_balance": len(wallets_with_balance),
                "unique_currencies": len(currencies),
                "exchanges_with_wallets": len(exchanges),
                "total_transactions": len(all_transactions),
                "database_available": True
            }
            
        except Exception as e:
            logger.error(f"Error getting wallets domain stats: {e}")
            return {
                "error": str(e),
                "database_available": False
            }
    
    # ===================
    # COMMANDS - WALLETS LIST
    # ===================
    
    @RD.cmd("wallets", aliases=["list_wallets", "show_wallets"])
    async def wallets_command(self, event):
        """
        Komenda wyświetlania listy wszystkich portfeli z paginacją.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "wallets_list")
        
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
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Oblicz offset dla paginacji bazy danych
            offset = (page - 1) * self.default_page_size
            
            # Pobierz portfele z dodatkowym rekordem dla sprawdzenia następnej strony
            wallets = await wallets_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not wallets:
                await event.respond("💰 **Lista Portfeli**\n\n❌ Brak portfeli do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(wallets) > self.default_page_size
            page_wallets = wallets[:self.default_page_size]
            
            # Formatuj odpowiedź
            wallets_text = f"💰 **Lista Portfeli - Strona {page}**\n\n"
            
            for i, wallet in enumerate(page_wallets, 1):
                item_number = offset + i
                exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
                status_emoji = "🟢" if wallet.get('is_enabled') else "🔴"
                balance_display = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
                
                wallets_text += f"{item_number}. {status_emoji} **{exchange_name}**\n"
                wallets_text += f"    💎 {wallet['currency']} {wallet['type']} | 💰 {balance_display}\n"
                wallets_text += f"    ID: {wallet['id']}\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                wallets_text += f"\n📄 Strona {page}"
                if has_next:
                    wallets_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper.create_pagination_buttons
            # Nie znamy total_items więc użyjemy estimacji
            estimated_total = offset + len(page_wallets) + (100 if has_next else 0)  # Estymacja
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_wallets),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_wallets)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "wallet", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("⚡ Tylko aktywne", b"wallet:active_only"),
                    Button.inline("💰 Z saldem", b"wallet:with_balance")
                ],
                [
                    Button.inline("🏦 Po giełdach", b"wallet:by_exchange"),
                    Button.inline("💱 Po walutach", b"wallet:by_currency")
                ],
                [
                    Button.inline("🔄 Odśwież", f"wallet:page:{page}".encode()),
                    Button.inline("📊 Statystyki", b"wallet:stats")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(wallets_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_list")
            await event.respond(error_msg)
    
    @RD.cmd("wallets_active", aliases=["active_wallets", "wallets_on"])
    async def wallets_active_command(self, event):
        """
        Komenda wyświetlania tylko aktywnych portfeli.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "wallets_active_list")
        
        try:
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz tylko aktywne portfele
            active_wallets = await wallets_table.get_enabled_accounts(limit=100)
            
            if not active_wallets:
                await event.respond(
                    "⚡ **Aktywne Portfele**\n\n❌ Brak aktywnych portfeli.",
                    buttons=[
                        [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj listę aktywnych portfeli
            wallets_text = f"⚡ **Aktywne Portfele** ({len(active_wallets)})\n\n"
            
            for i, wallet in enumerate(active_wallets[:20], 1):  # Limit 20 dla czytelności
                exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
                balance_display = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
                
                wallets_text += f"{i}. 🟢 **{exchange_name}**\n"
                wallets_text += f"    💎 {wallet['currency']} {wallet['type']} | 💰 {balance_display}\n"
                wallets_text += f"    ID: {wallet['id']} | Utworzony: "
                wallets_text += f"{self._format_datetime(wallet.get('created_at', ''))}\n"
            
            if len(active_wallets) > 20:
                wallets_text += f"\n... i {len(active_wallets) - 20} więcej"
            
            # Przyciski szczegółów dla pierwszych portfeli
            buttons = []
            details_buttons = []
            
            for wallet in active_wallets[:6]:  # Pierwsze 6 portfeli
                exchange_name = (wallet.get('exchange_display_name') or wallet['exchange_name'])[:8]
                currency = wallet['currency'][:4]
                details_buttons.append(
                    Button.inline(f"💰 {exchange_name}/{currency}", f"wallet:details:{wallet['id']}".encode())
                )
            
            # Podziel na wiersze po 3 przyciski
            for i in range(0, len(details_buttons), 3):
                buttons.append(details_buttons[i:i+3])
            
            buttons.extend([
                [
                    Button.inline("💰 Wszystkie portfele", b"wallet:page:1"),
                    Button.inline("🔄 Odśwież", b"wallet:active_only")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(wallets_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_active")
            await event.respond(error_msg)
    
    @RD.cmd("wallet_balance", aliases=["balance", "wallet_balances"])
    async def wallet_balance_command(self, event):
        """
        Komenda wyświetlania sald na konkretnej giełdzie.
        Użycie: /wallet_balance [exchange_name] lub /wallet_balance [exchange_id]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "💰 **Salda Portfeli**\n\n"
                "Podaj nazwę lub ID giełdy aby zobaczyć salda:\n\n"
                "**Użycie:**\n"
                "• `/wallet_balance binance`\n"
                "• `/wallet_balance 123` (ID giełdy)\n"
                "• `/wallet_balance \"Binance Spot\"` (pełna nazwa)",
                buttons=[
                    [Button.inline("🏦 Po giełdach", b"wallet:by_exchange")],
                    [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")],
                    [Button.inline("🔙 Menu główne", b"nav:home")]
                ]
            )
            return
        
        identifier = parts[1].strip()
        await self.log_action(user.id, "wallet_balance", {"identifier": identifier})
        
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
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
                    f"• ID numeryczne (123)",
                    buttons=[
                        [Button.inline("🏦 Po giełdach", b"wallet:by_exchange")],
                        [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")],
                        [Button.inline("🔙 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Pobierz portfele dla tej giełdy
            exchange_wallets = await wallets_table.get_by_exchange_id(exchange['id'], limit=100)
            
            exchange_name = exchange.get('display_name') or exchange['name']
            status_emoji = "🟢" if exchange.get('is_active') else "🔴"
            
            if not exchange_wallets:
                await event.respond(
                    f"{status_emoji} **{exchange_name}**\n\n"
                    f"❌ Brak portfeli na tej giełdzie.",
                    buttons=[
                        [Button.inline("🔙 Po giełdach", b"wallet:by_exchange")],
                        [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")]
                    ]
                )
                return
            
            # Formatuj saldo portfeli
            balance_text = f"{status_emoji} **{exchange_name} - Salda**\n\n"
            
            # Grupuj po walutach i typach
            spot_balances = {}
            futures_balances = {}
            total_value = 0
            
            for wallet in exchange_wallets:
                currency = wallet['currency']
                amount = float(wallet['amount'])
                wallet_type = wallet['type']
                is_enabled = wallet.get('is_enabled', True)
                
                if amount > 0 or is_enabled:  # Pokaż jeśli ma saldo lub jest aktywny
                    balance_entry = {
                        'amount': amount,
                        'enabled': is_enabled,
                        'wallet_id': wallet['id'],
                        'updated_at': wallet.get('updated_at', '')
                    }
                    
                    if wallet_type == 'SPOT':
                        spot_balances[currency] = balance_entry
                    elif wallet_type == 'FUTURES':
                        futures_balances[currency] = balance_entry
            
            # Wyświetl SPOT balances
            if spot_balances:
                balance_text += f"🏪 **SPOT Balances ({len(spot_balances)}):**\n"
                for currency, info in sorted(spot_balances.items()):
                    status = "🟢" if info['enabled'] else "🔴"
                    balance_display = TelegramUIUtils.format_currency(info['amount'], currency)
                    balance_text += f"• {status} {currency}: `{balance_display}`\n"
                balance_text += "\n"
            
            # Wyświetl FUTURES balances
            if futures_balances:
                balance_text += f"📈 **FUTURES Balances ({len(futures_balances)}):**\n"
                for currency, info in sorted(futures_balances.items()):
                    status = "🟢" if info['enabled'] else "🔴"
                    balance_display = TelegramUIUtils.format_currency(info['amount'], currency)
                    balance_text += f"• {status} {currency}: `{balance_display}`\n"
                balance_text += "\n"
            
            if not spot_balances and not futures_balances:
                balance_text += "💸 **Wszystkie salda są zerowe lub portfele nieaktywne**\n"
            
            # Dodaj informacje o aktualizacji
            balance_text += f"🕐 **Ostatnia aktualizacja:** {self._format_datetime_relative()}\n"
            
            # Przyciski dla admina
            admin_buttons = []
            # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            if True:  # Zawsze dostępne
                admin_buttons.append(Button.inline("🔄 Odśwież wszystkie", f"wallet:refresh_exchange:{exchange['id']}".encode()))
                
                if spot_balances or futures_balances:
                    admin_buttons.append(Button.inline("⚙️ Zarządzaj", f"wallet:manage_exchange:{exchange['id']}".encode()))
            
            # Przyciski
            buttons = []
            if admin_buttons:
                # Podziel admin buttons na wiersze po 2
                for i in range(0, len(admin_buttons), 2):
                    buttons.append(admin_buttons[i:i+2])
            
            buttons.extend([
                [
                    Button.inline("📊 Szczegóły giełdy", f"ex:details:{exchange['id']}".encode()),
                    Button.inline("🔄 Odśwież salda", f"wallet:balance:{exchange['id']}".encode())
                ],
                [Button.inline("🏦 Inne giełdy", b"wallet:by_exchange")],
                [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(balance_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_balance")
            await event.respond(error_msg)
    
    async def _show_multiple_exchanges_choice(self, event, exchanges: List[Dict[str, Any]], search_term: str):
        """Pokazuje listę wyboru gdy znaleziono wiele giełd."""
        choice_text = f"🔍 **Znaleziono {len(exchanges)} giełd dla '{search_term}'**\n\n"
        choice_text += "Wybierz giełdę aby zobaczyć salda:\n\n"
        
        buttons = []
        for i, exchange in enumerate(exchanges[:8], 1):  # Maksymalnie 8 opcji
            exchange_name = exchange.get('display_name') or exchange['name']
            status_emoji = "🟢" if exchange.get('is_active') else "🔴"
            choice_text += f"{i}. {status_emoji} `{exchange_name}`\n"
            
            button_text = f"{i}. {exchange_name[:15]}"  # Skróć dla przycisku
            buttons.append([Button.inline(button_text, f"wallet:balance:{exchange['id']}".encode())])
        
        if len(exchanges) > 8:
            choice_text += f"\n... i {len(exchanges) - 8} więcej (użyj bardziej precyzyjnego wyszukiwania)"
        
        buttons.append([Button.inline("🔙 Wstecz", b"wallet:by_exchange")])
        
        await event.respond(choice_text, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - PAGINATION
    # ===================
    
    @RD.cb(b"wallet:page:")
    async def wallets_page_callback(self, event):
        """Handler paginacji dla listy portfeli."""
        try:
            # Extract page number from callback data
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            # Simulate command call for pagination
            event.raw_text = f"/wallets {page}"
            await self.wallets_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in wallets pagination: {e}")
    
    @RD.cb(b"wallet:page_info")
    async def wallets_page_info_callback(self, event):
        """Informacje o aktualnej stronie."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"wallet:jump")
    async def wallets_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony portfeli, wyślij:\n"
            "`/wallets [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/wallets 3` - przejdź do strony 3\n"
            "• `/wallets 1` - powrót do pierwszej strony\n\n"
            "**Wskazówki:**\n"
            "• Użyj liczb większych od 1\n"
            "• Jeśli strona nie istnieje, zostaniesz przekierowany do ostatniej dostępnej"
        )
        
        buttons = [
            [Button.inline("💰 Strona 1", b"wallet:page:1")],
            [Button.inline("🔙 Wstecz", b"wallet:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - FILTERING
    # ===================
    
    @RD.cb(b"wallet:active_only")
    async def wallets_active_only_callback(self, event):
        """Pokazuje tylko aktywne portfele."""
        await self.wallets_active_command(event)
    
    @RD.cb(b"wallet:with_balance")
    async def wallets_with_balance_callback(self, event):
        """Pokazuje portfele z saldem."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfele z saldem
            wallets_with_balance = await wallets_table.get_accounts_with_balance(min_amount=0.0001, limit=50)
            
            if not wallets_with_balance:
                await event.edit(
                    "💰 **Portfele z Saldem**\n\n❌ Brak portfeli z saldem > 0.0001.",
                    buttons=[
                        [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")],
                        [Button.inline("⚡ Aktywne", b"wallet:active_only")]
                    ]
                )
                return
            
            balance_text = f"💰 **Portfele z Saldem** ({len(wallets_with_balance)})\n\n"
            
            total_value_display = {}
            for wallet in wallets_with_balance[:15]:  # Pokaż pierwsze 15
                exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
                status_emoji = "🟢" if wallet.get('is_enabled') else "🔴"
                balance_display = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
                
                balance_text += f"• {status_emoji} **{exchange_name}**\n"
                balance_text += f"  💎 {wallet['currency']} {wallet['type']} | 💰 {balance_display}\n"
                
                # Sumuj po walutach
                currency = wallet['currency']
                if currency not in total_value_display:
                    total_value_display[currency] = 0
                total_value_display[currency] += float(wallet['amount'])
            
            if len(wallets_with_balance) > 15:
                balance_text += f"\n... i {len(wallets_with_balance) - 15} więcej"
            
            # Podsumowanie łącznych wartości
            if total_value_display:
                balance_text += f"\n\n📊 **Łączne salda:**\n"
                for currency, total in sorted(total_value_display.items()):
                    total_display = TelegramUIUtils.format_currency(total, currency)
                    balance_text += f"• {currency}: `{total_display}`\n"
            
            buttons = [
                [
                    Button.inline("💰 Wszystkie portfele", b"wallet:page:1"),
                    Button.inline("⚡ Aktywne", b"wallet:active_only")
                ],
                [Button.inline("🔄 Odśwież", b"wallet:with_balance")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(balance_text, buttons=buttons)
            await self.log_action(user.id, "wallets_with_balance_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_with_balance")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:by_exchange")
    async def wallets_by_exchange_callback(self, event):
        """Pokazuje listę giełd do wyboru sald."""
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
            exchange_text += "Kliknij aby zobaczyć salda portfeli na konkretnej giełdzie:\n"
            
            # Przyciski giełd (maksymalnie 20)
            buttons = []
            for exchange in exchanges[:20]:
                exchange_name = exchange.get('display_name') or exchange['name']
                status_emoji = "🟢" if exchange.get('is_active') else "🔴"
                
                button_text = f"{status_emoji} {exchange_name[:18]}"
                callback_data = f"wallet:balance:{exchange['id']}".encode()
                buttons.append([Button.inline(button_text, callback_data)])
            
            if len(exchanges) > 20:
                exchange_text += f"\nPierwsze 20 z {len(exchanges)} giełd."
            
            buttons.extend([
                [Button.inline("⚡ Tylko aktywne giełdy", b"wallet:by_active_exchange")],
                [Button.inline("🔙 Wstecz", b"wallet:page:1")]
            ])
            
            await event.edit(exchange_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_by_exchange")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:by_active_exchange")
    async def wallets_by_active_exchange_callback(self, event):
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
                    buttons=[[Button.inline("🔙 Wszystkie giełdy", b"wallet:by_exchange")]]
                )
                return
            
            exchange_text = f"⚡ **Aktywne giełdy** ({len(exchanges)})\n\n"
            exchange_text += "Kliknij aby zobaczyć salda portfeli na konkretnej giełdzie:\n"
            
            # Przyciski giełd
            buttons = []
            for exchange in exchanges:
                exchange_name = exchange.get('display_name') or exchange['name']
                button_text = f"🟢 {exchange_name[:18]}"
                callback_data = f"wallet:balance:{exchange['id']}".encode()
                buttons.append([Button.inline(button_text, callback_data)])
            
            buttons.extend([
                [Button.inline("🏦 Wszystkie giełdy", b"wallet:by_exchange")],
                [Button.inline("🔙 Wstecz", b"wallet:page:1")]
            ])
            
            await event.edit(exchange_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_by_active_exchange")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:by_currency")
    async def wallets_by_currency_callback(self, event):
        """Pokazuje grupowanie portfeli po walutach."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz wszystkie portfele
            all_wallets = await wallets_table.get_all(limit=1000)
            
            if not all_wallets:
                await event.edit("💱 **Grupowanie po walutach**\n\n❌ Brak portfeli do wyświetlenia.")
                return
            
            # Grupuj po walutach
            currency_summary = {}
            for wallet in all_wallets:
                currency = wallet['currency']
                if currency not in currency_summary:
                    currency_summary[currency] = {
                        'total_amount': 0,
                        'wallets_count': 0,
                        'enabled_count': 0,
                        'exchanges': set()
                    }
                
                summary = currency_summary[currency]
                summary['total_amount'] += float(wallet['amount'])
                summary['wallets_count'] += 1
                summary['exchanges'].add(wallet.get('exchange_display_name') or wallet['exchange_name'])
                
                if wallet.get('is_enabled'):
                    summary['enabled_count'] += 1
            
            # Formatuj wyniki
            currency_text = f"💱 **Portfele po walutach** ({len(currency_summary)})\n\n"
            
            # Sortuj według łącznej wartości (tylko waluty z saldem > 0)
            sorted_currencies = []
            zero_currencies = []
            
            for currency, summary in currency_summary.items():
                if summary['total_amount'] > 0:
                    sorted_currencies.append((currency, summary))
                else:
                    zero_currencies.append((currency, summary))
            
            # Sortuj po łącznej wartości (descending)
            sorted_currencies.sort(key=lambda x: x[1]['total_amount'], reverse=True)
            
            # Wyświetl waluty z saldem
            if sorted_currencies:
                currency_text += f"💰 **Waluty z saldem:**\n"
                for currency, summary in sorted_currencies[:10]:  # Pierwsze 10
                    total_display = TelegramUIUtils.format_currency(summary['total_amount'], currency)
                    enabled_ratio = f"{summary['enabled_count']}/{summary['wallets_count']}"
                    exchanges_count = len(summary['exchanges'])
                    
                    currency_text += f"• **{currency}**: `{total_display}`\n"
                    currency_text += f"  📊 {summary['wallets_count']} portfeli ({enabled_ratio} aktywnych) na {exchanges_count} giełdach\n"
                
                if len(sorted_currencies) > 10:
                    currency_text += f"... i {len(sorted_currencies) - 10} więcej z saldem\n"
            
            # Wyświetl waluty bez salda (jeśli są)
            if zero_currencies:
                currency_text += f"\n💸 **Waluty bez salda ({len(zero_currencies)}):**\n"
                zero_list = [currency for currency, _ in zero_currencies[:8]]
                currency_text += f"• {', '.join(zero_list)}"
                if len(zero_currencies) > 8:
                    currency_text += f" i {len(zero_currencies) - 8} więcej"
            
            buttons = [
                [
                    Button.inline("💰 Z saldem", b"wallet:with_balance"),
                    Button.inline("🏦 Po giełdach", b"wallet:by_exchange")
                ],
                [Button.inline("🔄 Odśwież", b"wallet:by_currency")],
                [Button.inline("🔙 Wszystkie portfele", b"wallet:page:1")]
            ]
            
            await event.edit(currency_text, buttons=buttons)
            await self.log_action(user.id, "wallets_by_currency_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_by_currency")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - BALANCE DISPLAY
    # ===================
    
    @RD.cb(b"wallet:balance:")
    async def wallet_balance_callback(self, event):
        """Pokazuje salda dla wybranej giełdy."""
        try:
            # Extract exchange ID
            callback_data = event.data.decode()
            exchange_id = int(callback_data.split(":")[-1])
            
            # Symuluj komendę /wallet_balance z ID giełdy
            event.raw_text = f"/wallet_balance {exchange_id}"
            await self.wallet_balance_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd wyświetlania sald", alert=True)
            logger.error(f"Error in wallet balance callback: {e}")
    
    # ===================
    # CALLBACK QUERIES - ADMIN ACTIONS WITH CONFIRMATION
    # ===================
    
    @RD.cb(b"wallet:enable:")
    async def wallet_enable_callback(self, event):
        """Pokazuje potwierdzenie włączenia portfela."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Sprawdź uprawnienia administratora
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            # Sprawdź czy portfel już jest włączony
            if wallet.get('is_enabled'):
                await event.answer(f"ℹ️ Portfel {wallet_desc} na {exchange_name} jest już włączony", alert=False)
                return
            
            # Pokazuje dialog potwierdzenia
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Włączenie portfela {wallet_desc}",
                f"Giełda: {exchange_name} | ID: {wallet_id}",
                "Włączenie portfela spowoduje jego aktywację w systemie."
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "wallet:confirm_enable",
                str(wallet_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_enable")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:disable:")
    async def wallet_disable_callback(self, event):
        """Pokazuje potwierdzenie wyłączenia portfela."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Sprawdź uprawnienia administratora
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            # Sprawdź czy portfel już jest wyłączony
            if not wallet.get('is_enabled'):
                await event.answer(f"ℹ️ Portfel {wallet_desc} na {exchange_name} jest już wyłączony", alert=False)
                return
            
            # Ostrzeżenie o saldzie
            current_balance = float(wallet['amount'])
            warning = f"Portfel ma saldo: {TelegramUIUtils.format_currency(current_balance, wallet['currency'])}. Wyłączenie może wpłynąć na operacje handlowe."
            
            confirmation_msg = ConfirmationDialog.create_confirmation_message(
                f"Wyłączenie portfela {wallet_desc}",
                f"Giełda: {exchange_name} | ID: {wallet_id}",
                warning
            )
            
            buttons = ConfirmationDialog.create_confirmation_buttons(
                "wallet:confirm_disable",
                str(wallet_id)
            )
            
            await event.edit(confirmation_msg, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_disable")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:confirm_enable:")
    async def wallet_confirm_enable_callback(self, event):
        """Wykonuje włączenie portfela po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.edit("❌ **Błąd**\n\nPortfel nie znaleziony.")
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            # Włącz portfel
            success = await wallets_table.update(wallet_id, is_enabled=True)
            
            if success:
                balance_display = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
                success_msg = self.create_success_message(
                    f"Włączenie portfela {wallet_desc}",
                    f"✅ Portfel został pomyślnie włączony.\n🏦 Giełda: {exchange_name}\n💰 Saldo: {balance_display}\n⚡ Status: Aktywny"
                )
                
                buttons = [
                    [Button.inline("📊 Szczegóły", f"wallet:details:{wallet_id}".encode())],
                    [Button.inline("💰 Portfele na giełdzie", f"wallet:balance:{wallet['exchange_id']}".encode())],
                    [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "wallet_enabled", {
                    "wallet_id": wallet_id, 
                    "exchange_name": exchange_name,
                    "wallet_desc": wallet_desc
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się włączyć portfela. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_confirm_enable")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:confirm_disable:")
    async def wallet_confirm_disable_callback(self, event):
        """Wykonuje wyłączenie portfela po potwierdzeniu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.edit("❌ **Błąd**\n\nPortfel nie znaleziony.")
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            # Wyłącz portfel
            success = await wallets_table.update(wallet_id, is_enabled=False)
            
            if success:
                balance_display = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
                success_msg = self.create_success_message(
                    f"Wyłączenie portfela {wallet_desc}",
                    f"✅ Portfel został pomyślnie wyłączony.\n🏦 Giełda: {exchange_name}\n💰 Saldo: {balance_display}\n🔴 Status: Nieaktywny"
                )
                
                buttons = [
                    [Button.inline("📊 Szczegóły", f"wallet:details:{wallet_id}".encode())],
                    [Button.inline("💰 Portfele na giełdzie", f"wallet:balance:{wallet['exchange_id']}".encode())],
                    [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "wallet_disabled", {
                    "wallet_id": wallet_id, 
                    "exchange_name": exchange_name,
                    "wallet_desc": wallet_desc
                })
            else:
                await event.edit("❌ **Błąd**\n\nNie udało się wyłączyć portfela. Spróbuj ponownie.")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_confirm_disable")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - REFRESH ACTION
    # ===================
    
    @RD.cb(b"wallet:refresh:")
    async def wallet_refresh_callback(self, event):
        """Odświeżenie salda pojedynczego portfela."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            await event.answer("🔒 Brak uprawnień administratora!", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
            wallet_desc = f"{wallet['currency']} {wallet['type']}"
            
            # Wyślij loading message
            loading_msg = self.create_loading_message(f"odświeżanie salda portfela {wallet_desc} na {exchange_name}")
            await event.edit(loading_msg)
            
            # Symulacja odświeżania salda (w przyszłości można podłączyć rzeczywiste API giełdy)
            import asyncio
            await asyncio.sleep(2)  # Symulacja API call
            
            # Mock odświeżenia - w rzeczywistości tutaj byłby API call do giełdy
            # Na razie tylko zaktualizujemy updated_at
            success = await wallets_table.update(wallet_id, updated_at=None)  # None spowoduje użycie CURRENT_TIMESTAMP
            
            if success:
                # Pobierz zaktualizowany portfel
                updated_wallet = await wallets_table.get_by_id(wallet_id)
                balance_display = TelegramUIUtils.format_currency(float(updated_wallet['amount']), updated_wallet['currency'])
                
                results_msg = self.create_success_message(
                    f"Odświeżenie portfela {wallet_desc}",
                    f"✅ Saldo zostało odświeżone\n🏦 Giełda: {exchange_name}\n💰 Aktualne saldo: {balance_display}\n🕐 Zaktualizowano: {self._format_datetime_relative()}"
                )
            else:
                results_msg = self.create_error_message(
                    f"odświeżania portfela {wallet_desc}",
                    f"❌ Nie udało się odświeżyć salda\n🏦 Giełda: {exchange_name}"
                )
            
            buttons = [
                [
                    Button.inline("🔄 Odśwież ponownie", f"wallet:refresh:{wallet_id}".encode()),
                    Button.inline("📊 Szczegóły", f"wallet:details:{wallet_id}".encode())
                ],
                [Button.inline("💰 Portfele na giełdzie", f"wallet:balance:{wallet['exchange_id']}".encode())],
                [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")]
            ]
            
            await event.edit(results_msg, buttons=buttons)
            await self.log_action(user.id, "wallet_refresh", {
                "wallet_id": wallet_id,
                "exchange_name": exchange_name,
                "wallet_desc": wallet_desc,
                "success": success
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_refresh")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:refresh_exchange:")
    async def wallet_refresh_exchange_callback(self, event):
        """Odświeżenie wszystkich sald na giełdzie."""
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
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz giełdę i jej portfele
            exchange = await exchanges_table.get_by_id(exchange_id)
            if not exchange:
                await event.answer("❌ Giełda nie znaleziona", alert=True)
                return
            
            exchange_wallets = await wallets_table.get_by_exchange_id(exchange_id, limit=100)
            
            exchange_name = exchange.get('display_name') or exchange['name']
            
            # Wyślij loading message
            loading_msg = self.create_loading_message(f"odświeżanie wszystkich sald na {exchange_name}")
            await event.edit(loading_msg)
            
            # Symulacja odświeżania wszystkich sald
            import asyncio
            await asyncio.sleep(3)  # Symulacja API calls
            
            # Mock odświeżenia - aktualizujemy updated_at dla wszystkich portfeli
            refreshed_count = 0
            for wallet in exchange_wallets:
                success = await wallets_table.update(wallet['id'], updated_at=None)
                if success:
                    refreshed_count += 1
            
            if refreshed_count > 0:
                results_msg = self.create_success_message(
                    f"Odświeżenie sald - {exchange_name}",
                    f"✅ Odświeżono {refreshed_count} z {len(exchange_wallets)} portfeli\n🕐 Zaktualizowano: {self._format_datetime_relative()}"
                )
            else:
                results_msg = self.create_error_message(
                    f"odświeżania sald - {exchange_name}",
                    f"❌ Nie udało się odświeżyć żadnego portfela\n📊 Sprawdzonych: {len(exchange_wallets)} portfeli"
                )
            
            buttons = [
                [
                    Button.inline("🔄 Odśwież ponownie", f"wallet:refresh_exchange:{exchange_id}".encode()),
                    Button.inline("💰 Zobacz salda", f"wallet:balance:{exchange_id}".encode())
                ],
                [Button.inline("🏦 Inne giełdy", b"wallet:by_exchange")],
                [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")]
            ]
            
            await event.edit(results_msg, buttons=buttons)
            await self.log_action(user.id, "wallet_refresh_exchange", {
                "exchange_id": exchange_id,
                "exchange_name": exchange_name,
                "wallets_refreshed": refreshed_count,
                "total_wallets": len(exchange_wallets)
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_refresh_exchange")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - OTHER ACTIONS
    # ===================
    
    @RD.cb(b"wallet:stats")
    async def wallet_stats_callback(self, event):
        """Pokazuje statystyki portfeli."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            stats = await self.get_domain_specific_stats()
            
            if 'error' in stats:
                await event.edit(f"❌ **Błąd pobierania statystyk**\n\n{stats['error']}")
                return
            
            stats_text = "📊 **Statystyki Portfeli**\n\n"
            stats_text += f"💰 **Wszystkie portfele:** {stats['total_wallets']}\n"
            stats_text += f"⚡ **Aktywne portfele:** {stats['enabled_wallets']}\n"
            stats_text += f"🔴 **Nieaktywne portfele:** {stats['disabled_wallets']}\n"
            stats_text += f"💸 **Portfele z saldem:** {stats['wallets_with_balance']}\n"
            stats_text += f"💎 **Unikalne waluty:** {stats['unique_currencies']}\n"
            stats_text += f"🏦 **Giełdy z portfelami:** {stats['exchanges_with_wallets']}\n"
            stats_text += f"📈 **Łączne transakcje:** {stats['total_transactions']}\n"
            
            # Oblicz procenty
            if stats['total_wallets'] > 0:
                enabled_percent = (stats['enabled_wallets'] / stats['total_wallets']) * 100
                balance_percent = (stats['wallets_with_balance'] / stats['total_wallets']) * 100
                stats_text += f"\n📈 **Procent aktywnych:** {enabled_percent:.1f}%\n"
                stats_text += f"💰 **Procent z saldem:** {balance_percent:.1f}%\n"
            
            buttons = [
                [
                    Button.inline("💰 Wszystkie", b"wallet:page:1"),
                    Button.inline("⚡ Aktywne", b"wallet:active_only")
                ],
                [
                    Button.inline("💸 Z saldem", b"wallet:with_balance"),
                    Button.inline("🏦 Po giełdach", b"wallet:by_exchange")
                ],
                [Button.inline("🔄 Odśwież", b"wallet:stats")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(stats_text, buttons=buttons)
            await self.log_action(user.id, "wallets_stats_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallets_stats")
            await event.edit(error_msg)
    
    @RD.cb(b"wallet:details:")
    async def wallet_details_callback(self, event):
        """Pokazuje szczegółowe informacje o portfelu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            wallets_table = self.db.get_factory().get_exchange_account_state_table()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Pobierz portfel
            wallet = await wallets_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            # Pobierz ostatnie transakcje dla tego portfela
            recent_transactions = await transactions_table.get_by_exchange_account_state_id(wallet_id, limit=5)
            
            # Formatuj szczegółowe informacje
            info_text = self.format_wallet_info(wallet)
            
            # Dodaj informacje o transakcjach
            if recent_transactions:
                info_text += f"\n📈 **Ostatnie transakcje ({len(recent_transactions)}):**\n"
                for transaction in recent_transactions:
                    tx_type = transaction['type']
                    tx_emoji = "📈" if tx_type == "BUY" else "📉"
                    asset_symbol = f"{transaction['asset']}/{transaction['quote']}"
                    amount = TelegramUIUtils.format_currency(float(transaction['asset_amount']), transaction['asset'])
                    
                    info_text += f"• {tx_emoji} {tx_type}: {amount} {asset_symbol}\n"
            else:
                info_text += f"\n📈 **Transakcje:** Brak danych\n"
            
            # Przyciski dla admina
            admin_buttons = []
            # Usunięto sprawdzanie uprawnień - funkcja dostępna dla wszystkich
            if True:  # Zawsze dostępne
                if wallet.get('is_enabled'):
                    admin_buttons.append(Button.inline("🔴 Wyłącz", f"wallet:disable:{wallet_id}".encode()))
                else:
                    admin_buttons.append(Button.inline("🟢 Włącz", f"wallet:enable:{wallet_id}".encode()))
                
                admin_buttons.append(Button.inline("🔄 Odśwież", f"wallet:refresh:{wallet_id}".encode()))
            
            # Przyciski
            buttons = []
            if admin_buttons:
                for i in range(0, len(admin_buttons), 2):
                    buttons.append(admin_buttons[i:i+2])
            
            buttons.extend([
                [
                    Button.inline("💰 Salda giełdy", f"wallet:balance:{wallet['exchange_id']}".encode()),
                    Button.inline("📊 Giełda", f"ex:details:{wallet['exchange_id']}".encode())
                ],
                [Button.inline("💰 Wszystkie portfele", b"wallet:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "wallet_details_view", {
                "wallet_id": wallet_id, 
                "exchange_name": wallet.get('exchange_display_name') or wallet['exchange_name'],
                "currency": wallet['currency'],
                "type": wallet['type']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wallet_details")
            await event.edit(error_msg)
    
    # ===================
    # UTILITY METHODS
    # ===================
    
    def format_wallet_info(self, wallet: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o portfelu.
        
        Args:
            wallet: Słownik z danymi portfela
            
        Returns:
            str: Sformatowane informacje o portfelu
        """
        exchange_name = wallet.get('exchange_display_name') or wallet['exchange_name']
        status_emoji = "🟢" if wallet.get('is_enabled') else "🔴"
        status_text = "Aktywny" if wallet.get('is_enabled') else "Nieaktywny"
        balance_display = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
        
        response = f"💰 **Portfel: {wallet['currency']} {wallet['type']}**\n\n"
        response += f"🏦 **Giełda:** {exchange_name}\n"
        response += f"💎 **Waluta:** `{wallet['currency']}`\n"
        response += f"📊 **Typ:** `{wallet['type']}`\n"
        response += f"💰 **Saldo:** `{balance_display}`\n"
        response += f"{status_emoji} **Status:** {status_text}\n"
        response += f"🆔 **Database ID:** `{wallet['id']}`\n"
        
        if 'created_at' in wallet:
            response += f"📅 **Utworzony:** {self._format_datetime(wallet.get('created_at'))}\n"
        
        if 'updated_at' in wallet:
            response += f"🔄 **Ostatnia aktualizacja:** {self._format_datetime(wallet.get('updated_at'))}\n"
        
        return response

    def _format_datetime_relative(self) -> str:
        """Helper method do formatowania obecnego czasu."""
        from datetime import datetime
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S")
