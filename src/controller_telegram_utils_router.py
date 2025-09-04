"""
System routingu dla Telethon - separacja logiki handlerów w klasy domenowe.

Ten moduł zawiera:
- RouterDecorators (RD): Fabrykę dekoratorów dla oznaczania metod handlerów
- ClassRouter: Główną klasę do zbierania i rejestrowania handlerów
- BoundRoute: Dataclass przechowujący informacje o routach
- DomainBase: Bazową klasę dla klas domenowych

Autor: AI Assistant
"""

import asyncio
import logging
import re
import traceback
from dataclasses import dataclass
from typing import Callable, Pattern, List, Optional, Any, Dict, Union
from abc import ABC, abstractmethod

from telethon import events, Button
from telethon.tl.types import User

logger = logging.getLogger(__name__)


@dataclass
class BoundRoute:
    """
    Reprezentuje zbindowany route zawierający wszystkie informacje 
    potrzebne do obsługi zdarzenia w Telethon.
    """
    kind: str                    # "msg" | "cb" | "cmd"
    pattern: Union[Pattern, bytes, str]  # wzorzec dla dopasowania
    handler: Callable           # funkcja obsługująca zdarzenie
    domain: str                 # nazwa domeny (np. "trading", "admin")
    owner: Any                  # instancja klasy domeny
    aliases: Optional[List[str]] = None  # aliasy dla komend


class RouterDecorators:
    """
    Fabryka dekoratorów dla oznaczania metod jako handlerów Telethon.
    
    Użycie:
        @RD.cmd("start", aliases=["help"])
        @RD.msg(r"^hello.*")  
        @RD.cb(b"nav:trading")
    """
    
    @staticmethod
    def cmd(name: str, *, aliases: Optional[List[str]] = None, domain: Optional[str] = None):
        """
        Dekorator dla komend (wiadomości zaczynających się od /).
        
        Args:
            name: Nazwa komendy (bez /)
            aliases: Lista aliasów komendy
            domain: Opcjonalna nazwa domeny (nadpisuje DOMAIN z klasy)
            
        Przykład:
            @RD.cmd("start", aliases=["help", "begin"])
            async def start_handler(self, event): ...
        """
        def decorator(func):
            func._route_meta = {
                "kind": "cmd", 
                "name": name, 
                "aliases": aliases or [], 
                "domain": domain
            }
            return func
        return decorator
    
    @staticmethod
    def msg(pattern: str, *, flags: int = re.IGNORECASE, domain: Optional[str] = None):
        """
        Dekorator dla wiadomości dopasowywanych przez regex.
        
        Args:
            pattern: Wzorzec regex
            flags: Flagi regex (domyślnie re.IGNORECASE)
            domain: Opcjonalna nazwa domeny
            
        Przykład:
            @RD.msg(r"^(hi|hello|cześć)$")
            async def greet_handler(self, event): ...
        """
        def decorator(func):
            func._route_meta = {
                "kind": "msg", 
                "pattern": re.compile(pattern, flags), 
                "domain": domain
            }
            return func
        return decorator
    
    @staticmethod
    def cb(prefix: bytes, *, domain: Optional[str] = None):
        """
        Dekorator dla callback queries (inline buttons).
        
        Args:
            prefix: Prefiks callback data (jako bytes)
            domain: Opcjonalna nazwa domeny
            
        Przykład:
            @RD.cb(b"nav:trading")
            async def nav_trading_handler(self, event): ...
        """
        def decorator(func):
            func._route_meta = {
                "kind": "cb", 
                "prefix": prefix, 
                "domain": domain
            }
            return func
        return decorator


# Globalna instancja do importu w domenach
RD = RouterDecorators()


class DomainBase(ABC):
    """
    Bazowa klasa dla wszystkich domen handlerów Telethon.
    
    Każda domena powinna dziedziczyć po tej klasie i zdefiniować
    stałą DOMAIN oraz implementować potrzebne metody.
    """
    
    DOMAIN: str = ""  # Nazwa domeny - powinna być nadpisana w klasach dziedziczących
    
    def __init__(self, **kwargs):
        """Inicjalizacja domeny z opcjonalnymi parametrami konfiguracyjnymi."""
        self.config = kwargs
        self.logger = logging.getLogger(f"domain.{self.get_domain_name()}")
    
    def get_domain_name(self) -> str:
        """Zwraca nazwę domeny - DOMAIN lub nazwę klasy."""
        return self.DOMAIN or self.__class__.__name__.lower().replace('domain', '')
    
    async def is_user_allowed(self, user_id: int) -> bool:
        """
        Sprawdza czy użytkownik ma uprawnienia do wykonania akcji w tej domenie.
        Domyślnie wszyscy użytkownicy mają dostęp.
        """
        return True
    
    async def before_handle(self, event) -> bool:
        """
        Hook wykonywany przed obsługą każdego zdarzenia.
        Zwraca True jeśli zdarzenie ma być obsłużone, False w przeciwnym razie.
        """
        return True
    
    async def after_handle(self, event, result: Any = None, error: Optional[Exception] = None) -> None:
        """
        Hook wykonywany po obsłużeniu każdego zdarzenia.
        Może być używany do logowania, metryk itp.
        """
        if error:
            self.logger.error(f"Błąd w handlerze: {error}")
        else:
            self.logger.debug(f"Handler wykonany pomyślnie")
    
    async def get_user_info(self, event) -> Optional[User]:
        """Pomocna metoda do pobierania informacji o użytkowniku."""
        try:
            return await event.get_sender()
        except Exception as e:
            self.logger.warning(f"Nie można pobrać informacji o użytkowniku: {e}")
            return None


class ClassRouter:
    """
    Główna klasa routingu odpowiedzialna za:
    - Zbieranie handlerów z klas domenowych
    - Rejestrowanie ich w kliencie Telethon
    - Middleware dla obsługi błędów i logowania
    """
    
    def __init__(self, enable_logging: bool = True, enable_error_responses: bool = True):
        """
        Inicjalizacja routera.
        
        Args:
            enable_logging: Czy włączyć logowanie zdarzeń
            enable_error_responses: Czy wysyłać wiadomości o błędach do użytkowników
        """
        self.routes: List[BoundRoute] = []
        self.domains: Dict[str, DomainBase] = {}
        self.enable_logging = enable_logging
        self.enable_error_responses = enable_error_responses
        self.logger = logging.getLogger("telegram.router")
        
        # Statystyki
        self.stats = {
            "messages_processed": 0,
            "callbacks_processed": 0,
            "commands_processed": 0,
            "errors_count": 0
        }
    
    def mount(self, domain_instance: DomainBase, domain_name: Optional[str] = None) -> None:
        """
        Montuje instancję domeny - skanuje jej metody w poszukiwaniu handlerów.
        
        Args:
            domain_instance: Instancja klasy domenowej
            domain_name: Opcjonalna nazwa domeny (nadpisuje auto-detection)
        """
        domain_name = domain_name or domain_instance.get_domain_name()
        
        if domain_name in self.domains:
            self.logger.warning(f"Domena '{domain_name}' już istnieje - zostanie nadpisana")
        
        self.domains[domain_name] = domain_instance
        
        # Skanowanie metod klasy w poszukiwaniu handlerów
        for attr_name in dir(domain_instance):
            if attr_name.startswith("_"):
                continue
                
            method = getattr(domain_instance, attr_name)
            route_meta = getattr(method, "_route_meta", None)
            
            if not route_meta or not callable(method):
                continue
            
            self._process_route_meta(method, route_meta, domain_instance, domain_name)
        
        self.logger.info(f"Zmontowano domenę '{domain_name}' z {len([r for r in self.routes if r.domain == domain_name])} handlerami")
    
    def _process_route_meta(self, method: Callable, route_meta: dict, 
                          domain_instance: DomainBase, domain_name: str) -> None:
        """Przetwarza metadane route i tworzy BoundRoute."""
        kind = route_meta["kind"]
        explicit_domain = route_meta.get("domain") or domain_name
        
        if kind == "cmd":
            # Dla komend tworzymy wzorzec regex
            name = route_meta["name"]
            aliases = route_meta.get("aliases", [])
            
            if aliases:
                pattern_str = rf"^/(?:{name}|{'|'.join(aliases)})(?:\s+.*)?$"
            else:
                pattern_str = rf"^/{name}(?:\s+.*)?$"
                
            pattern = re.compile(pattern_str, re.IGNORECASE)
            
            bound_route = BoundRoute(
                kind="msg",  # Komendy są obsługiwane jako wiadomości
                pattern=pattern,
                handler=method,
                domain=explicit_domain,
                owner=domain_instance,
                aliases=aliases
            )
            
        elif kind == "msg":
            bound_route = BoundRoute(
                kind="msg",
                pattern=route_meta["pattern"],
                handler=method,
                domain=explicit_domain,
                owner=domain_instance
            )
            
        elif kind == "cb":
            bound_route = BoundRoute(
                kind="cb",
                pattern=route_meta["prefix"],
                handler=method,
                domain=explicit_domain,
                owner=domain_instance
            )
        else:
            self.logger.warning(f"Nieznany typ route: {kind}")
            return
        
        self.routes.append(bound_route)
    
    async def _invoke_handler(self, route: BoundRoute, event) -> None:
        """
        Wywołuje handler z middleware (logging, error handling, hooks).
        """
        domain_instance = route.owner
        handler_name = route.handler.__name__
        
        try:
            # Hook before_handle
            if not await domain_instance.before_handle(event):
                self.logger.debug(f"Handler {handler_name} anulowany przez before_handle")
                return
            
            # Sprawdzenie uprawnień użytkownika
            user = await domain_instance.get_user_info(event)
            if user and not await domain_instance.is_user_allowed(user.id):
                await event.respond("⛔️ Brak uprawnień do wykonania tej akcji.")
                return
            
            # Logowanie
            if self.enable_logging:
                user_info = f"user:{user.id}" if user else "user:unknown"
                self.logger.info(f"Obsługa {route.kind} przez {route.domain}.{handler_name} ({user_info})")
            
            # Wywołanie handlera
            result = await route.handler(event)
            
            # Hook after_handle - sukces
            await domain_instance.after_handle(event, result=result)
            
            # Aktualizacja statystyk
            if route.kind == "msg":
                self.stats["messages_processed"] += 1
            elif route.kind == "cb":
                self.stats["callbacks_processed"] += 1
                
        except Exception as e:
            self.stats["errors_count"] += 1
            
            # Hook after_handle - błąd
            await domain_instance.after_handle(event, error=e)
            
            # Logowanie błędu
            self.logger.error(f"Błąd w handlerze {route.domain}.{handler_name}: {e}")
            self.logger.debug(traceback.format_exc())
            
            # Odpowiedź użytkownikowi o błędzie (jeśli włączone)
            if self.enable_error_responses:
                try:
                    error_msg = f"⚠️ Wystąpił błąd podczas przetwarzania żądania."
                    if hasattr(event, 'respond'):
                        await event.respond(error_msg)
                    elif hasattr(event, 'edit'):
                        await event.edit(error_msg)
                except Exception as resp_error:
                    self.logger.error(f"Nie można wysłać wiadomości o błędzie: {resp_error}")
    
    def attach(self, client) -> None:
        """
        Załącza router do klienta Telethon - rejestruje wszystkie handlery.
        
        Args:
            client: Instancja TelegramClient z Telethon
        """
        if not self.routes:
            self.logger.warning("Brak routów do załączenia!")
            return
        
        # Handler dla wiadomości (w tym komendy)
        @client.on(events.NewMessage(incoming=True))
        async def _on_new_message(event):
            if not event.raw_text:
                return
                
            text = event.raw_text.strip()
            
            for route in self.routes:
                if route.kind != "msg":
                    continue
                    
                if isinstance(route.pattern, re.Pattern):
                    if route.pattern.search(text):
                        await self._invoke_handler(route, event)
                        return  # Pierwszy match wygrywa
        
        # Handler dla callback queries (inline buttons)
        @client.on(events.CallbackQuery)
        async def _on_callback_query(event):
            if not event.data:
                return
                
            for route in self.routes:
                if route.kind != "cb":
                    continue
                    
                if isinstance(route.pattern, bytes) and event.data.startswith(route.pattern):
                    await self._invoke_handler(route, event)
                    return  # Pierwszy match wygrywa
        
        self.logger.info(f"Załączono router z {len(self.routes)} routami do klienta Telethon")
    
    def get_routes_summary(self) -> Dict[str, List[str]]:
        """
        Zwraca podsumowanie wszystkich zarejestrowanych routów pogrupowane po domenach.
        
        Returns:
            Dict z domenami jako kluczami i listami opisów routów jako wartościami
        """
        summary: Dict[str, List[str]] = {}
        
        for route in self.routes:
            domain_routes = summary.setdefault(route.domain, [])
            
            if route.kind == "msg" and isinstance(route.pattern, re.Pattern):
                pattern_str = route.pattern.pattern
                
                # Próba wyciągnięcia nazwy komendy z wzorca
                if pattern_str.startswith("^/(?:") and route.aliases:
                    # Komenda z aliasami
                    cmd_part = pattern_str.split("(?:", 1)[1].split(")")[0]
                    commands = cmd_part.split("|")
                    for cmd in commands:
                        domain_routes.append(f"/{cmd}")
                elif pattern_str.startswith("^/"):
                    # Prosta komenda
                    cmd = pattern_str.split("/", 1)[1].split("(?:", 1)[0]
                    domain_routes.append(f"/{cmd}")
                else:
                    # Wzorzec wiadomości
                    domain_routes.append(f"msg: {pattern_str}")
                    
            elif route.kind == "cb":
                domain_routes.append(f"callback: {route.pattern.decode()}")
        
        return summary
    
    def get_stats(self) -> Dict[str, int]:
        """Zwraca statystyki routera."""
        return self.stats.copy()
    
    def get_domains(self) -> Dict[str, DomainBase]:
        """Zwraca słownik wszystkich zmontowanych domen."""
        return self.domains.copy()
