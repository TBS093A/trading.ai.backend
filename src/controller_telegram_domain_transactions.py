"""
Kontroler Transactions dla Telegram - zarządzanie transakcjami kryptowalutowymi.

Ta klasa implementuje:
- Przeglądanie transakcji z filtrowaniem i paginacją
- Interaktywny kreator nowej transakcji
- Szczegółowe informacje o transakcjach
- Zarządzanie transakcjami oczekującymi na interpretację
- Integrację z sync_transactions.py dla wykonywania transakcji

Autor: AI Assistant
"""

import logging
import asyncio
import traceback
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from telethon import Button

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, UserPermissionLevel, RD
from .controller_telegram_utils_ui import PaginationHelper, ConfirmationDialog, ValidationHelper, TelegramUIUtils
from .sync_transactions import Transactions

logger = logging.getLogger(__name__)


class TransactionsTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla zarządzania transakcjami kryptowalutowymi w systemie Telegram.
    
    Zapewnia funkcjonalności:
    - Lista ostatnich transakcji z paginacją
    - Filtrowanie transakcji bez interpretacji
    - Interaktywny kreator nowych transakcji
    - Szczegółowe informacje o transakcjach
    - Integrację z system wykonywania transakcji
    - Wybór giełd, assetów i strategii
    """
    
    DOMAIN = "transactions"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera transakcji.
        
        Args:
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        
        # Konfiguracja paginacji
        self.default_page_size = 20
        self.max_page_size = 100
        
        # Wizard state dla tworzenia transakcji
        self.transaction_wizards = {}
        
        # Integration with sync_transactions
        self.transactions_sync = Transactions(test_mode=False)
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny transakcji."""
        try:
            if not self.db:
                return {"error": "Database not available"}
            
            await self.init_database()
            
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Pobierz podstawowe statystyki
            all_transactions = await transactions_table.get_all(limit=10000)
            buy_transactions = await transactions_table.get_by_type("BUY", limit=5000)
            sell_transactions = await transactions_table.get_by_type("SELL", limit=5000)
            pending_transactions = await transactions_table.get_transactions_without_interpretation(limit=1000)
            
            # Oblicz statystyki za ostatnie 24h
            yesterday_timestamp = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
            today_timestamp = int(datetime.now().timestamp() * 1000)
            recent_transactions = await transactions_table.get_by_date_range(
                yesterday_timestamp, today_timestamp, limit=1000
            )
            
            return {
                "total_transactions": len(all_transactions),
                "buy_transactions": len(buy_transactions),
                "sell_transactions": len(sell_transactions),
                "pending_interpretation": len(pending_transactions),
                "last_24h_transactions": len(recent_transactions),
                "database_available": True
            }
            
        except Exception as e:
            logger.error(f"Error getting transactions domain stats: {e}")
            return {
                "error": str(e),
                "database_available": False
            }
    
    # ===================
    # COMMANDS - TRANSACTIONS LIST
    # ===================
    
    @RD.cmd("transactions", aliases=["tx", "list_transactions"])
    async def transactions_command(self, event):
        """
        Komenda wyświetlania listy ostatnich transakcji z opcjonalnym limitem.
        Użycie: /transactions [limit]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "transactions_list")
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = self.default_page_size
        page = 1
        
        if len(text_parts) >= 2:
            try:
                # Sprawdź czy to jest limit czy numer strony
                value = int(text_parts[1])
                if value <= 50:  # Jeśli wartość <= 50, traktuj jako limit
                    limit = min(value, self.max_page_size)
                else:  # W przeciwnym razie jako page
                    page = max(1, value)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * limit
            
            # Pobierz transakcje z dodatkowym rekordem dla sprawdzenia następnej strony
            transactions = await transactions_table.get_all(limit=limit + 1, offset=offset)
            
            if not transactions:
                await event.respond("💸 **Lista Transakcji**\n\n❌ Brak transakcji do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(transactions) > limit
            page_transactions = transactions[:limit]
            
            # Formatuj odpowiedź
            transactions_text = f"💸 **Lista Transakcji - Strona {page}** (Limit: {limit})\n\n"
            
            for i, transaction in enumerate(page_transactions, 1):
                item_number = offset + i
                tx_type_emoji = "🟢" if transaction['type'] == 'BUY' else "🔴"
                exchange_name = transaction.get('exchange_display_name') or transaction['exchange_name']
                asset_symbol = f"{transaction['asset']}/{transaction['quote']}"
                
                # Formatuj kwoty
                quote_amount = TelegramUIUtils.format_currency(
                    float(transaction['quote_amount']), transaction['quote']
                )
                asset_amount = f"{float(transaction['asset_amount']):.8f} {transaction['asset']}"
                
                # Format czasu
                tx_time = self._format_datetime_from_timestamp(transaction['created_at'])
                
                transactions_text += f"{item_number}. {tx_type_emoji} **{transaction['type']}** `{asset_symbol}`\n"
                transactions_text += f"    🏦 {exchange_name} | 💰 {quote_amount}\n"
                transactions_text += f"    📊 {asset_amount} | ⏰ {tx_time}\n"
                
                # Dodaj info o strategii/interpretacji
                if transaction.get('interpretation_title'):
                    title = transaction['interpretation_title'][:30] + "..." if len(transaction['interpretation_title']) > 30 else transaction['interpretation_title']
                    transactions_text += f"    🧠 {title}\n"
                elif transaction.get('buy_strategy_type') or transaction.get('sell_strategy_type'):
                    strategy_type = transaction.get('buy_strategy_type') or transaction.get('sell_strategy_type')
                    transactions_text += f"    📈 Strategia: {strategy_type}\n"
                else:
                    transactions_text += f"    ⚠️ Brak interpretacji\n"
                
                transactions_text += "\n"
            
            # Dodaj informację o paginacji
            if page > 1 or has_next:
                transactions_text += f"📄 Strona {page}"
                if has_next:
                    transactions_text += f" (więcej dostępne)"
            
            # Stwórz pagination_info dla PaginationHelper
            estimated_total = offset + len(page_transactions) + (100 if has_next else 0)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, limit),
                'total_items': estimated_total,
                'items_on_page': len(page_transactions),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_transactions)
            }
            
            # Użyj PaginationHelper do utworzenia przycisków paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "tx", 
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("⏳ Bez interpretacji", b"tx:pending"),
                    Button.inline("📊 Statystyki", b"tx:stats")
                ],
                [
                    Button.inline("➕ Nowa transakcja", b"tx:create_wizard:start"),
                    Button.inline("🔄 Odśwież", f"tx:page:{page}".encode())
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(transactions_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transactions_list")
            await event.respond(error_msg)
    
    @RD.cmd("transactions_pending", aliases=["tx_pending", "pending_transactions"])
    async def transactions_pending_command(self, event):
        """
        Komenda wyświetlania transakcji bez interpretacji.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "transactions_pending_list")
        
        try:
            await self.init_database()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Pobierz transakcje bez interpretacji
            pending_transactions = await transactions_table.get_transactions_without_interpretation(limit=50)
            
            if not pending_transactions:
                await event.respond(
                    "⏳ **Transakcje bez interpretacji**\n\n✅ Wszystkie transakcje mają interpretację!",
                    buttons=[
                        [Button.inline("💸 Wszystkie transakcje", b"tx:page:1")],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj listę oczekujących transakcji
            pending_text = f"⏳ **Transakcje bez interpretacji** ({len(pending_transactions)})\n\n"
            pending_text += "Te transakcje wymagają interpretacji AI:\n\n"
            
            for i, transaction in enumerate(pending_transactions[:15], 1):
                tx_type_emoji = "🟢" if transaction['type'] == 'BUY' else "🔴"
                exchange_name = transaction.get('exchange_display_name') or transaction['exchange_name']
                asset_symbol = f"{transaction['asset']}/{transaction['quote']}"
                
                quote_amount = TelegramUIUtils.format_currency(
                    float(transaction['quote_amount']), transaction['quote']
                )
                
                tx_time = self._format_datetime_from_timestamp(transaction['created_at'])
                
                pending_text += f"{i}. {tx_type_emoji} **{transaction['type']}** `{asset_symbol}`\n"
                pending_text += f"    🏦 {exchange_name} | 💰 {quote_amount} | ⏰ {tx_time}\n"
            
            if len(pending_transactions) > 15:
                pending_text += f"\n... i {len(pending_transactions) - 15} więcej"
            
            # Przyciski szczegółów dla pierwszych transakcji
            buttons = []
            details_buttons = []
            
            for transaction in pending_transactions[:6]:
                tx_symbol = f"{transaction['asset'][:4]}/{transaction['quote'][:4]}"
                tx_type_short = "B" if transaction['type'] == 'BUY' else "S"
                details_buttons.append(
                    Button.inline(f"{tx_type_short}:{tx_symbol}", f"tx:details:{transaction['id']}".encode())
                )
            
            # Podziel na wiersze po 3 przyciski
            for i in range(0, len(details_buttons), 3):
                buttons.append(details_buttons[i:i+3])
            
            buttons.extend([
                [
                    Button.inline("💸 Wszystkie", b"tx:page:1"),
                    Button.inline("🔄 Odśwież", b"tx:pending")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(pending_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transactions_pending")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - TRANSACTION CREATION
    # ===================
    
    @RD.cmd("transaction_create", aliases=["tx_create", "create_transaction"])
    async def transaction_create_command(self, event):
        """
        Komenda rozpoczynająca interaktywny kreator nowej transakcji.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.respond("🔒 Brak uprawnień do tworzenia transakcji!\n\nWymagany poziom: **Trader**")
            return
        
        await self.log_action(user.id, "transaction_create_start")
        
        # Rozpocznij wizard tworzenia transakcji
        await self._start_transaction_wizard(event, user)
    
    # ===================
    # COMMANDS - TRANSACTION INFO
    # ===================
    
    @RD.cmd("transaction_info", aliases=["tx_info", "info_transaction"])
    async def transaction_info_command(self, event):
        """
        Komenda szczegółowych informacji o transakcji.
        Użycie: /transaction_info [id]
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "📊 **Informacje o transakcji**\n\n"
                "Podaj ID transakcji:\n\n"
                "**Użycie:**\n"
                "• `/transaction_info 123`\n"
                "• `/tx_info 456`",
                buttons=[
                    [Button.inline("💸 Lista transakcji", b"tx:page:1")],
                    [Button.inline("⏳ Bez interpretacji", b"tx:pending")],
                    [Button.inline("🔙 Menu główne", b"nav:home")]
                ]
            )
            return
        
        try:
            transaction_id = int(parts[1].strip())
        except ValueError:
            await event.respond("❌ **Nieprawidłowe ID transakcji**\n\nID musi być liczbą.")
            return
        
        await self.log_action(user.id, "transaction_info", {"transaction_id": transaction_id})
        
        try:
            await self.init_database()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Pobierz transakcję
            transaction = await transactions_table.get_by_id(transaction_id)
            if not transaction:
                await event.respond(
                    f"❌ **Transakcja nie znaleziona**\n\n"
                    f"Nie można znaleźć transakcji o ID: `{transaction_id}`",
                    buttons=[
                        [Button.inline("💸 Lista transakcji", b"tx:page:1")],
                        [Button.inline("🔙 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj szczegółowe informacje
            info_text = self.format_transaction_info(transaction)
            
            # Przyciski
            buttons = [
                [Button.inline("🔄 Odśwież", f"tx:details:{transaction_id}".encode())],
                [
                    Button.inline("💸 Lista transakcji", b"tx:page:1"),
                    Button.inline("⏳ Bez interpretacji", b"tx:pending")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.respond(info_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transaction_info")
            await event.respond(error_msg)
    
    # ===================
    # CALLBACK QUERIES - PAGINATION
    # ===================
    
    @RD.cb(b"tx:page:")
    async def transactions_page_callback(self, event):
        """Handler paginacji dla listy transakcji."""
        try:
            # Extract page number from callback data
            callback_data = event.data.decode()
            page = int(callback_data.split(":")[-1])
            
            # Simulate command call for pagination
            event.raw_text = f"/transactions {page}"
            await self.transactions_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in transactions pagination: {e}")
    
    @RD.cb(b"tx:page_info")
    async def transactions_page_info_callback(self, event):
        """Informacje o aktualnej stronie."""
        await event.answer("ℹ️ Nawigacja po stronach - użyj przycisków ◀️ ▶️", alert=False)
    
    @RD.cb(b"tx:jump")
    async def transactions_jump_callback(self, event):
        """Obsługa przycisku jump to page z PaginationHelper."""
        jump_help = (
            "🔢 **Przejdź do strony**\n\n"
            "Aby przejść do konkretnej strony transakcji, wyślij:\n"
            "`/transactions [numer_strony]`\n\n"
            "**Przykłady:**\n"
            "• `/transactions 5` - przejdź do strony 5\n"
            "• `/transactions 1` - powrót do pierwszej strony\n"
            "• `/tx 10` - przejdź do strony 10\n\n"
            "**Wskazówki:**\n"
            "• Możesz też ustawić limit: `/transactions 25` (limit 25)\n"
            "• Maksymalny limit to 100 transakcji na stronę"
        )
        
        buttons = [
            [Button.inline("💸 Strona 1", b"tx:page:1")],
            [Button.inline("🔙 Wstecz", b"tx:page:1")]
        ]
        
        await event.edit(jump_help, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - TRANSACTION DETAILS
    # ===================
    
    @RD.cb(b"tx:details:")
    async def transaction_details_callback(self, event):
        """Pokazuje szczegółowe informacje o transakcji."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract transaction ID
            callback_data = event.data.decode()
            transaction_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            # Pobierz transakcję
            transaction = await transactions_table.get_by_id(transaction_id)
            if not transaction:
                await event.answer("❌ Transakcja nie znaleziona", alert=True)
                return
            
            # Formatuj szczegółowe informacje
            info_text = self.format_transaction_info(transaction)
            
            # Przyciski
            buttons = [
                [Button.inline("🔄 Odśwież", f"tx:details:{transaction_id}".encode())],
                [
                    Button.inline("💸 Lista transakcji", b"tx:page:1"),
                    Button.inline("⏳ Bez interpretacji", b"tx:pending")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(info_text, buttons=buttons)
            await self.log_action(user.id, "transaction_details_view", {
                "transaction_id": transaction_id,
                "transaction_type": transaction['type'],
                "asset": transaction['asset'],
                "quote": transaction['quote']
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transaction_details")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - OTHER ACTIONS
    # ===================
    
    @RD.cb(b"tx:pending")
    async def transactions_pending_callback(self, event):
        """Pokazuje transakcje bez interpretacji."""
        await self.transactions_pending_command(event)
    
    @RD.cb(b"tx:stats")
    async def transactions_stats_callback(self, event):
        """Pokazuje statystyki transakcji."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            stats = await self.get_domain_specific_stats()
            
            if 'error' in stats:
                await event.edit(f"❌ **Błąd pobierania statystyk**\n\n{stats['error']}")
                return
            
            stats_text = "📊 **Statystyki Transakcji**\n\n"
            stats_text += f"💸 **Wszystkie transakcje:** {stats['total_transactions']}\n"
            stats_text += f"🟢 **Transakcje kupna:** {stats['buy_transactions']}\n"
            stats_text += f"🔴 **Transakcje sprzedaży:** {stats['sell_transactions']}\n"
            stats_text += f"⏳ **Bez interpretacji:** {stats['pending_interpretation']}\n"
            stats_text += f"🕐 **Ostatnie 24h:** {stats['last_24h_transactions']}\n"
            
            # Oblicz procenty
            if stats['total_transactions'] > 0:
                buy_percent = (stats['buy_transactions'] / stats['total_transactions']) * 100
                sell_percent = (stats['sell_transactions'] / stats['total_transactions']) * 100
                pending_percent = (stats['pending_interpretation'] / stats['total_transactions']) * 100
                
                stats_text += f"\n📈 **Rozkład:**\n"
                stats_text += f"• Kupno: {buy_percent:.1f}%\n"
                stats_text += f"• Sprzedaż: {sell_percent:.1f}%\n"
                stats_text += f"• Oczekujące: {pending_percent:.1f}%\n"
            
            buttons = [
                [
                    Button.inline("💸 Wszystkie", b"tx:page:1"),
                    Button.inline("⏳ Oczekujące", b"tx:pending")
                ],
                [Button.inline("🔄 Odśwież", b"tx:stats")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(stats_text, buttons=buttons)
            await self.log_action(user.id, "transactions_stats_view")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transactions_stats")
            await event.edit(error_msg)
    
    # ===================
    # TRANSACTION WIZARD - START AND STEPS
    # ===================
    
    @RD.cb(b"tx:create_wizard:")
    async def transaction_create_wizard_callback(self, event):
        """Handler głównego wizarda tworzenia transakcji."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do tworzenia transakcji!", alert=True)
            return
        
        try:
            # Parse callback data
            callback_data = event.data.decode()
            step = callback_data.split(":")[-1]
            
            if step == "start":
                await self._start_transaction_wizard(event, user)
            elif step == "type_buy":
                await self._set_transaction_type(event, user, "BUY")
            elif step == "type_sell":
                await self._set_transaction_type(event, user, "SELL")
            elif step == "cancel":
                await self._cancel_transaction_wizard(event, user)
            else:
                await event.answer("❌ Nieprawidłowy krok wizarda", alert=True)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transaction_wizard")
            await event.edit(error_msg)
    
    async def _start_transaction_wizard(self, event, user):
        """Rozpoczyna wizard tworzenia transakcji."""
        # Wyczyść poprzedni stan wizarda
        if user.id in self.transaction_wizards:
            del self.transaction_wizards[user.id]
        
        wizard_text = (
            "🧙‍♂️ **Kreator Nowej Transakcji**\n\n"
            "📋 **Krok 1/5: Typ transakcji**\n\n"
            "Wybierz typ transakcji którą chcesz wykonać:\n\n"
            "🟢 **BUY** - Kupno kryptowaluty\n"
            "🔴 **SELL** - Sprzedaż kryptowaluty\n\n"
            "⚠️ **Uwaga:** Transakcja będzie wykonana natychmiast na giełdzie!"
        )
        
        buttons = [
            [
                Button.inline("🟢 KUPNO", b"tx:create_wizard:type_buy"),
                Button.inline("🔴 SPRZEDAŻ", b"tx:create_wizard:type_sell")
            ],
            [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
        ]
        
        if hasattr(event, 'edit'):
            await event.edit(wizard_text, buttons=buttons)
        else:
            await event.respond(wizard_text, buttons=buttons)
    
    async def _set_transaction_type(self, event, user, transaction_type: str):
        """Ustawia typ transakcji i przechodzi do wyboru giełdy."""
        # Zapisz typ transakcji
        self.transaction_wizards[user.id] = {
            "step": "select_exchange",
            "data": {
                "type": transaction_type,
            },
            "created_at": self._get_current_timestamp()
        }
        
        type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
        type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
        
        wizard_text = (
            f"🧙‍♂️ **Kreator Nowej Transakcji**\n\n"
            f"📋 **Krok 2/5: Wybór giełdy**\n\n"
            f"✅ **Typ:** {type_emoji} {type_name}\n\n"
            f"Wybierz giełdę na której chcesz wykonać transakcję:"
        )
        
        # Pobierz aktywne giełdy
        try:
            await self.init_database()
            exchanges_table = self.db.get_factory().get_exchanges_table()
            active_exchanges = await exchanges_table.get_active(limit=20)
            
            if not active_exchanges:
                await event.edit(
                    "❌ **Brak aktywnych giełd**\n\n"
                    "Nie można kontynuować bez dostępnych giełd.",
                    buttons=[[Button.inline("🔙 Wstecz", b"tx:create_wizard:start")]]
                )
                return
            
            buttons = []
            for exchange in active_exchanges[:10]:  # Limit 10 giełd
                exchange_name = exchange.get('display_name') or exchange['name']
                buttons.append([Button.inline(
                    f"🏦 {exchange_name}", 
                    f"tx:select_exchange:{exchange['id']}".encode()
                )])
            
            buttons.append([Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")])
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_select_exchange")
            await event.edit(error_msg)
    
    async def _cancel_transaction_wizard(self, event, user):
        """Anuluje wizard tworzenia transakcji."""
        if user.id in self.transaction_wizards:
            del self.transaction_wizards[user.id]
        
        await event.edit(
            "❌ **Kreator anulowany**\n\n"
            "Tworzenie transakcji zostało anulowane.",
            buttons=[
                [Button.inline("💸 Lista transakcji", b"tx:page:1")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
        )
    
    # ===================
    # TRANSACTION WIZARD - EXCHANGE AND ASSET SELECTION
    # ===================
    
    @RD.cb(b"tx:select_exchange:")
    async def select_exchange_callback(self, event):
        """Handler wyboru giełdy w wizardzie."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            await event.answer("❌ Sesja wizarda wygasła", alert=True)
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
            
            # Aktualizuj wizard state
            wizard_state = self.transaction_wizards[user.id]
            wizard_state['data']['exchange_id'] = exchange_id
            wizard_state['data']['exchange'] = exchange
            wizard_state['step'] = "select_asset"
            
            exchange_name = exchange.get('display_name') or exchange['name']
            transaction_type = wizard_state['data']['type']
            type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
            type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
            
            # Przejdź do wyboru assetu
            await self._show_asset_selection(event, user, exchange_id, exchange_name, transaction_type)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_exchange_selection")
            await event.edit(error_msg)
    
    async def _show_asset_selection(self, event, user, exchange_id: int, exchange_name: str, transaction_type: str):
        """Pokazuje wybór assetu dla danej giełdy."""
        try:
            await self.init_database()
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            
            # Pobierz assety dostępne na tej giełdzie
            exchange_assets = await asset_exchanges_table.get_by_exchange_id(exchange_id, limit=50)
            
            if not exchange_assets:
                await event.edit(
                    f"❌ **Brak assetów na giełdzie {exchange_name}**\n\n"
                    "Nie można kontynuować bez dostępnych assetów.",
                    buttons=[
                        [Button.inline("🔙 Wybierz inną giełdę", b"tx:create_wizard:start")],
                        [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
                    ]
                )
                return
            
            type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
            type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
            
            wizard_text = (
                f"🧙‍♂️ **Kreator Nowej Transakcji**\n\n"
                f"📋 **Krok 3/5: Wybór assetu**\n\n"
                f"✅ **Typ:** {type_emoji} {type_name}\n"
                f"✅ **Giełda:** 🏦 {exchange_name}\n\n"
                f"Wybierz asset do transakcji ({len(exchange_assets)} dostępnych):"
            )
            
            # Pogrupuj assety według popularności (najpierw USDT, USD, BTC, ETH)
            popular_quotes = ['USDT', 'USD', 'BTC', 'ETH', 'BNB']
            popular_assets = []
            other_assets = []
            
            for asset_exchange in exchange_assets:
                asset_symbol = f"{asset_exchange['asset']}/{asset_exchange['quote']}"
                if asset_exchange['quote'] in popular_quotes:
                    popular_assets.append(asset_exchange)
                else:
                    other_assets.append(asset_exchange)
            
            # Sortuj popularne po kolejności w popular_quotes
            popular_assets.sort(key=lambda x: popular_quotes.index(x['quote']) if x['quote'] in popular_quotes else 999)
            
            buttons = []
            all_assets = popular_assets + other_assets
            
            # Pokaż pierwsze 15 assetów
            for asset_exchange in all_assets[:15]:
                asset_symbol = f"{asset_exchange['asset']}/{asset_exchange['quote']}"
                buttons.append([Button.inline(
                    f"💎 {asset_symbol}",
                    f"tx:select_asset:{exchange_id}:{asset_exchange['asset_id']}".encode()
                )])
            
            if len(all_assets) > 15:
                wizard_text += f"\n\n(Pokazane pierwsze 15 z {len(all_assets)} assetów)"
            
            buttons.extend([
                [Button.inline("🔙 Wybierz giełdę", b"tx:create_wizard:start")],
                [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
            ])
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_asset_selection")
            await event.edit(error_msg)
    
    @RD.cb(b"tx:select_asset:")
    async def select_asset_callback(self, event):
        """Handler wyboru assetu w wizardzie."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            await event.answer("❌ Sesja wizarda wygasła", alert=True)
            return
        
        try:
            # Parse callback data: tx:select_asset:exchange_id:asset_id
            callback_data = event.data.decode()
            parts = callback_data.split(":")
            exchange_id = int(parts[2])
            asset_id = int(parts[3])
            
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Pobierz asset
            asset = await assets_table.get_by_id(asset_id)
            if not asset:
                await event.answer("❌ Asset nie znaleziony", alert=True)
                return
            
            # Aktualizuj wizard state
            wizard_state = self.transaction_wizards[user.id]
            wizard_state['data']['asset_id'] = asset_id
            wizard_state['data']['asset'] = asset
            wizard_state['step'] = "select_wallet"
            
            # Przejdź do wyboru portfela
            await self._show_wallet_selection(event, user, wizard_state)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_asset_selection")
            await event.edit(error_msg)
    
    # ===================
    # TRANSACTION WIZARD - WALLET AND STRATEGY SELECTION
    # ===================
    
    async def _show_wallet_selection(self, event, user, wizard_state: Dict[str, Any]):
        """Pokazuje wybór portfela (exchange account state)."""
        try:
            exchange_id = wizard_state['data']['exchange_id']
            asset = wizard_state['data']['asset']
            exchange = wizard_state['data']['exchange']
            transaction_type = wizard_state['data']['type']
            
            await self.init_database()
            account_state_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfele na tej giełdzie
            wallets = await account_state_table.get_by_exchange_id(exchange_id, limit=50)
            
            if not wallets:
                await event.edit(
                    f"❌ **Brak portfeli na giełdzie {exchange['name']}**\n\n"
                    "Nie można kontynuować bez dostępnych portfeli.",
                    buttons=[
                        [Button.inline("🔙 Wybierz asset", f"tx:select_exchange:{exchange_id}".encode())],
                        [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
                    ]
                )
                return
            
            type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
            type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
            exchange_name = exchange.get('display_name') or exchange['name']
            asset_symbol = f"{asset['asset']}/{asset['quote']}"
            
            wizard_text = (
                f"🧙‍♂️ **Kreator Nowej Transakcji**\n\n"
                f"📋 **Krok 4/5: Wybór portfela**\n\n"
                f"✅ **Typ:** {type_emoji} {type_name}\n"
                f"✅ **Giełda:** 🏦 {exchange_name}\n"
                f"✅ **Asset:** 💎 {asset_symbol}\n\n"
                f"Wybierz portfel z którego/do którego wykonasz transakcję:"
            )
            
            buttons = []
            for wallet in wallets[:10]:  # Limit 10 portfeli
                balance = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
                wallet_info = f"{wallet['currency']} {wallet['type'][:6]} ({balance})"
                
                buttons.append([Button.inline(
                    f"💰 {wallet_info}",
                    f"tx:select_wallet:{wallet['id']}".encode()
                )])
            
            buttons.extend([
                [Button.inline("🔙 Wybierz asset", f"tx:select_exchange:{exchange_id}".encode())],
                [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
            ])
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_wallet_selection")
            await event.edit(error_msg)
    
    @RD.cb(b"tx:select_wallet:")
    async def select_wallet_callback(self, event):
        """Handler wyboru portfela w wizardzie."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            await event.answer("❌ Sesja wizarda wygasła", alert=True)
            return
        
        try:
            # Extract wallet ID
            callback_data = event.data.decode()
            wallet_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            account_state_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Pobierz portfel
            wallet = await account_state_table.get_by_id(wallet_id)
            if not wallet:
                await event.answer("❌ Portfel nie znaleziony", alert=True)
                return
            
            # Aktualizuj wizard state
            wizard_state = self.transaction_wizards[user.id]
            wizard_state['data']['wallet_id'] = wallet_id
            wizard_state['data']['wallet'] = wallet
            wizard_state['step'] = "select_strategy"
            
            # Przejdź do wyboru strategii (opcjonalne)
            await self._show_strategy_selection(event, user, wizard_state)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_wallet_selection")
            await event.edit(error_msg)
    
    async def _show_strategy_selection(self, event, user, wizard_state: Dict[str, Any]):
        """Pokazuje opcjonalny wybór strategii."""
        try:
            wallet_id = wizard_state['data']['wallet_id']
            wallet = wizard_state['data']['wallet']
            transaction_type = wizard_state['data']['type']
            asset = wizard_state['data']['asset']
            exchange = wizard_state['data']['exchange']
            
            await self.init_database()
            
            # Pobierz strategie dla tego portfela
            strategies = []
            if transaction_type == "BUY":
                buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
                strategies = await buy_strategies_table.get_by_exchange_account_state_id(wallet_id, limit=20)
                strategy_type = "buy"
            else:
                sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
                strategies = await sell_strategies_table.get_by_exchange_account_state_id(wallet_id, limit=20)
                strategy_type = "sell"
            
            type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
            type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
            exchange_name = exchange.get('display_name') or exchange['name']
            asset_symbol = f"{asset['asset']}/{asset['quote']}"
            wallet_balance = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
            wallet_info = f"{wallet['currency']} {wallet['type']} ({wallet_balance})"
            
            wizard_text = (
                f"🧙‍♂️ **Kreator Nowej Transakcji**\n\n"
                f"📋 **Krok 5/5: Strategia (opcjonalne)**\n\n"
                f"✅ **Typ:** {type_emoji} {type_name}\n"
                f"✅ **Giełda:** 🏦 {exchange_name}\n"
                f"✅ **Asset:** 💎 {asset_symbol}\n"
                f"✅ **Portfel:** 💰 {wallet_info}\n\n"
                f"Możesz wybrać strategię lub wykonać transakcję ręcznie:"
            )
            
            buttons = []
            
            # Dodaj przycisk dla transakcji ręcznej
            buttons.append([Button.inline("📝 Transakcja ręczna", b"tx:manual_transaction")])
            
            # Dodaj strategie jeśli są dostępne
            if strategies:
                wizard_text += f"\n\n**Dostępne strategie ({len(strategies)}):**"
                
                for strategy in strategies[:8]:  # Limit 8 strategii
                    amount_type = "%" if strategy['is_percent'] else strategy.get('currency', wallet['currency'])
                    strategy_desc = f"{strategy['type']} {strategy['movement_amount']} {amount_type}"
                    
                    buttons.append([Button.inline(
                        f"📊 {strategy_desc}",
                        f"tx:select_strategy:{strategy_type}:{strategy['id']}".encode()
                    )])
            
            buttons.extend([
                [Button.inline("🔙 Wybierz portfel", f"tx:select_exchange:{exchange['id']}".encode())],
                [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
            ])
            
            await event.edit(wizard_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_strategy_selection")
            await event.edit(error_msg)
    
    # ===================
    # TRANSACTION WIZARD - FINAL STEPS AND EXECUTION
    # ===================
    
    @RD.cb(b"tx:select_strategy:")
    async def select_strategy_callback(self, event):
        """Handler wyboru strategii w wizardzie."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            await event.answer("❌ Sesja wizarda wygasła", alert=True)
            return
        
        try:
            # Parse callback data: tx:select_strategy:strategy_type:strategy_id
            callback_data = event.data.decode()
            parts = callback_data.split(":")
            strategy_type = parts[2]  # "buy" or "sell"
            strategy_id = int(parts[3])
            
            # Aktualizuj wizard state
            wizard_state = self.transaction_wizards[user.id]
            wizard_state['data']['strategy_type'] = strategy_type
            wizard_state['data']['strategy_id'] = strategy_id
            wizard_state['step'] = "confirm"
            
            # Przejdź do potwierdzenia
            await self._show_transaction_confirmation(event, user, wizard_state)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_strategy_selection")
            await event.edit(error_msg)
    
    @RD.cb(b"tx:manual_transaction")
    async def manual_transaction_callback(self, event):
        """Handler dla transakcji ręcznej (bez strategii)."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            await event.answer("❌ Sesja wizarda wygasła", alert=True)
            return
        
        try:
            # Aktualizuj wizard state
            wizard_state = self.transaction_wizards[user.id]
            wizard_state['data']['strategy_type'] = None
            wizard_state['data']['strategy_id'] = None
            wizard_state['step'] = "manual_amount"
            
            # Pokaż formularz wprowadzania kwoty
            await self._show_manual_amount_input(event, user, wizard_state)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_manual_transaction")
            await event.edit(error_msg)
    
    async def _show_manual_amount_input(self, event, user, wizard_state: Dict[str, Any]):
        """Pokazuje formularz wprowadzania kwoty dla transakcji ręcznej."""
        transaction_type = wizard_state['data']['type']
        asset = wizard_state['data']['asset']
        exchange = wizard_state['data']['exchange']
        wallet = wizard_state['data']['wallet']
        
        type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
        type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
        exchange_name = exchange.get('display_name') or exchange['name']
        asset_symbol = f"{asset['asset']}/{asset['quote']}"
        wallet_balance = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
        wallet_info = f"{wallet['currency']} {wallet['type']} ({wallet_balance})"
        
        wizard_text = (
            f"🧙‍♂️ **Kreator Nowej Transakcji**\n\n"
            f"📋 **Krok 5/5: Kwota transakcji**\n\n"
            f"✅ **Typ:** {type_emoji} {type_name}\n"
            f"✅ **Giełda:** 🏦 {exchange_name}\n"
            f"✅ **Asset:** 💎 {asset_symbol}\n"
            f"✅ **Portfel:** 💰 {wallet_info}\n"
            f"✅ **Strategia:** 📝 Ręczna\n\n"
            f"**Wyślij kwotę transakcji jako następną wiadomość:**\n\n"
        )
        
        if transaction_type == "BUY":
            wizard_text += (
                f"**Format dla KUPNA:**\n"
                f"• `100` - kwota w {asset['quote']} (bezwzględna)\n"
                f"• `50%` - procent salda portfela\n"
                f"• `MARKET 75%` - typ zlecenia + procent\n"
                f"• `LIMIT 200` - typ zlecenia + kwota\n\n"
                f"**Dostępne:** {wallet_balance} {wallet['currency']}"
            )
        else:
            wizard_text += (
                f"**Format dla SPRZEDAŻY:**\n"
                f"• `0.5` - kwota w {asset['asset']} (bezwzględna)\n"
                f"• `25%` - procent salda portfela\n"
                f"• `MARKET 50%` - typ zlecenia + procent\n"
                f"• `LIMIT 0.1` - typ zlecenia + kwota\n\n"
                f"**Dostępne:** {wallet_balance} {wallet['currency']}"
            )
        
        buttons = [
            [Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")]
        ]
        
        await event.edit(wizard_text, buttons=buttons)
        
        # Ustaw stan oczekiwania na input
        wizard_state['step'] = "waiting_manual_input"
    
    async def _show_transaction_confirmation(self, event, user, wizard_state: Dict[str, Any], manual_params: Optional[Dict] = None):
        """Pokazuje potwierdzenie transakcji przed wykonaniem."""
        try:
            transaction_type = wizard_state['data']['type']
            asset = wizard_state['data']['asset']
            exchange = wizard_state['data']['exchange']
            wallet = wizard_state['data']['wallet']
            
            type_emoji = "🟢" if transaction_type == "BUY" else "🔴"
            type_name = "KUPNO" if transaction_type == "BUY" else "SPRZEDAŻ"
            exchange_name = exchange.get('display_name') or exchange['name']
            asset_symbol = f"{asset['asset']}/{asset['quote']}"
            wallet_balance = TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])
            wallet_info = f"{wallet['currency']} {wallet['type']} ({wallet_balance})"
            
            confirmation_text = (
                f"❓ **Potwierdzenie transakcji**\n\n"
                f"🔄 **Typ:** {type_emoji} {type_name}\n"
                f"🏦 **Giełda:** {exchange_name}\n"
                f"💎 **Asset:** {asset_symbol}\n"
                f"💰 **Portfel:** {wallet_info}\n"
            )
            
            # Dodaj informacje o strategii lub manual params
            if manual_params:
                order_type = manual_params.get('order_type', 'MARKET')
                amount = manual_params['amount']
                is_percent = manual_params['is_percent']
                amount_display = f"{amount}%" if is_percent else f"{amount}"
                
                confirmation_text += f"📝 **Typ zlecenia:** {order_type}\n"
                confirmation_text += f"💸 **Kwota:** {amount_display}\n"
                
                # Oblicz rzeczywistą kwotę dla procentów
                if is_percent:
                    real_amount = (float(wallet['amount']) * amount) / 100
                    real_amount_display = TelegramUIUtils.format_currency(real_amount, wallet['currency'])
                    confirmation_text += f"💰 **Rzeczywista kwota:** {real_amount_display}\n"
                
                # Zapisz w wizard state
                wizard_state['data']['manual_params'] = manual_params
                
            elif wizard_state['data'].get('strategy_id'):
                strategy_type = wizard_state['data']['strategy_type']
                confirmation_text += f"📊 **Strategia:** {strategy_type} #{wizard_state['data']['strategy_id']}\n"
            
            confirmation_text += (
                f"\n⚠️ **UWAGA:** Ta transakcja zostanie wykonana natychmiast na giełdzie!\n"
                f"❓ Czy na pewno chcesz kontynuować?"
            )
            
            # Utwórz hash parametrów dla bezpieczeństwa
            params_hash = self._create_transaction_params_hash(wizard_state['data'])
            
            buttons = [
                [
                    Button.inline("✅ WYKONAJ TRANSAKCJĘ", f"tx:confirm:{params_hash}".encode()),
                    Button.inline("❌ Anuluj", b"tx:create_wizard:cancel")
                ]
            ]
            
            await event.edit(confirmation_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "wizard_confirmation")
            await event.edit(error_msg)
    
    def _create_transaction_params_hash(self, data: Dict[str, Any]) -> str:
        """Tworzy hash parametrów transakcji dla bezpieczeństwa."""
        import hashlib
        import json
        
        # Wybierz tylko kluczowe parametry
        key_params = {
            'type': data['type'],
            'exchange_id': data['exchange_id'],
            'asset_id': data['asset_id'],
            'wallet_id': data['wallet_id'],
            'strategy_id': data.get('strategy_id'),
            'manual_params': data.get('manual_params'),
            'timestamp': self._get_current_timestamp()
        }
        
        params_str = json.dumps(key_params, sort_keys=True)
        return hashlib.md5(params_str.encode()).hexdigest()[:8]
    
    # ===================
    # MESSAGE HANDLER FOR WIZARD INPUT
    # ===================
    
    @RD.msg(r".*")
    async def process_wizard_input(self, event):
        """Przetwarza input użytkownika w trakcie wizarda transakcji."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            return
        
        wizard_state = self.transaction_wizards[user.id]
        
        if wizard_state['step'] == 'waiting_manual_input':
            await self._process_manual_transaction_input(event, user, wizard_state)
    
    async def _process_manual_transaction_input(self, event, user, wizard_state):
        """Przetwarza input dla transakcji ręcznej."""
        try:
            message_text = event.raw_text.strip().upper()
            transaction_type = wizard_state['data']['type']
            wallet = wizard_state['data']['wallet']
            
            # Parse input - może zawierać typ zlecenia
            parts = message_text.split()
            order_type = "MARKET"  # Domyślny
            amount_str = message_text
            
            # Sprawdź czy input zawiera typ zlecenia
            if len(parts) >= 2 and parts[0] in ["MARKET", "LIMIT"]:
                order_type = parts[0]
                amount_str = parts[1]
            
            # Parse kwoty
            is_percent = amount_str.endswith('%')
            if is_percent:
                try:
                    amount_value = float(amount_str[:-1])
                    if amount_value <= 0 or amount_value > 100:
                        await event.respond("❌ **Procent musi być między 1-100%**")
                        return
                except ValueError:
                    await event.respond("❌ **Nieprawidłowy format procentu**")
                    return
            else:
                try:
                    amount_value = float(amount_str)
                    if amount_value <= 0:
                        await event.respond("❌ **Kwota musi być większa niż 0**")
                        return
                    
                    # Sprawdź czy nie przekracza salda portfela
                    if amount_value > float(wallet['amount']):
                        await event.respond(
                            f"❌ **Kwota przekracza saldo portfela**\n\n"
                            f"Dostępne: {TelegramUIUtils.format_currency(float(wallet['amount']), wallet['currency'])}"
                        )
                        return
                        
                except ValueError:
                    await event.respond("❌ **Nieprawidłowa kwota**")
                    return
            
            # Przygotuj parametry manual
            manual_params = {
                'order_type': order_type,
                'amount': amount_value,
                'is_percent': is_percent
            }
            
            # Przejdź do potwierdzenia
            await self._show_transaction_confirmation(event, user, wizard_state, manual_params)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "manual_input_processing")
            await event.respond(error_msg)
    
    # ===================
    # TRANSACTION EXECUTION
    # ===================
    
    @RD.cb(b"tx:confirm:")
    async def confirm_transaction_callback(self, event):
        """Wykonuje potwierdzoną transakcję."""
        user = await self.get_user_info(event)
        if not user or user.id not in self.transaction_wizards:
            await event.answer("❌ Sesja wizarda wygasła", alert=True)
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.TRADER):
            await event.answer("🔒 Brak uprawnień do wykonania transakcji!", alert=True)
            return
        
        try:
            # Extract params hash
            callback_data = event.data.decode()
            params_hash = callback_data.split(":")[-1]
            
            wizard_state = self.transaction_wizards[user.id]
            
            # Walidacja hash (dla bezpieczeństwa)
            expected_hash = self._create_transaction_params_hash(wizard_state['data'])
            if params_hash != expected_hash:
                await event.edit("❌ **Błąd bezpieczeństwa**\n\nParametry transakcji zostały zmodyfikowane.")
                return
            
            # Wyświetl loading message
            loading_msg = self.create_loading_message("transakcję")
            await event.edit(loading_msg)
            
            # Wykonaj transakcję
            result = await self._execute_transaction_from_wizard(wizard_state['data'])
            
            # Usuń wizard state
            del self.transaction_wizards[user.id]
            
            if result and result.get('success'):
                transaction_id = result.get('transaction_id')
                success_msg = self.create_success_message(
                    "Wykonanie transakcji",
                    f"✅ Transakcja została wykonana pomyślnie!\n"
                    f"🆔 ID transakcji: {transaction_id}\n"
                    f"💸 Typ: {wizard_state['data']['type']}\n"
                    f"🏦 Giełda: {wizard_state['data']['exchange']['name']}"
                )
                
                buttons = [
                    [Button.inline("📊 Zobacz szczegóły", f"tx:details:{transaction_id}".encode())],
                    [Button.inline("💸 Lista transakcji", b"tx:page:1")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ]
                
                await event.edit(success_msg, buttons=buttons)
                await self.log_action(user.id, "transaction_executed", {
                    "transaction_id": transaction_id,
                    "type": wizard_state['data']['type'],
                    "exchange_id": wizard_state['data']['exchange_id'],
                    "asset_id": wizard_state['data']['asset_id']
                })
            else:
                error_msg = result.get('error', 'Nieznany błąd') if result else 'Brak odpowiedzi z systemu'
                await event.edit(
                    f"❌ **Błąd wykonania transakcji**\n\n{error_msg}",
                    buttons=[
                        [Button.inline("🔄 Spróbuj ponownie", b"tx:create_wizard:start")],
                        [Button.inline("💸 Lista transakcji", b"tx:page:1")]
                    ]
                )
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "transaction_execution")
            await event.edit(error_msg)
    
    async def _execute_transaction_from_wizard(self, wizard_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Wykonuje transakcję na podstawie danych z wizarda.
        
        Args:
            wizard_data: Dane z wizarda transakcji
            
        Returns:
            Dict z wynikami transakcji lub None w przypadku błędu
        """
        try:
            transaction_type = wizard_data['type']
            exchange_id = wizard_data['exchange_id']
            asset_id = wizard_data['asset_id']
            wallet_id = wizard_data['wallet_id']
            manual_params = wizard_data.get('manual_params')
            strategy_id = wizard_data.get('strategy_id')
            strategy_type = wizard_data.get('strategy_type')
            
            await self.init_database()
            
            # Pobierz potrzebne dane
            exchanges_table = self.db.get_factory().get_exchanges_table()
            assets_table = self.db.get_factory().get_assets_table()
            account_state_table = self.db.get_factory().get_exchange_account_state_table()
            transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            exchange = await exchanges_table.get_by_id(exchange_id)
            asset = await assets_table.get_by_id(asset_id)
            wallet = await account_state_table.get_by_id(wallet_id)
            
            if not exchange or not asset or not wallet:
                return {"success": False, "error": "Nie można znaleźć danych giełdy, assetu lub portfela"}
            
            # Przygotuj parametry transakcji
            if manual_params:
                # Transakcja ręczna
                order_type = manual_params['order_type']
                amount = manual_params['amount']
                is_percent = manual_params['is_percent']
                
                # Oblicz rzeczywistą kwotę
                if is_percent:
                    transaction_amount = (float(wallet['amount']) * amount) / 100
                else:
                    transaction_amount = amount
                
                # Symulacja wykonania transakcji (w produkcji używaj sync_transactions)
                # TODO: Integrate with actual exchange API via sync_transactions
                
                # Mock execution for now
                quote_amount = transaction_amount
                asset_amount = transaction_amount / 100  # Mock price
                
                # Zapisz transakcję w bazie
                transaction_id = await transactions_table.create(
                    exchange_id=exchange_id,
                    asset_id=asset_id,
                    exchange_account_state_id=wallet_id,
                    type=transaction_type,
                    quote_amount=quote_amount,
                    asset_amount=asset_amount,
                    buy_strategy_id=strategy_id if transaction_type == 'BUY' and strategy_type == 'buy' else None,
                    sell_strategy_id=strategy_id if transaction_type == 'SELL' and strategy_type == 'sell' else None
                )
                
                return {
                    "success": True,
                    "transaction_id": transaction_id,
                    "quote_amount": quote_amount,
                    "asset_amount": asset_amount
                }
                
            elif strategy_id:
                # Transakcja ze strategią
                if strategy_type == 'buy':
                    buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
                    strategy = await buy_strategies_table.get_by_id(strategy_id)
                else:
                    sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
                    strategy = await sell_strategies_table.get_by_id(strategy_id)
                
                if not strategy:
                    return {"success": False, "error": "Nie można znaleźć strategii"}
                
                # Użyj sync_transactions do wykonania transakcji ze strategią
                # TODO: Implement strategy-based execution
                
                # Mock execution for now
                movement_amount = strategy['movement_amount']
                is_percent = strategy['is_percent']
                
                if is_percent:
                    transaction_amount = (float(wallet['amount']) * movement_amount) / 100
                else:
                    transaction_amount = movement_amount
                
                quote_amount = transaction_amount
                asset_amount = transaction_amount / 100  # Mock price
                
                transaction_id = await transactions_table.create(
                    exchange_id=exchange_id,
                    asset_id=asset_id,
                    exchange_account_state_id=wallet_id,
                    type=transaction_type,
                    quote_amount=quote_amount,
                    asset_amount=asset_amount,
                    buy_strategy_id=strategy_id if transaction_type == 'BUY' else None,
                    sell_strategy_id=strategy_id if transaction_type == 'SELL' else None
                )
                
                return {
                    "success": True,
                    "transaction_id": transaction_id,
                    "quote_amount": quote_amount,
                    "asset_amount": asset_amount
                }
            
            return {"success": False, "error": "Brak parametrów transakcji"}
            
        except Exception as e:
            logger.error(f"Error executing transaction from wizard: {e}")
            return {"success": False, "error": str(e)}
    
    # ===================
    # UTILITY METHODS
    # ===================
    
    def format_transaction_info(self, transaction: Dict[str, Any]) -> str:
        """
        Formatuje szczegółowe informacje o transakcji.
        
        Args:
            transaction: Słownik z danymi transakcji
            
        Returns:
            str: Sformatowane informacje o transakcji
        """
        tx_type_emoji = "🟢" if transaction['type'] == 'BUY' else "🔴"
        exchange_name = transaction.get('exchange_display_name') or transaction['exchange_name']
        asset_symbol = f"{transaction['asset']}/{transaction['quote']}"
        
        response = f"{tx_type_emoji} **Transakcja: {transaction['type']} {asset_symbol}**\n\n"
        response += f"🏦 **Giełda:** {exchange_name}\n"
        response += f"💎 **Asset:** {transaction['asset']}\n"
        response += f"💰 **Quote:** {transaction['quote']}\n"
        
        # Formatuj kwoty
        quote_amount = TelegramUIUtils.format_currency(
            float(transaction['quote_amount']), transaction['quote']
        )
        asset_amount = f"{float(transaction['asset_amount']):.8f} {transaction['asset']}"
        
        response += f"💸 **Kwota Quote:** {quote_amount}\n"
        response += f"💎 **Kwota Asset:** {asset_amount}\n"
        
        # Informacje o portfelu
        wallet_balance = TelegramUIUtils.format_currency(
            float(transaction['account_amount']), transaction['currency']
        )
        response += f"💰 **Portfel:** {transaction['currency']} {transaction['account_type']} ({wallet_balance})\n"
        
        # Informacje o strategii
        if transaction.get('buy_strategy_type') or transaction.get('sell_strategy_type'):
            strategy_type = transaction.get('buy_strategy_type') or transaction.get('sell_strategy_type')
            strategy_amount = transaction.get('buy_movement_amount') or transaction.get('sell_movement_amount')
            strategy_is_percent = transaction.get('buy_is_percent') or transaction.get('sell_is_percent')
            amount_type = "%" if strategy_is_percent else transaction['currency']
            
            response += f"📊 **Strategia:** {strategy_type} {strategy_amount} {amount_type}\n"
        
        # Informacje o interpretacji
        if transaction.get('interpretation_title'):
            response += f"🧠 **Interpretacja:** {transaction['interpretation_title']}\n"
        else:
            response += f"⚠️ **Interpretacja:** Brak\n"
        
        # Czas transakcji
        tx_time = self._format_datetime_from_timestamp(transaction['created_at'])
        response += f"⏰ **Czas:** {tx_time}\n"
        
        response += f"🆔 **Database ID:** `{transaction['id']}`\n"
        
        return response
    
    def _format_datetime_from_timestamp(self, timestamp: int) -> str:
        """Formatuje timestamp (ms) na czytelną datę."""
        try:
            dt = datetime.fromtimestamp(timestamp / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return "N/A"
    
    def _get_current_timestamp(self) -> int:
        """Zwraca aktualny timestamp w milisekundach."""
        return int(datetime.now().timestamp() * 1000)
