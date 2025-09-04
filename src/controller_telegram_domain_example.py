"""
Przykładowa klasa domenowa dla systemu routingu Telethon.

Ta klasa demonstruje użycie różnych typów handlerów:
- Komendy z aliasami
- Wzorce wiadomości regex
- Callback queries (inline buttons)
- Hooks i middleware
- Kontrolę uprawnień

Autor: AI Assistant
"""

import logging
from typing import List, Optional
from telethon import Button
from telethon.tl.types import User

from .controller_telegram_utils_router import DomainBase, RD

logger = logging.getLogger(__name__)


class PumpBotExampleDomain(DomainBase):
    """
    Przykładowa domena dla bota pump, demonstrująca różne funkcjonalności routingu.
    
    Ta domena zawiera przykłady:
    - Komendy podstawowe i z aliasami
    - Obsługę wzorców wiadomości
    - Callback queries z inline buttons
    - Kontrolę uprawnień użytkowników
    - Integrację z API zewnętrznymi (mock)
    """
    
    DOMAIN = "pump_example"
    
    def __init__(self, admin_users: Optional[List[int]] = None, **kwargs):
        """
        Inicjalizacja domeny przykładowej.
        
        Args:
            admin_users: Lista ID użytkowników z uprawnieniami administracyjnymi
            **kwargs: Dodatkowe parametry konfiguracyjne
        """
        super().__init__(**kwargs)
        self.admin_users = set(admin_users or [])
        self.user_sessions = {}  # Przechowywanie sesji użytkowników
        
    async def is_user_allowed(self, user_id: int) -> bool:
        """Sprawdza podstawowe uprawnienia użytkownika."""
        # Wszyscy użytkownicy mają podstawowe uprawnienia
        return True
    
    def is_admin(self, user_id: int) -> bool:
        """Sprawdza czy użytkownik jest administratorem."""
        return user_id in self.admin_users
    
    async def before_handle(self, event) -> bool:
        """Hook wykonywany przed każdym handlerem."""
        user = await self.get_user_info(event)
        if user:
            self.logger.debug(f"Użytkownik {user.first_name} ({user.id}) wykonuje akcję")
        return True
    
    async def after_handle(self, event, result: Optional[any] = None, error: Optional[Exception] = None) -> None:
        """Hook wykonywany po każdym handlerze."""
        if error:
            self.logger.error(f"Błąd w domenie {self.DOMAIN}: {error}")
        else:
            self.logger.debug(f"Akcja w domenie {self.DOMAIN} wykonana pomyślnie")
    
    # =================
    # KOMENDY PODSTAWOWE
    # =================
    
    @RD.cmd("start", aliases=["help", "menu"])
    async def start_command(self, event):
        """
        Komenda startowa - wyświetla główne menu bota.
        Dostępna przez /start, /help lub /menu.
        """
        user = await self.get_user_info(event)
        welcome_text = f"🚀 Witaj{f' {user.first_name}' if user else ''}!\n\n"
        welcome_text += "🤖 **Pump Bot Example** - Przykładowy bot dla analizy rynku crypto.\n\n"
        welcome_text += "📋 **Dostępne funkcje:**"
        
        buttons = [
            [
                Button.inline("📈 Trading", b"nav:trading"),
                Button.inline("📊 Analiza", b"nav:analysis")
            ],
            [
                Button.inline("🔔 Alerty", b"nav:alerts"),
                Button.inline("⚙️ Ustawienia", b"nav:settings")
            ]
        ]
        
        # Dodaj przycisk admin dla administratorów
        if user and self.is_admin(user.id):
            buttons.append([Button.inline("👑 Admin", b"nav:admin")])
        
        buttons.append([Button.inline("ℹ️ Info", b"nav:info")])
        
        await event.respond(welcome_text, buttons=buttons)
    
    @RD.cmd("status", aliases=["ping", "health"])
    async def status_command(self, event):
        """
        Komenda sprawdzania statusu bota.
        Dostępna przez /status, /ping lub /health.
        """
        user = await self.get_user_info(event)
        
        status_text = "🟢 **Bot Status: ONLINE**\n\n"
        status_text += f"👤 Użytkownik: {user.first_name if user else 'Nieznany'}\n"
        status_text += f"🆔 ID: `{user.id if user else 'N/A'}`\n"
        status_text += f"📊 Domena: `{self.DOMAIN}`\n"
        status_text += f"🔄 Sesje aktywne: {len(self.user_sessions)}\n"
        
        # Informacje dla adminów
        if user and self.is_admin(user.id):
            status_text += f"\n👑 **Status Admin:**\n"
            status_text += f"⚡ Uptime: Mock - 24h 15m\n"
            status_text += f"💾 Memory: Mock - 245MB\n"
            status_text += f"🌐 Connections: Mock - 127\n"
        
        await event.respond(status_text)
    
    @RD.cmd("quote")
    async def quote_command(self, event):
        """
        Komenda pobierania kursu kryptowaluty.
        Użycie: /quote BTCUSDT
        """
        text = event.raw_text.strip()
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await event.respond(
                "📊 **Podaj symbol do sprawdzenia kursu:**\n\n"
                "Użycie: `/quote BTCUSDT`\n"
                "Przykład: `/quote ETHUSDT`",
                buttons=[
                    [
                        Button.inline("₿ BTC", b"quote:BTCUSDT"),
                        Button.inline("⟠ ETH", b"quote:ETHUSDT")
                    ],
                    [
                        Button.inline("🔙 Menu", b"nav:home")
                    ]
                ]
            )
            return
        
        symbol = parts[1].upper()
        
        # Mock data - w rzeczywistości pobrałbyś z API
        mock_price = {
            "BTCUSDT": {"price": "43,250.67", "change": "+2.34%", "icon": "₿"},
            "ETHUSDT": {"price": "2,678.91", "change": "-1.23%", "icon": "⟠"},
            "ADAUSDT": {"price": "0.4567", "change": "+5.67%", "icon": "🔸"},
        }.get(symbol, {"price": "1,234.56", "change": "+0.00%", "icon": "💰"})
        
        quote_text = f"{mock_price['icon']} **{symbol}**\n\n"
        quote_text += f"💰 **Cena:** `${mock_price['price']}`\n"
        quote_text += f"📈 **Zmiana 24h:** `{mock_price['change']}`\n"
        quote_text += f"🕐 **Ostatnia aktualizacja:** Mock - właśnie teraz\n"
        
        buttons = [
            [
                Button.inline("📊 Analiza", f"analyze:{symbol}".encode()),
                Button.inline("🔔 Alert", f"alert:{symbol}".encode())
            ],
            [Button.inline("🔙 Menu", b"nav:home")]
        ]
        
        await event.respond(quote_text, buttons=buttons)
    
    # ==================
    # WZORCE WIADOMOŚCI
    # ==================
    
    @RD.msg(r"^(hi|hello|cześć|siema|witaj)$")
    async def greet_message(self, event):
        """Odpowiada na pozdrowienia."""
        user = await self.get_user_info(event)
        greeting = f"Cześć{f' {user.first_name}' if user else ''}! 👋\n\n"
        greeting += "Użyj /start aby zobaczyć menu główne."
        
        await event.reply(greeting)
    
    @RD.msg(r"^(ile|jaki|price|cena)\s+(.+)$")
    async def price_question(self, event):
        """Odpowiada na pytania o ceny w naturalnym języku."""
        import re
        match = re.search(r"^(ile|jaki|price|cena)\s+(.+)$", event.raw_text.lower())
        if match:
            symbol_part = match.group(2).upper().replace(" ", "")
            
            # Próbuj dopasować symbol
            if "BTC" in symbol_part or "BITCOIN" in symbol_part:
                symbol = "BTCUSDT"
            elif "ETH" in symbol_part or "ETHEREUM" in symbol_part:
                symbol = "ETHUSDT"
            else:
                symbol = f"{symbol_part}USDT"
            
            response = f"🤔 Pytasz o **{symbol}**?\n\n"
            response += f"Użyj `/quote {symbol}` aby sprawdzić aktualny kurs!\n\n"
            response += "Lub kliknij przycisk poniżej:"
            
            await event.respond(
                response,
                buttons=[Button.inline(f"📊 Kurs {symbol}", f"quote:{symbol}".encode())]
            )
    
    @RD.msg(r"^pump\s+(.+)$")
    async def pump_analysis(self, event):
        """Analizuje potencjalny pump dla podanego symbolu."""
        import re
        match = re.search(r"^pump\s+(.+)$", event.raw_text.lower())
        if not match:
            return
        
        symbol = match.group(1).upper()
        
        await event.respond(f"🚀 **Analiza PUMP dla {symbol}**\n\n🔄 Analizuję...", buttons=None)
        
        # Symulacja oczekiwania na analizę
        import asyncio
        await asyncio.sleep(2)
        
        analysis = f"🚀 **Analiza PUMP - {symbol}**\n\n"
        analysis += f"📊 **Score:** Mock - 7.2/10\n"
        analysis += f"📈 **Trend:** Wzrostowy\n"
        analysis += f"⚡ **Volatility:** Wysoka\n"
        analysis += f"💰 **Volume:** 127M USDT\n"
        analysis += f"🎯 **Rekomendacja:** WAIT\n\n"
        analysis += f"⚠️ **Uwaga:** To jest przykładowa analiza!"
        
        buttons = [
            [Button.inline("🔔 Ustaw Alert", f"alert:{symbol}".encode())],
            [Button.inline("🔙 Menu", b"nav:home")]
        ]
        
        await event.edit(analysis, buttons=buttons)
    
    # ==================
    # CALLBACK QUERIES
    # ==================
    
    @RD.cb(b"nav:home")
    async def nav_home(self, event):
        """Powrót do menu głównego."""
        await self.start_command(event)
    
    @RD.cb(b"nav:trading")
    async def nav_trading(self, event):
        """Menu trading."""
        trading_text = "📈 **Trading Panel**\n\n"
        trading_text += "🔹 Zarządzaj swoimi pozycjami\n"
        trading_text += "🔸 Sprawdzaj kursy w czasie rzeczywistym\n"
        trading_text += "🔹 Analizuj trendy rynkowe\n"
        
        buttons = [
            [
                Button.inline("📊 Kursy", b"quotes:main"),
                Button.inline("📈 Portfel", b"portfolio:main")
            ],
            [
                Button.inline("🎯 Sygnały", b"signals:main"),
                Button.inline("📋 Historia", b"history:main")
            ],
            [Button.inline("🔙 Menu Główne", b"nav:home")]
        ]
        
        await event.edit(trading_text, buttons=buttons)
    
    @RD.cb(b"nav:analysis")
    async def nav_analysis(self, event):
        """Menu analizy."""
        analysis_text = "📊 **Panel Analiz**\n\n"
        analysis_text += "🧠 AI-powered analizy techniczne\n"
        analysis_text += "📰 Analiza fundamentalna\n"
        analysis_text += "🚀 Detekcja potencjalnych PUMP'ów\n"
        
        buttons = [
            [
                Button.inline("🧠 AI Analiza", b"ai:analyze"),
                Button.inline("📰 News", b"news:latest")
            ],
            [
                Button.inline("🚀 PUMP Scanner", b"pump:scanner"),
                Button.inline("📊 Technical", b"technical:main")
            ],
            [Button.inline("🔙 Menu Główne", b"nav:home")]
        ]
        
        await event.edit(analysis_text, buttons=buttons)
    
    @RD.cb(b"nav:alerts")
    async def nav_alerts(self, event):
        """Menu alertów."""
        user = await self.get_user_info(event)
        user_alerts_count = len(self.user_sessions.get(str(user.id) if user else "0", {}).get("alerts", []))
        
        alerts_text = f"🔔 **Panel Alertów**\n\n"
        alerts_text += f"📊 Aktywne alerty: **{user_alerts_count}**\n"
        alerts_text += f"🎯 Otrzymuj powiadomienia o ważnych zmianach\n"
        alerts_text += f"⚡ Błyskawiczne reakcje na rynek\n"
        
        buttons = [
            [
                Button.inline("➕ Nowy Alert", b"alert:create"),
                Button.inline("📋 Moje Alerty", b"alert:list")
            ],
            [
                Button.inline("⚙️ Ustawienia", b"alert:settings"),
                Button.inline("📊 Statystyki", b"alert:stats")
            ],
            [Button.inline("🔙 Menu Główne", b"nav:home")]
        ]
        
        await event.edit(alerts_text, buttons=buttons)
    
    @RD.cb(b"nav:admin")
    async def nav_admin(self, event):
        """Menu administratora - tylko dla uprawnionych."""
        user = await self.get_user_info(event)
        
        if not user or not self.is_admin(user.id):
            await event.answer("⛔️ Brak uprawnień administratora!", alert=True)
            return
        
        admin_text = "👑 **Panel Administratora**\n\n"
        admin_text += f"🔧 Zarządzanie botem\n"
        admin_text += f"📊 Statystyki systemu\n"
        admin_text += f"👥 Zarządzanie użytkownikami\n"
        
        buttons = [
            [
                Button.inline("📊 Stats", b"admin:stats"),
                Button.inline("👥 Users", b"admin:users")
            ],
            [
                Button.inline("🔧 Config", b"admin:config"),
                Button.inline("📋 Logs", b"admin:logs")
            ],
            [Button.inline("🔙 Menu Główne", b"nav:home")]
        ]
        
        await event.edit(admin_text, buttons=buttons)
    
    @RD.cb(b"nav:info")
    async def nav_info(self, event):
        """Informacje o bocie."""
        info_text = "ℹ️ **Informacje o Bocie**\n\n"
        info_text += f"🤖 **Nazwa:** Pump Bot Example\n"
        info_text += f"🏷️ **Wersja:** 1.0.0\n"
        info_text += f"👨‍💻 **Autor:** AI Assistant\n"
        info_text += f"📅 **Data:** 2024\n\n"
        info_text += f"🔧 **Framework:** Telethon\n"
        info_text += f"🎯 **Cel:** Demo systemu routingu\n"
        info_text += f"📝 **Licencja:** MIT\n\n"
        info_text += f"⚠️ **Uwaga:** To jest bot demonstracyjny!"
        
        buttons = [
            [Button.inline("📚 Pomoc", b"help:main")],
            [Button.inline("🔙 Menu Główne", b"nav:home")]
        ]
        
        await event.edit(info_text, buttons=buttons)
    
    # ==================
    # CALLBACK QUERIES - Szczegółowe
    # ==================
    
    @RD.cb(b"quote:")
    async def callback_quote(self, event):
        """Handler dla callbacków quote:SYMBOL."""
        symbol = event.data.decode().split(":", 1)[1]
        
        # Mock data
        mock_price = {
            "BTCUSDT": {"price": "43,250.67", "change": "+2.34%", "icon": "₿"},
            "ETHUSDT": {"price": "2,678.91", "change": "-1.23%", "icon": "⟠"},
        }.get(symbol, {"price": "1,234.56", "change": "+0.00%", "icon": "💰"})
        
        quote_text = f"{mock_price['icon']} **{symbol}**\n\n"
        quote_text += f"💰 **Cena:** `${mock_price['price']}`\n"
        quote_text += f"📈 **Zmiana 24h:** `{mock_price['change']}`\n"
        quote_text += f"🕐 **Aktualizacja:** właśnie teraz\n"
        
        buttons = [
            [Button.inline("🔄 Odśwież", f"quote:{symbol}".encode())],
            [Button.inline("🔙 Wstecz", b"nav:home")]
        ]
        
        await event.edit(quote_text, buttons=buttons)
    
    @RD.cb(b"alert:")
    async def callback_alert_setup(self, event):
        """Handler do konfiguracji alertów."""
        data_parts = event.data.decode().split(":", 2)
        
        if len(data_parts) < 2:
            await event.answer("⚠️ Błędne dane alertu", alert=True)
            return
        
        if data_parts[1] == "create":
            alert_text = "🔔 **Tworzenie Nowego Alertu**\n\n"
            alert_text += "📝 Wybierz typ alertu:\n"
            
            buttons = [
                [
                    Button.inline("📈 Cena wyżej", b"alert:type:price_above"),
                    Button.inline("📉 Cena niżej", b"alert:type:price_below")
                ],
                [
                    Button.inline("💥 Pump Alert", b"alert:type:pump"),
                    Button.inline("🚨 Volume Alert", b"alert:type:volume")
                ],
                [Button.inline("🔙 Wstecz", b"nav:alerts")]
            ]
            
            await event.edit(alert_text, buttons=buttons)
            
        elif len(data_parts) >= 2:
            # Alert dla konkretnego symbolu
            symbol = data_parts[1]
            alert_text = f"🔔 **Alert dla {symbol}**\n\n"
            alert_text += f"⚡ Skonfiguruj alert dla tego symbolu\n"
            alert_text += f"📊 Aktualny kurs: Mock - $42,150.67\n\n"
            alert_text += f"📝 **Dostępne typy alertów:**\n"
            
            buttons = [
                [Button.inline("📈 Cena > X", f"alert:setup:{symbol}:above".encode())],
                [Button.inline("📉 Cena < X", f"alert:setup:{symbol}:below".encode())],
                [Button.inline("🔙 Wstecz", b"nav:alerts")]
            ]
            
            await event.edit(alert_text, buttons=buttons)
    
    @RD.cb(b"admin:")
    async def callback_admin(self, event):
        """Handlery dla panelu administratora."""
        user = await self.get_user_info(event)
        if not user or not self.is_admin(user.id):
            await event.answer("⛔️ Brak uprawnień!", alert=True)
            return
        
        action = event.data.decode().split(":", 1)[1]
        
        if action == "stats":
            stats_text = "📊 **Statystyki Systemu**\n\n"
            stats_text += f"👥 **Użytkownicy:** Mock - 1,234\n"
            stats_text += f"📨 **Wiadomości:** Mock - 15,678\n"
            stats_text += f"⚡ **Requests/min:** Mock - 45\n"
            stats_text += f"🔔 **Aktywne alerty:** Mock - 89\n"
            stats_text += f"💾 **Użycie RAM:** Mock - 245MB\n"
            stats_text += f"🏃 **Uptime:** Mock - 5d 12h 34m\n"
            
            buttons = [[Button.inline("🔙 Admin Panel", b"nav:admin")]]
            await event.edit(stats_text, buttons=buttons)
            
        elif action == "users":
            users_text = "👥 **Zarządzanie Użytkownikami**\n\n"
            users_text += f"📊 **Aktywni użytkownicy:** Mock - 342\n"
            users_text += f"🆕 **Nowi (24h):** Mock - 23\n"
            users_text += f"👑 **Administratorzy:** {len(self.admin_users)}\n"
            users_text += f"🚫 **Zablokowani:** Mock - 5\n"
            
            buttons = [
                [Button.inline("📋 Lista", b"admin:users:list")],
                [Button.inline("🔙 Admin Panel", b"nav:admin")]
            ]
            await event.edit(users_text, buttons=buttons)
