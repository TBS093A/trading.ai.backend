"""
Utilities dla UX/UI w Telegram botach.

Zawiera:
- Formatowanie wiadomości i tabel
- Progress bars i loading animations
- Interactive wizards  
- Confirmation dialogs
- Data validation
- UI components

Autor: AI Assistant
"""

import re
import hashlib
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime, timedelta
from telethon import Button


class TelegramUIUtils:
    """Klasa utility dla formatowania UI w Telegram."""
    
    # Emoji dictionary dla różnych typów danych
    EMOJIS = {
        # Status
        'success': '✅',
        'error': '❌',
        'warning': '⚠️',
        'info': 'ℹ️',
        'loading': '🔄',
        'pending': '⏳',
        
        # Actions
        'create': '➕',
        'edit': '✏️',
        'delete': '🗑️',
        'view': '👁️',
        'refresh': '🔄',
        'search': '🔍',
        'filter': '🔽',
        'sort': '↕️',
        
        # Data types
        'money': '💰',
        'exchange': '🏦',
        'asset': '💎',
        'transaction': '💸',
        'analysis': '📊',
        'user': '👤',
        'admin': '👑',
        'time': '🕐',
        'date': '📅',
        
        # Navigation
        'home': '🏠',
        'back': '🔙',
        'next': '▶️',
        'previous': '◀️',
        'up': '⬆️',
        'down': '⬇️',
        
        # Status indicators
        'online': '🟢',
        'offline': '🔴',
        'active': '✅',
        'inactive': '❌',
        'maintenance': '🔧',
        'healthy': '💚',
        'unhealthy': '💔'
    }
    
    @staticmethod
    def format_currency(amount: float, currency: str = "USD", decimals: int = 2) -> str:
        """
        Formatuje kwotę w walucie.
        
        Args:
            amount: Kwota
            currency: Waluta
            decimals: Liczba miejsc po przecinku
            
        Returns:
            str: Sformatowana kwota
        """
        if currency.upper() == "USD":
            symbol = "$"
        elif currency.upper() == "EUR":
            symbol = "€"
        elif currency.upper() == "PLN":
            symbol = "zł"
        else:
            symbol = currency.upper()
        
        formatted_amount = f"{amount:,.{decimals}f}"
        return f"{symbol}{formatted_amount}" if currency.upper() == "USD" else f"{formatted_amount} {symbol}"
    
    @staticmethod
    def format_percentage(value: float, decimals: int = 2) -> str:
        """
        Formatuje wartość procentową.
        
        Args:
            value: Wartość w procentach
            decimals: Liczba miejsc po przecinku
            
        Returns:
            str: Sformatowana wartość procentowa
        """
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.{decimals}f}%"
    
    @staticmethod
    def format_duration(seconds: int) -> str:
        """
        Formatuje czas trwania.
        
        Args:
            seconds: Liczba sekund
            
        Returns:
            str: Sformatowany czas
        """
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    @staticmethod
    def create_progress_bar(current: int, total: int, length: int = 20, 
                          filled_char: str = "█", empty_char: str = "░") -> str:
        """
        Tworzy progress bar.
        
        Args:
            current: Aktualna wartość
            total: Maksymalna wartość
            length: Długość progress bara
            filled_char: Znak wypełniony
            empty_char: Znak pusty
            
        Returns:
            str: Progress bar
        """
        if total == 0:
            return empty_char * length
        
        filled_length = int(length * current / total)
        bar = filled_char * filled_length + empty_char * (length - filled_length)
        percentage = (current / total) * 100
        
        return f"{bar} {percentage:.1f}%"
    
    @staticmethod
    def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
        """
        Obcina tekst do określonej długości.
        
        Args:
            text: Tekst do obcięcia
            max_length: Maksymalna długość
            suffix: Sufiks dla obciętego tekstu
            
        Returns:
            str: Obcięty tekst
        """
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix
    
    @classmethod
    def create_status_message(cls, status: str, title: str, details: str = "") -> str:
        """
        Tworzy wiadomość statusu.
        
        Args:
            status: Status (success/error/warning/info/loading)
            title: Tytuł wiadomości
            details: Szczegóły
            
        Returns:
            str: Sformatowana wiadomość
        """
        emoji = cls.EMOJIS.get(status, '📋')
        message = f"{emoji} **{title}**"
        
        if details:
            message += f"\n\n{details}"
        
        return message
    
    @classmethod
    def create_data_table(cls, data: List[Dict[str, Any]], 
                         columns: List[Dict[str, Any]], 
                         title: str = "",
                         max_rows: int = 10) -> str:
        """
        Tworzy sformatowaną tabelę danych.
        
        Args:
            data: Lista rekordów
            columns: Definicje kolumn [{"key": "field_name", "title": "Display Name", "width": 12}]
            title: Tytuł tabeli
            max_rows: Maksymalna liczba wierszy
            
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
        
        response += "```\n"
        
        # Nagłówki
        header_parts = []
        for col in columns:
            width = col.get('width', 12)
            title_text = col['title'][:width].ljust(width)
            header_parts.append(title_text)
        
        response += " | ".join(header_parts) + "\n"
        response += "-" * (sum(col.get('width', 12) for col in columns) + len(columns) * 3 - 1) + "\n"
        
        # Wiersze danych
        for row in display_data:
            row_parts = []
            for col in columns:
                width = col.get('width', 12)
                field_key = col['key']
                
                # Pobierz wartość z zagnieżdżonych kluczy (np. "user.name")
                value = row
                for key_part in field_key.split('.'):
                    value = value.get(key_part, '') if isinstance(value, dict) else ''
                
                # Formatuj wartość
                if col.get('type') == 'currency':
                    try:
                        value = cls.format_currency(float(value))
                    except:
                        pass
                elif col.get('type') == 'percentage':
                    try:
                        value = cls.format_percentage(float(value))
                    except:
                        pass
                elif col.get('type') == 'datetime':
                    try:
                        if isinstance(value, str):
                            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                            value = dt.strftime("%Y-%m-%d %H:%M")
                    except:
                        pass
                
                value_text = str(value)[:width].ljust(width)
                row_parts.append(value_text)
            
            response += " | ".join(row_parts) + "\n"
        
        response += "```\n"
        
        # Informacja o obcięciu
        if len(data) > max_rows:
            response += f"\n📄 Wyświetlono {max_rows} z {len(data)} rekordów.\n"
        
        return response


class PaginationHelper:
    """Helper dla obsługi paginacji."""
    
    @staticmethod
    def calculate_pages(total_items: int, page_size: int) -> int:
        """Oblicza liczbę stron."""
        return (total_items + page_size - 1) // page_size if total_items > 0 else 0
    
    @staticmethod
    def get_page_data(data: List[Any], page: int, page_size: int) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Pobiera dane dla konkretnej strony.
        
        Args:
            data: Pełne dane
            page: Numer strony (1-based)
            page_size: Rozmiar strony
            
        Returns:
            Tuple[List[Any], Dict[str, Any]]: (dane_strony, info_paginacji)
        """
        total_items = len(data)
        total_pages = PaginationHelper.calculate_pages(total_items, page_size)
        
        # Walidacja strony
        page = max(1, min(page, total_pages)) if total_pages > 0 else 1
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total_items)
        page_data = data[start_idx:end_idx]
        
        pagination_info = {
            'current_page': page,
            'total_pages': total_pages,
            'total_items': total_items,
            'items_on_page': len(page_data),
            'has_previous': page > 1,
            'has_next': page < total_pages,
            'start_idx': start_idx,
            'end_idx': end_idx
        }
        
        return page_data, pagination_info
    
    @staticmethod
    def create_pagination_buttons(pagination_info: Dict[str, Any], 
                                callback_prefix: str,
                                additional_data: str = "") -> List[List[Button]]:
        """
        Tworzy przyciski paginacji.
        
        Args:
            pagination_info: Informacje o paginacji z get_page_data()
            callback_prefix: Prefix dla callbacków
            additional_data: Dodatkowe dane do przekazania
            
        Returns:
            List[List[Button]]: Lista wierszy przycisków
        """
        if pagination_info['total_pages'] <= 1:
            return []
        
        buttons = []
        nav_row = []
        
        current_page = pagination_info['current_page']
        total_pages = pagination_info['total_pages']
        
        # Previous button
        if pagination_info['has_previous']:
            prev_callback = f"{callback_prefix}:page:{current_page-1}"
            if additional_data:
                prev_callback += f":{additional_data}"
            nav_row.append(Button.inline("◀️ Wstecz", prev_callback.encode()))
        
        # Page info
        page_info = f"📄 {current_page}/{total_pages}"
        nav_row.append(Button.inline(page_info, f"{callback_prefix}:page_info".encode()))
        
        # Next button
        if pagination_info['has_next']:
            next_callback = f"{callback_prefix}:page:{current_page+1}"
            if additional_data:
                next_callback += f":{additional_data}"
            nav_row.append(Button.inline("Dalej ▶️", next_callback.encode()))
        
        if nav_row:
            buttons.append(nav_row)
        
        # Jump to page button (for large datasets)
        if total_pages > 5:
            jump_callback = f"{callback_prefix}:jump"
            if additional_data:
                jump_callback += f":{additional_data}"
            buttons.append([Button.inline("🔢 Idź do strony...", jump_callback.encode())])
        
        return buttons


class InteractiveWizard:
    """Klasa pomocnicza dla interactive wizards."""
    
    def __init__(self, wizard_id: str, steps: List[Dict[str, Any]]):
        """
        Inicjalizacja wizard.
        
        Args:
            wizard_id: Unikalny ID wizard
            steps: Lista kroków wizard [{"id": "step1", "title": "Krok 1", "handler": callable}]
        """
        self.wizard_id = wizard_id
        self.steps = steps
        self.user_data = {}
    
    def get_step_by_id(self, step_id: str) -> Optional[Dict[str, Any]]:
        """Pobiera krok po ID."""
        for step in self.steps:
            if step['id'] == step_id:
                return step
        return None
    
    def get_current_step_index(self, step_id: str) -> int:
        """Pobiera indeks aktualnego kroku."""
        for i, step in enumerate(self.steps):
            if step['id'] == step_id:
                return i
        return 0
    
    def get_navigation_buttons(self, current_step_id: str, 
                             callback_prefix: str) -> List[List[Button]]:
        """
        Tworzy przyciski nawigacji dla wizard.
        
        Args:
            current_step_id: ID aktualnego kroku
            callback_prefix: Prefix dla callbacków
            
        Returns:
            List[List[Button]]: Przyciski nawigacji
        """
        buttons = []
        current_index = self.get_current_step_index(current_step_id)
        
        nav_row = []
        
        # Previous button
        if current_index > 0:
            prev_step = self.steps[current_index - 1]['id']
            nav_row.append(Button.inline(
                "◀️ Wstecz", 
                f"{callback_prefix}:step:{prev_step}".encode()
            ))
        
        # Step info
        step_info = f"📋 {current_index + 1}/{len(self.steps)}"
        nav_row.append(Button.inline(step_info, f"{callback_prefix}:info".encode()))
        
        # Next button (if data is complete)
        if current_index < len(self.steps) - 1:
            next_step = self.steps[current_index + 1]['id']
            nav_row.append(Button.inline(
                "Dalej ▶️",
                f"{callback_prefix}:step:{next_step}".encode()
            ))
        
        if nav_row:
            buttons.append(nav_row)
        
        # Cancel button
        buttons.append([Button.inline("❌ Anuluj", f"{callback_prefix}:cancel".encode())])
        
        return buttons
    
    def create_progress_indicator(self, current_step_id: str) -> str:
        """
        Tworzy wskaźnik postępu wizard.
        
        Args:
            current_step_id: ID aktualnego kroku
            
        Returns:
            str: Wskaźnik postępu
        """
        current_index = self.get_current_step_index(current_step_id)
        progress_bar = TelegramUIUtils.create_progress_bar(
            current_index + 1, len(self.steps), length=15
        )
        
        current_step = self.get_step_by_id(current_step_id)
        step_title = current_step['title'] if current_step else "Unknown Step"
        
        return f"🧙‍♂️ **{self.wizard_id.title()} Wizard**\n\n" \
               f"📋 **{step_title}**\n" \
               f"📊 **Postęp:** {progress_bar}\n\n"


class ValidationHelper:
    """Helper dla walidacji danych wejściowych."""
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Waliduje adres email."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_number(value: str, min_val: float = None, 
                       max_val: float = None) -> Tuple[bool, Optional[float]]:
        """
        Waliduje liczbę.
        
        Args:
            value: Wartość do walidacji
            min_val: Minimalna wartość
            max_val: Maksymalna wartość
            
        Returns:
            Tuple[bool, Optional[float]]: (czy_prawidłowa, wartość_liczbowa)
        """
        try:
            num = float(value)
            if min_val is not None and num < min_val:
                return False, None
            if max_val is not None and num > max_val:
                return False, None
            return True, num
        except ValueError:
            return False, None
    
    @staticmethod
    def validate_asset_symbol(symbol: str) -> bool:
        """Waliduje symbol assetu (np. BTCUSDT)."""
        # Symbol powinien zawierać tylko litery i cyfry, długość 3-20 znaków
        pattern = r'^[A-Z0-9]{3,20}$'
        return bool(re.match(pattern, symbol.upper()))
    
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Czyści input użytkownika z potencjalnie niebezpiecznych znaków."""
        # Usuń markdown/HTML tags
        text = re.sub(r'[<>*_`\[\]()]', '', text)
        # Ogranicz długość
        text = text[:500]
        # Usuń nadmiarowe białe znaki
        text = ' '.join(text.split())
        return text.strip()


class ConfirmationDialog:
    """Helper dla dialogów potwierdzenia."""
    
    @staticmethod
    def create_confirmation_message(action: str, item_name: str = "", 
                                  warning: str = "") -> str:
        """
        Tworzy wiadomość potwierdzenia.
        
        Args:
            action: Akcja do potwierdzenia
            item_name: Nazwa elementu
            warning: Opcjonalne ostrzeżenie
            
        Returns:
            str: Sformatowana wiadomość
        """
        message = f"❓ **Potwierdzenie akcji**\n\n"
        message += f"🔄 **Akcja:** {action}\n"
        
        if item_name:
            message += f"📋 **Element:** {item_name}\n"
        
        if warning:
            message += f"\n⚠️ **Uwaga:** {warning}\n"
        
        message += f"\n❓ Czy na pewno chcesz kontynuować?"
        
        return message
    
    @staticmethod
    def create_confirmation_buttons(callback_prefix: str, 
                                  action_data: str = "") -> List[List[Button]]:
        """
        Tworzy przyciski potwierdzenia.
        
        Args:
            callback_prefix: Prefix dla callbacków
            action_data: Dane akcji do przekazania
            
        Returns:
            List[List[Button]]: Przyciski potwierdzenia
        """
        confirm_callback = f"{callback_prefix}:confirm"
        cancel_callback = f"{callback_prefix}:cancel"
        
        if action_data:
            confirm_callback += f":{action_data}"
            cancel_callback += f":{action_data}"
        
        return [
            [
                Button.inline("✅ Potwierdź", confirm_callback.encode()),
                Button.inline("❌ Anuluj", cancel_callback.encode())
            ]
        ]


class DataHashHelper:
    """Helper dla hashowania danych w callbackach."""
    
    @staticmethod
    def create_data_hash(data: Dict[str, Any]) -> str:
        """
        Tworzy hash danych dla callbacków.
        
        Args:
            data: Dane do zahashowania
            
        Returns:
            str: Hash danych
        """
        import json
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()[:8]
    
    @staticmethod
    def encode_callback_data(prefix: str, action: str, 
                           data: Dict[str, Any] = None) -> str:
        """
        Koduje dane dla callbacku.
        
        Args:
            prefix: Prefix callbacku
            action: Akcja
            data: Dodatkowe dane
            
        Returns:
            str: Zakodowane dane callbacku
        """
        callback = f"{prefix}:{action}"
        
        if data:
            data_hash = DataHashHelper.create_data_hash(data)
            callback += f":{data_hash}"
        
        return callback


# Convenience functions
def create_loading_message(action: str) -> str:
    """Shortcut dla tworzenia wiadomości loading."""
    return TelegramUIUtils.create_status_message('loading', f'Ładuję {action}', 'Proszę czekać...')

def create_success_message(action: str, details: str = "") -> str:
    """Shortcut dla tworzenia wiadomości sukcesu."""
    return TelegramUIUtils.create_status_message('success', f'{action} zakończone pomyślnie', details)

def create_error_message(action: str, error: str = "") -> str:
    """Shortcut dla tworzenia wiadomości błędu."""
    return TelegramUIUtils.create_status_message('error', f'Błąd podczas {action}', error)
