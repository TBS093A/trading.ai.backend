"""
Kontroler Analysis dla Telegram - zarządzanie analizami finansowymi.

Ta klasa implementuje:
- Przeglądanie analiz fundamentalnych, technicznych i wzorców harmonicznych
- Wyświetlanie interpretacji z możliwością przełączania między typami
- Wysyłanie chart images w pełnej rozdzielczości
- Filtrowanie analiz po assetach
- Integrację z systemem interpretacji

Autor: AI Assistant
"""

import logging
import traceback
import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from telethon import Button
from telethon.tl.types import InputMediaUploadedPhoto

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, RD
from .controller_telegram_utils_ui import PaginationHelper, TelegramUIUtils

logger = logging.getLogger(__name__)


class AnalysisTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla zarządzania analizami finansowymi w systemie Telegram.
    
    Zapewnia funkcjonalności:
    - Przegląd różnych typów analiz (fundamentalne, techniczne, wzorce)
    - Interpretacje generalne z przełączaniem między typami
    - Wysyłanie chart images w pełnej rozdzielczości
    - Filtrowanie analiz po assetach
    - Integrację z bazą danych analiz
    """
    
    DOMAIN = "analysis"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera analiz.
        
        Args:
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        
        # Konfiguracja paginacji
        self.default_page_size = 5  # Zmniejszone z 5 na 2 - zbyt długie komunikaty Telegram
        self.max_page_size = 25
        
        # Ścieżki do chart images (w przyszłości można skonfigurować)
        self.chart_images_path = "/tmp/chart_images"  # Default path
    
    # ===================
    # DOMAIN MENU
    # ===================
    
    async def get_domain_menu(self, event, user_id: Optional[int] = None) -> Tuple[str, List[List[Button]]]:
        """Zwraca menu domeny analiz z przyciskami komend."""
        try:
            stats = await self.get_domain_specific_stats()
            
            menu_text = "🔍 **Analysis - Analizy Finansowe**\n\n"
            
            if stats.get('database_available'):
                menu_text += f"📊 **Statystyki:**\n"
                menu_text += f"• Analizy fundamentalne: {stats.get('fundamental_analysis', 'N/A')}\n"
                menu_text += f"• Analizy techniczne: {stats.get('technical_analysis', 'N/A')}\n"
                menu_text += f"• Wzorce harmoniczne: {stats.get('harmonic_patterns', 'N/A')}\n"
                menu_text += f"• Interpretacje: {stats.get('total_interpretations', 'N/A')}\n\n"
            else:
                menu_text += "⚠️ **Baza danych niedostępna**\n\n"
            
            menu_text += "📋 **Dostępne funkcje:**\n"
            menu_text += "• Przegląd wszystkich analiz\n"
            menu_text += "• Analizy fundamentalne i techniczne\n"
            menu_text += "• Wzorce harmoniczne\n"
            menu_text += "• Interpretacje analiz\n"
            
            buttons = [
                [
                    Button.inline("📊 Wszystkie Analizy", b"analysis:all"),
                ],
                [
                    Button.inline("📈 Analizy Tech.", b"analysis:technical"),
                    Button.inline("💰 Analizy Fund.", b"analysis:fundamental")
                ],
                [
                    Button.inline("💡 Interpr. Fund. LLM", b"analysis:interpretations_fundamental"),
                    Button.inline("💡 Interpr. Tech. LLM", b"analysis:interpretations_technical")
                ],
                [
                    Button.inline("💡 Interpr. Gen. LLM", b"analysis:interpretations")
                ]
                [
                    Button.inline("🏠 Menu Główne", b"nav:main_menu")
                ]
            ]
            
            return menu_text, buttons
            
        except Exception as e:
            logger.error(f"Błąd w get_domain_menu (analysis): {e}")
            return await super().get_domain_menu(event, user_id)
    
    # ===================
    # CALLBACK HANDLERS - DIRECT COMMAND EXECUTION
    # ===================
    
    @RD.cb(b"analysis:all")
    async def callback_analysis_all(self, event):
        """Callback dla bezpośredniego wykonania komendy /analysis z domyślną stroną 1"""
        await self.analysis_command(event)
    
    @RD.cb(b"analysis:fundamental")
    async def callback_analysis_fundamental(self, event):
        """Callback dla bezpośredniego wykonania komendy /analysis_fundamental z domyślną stroną 1"""
        await self.analysis_fundamental_command(event)
    
    @RD.cb(b"analysis:technical")
    async def callback_analysis_technical(self, event):
        """Callback dla bezpośredniego wykonania komendy /analysis_technical z domyślną stroną 1"""
        await self.analysis_technical_command(event)
    
    @RD.cb(b"analysis:patterns")
    async def callback_analysis_patterns(self, event):
        """Callback dla bezpośredniego wykonania komendy /analysis_technical_harmonic_patterns z domyślną stroną 1"""
        await self.analysis_harmonic_patterns_command(event)
    
    @RD.cb(b"analysis:interpretations")
    async def callback_analysis_interpretations(self, event):
        """Callback dla bezpośredniego wykonania komendy /analysis_interpretations z domyślną stroną 1"""
        await self.analysis_interpretations_command(event)
        
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny analiz."""
        try:
            if not self.db:
                return {"error": "Database not available"}
            
            await self.init_database()
            
            # Pobierz tabele
            fundamental_table = self.db.get_factory().get_fundamental_analysis_table()
            harmonic_patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            tech_interp_table = self.db.get_factory().get_technical_analysis_interpretation_table()
            general_interp_table = self.db.get_factory().get_general_interpretation_table()
            fund_interp_table = self.db.get_factory().get_fundamental_analysis_interpretation_table()
            
            # Pobierz statystyki
            fundamental_count = len(await fundamental_table.get_all(limit=10000))
            # Uwaga: Brak osobnej tabeli technical_analysis - używamy harmonic_patterns jako proxy
            harmonic_patterns_count = len(await harmonic_patterns_table.get_all(limit=10000))
            general_interp_count = len(await general_interp_table.get_all(limit=10000))
            fund_interp_count = len(await fund_interp_table.get_all(limit=10000))
            tech_interp_count = len(await tech_interp_table.get_all(limit=10000))
            
            return {
                "fundamental_analysis": fundamental_count,
                "technical_analysis": harmonic_patterns_count,  # Używamy wzorców harmonicznych jako proxy
                "harmonic_patterns": harmonic_patterns_count,
                "general_interpretations": general_interp_count,
                "fundamental_interpretations": fund_interp_count,
                "technical_interpretations": tech_interp_count,
                "total_analysis": fundamental_count + harmonic_patterns_count,
                "total_interpretations": general_interp_count + fund_interp_count + tech_interp_count,
                "database_available": True
            }
            
        except Exception as e:
            logger.error(f"Error getting analysis domain stats: {e}")
            return {
                "error": str(e),
                "database_available": False
            }
    
    # ===================
    # COMMANDS - ANALYSIS OVERVIEW
    # ===================
    
    @RD.cmd("analysis", aliases=["analyses", "show_analysis"])
    async def analysis_command(self, event):
        """
        Komenda przeglądu dostępnych analiz.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "analysis_overview")
        
        try:
            # Pobierz statystyki
            stats = await self.get_domain_specific_stats()
            
            if 'error' in stats:
                await event.respond(f"❌ **Błąd analiz**\n\n{stats['error']}")
                return
            
            # Formatuj przegląd
            overview_text = f"📈 **Przegląd Analiz**\n\n"
            overview_text += f"📊 **Dostępne analizy:**\n"
            overview_text += f"• 💼 Fundamentalne: `{stats['fundamental_analysis']}`\n"
            overview_text += f"• 📈 Techniczne: `{stats['technical_analysis']}`\n"
            overview_text += f"• 🔄 Wzorce harmoniczne: `{stats['harmonic_patterns']}`\n\n"
            
            overview_text += f"🧠 **Interpretacje:**\n"
            overview_text += f"• 🎯 Generalne: `{stats['general_interpretations']}`\n"
            overview_text += f"• 💼 Fundamentalne: `{stats['fundamental_interpretations']}`\n"
            overview_text += f"• 📈 Techniczne: `{stats['technical_interpretations']}`\n\n"
            
            overview_text += f"📋 **Podsumowanie:**\n"
            overview_text += f"• Łączne analizy: `{stats['total_analysis']}`\n"
            overview_text += f"• Łączne interpretacje: `{stats['total_interpretations']}`"
            
            # Przyciski nawigacji
            buttons = [
                [
                    Button.inline("💼 Fundamentalne", b"analysis:fund_overview"),
                    Button.inline("📈 Techniczne", b"analysis:tech_overview")
                ],
                [
                    Button.inline("🔄 Wzorce", b"analysis:patterns_overview"),
                ],
                [
                    Button.inline("💼 Fundamentalne LLM", b"analysis:fund_llm_overview"),
                    Button.inline("📈 Techniczne LLM", b"analysis:tech_llm_overview")
                ],
                [
                    Button.inline("🎯 General LLM", b"interp:general")
                ],
                [
                    Button.inline("🔍 Wyszukaj po asset", b"analysis:search_asset"),
                    Button.inline("🔄 Odśwież", b"analysis:refresh")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.respond(overview_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "analysis_overview")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - FUNDAMENTAL ANALYSIS
    # ===================
    
    @RD.cmd("analysis_fundamental", aliases=["fundamental", "fund_analysis"])
    async def analysis_fundamental_command(self, event):
        """
        Komenda analizy fundamentalnej.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "fundamental_analysis_list")
        
        # Parse argumentów dla paginacji
        text_parts = self.parse_command_args(event)
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            fundamental_table = self.db.get_factory().get_fundamental_analysis_table()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz analizy fundamentalne
            fundamental_analyses = await fundamental_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not fundamental_analyses:
                await event.respond("💼 **Analizy Fundamentalne**\n\n❌ Brak analiz fundamentalnych do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(fundamental_analyses) > self.default_page_size
            page_analyses = fundamental_analyses[:self.default_page_size]
            
            # Formatuj listę
            analysis_text = f"💼 **Analizy Fundamentalne - Strona {page}**\n\n"
            
            for i, analysis in enumerate(page_analyses, 1):
                item_number = offset + i
                
                # Pobierz asset info z tablic assets i quotes (już w wyniku JOIN)
                asset_info = ""
                if 'assets' in analysis and 'quotes' in analysis and analysis['assets'] and analysis['quotes']:
                    try:
                        # Weź pierwszy asset jeśli jest więcej
                        asset_name = analysis['assets'][0] if isinstance(analysis['assets'], list) else analysis['assets']
                        quote_name = analysis['quotes'][0] if isinstance(analysis['quotes'], list) else analysis['quotes']
                        asset_info = f" ({asset_name}/{quote_name})"
                    except (IndexError, TypeError):
                        pass
                
                analysis_text += f"{item_number}. 📊 Analiza #{analysis['id']}{asset_info}\n"
                
                # Wyświetl WSZYSTKIE kolumny z bazy danych (poza content i asset info)
                for key, value in analysis.items():
                    if key in ['id', 'assets', 'quotes', 'asset_ids', 'content']:  # Pomijamy już wyświetlone i content
                        continue
                    if value is not None and value != '' and value != []:
                        if key == 'created_at':
                            analysis_text += f"    📅 {key}: {self._format_datetime(value)}\n"
                        elif key == 'timestamp':
                            analysis_text += f"    ⏰ {key}: {value}\n"
                        else:
                            # Ograniczenie długich wartości kolumn
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            analysis_text += f"    📋 {key}: {value_display}\n"
                
                # Wyświetl zawartość content dict (limit 5 pierwszych kluczy)
                content = analysis.get('content', {})
                if isinstance(content, dict) and content:
                    analysis_text += f"    📄 **CONTENT:**\n"
                    displayed_keys = 0
                    for key, value in content.items():
                        if displayed_keys >= 10:  # Limit do 10 kluczy
                            analysis_text += f"      • ... (i {len(content) - displayed_keys} więcej kluczy)\n"
                            break
                        if value is not None and value != '' and value != []:
                            # Skróć długie wartości
                            if isinstance(value, str) and len(value) > 150:
                                value_display = value[:150] + "..."
                            elif isinstance(value, (list, dict)):
                                value_display = str(value)[:150] + "..." if len(str(value)) > 150 else str(value)
                            else:
                                value_display = str(value)
                            analysis_text += f"      • {key}: {value_display}\n"
                            displayed_keys += 1
                
                analysis_text += "\n"
            
            # Pobierz dokładną liczbę wszystkich rekordów dla poprawnej paginacji
            total_count = await fundamental_table.count_all()
            
            # Informacja o paginacji
            if page > 1 or has_next:
                analysis_text += f"📄 Strona {page}"
                if has_next:
                    analysis_text += f" (więcej dostępne)"
            
            # Pagination info z dokładną liczbą
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(total_count, self.default_page_size),
                'total_items': total_count,
                'items_on_page': len(page_analyses),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_analyses)
            }
            
            # Przyciski paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "analysis:fund_page",
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Po assetach", b"analysis:fund_by_asset"),
                    Button.inline("📊 Szczegóły", b"analysis:fund_details_menu")
                ],
                [
                    Button.inline("📈 Analiza ogólna", b"analysis:overview"),
                    Button.inline("🔄 Odśwież", f"analysis:fund_page:{page}".encode())
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.respond(analysis_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "fundamental_analysis")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - FUNDAMENTAL ANALYSIS BY ASSET
    # ===================
    
    @RD.cmd("analysis_fundamental_asset", aliases=["fund_asset", "fa"])
    async def analysis_fundamental_asset_command(self, event):
        """
        Komenda bezpośredniego dostępu do analiz fundamentalnych dla konkretnego assetu.
        Format: /analysis_fundamental_asset SYMBOL [page]
        Przykłady: /analysis_fundamental_asset BTC-USDT, /analysis_fundamental_asset ETH-USDT 2
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Parse argumentów
        text_parts = self.parse_command_args(event)
        if len(text_parts) < 2:
            await event.respond(
                "💼 **Analizy Fundamentalne po Asset**\n\n"
                "**Format:** `/analysis_fundamental_asset SYMBOL [strona]`\n\n"
                "**Przykłady:**\n"
                "• `/analysis_fundamental_asset BTC-USDT`\n"
                "• `/analysis_fundamental_asset ETH-USDT 2`\n\n"
                "**Format symbolu:** ASSET-QUOTE (np. BTC-USDT, ETH-BTC)"
            )
            return
        
        symbol = text_parts[1].upper().replace('-', '/')  # BTC-USDT -> BTC/USDT
        page = 1
        
        if len(text_parts) >= 3:
            try:
                page = int(text_parts[2])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Parse asset/quote z symbolu
            if '/' not in symbol:
                await event.respond("❌ Nieprawidłowy format symbolu. Użyj: ASSET-QUOTE (np. BTC-USDT)")
                return
            
            asset, quote = symbol.split('/', 1)
            asset_record = await assets_table.get_by_asset_quote(asset, quote)
            
            if not asset_record:
                await event.respond(f"❌ Asset {symbol} nie został znaleziony w bazie danych.")
                return
            
            await self.log_action(user.id, "fundamental_analysis_by_asset_command", {"symbol": symbol, "page": page})
            await self._show_analysis_for_asset(event, "fundamental", page, asset_record['id'])
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "fundamental_analysis_by_asset")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - TECHNICAL ANALYSIS
    # ===================
    
    @RD.cmd("analysis_technical", aliases=["technical", "tech_analysis"])
    async def analysis_technical_command(self, event):
        """
        Komenda analizy technicznej.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "technical_analysis_list")
        
        # Parse argumentów dla paginacji
        text_parts = self.parse_command_args(event)
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            # Uwaga: Używamy harmonic_patterns jako tabelę analiz technicznych
            technical_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz analizy techniczne
            technical_analyses = await technical_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not technical_analyses:
                await event.respond("📈 **Analizy Techniczne**\n\n❌ Brak analiz technicznych do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(technical_analyses) > self.default_page_size
            page_analyses = technical_analyses[:self.default_page_size]
            
            # Formatuj listę
            analysis_text = f"📈 **Analizy Techniczne - Strona {page}**\n\n"
            
            for i, analysis in enumerate(page_analyses, 1):
                item_number = offset + i
                
                # Pobierz asset info (już w wyniku JOIN)
                asset_info = ""
                if 'asset' in analysis and 'quote' in analysis:
                    asset_info = f" ({analysis['asset']}/{analysis['quote']})"
                
                analysis_text += f"{item_number}. 📊 Wzorzec #{analysis['id']}{asset_info}\n"
                
                # Wyświetl WSZYSTKIE kolumny z bazy danych (poza ta_object_json i asset info)
                for key, value in analysis.items():
                    if key in ['id', 'asset', 'quote', 'ta_object_json']:  # Pomijamy już wyświetlone i ta_object_json
                        continue
                    if value is not None and value != '' and value != []:
                        if 'timestamp' in key.lower():
                            # Konwertuj timestamp na datetime
                            from datetime import datetime
                            try:
                                dt = datetime.fromtimestamp(value / 1000 if value > 1e10 else value)
                                analysis_text += f"    📅 {key}: {dt.strftime('%Y-%m-%d %H:%M')}\n"
                            except (ValueError, OSError):
                                analysis_text += f"    📅 {key}: {value}\n"
                        else:
                            # Ograniczenie długich wartości kolumn
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            analysis_text += f"    📋 {key}: {value_display}\n"
                
                # Wyświetl zawartość ta_object_json dict (limit 5 pierwszych kluczy)
                ta_object = analysis.get('ta_object_json', {})
                if isinstance(ta_object, dict) and ta_object:
                    analysis_text += f"    📄 **TA_OBJECT_JSON:**\n"
                    displayed_keys = 0
                    for key, value in ta_object.items():
                        if displayed_keys >= 5:  # Limit do 5 kluczy
                            analysis_text += f"      • ... (i {len(ta_object) - displayed_keys} więcej kluczy)\n"
                            break
                        if value is not None and value != '' and value != []:
                            # Skróć długie wartości
                            if isinstance(value, str) and len(value) > 30:
                                value_display = value[:30] + "..."
                            elif isinstance(value, (list, dict)):
                                value_display = str(value)[:30] + "..." if len(str(value)) > 30 else str(value)
                            else:
                                value_display = str(value)
                            analysis_text += f"      • {key}: {value_display}\n"
                            displayed_keys += 1
                
                analysis_text += "\n"
            
            # Informacja o paginacji
            if page > 1 or has_next:
                analysis_text += f"📄 Strona {page}"
                if has_next:
                    analysis_text += f" (więcej dostępne)"
            
            # Pagination info
            estimated_total = offset + len(page_analyses) + (100 if has_next else 0)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_analyses),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_analyses)
            }
            
            # Przyciski paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "analysis:tech_page",
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Po assetach", b"analysis:tech_by_asset"),
                    Button.inline("📊 Szczegóły", b"analysis:tech_details_menu")
                ],
                [
                    Button.inline("🔄 Wzorce harm.", b"analysis:patterns_overview"),
                    Button.inline("📈 Analiza ogólna", b"analysis:overview")
                ],
                [
                    Button.inline("🔄 Odśwież", f"analysis:tech_page:{page}".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ])
            
            await event.respond(analysis_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "technical_analysis")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - TECHNICAL ANALYSIS BY ASSET
    # ===================
    
    @RD.cmd("analysis_technical_asset", aliases=["tech_asset", "ta"])
    async def analysis_technical_asset_command(self, event):
        """
        Komenda bezpośredniego dostępu do analiz technicznych dla konkretnego assetu.
        Format: /analysis_technical_asset SYMBOL [page]
        Przykłady: /analysis_technical_asset BTC-USDT, /analysis_technical_asset ETH-USDT 2
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Parse argumentów
        text_parts = self.parse_command_args(event)
        if len(text_parts) < 2:
            await event.respond(
                "📈 **Analizy Techniczne po Asset**\n\n"
                "**Format:** `/analysis_technical_asset SYMBOL [strona]`\n\n"
                "**Przykłady:**\n"
                "• `/analysis_technical_asset BTC-USDT`\n"
                "• `/analysis_technical_asset ETH-USDT 2`\n\n"
                "**Format symbolu:** ASSET-QUOTE (np. BTC-USDT, ETH-BTC)"
            )
            return
        
        symbol = text_parts[1].upper().replace('-', '/')  # BTC-USDT -> BTC/USDT
        page = 1
        
        if len(text_parts) >= 3:
            try:
                page = int(text_parts[2])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Parse asset/quote z symbolu
            if '/' not in symbol:
                await event.respond("❌ Nieprawidłowy format symbolu. Użyj: ASSET-QUOTE (np. BTC-USDT)")
                return
            
            asset, quote = symbol.split('/', 1)
            asset_record = await assets_table.get_by_asset_quote(asset, quote)
            
            if not asset_record:
                await event.respond(f"❌ Asset {symbol} nie został znaleziony w bazie danych.")
                return
            
            await self.log_action(user.id, "technical_analysis_by_asset_command", {"symbol": symbol, "page": page})
            await self._show_analysis_for_asset(event, "technical", page, asset_record['id'])
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "technical_analysis_by_asset")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - HARMONIC PATTERNS
    # ===================
    
    @RD.cmd("analysis_technical_harmonic_patterns", aliases=["harmonic_patterns", "patterns"])
    async def analysis_harmonic_patterns_command(self, event):
        """
        Komenda wzorców harmonicznych.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "harmonic_patterns_list")
        
        # Parse argumentów dla paginacji
        text_parts = self.parse_command_args(event)
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz wzorce harmoniczne
            patterns = await patterns_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not patterns:
                await event.respond("🔄 **Wzorce Harmoniczne**\n\n❌ Brak wzorców harmonicznych do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(patterns) > self.default_page_size
            page_patterns = patterns[:self.default_page_size]
            
            # Formatuj listę
            patterns_text = f"🔄 **Wzorce Harmoniczne - Strona {page}**\n\n"
            
            for i, pattern in enumerate(page_patterns, 1):
                item_number = offset + i
                
                # Pobierz asset info (już w wyniku JOIN)
                asset_info = ""
                if 'asset' in pattern and 'quote' in pattern:
                    asset_info = f" ({pattern['asset']}/{pattern['quote']})"
                
                patterns_text += f"{item_number}. 🔄 Wzorzec #{pattern['id']}{asset_info}\n"
                
                # Wyświetl WSZYSTKIE kolumny z bazy danych (poza ta_object_json i asset info)
                for key, value in pattern.items():
                    if key in ['id', 'asset', 'quote', 'ta_object_json']:  # Pomijamy już wyświetlone i ta_object_json
                        continue
                    if value is not None and value != '' and value != []:
                        if 'timestamp' in key.lower():
                            # Konwertuj timestamp na datetime
                            from datetime import datetime
                            try:
                                dt = datetime.fromtimestamp(value / 1000 if value > 1e10 else value)
                                patterns_text += f"    📅 {key}: {dt.strftime('%Y-%m-%d %H:%M')}\n"
                            except (ValueError, OSError):
                                patterns_text += f"    📅 {key}: {value}\n"
                        else:
                            # Ograniczenie długich wartości kolumn
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            patterns_text += f"    📋 {key}: {value_display}\n"
                
                # Wyświetl zawartość ta_object_json dict (limit 5 pierwszych kluczy)
                ta_object = pattern.get('ta_object_json', {})
                if isinstance(ta_object, dict) and ta_object:
                    patterns_text += f"    📄 **TA_OBJECT_JSON:**\n"
                    displayed_keys = 0
                    for key, value in ta_object.items():
                        if displayed_keys >= 5:  # Limit do 5 kluczy
                            patterns_text += f"      • ... (i {len(ta_object) - displayed_keys} więcej kluczy)\n"
                            break
                        if value is not None and value != '' and value != []:
                            # Skróć długie wartości
                            if isinstance(value, str) and len(value) > 30:
                                value_display = value[:30] + "..."
                            elif isinstance(value, (list, dict)):
                                value_display = str(value)[:30] + "..." if len(str(value)) > 30 else str(value)
                            else:
                                value_display = str(value)
                            patterns_text += f"      • {key}: {value_display}\n"
                            displayed_keys += 1
                
                patterns_text += "\n"
            
            # Informacja o paginacji
            if page > 1 or has_next:
                patterns_text += f"📄 Strona {page}"
                if has_next:
                    patterns_text += f" (więcej dostępne)"
            
            # Pagination info
            estimated_total = offset + len(page_patterns) + (100 if has_next else 0)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_patterns),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_patterns)
            }
            
            # Przyciski paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "analysis:patterns_page",
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Po assetach", b"analysis:patterns_by_asset"),
                    Button.inline("📊 Szczegóły", b"analysis:patterns_details_menu")
                ],
                [
                    Button.inline("📈 Analiza techn.", b"analysis:tech_overview"),
                    Button.inline("📈 Analiza ogólna", b"analysis:overview")
                ],
                [
                    Button.inline("🔄 Odśwież", f"analysis:patterns_page:{page}".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ])
            
            await event.respond(patterns_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "harmonic_patterns")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - HARMONIC PATTERNS BY ASSET
    # ===================
    
    @RD.cmd("analysis_patterns_asset", aliases=["patterns_asset", "pa"])
    async def analysis_patterns_asset_command(self, event):
        """
        Komenda bezpośredniego dostępu do wzorców harmonicznych dla konkretnego assetu.
        Format: /analysis_patterns_asset SYMBOL [page]
        Przykłady: /analysis_patterns_asset BTC-USDT, /analysis_patterns_asset ETH-USDT 2
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Parse argumentów
        text_parts = self.parse_command_args(event)
        if len(text_parts) < 2:
            await event.respond(
                "🔄 **Wzorce Harmoniczne po Asset**\n\n"
                "**Format:** `/analysis_patterns_asset SYMBOL [strona]`\n\n"
                "**Przykłady:**\n"
                "• `/analysis_patterns_asset BTC-USDT`\n"
                "• `/analysis_patterns_asset ETH-USDT 2`\n\n"
                "**Format symbolu:** ASSET-QUOTE (np. BTC-USDT, ETH-BTC)"
            )
            return
        
        symbol = text_parts[1].upper().replace('-', '/')  # BTC-USDT -> BTC/USDT
        page = 1
        
        if len(text_parts) >= 3:
            try:
                page = int(text_parts[2])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Parse asset/quote z symbolu
            if '/' not in symbol:
                await event.respond("❌ Nieprawidłowy format symbolu. Użyj: ASSET-QUOTE (np. BTC-USDT)")
                return
            
            asset, quote = symbol.split('/', 1)
            asset_record = await assets_table.get_by_asset_quote(asset, quote)
            
            if not asset_record:
                await event.respond(f"❌ Asset {symbol} nie został znaleziony w bazie danych.")
                return
            
            await self.log_action(user.id, "patterns_analysis_by_asset_command", {"symbol": symbol, "page": page})
            await self._show_analysis_for_asset(event, "patterns", page, asset_record['id'])
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "patterns_analysis_by_asset")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - INTERPRETATIONS
    # ===================
    
    @RD.cmd("analysis_interpretations", aliases=["interpretations", "interp"])
    async def analysis_interpretations_command(self, event):
        """
        Komenda interpretacji generalnych.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "interpretations_list")
        
        # Parse argumentów dla paginacji
        text_parts = self.parse_command_args(event)
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            interp_table = self.db.get_factory().get_general_interpretation_table()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz interpretacje generalne
            interpretations = await interp_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not interpretations:
                await event.respond("🧠 **Interpretacje Generalne**\n\n❌ Brak interpretacji do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(interpretations) > self.default_page_size
            page_interpretations = interpretations[:self.default_page_size]
            
            # Formatuj listę
            interp_text = f"🧠 **Interpretacje Generalne - Strona {page}**\n\n"
            
            for i, interp in enumerate(page_interpretations, 1):
                item_number = offset + i
                
                # Pobierz asset info (już w wyniku JOIN)
                asset_info = ""
                if 'asset' in interp and 'quote' in interp:
                    asset_info = f" ({interp['asset']}/{interp['quote']})"
                
                interp_text += f"{item_number}. 🧠 Interpretacja #{interp['id']}{asset_info}\n"
                
                # Wyświetl WSZYSTKIE kolumny z bazy danych
                for key, value in interp.items():
                    if key in ['id', 'asset', 'quote']:  # Pomijamy już wyświetlone
                        continue
                    if value is not None and value != '' and value != []:
                        if key == 'created_at':
                            interp_text += f"    📅 {key}: {self._format_datetime(value)}\n"
                        elif key == 'content':
                            # Skróć treść content bardziej agresywnie
                            content_text = str(value)
                            summary = content_text[:80] + "..." if len(content_text) > 80 else content_text
                            interp_text += f"    📝 {key}: {summary}\n"
                            
                            # Spróbuj wykryć rekomendację z treści
                            content_upper = content_text.upper()
                            if any(word in content_upper for word in ['BUY', 'KUPUJ', 'KPUJ', 'ZAKUP']):
                                interp_text += f"      🟢 Sygnał: BUY\n"
                            elif any(word in content_upper for word in ['SELL', 'SPRZEDAJ', 'SPRZEDAŻ']):
                                interp_text += f"      🔴 Sygnał: SELL\n"
                            elif any(word in content_upper for word in ['HOLD', 'TRZYMAJ', 'CZEKAJ']):
                                interp_text += f"      🟡 Sygnał: HOLD\n"
                        elif key == 'investment_strategy_name':
                            interp_text += f"    📊 {key}: {value}\n"
                        elif 'id' in key and key != 'id':  # powiązane ID
                            interp_text += f"    🔗 {key}: {value}\n"
                        else:
                            # Ograniczenie długich wartości kolumn
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            interp_text += f"    📋 {key}: {value_display}\n"
                
                interp_text += "\n"
            
            # Informacja o paginacji
            if page > 1 or has_next:
                interp_text += f"📄 Strona {page}"
                if has_next:
                    interp_text += f" (więcej dostępne)"
            
            # Pagination info
            estimated_total = offset + len(page_interpretations) + (100 if has_next else 0)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_interpretations),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_interpretations)
            }
            
            # Przyciski paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "interp:general_page",
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Po assetach", b"interp:by_asset"),
                    Button.inline("📊 Szczegóły", b"interp:details_menu")
                ],
                [
                    Button.inline("🎯 Według decyzji", b"interp:by_decision"),
                    Button.inline("📈 Analiza ogólna", b"analysis:overview")
                ],
                [
                    Button.inline("🔄 Odśwież", f"interp:general_page:{page}".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ])
            
            await event.respond(interp_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "interpretations")
            await event.respond(error_msg)
    
    @RD.cmd("analysis_fund_llm_interpretations", aliases=["fund_llm_interp", "fli"])
    async def analysis_fund_llm_interpretations_command(self, event):
        """
        Komenda interpretacji LLM fundamentalnych.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "fund_llm_interpretations_list")
        
        # Parse argumentów dla paginacji
        text_parts = self.parse_command_args(event)
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            fund_interp_table = self.db.get_factory().get_fundamental_analysis_interpretation_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz interpretacje fundamentalne LLM
            interpretations = await fund_interp_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not interpretations:
                await event.respond("💼 **Interpretacje LLM Fundamentalne**\n\n❌ Brak interpretacji do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(interpretations) > self.default_page_size
            page_interpretations = interpretations[:self.default_page_size]
            
            # Formatuj listę
            interp_text = f"💼 **Interpretacje LLM Fundamentalne - Strona {page}**\n\n"
            
            for i, interp in enumerate(page_interpretations, 1):
                item_number = offset + i
                
                # Pobierz asset info (już w wyniku JOIN)
                asset_info = ""
                if 'asset' in interp and 'quote' in interp:
                    asset_info = f" ({interp['asset']}/{interp['quote']})"
                elif 'symbol' in interp:
                    asset_info = f" ({interp['symbol']})"
                
                interp_text += f"{item_number}. 💼 Interpretacja LLM Fund #{interp['id']}{asset_info}\n"
                
                # Wyświetl kluczowe kolumny
                for key, value in interp.items():
                    if key in ['id', 'asset', 'quote', 'symbol']:
                        continue
                    if value is not None and value != '' and value != []:
                        if key == 'created_at':
                            interp_text += f"    📅 {key}: {self._format_datetime(value)}\n"
                        elif key == 'content':
                            content_text = str(value)
                            summary = content_text[:80] + "..." if len(content_text) > 80 else content_text
                            interp_text += f"    📝 {key}: {summary}\n"
                            
                            # Wykryj rekomendację
                            content_upper = content_text.upper()
                            if any(word in content_upper for word in ['BUY', 'KUPUJ', 'KPUJ', 'ZAKUP']):
                                interp_text += f"      🟢 Sygnał: BUY\n"
                            elif any(word in content_upper for word in ['SELL', 'SPRZEDAJ', 'SPRZEDAŻ']):
                                interp_text += f"      🔴 Sygnał: SELL\n"
                            elif any(word in content_upper for word in ['HOLD', 'TRZYMAJ', 'CZEKAJ']):
                                interp_text += f"      🟡 Sygnał: HOLD\n"
                        elif key == 'interpretation':
                            interpretation_text = str(value)
                            summary = interpretation_text[:100] + "..." if len(interpretation_text) > 100 else interpretation_text
                            interp_text += f"    🧠 {key}: {summary}\n"
                        elif 'id' in key and key != 'id':
                            interp_text += f"    🔗 {key}: {value}\n"
                        else:
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            interp_text += f"    📋 {key}: {value_display}\n"
                
                interp_text += "\n"
            
            # Informacja o paginacji
            if page > 1 or has_next:
                interp_text += f"📄 Strona {page}"
                if has_next:
                    interp_text += f" (więcej dostępne)"
            
            # Pagination info
            estimated_total = offset + len(page_interpretations) + (100 if has_next else 0)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_interpretations),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_interpretations)
            }
            
            # Przyciski paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "interp:fund_page",
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Po assetach", b"interp:fund_by_asset"),
                    Button.inline("📊 Szczegóły", b"interp:fund_details_menu")
                ],
                [
                    Button.inline("📈 LLM Technical", b"analysis:tech_llm_overview"),
                    Button.inline("🎯 General LLM", b"interp:general")
                ],
                [
                    Button.inline("🔄 Odśwież", f"interp:fund_page:{page}".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ])
            
            await event.respond(interp_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "fund_llm_interpretations")
            await event.respond(error_msg)
    
    @RD.cmd("analysis_tech_llm_interpretations", aliases=["tech_llm_interp", "tli"])
    async def analysis_tech_llm_interpretations_command(self, event):
        """
        Komenda interpretacji LLM technicznych.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "tech_llm_interpretations_list")
        
        # Parse argumentów dla paginacji
        text_parts = self.parse_command_args(event)
        page = 1
        
        if len(text_parts) >= 2:
            try:
                page = int(text_parts[1])
                page = max(1, page)
            except ValueError:
                pass
        
        try:
            await self.init_database()
            tech_interp_table = self.db.get_factory().get_technical_analysis_interpretation_table()
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz interpretacje techniczne LLM
            interpretations = await tech_interp_table.get_all(limit=self.default_page_size + 1, offset=offset)
            
            if not interpretations:
                await event.respond("📈 **Interpretacje LLM Techniczne**\n\n❌ Brak interpretacji do wyświetlenia.")
                return
            
            # Sprawdź czy są następne strony
            has_next = len(interpretations) > self.default_page_size
            page_interpretations = interpretations[:self.default_page_size]
            
            # Formatuj listę
            interp_text = f"📈 **Interpretacje LLM Techniczne - Strona {page}**\n\n"
            
            for i, interp in enumerate(page_interpretations, 1):
                item_number = offset + i
                
                # Pobierz asset info
                asset_info = ""
                if 'asset' in interp and 'quote' in interp:
                    asset_info = f" ({interp['asset']}/{interp['quote']})"
                elif 'symbol' in interp:
                    asset_info = f" ({interp['symbol']})"
                
                interp_text += f"{item_number}. 📈 Interpretacja LLM Tech #{interp['id']}{asset_info}\n"
                
                # Wyświetl kluczowe kolumny
                for key, value in interp.items():
                    if key in ['id', 'asset', 'quote', 'symbol']:
                        continue
                    if value is not None and value != '' and value != []:
                        if key == 'created_at':
                            interp_text += f"    📅 {key}: {self._format_datetime(value)}\n"
                        elif key == 'content':
                            content_text = str(value)
                            summary = content_text[:80] + "..." if len(content_text) > 80 else content_text
                            interp_text += f"    📝 {key}: {summary}\n"
                            
                            # Wykryj rekomendację
                            content_upper = content_text.upper()
                            if any(word in content_upper for word in ['BUY', 'KUPUJ', 'KPUJ', 'ZAKUP']):
                                interp_text += f"      🟢 Sygnał: BUY\n"
                            elif any(word in content_upper for word in ['SELL', 'SPRZEDAJ', 'SPRZEDAŻ']):
                                interp_text += f"      🔴 Sygnał: SELL\n"
                            elif any(word in content_upper for word in ['HOLD', 'TRZYMAJ', 'CZEKAJ']):
                                interp_text += f"      🟡 Sygnał: HOLD\n"
                        elif key == 'interpretation':
                            interpretation_text = str(value)
                            summary = interpretation_text[:100] + "..." if len(interpretation_text) > 100 else interpretation_text
                            interp_text += f"    🧠 {key}: {summary}\n"
                        elif key == 'patterns_analysis':
                            patterns_text = str(value)
                            summary = patterns_text[:100] + "..." if len(patterns_text) > 100 else patterns_text
                            interp_text += f"    📊 {key}: {summary}\n"
                        elif 'id' in key and key != 'id':
                            interp_text += f"    🔗 {key}: {value}\n"
                        else:
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            interp_text += f"    📋 {key}: {value_display}\n"
                
                interp_text += "\n"
            
            # Informacja o paginacji
            if page > 1 or has_next:
                interp_text += f"📄 Strona {page}"
                if has_next:
                    interp_text += f" (więcej dostępne)"
            
            # Pagination info
            estimated_total = offset + len(page_interpretations) + (100 if has_next else 0)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(estimated_total, self.default_page_size),
                'total_items': estimated_total,
                'items_on_page': len(page_interpretations),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_interpretations)
            }
            
            # Przyciski paginacji
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                "interp:tech_page",
                ""
            )
            
            # Dodatkowe opcje
            buttons.extend([
                [
                    Button.inline("🔍 Po assetach", b"interp:tech_by_asset"),
                    Button.inline("📊 Szczegóły", b"interp:tech_details_menu")
                ],
                [
                    Button.inline("💼 LLM Fundamental", b"analysis:fund_llm_overview"),
                    Button.inline("🎯 General LLM", b"interp:general")
                ],
                [
                    Button.inline("🔄 Odśwież", f"interp:tech_page:{page}".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ])
            
            await event.respond(interp_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "tech_llm_interpretations")
            await event.respond(error_msg)
    
    # ===================
    # COMMANDS - INTERPRETATIONS BY ASSET
    # ===================
    
    @RD.cmd("analysis_interpretations_asset", aliases=["interp_asset", "ia"])
    async def analysis_interpretations_asset_command(self, event):
        """
        Komenda bezpośredniego dostępu do interpretacji dla konkretnego assetu.
        Format: /analysis_interpretations_asset SYMBOL [page]
        Przykłady: /analysis_interpretations_asset BTC-USDT, /analysis_interpretations_asset ETH-USDT 2
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Parse argumentów
        text_parts = self.parse_command_args(event)
        if len(text_parts) < 2:
            await event.respond(
                "🧠 **Interpretacje po Asset**\n\n"
                "**Format:** `/analysis_interpretations_asset SYMBOL`\n\n"
                "**Przykłady:**\n"
                "• `/analysis_interpretations_asset BTC-USDT`\n"
                "• `/analysis_interpretations_asset ETH-USDT`\n\n"
                "**Format symbolu:** ASSET-QUOTE (np. BTC-USDT, ETH-BTC)"
            )
            return
        
        symbol = text_parts[1].upper().replace('-', '/')  # BTC-USDT -> BTC/USDT
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Parse asset/quote z symbolu
            if '/' not in symbol:
                await event.respond("❌ Nieprawidłowy format symbolu. Użyj: ASSET-QUOTE (np. BTC-USDT)")
                return
            
            asset, quote = symbol.split('/', 1)
            asset_record = await assets_table.get_by_asset_quote(asset, quote)
            
            if not asset_record:
                await event.respond(f"❌ Asset {symbol} nie został znaleziony w bazie danych.")
                return
            
            await self.log_action(user.id, "interpretations_by_asset_command", {"symbol": symbol})
            
            # Przekieruj do istniejącego handlera interpretacji dla assetu
            # Symuluj event callback z asset_id
            event.data = f"interp:asset:{asset_record['id']}".encode()
            await self.interpretations_asset_callback(event)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "interpretations_by_asset")
            await event.respond(error_msg)
    
    # ===================
    # CALLBACK QUERIES - ANALYSIS PAGINATION
    # ===================
    
    @RD.cb(b"analysis:fund_page:")
    async def analysis_fund_page_callback(self, event):
        """Handler paginacji dla analiz fundamentalnych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony**\n\n"
                    "Aby przejść do konkretnej strony analiz fundamentalnych, wyślij:\n"
                    "`/analysis_fundamental [numer_strony]`\n\n"
                    "**Przykłady:**\n"
                    "• `/analysis_fundamental 3` - przejdź do strony 3\n"
                    "• `/analysis_fundamental 1` - powrót do pierwszej strony"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"analysis:fund_page:1")],
                    [Button.inline("🔙 Wstecz", b"analysis:fund_page:1")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            event.raw_text = f"/analysis_fundamental {page}"
            await self.analysis_fundamental_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in fund analysis pagination: {e}")
    
    @RD.cb(b"analysis:tech_page:")
    async def analysis_tech_page_callback(self, event):
        """Handler paginacji dla analiz technicznych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony**\n\n"
                    "Aby przejść do konkretnej strony analiz technicznych, wyślij:\n"
                    "`/analysis_technical [numer_strony]`\n\n"
                    "**Przykłady:**\n"
                    "• `/analysis_technical 3` - przejdź do strony 3\n"
                    "• `/analysis_technical 1` - powrót do pierwszej strony"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"analysis:tech_page:1")],
                    [Button.inline("🔙 Wstecz", b"analysis:tech_page:1")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            event.raw_text = f"/analysis_technical {page}"
            await self.analysis_technical_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in tech analysis pagination: {e}")
    
    @RD.cb(b"analysis:patterns_page:")
    async def analysis_patterns_page_callback(self, event):
        """Handler paginacji dla wzorców harmonicznych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony**\n\n"
                    "Aby przejść do konkretnej strony wzorców harmonicznych, wyślij:\n"
                    "`/analysis_technical_harmonic_patterns [numer_strony]`\n\n"
                    "**Przykłady:**\n"
                    "• `/analysis_technical_harmonic_patterns 3` - przejdź do strony 3\n"
                    "• `/analysis_technical_harmonic_patterns 1` - powrót do pierwszej strony"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"analysis:patterns_page:1")],
                    [Button.inline("🔙 Wstecz", b"analysis:patterns_page:1")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            event.raw_text = f"/analysis_technical_harmonic_patterns {page}"
            await self.analysis_harmonic_patterns_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in patterns pagination: {e}")
    
    @RD.cb(b"interp:general_page:")
    async def interpretations_page_callback(self, event):
        """Handler paginacji dla interpretacji generalnych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony**\n\n"
                    "Aby przejść do konkretnej strony interpretacji, wyślij:\n"
                    "`/analysis_interpretations [numer_strony]`\n\n"
                    "**Przykłady:**\n"
                    "• `/analysis_interpretations 3` - przejdź do strony 3\n"
                    "• `/analysis_interpretations 1` - powrót do pierwszej strony"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"interp:general_page:1")],
                    [Button.inline("🔙 Wstecz", b"interp:general_page:1")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            event.raw_text = f"/analysis_interpretations {page}"
            await self.analysis_interpretations_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in interpretations pagination: {e}")
    
    @RD.cb(b"interp:fund_page:")
    async def interpretations_fund_page_callback(self, event):
        """Handler paginacji dla interpretacji LLM fundamentalnych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony (LLM Fundamentalne)**\n\n"
                    "Aby przejść do konkretnej strony interpretacji, wyślij:\n"
                    "`/analysis_fund_llm_interpretations [numer_strony]`\n\n"
                    "**Przykłady:**\n"
                    "• `/analysis_fund_llm_interpretations 3` - przejdź do strony 3\n"
                    "• `/analysis_fund_llm_interpretations 1` - powrót do pierwszej strony"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"interp:fund_page:1")],
                    [Button.inline("🔙 Wstecz", b"interp:fund_page:1")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            event.raw_text = f"/analysis_fund_llm_interpretations {page}"
            await self.analysis_fund_llm_interpretations_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in fund llm interpretations pagination: {e}")
    
    @RD.cb(b"interp:tech_page:")
    async def interpretations_tech_page_callback(self, event):
        """Handler paginacji dla interpretacji LLM technicznych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony (LLM Techniczne)**\n\n"
                    "Aby przejść do konkretnej strony interpretacji, wyślij:\n"
                    "`/analysis_tech_llm_interpretations [numer_strony]`\n\n"
                    "**Przykłady:**\n"
                    "• `/analysis_tech_llm_interpretations 3` - przejdź do strony 3\n"
                    "• `/analysis_tech_llm_interpretations 1` - powrót do pierwszej strony"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"interp:tech_page:1")],
                    [Button.inline("🔙 Wstecz", b"interp:tech_page:1")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            event.raw_text = f"/analysis_tech_llm_interpretations {page}"
            await self.analysis_tech_llm_interpretations_command(event)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in tech llm interpretations pagination: {e}")
    
    @RD.cb(b"analysis:fund_asset_page:")
    async def analysis_fund_asset_page_callback(self, event):
        """Handler paginacji dla analiz fundamentalnych per asset."""
        try:
            callback_data = event.data.decode()
            logger.debug(f"Fund asset pagination callback: {callback_data}")
            
            # Ignoruj kliknięcia na informację o stronie (page_info)
            if "page_info" in callback_data:
                await event.answer("ℹ️ To jest informacja o bieżącej stronie", alert=False)
                return
            
            # Sprawdź czy to przycisk jump
            if ":jump:" in callback_data:
                parts = callback_data.split(":")
                asset_id = int(parts[-1])  # asset_id na końcu
                
                # Pobierz informacje o assecie dla instrukcji
                await self.init_database()
                assets_table = self.db.get_factory().get_assets_table()
                asset = await assets_table.get_by_id(asset_id)
                asset_symbol = f"{asset['asset']}/{asset['quote']}" if asset else f"Asset #{asset_id}"
                
                jump_help = (
                    f"🔢 **Przejdź do strony - {asset_symbol}**\n\n"
                    f"Analizy fundamentalne dla tego assetu możesz przeglądać używając przycisków paginacji.\n\n"
                    f"**Alternatywnie:**\n"
                    f"• Użyj przycisków ⬅️ Poprzednia / Następna ➡️\n"
                    f"• Lub wróć do głównej listy i użyj `/analysis_fundamental [strona]`"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", f"analysis:fund_asset_page:page:1:{asset_id}".encode())],
                    [Button.inline("🔙 Wstecz", b"analysis:fund_overview")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            parts = callback_data.split(":")
            logger.debug(f"Callback parts: {parts}")
            
            # Format: analysis:fund_asset_page:page:2:123
            # Ale mogą być też błędne formaty z podwójnymi dwukropkami
            if len(parts) < 5:
                logger.error(f"Invalid callback format: {callback_data}, parts: {parts}")
                await event.answer("❌ Nieprawidłowy format callbacku", alert=True)
                return
            
            # Parsowanie z zabezpieczeniem na puste stringi (podwójne dwukropki)
            try:
                page = int(parts[3]) if parts[3] else 1      # parts[3] = page number
                asset_id = int(parts[4]) if parts[4] else (int(parts[5]) if len(parts) > 5 and parts[5] else None)  # parts[4] = asset_id
                
                if asset_id is None:
                    logger.error(f"Cannot extract asset_id from callback: {callback_data}")
                    await event.answer("❌ Nie można wyodrębnić ID assetu", alert=True)
                    return
                    
            except (ValueError, IndexError) as parse_error:
                logger.error(f"Error parsing callback: {callback_data}, error: {parse_error}")
                await event.answer("❌ Błąd parsowania callbacku", alert=True)
                return
            
            logger.debug(f"Parsed: page={page}, asset_id={asset_id}")
            await self._show_analysis_for_asset(event, "fundamental", page, asset_id)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in fund asset pagination: {e}, callback_data: {callback_data if 'callback_data' in locals() else 'N/A'}")
    
    @RD.cb(b"analysis:tech_asset_page:")
    async def analysis_tech_asset_page_callback(self, event):
        """Handler paginacji dla analiz technicznych per asset."""
        try:
            callback_data = event.data.decode()
            logger.debug(f"Tech asset pagination callback: {callback_data}")
            
            # Ignoruj kliknięcia na informację o stronie (page_info)
            if "page_info" in callback_data:
                await event.answer("ℹ️ To jest informacja o bieżącej stronie", alert=False)
                return
            
            # Sprawdź czy to przycisk jump
            if ":jump:" in callback_data:
                parts = callback_data.split(":")
                asset_id = int(parts[-1])  # asset_id na końcu
                
                # Pobierz informacje o assecie dla instrukcji
                await self.init_database()
                assets_table = self.db.get_factory().get_assets_table()
                asset = await assets_table.get_by_id(asset_id)
                asset_symbol = f"{asset['asset']}/{asset['quote']}" if asset else f"Asset #{asset_id}"
                
                jump_help = (
                    f"🔢 **Przejdź do strony - {asset_symbol}**\n\n"
                    f"Analizy techniczne dla tego assetu możesz przeglądać używając przycisków paginacji.\n\n"
                    f"**Alternatywnie:**\n"
                    f"• Użyj przycisków ⬅️ Poprzednia / Następna ➡️\n"
                    f"• Lub wróć do głównej listy i użyj `/analysis_technical [strona]`"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", f"analysis:tech_asset_page:page:1:{asset_id}".encode())],
                    [Button.inline("🔙 Wstecz", b"analysis:tech_overview")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            parts = callback_data.split(":")
            logger.debug(f"Callback parts: {parts}")
            
            # Format: analysis:tech_asset_page:page:2:123
            if len(parts) < 5:
                logger.error(f"Invalid callback format: {callback_data}, parts: {parts}")
                await event.answer("❌ Nieprawidłowy format callbacku", alert=True)
                return
            
            # Parsowanie z zabezpieczeniem na puste stringi (podwójne dwukropki)
            try:
                page = int(parts[3]) if parts[3] else 1
                asset_id = int(parts[4]) if parts[4] else (int(parts[5]) if len(parts) > 5 and parts[5] else None)
                
                if asset_id is None:
                    logger.error(f"Cannot extract asset_id from callback: {callback_data}")
                    await event.answer("❌ Nie można wyodrębnić ID assetu", alert=True)
                    return
                    
            except (ValueError, IndexError) as parse_error:
                logger.error(f"Error parsing callback: {callback_data}, error: {parse_error}")
                await event.answer("❌ Błąd parsowania callbacku", alert=True)
                return
            
            logger.debug(f"Parsed: page={page}, asset_id={asset_id}")
            await self._show_analysis_for_asset(event, "technical", page, asset_id)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in tech asset pagination: {e}, callback_data: {callback_data if 'callback_data' in locals() else 'N/A'}")
    
    @RD.cb(b"analysis:patterns_asset_page:")
    async def analysis_patterns_asset_page_callback(self, event):
        """Handler paginacji dla wzorców harmonicznych per asset."""
        try:
            callback_data = event.data.decode()
            logger.debug(f"Patterns asset pagination callback: {callback_data}")
            
            # Ignoruj kliknięcia na informację o stronie (page_info)
            if "page_info" in callback_data:
                await event.answer("ℹ️ To jest informacja o bieżącej stronie", alert=False)
                return
            
            # Sprawdź czy to przycisk jump
            if ":jump:" in callback_data:
                parts = callback_data.split(":")
                asset_id = int(parts[-1])  # asset_id na końcu
                
                # Pobierz informacje o assecie dla instrukcji
                await self.init_database()
                assets_table = self.db.get_factory().get_assets_table()
                asset = await assets_table.get_by_id(asset_id)
                asset_symbol = f"{asset['asset']}/{asset['quote']}" if asset else f"Asset #{asset_id}"
                
                jump_help = (
                    f"🔢 **Przejdź do strony - {asset_symbol}**\n\n"
                    f"Wzorce harmoniczne dla tego assetu możesz przeglądać używając przycisków paginacji.\n\n"
                    f"**Alternatywnie:**\n"
                    f"• Użyj przycisków ⬅️ Poprzednia / Następna ➡️\n"
                    f"• Lub wróć do głównej listy i użyj `/analysis_technical_harmonic_patterns [strona]`"
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", f"analysis:patterns_asset_page:page:1:{asset_id}".encode())],
                    [Button.inline("🔙 Wstecz", b"analysis:patterns_overview")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            parts = callback_data.split(":")
            logger.debug(f"Callback parts: {parts}")
            
            # Format: analysis:patterns_asset_page:page:2:123
            if len(parts) < 5:
                logger.error(f"Invalid callback format: {callback_data}, parts: {parts}")
                await event.answer("❌ Nieprawidłowy format callbacku", alert=True)
                return
            
            # Parsowanie z zabezpieczeniem na puste stringi (podwójne dwukropki)
            try:
                page = int(parts[3]) if parts[3] else 1
                asset_id = int(parts[4]) if parts[4] else (int(parts[5]) if len(parts) > 5 and parts[5] else None)
                
                if asset_id is None:
                    logger.error(f"Cannot extract asset_id from callback: {callback_data}")
                    await event.answer("❌ Nie można wyodrębnić ID assetu", alert=True)
                    return
                    
            except (ValueError, IndexError) as parse_error:
                logger.error(f"Error parsing callback: {callback_data}, error: {parse_error}")
                await event.answer("❌ Błąd parsowania callbacku", alert=True)
                return
            
            logger.debug(f"Parsed: page={page}, asset_id={asset_id}")
            await self._show_analysis_for_asset(event, "patterns", page, asset_id)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji", alert=True)
            logger.error(f"Error in patterns asset pagination: {e}, callback_data: {callback_data if 'callback_data' in locals() else 'N/A'}")
    
    # ===================
    # CALLBACK QUERIES - ANALYSIS BY ASSET
    # ===================
    
    @RD.cb(b"analysis:fund:")
    async def analysis_fund_asset_callback(self, event):
        """Pokazuje analizy fundamentalne dla konkretnego assetu."""
        await self._show_analysis_for_asset(event, "fundamental")
    
    @RD.cb(b"analysis:tech:")
    async def analysis_tech_asset_callback(self, event):
        """Pokazuje analizy techniczne dla konkretnego assetu."""
        await self._show_analysis_for_asset(event, "technical")
    
    @RD.cb(b"analysis:patterns:")
    async def analysis_patterns_asset_callback(self, event):
        """Pokazuje wzorce harmoniczne dla konkretnego assetu."""
        await self._show_analysis_for_asset(event, "patterns")
    
    async def _show_analysis_for_asset(self, event, analysis_type: str, page: int = 1, asset_id_override: int = None):
        """
        Helper method do wyświetlania analiz dla konkretnego assetu.
        
        Args:
            event: Event Telegram
            analysis_type: Typ analizy ('fundamental', 'technical', 'patterns')
            page: Numer strony (domyślnie 1)
            asset_id_override: Jeśli podane, używa tego asset_id zamiast parsowania z callback
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            if asset_id_override:
                asset_id = asset_id_override
            else:
                # Extract asset ID z callback data
                callback_data = event.data.decode()
                parts = callback_data.split(":")
                
                # Różne formaty callbacków:
                # Normal: analysis:fund:123 -> asset_id = parts[-1] = "123"
                # Pagination: analysis:fund_asset_page:page:2:123 -> asset_id = parts[-1] = "123"  
                if "page" in callback_data and len(parts) >= 5:
                    # Format paginacji: analysis:fund_asset_page:page:2:123
                    asset_id = int(parts[4])  # asset_id na pozycji 4
                else:
                    # Format zwykły: analysis:fund:123  
                    asset_id = int(parts[-1])
            
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Pobierz informacje o assecie
            asset = await assets_table.get_by_id(asset_id)
            if not asset:
                await event.answer("❌ Asset nie znaleziony", alert=True)
                return
            
            asset_symbol = f"{asset['asset']}/{asset['quote']}"
            
            # Wybierz odpowiednią tabelę
            if analysis_type == "fundamental":
                table = self.db.get_factory().get_fundamental_analysis_table()
                title = "💼 Analizy Fundamentalne"
                callback_prefix = "analysis:fund"
            elif analysis_type == "technical":
                # Używamy harmonic_patterns jako tabelę analiz technicznych
                table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
                title = "📈 Analizy Techniczne"
                callback_prefix = "analysis:tech"
            else:  # patterns
                table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
                title = "🔄 Wzorce Harmoniczne"
                callback_prefix = "analysis:patterns"
            
            # Oblicz offset dla paginacji
            offset = (page - 1) * self.default_page_size
            
            # Pobierz analizy dla assetu z marginesem dla sprawdzenia następnej strony
            analyses = await table.get_by_asset_id(asset_id, limit=self.default_page_size + 1, offset=offset)
            
            if not analyses:
                await event.edit(
                    f"{title} - {asset_symbol}\n\n❌ Brak analiz dla tego assetu na stronie {page}.",
                    buttons=[
                        [Button.inline("🔙 Wstecz", f"{callback_prefix}_overview".encode())],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Sprawdź czy są następne strony
            has_next = len(analyses) > self.default_page_size
            page_analyses = analyses[:self.default_page_size]
            
            # Formatuj wyniki z pełnym formatowaniem jak w głównych komendach
            results_text = f"{title} - {asset_symbol} - Strona {page}\n\n"
            
            for i, analysis in enumerate(page_analyses, 1):
                item_number = offset + i
                results_text += f"{item_number}. 📊 Analiza #{analysis['id']}\n"
                
                # Formatowanie specyficzne dla typu analizy
                if analysis_type == "fundamental":
                    # Formatowanie jak w analysis_fundamental_command
                    for key, value in analysis.items():
                        if key in ['id', 'assets', 'quotes', 'asset_ids', 'content']:
                            continue
                        if value is not None and value != '' and value != []:
                            if key == 'created_at':
                                results_text += f"    📅 {key}: {self._format_datetime(value)}\n"
                            elif key == 'timestamp':
                                results_text += f"    ⏰ {key}: {value}\n"
                            else:
                                if isinstance(value, str) and len(value) > 50:
                                    value_display = value[:50] + "..."
                                else:
                                    value_display = value
                                results_text += f"    📋 {key}: {value_display}\n"
                    
                    # Content dict dla fundamental
                    content = analysis.get('content', {})
                    if isinstance(content, dict) and content:
                        results_text += f"    📄 **CONTENT:**\n"
                        displayed_keys = 0
                        for key, value in content.items():
                            if displayed_keys >= 10:
                                results_text += f"      • ... (i {len(content) - displayed_keys} więcej kluczy)\n"
                                break
                            if value is not None and value != '' and value != []:
                                if isinstance(value, str) and len(value) > 150:
                                    value_display = value[:150] + "..."
                                elif isinstance(value, (list, dict)):
                                    value_display = str(value)[:150] + "..." if len(str(value)) > 150 else str(value)
                                else:
                                    value_display = str(value)
                                results_text += f"      • {key}: {value_display}\n"
                                displayed_keys += 1
                
                elif analysis_type in ["technical", "patterns"]:
                    # Formatowanie jak w analysis_technical_command/patterns_command
                    for key, value in analysis.items():
                        if key in ['id', 'asset', 'quote', 'ta_object_json']:
                            continue
                        if value is not None and value != '' and value != []:
                            if 'timestamp' in key.lower():
                                from datetime import datetime
                                try:
                                    dt = datetime.fromtimestamp(value / 1000 if value > 1e10 else value)
                                    results_text += f"    📅 {key}: {dt.strftime('%Y-%m-%d %H:%M')}\n"
                                except (ValueError, OSError):
                                    results_text += f"    📅 {key}: {value}\n"
                            else:
                                if isinstance(value, str) and len(value) > 50:
                                    value_display = value[:50] + "..."
                                else:
                                    value_display = value
                                results_text += f"    📋 {key}: {value_display}\n"
                    
                    # TA_OBJECT_JSON dict dla technical/patterns
                    ta_object = analysis.get('ta_object_json', {})
                    if isinstance(ta_object, dict) and ta_object:
                        results_text += f"    📄 **TA_OBJECT_JSON:**\n"
                        displayed_keys = 0
                        for key, value in ta_object.items():
                            if displayed_keys >= 10:
                                results_text += f"      • ... (i {len(ta_object) - displayed_keys} więcej kluczy)\n"
                                break
                            if value is not None and value != '' and value != []:
                                if isinstance(value, str) and len(value) > 150:
                                    value_display = value[:150] + "..."
                                elif isinstance(value, (list, dict)):
                                    value_display = str(value)[:150] + "..." if len(str(value)) > 150 else str(value)
                                else:
                                    value_display = str(value)
                                results_text += f"      • {key}: {value_display}\n"
                                displayed_keys += 1
                
                results_text += "\n"
            
            # Pobierz dokładną liczbę rekordów dla tego assetu dla poprawnej paginacji
            if analysis_type == "fundamental":
                total_count = await table.count_by_asset(asset_id)
            else:
                # Dla technical/patterns używamy szacowania (bo nie mamy jeszcze count_by_asset)
                total_count = offset + len(page_analyses) + (100 if has_next else 0)
            
            # Informacja o paginacji
            if page > 1 or has_next:
                results_text += f"📄 Strona {page}"
                if has_next:
                    results_text += f" (więcej dostępne)"
            
            # Pagination info z dokładną liczbą (dla fundamental) lub szacowaną (dla tech/patterns)
            pagination_info = {
                'current_page': page,
                'total_pages': PaginationHelper.calculate_pages(total_count, self.default_page_size),
                'total_items': total_count,
                'items_on_page': len(page_analyses),
                'has_previous': page > 1,
                'has_next': has_next,
                'start_idx': offset,
                'end_idx': offset + len(page_analyses)
            }
            
            # Przyciski paginacji
            pagination_callback_prefix = f"analysis:{callback_prefix.split(':')[1]}_asset_page"
            logger.debug(f"Creating pagination buttons with prefix: {pagination_callback_prefix}, asset_id: {asset_id}")
            
            buttons = PaginationHelper.create_pagination_buttons(
                pagination_info, 
                pagination_callback_prefix,
                f"{asset_id}"  # Usunięto ':' na początku
            )
            
            # Dodatkowe opcje nawigacji
            buttons.extend([
                [Button.inline("🔙 Wstecz", f"{callback_prefix}_overview".encode())],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            # Sprawdź czy treść się zmieniła (uniknięcie MessageNotModifiedError)
            try:
                await event.edit(results_text, buttons=buttons)
            except Exception as edit_error:
                if "Content of the message was not modified" in str(edit_error) or "MessageNotModifiedError" in str(edit_error):
                    logger.debug(f"Message content unchanged for asset {asset_id}, page {page}")
                    # Nie robimy nic - wiadomość już ma prawidłową treść
                else:
                    # Inne błędy - podnieś dalej
                    raise
            
            await self.log_action(user.id, f"{analysis_type}_analysis_for_asset", {
                "asset_id": asset_id, 
                "asset_symbol": asset_symbol,
                "analyses_count": len(analyses)
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, f"{analysis_type}_analysis_for_asset")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - INTERPRETATIONS
    # ===================
    
    @RD.cb(b"interp:general")
    async def interpretations_general_callback(self, event):
        """Pokazuje interpretacje generalne."""
        # Ustawić raw_text dla callback query, aby analysis_interpretations_command mogło parsować argumenty
        await self.analysis_interpretations_command(event)
    
    @RD.cb(b"interp:asset:")
    async def interpretations_asset_callback(self, event):
        """Pokazuje interpretacje dla konkretnego assetu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract asset ID
            callback_data = event.data.decode()
            asset_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            interp_table = self.db.get_factory().get_general_interpretation_table()
            
            # Pobierz asset
            asset = await assets_table.get_by_id(asset_id)
            if not asset:
                await event.answer("❌ Asset nie znaleziony", alert=True)
                return
            
            # Pobierz interpretacje dla assetu
            interpretations = await interp_table.get_by_asset_id(asset_id, limit=20)
            
            asset_symbol = f"{asset['asset']}/{asset['quote']}"
            
            if not interpretations:
                await event.edit(
                    f"🧠 **Interpretacje - {asset_symbol}**\n\n❌ Brak interpretacji dla tego assetu.",
                    buttons=[
                        [Button.inline("🔙 Wszystkie interpretacje", b"interp:general")],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Formatuj wyniki
            interp_text = f"🧠 **Interpretacje - {asset_symbol}**\n\n"
            interp_text += f"✅ Znaleziono {len(interpretations)} interpretacji:\n\n"
            
            for i, interp in enumerate(interpretations[:8], 1):
                interp_text += f"{i}. 🧠 Interpretacja #{interp['id']}\n"
                
                # Wyświetl WSZYSTKIE kolumny z bazy danych
                for key, value in interp.items():
                    if key in ['id']:  # Pomijamy już wyświetlone
                        continue
                    if value is not None and value != '' and value != []:
                        if key == 'created_at':
                            interp_text += f"    📅 {key}: {self._format_datetime(value)}\n"
                        elif key == 'content':
                            # Skróć treść content bardziej agresywnie
                            content_text = str(value)
                            summary = content_text[:80] + "..." if len(content_text) > 80 else content_text
                            interp_text += f"    📝 {key}: {summary}\n"
                            
                            # Spróbuj wykryć rekomendację z treści
                            content_upper = content_text.upper()
                            if any(word in content_upper for word in ['BUY', 'KUPUJ', 'KPUJ', 'ZAKUP']):
                                interp_text += f"      🟢 Sygnał: BUY\n"
                            elif any(word in content_upper for word in ['SELL', 'SPRZEDAJ', 'SPRZEDAŻ']):
                                interp_text += f"      🔴 Sygnał: SELL\n"
                            elif any(word in content_upper for word in ['HOLD', 'TRZYMAJ', 'CZEKAJ']):
                                interp_text += f"      🟡 Sygnał: HOLD\n"
                        elif key == 'investment_strategy_name':
                            interp_text += f"    📊 {key}: {value}\n"
                        elif 'id' in key and key != 'id':  # powiązane ID
                            interp_text += f"    🔗 {key}: {value}\n"
                        else:
                            # Ograniczenie długich wartości kolumn
                            if isinstance(value, str) and len(value) > 50:
                                value_display = value[:50] + "..."
                            else:
                                value_display = value
                            interp_text += f"    📋 {key}: {value_display}\n"
                
                interp_text += "\n"
            
            if len(interpretations) > 8:
                interp_text += f"... i {len(interpretations) - 8} więcej"
            
            # Przyciski szczegółów
            buttons = []
            details_buttons = []
            
            for interp in interpretations[:6]:
                interp_id = interp['id']
                details_buttons.append(
                    Button.inline(f"📊 #{interp_id}", f"interp:details:{interp_id}".encode())
                )
            
            # Podziel na wiersze po 3
            for i in range(0, len(details_buttons), 3):
                buttons.append(details_buttons[i:i+3])
            
            buttons.extend([
                [Button.inline("🔙 Wszystkie interpretacje", b"interp:general")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ])
            
            await event.edit(interp_text, buttons=buttons)
            await self.log_action(user.id, "interpretations_for_asset", {
                "asset_id": asset_id, 
                "asset_symbol": asset_symbol,
                "interpretations_count": len(interpretations)
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "interpretations_for_asset")
            await event.edit(error_msg)
    
    @RD.cb(b"interp:details:")
    async def interpretation_details_callback(self, event):
        """
        Pokazuje szczegółową interpretację z możliwością przełączania między typami.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract interpretation ID
            callback_data = event.data.decode()
            interp_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            
            # Pobierz interpretację generalną
            interp_table = self.db.get_factory().get_general_interpretation_table()
            interpretation = await interp_table.get_by_id(interp_id)
            
            if not interpretation:
                await event.answer("❌ Interpretacja nie znaleziona", alert=True)
                return
            
            # Pobierz informacje o assecie
            asset_info = ""
            if 'asset_id' in interpretation and interpretation['asset_id']:
                try:
                    assets_table = self.db.get_factory().get_assets_table()
                    asset = await assets_table.get_by_id(interpretation['asset_id'])
                    if asset:
                        asset_info = f" ({asset['asset']}/{asset['quote']})"
                except:
                    pass
            
            # Formatuj szczegóły interpretacji generalnej
            details_text = f"🧠 **Interpretacja Generalna #{interp_id}**{asset_info}\n\n"
            
            # Wykryj rekomendację z content
            if 'content' in interpretation and interpretation['content']:
                content_upper = str(interpretation['content']).upper()
                if any(word in content_upper for word in ['BUY', 'KUPUJ', 'KPUJ', 'ZAKUP']):
                    details_text += f"🟢 **Sygnał:** BUY wykryty w treści\n\n"
                elif any(word in content_upper for word in ['SELL', 'SPRZEDAJ', 'SPRZEDAŻ']):
                    details_text += f"🔴 **Sygnał:** SELL wykryty w treści\n\n"
                elif any(word in content_upper for word in ['HOLD', 'TRZYMAJ', 'CZEKAJ']):
                    details_text += f"🟡 **Sygnał:** HOLD wykryty w treści\n\n"
            
            # Używaj content zamiast interpretation_summary
            if 'content' in interpretation and interpretation['content']:
                details_text += f"📝 **Treść:**\n{str(interpretation['content'])[:500]}\n\n"
            
            details_text += f"📅 **Data utworzenia:** {self._format_datetime(interpretation.get('created_at', ''))}\n"
            
            # Przyciski przełączania między typami interpretacji
            buttons = [
                [
                    Button.inline("🧠 Generalna", f"interp:switch:general:{interp_id}".encode()),
                    Button.inline("💼 Fundamentalna", f"interp:switch:fundamental:{interp_id}".encode())
                ],
                [
                    Button.inline("📈 Techniczna", f"interp:switch:technical:{interp_id}".encode()),
                    Button.inline("📷 Chart images", f"interp:charts:{interp_id}".encode())
                ],
                [
                    Button.inline("🔄 Odśwież", f"interp:details:{interp_id}".encode()),
                    Button.inline("🔙 Lista", b"interp:general")
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(details_text, buttons=buttons)
            await self.log_action(user.id, "interpretation_details_view", {"interpretation_id": interp_id})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "interpretation_details")
            await event.edit(error_msg)
    
    @RD.cb(b"interp:switch:")
    async def interpretation_switch_callback(self, event):
        """
        Przełącza między różnymi typami interpretacji.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract switch type and interpretation ID
            callback_data = event.data.decode()
            parts = callback_data.split(":")
            switch_type = parts[2]  # general, fundamental, technical
            interp_id = int(parts[3])
            
            await self.init_database()
            
            if switch_type == "general":
                await self._show_general_interpretation_details(event, interp_id)
            elif switch_type == "fundamental":
                await self._show_fundamental_interpretation_details(event, interp_id)
            elif switch_type == "technical":
                await self._show_technical_interpretation_details(event, interp_id)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "interpretation_switch")
            await event.edit(error_msg)
    
    async def _show_general_interpretation_details(self, event, interp_id: int):
        """Pokazuje szczegóły interpretacji generalnej."""
        interp_table = self.db.get_factory().get_general_interpretation_table()
        interpretation = await interp_table.get_by_id(interp_id)
        
        if not interpretation:
            await event.edit("❌ Interpretacja generalna nie znaleziona.")
            return
        
        # Pobierz asset info
        asset_info = await self._get_asset_info_string(interpretation.get('asset_id'))
        
        details_text = f"🧠 **Interpretacja Generalna #{interp_id}**{asset_info}\n\n"
        
        # Wykryj rekomendację z treści
        if 'content' in interpretation and interpretation['content']:
            content_upper = str(interpretation['content']).upper()
            if any(word in content_upper for word in ['BUY', 'KUPUJ', 'KPUJ', 'ZAKUP']):
                details_text += f"🟢 **Sygnał:** BUY wykryty w treści\n\n"
            elif any(word in content_upper for word in ['SELL', 'SPRZEDAJ', 'SPRZEDAŻ']):
                details_text += f"🔴 **Sygnał:** SELL wykryty w treści\n\n"
            elif any(word in content_upper for word in ['HOLD', 'TRZYMAJ', 'CZEKAJ']):
                details_text += f"🟡 **Sygnał:** HOLD wykryty w treści\n\n"
        
        if 'content' in interpretation and interpretation['content']:
            details_text += f"📝 **Treść:**\n{str(interpretation['content'])[:800]}\n\n"
        
        # Brak confidence_score w tabeli general_interpretation - usunięto tę sekcję
        
        details_text += f"📅 **Data:** {self._format_datetime(interpretation.get('created_at', ''))}"
        
        # Przyciski przełączania
        buttons = self._get_interpretation_switch_buttons(interp_id, "general")
        await event.edit(details_text, buttons=buttons)
    
    async def _show_fundamental_interpretation_details(self, event, interp_id: int):
        """Pokazuje szczegóły interpretacji fundamentalnej powiązanej z generalną."""
        # Pobierz interpretację generalną aby znaleźć powiązane analizy
        interp_table = self.db.get_factory().get_general_interpretation_table()
        general_interp = await interp_table.get_by_id(interp_id)
        
        if not general_interp or not general_interp.get('asset_id'):
            await event.edit("❌ Nie można znaleźć powiązanych analiz fundamentalnych.")
            return
        
        # Pobierz interpretacje fundamentalne dla tego samego assetu
        fund_interp_table = self.db.get_factory().get_fundamental_analysis_interpretation_table()
        fund_interpretations = await fund_interp_table.get_by_asset_id(general_interp['asset_id'], limit=5)
        
        asset_info = await self._get_asset_info_string(general_interp.get('asset_id'))
        
        if not fund_interpretations:
            details_text = f"💼 **Interpretacje Fundamentalne #{interp_id}**{asset_info}\n\n"
            details_text += "❌ Brak powiązanych interpretacji fundamentalnych dla tego assetu."
        else:
            details_text = f"💼 **Interpretacje Fundamentalne #{interp_id}**{asset_info}\n\n"
            details_text += f"✅ Znaleziono {len(fund_interpretations)} powiązanych interpretacji:\n\n"
            
            for i, fund_interp in enumerate(fund_interpretations, 1):
                details_text += f"{i}. 📊 Interpretacja #{fund_interp['id']}\n"
                if 'content' in fund_interp and fund_interp['content']:
                    summary = str(fund_interp['content'])[:100] + "..." if len(str(fund_interp['content'])) > 100 else str(fund_interp['content'])
                    details_text += f"   {summary}\n"
                details_text += f"   📅 {self._format_datetime(fund_interp.get('created_at', ''))}\n\n"
        
        # Przyciski przełączania
        buttons = self._get_interpretation_switch_buttons(interp_id, "fundamental")
        await event.edit(details_text, buttons=buttons)
    
    async def _show_technical_interpretation_details(self, event, interp_id: int):
        """Pokazuje szczegóły interpretacji technicznej z opcjami wzorców i chart images."""
        # Pobierz interpretację generalną aby znaleźć powiązane analizy
        interp_table = self.db.get_factory().get_general_interpretation_table()
        general_interp = await interp_table.get_by_id(interp_id)
        
        if not general_interp or not general_interp.get('asset_id'):
            await event.edit("❌ Nie można znaleźć powiązanych analiz technicznych.")
            return
        
        # Pobierz interpretacje techniczne dla tego samego assetu
        tech_interp_table = self.db.get_factory().get_technical_analysis_interpretation_table()
        tech_interpretations = await tech_interp_table.get_by_asset_id(general_interp['asset_id'], limit=3)
        
        asset_info = await self._get_asset_info_string(general_interp.get('asset_id'))
        
        if not tech_interpretations:
            details_text = f"📈 **Interpretacje Techniczne #{interp_id}**{asset_info}\n\n"
            details_text += "❌ Brak powiązanych interpretacji technicznych dla tego assetu."
        else:
            details_text = f"📈 **Interpretacje Techniczne #{interp_id}**{asset_info}\n\n"
            details_text += f"✅ Znaleziono {len(tech_interpretations)} powiązanych interpretacji:\n\n"
            
            for i, tech_interp in enumerate(tech_interpretations, 1):
                details_text += f"{i}. 📊 Interpretacja #{tech_interp['id']}\n"
                if 'content' in tech_interp and tech_interp['content']:
                    summary = str(tech_interp['content'])[:100] + "..." if len(str(tech_interp['content'])) > 100 else str(tech_interp['content'])
                    details_text += f"   {summary}\n"
                details_text += f"   📅 {self._format_datetime(tech_interp.get('created_at', ''))}\n\n"
        
        # Przyciski przełączania z dodatkowymi opcjami dla tech
        buttons = [
            [
                Button.inline("🧠 Generalna", f"interp:switch:general:{interp_id}".encode()),
                Button.inline("💼 Fundamentalna", f"interp:switch:fundamental:{interp_id}".encode())
            ],
            [
                Button.inline("📈 Techniczna", f"interp:switch:technical:{interp_id}".encode()),
                Button.inline("🔄 Wzorce", f"interp:patterns:{interp_id}".encode())
            ],
            [
                Button.inline("📷 Chart images", f"interp:charts:{interp_id}".encode()),
                Button.inline("🔄 Odśwież", f"interp:details:{interp_id}".encode())
            ],
            [
                Button.inline("🔙 Lista", b"interp:general"),
                Button.inline("🏠 Menu główne", b"nav:home")
            ]
        ]
        
        await event.edit(details_text, buttons=buttons)
    
    def _get_interpretation_switch_buttons(self, interp_id: int, current_type: str) -> List[List[Button]]:
        """Generuje przyciski przełączania między typami interpretacji."""
        buttons = [
            [
                Button.inline("🧠 Generalna", f"interp:switch:general:{interp_id}".encode()),
                Button.inline("💼 Fundamentalna", f"interp:switch:fundamental:{interp_id}".encode())
            ],
            [
                Button.inline("📈 Techniczna", f"interp:switch:technical:{interp_id}".encode()),
                Button.inline("📷 Chart images", f"interp:charts:{interp_id}".encode())
            ],
            [
                Button.inline("🔄 Odśwież", f"interp:details:{interp_id}".encode()),
                Button.inline("🔙 Lista", b"interp:general")
            ],
            [Button.inline("🏠 Menu główne", b"nav:home")]
        ]
        return buttons
    
    # ===================
    # CALLBACK QUERIES - CHART IMAGES
    # ===================
    
    @RD.cb(b"interp:charts:")
    async def interpretation_charts_callback(self, event):
        """
        Wysyła chart images powiązane z interpretacją w pełnej rozdzielczości.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract interpretation ID
            callback_data = event.data.decode()
            interp_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            
            # Pobierz interpretację generalną
            interp_table = self.db.get_factory().get_general_interpretation_table()
            interpretation = await interp_table.get_by_id(interp_id)
            
            if not interpretation or not interpretation.get('asset_id'):
                await event.answer("❌ Nie można znaleźć powiązanych chart images", alert=True)
                return
            
            # Pobierz analizy techniczne dla tego assetu (które mogą mieć chart images)
            # Używamy harmonic_patterns jako proxy dla analiz technicznych
            tech_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            tech_analyses = await tech_table.get_by_asset_id(interpretation['asset_id'], limit=10)
            
            # Filtruj analizy które mają chart images
            analyses_with_charts = []
            for analysis in tech_analyses:
                if 'chart_image_path' in analysis and analysis['chart_image_path']:
                    analyses_with_charts.append(analysis)
            
            if not analyses_with_charts:
                await event.edit(
                    f"📷 **Chart Images - Interpretacja #{interp_id}**\n\n"
                    f"❌ Brak dostępnych chart images dla tej interpretacji.",
                    buttons=[
                        [Button.inline("🔙 Wstecz", f"interp:details:{interp_id}".encode())],
                        [Button.inline("🏠 Menu główne", b"nav:home")]
                    ]
                )
                return
            
            # Wyślij informację o rozpoczęciu wysyłania
            loading_msg = f"📷 **Chart Images - Interpretacja #{interp_id}**\n\n"
            loading_msg += f"🔄 Wysyłam {len(analyses_with_charts)} chart image(s)...\n"
            loading_msg += f"Proszę czekać..."
            
            await event.edit(loading_msg)
            
            # Wyślij każdy chart image osobno
            sent_count = 0
            for i, analysis in enumerate(analyses_with_charts[:5], 1):  # Limit 5 obrazów
                try:
                    chart_path = analysis['chart_image_path']
                    
                    # Sprawdź czy plik istnieje (w rzeczywistości sprawdź ścieżkę)
                    if await self._send_chart_image(event, chart_path, f"Chart #{analysis['id']}"):
                        sent_count += 1
                        # Krótka przerwa między wysyłaniem obrazów
                        await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error sending chart image {analysis['id']}: {e}")
                    continue
            
            # Wyślij podsumowanie
            summary_msg = f"📷 **Chart Images - Interpretacja #{interp_id}**\n\n"
            if sent_count > 0:
                summary_msg += f"✅ Wysłano {sent_count} chart image(s) pomyślnie.\n\n"
                summary_msg += f"📊 **Analizy z chart images:**\n"
                for analysis in analyses_with_charts[:sent_count]:
                    summary_msg += f"• Analiza #{analysis['id']} - {self._format_datetime(analysis.get('created_at', ''))}\n"
            else:
                summary_msg += f"❌ Nie udało się wysłać żadnych chart images.\n"
                summary_msg += f"Możliwe przyczyny:\n"
                summary_msg += f"• Pliki nie istnieją w systemie\n"
                summary_msg += f"• Problemy z dostępem do plików\n"
                summary_msg += f"• Błędy formatów obrazów"
            
            buttons = [
                [
                    Button.inline("🔄 Spróbuj ponownie", f"interp:charts:{interp_id}".encode()),
                    Button.inline("📈 Techniczna", f"interp:switch:technical:{interp_id}".encode())
                ],
                [
                    Button.inline("🔙 Interpretacja", f"interp:details:{interp_id}".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ]
            
            await event.edit(summary_msg, buttons=buttons)
            await self.log_action(user.id, "chart_images_sent", {
                "interpretation_id": interp_id,
                "images_sent": sent_count,
                "total_available": len(analyses_with_charts)
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "chart_images")
            await event.edit(error_msg)
    
    async def _send_chart_image(self, event, chart_path: str, caption: str) -> bool:
        """
        Wysyła chart image w pełnej rozdzielczości do Telegram.
        
        Args:
            event: Event Telegram
            chart_path: Ścieżka do pliku obrazu
            caption: Opis obrazu
            
        Returns:
            bool: True jeśli wysłano pomyślnie
        """
        try:
            # W rzeczywistej implementacji sprawdź czy plik istnieje
            if not os.path.exists(chart_path):
                # Mock implementation - symuluj wysyłanie obrazu
                mock_msg = f"📷 **{caption}**\n\n"
                mock_msg += f"🔄 *Symulacja wysyłania chart image*\n"
                mock_msg += f"📁 Ścieżka: `{chart_path}`\n"
                mock_msg += f"⚠️  Plik nie istnieje w systemie (mock mode)\n\n"
                mock_msg += f"W rzeczywistej implementacji tutaj zostałby wysłany obraz w pełnej rozdzielczości."
                
                await event.respond(mock_msg)
                return True
            
            # Rzeczywiste wysyłanie obrazu (gdy plik istnieje)
            await event.client.send_file(
                event.chat_id,
                chart_path,
                caption=f"📷 **{caption}**",
                force_document=False  # Wyślij jako zdjęcie, nie jako dokument
            )
            return True
            
        except Exception as e:
            logger.error(f"Error sending chart image {chart_path}: {e}")
            
            # Wyślij informację o błędzie
            error_msg = f"❌ **Błąd wysyłania {caption}**\n\n"
            error_msg += f"📁 Ścieżka: `{chart_path}`\n"
            error_msg += f"🔥 Błąd: {str(e)[:100]}"
            
            await event.respond(error_msg)
            return False
    
    @RD.cb(b"interp:patterns:")
    async def interpretation_patterns_callback(self, event):
        """
        Pokazuje wzorce harmoniczne powiązane z interpretacją techniczną.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Extract interpretation ID
            callback_data = event.data.decode()
            interp_id = int(callback_data.split(":")[-1])
            
            await self.init_database()
            
            # Pobierz interpretację generalną
            interp_table = self.db.get_factory().get_general_interpretation_table()
            interpretation = await interp_table.get_by_id(interp_id)
            
            if not interpretation or not interpretation.get('asset_id'):
                await event.answer("❌ Nie można znaleźć powiązanych wzorców", alert=True)
                return
            
            # Pobierz wzorce harmoniczne dla tego assetu
            patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            patterns = await patterns_table.get_by_asset_id(interpretation['asset_id'], limit=10)
            
            asset_info = await self._get_asset_info_string(interpretation.get('asset_id'))
            
            if not patterns:
                patterns_text = f"🔄 **Wzorce Harmoniczne - Interpretacja #{interp_id}**{asset_info}\n\n"
                patterns_text += "❌ Brak powiązanych wzorców harmonicznych dla tego assetu."
            else:
                patterns_text = f"🔄 **Wzorce Harmoniczne - Interpretacja #{interp_id}**{asset_info}\n\n"
                patterns_text += f"✅ Znaleziono {len(patterns)} powiązanych wzorców:\n\n"
                
                for i, pattern in enumerate(patterns, 1):
                    patterns_text += f"{i}. 🔄 Wzorzec #{pattern['id']}\n"
                    
                    if 'pattern_type' in pattern and pattern['pattern_type']:
                        patterns_text += f"   🎯 Typ: {pattern['pattern_type']}\n"
                    
                    if 'status' in pattern and pattern['status']:
                        status_emoji = "✅" if pattern['status'] == 'completed' else "⏳" if pattern['status'] == 'in_progress' else "📋"
                        patterns_text += f"   {status_emoji} Status: {pattern['status']}\n"
                    
                    patterns_text += f"   📅 {self._format_datetime(pattern.get('created_at', ''))}\n\n"
            
            # Przyciski
            buttons = [
                [
                    Button.inline("📈 Techniczna", f"interp:switch:technical:{interp_id}".encode()),
                    Button.inline("📷 Chart images", f"interp:charts:{interp_id}".encode())
                ],
                [
                    Button.inline("🔙 Interpretacja", f"interp:details:{interp_id}".encode()),
                    Button.inline("🔄 Odśwież", f"interp:patterns:{interp_id}".encode())
                ],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.edit(patterns_text, buttons=buttons)
            await self.log_action(user.id, "interpretation_patterns_view", {
                "interpretation_id": interp_id,
                "patterns_count": len(patterns) if patterns else 0
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "interpretation_patterns")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - OVERVIEW ACTIONS
    # ===================
    
    @RD.cb(b"analysis:fund_overview")
    async def analysis_fund_overview_callback(self, event):
        """Przekierowanie do przeglądu analiz fundamentalnych."""
        # Ustawić raw_text dla callback query, aby analysis_fundamental_command mogło parsować argumenty
        await self.analysis_fundamental_command(event)
    
    @RD.cb(b"analysis:tech_overview")
    async def analysis_tech_overview_callback(self, event):
        """Przekierowanie do przeglądu analiz technicznych."""
        # Ustawić raw_text dla callback query, aby analysis_technical_command mogło parsować argumenty
        await self.analysis_technical_command(event)
    
    @RD.cb(b"analysis:patterns_overview")
    async def analysis_patterns_overview_callback(self, event):
        """Przekierowanie do przeglądu wzorców harmonicznych."""
        # Ustawić raw_text dla callback query, aby analysis_harmonic_patterns_command mogło parsować argumenty
        await self.analysis_harmonic_patterns_command(event)
    
    @RD.cb(b"analysis:overview")
    async def analysis_overview_callback(self, event):
        """Przekierowanie do głównego przeglądu analiz."""
        # analysis_command nie wymaga raw_text, więc nie trzeba go ustawiać
        await self.analysis_command(event)
    
    @RD.cb(b"analysis:refresh")
    async def analysis_refresh_callback(self, event):
        """Odświeżenie przeglądu analiz."""
        # analysis_command nie wymaga raw_text, więc nie trzeba go ustawiać
        await self.analysis_command(event)
    
    @RD.cb(b"analysis:fund_llm_overview")
    async def analysis_fund_llm_overview_callback(self, event):
        """Przekierowanie do przeglądu interpretacji LLM fundamentalnych."""
        await self.analysis_fund_llm_interpretations_command(event)
    
    @RD.cb(b"analysis:tech_llm_overview")
    async def analysis_tech_llm_overview_callback(self, event):
        """Przekierowanie do przeglądu interpretacji LLM technicznych."""
        await self.analysis_tech_llm_interpretations_command(event)
    
    @RD.cb(b"nav:home")
    async def nav_home_callback(self, event):
        """Powrót do menu głównego analiz."""
        # analysis_command nie wymaga raw_text, więc nie trzeba go ustawiać
        await self.analysis_command(event)
    
    # ===================
    # CALLBACK QUERIES - ASSET SELECTION FOR ANALYSIS
    # ===================
    
    @RD.cb(b"analysis:search_asset")
    async def analysis_search_asset_callback(self, event):
        """Pokazuje instrukcje wyszukiwania analiz po assetach."""
        search_help = (
            "🔍 **Wyszukiwanie Analiz po Assets**\n\n"
            "**Aby zobaczyć analizy dla konkretnego assetu:**\n\n"
            "**Analizy fundamentalne:**\n"
            "• Przejdź do 💼 Fundamentalne\n"
            "• Wybierz 🔍 Po assetach\n\n"
            "**Analizy techniczne:**\n"
            "• Przejdź do 📈 Techniczne  \n"
            "• Wybierz 🔍 Po assetach\n\n"
            "**Wzorce harmoniczne:**\n"
            "• Przejdź do 🔄 Wzorce\n"
            "• Wybierz 🔍 Po assetach\n\n"
            "**Interpretacje:**\n"
            "• Przejdź do 🧠 Interpretacje\n"
            "• Wybierz 🔍 Po assetach"
        )
        
        buttons = [
            [
                Button.inline("💼 Fundamentalne", b"analysis:fund_overview"),
                Button.inline("📈 Techniczne", b"analysis:tech_overview")
            ],
            [
                Button.inline("🔄 Wzorce", b"analysis:patterns_overview"),
                Button.inline("🧠 Interpretacje", b"interp:general")
            ],
            [Button.inline("🔙 Wstecz", b"analysis:overview")]
        ]
        
        await event.edit(search_help, buttons=buttons)
    
    # ===================
    # CALLBACK QUERIES - MISSING HANDLERS
    # ===================
    
    @RD.cb(b"analysis:fund_by_asset")
    async def analysis_fund_by_asset_callback(self, event):
        """Pokazuje listę assetów dla analiz fundamentalnych."""
        await self._show_assets_for_analysis_selection(event, "fundamental", page=1)
    
    @RD.cb(b"analysis:tech_by_asset")
    async def analysis_tech_by_asset_callback(self, event):
        """Pokazuje listę assetów dla analiz technicznych.""" 
        await self._show_assets_for_analysis_selection(event, "technical", page=1)
    
    @RD.cb(b"analysis:patterns_by_asset")
    async def analysis_patterns_by_asset_callback(self, event):
        """Pokazuje listę assetów dla wzorców harmonicznych."""
        await self._show_assets_for_analysis_selection(event, "patterns", page=1)
    
    @RD.cb(b"interp:by_asset")
    async def interpretations_by_asset_callback(self, event):
        """Pokazuje listę assetów dla interpretacji."""
        await self._show_assets_for_analysis_selection(event, "interpretations", page=1)
    
    @RD.cb(b"interp:fund_by_asset")
    async def interpretations_fund_by_asset_callback(self, event):
        """Pokazuje listę assetów dla interpretacji LLM fundamentalnych."""
        await self._show_assets_for_analysis_selection(event, "fund_interpretations", page=1)
    
    @RD.cb(b"interp:tech_by_asset")
    async def interpretations_tech_by_asset_callback(self, event):
        """Pokazuje listę assetów dla interpretacji LLM technicznych."""
        await self._show_assets_for_analysis_selection(event, "tech_interpretations", page=1)
    
    @RD.cb(b"interp:fund_details_menu")
    async def interpretations_fund_details_menu_callback(self, event):
        """Pokazuje menu szczegółowych opcji dla interpretacji LLM fundamentalnych."""
        await self._show_analysis_details_menu(event, "fund_interpretations")
    
    @RD.cb(b"interp:tech_details_menu")
    async def interpretations_tech_details_menu_callback(self, event):
        """Pokazuje menu szczegółowych opcji dla interpretacji LLM technicznych."""
        await self._show_analysis_details_menu(event, "tech_interpretations")
    
    @RD.cb(b"analysis:fund_details_menu")
    async def analysis_fund_details_menu_callback(self, event):
        """Pokazuje menu szczegółowych opcji dla analiz fundamentalnych."""
        await self._show_analysis_details_menu(event, "fundamental")
    
    @RD.cb(b"analysis:tech_details_menu") 
    async def analysis_tech_details_menu_callback(self, event):
        """Pokazuje menu szczegółowych opcji dla analiz technicznych."""
        await self._show_analysis_details_menu(event, "technical")
    
    @RD.cb(b"analysis:patterns_details_menu")
    async def analysis_patterns_details_menu_callback(self, event):
        """Pokazuje menu szczegółowych opcji dla wzorców harmonicznych."""
        await self._show_analysis_details_menu(event, "patterns")
    
    async def _show_assets_for_analysis_selection(self, event, analysis_type: str, page: int = 1):
        """
        Helper method do wyświetlenia listy assetów dla wybranego typu analiz z paginacją.
        
        Args:
            event: Event Telegram
            analysis_type: Typ analizy ('fundamental', 'technical', 'patterns')
            page: Numer strony (domyślnie 1)
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            await self.init_database()
            assets_table = self.db.get_factory().get_assets_table()
            
            # Paginacja: 12 assetów na stronę (6 rzędów po 2)
            assets_per_page = 12
            offset = (page - 1) * assets_per_page
            
            # Pobierz dokładną liczbę wszystkich assetów dla paginacji
            total_assets = await assets_table.count_all()
            total_pages = (total_assets + assets_per_page - 1) // assets_per_page  # Ceil division
            
            # Pobierz assety z marginesem dla sprawdzenia następnej strony
            assets = await assets_table.get_all(limit=assets_per_page + 1, offset=offset)
            
            if not assets:
                await event.edit(
                    f"🔍 **Wyszukiwanie po assetach - {analysis_type} - Strona {page}**\n\n❌ Brak assetów na tej stronie.",
                    buttons=[[Button.inline("🔙 Wstecz", f"analysis:{analysis_type.split('_')[0]}_overview".encode())]]
                )
                return
            
            # Sprawdź czy są następne strony
            has_next = len(assets) > assets_per_page
            page_assets = assets[:assets_per_page]
            
            # Formatuj listę assetów
            type_emoji = "💼" if analysis_type == "fundamental" else "📈" if analysis_type == "technical" else "🔄" if analysis_type == "patterns" else "🧠"
            type_name = "Fundamentalne" if analysis_type == "fundamental" else "Techniczne" if analysis_type == "technical" else "Wzorce Harmoniczne" if analysis_type == "patterns" else "Interpretacje"
            title = f"{type_emoji} **Wybierz Asset dla Analiz {type_name}**"
            if total_pages > 1:
                title += f" - Strona {page} z {total_pages}"
            title += "\n\n"
            
            # Przyciski z assetami (po 2 na rząd)
            buttons = []
            for i in range(0, len(page_assets), 2):  # Po 2 na rząd
                row = []
                for j in range(2):
                    if i + j < len(page_assets):
                        asset = page_assets[i + j]
                        asset_symbol = f"{asset['asset']}/{asset['quote']}"
                        if analysis_type == "interpretations":
                            callback_data = f"interp:asset:{asset['id']}"
                        else:
                            callback_type = "fund" if analysis_type == "fundamental" else "tech" if analysis_type == "technical" else "patterns"
                            callback_data = f"analysis:{callback_type}:{asset['id']}"
                        row.append(Button.inline(asset_symbol, callback_data.encode()))
                buttons.append(row)
            
            # Dodaj przyciski paginacji jeśli potrzebne
            if total_pages > 1:
                pagination_row = []
                
                if page > 1:
                    if analysis_type == "interpretations":
                        pagination_row.append(Button.inline("⬅️ Poprzednia", f"interp:assets_page:{page-1}".encode()))
                    else:
                        callback_type = "fund" if analysis_type == "fundamental" else "tech" if analysis_type == "technical" else "patterns"
                        pagination_row.append(Button.inline("⬅️ Poprzednia", f"analysis:{callback_type}_assets_page:{page-1}".encode()))
                
                # Informacja o stronie
                pagination_row.append(Button.inline(f"📄 {page}/{total_pages}", f"analysis:assets_page_info:{page}".encode()))
                
                if page < total_pages:
                    if analysis_type == "interpretations":
                        pagination_row.append(Button.inline("Następna ➡️", f"interp:assets_page:{page+1}".encode()))
                    else:
                        callback_type = "fund" if analysis_type == "fundamental" else "tech" if analysis_type == "technical" else "patterns"
                        pagination_row.append(Button.inline("Następna ➡️", f"analysis:{callback_type}_assets_page:{page+1}".encode()))
                
                buttons.append(pagination_row)
                
                # Dodaj przycisk "Idź do strony..." jeśli mamy więcej niż 1 stronę
                if analysis_type == "interpretations":
                    buttons.append([Button.inline("🔢 Idź do strony...", f"interp:assets_page:jump".encode())])
                else:
                    callback_type = "fund" if analysis_type == "fundamental" else "tech" if analysis_type == "technical" else "patterns"
                    buttons.append([Button.inline("🔢 Idź do strony...", f"analysis:{callback_type}_assets_page:jump".encode())])
            
            # Przyciski nawigacji
            if analysis_type == "interpretations":
                buttons.extend([
                    [Button.inline("🔙 Wstecz", b"interp:general")],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ])
            else:
                buttons.extend([
                    [Button.inline("🔙 Wstecz", f"analysis:{analysis_type.split('_')[0]}_overview".encode())],
                    [Button.inline("🏠 Menu główne", b"nav:home")]
                ])
            
            await event.edit(title, buttons=buttons)
            await self.log_action(user.id, f"assets_selection_for_{analysis_type}", {
                "assets_count": len(page_assets), 
                "page": page,
                "has_next": has_next
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, f"assets_selection_{analysis_type}")
            await event.edit(error_msg)
    
    # ===================
    # CALLBACK QUERIES - ASSETS SELECTION PAGINATION
    # ===================
    
    @RD.cb(b"analysis:fund_assets_page:")
    async def analysis_fund_assets_page_callback(self, event):
        """Handler paginacji dla wyboru assetów analiz fundamentalnych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony assetów**\n\n"
                    "Używaj przycisków ⬅️ Poprzednia / Następna ➡️ do nawigacji między stronami assetów.\n\n"
                    "**Każda strona zawiera maksymalnie 12 assetów (6 rzędów po 2).**\n\n"
                    "Alternatywnie możesz wrócić do głównej listy analiz fundamentalnych."
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"analysis:fund_assets_page:1")],
                    [Button.inline("🔙 Wstecz", b"analysis:fund_overview")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            await self._show_assets_for_analysis_selection(event, "fundamental", page)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji assetów", alert=True)
            logger.error(f"Error in fund assets pagination: {e}")
    
    @RD.cb(b"analysis:tech_assets_page:")
    async def analysis_tech_assets_page_callback(self, event):
        """Handler paginacji dla wyboru assetów analiz technicznych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony assetów**\n\n"
                    "Używaj przycisków ⬅️ Poprzednia / Następna ➡️ do nawigacji między stronami assetów.\n\n"
                    "**Każda strona zawiera maksymalnie 12 assetów (6 rzędów po 2).**\n\n"
                    "Alternatywnie możesz wrócić do głównej listy analiz technicznych."
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"analysis:tech_assets_page:1")],
                    [Button.inline("🔙 Wstecz", b"analysis:tech_overview")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            await self._show_assets_for_analysis_selection(event, "technical", page)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji assetów", alert=True)
            logger.error(f"Error in tech assets pagination: {e}")
    
    @RD.cb(b"analysis:patterns_assets_page:")
    async def analysis_patterns_assets_page_callback(self, event):
        """Handler paginacji dla wyboru assetów wzorców harmonicznych."""
        try:
            callback_data = event.data.decode()
            last_part = callback_data.split(":")[-1]
            
            # Sprawdź czy to przycisk jump
            if last_part == "jump":
                jump_help = (
                    "🔢 **Przejdź do strony assetów**\n\n"
                    "Używaj przycisków ⬅️ Poprzednia / Następna ➡️ do nawigacji między stronami assetów.\n\n"
                    "**Każda strona zawiera maksymalnie 12 assetów (6 rzędów po 2).**\n\n"
                    "Alternatywnie możesz wrócić do głównej listy wzorców harmonicznych."
                )
                
                buttons = [
                    [Button.inline("📊 Strona 1", b"analysis:patterns_assets_page:1")],
                    [Button.inline("🔙 Wstecz", b"analysis:patterns_overview")]
                ]
                
                await event.edit(jump_help, buttons=buttons)
                return
            
            page = int(last_part)
            await self._show_assets_for_analysis_selection(event, "patterns", page)
            
        except Exception as e:
            await event.answer("❌ Błąd paginacji assetów", alert=True)
            logger.error(f"Error in patterns assets pagination: {e}")
    
    @RD.cb(b"analysis:assets_page_info:")
    async def analysis_assets_page_info_callback(self, event):
        """Handler dla przycisków informacyjnych o stronie assetów (ignorowanie kliknięć)."""
        await event.answer("ℹ️ To jest informacja o bieżącej stronie assetów", alert=False)
    
    @RD.cb(b"interp:assets_page:")
    async def interpretations_assets_page_callback(self, event):
        """Handler paginacji dla selekcji assetów w interpretacjach."""
        callback_data = event.data.decode()
        last_part = callback_data.split(":")[-1]
        
        if last_part == "jump":
            await event.answer(
                "🔢 Aby przejść do konkretnej strony, użyj komend:\n"
                "• /analysis_interpretations [numer_strony]\n"
                "• Lub kliknij Poprzednia/Następna"
            )
            return
        
        try:
            page = int(last_part)
            await self._show_assets_for_analysis_selection(event, "interpretations", page)
        except (ValueError, IndexError) as e:
            await event.answer("❌ Błąd parsowania strony", alert=True)
    
    async def _show_analysis_details_menu(self, event, analysis_type: str):
        """
        Helper method do wyświetlenia menu szczegółowych opcji dla analiz.
        
        Args:
            event: Event Telegram  
            analysis_type: Typ analizy ('fundamental', 'technical', 'patterns')
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        try:
            # Formatuj menu szczegółów
            type_emoji = "💼" if analysis_type == "fundamental" else "📈" if analysis_type == "technical" else "🔄"
            title = f"{type_emoji} **Szczegóły Analiz {analysis_type.title()}**\n\n"
            title += f"Wybierz opcję szczegółową:"
            
            callback_prefix = "fund" if analysis_type == "fundamental" else "tech" if analysis_type == "technical" else "patterns"
            
            buttons = [
                [
                    Button.inline("🔍 Po assetach", f"analysis:{callback_prefix}_by_asset".encode()),
                    Button.inline("📊 Najnowsze", f"analysis:{callback_prefix}_latest".encode())
                ],
                [
                    Button.inline("📈 Statystyki", f"analysis:{callback_prefix}_stats".encode()),
                    Button.inline("🎯 Najlepsze", f"analysis:{callback_prefix}_best".encode())
                ],
                [
                    Button.inline("🔙 Wstecz", f"analysis:{callback_prefix}_overview".encode()),
                    Button.inline("🏠 Menu główne", b"nav:home")
                ]
            ]
            
            await event.edit(title, buttons=buttons)
            await self.log_action(user.id, f"details_menu_{analysis_type}")
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, f"details_menu_{analysis_type}")
            await event.edit(error_msg)
    
    # ===================
    # UTILITY METHODS
    # ===================
    
    async def _get_asset_info_string(self, asset_id: Optional[int]) -> str:
        """
        Pobiera sformatowany string z informacją o assecie.
        
        Args:
            asset_id: ID assetu lub None
            
        Returns:
            str: Sformatowana informacja o assecie lub pusty string
        """
        if not asset_id:
            return ""
        
        try:
            assets_table = self.db.get_factory().get_assets_table()
            asset = await assets_table.get_by_id(asset_id)
            if asset:
                return f" ({asset['asset']}/{asset['quote']})"
        except Exception as e:
            logger.error(f"Error getting asset info for ID {asset_id}: {e}")
        
        return ""
    
    def create_loading_message(self, action: str) -> str:
        """Tworzy wiadomość loading (override z base class)."""
        return TelegramUIUtils.create_status_message('loading', f'Ładuję {action}', 'Proszę czekać...')
    
    def create_success_message(self, action: str, details: str = "") -> str:
        """Tworzy wiadomość sukcesu (override z base class)."""
        return TelegramUIUtils.create_status_message('success', f'{action} zakończone pomyślnie', details)
    
    def create_error_message(self, action: str, error: str = "") -> str:
        """Tworzy wiadomość błędu (override z base class)."""
        return TelegramUIUtils.create_status_message('error', f'Błąd podczas {action}', error)
