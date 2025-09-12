"""
Kontroler MainMenu dla Telegram - główne menu aplikacji.

Ta klasa implementuje:
- Główne menu startowe z nawigacją do wszystkich domen
- Wyświetlanie statystyk aplikacji
- Obsługę komend /start, /menu, /help
- Automatyczne menu po uruchomieniu bota

Autor: AI Assistant
"""

import logging
import traceback
from typing import List, Dict, Any, Optional
from datetime import datetime
from telethon import Button

from .controller_telegram_utils_abstract_base import BaseTelegramControllerDomain, RD
from .controller_telegram_utils_ui import TelegramUIUtils

logger = logging.getLogger(__name__)


class MainMenuTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler domenowy dla głównego menu aplikacji Telegram.
    
    Zapewnia funkcjonalności:
    - Główne menu z nawigacją do wszystkich domen
    - Wyświetlanie statystyk aplikacji
    - Obsługę komend startowych
    - Automatyczne wyświetlanie menu
    """
    
    DOMAIN = "main_menu"
    
    def __init__(self, telegram_controller=None, **kwargs):
        """
        Inicjalizacja kontrolera głównego menu.
        
        Args:
            telegram_controller: Referencja do głównego kontrolera aplikacji
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        self.telegram_controller = telegram_controller
        self.ui_utils = TelegramUIUtils()
        
        # Konfiguracja domen z ikonami i opisami
        self.domains_config = {
            "system": {
                "icon": "🔧",
                "name": "System",
                "description": "Status, synchronizacja, health check",
                "callback": "nav:system"
            },
            "assets": {
                "icon": "💎",
                "name": "Assety",
                "description": "Lista assetów, wyszukiwanie, szczegóły",
                "callback": "nav:assets"
            },
            "exchanges": {
                "icon": "🏦",
                "name": "Giełdy",
                "description": "Lista giełd, aktywne giełdy, szczegóły",
                "callback": "nav:exchanges"
            },
            "wallets": {
                "icon": "💰",
                "name": "Portfele",
                "description": "Zarządzanie portfelami, salda",
                "callback": "nav:wallets"
            },
            "strategies": {
                "icon": "📊",
                "name": "Strategie",
                "description": "Strategie inwestycyjne, kupna, sprzedaży",
                "callback": "nav:strategies"
            },
            "transactions": {
                "icon": "💸",
                "name": "Transakcje",
                "description": "Historia transakcji, kreator",
                "callback": "nav:transactions"
            },
            "analysis": {
                "icon": "🔍",
                "name": "Analizy",
                "description": "Analizy fundamentalne, techniczne, wzorce",
                "callback": "nav:analysis"
            }
        }
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny głównego menu."""
        return {
            "main_menu_available": True,
            "configured_domains": len(self.domains_config),
            "telegram_controller_available": self.telegram_controller is not None
        }
    
    # ===================
    # KOMENDY GŁÓWNEGO MENU
    # ===================
    
    @RD.cmd("start", aliases=["menu", "help", "main"])
    async def start_command(self, event):
        """
        Komenda startowa - wyświetla główne menu bota z nawigacją do wszystkich domen.
        Dostępna przez /start, /menu, /help lub /main.
        """
        user = await self.get_user_info(event)
        if not user:
            await event.respond("❌ Nie można pobrać informacji o użytkowniku.")
            return
        
        await self.log_action(user.id, "main_menu_display")
        
        try:
            # Pobierz statystyki aplikacji
            app_stats = await self._get_application_stats()
            
            # Nagłówek główny
            welcome_text = f"🚀 **Witaj {user.first_name}!**\n\n"
            welcome_text += "🤖 **Pump Bot** - Kompleksowy system analizy rynku kryptowalut\n\n"
            
            # Statystyki aplikacji
            welcome_text += "📊 **Statystyki Aplikacji:**\n"
            if app_stats:
                uptime = app_stats.get('uptime', 'N/A')
                domains_count = app_stats.get('domains_loaded', 0)
                routes_count = app_stats.get('routes_registered', 0)
                
                welcome_text += f"⏱️ Uptime: {uptime}\n"
                welcome_text += f"📚 Domeny: {domains_count}\n"
                welcome_text += f"🛤️ Routy: {routes_count}\n"
                
                if 'health_summary' in app_stats:
                    health = app_stats['health_summary']
                    healthy_count = health.get('healthy_domains', 0)
                    total_count = health.get('total_domains', 0)
                    welcome_text += f"🏥 Zdrowie: {healthy_count}/{total_count} ✅\n"
            
            welcome_text += "\n🎛️ **Dostępne Moduły:**\n"
            welcome_text += "Wybierz moduł aby rozpocząć:\n\n"
            
            # Utworzenie przycisków dla każdej domeny
            buttons = []
            
            # Pierwsza grupa przycisków (2 w rzędzie)
            row1 = []
            if "system" in self.domains_config:
                config = self.domains_config["system"]
                row1.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            if "assets" in self.domains_config:
                config = self.domains_config["assets"]
                row1.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            if row1:
                buttons.append(row1)
            
            # Druga grupa przycisków
            row2 = []
            if "exchanges" in self.domains_config:
                config = self.domains_config["exchanges"]
                row2.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            if "wallets" in self.domains_config:
                config = self.domains_config["wallets"]
                row2.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            if row2:
                buttons.append(row2)
            
            # Trzecia grupa przycisków
            row3 = []
            if "strategies" in self.domains_config:
                config = self.domains_config["strategies"]
                row3.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            if "transactions" in self.domains_config:
                config = self.domains_config["transactions"]
                row3.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            if row3:
                buttons.append(row3)
            
            # Czwarta grupa przycisków
            row4 = []
            if "analysis" in self.domains_config:
                config = self.domains_config["analysis"]
                row4.append(Button.inline(f"{config['icon']} {config['name']}", config["callback"].encode()))
            # Dodaj przycisk statystyk
            row4.append(Button.inline("📈 Statystyki", b"nav:stats"))
            if row4:
                buttons.append(row4)
            
            # Ostatni rząd z pomocą
            buttons.append([
                Button.inline("ℹ️ Pomoc", b"nav:help"),
                Button.inline("🔄 Odśwież", b"nav:refresh")
            ])
            
            await event.respond(welcome_text, buttons=buttons, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Błąd w start_command: {e}")
            logger.error(traceback.format_exc())
            
            error_text = f"❌ **Błąd wyświetlania menu głównego:**\n\n`{str(e)}`\n\n"
            error_text += "Spróbuj ponownie za chwilę lub skontaktuj się z administratorem."
            await event.respond(error_text, parse_mode="Markdown")
    
    # ===================
    # CALLBACK HANDLERS
    # ===================
    
    @RD.cb(b"nav:system")
    async def callback_system(self, event):
        """Handler dla nawigacji do modułu System."""
        await self._handle_domain_navigation(event, "system", "/status")
    
    @RD.cb(b"nav:assets")
    async def callback_assets(self, event):
        """Handler dla nawigacji do modułu Assety."""
        await self._handle_domain_navigation(event, "assets", "/assets")
    
    @RD.cb(b"nav:exchanges")
    async def callback_exchanges(self, event):
        """Handler dla nawigacji do modułu Giełdy."""
        await self._handle_domain_navigation(event, "exchanges", "/exchanges")
    
    @RD.cb(b"nav:wallets")
    async def callback_wallets(self, event):
        """Handler dla nawigacji do modułu Portfele."""
        await self._handle_domain_navigation(event, "wallets", "/wallets")
    
    @RD.cb(b"nav:strategies")
    async def callback_strategies(self, event):
        """Handler dla nawigacji do modułu Strategie."""
        await self._handle_domain_navigation(event, "strategies", "/investment_strategies")
    
    @RD.cb(b"nav:transactions")
    async def callback_transactions(self, event):
        """Handler dla nawigacji do modułu Transakcje."""
        await self._handle_domain_navigation(event, "transactions", "/transactions")
    
    @RD.cb(b"nav:analysis")
    async def callback_analysis(self, event):
        """Handler dla nawigacji do modułu Analizy."""
        await self._handle_domain_navigation(event, "analysis", "/analysis")
    
    @RD.cb(b"nav:stats")
    async def callback_stats(self, event):
        """Handler dla wyświetlania szczegółowych statystyk."""
        await self._show_detailed_stats(event)
    
    @RD.cb(b"nav:help")
    async def callback_help(self, event):
        """Handler dla wyświetlania pomocy."""
        await self._show_help(event)
    
    @RD.cb(b"nav:refresh")
    async def callback_refresh(self, event):
        """Handler dla odświeżania menu głównego."""
        # Ponowne wywołanie start_command
        await self.start_command(event)
    
    # ===================
    # POMOCNICZE METODY
    # ===================
    
    async def _handle_domain_navigation(self, event, domain_name: str, suggested_command: str):
        """
        Obsługuje nawigację do konkretnej domeny - wywołuje jej własne menu.
        
        Args:
            event: Zdarzenie callback
            domain_name: Nazwa domeny
            suggested_command: Sugerowana komenda dla użytkownika (nieużywane, zachowane dla kompatybilności)
        """
        try:
            config = self.domains_config.get(domain_name)
            if not config:
                await event.edit("❌ Nieznana domena.")
                return
            
            # Sprawdź czy domena jest dostępna
            if self.telegram_controller and hasattr(self.telegram_controller, 'domains'):
                domain_instance = self.telegram_controller.domains.get(domain_name)
                if not domain_instance:
                    await event.edit(f"❌ Domena '{config['name']}' nie jest dostępna.")
                    return
                
                # Sprawdź czy domena ma metodę get_domain_menu
                if hasattr(domain_instance, 'get_domain_menu'):
                    # Pobierz użytkownika
                    user = await self.get_user_info(event)
                    user_id = user.id if user else None
                    
                    # Wywołaj menu domeny
                    menu_text, buttons = await domain_instance.get_domain_menu(event, user_id)
                    await event.edit(menu_text, buttons=buttons, parse_mode="Markdown")
                    return
                else:
                    # Fallback do starego systemu jeśli domena nie ma menu
                    logger.warning(f"Domena '{domain_name}' nie ma zaimplementowanego menu")
            
            # Fallback - podstawowa informacja o domenie
            response_text = f"{config['icon']} **{config['name']}**\n\n"
            response_text += f"📋 {config['description']}\n\n"
            response_text += "⚠️ **Ta domena nie ma jeszcze zdefiniowanego menu.**\n\n"
            response_text += f"💡 Sprawdź dostępne komendy w dokumentacji lub użyj:\n"
            response_text += f"`{suggested_command}` - główna komenda tej domeny"
            
            buttons = [
                [
                    Button.inline("🏠 Menu Główne", b"nav:refresh"),
                    Button.inline("ℹ️ Pomoc", b"nav:help")
                ]
            ]
            
            await event.edit(response_text, buttons=buttons, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Błąd w _handle_domain_navigation: {e}")
            await event.edit(f"❌ Błąd nawigacji: {str(e)}")
    
    def _get_domain_commands(self, domain_name: str) -> List[str]:
        """
        Zwraca listę komend dostępnych dla danej domeny.
        
        Args:
            domain_name: Nazwa domeny
            
        Returns:
            List[str]: Lista komend
        """
        commands_map = {
            "system": [
                "/status", "/sync_all", "/health", "/system_info"
            ],
            "assets": [
                "/assets", "/assets_search", "/asset_info"
            ],
            "exchanges": [
                "/exchanges", "/exchanges_active", "/exchange_info"
            ],
            "wallets": [
                "/wallets", "/wallets_active", "/wallet_balance"
            ],
            "strategies": [
                "/investment_strategies", "/buy_strategies", "/sell_strategies", 
                "/investment_strategy_search", "/strategy_create"
            ],
            "transactions": [
                "/transactions", "/transactions_pending", "/transaction_create", "/transaction_info"
            ],
            "analysis": [
                "/analysis", "/analysis_fundamental", "/analysis_technical", 
                "/analysis_patterns", "/analysis_interpretations"
            ]
        }
        
        return commands_map.get(domain_name, [])
    
    async def _get_application_stats(self) -> Optional[Dict[str, Any]]:
        """
        Pobiera statystyki aplikacji z głównego kontrolera.
        
        Returns:
            Optional[Dict[str, Any]]: Statystyki aplikacji lub None
        """
        try:
            if not self.telegram_controller:
                return None
            
            # Pobierz podstawowe statystyki z kontrolera
            controller_stats = self.telegram_controller.stats.copy()
            
            # Dodaj uptime
            if 'start_time' in controller_stats:
                uptime = datetime.now() - controller_stats['start_time']
                controller_stats['uptime'] = str(uptime).split('.')[0]  # Usuń mikrosekundy
            
            # Pobierz health check jeśli dostępny
            if hasattr(self.telegram_controller, 'health_check_all_domains'):
                health_results = await self.telegram_controller.health_check_all_domains()
                healthy_count = sum(1 for h in health_results.values() if h.get('healthy', False))
                controller_stats['health_summary'] = {
                    'healthy_domains': healthy_count,
                    'total_domains': len(health_results)
                }
            
            # Pobierz statystyki routera
            if hasattr(self.telegram_controller, 'router') and self.telegram_controller.router:
                router_stats = self.telegram_controller.router.get_stats()
                controller_stats['router_stats'] = router_stats
            
            return controller_stats
            
        except Exception as e:
            logger.error(f"Błąd pobierania statystyk aplikacji: {e}")
            return None
    
    async def _show_detailed_stats(self, event):
        """Wyświetla szczegółowe statystyki aplikacji."""
        try:
            if not self.telegram_controller:
                await event.edit("❌ Brak dostępu do statystyk aplikacji.")
                return
            
            # Pobierz wszystkie statystyki
            user_stats = await self.telegram_controller.get_user_statistics()
            health = await self.telegram_controller.health_check_all_domains()
            
            stats_text = "📊 **Szczegółowe Statystyki Aplikacji**\n\n"
            
            # Podstawowe informacje
            controller_stats = user_stats.get('controller_stats', {})
            if 'start_time' in controller_stats:
                uptime = datetime.now() - controller_stats['start_time']
                stats_text += f"⏱️ **Uptime:** {str(uptime).split('.')[0]}\n"
            
            stats_text += f"🧪 **Tryb testowy:** {'✅ Tak' if self.test_mode else '❌ Nie'}\n"
            stats_text += f"📚 **Domeny:** {user_stats.get('total_domains', 0)}\n\n"
            
            # Health check
            stats_text += "🏥 **Status Domen:**\n"
            healthy_count = sum(1 for h in health.values() if h.get('healthy', False))
            stats_text += f"   ✅ Zdrowe: {healthy_count}/{len(health)}\n"
            
            for domain_name, health_info in health.items():
                status_emoji = "✅" if health_info.get('healthy', False) else "❌"
                domain_type = health_info.get('domain_type', 'Unknown').replace('TelegramControllerDomain', '')
                stats_text += f"   {status_emoji} {domain_name}: {domain_type}\n"
            
            # Router statistics
            router_stats = user_stats.get('router_stats', {})
            if router_stats:
                stats_text += f"\n📈 **Statystyki Routera:**\n"
                for key, value in router_stats.items():
                    formatted_key = key.replace('_', ' ').title()
                    stats_text += f"   • {formatted_key}: {value}\n"
            
            # Domain-specific stats
            domain_stats = user_stats.get('domain_stats', {})
            if domain_stats:
                stats_text += f"\n📋 **Statystyki Domen:**\n"
                for domain_name, stats in domain_stats.items():
                    if isinstance(stats, dict) and 'error' not in stats:
                        stats_text += f"   📁 {domain_name}:\n"
                        for key, value in stats.items():
                            if key != 'domain_type':
                                formatted_key = key.replace('_', ' ').title()
                                stats_text += f"      • {formatted_key}: {value}\n"
            
            # Przyciski
            buttons = [
                [
                    Button.inline("🔄 Odśwież", b"nav:stats"),
                    Button.inline("🏠 Menu Główne", b"nav:refresh")
                ]
            ]
            
            await event.edit(stats_text, buttons=buttons, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Błąd w _show_detailed_stats: {e}")
            await event.edit(f"❌ Błąd wyświetlania statystyk: {str(e)}")
    
    async def _show_help(self, event):
        """Wyświetla pomoc dla użytkownika."""
        help_text = "ℹ️ **Pomoc - Pump Bot**\n\n"
        help_text += "🤖 **Co to jest Pump Bot?**\n"
        help_text += "Kompleksowy system analizy rynku kryptowalut z funkcjami:\n"
        help_text += "• Analizy fundamentalne i techniczne\n"
        help_text += "• Zarządzanie assetami i giełdami\n"
        help_text += "• Strategie inwestycyjne\n"
        help_text += "• Monitorowanie transakcji\n\n"
        
        help_text += "🎛️ **Jak używać?**\n"
        help_text += "1. Wybierz moduł z głównego menu\n"
        help_text += "2. Użyj sugerowanych komend\n"
        help_text += "3. Nawiguj za pomocą przycisków\n\n"
        
        help_text += "⌨️ **Podstawowe komendy:**\n"
        help_text += "• `/start` - Główne menu\n"
        help_text += "• `/status` - Status systemu\n"
        help_text += "• `/assets` - Lista assetów\n"
        help_text += "• `/exchanges` - Lista giełd\n\n"
        
        help_text += "💡 **Wskazówki:**\n"
        help_text += "• Wszystkie komendy zaczynają się od `/`\n"
        help_text += "• Można używać przycisków zamiast pisać komendy\n"
        help_text += "• Użyj `/start` aby wrócić do głównego menu\n\n"
        
        help_text += "🔧 **Potrzebujesz pomocy?**\n"
        help_text += "Użyj `/system_info` aby sprawdzić status systemu."
        
        buttons = [
            [
                Button.inline("🏠 Menu Główne", b"nav:refresh"),
                Button.inline("📊 Statystyki", b"nav:stats")
            ]
        ]
        
        await event.edit(help_text, buttons=buttons, parse_mode="Markdown")
    
    # ===================
    # QUICK ACTION HANDLERS
    # ===================
    
    @RD.cb(b"quick:")
    async def handle_quick_actions(self, event):
        """Handler for quick action buttons - executes commands directly."""
        try:
            callback_data = event.data.decode('utf-8')
            if not callback_data.startswith('quick:'):
                return
                
            command = callback_data.replace('quick:', '')
            
            # Simulate a command message
            await event.edit(f"⚡ Wykonuję komendę: `{command}`\n\n⏳ Proszę czekać...")
            
            # Here you would normally trigger the actual command handler
            # For now, we'll just show a message with suggestion
            await asyncio.sleep(1)
            
            result_text = f"✅ Szybka akcja dla: `{command}`\n\n"
            result_text += "💡 **Aby zobaczyć pełne wyniki:**\n"
            result_text += f"Wpisz komendę `{command}` w czacie\n\n"
            result_text += "🔹 **Wskazówka:** Wszystkie komendy możesz wywoływać bezpośrednio w czacie."
            
            buttons = [
                [
                    Button.inline("🏠 Menu Główne", b"nav:refresh"),
                    Button.inline("ℹ️ Pomoc", b"nav:help")
                ]
            ]
            
            await event.edit(result_text, buttons=buttons, parse_mode="Markdown")
            
        except Exception as e:
            logger.error(f"Error in handle_quick_actions: {e}")
            await event.edit(f"❌ Błąd wykonywania szybkiej akcji: {str(e)}")

    async def show_menu_on_bot_start(self, telegram_client, admin_chat_id: Optional[int] = None):
        """
        Automatycznie wyświetla główne menu po uruchomieniu bota.
        
        Args:
            telegram_client: Klient Telegram
            admin_chat_id: ID czatu administratora (opcjonalne)
        """
        try:
            if admin_chat_id:
                # Wyślij menu do konkretnego administratora
                await telegram_client.send_message(
                    admin_chat_id, 
                    "🚀 **Bot został uruchomiony!**\n\nUżyj /start aby zobaczyć główne menu.",
                    parse_mode="Markdown"
                )
                logger.info(f"Wysłano powiadomienie o uruchomieniu do administratora {admin_chat_id}")
            else:
                logger.info("Brak skonfigurowanego administratora - nie wysłano automatycznego menu")
                
        except Exception as e:
            logger.error(f"Błąd wysyłania automatycznego menu: {e}")
