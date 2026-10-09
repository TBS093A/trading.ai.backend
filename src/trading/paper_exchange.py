"""
Giełda symulowana: wypełnienia zleceń na świecach - te same reguły co symulator setupów
(src/harmonic_setups.simulate, src/setup_variants), żeby paper był porównywalny z backtestem:

- zlecenie limit wejścia wypełnia się, gdy świeca dotknie ceny; po cenie otwarcia, jeśli świeca otworzyła
  się już za ceną (luka), inaczej po cenie zlecenia; opłata maker;
- w świecy wejścia liczy się tylko SL (jej ekstremum mogło być przed wejściem);
- SL i TP w tej samej świecy -> SL (konserwatywnie); SL to zlecenie stop: poślizg i opłata taker;
- TP to zlecenie limit: po cenie TP, opłata maker.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Fill:
    price: float
    time: int        # open_time świecy (ms)
    index: int       # indeks świecy w przekazanej liście


def _ohlc(k: Dict) -> tuple:
    return float(k["open"]), float(k["high"]), float(k["low"]), float(k["close"])


def match_limit_entry(candles: List[Dict], direction: str, price: float) -> Optional[Fill]:
    """Pierwsza świeca, w której limit wejścia się wypełnia (long: low <= cena, short: high >= cena)."""
    for i, k in enumerate(candles):
        o, h, l, _ = _ohlc(k)
        if direction == "long" and l <= price:
            return Fill(min(o, price), int(k["open_time"]), i)
        if direction == "short" and h >= price:
            return Fill(max(o, price), int(k["open_time"]), i)
    return None


def match_exit(candles: List[Dict], direction: str, sl: float, tp: float, entry_time: int,
               slippage_pct: float = 0.0, entered_at_open: bool = False) -> Optional[Dict]:
    """Pierwsze wyjście po wejściu: {"reason": "sl"|"tp", "fill": Fill} albo None (pozycja otwarta).

    entered_at_open: wejście na otwarciu świecy entry_time (tryb "confirm" - rynek po zamknięciu poprzedniej),
    więc TP w tej świecy też się liczy; przy limicie dotkniętym w trakcie świecy - tylko SL.
    """
    slip = slippage_pct / 100.0
    for i, k in enumerate(candles):
        t = int(k["open_time"])
        if t < entry_time:
            continue
        o, h, l, _ = _ohlc(k)
        if direction == "long":
            if l <= sl:
                return {"reason": "sl", "fill": Fill(min(o, sl) * (1 - slip), t, i)}
            if (t > entry_time or entered_at_open) and h >= tp:
                return {"reason": "tp", "fill": Fill(max(o, tp) if o > tp else tp, t, i)}
        else:
            if h >= sl:
                return {"reason": "sl", "fill": Fill(max(o, sl) * (1 + slip), t, i)}
            if (t > entry_time or entered_at_open) and l <= tp:
                return {"reason": "tp", "fill": Fill(min(o, tp) if o < tp else tp, t, i)}
    return None


def pnl(direction: str, entry: float, exit_price: float, qty: float) -> float:
    return (exit_price - entry) * qty if direction == "long" else (entry - exit_price) * qty


def fee(price: float, qty: float, fee_pct: float) -> float:
    return abs(price * qty) * fee_pct / 100.0
