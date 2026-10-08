"""Wspólne pomocnicze dla detektorów konfluencji."""

from typing import Dict, List, Optional

POINT_NAMES = ("X", "A", "B", "C", "D")


def d_point_price(klines: List[Dict], d_index: int, is_bullish: bool,
                  pattern_points: Optional[Dict] = None) -> float:
    """Cena punktu D formacji.

    Punkt D to ekstremum (dołek dla formacji bullish, szczyt dla bearish), a nie zamknięcie
    świecy - detektory porównywały wcześniej close świecy D z poziomami i z cenami punktów
    X/B (też ekstremami), co przesuwało D o cały korpus/knot świecy. Pierwszeństwo ma cena z
    pattern_points (ta sama, którą wyznaczył silnik), a bez niej - low/high świecy D.
    """
    if pattern_points and "D" in pattern_points and pattern_points["D"].get("price") is not None:
        return float(pattern_points["D"]["price"])
    kline = klines[d_index]
    return float(kline["low"] if is_bullish else kline["high"])


def pattern_point_indices(pattern_points: Optional[Dict], before: int) -> set:
    """Indeksy świec punktów X..C formacji (przed D) - do wykluczenia z jej własnego tła."""
    if not pattern_points:
        return set()
    return {
        int(p["index"]) for name, p in pattern_points.items()
        if name in POINT_NAMES and name != "D" and p.get("index") is not None and int(p["index"]) < before
    }


# ─────────── przyczynowość post-processingu (konfluencje z innych formacji / wyższych TF) ───────────
# Konfluencja w punkcie D może korzystać tylko z tego, co było znane w chwili D - inaczej formacje
# historyczne dostają "potwierdzenia" z przyszłości, a model siły uczyłby się z wyniku.

def pattern_is_bullish(pattern: Dict) -> bool:
    ta = pattern.get('ta_object_json') or {}
    return bool(ta.get('is_bullish', ta.get('bullish', True)))


def pattern_end_timestamp(pattern: Dict) -> Optional[int]:
    """Ostatni punkt formacji (D, a dla ABC - C), ms."""
    for key in ('d_point_timestamp', 'c_point_timestamp'):
        value = pattern.get(key)
        if value:
            return int(value)
    return None


def patterns_known_before(patterns: List[Dict], timestamp: Optional[int], interval_ms: int = 0) -> List[Dict]:
    """Formacje zakończone przed `timestamp` (dla wyższego TF: ze świecą końca już zamkniętą)."""
    if timestamp is None:
        return list(patterns)
    out = []
    for p in patterns:
        end = pattern_end_timestamp(p)
        if end is not None and end + interval_ms <= timestamp and end < timestamp:
            out.append(p)
    return out


def klines_closed_before(klines: List[Dict], interval: str, timestamp: Optional[int]) -> List[Dict]:
    """Świece interwału `interval` zamknięte najpóźniej w chwili `timestamp` (ms)."""
    if timestamp is None:
        return klines
    from ...harmonic_scan import INTERVAL_MS

    step = INTERVAL_MS.get(interval, 0)
    return [k for k in klines if int(k.get('open_time', 0)) + step <= timestamp]
