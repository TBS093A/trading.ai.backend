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
