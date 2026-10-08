"""
Setupy formacji harmonicznych i ich wyniki - uczciwy pomiar skuteczności.

Dlaczego nie gotowe formacje z bazy: silnik (pyharmonics) uznaje D za punkt dopiero, gdy jest
szczytem/dołkiem, czyli gdy odwrót już nastąpił - formacja, w której cena przebiła PRZ i poszła
dalej, w ogóle nie zostaje wykryta. Win rate liczony na nich byłby zawyżony z konstrukcji.
(pyharmonics.HarmonicSearch.forming() też się nie nadaje: z limit_to=-1 zwraca "formujące się"
formacje z całej historii okna, nie te znane w danej chwili.)

Tutaj setup = X, A, B, C znane w chwili t (C potwierdzony jako pivot) + strefa D (PRZ) z tych
samych definicji co walidacja ręczna (src/harmonic_validation.py). Dalej tylko świece po t:

    waiting --(cena dotyka PRZ)--> open --(TP1 albo SL, co pierwsze)--> win / loss
       |                             '--(brak rozstrzygnięcia przez 2*L świec)--> expired
       |--(cena przebija C)--> invalidated
       '--(brak wejścia przez L świec)--> no_entry             L = liczba świec od X do C

Pivot w świecy i jest potwierdzony dopiero w świecy i + spacing (ekstremum okna [i-s, i+s]),
więc odtwarzanie historii nie korzysta z przyszłości. Wejście po bliższej krawędzi PRZ (albo po
otwarciu, jeśli świeca otworzyła się za nią). SL/TP z tych samych reguł co na wykresie
(FibonacciTargets) z D = cena wejścia. Wynik: całość zamykana na TP1 (r_multiple), dodatkowo
odnotowane, czy TP2 padł przed SL. TP i SL w tej samej świecy -> SL (wariant konserwatywny).
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from pyharmonics import constants

from .harmonic_validation import POINT_NAMES, Point, ValidationError, validate_xabcd

SPACINGS = (5, 8, 13, 21)
FIB_TOLERANCE = 0.03
MAX_BACK_PIVOTS = 8          # ile pivotów przed C bierzemy pod uwagę jako X/A/B
TRADE_TIMEOUT_FACTOR = 2     # czas na rozstrzygnięcie po wejściu = 2 * L świec
FINAL_STATUSES = {"win", "loss", "expired", "no_entry", "invalidated"}
# Nowy setup daje zdarzenie (alert), gdy jego zmiana statusu zaszła najwyżej tyle świec temu - pierwszy
# przebieg na żywo dla świeżo dodanego assetu nie zasypie skrzynki historią.
EVENT_LOOKBACK_CANDLES = 3

SETUP_PARAMS: Dict[str, Any] = {
    "spacings": list(SPACINGS), "fib_tolerance": FIB_TOLERANCE, "max_back_pivots": MAX_BACK_PIVOTS,
    "trade_timeout_factor": TRADE_TIMEOUT_FACTOR, "entry": "near PRZ edge or open",
    "exit": "all at TP1", "same_candle": "SL first",
    # 2: konfluencje setupów = pełny zestaw z sidebara (+ Fib cluster, wyższe TF), przyczynowe.
    "confluences": "sidebar set, causal", "version": 2,
}


def params_version() -> str:
    return hashlib.sha256(json.dumps(SETUP_PARAMS, sort_keys=True).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float
    is_high: bool
    confirmed_at: int  # pierwsza świeca, w której pivot jest znany


@dataclass
class Setup:
    pattern: str
    is_bullish: bool
    points: Dict[str, Pivot]          # X, A, B, C
    prz_min: float
    prz_max: float
    created_index: int                # świeca, w której setup jest znany (potwierdzenie C)
    spacing: int

    @property
    def key(self) -> Tuple:
        return (self.pattern,) + tuple(self.points[n].index for n in POINT_NAMES[:4])


@dataclass
class Outcome:
    status: str = "waiting"           # waiting | open | win | loss | expired | no_entry | invalidated
    entry_index: Optional[int] = None
    entry_price: Optional[float] = None
    sl: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    targets_source: Optional[str] = None
    exit_index: Optional[int] = None
    r_multiple: Optional[float] = None
    tp2_reached: bool = False
    mfe_r: float = 0.0
    mae_r: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


# ─────────────────────────── pivots ───────────────────────────

def raw_pivots(klines: List[Dict], spacing: int) -> List[Pivot]:
    """Kandydaci na pivot w kolejności potwierdzenia; i jest pivotem, gdy jest PIERWSZYM
    ekstremum okna [i-s, i+s] - znany dopiero w świecy i + s."""
    highs = [float(k["high"]) for k in klines]
    lows = [float(k["low"]) for k in klines]
    out: List[Pivot] = []
    for i in range(spacing, len(klines) - spacing):
        window_h = highs[i - spacing: i + spacing + 1]
        window_l = lows[i - spacing: i + spacing + 1]
        if window_h.index(max(window_h)) == spacing:
            out.append(Pivot(i, highs[i], True, i + spacing))
        if window_l.index(min(window_l)) == spacing:
            out.append(Pivot(i, lows[i], False, i + spacing))
    return sorted(out, key=lambda p: (p.confirmed_at, p.index, not p.is_high))


def _zigzag_push(zigzag: List[Pivot], p: Pivot) -> bool:
    """Dokłada pivot do zygzaka (kolejny tego samego typu zostaje, jeśli bardziej skrajny).
    Zwraca True, gdy p stał się ostatnim punktem zygzaka."""
    if zigzag and zigzag[-1].index == p.index:
        return False  # świeca będąca jednocześnie szczytem i dołkiem - pierwszy wygrywa
    if zigzag and zigzag[-1].is_high == p.is_high:
        last = zigzag[-1]
        if (p.price > last.price) if p.is_high else (p.price < last.price):
            zigzag[-1] = p
            return True
        return False
    zigzag.append(p)
    return True


def confirmed_pivots(klines: List[Dict], spacing: int) -> List[Pivot]:
    """Końcowy zygzak (naprzemienne szczyty/dołki) ze wszystkich świec."""
    zigzag: List[Pivot] = []
    for p in raw_pivots(klines, spacing):
        _zigzag_push(zigzag, p)
    return zigzag


# ─────────────────────────── setups ───────────────────────────

def _abc_ok(pattern: str, ratios: Dict[str, float], tolerance: float) -> bool:
    definition = constants.HARMONIC_PATTERNS[constants.XABCD].get(pattern, {})
    for key in ("ABC", "XAC"):
        if key in definition:
            lo = definition[key][constants.MIN] * (1 - tolerance)
            hi = definition[key][constants.MAX] * (1 + tolerance)
            if not lo <= ratios[key] <= hi:
                return False
    return True


def generate_setups(klines: List[Dict], spacing: int, tolerance: float = FIB_TOLERANCE,
                    max_back: int = MAX_BACK_PIVOTS) -> List[Setup]:
    """Setupy w kolejności ich powstania. Zygzak budowany przyrostowo - w chwili potwierdzenia C
    widać tylko pivoty potwierdzone do tej chwili. Końcowy zygzak z całej historii może później
    zastąpić pivot bardziej skrajnym, a setup, który na żywo by powstał, w odtworzeniu by zniknął."""
    zigzag: List[Pivot] = []
    setups: List[Setup] = []
    for c in raw_pivots(klines, spacing):
        if not _zigzag_push(zigzag, c) or len(zigzag) < 4:
            continue
        earlier = zigzag[max(0, len(zigzag) - 1 - max_back): -1]
        setups.extend(_setups_for_c(c, earlier, spacing, tolerance))
    return setups


def _setups_for_c(c: Pivot, earlier: List[Pivot], spacing: int, tolerance: float) -> List[Setup]:
    found: List[Setup] = []
    for xi, x in enumerate(earlier):
        if x.is_high == c.is_high:
            continue
        for ai in range(xi + 1, len(earlier)):
            a = earlier[ai]
            if a.is_high != c.is_high:
                continue
            for bi in range(ai + 1, len(earlier)):
                b = earlier[bi]
                if b.is_high != x.is_high:
                    continue
                pts = {"X": x, "A": a, "B": b, "C": c}
                try:
                    result = validate_xabcd(
                        {n: Point(time=p.index, price=p.price) for n, p in pts.items()},
                        fib_tolerance=tolerance,
                    )
                except ValidationError:
                    continue
                ratios = result["ratios"]
                bullish = result["direction"] == "bullish"
                for match in result["matches"]:
                    prz = match["prz"]
                    if not prz or prz["min"] <= 0 or not _abc_ok(match["pattern"], ratios, tolerance):
                        continue
                    # D musi leżeć za C w kierunku ruchu CD.
                    if (bullish and prz["max"] >= c.price) or (not bullish and prz["min"] <= c.price):
                        continue
                    found.append(Setup(match["pattern"], bullish, pts, prz["min"], prz["max"],
                                       c.confirmed_at, spacing))
    return found


def generate_all_setups(klines: List[Dict], spacings: Iterable[int] = SPACINGS) -> List[Setup]:
    """Setupy ze wszystkich spacingów, bez duplikatów (te same punkty X..C i typ)."""
    by_key: Dict[Tuple, Setup] = {}
    for s in spacings:
        for setup in generate_setups(klines, s):
            prev = by_key.get(setup.key)
            if prev is None or setup.created_index < prev.created_index:
                by_key[setup.key] = setup
    return sorted(by_key.values(), key=lambda s: (s.created_index, s.key))


# ─────────────────────────── outcome ───────────────────────────

TargetsFn = Callable[[Setup, float], Tuple[Optional[float], Optional[float], Optional[float], str]]


def fallback_targets(setup: Setup, entry: float) -> Tuple[float, float, float, str]:
    """TP = zniesienia 38.2/61.8% ramienia AD, SL = za X (albo za dalszą krawędzią PRZ)."""
    a, x = setup.points["A"].price, setup.points["X"].price
    sign = 1 if setup.is_bullish else -1
    leg = abs(a - entry)
    tp1, tp2 = entry + sign * 0.382 * leg, entry + sign * 0.618 * leg
    far_edge = setup.prz_min if setup.is_bullish else setup.prz_max
    candidates = [p for p in (x, far_edge) if (p < entry if setup.is_bullish else p > entry)]
    if candidates:
        sl = min(candidates) if setup.is_bullish else max(candidates)
    else:
        sl = entry - 0.5 * (tp1 - entry)  # pół drogi do TP1 po drugiej stronie wejścia
    return sl, tp1, tp2, "fallback"


def _targets_valid(bullish: bool, entry: float, sl, tp1, tp2) -> bool:
    if sl is None or tp1 is None:
        return False
    if bullish:
        return sl < entry < tp1 and (tp2 is None or tp2 >= tp1)
    return sl > entry > tp1 and (tp2 is None or tp2 <= tp1)


def simulate(setup: Setup, klines: List[Dict], targets_fn: Optional[TargetsFn] = None) -> Outcome:
    """Przebieg setupu na świecach po setup.created_index (tylko to, co dostępne w klines)."""
    out = Outcome()
    bull = setup.is_bullish
    c_price = setup.points["C"].price
    span = max(1, setup.points["C"].index - setup.points["X"].index)
    entry_deadline = setup.created_index + span
    near_edge = setup.prz_max if bull else setup.prz_min

    i = setup.created_index + 1
    while i < len(klines):
        k = klines[i]
        hi, lo, op = float(k["high"]), float(k["low"]), float(k["open"])
        if out.status == "waiting":
            if (bull and hi > c_price) or (not bull and lo < c_price):
                out.status, out.exit_index = "invalidated", i
                return out
            touched = lo <= near_edge if bull else hi >= near_edge
            if touched:
                entry = min(op, near_edge) if bull else max(op, near_edge)
                sl, tp1, tp2, source = (targets_fn or fallback_targets)(setup, entry)
                if not _targets_valid(bull, entry, sl, tp1, tp2):
                    sl, tp1, tp2, source = fallback_targets(setup, entry)
                out.status, out.entry_index, out.entry_price = "open", i, entry
                out.sl, out.tp1, out.tp2, out.targets_source = sl, tp1, tp2, source
                # SL już w świecy wejścia (konserwatywnie: SL przed TP)
                if (bull and lo <= sl) or (not bull and hi >= sl):
                    _close(out, "loss", i, -1.0)
                    out.mae_r = 1.0
                    return out
            elif i > entry_deadline:
                out.status, out.exit_index = "no_entry", i
                return out
        else:
            risk = abs(out.entry_price - out.sl)
            favorable = (hi - out.entry_price) if bull else (out.entry_price - lo)
            adverse = (out.entry_price - lo) if bull else (hi - out.entry_price)
            out.mfe_r = max(out.mfe_r, favorable / risk)
            out.mae_r = max(out.mae_r, adverse / risk)
            sl_hit = lo <= out.sl if bull else hi >= out.sl
            tp1_hit = hi >= out.tp1 if bull else lo <= out.tp1
            if out.tp2 is not None and not sl_hit and (hi >= out.tp2 if bull else lo <= out.tp2):
                out.tp2_reached = True
            if sl_hit:
                _close(out, "loss", i, -1.0)
                return out
            if tp1_hit:
                _close(out, "win", i, abs(out.tp1 - out.entry_price) / risk)
                # Czy TP2 padł później, zanim padłby SL? (informacyjnie, wynik zostaje na TP1)
                out.tp2_reached = out.tp2_reached or _tp2_before_sl(out, klines, i, bull)
                return out
            if i - out.entry_index >= TRADE_TIMEOUT_FACTOR * span:
                close = float(k["close"])
                _close(out, "expired", i, ((close - out.entry_price) if bull else (out.entry_price - close)) / risk)
                return out
        i += 1
    return out  # waiting / open - za mało świec, dokończy następny przebieg


def _close(out: Outcome, status: str, index: int, r: float) -> None:
    out.status, out.exit_index, out.r_multiple = status, index, round(r, 4)


def _tp2_before_sl(out: Outcome, klines: List[Dict], start: int, bull: bool) -> bool:
    if out.tp2 is None:
        return False
    for k in klines[start:]:
        hi, lo = float(k["high"]), float(k["low"])
        if (bull and lo <= out.sl) or (not bull and hi >= out.sl):
            return False
        if (bull and hi >= out.tp2) or (not bull and lo <= out.tp2):
            return True
    return False


# ─────────────────────────── app targets ───────────────────────────

def app_targets(setup: Setup, entry: float):
    """SL/TP z tych samych reguł co na wykresie (FibonacciTargets) z D = cena wejścia."""
    from .technical_analysis.technical_analysis_objects.tao_fibonacci_all_harmonic_pattern_points_levels import (
        FibonacciAllHarmonicPatternPointsLevels,
    )
    from .technical_analysis.technical_analysis_objects.tao_fibonacci_targets import FibonacciTargets

    pp = {n: {"index": p.index, "price": p.price} for n, p in setup.points.items()}
    pp["D"] = {"index": setup.points["C"].index + 1, "price": entry}
    levels = FibonacciAllHarmonicPatternPointsLevels()
    levels.calculate([], pattern_points=pp)
    targets = FibonacciTargets()
    targets.calculate([], pattern_points=pp, pattern_type=setup.pattern, all_fibos=levels.calculated_data,
                      is_bullish=setup.is_bullish)
    t = targets.calculated_data or {}
    price = lambda name: (t.get(name) or {}).get("price")
    return price("SL"), price("TP1"), price("TP2"), "app"


# ─────────────────────────── persistence ───────────────────────────

def setup_key_times(setup: Setup, klines: List[Dict]) -> Tuple:
    return (setup.pattern,) + tuple(int(klines[setup.points[n].index]["open_time"]) for n in POINT_NAMES[:4])


def to_row(setup: Setup, outcome: Outcome, klines: List[Dict], asset_id: int, interval: str,
           source: str, confluences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Wiersz technical_analysis_harmonic_setups - indeksy świec zamienione na open_time (ms)."""
    t = lambda i: None if i is None else int(klines[i]["open_time"])
    _, x_t, a_t, b_t, c_t = setup_key_times(setup, klines)
    return {
        "asset_id": asset_id, "interval": interval, "params_version": params_version(),
        "pattern_type": setup.pattern, "is_bullish": setup.is_bullish, "spacing": setup.spacing,
        "x_time": x_t, "a_time": a_t, "b_time": b_t, "c_time": c_t,
        "points_json": {n: {"time": t(p.index), "price": p.price} for n, p in setup.points.items()},
        "prz_min": setup.prz_min, "prz_max": setup.prz_max, "created_time": t(setup.created_index),
        "status": outcome.status, "entry_time": t(outcome.entry_index), "entry_price": outcome.entry_price,
        "sl": outcome.sl, "tp1": outcome.tp1, "tp2": outcome.tp2, "targets_source": outcome.targets_source,
        "exit_time": t(outcome.exit_index), "r_multiple": outcome.r_multiple, "tp2_reached": outcome.tp2_reached,
        "mfe_r": round(outcome.mfe_r, 4) if outcome.entry_index is not None else None,
        "mae_r": round(outcome.mae_r, 4) if outcome.entry_index is not None else None,
        "confluences_json": confluences, "source": source,
    }


def wilson_interval(wins: int, n: int, z: float = 1.96) -> Tuple[Optional[float], Optional[float]]:
    """95% przedział ufności dla win rate - przy małych próbkach mówi, ile jest wart wynik."""
    if n <= 0:
        return None, None
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return round(max(0.0, center - half), 4), round(min(1.0, center + half), 4)


ConfluencesFn = Callable[[Setup, Outcome, List[Dict]], Optional[Dict[str, Any]]]


def evaluate(klines: List[Dict], asset_id: int, interval: str, source: str,
             skip_keys: Iterable[Tuple] = (), targets_fn: Optional[TargetsFn] = None,
             confluences_fn: Optional[ConfluencesFn] = None,
             spacings: Iterable[int] = SPACINGS) -> List[Dict[str, Any]]:
    """Setupy z klines (tylko zamknięte świece!) i ich wyniki jako wiersze tabeli.

    skip_keys: klucze (pattern, x_time, a_time, b_time, c_time) już rozstrzygnięte w bazie.
    confluences_fn dostaje świece do świecy wejścia włącznie - konfluencje znane w chwili wejścia.
    """
    skip = set(skip_keys)
    rows = []
    for setup in generate_all_setups(klines, spacings):
        if setup_key_times(setup, klines) in skip:
            continue
        outcome = simulate(setup, klines, targets_fn)
        confluences = None
        if confluences_fn is not None and outcome.entry_index is not None:
            confluences = confluences_fn(setup, outcome, klines[: outcome.entry_index + 1])
        rows.append(to_row(setup, outcome, klines, asset_id, interval, source, confluences))
    return rows


def stats_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Agregat z TechnicalAnalysisHarmonicSetupsTable.stats + win rate i przedział Wilsona."""
    out = dict(row)
    decided = int(row.get("wins") or 0) + int(row.get("losses") or 0) + int(row.get("expired") or 0)
    wins = int(row.get("wins") or 0)
    out["trades"] = decided
    out["win_rate"] = round(wins / decided, 4) if decided else None
    out["win_rate_ci95"] = list(wilson_interval(wins, decided))
    out["tp2_rate"] = round(int(row.get("tp2_reached") or 0) / decided, 4) if decided else None
    # Odsetek setupów, w których doszło do wejścia (z rozstrzygniętych przed/po wejściu).
    skipped = int(row.get("no_entry") or 0) + int(row.get("invalidated") or 0)
    out["entry_rate"] = round(decided / (decided + skipped), 4) if decided + skipped else None
    for c in ("avg_r", "avg_mfe_r", "avg_mae_r"):
        if out.get(c) is not None:
            out[c] = round(float(out[c]), 4)
    return out


def _event_time(row: Dict[str, Any]) -> int:
    if row["status"] in FINAL_STATUSES and row.get("exit_time") is not None:
        return row["exit_time"]
    if row["status"] == "open" and row.get("entry_time") is not None:
        return row["entry_time"]
    return row["created_time"]


def status_events(rows: List[Dict[str, Any]], previous: Dict[Tuple, str], symbol: str,
                  new_since: int) -> List[Dict[str, Any]]:
    """Zdarzenia z jednego przebiegu na żywo.

    previous: statusy nierozstrzygniętych setupów sprzed przebiegu (klucz pattern, x, a, b, c).
    - setup znany i status się zmienił -> zdarzenie zawsze (np. waiting -> open, open -> win);
    - setup nowy -> zdarzenie tylko, gdy jego ostatnia zmiana zaszła od `new_since` (ms), inaczej
      to historia doliczona przy pierwszym przebiegu.
    """
    events = []
    for r in rows:
        key = (r["pattern_type"], r["x_time"], r["a_time"], r["b_time"], r["c_time"])
        before = previous.get(key)
        when = _event_time(r)
        if before == r["status"]:
            continue
        if before is None and when < new_since:
            continue
        events.append({
            "asset_id": r["asset_id"], "interval": r["interval"], "params_version": r["params_version"],
            "pattern_type": r["pattern_type"], "is_bullish": r["is_bullish"],
            "x_time": r["x_time"], "c_time": r["c_time"],
            "from_status": before, "to_status": r["status"], "event_time": when,
            "payload": {
                "symbol": symbol, "points": r["points_json"], "prz": [r["prz_min"], r["prz_max"]],
                "created_time": r["created_time"], "entry_time": r["entry_time"],
                "entry_price": r["entry_price"], "sl": r["sl"], "tp1": r["tp1"], "tp2": r["tp2"],
                "exit_time": r["exit_time"], "r_multiple": r["r_multiple"],
                "targets_source": r["targets_source"],
            },
        })
    return events
