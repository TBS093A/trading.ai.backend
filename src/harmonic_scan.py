"""
Skanowanie formacji harmonicznych XABCD w zadanym zakresie czasu, z trwałym cache w bazie.

Wyniki zapisuje worker Celery: formacje do technical_analysis_harmonic_patterns (ta sama tabela
i ta sama deduplikacja po punktach co nocny sync), a okna, które przeskanował, do
technical_analysis_harmonic_scan_windows. Następny request o zakres już przeskanowany czyta wyniki
z bazy, a liczy tylko brakujące fragmenty.

Kiedy fragment jest "pokryty"? Formacja jest gwarantowanie znaleziona, jeśli wszystkie jej punkty
leżą w JEDNYM przeskanowanym oknie. Sąsiednie okna, które nachodzą na siebie o co najmniej
MAX_PATTERN_SPAN (500 x interwał czasu kalendarzowego), działają jak jedno okno dla formacji nie
dłuższych niż ta rozpiętość. Brakujące fragmenty skanujemy z zakładką MAX_PATTERN_SPAN w każdą
stronę, więc nowe okna łączą się z istniejącymi, a formacje przechodzące przez granicę też są
znalezione. Formacje dłuższe niż MAX_PATTERN_SPAN mogą być pominięte na granicach okien.

Szczyty i dołki wymagają świec po obu stronach, więc każde okno liczone jest na świecach z
zapasem PAD_CANDLES, a zapisywane są tylko formacje w całości wewnątrz okna.
"""

import hashlib
import json
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
    "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000, "1M": 2_592_000_000,
    # Interwały nocnego syncu (TechnicalAnalysis.CHART_INTERVALS) - ta sama nazwa w bazie.
    "3M": 93 * 86_400_000, "1Y": 365 * 86_400_000,
}

MAX_PATTERN_CANDLES = 500     # = tryb "ostatnie 500 świec"
MAX_RANGE_CANDLES = 2000      # górna granica zakresu z frontu (koszt wyszukiwania rośnie szybciej niż liniowo)
DEFAULT_RANGE_CANDLES = 500
PAD_CANDLES = 30              # = największy peak_spacing silnika
PAD_CALENDAR_FACTOR = 3       # zapas czasu na weekendy / sesje giełd akcji (Yahoo)
KLINES_PAGE = 1000

# Parametry silnika - hash wchodzi do klucza pokrycia, więc zmiana ustawień HarmonicPatterns
# (np. inny zestaw peak_spacing) automatycznie unieważnia stare okna.
SCAN_PARAMS: Dict[str, Any] = {
    "engine": "pyharmonics/HarmonicPatterns",
    "find_xabcd": True,
    "find_abcd": True,
    "find_abc": False,
    "fib_tolerance": {"hard_restricted": 0.03},
    "peak_spacing": list(range(3, 31)),
    "pad_candles": PAD_CANDLES,
    "max_pattern_candles": MAX_PATTERN_CANDLES,
    "version": 1,
}

EXCHANGE_PRIORITY = ("BINANCE", "YAHOO")

Window = Tuple[int, int]


def params_hash(params: Dict[str, Any] = SCAN_PARAMS) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def interval_ms(interval: str) -> int:
    try:
        return INTERVAL_MS[interval]
    except KeyError:
        raise ValueError(f"nieobsługiwany interwał: {interval}")


def max_pattern_span_ms(interval: str) -> int:
    return MAX_PATTERN_CANDLES * interval_ms(interval)


WEEK_OFFSET_MS = 4 * 86_400_000  # 1970-01-01 to czwartek; tygodnie Binance zaczynają się w poniedziałek


def align_down(interval: str, t_ms: int) -> int:
    """open_time świecy, w której leży t_ms (świece Binance: UTC, tydzień od poniedziałku,
    miesiąc/kwartał/rok od pierwszego dnia)."""
    from datetime import datetime, timezone

    if interval in ("1M", "3M", "1Y"):
        d = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)
        if interval == "1Y":
            d = d.replace(month=1)
        elif interval == "3M":
            d = d.replace(month=(d.month - 1) // 3 * 3 + 1)
        d = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return int(d.timestamp() * 1000)
    step = interval_ms(interval)
    offset = WEEK_OFFSET_MS if interval == "1w" else 0
    return (t_ms - offset) // step * step + offset


def last_closed_open_time(interval: str, now_ms: int) -> int:
    return align_down(interval, align_down(interval, now_ms) - 1)


def resolve_range(interval: str, start_time: Optional[int], end_time: Optional[int], now_ms: int) -> Window:
    """Zakres [start, end] (open_time świec) ograniczony do zamkniętych świec.

    Domyślnie ostatnie DEFAULT_RANGE_CANDLES zamkniętych świec; sam start_time = od startu do
    ostatniej zamkniętej; sam end_time = DEFAULT_RANGE_CANDLES świec kończących się na end_time.
    Koniec jest wyrównany do open_time ostatniej zamkniętej świecy - zakres (a więc i klucz
    pokrycia) zmienia się dopiero, gdy zamknie się nowa świeca, a nie co milisekundę.
    """
    step = interval_ms(interval)
    last_closed = last_closed_open_time(interval, now_ms)
    end = min(end_time, last_closed) if end_time is not None else last_closed
    start = start_time if start_time is not None else end - (DEFAULT_RANGE_CANDLES - 1) * step
    if start >= end:
        raise ValueError("start_time musi być wcześniejszy niż end_time (i niż ostatnia zamknięta świeca)")
    if (end - start) // step + 1 > MAX_RANGE_CANDLES:
        raise ValueError(f"zakres może mieć najwyżej {MAX_RANGE_CANDLES} świec (interwał {interval})")
    return start, end


def _merge(windows: Iterable[Window], required_overlap: int) -> List[Window]:
    merged: List[List[int]] = []
    for s, e in sorted(windows):
        if merged and (s <= merged[-1][1] - required_overlap or e <= merged[-1][1]):
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def missing_windows(request: Window, scanned: Sequence[Window], span: int) -> List[Window]:
    """Okna do przeskanowania, żeby każda formacja z rozpiętością <= span w `request` była znaleziona.

    `scanned` - okna już przeskanowane (te same parametry silnika). Łańcuchy okien nachodzących na
    siebie o >= span działają jak jedno okno; luki między łańcuchami i styki z małą zakładką
    skanujemy z zakładką `span` w każdą stronę (przycięte do `request`).
    """
    rs, re_ = request
    chains = [(s, e) for s, e in _merge(scanned, span) if e >= rs and s <= re_]
    needed: List[Window] = []

    def add(s: int, e: int) -> None:
        s, e = max(rs, s), min(re_, e)
        if s < e:
            needed.append((s, e))

    cursor: Optional[int] = None  # koniec ostatniego łańcucha w obrębie request
    for cs, ce in chains:
        if cursor is None:
            if cs > rs:
                add(rs, cs + span)  # luka na początku zakresu
        elif cs > rs and cursor < re_:
            # Luka między łańcuchami albo styk z zakładką < span: każda formacja (<= span), która
            # ma punkt w luce lub przechodzi przez styk, mieści się w (cursor - span, cs + span).
            # Nowe okno nachodzi na oba łańcuchy o span (albo sięga granicy zakresu), więc potem
            # się z nimi łączy. Styk, który dotyka granicy zakresu (cs <= rs albo cursor >= re_),
            # nie ma formacji w całości wewnątrz zakresu, które by przez niego przechodziły.
            add(cursor - span, cs + span)
        cursor = ce if cursor is None else max(cursor, ce)
    if cursor is None:
        add(rs, re_)
    elif cursor < re_:
        add(cursor - span, re_)  # luka na końcu zakresu
    return _merge(needed, 0)


def pattern_bounds(pattern: Dict[str, Any]) -> Optional[Window]:
    """Najwcześniejszy i najpóźniejszy punkt formacji (ms)."""
    ts = [pattern.get(f"{p}_point_timestamp") for p in ("x", "a", "b", "c", "d")]
    ts = [t for t in ts if t is not None]
    return (min(ts), max(ts)) if ts else None


def patterns_inside(patterns: Iterable[Dict[str, Any]], window: Window) -> List[Dict[str, Any]]:
    out = []
    for p in patterns:
        b = pattern_bounds(p)
        if b and window[0] <= b[0] and b[1] <= window[1]:
            out.append(p)
    return out


def padded_window(interval: str, window: Window, now_ms: int) -> Window:
    pad = PAD_CANDLES * interval_ms(interval) * PAD_CALENDAR_FACTOR
    return window[0] - pad, min(window[1] + pad, now_ms)


def pick_exchange(asset_exchange_names: Iterable[str]) -> Optional[str]:
    """Ta sama kolejność co GET /exchanges/klines - wykres i skan liczą na tych samych świecach."""
    names = {n.upper() for n in asset_exchange_names if n}
    for prio in EXCHANGE_PRIORITY:
        if any(prio in n for n in names):
            return prio
    return None


def fetch_klines_range(
    get_klines: Callable[..., List[Dict[str, Any]]],
    base: str, quote: str, interval: str, start: int, end: int,
) -> List[Dict[str, Any]]:
    """Wszystkie świece z [start, end], stronami po KLINES_PAGE od najnowszych (end_time -> wstecz)."""
    by_open: Dict[int, Dict[str, Any]] = {}
    cursor = end
    while True:
        page = get_klines(base_currency=base, quote_currency=quote, interval=interval,
                          start_time=start, end_time=cursor, limit=KLINES_PAGE)
        page = [k for k in page if start <= k["open_time"] <= end]
        for k in page:
            by_open[k["open_time"]] = k
        if len(page) < KLINES_PAGE:
            break
        oldest = min(k["open_time"] for k in page)
        if oldest <= start or oldest - 1 >= cursor:
            break
        cursor = oldest - 1
    return [by_open[t] for t in sorted(by_open)]
