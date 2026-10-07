"""
Cache stron klines dla GET /exchanges/klines/{asset_id}/{interval}.

Frontend doładowuje historię wykresu stronami (end_time = najstarszy open_time - 1, limit=1000),
więc te same strony wracają często, a zamknięte świece się nie zmieniają:

- strona historyczna (end_time podany i każda świeca zamknięta przed "teraz") jest niezmienna -
  trzymana długo, a klient dostaje Cache-Control immutable;
- strona "na żywo" (bez end_time albo z niezamkniętą ostatnią świecą) - kilka sekund.

Dodatkowo:
- jedno zapytanie do giełdy na klucz naraz (single-flight) - burza identycznych requestów przy
  przewijaniu wykresu idzie upstream raz;
- limit równoległych zapytań na giełdę (rate limity, np. waga requestów Binance);
- synchroniczne klienty giełd (requests / yfinance) uruchamiane w wątku, nie w pętli zdarzeń
  uvicorna - wcześniej każde zapytanie upstream blokowało cały proces API.

Cache jest w pamięci procesu: rest-api-controller ma jedną replikę. Rozmiar ograniczony liczbą
świec (LRU), bo pod ma limit 1Gi.
"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, Hashable, List, Optional, Tuple

# Kolejność pól świecy w cache (krotki zamiast dictów - kilka razy mniej pamięci).
KLINE_FIELDS = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base_volume", "taker_buy_quote_volume",
)
COMPACT_FIELDS = ("open_time", "open", "high", "low", "close", "volume")

HISTORY_TTL_SECONDS = 24 * 3600
HEAD_TTL_SECONDS = 5
MAX_CACHED_CANDLES = 100_000
UPSTREAM_CONCURRENCY_PER_EXCHANGE = 4

CACHE_CONTROL_HISTORY = "private, max-age=31536000, immutable"
CACHE_CONTROL_HEAD = f"private, max-age={HEAD_TTL_SECONDS}"


def to_rows(klines: List[Dict[str, Any]]) -> List[Tuple]:
    """Dicty z klienta giełdy -> krotki w kolejności KLINE_FIELDS (brakujące pola: None)."""
    return [tuple(k.get(f) for f in KLINE_FIELDS) for k in klines]


def to_objects(rows: List[Tuple]) -> List[Dict[str, Any]]:
    """Krotki -> dicty jak dotychczas zwracał endpoint (pola None pomijane - Yahoo ich nie ma)."""
    return [{f: v for f, v in zip(KLINE_FIELDS, row) if v is not None} for row in rows]


def to_compact(rows: List[Tuple]) -> List[List[Any]]:
    """Krotki -> [[open_time, open, high, low, close, volume], ...]."""
    n = len(COMPACT_FIELDS)
    return [list(row[:n]) for row in rows]


def is_closed_history(rows: List[Tuple], end_time: Optional[int], now_ms: int) -> bool:
    """Strona jest niezmienna, gdy klient przypiął end_time i każda świeca jest już zamknięta.

    Bez end_time strona przesuwa się razem z czasem (najnowsze świece), więc nigdy nie jest
    historyczna. Pusta strona z end_time w przeszłości też jest niezmienna (koniec historii).
    """
    if end_time is None:
        return False
    if end_time >= now_ms:
        return False
    close_idx = KLINE_FIELDS.index("close_time")
    open_idx = KLINE_FIELDS.index("open_time")
    for row in rows:
        closed_at = row[close_idx] if row[close_idx] is not None else row[open_idx]
        if closed_at is None or closed_at >= now_ms:
            return False
    return True


@dataclass
class Page:
    rows: List[Tuple]
    immutable: bool
    expires_at: float


class KlinesPageCache:
    def __init__(
        self,
        max_candles: int = MAX_CACHED_CANDLES,
        history_ttl: float = HISTORY_TTL_SECONDS,
        head_ttl: float = HEAD_TTL_SECONDS,
        upstream_concurrency: int = UPSTREAM_CONCURRENCY_PER_EXCHANGE,
        clock: Callable[[], float] = time.time,
    ):
        self._pages: "OrderedDict[Hashable, Page]" = OrderedDict()
        self._candles = 0
        self._inflight: Dict[Hashable, "asyncio.Future[Page]"] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._max_candles = max_candles
        self._history_ttl = history_ttl
        self._head_ttl = head_ttl
        self._upstream_concurrency = upstream_concurrency
        self._clock = clock
        self.upstream_calls = 0

    def _semaphore(self, exchange: str) -> asyncio.Semaphore:
        if exchange not in self._semaphores:
            self._semaphores[exchange] = asyncio.Semaphore(self._upstream_concurrency)
        return self._semaphores[exchange]

    def _get_fresh(self, key: Hashable) -> Optional[Page]:
        page = self._pages.get(key)
        if page is None:
            return None
        if page.expires_at <= self._clock():
            self._drop(key)
            return None
        self._pages.move_to_end(key)
        return page

    def _drop(self, key: Hashable) -> None:
        page = self._pages.pop(key, None)
        if page is not None:
            self._candles -= len(page.rows)

    def _store(self, key: Hashable, page: Page) -> None:
        self._drop(key)
        self._pages[key] = page
        self._candles += len(page.rows)
        while self._candles > self._max_candles and len(self._pages) > 1:
            oldest = next(iter(self._pages))
            self._drop(oldest)

    async def get_page(
        self,
        key: Hashable,
        exchange: str,
        fetch: Callable[[], List[Dict[str, Any]]],
        end_time: Optional[int],
    ) -> Page:
        """Strona z cache albo z giełdy. `fetch` jest synchroniczny i biegnie w wątku."""
        page = self._get_fresh(key)
        if page is not None:
            return page

        inflight = self._inflight.get(key)
        if inflight is not None:
            return await asyncio.shield(inflight)

        future: "asyncio.Future[Page]" = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            async with self._semaphore(exchange):
                self.upstream_calls += 1
                klines = await asyncio.to_thread(fetch)
            rows = to_rows(klines)
            now = self._clock()
            immutable = is_closed_history(rows, end_time, int(now * 1000))
            page = Page(rows=rows, immutable=immutable,
                        expires_at=now + (self._history_ttl if immutable else self._head_ttl))
            self._store(key, page)
            future.set_result(page)
            return page
        except BaseException as error:
            # Błędy nie trafiają do cache - czekający dostają ten sam wyjątek, następny request
            # próbuje ponownie.
            future.set_exception(error)
            # Wyjątek future jest "odebrany" przez czekających; gdy nikt nie czekał, nie loguj
            # "Future exception was never retrieved".
            future.exception()
            raise
        finally:
            self._inflight.pop(key, None)


klines_cache = KlinesPageCache()


class KlinesGZipMiddleware:
    """GZip tylko dla wybranych ścieżek z danymi rynkowymi (świece, formacje harmoniczne).

    Celowo nie dla całego API: kompresja odpowiedzi, które niosą sekrety (token CSRF, dane
    sesji) obok danych zależnych od requestu, otwiera atak BREACH. Świece i formacje to publiczne
    dane rynkowe - kompresja ich nic nie zdradza.
    """

    def __init__(self, app, path_prefix=("/exchanges/klines/",), minimum_size: int = 1000):
        from starlette.middleware.gzip import GZipMiddleware

        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=minimum_size)
        self.path_prefixes = (path_prefix,) if isinstance(path_prefix, str) else tuple(path_prefix)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path", "").startswith(self.path_prefixes):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)
