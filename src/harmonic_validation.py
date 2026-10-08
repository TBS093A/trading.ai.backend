"""
Ręczna walidacja formacji harmonicznej: użytkownik zaznacza na wykresie punkty X, A, B, C
(i opcjonalnie D), backend liczy proporcje ramion i sprawdza je względem definicji formacji.

Definicje i tolerancja pochodzą z tego samego miejsca co automatyczne wyszukiwanie
(pyharmonics.utils.get_pattern_definition(fib_tolerance, MATRIX_PATTERNS)), więc ręczna
walidacja daje ten sam werdykt co HarmonicSearch dla tych samych punktów.

Proporcje (|..| = różnica cen):
    XAB = |A-B| / |X-A|     (B jako zniesienie XA)
    ABC = |B-C| / |A-B|
    BCD = |C-D| / |B-C|     (D jako rozszerzenie BC)
    XAD = |A-D| / |X-A|     (D względem XA; Cypher liczy D względem XC: |C-D| / |X-C|)
Bez D zwracane są strefy, w których D musiałoby wypaść dla każdej formacji pasującej do X, A, B, C.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from pyharmonics import constants, utils

POINT_NAMES = ("X", "A", "B", "C", "D")
DEFAULT_FIB_TOLERANCE = 0.03
# Formacje, których ostatnie ramię liczy się od C (pyharmonics: peak_idx == C_idx), nie od A.
D_FROM_C = {"cypher"}
TARGET_RETRACES = (0.382, 0.618)


class ValidationError(ValueError):
    """Nieprawidłowe punkty - komunikat nadaje się do odpowiedzi 422."""


@dataclass(frozen=True)
class Point:
    time: int
    price: float


@lru_cache(maxsize=16)
def _definitions(fib_tolerance: float) -> Dict[str, Dict[str, Dict[str, float]]]:
    # Cache: generator setupów (src/harmonic_setups.py) woła walidację dziesiątki tysięcy razy.
    return utils.get_pattern_definition(fib_tolerance, constants.MATRIX_PATTERNS)


def _ordered_points(points: Dict[str, Point]) -> List[Tuple[str, Point]]:
    names = [n for n in POINT_NAMES if n in points]
    if names not in (list(POINT_NAMES), list(POINT_NAMES[:4])):
        raise ValidationError("wymagane punkty X, A, B, C (i opcjonalnie D)")
    ordered = [(n, points[n]) for n in names]
    for (n1, p1), (n2, p2) in zip(ordered, ordered[1:]):
        if p2.time <= p1.time:
            raise ValidationError(f"punkt {n2} musi być później niż {n1}")
    for name, p in ordered:
        if not p.price > 0:
            raise ValidationError(f"cena punktu {name} musi być dodatnia")
    # Formacja to zygzak: kolejne punkty na przemian dołek / szczyt.
    for (n1, p1), (n2, p2), (n3, p3) in zip(ordered, ordered[1:], ordered[2:]):
        if (p2.price - p1.price) * (p3.price - p2.price) >= 0:
            raise ValidationError(f"punkty {n1}-{n2}-{n3} nie tworzą zygzaka (na przemian dołek i szczyt)")
    return ordered


def _ratio(a: float, b: float, c: float, d: float) -> float:
    """|c-d| / |a-b|"""
    return abs(c - d) / abs(a - b)


def compute_ratios(points: Dict[str, Point]) -> Dict[str, float]:
    p = {n: pt.price for n, pt in points.items()}
    ratios = {
        "XAB": _ratio(p["X"], p["A"], p["A"], p["B"]),
        "ABC": _ratio(p["A"], p["B"], p["B"], p["C"]),
        "XAC": _ratio(p["X"], p["A"], p["X"], p["C"]),
    }
    if "D" in p:
        ratios["BCD"] = _ratio(p["B"], p["C"], p["C"], p["D"])
        ratios["XAD"] = _ratio(p["X"], p["A"], p["A"], p["D"])
        ratios["XCD"] = _ratio(p["X"], p["C"], p["C"], p["D"])
    return {k: round(v, 4) for k, v in ratios.items()}


def _check(value: float, bounds: Dict[str, float]) -> Dict[str, object]:
    lo, hi = bounds[constants.MIN], bounds[constants.MAX]
    return {"value": value, "min": round(lo, 4), "max": round(hi, 4), "ok": lo <= value <= hi}


def _d_zone(points: Dict[str, Point], pattern: str, defs, bullish: bool) -> Optional[Dict[str, float]]:
    """Cena D wynikająca z ostatniego ramienia (XAD albo XCD) i z BCD - część wspólna to PRZ."""
    p = {n: pt.price for n, pt in points.items()}
    direction = -1 if bullish else 1  # bullish: D poniżej A (i C), bearish: powyżej
    zones = []
    if pattern in defs[constants.XABCD]:
        b = defs[constants.XABCD][pattern]
        anchor, leg = (p["C"], abs(p["X"] - p["C"])) if pattern in D_FROM_C else (p["A"], abs(p["X"] - p["A"]))
        zones.append(sorted((anchor + direction * b[constants.MIN] * leg, anchor + direction * b[constants.MAX] * leg)))
    if pattern in defs[constants.BCD]:
        b = defs[constants.BCD][pattern]
        leg = abs(p["B"] - p["C"])
        zones.append(sorted((p["C"] + direction * b[constants.MIN] * leg, p["C"] + direction * b[constants.MAX] * leg)))
    if not zones:
        return None
    lo, hi = max(z[0] for z in zones), min(z[1] for z in zones)
    if lo > hi:
        # Ramiona się nie przecinają - zwróć strefę z XAD/XCD (najważniejszą), oznaczoną jako rozłączną.
        return {"min": round(zones[0][0], 8), "max": round(zones[0][1], 8), "overlapping": False}
    return {"min": round(lo, 8), "max": round(hi, 8), "overlapping": True}


def _targets(points: Dict[str, Point], bullish: bool) -> Dict[str, float]:
    """Cele po D: zniesienia ramienia AD (0.382 / 0.618)."""
    a, d = points["A"].price, points["D"].price
    direction = 1 if bullish else -1
    return {f"T{i + 1}_{r}": round(d + direction * r * abs(a - d), 8) for i, r in enumerate(TARGET_RETRACES)}


def validate_xabcd(points: Dict[str, Point], fib_tolerance: float = DEFAULT_FIB_TOLERANCE) -> Dict[str, object]:
    if not 0 <= fib_tolerance <= 0.2:
        raise ValidationError("fib_tolerance musi być w zakresie 0..0.2")
    ordered = _ordered_points(points)
    points = dict(ordered)
    bullish = points["A"].price > points["X"].price  # X dołek, A szczyt -> D dołek (kupno)
    ratios = compute_ratios(points)
    defs = _definitions(fib_tolerance)
    has_d = "D" in points

    results = []
    for pattern in sorted(defs[constants.XAB]):
        checks = {"XAB": _check(ratios["XAB"], defs[constants.XAB][pattern])}
        if has_d:
            if pattern in defs[constants.BCD]:
                checks["BCD"] = _check(ratios["BCD"], defs[constants.BCD][pattern])
            if pattern in defs[constants.XABCD]:
                key = "XCD" if pattern in D_FROM_C else "XAD"
                checks[key] = _check(ratios[key], defs[constants.XABCD][pattern])
        entry = {
            "pattern": pattern,
            "match": all(c["ok"] for c in checks.values()),
            "checks": checks,
            "prz": _d_zone(points, pattern, defs, bullish),
        }
        if has_d and entry["match"]:
            entry["targets"] = _targets(points, bullish)
        results.append(entry)

    def distance(entry):
        # Suma względnych odchyleń poza zakresy - 0 dla pełnego dopasowania.
        total = 0.0
        for c in entry["checks"].values():
            if c["value"] < c["min"]:
                total += (c["min"] - c["value"]) / c["min"]
            elif c["value"] > c["max"]:
                total += (c["value"] - c["max"]) / c["max"]
        return total

    results.sort(key=lambda e: (not e["match"], distance(e), e["pattern"]))
    for e in results:
        e["deviation"] = round(distance(e), 4)

    return {
        "direction": "bullish" if bullish else "bearish",
        "complete": has_d,
        "fib_tolerance": fib_tolerance,
        "ratios": ratios,
        # Bez D "match" znaczy tylko, że X, A, B pasują do formacji - D trzeba szukać w "prz".
        "matches": [e for e in results if e["match"]],
        "candidates": results,
    }
