"""
Klasa abstrakcyjna dla kontrolerów Telegram z wspólnymi funkcjonalnościami.

Ta klasa zawiera:
- Formatowanie tabelaryczne wyników
- System paginacji
- Walidację uprawnień 
- Obsługę błędów bazy danych
- Utilities dla UX/UI
- Logowanie akcji użytkowników

Autor: AI Assistant
"""

import logging
import traceback
import hashlib
import json
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime
from telethon import Button
from telethon.tl.types import User

from .controller_telegram_utils_router import DomainBase, RD
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


# Usunięto system uprawnień użytkowników


class BaseTelegramControllerDomain(DomainBase, ABC):
    """
    Abstrakcyjna klasa bazowa dla wszystkich kontrolerów Telegram.
    
    Zapewnia wspólne funkcjonalności:
    - Formatowanie tabelaryczne
    - Paginacja
    - Permissions management
    - Error handling
    - Database integration
    - User action logging
    """
    
    def __init__(self, test_mode: bool = False, **kwargs):
        """
        Inicjalizacja klasy bazowej.
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
            **kwargs: Dodatkowe parametry konfiguracyjne
        """
        super().__init__(**kwargs)
        self.test_mode = test_mode
        
        # Inicjalizacja bazy danych
        try:
            if not self.test_mode:
                self.db = DatabaseFacade().get_database_postgresql()
            else:
                self.db = DatabaseFacade().get_test_database_postgresql()
        except Exception as e:
            self.logger.error(f"Błąd inicjalizacji bazy danych: {e}")
            self.db = None

        # Statistyki domeny
        self.stats = {
            "actions_count": 0,
            "errors_count": 0,
            "commands_executed": {},
            "callbacks_handled": {}
        }
    
    async def init_database(self) -> bool:
        """
        Inicjalizuje połączenie z bazą danych.
        
        Returns:
            bool: True jeśli inicjalizacja się udała
        """
        try:
            if self.db and not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
                return True
            return True
        except Exception as e:
            self.logger.error(f"Błąd inicjalizacji bazy danych: {e}")
            return False
    
    # ===================
    # SIMPLIFIED PERMISSIONS (no database)
    # ===================
    
    async def validate_permissions(self, user_id: int, required_level: str) -> bool:
        """
        Sprawdza czy użytkownik ma wymagany poziom uprawnień.
        Uproszczona wersja - zawsze zwraca True (brak systemu uprawnień).
        
        Args:
            user_id: ID użytkownika (ignorowany)
            required_level: Wymagany poziom uprawnień (ignorowany)
            
        Returns:
            bool: Zawsze True
        """
        return True
    
    def is_admin(self, user_id: int) -> bool:
        """Sprawdza czy użytkownik jest administratorem - zawsze True."""
        return True
    
    # ===================
    # FORMATTING SYSTEM
    # ===================
    
    def format_table_response(self, data: List[Dict[str, Any]], 
                            headers: List[str], 
                            title: str = "",
                            max_rows: int = 10) -> str:
        """
        Formatuje dane w formie tabelarycznej dla Telegram.
        
        Args:
            data: Lista słowników z danymi
            headers: Lista nagłówków kolumn
            title: Tytuł tabeli
            max_rows: Maksymalna liczba wierszy do wyświetlenia
            
        Returns:
            str: Sformatowana tabela
        """
        if not data:
            return f"📊 **{title}**\n\n❌ Brak danych do wyświetlenia."
        
        response = ""
        if title:
            response += f"📊 **{title}**\n\n"
        
        # Ograniczenie liczby wierszy
        display_data = data[:max_rows]
        
        # Formatowanie tabeli
        response += "```\n"
        
        # Nagłówki
        header_line = " | ".join([h.ljust(12)[:12] for h in headers])
        response += f"{header_line}\n"
        response += "-" * len(header_line) + "\n"
        
        # Wiersze danych
        for row in display_data:
            row_values = []
            for header in headers:
                value = str(row.get(header, "")).ljust(12)[:12]
                row_values.append(value)
            response += " | ".join(row_values) + "\n"
        
        response += "```\n"
        
        # Informacja o obcięciu
        if len(data) > max_rows:
            response += f"\n📄 Wyświetlono {max_rows} z {len(data)} rekordów.\n"
        
        return response
    
    def format_pagination_buttons(self, current_page: int, total_pages: int, 
                                prefix: str, data_params: str = "") -> List[List[Button]]:
        """
        Tworzy przyciski paginacji.
        
        Args:
            current_page: Aktualna strona (1-based)
            total_pages: Całkowita liczba stron
            prefix: Prefix dla callback data
            data_params: Dodatkowe parametry do przekazania
            
        Returns:
            List[List[Button]]: Lista wierszy przycisków
        """
        if total_pages <= 1:
            return []
        
        buttons = []
        nav_row = []
        
        # Przycisk Previous
        if current_page > 1:
            prev_data = f"{prefix}:page:{current_page-1}"
            if data_params:
                prev_data += f":{data_params}"
            nav_row.append(Button.inline("◀️ Wstecz", prev_data.encode()))
        
        # Informacja o stronie
        page_info = f"📄 {current_page}/{total_pages}"
        nav_row.append(Button.inline(page_info, f"{prefix}:page_info".encode()))
        
        # Przycisk Next
        if current_page < total_pages:
            next_data = f"{prefix}:page:{current_page+1}"
            if data_params:
                next_data += f":{data_params}"
            nav_row.append(Button.inline("Dalej ▶️", next_data.encode()))
        
        buttons.append(nav_row)
        
        # Jump to page (tylko jeśli więcej niż 3 strony)
        if total_pages > 3:
            jump_row = [Button.inline("🔢 Idź do strony...", f"{prefix}:jump".encode())]
            buttons.append(jump_row)
        
        return buttons
    
    def format_asset_info(self, asset: Dict[str, Any]) -> str:
        """
        Formatuje informacje o assecie.
        
        Args:
            asset: Słownik z danymi assetu
            
        Returns:
            str: Sformatowane informacje o assecie
        """
        response = f"💎 **Asset: {asset.get('asset', 'N/A')}**\n\n"
        response += f"🔤 **Symbol:** `{asset.get('asset', 'N/A')}/{asset.get('quote', 'N/A')}`\n"
        response += f"🆔 **ID:** `{asset.get('id', 'N/A')}`\n"
        response += f"📅 **Utworzony:** {self._format_datetime(asset.get('created_at'))}\n"
        
        if 'last_price' in asset:
            response += f"💰 **Ostatnia cena:** `${asset.get('last_price', 'N/A')}`\n"
        
        return response
    
    def format_exchange_info(self, exchange: Dict[str, Any]) -> str:
        """
        Formatuje informacje o giełdzie.
        
        Args:
            exchange: Słownik z danymi giełdy
            
        Returns:
            str: Sformatowane informacje o giełdzie
        """
        status_emoji = "🟢" if exchange.get('is_active') else "🔴"
        
        response = f"🏦 **Giełda: {exchange.get('display_name', 'N/A')}**\n\n"
        response += f"🔤 **Nazwa:** `{exchange.get('name', 'N/A')}`\n"
        response += f"🆔 **ID:** `{exchange.get('id', 'N/A')}`\n"
        response += f"{status_emoji} **Status:** {'Aktywna' if exchange.get('is_active') else 'Nieaktywna'}\n"
        response += f"📅 **Utworzona:** {self._format_datetime(exchange.get('created_at'))}\n"
        
        return response
    
    def _format_datetime(self, dt) -> str:
        """Formatuje datetime dla wyświetlenia."""
        if not dt:
            return "N/A"
        
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except:
                return str(dt)
        
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # ===================
    # RESPONSE UTILITIES
    # ===================
    
    async def send_paginated_response(self, event, data: List[Dict[str, Any]], 
                                    headers: List[str], title: str,
                                    page: int = 1, page_size: int = 10,
                                    callback_prefix: str = "data",
                                    additional_buttons: Optional[List[List[Button]]] = None) -> None:
        """
        Wysyła odpowiedź z paginacją.
        
        Args:
            event: Event Telegram
            data: Dane do wyświetlenia
            headers: Nagłówki tabeli
            title: Tytuł
            page: Numer strony (1-based)
            page_size: Rozmiar strony
            callback_prefix: Prefix dla callbacks paginacji
            additional_buttons: Dodatkowe przyciski
        """
        if not data:
            await event.respond(f"📊 **{title}**\n\n❌ Brak danych do wyświetlenia.")
            return
        
        # Oblicz paginację
        total_items = len(data)
        total_pages = (total_items + page_size - 1) // page_size
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_data = data[start_idx:end_idx]
        
        # Sformatuj odpowiedź
        response = self.format_table_response(
            page_data, headers, title, max_rows=page_size
        )
        
        # Dodaj informacje o paginacji
        if total_pages > 1:
            response += f"\n📄 Strona {page} z {total_pages} ({total_items} rekordów total)\n"
        
        # Przygotuj przyciski
        buttons = []
        
        # Przyciski paginacji
        pagination_buttons = self.format_pagination_buttons(
            page, total_pages, callback_prefix
        )
        buttons.extend(pagination_buttons)
        
        # Dodatkowe przyciski
        if additional_buttons:
            buttons.extend(additional_buttons)
        
        # Wyślij odpowiedź
        if hasattr(event, 'edit'):
            await event.edit(response, buttons=buttons)
        else:
            await event.respond(response, buttons=buttons)
    
    def create_confirmation_callback(self, action: str, item_id: Any, 
                                   additional_data: str = "") -> str:
        """
        Tworzy callback dla potwierdzenia akcji.
        
        Args:
            action: Nazwa akcji
            item_id: ID elementu
            additional_data: Dodatkowe dane
            
        Returns:
            str: Callback string
        """
        callback = f"confirm:{action}:{item_id}"
        if additional_data:
            callback += f":{additional_data}"
        return callback
    
    # ===================
    # ERROR HANDLING
    # ===================
    
    async def handle_database_error(self, error: Exception, user_id: int, 
                                  action: str) -> str:
        """
        Obsługuje błędy bazy danych w user-friendly sposób.
        
        Args:
            error: Wyjątek bazy danych
            user_id: ID użytkownika
            action: Akcja która spowodowała błąd
            
        Returns:
            str: User-friendly komunikat błędu
        """
        self.stats["errors_count"] += 1
        
        error_message = str(error).lower()
        
        # Określ typ błędu
        if "connection" in error_message or "timeout" in error_message:
            user_message = "🔌 **Błąd połączenia z bazą danych**\n\n"
            user_message += "Spróbuj ponownie za chwilę. Jeśli problem się powtarza, "
            user_message += "skontaktuj się z administratorem."
        elif "duplicate" in error_message or "unique" in error_message:
            user_message = "⚠️ **Duplikat danych**\n\n"
            user_message += "Ten element już istnieje w systemie."
        elif "not found" in error_message:
            user_message = "🔍 **Nie znaleziono**\n\n"
            user_message += "Szukany element nie istnieje lub został usunięty."
        elif "permission" in error_message or "access" in error_message:
            user_message = "🔒 **Brak uprawnień**\n\n"
            user_message += "Nie masz uprawnień do wykonania tej operacji."
        else:
            user_message = "❌ **Wystąpił błąd bazy danych**\n\n"
            user_message += "Spróbuj ponownie. Jeśli problem się powtarza, "
            user_message += "skontaktuj się z administratorem."
        
        # Loguj szczegółowy błąd
        self.logger.error(
            f"Database error for user {user_id} during action '{action}': {error}",
            exc_info=True
        )
        
        return user_message
    
    # ===================
    # LOGGING SYSTEM
    # ===================
    
    async def log_action(self, user_id: int, action: str, details: Dict[str, Any] = None) -> None:
        """
        Loguje akcję użytkownika.
        
        Args:
            user_id: ID użytkownika
            action: Nazwa akcji
            details: Szczegóły akcji
        """
        self.stats["actions_count"] += 1
        self.stats["users_interacted"].add(user_id)
        
        # Zlicz akcję
        if action in self.stats["commands_executed"]:
            self.stats["commands_executed"][action] += 1
        else:
            self.stats["commands_executed"][action] = 1
        
        # Log do pliku
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "domain": self.get_domain_name(),
            "user_id": user_id,
            "action": action,
            "details": details or {}
        }
        
        self.logger.info(f"User action: {json.dumps(log_entry, default=str)}")
        
        # Opcjonalnie zapisz do bazy danych
        try:
            if self.db:
                users_table = self.db.get_factory().get_users_table()
                await users_table.log_action(user_id, action, details)
        except Exception as e:
            self.logger.warning(f"Nie udało się zapisać logu akcji do bazy danych: {e}")
    
    # ===================
    # UI UTILITIES
    # ===================
    
    def create_loading_message(self, action: str) -> str:
        """Tworzy wiadomość loading."""
        return f"🔄 **Ładuję {action}...**\n\nProszę czekać..."
    
    def create_success_message(self, action: str, details: str = "") -> str:
        """Tworzy wiadomość sukcesu."""
        message = f"✅ **{action} zakończone pomyślnie!**"
        if details:
            message += f"\n\n{details}"
        return message
    
    def create_error_message(self, action: str, error: str = "") -> str:
        """Tworzy wiadomość błędu."""
        message = f"❌ **Błąd podczas {action}**"
        if error:
            message += f"\n\n{error}"
        return message
    
    # ===================
    # ABSTRACT METHODS
    # ===================
    
    @abstractmethod
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """
        Zwraca statystyki specyficzne dla domeny.
        
        Returns:
            Dict[str, Any]: Statystyki domeny
        """
        pass
    
    # ===================
    # HOOKS OVERRIDE
    # ===================
    
    async def before_handle(self, event) -> bool:
        """Hook wykonywany przed każdym handlerem."""
        try:
            user = await self.get_user_info(event)
            if user:
                # Sprawdź podstawowe uprawnienia
                if not await self.is_user_allowed(user.id):
                    await event.respond("🔒 **Brak uprawnień**\n\nNie masz dostępu do tej funkcji.")
                    return False
                
                self.logger.debug(f"User {user.first_name} ({user.id}) wykonuje akcję w domenie {self.get_domain_name()}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Błąd w before_handle: {e}")
            return False
    
    async def after_handle(self, event, result: Optional[Any] = None, error: Optional[Exception] = None) -> None:
        """Hook wykonywany po każdym handlerze."""
        try:
            user = await self.get_user_info(event)
            if user and hasattr(event, 'raw_text'):
                action = event.raw_text[:50]  # Pierwsze 50 znaków jako akcja
                await self.log_action(user.id, action, {"result": bool(result), "error": str(error) if error else None})
            
            if error:
                self.logger.error(f"Błąd w domenie {self.get_domain_name()}: {error}")
            else:
                self.logger.debug(f"Akcja w domenie {self.get_domain_name()} wykonana pomyślnie")
                
        except Exception as e:
            self.logger.error(f"Błąd w after_handle: {e}")
