"""
Warianty wejścia i zarządzania pozycją dla setupów XABCD - porównanie na tej samej historii.

Każdy wariant przechodzi te same setupy (src/harmonic_setups.py: X..C + PRZ znane w chwili t) i różni
się tylko tym, kiedy wchodzi i jak prowadzi pozycję:

- entry="touch"    - wejście przy dotknięciu bliższej krawędzi PRZ (jak seria produkcyjna);
- entry="confirm"  - po dotknięciu czekamy (najwyżej confirm_window świec) na świecę odwrócenia:
                     bullish = świeca wzrostowa zamknięta powyżej dolnej krawędzi PRZ (bearish lustrzanie);
                     wejście po jej zamknięciu, SL za ekstremum od dotknięcia (albo dalej - wg reguł z wykresu);
- breakeven_at     - po zysku >= k*R SL przesuwany na cenę wejścia (od następnej świecy);
- rr_cap           - TP1 nie dalej niż cap*R od wejścia;
- min_strength     - tylko setupy z siłą (model "entry", percentyl) >= progu w chwili wejścia;
- min_ev           - tylko setupy z wartością oczekiwaną p_win*R:R - (1-p_win) >= progu.

Konserwatywnie jak w serii produkcyjnej: SL i TP w tej samej świecy -> SL; limit czasu 2 x rozpiętość X..C.
Siła liczona przyczynowo: przy dotknięciu PRZ model wstępny na konfluencjach poziomowych do świecy przed
dotknięciem (świeca wejścia nie jest jeszcze zamknięta), po potwierdzeniu model pełny na zamkniętej świecy
potwierdzenia. Oba modele uczone tylko na danych sprzed cutoff - wyniki "out" (po cutoff) są uczciwe,
"in" dla wariantów z siłą są optymistyczne.
"""

import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .harmonic_setups import TRADE_TIMEOUT_FACTOR, Setup, TargetsFn, _targets_valid, fallback_targets, wilson_interval


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    entry: str = "touch"
    confirm_window: int = 3
    breakeven_at: Optional[float] = None
    rr_cap: Optional[float] = None
    min_strength: Optional[int] = None
    min_ev: Optional[float] = None
    trend: Optional[str] = None      # "with" - tylko z trendem wyższego TF, "not_against" - nie przeciw niemu

    @property
    def needs_strength(self) -> bool:
        return self.min_strength is not None or self.min_ev is not None or self.trend is not None

    @property
    def strength_kind(self) -> str:
        """Przy dotknięciu wejście jest w trakcie świecy - znamy tylko konfluencje poziomowe sprzed niej
        (model "pre"); po potwierdzeniu świeca jest zamknięta - pełny model "entry" jest uczciwy."""
        return "entry" if self.entry == "confirm" else "pre"


VARIANTS: Tuple[Variant, ...] = (
    Variant("baseline", "dotknięcie PRZ, całość na TP1 (jak dziś)"),
    Variant("be_1r", "jak baseline + SL na wejście po +1R", breakeven_at=1.0),
    Variant("rr_cap_2", "jak baseline, TP1 najwyżej 2R", rr_cap=2.0),
    Variant("rr_cap_1_5", "jak baseline, TP1 najwyżej 1.5R", rr_cap=1.5),
    Variant("confirm", "wejście po świecy odwrócenia w PRZ", entry="confirm"),
    Variant("confirm_be", "potwierdzenie + SL na wejście po +1R", entry="confirm", breakeven_at=1.0),
    Variant("confirm_cap_2", "potwierdzenie + TP1 najwyżej 2R", entry="confirm", rr_cap=2.0),
    # Wejście przy dotknięciu: siła WSTĘPNA (model "pre", konfluencje poziomowe do świecy przed
    # dotknięciem) - to samo, co widzi konto paper w chwili wystawienia zlecenia.
    Variant("pre_strength_60", "dotknięcie, siła wstępna >= 60 (jak konto paper)", min_strength=60),
    Variant("pre_strength_70", "dotknięcie, siła wstępna >= 70", min_strength=70),
    Variant("pre_strength_80", "dotknięcie, siła wstępna >= 80", min_strength=80),
    Variant("pre_ev_positive", "dotknięcie, EV wstępne >= 0", min_ev=0.0),
    # Wejście po potwierdzeniu: siła PEŁNA na zamkniętej świecy potwierdzenia - uczciwa.
    Variant("confirm_strength_60", "potwierdzenie + siła >= 60", entry="confirm", min_strength=60),
    Variant("confirm_strength_70", "potwierdzenie + siła >= 70", entry="confirm", min_strength=70),
    Variant("confirm_strength_80", "potwierdzenie + siła >= 80", entry="confirm", min_strength=80),
    Variant("confirm_ev_be", "potwierdzenie + EV >= 0 + SL na wejście po +1R", entry="confirm", min_ev=0.0,
            breakeven_at=1.0),
    # Filtr trendu z wyższego TF (EMA 200, utils/harmonic_patterns/trend_confluences.py)
    Variant("baseline_trend", "dotknięcie, tylko z trendem wyższego TF", trend="with"),
    Variant("baseline_not_against", "dotknięcie, nie przeciw trendowi wyższego TF", trend="not_against"),
    Variant("pre_strength_70_trend", "dotknięcie, siła wstępna >= 70, z trendem", min_strength=70, trend="with"),
    Variant("confirm_trend", "potwierdzenie, tylko z trendem", entry="confirm", trend="with"),
    Variant("confirm_strength_80_trend", "potwierdzenie + siła >= 80, z trendem", entry="confirm", min_strength=80,
            trend="with"),
    Variant("confirm_strength_70_not_against", "potwierdzenie + siła >= 70, nie przeciw trendowi", entry="confirm",
            min_strength=70, trend="not_against"),
)
VARIANTS_BY_NAME = {v.name: v for v in VARIANTS}

SL_BUFFER = 0.001   # SL wariantu "confirm": 0.1% za ekstremum od dotknięcia

# score_fn(setup, entry_index, entry, sl, tp1, kind) -> {"score": 0-100, "p_win": 0-1} albo None;
# kind = Variant.strength_kind ("pre" przy dotknięciu, "entry" po potwierdzeniu)
ScoreFn = Callable[[Setup, int, float, float, float, str], Optional[Dict[str, Any]]]


@dataclass
class Trade:
    variant: str
    entry_index: int
    exit_index: int
    entry_price: float
    sl: float
    tp1: float
    status: str             # win | loss | be | expired
    r: float
    strength: Optional[int] = None
    p_win: Optional[float] = None
    ev: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _touch(setup: Setup, klines: List[Dict]) -> Optional[int]:
    """Pierwsza świeca dotykająca bliższej krawędzi PRZ (albo None: C przebite / minął czas / brak danych)."""
    bull = setup.is_bullish
    c_price = setup.points["C"].price
    span = max(1, setup.points["C"].index - setup.points["X"].index)
    near = setup.prz_max if bull else setup.prz_min
    for i in range(setup.created_index + 1, len(klines)):
        hi, lo = float(klines[i]["high"]), float(klines[i]["low"])
        if (bull and hi > c_price) or (not bull and lo < c_price):
            return None
        if (lo <= near) if bull else (hi >= near):
            return i
        if i > setup.created_index + span:
            return None
    return None


def _confirmation(setup: Setup, klines: List[Dict], touch: int, window: int) -> Optional[Tuple[int, float]]:
    """(indeks świecy potwierdzenia, ekstremum od dotknięcia) albo None."""
    bull = setup.is_bullish
    far = setup.prz_min if bull else setup.prz_max
    x_price = setup.points["X"].price
    extreme = None
    for j in range(touch, min(len(klines), touch + window)):
        k = klines[j]
        o, h, l, c = (float(k[f]) for f in ("open", "high", "low", "close"))
        extreme = (l if extreme is None else min(extreme, l)) if bull else (h if extreme is None else max(extreme, h))
        if (bull and c < x_price) or (not bull and c > x_price):
            return None   # zamknięcie za X - formacja zniszczona
        if (bull and c > o and c >= far) or (not bull and c < o and c <= far):
            return j, extreme
    return None


def simulate_variant(setup: Setup, klines: List[Dict], variant: Variant, targets_fn: Optional[TargetsFn] = None,
                     score_fn: Optional[ScoreFn] = None) -> Optional[Trade]:
    """Transakcja wariantu dla setupu albo None (brak wejścia, odfiltrowany, za mało danych)."""
    bull = setup.is_bullish
    sign = 1 if bull else -1
    span = max(1, setup.points["C"].index - setup.points["X"].index)
    touch = _touch(setup, klines)
    if touch is None:
        return None

    if variant.entry == "confirm":
        confirmed = _confirmation(setup, klines, touch, variant.confirm_window)
        if confirmed is None:
            return None
        e_idx, extreme = confirmed
        entry = float(klines[e_idx]["close"])
        start = e_idx + 1                      # wejście na zamknięciu - prowadzenie od następnej świecy
        sl, tp1, _tp2, _src = (targets_fn or fallback_targets)(setup, entry)
        structural = extreme * (1 - SL_BUFFER) if bull else extreme * (1 + SL_BUFFER)
        sl = structural if sl is None else (min(sl, structural) if bull else max(sl, structural))
        if not _targets_valid(bull, entry, sl, tp1, None):
            sl, tp1, _tp2, _src = fallback_targets(setup, entry)
            sl = min(sl, structural) if bull else max(sl, structural)
    else:
        e_idx = touch
        near = setup.prz_max if bull else setup.prz_min
        op = float(klines[touch]["open"])
        entry = min(op, near) if bull else max(op, near)
        start = e_idx                          # SL możliwy już w świecy wejścia (jak seria produkcyjna)
        sl, tp1, _tp2, _src = (targets_fn or fallback_targets)(setup, entry)
        if not _targets_valid(bull, entry, sl, tp1, None):
            sl, tp1, _tp2, _src = fallback_targets(setup, entry)

    risk = abs(entry - sl)
    if risk <= 0 or not _targets_valid(bull, entry, sl, tp1, None):
        return None
    if variant.rr_cap is not None and abs(tp1 - entry) > variant.rr_cap * risk:
        tp1 = entry + sign * variant.rr_cap * risk

    strength = p_win = ev = None
    if variant.needs_strength or score_fn is not None:
        scored = score_fn(setup, e_idx, entry, sl, tp1, variant.strength_kind) if score_fn else None
        if scored is not None and scored.get("score") is not None:
            strength, p_win = int(scored["score"]), float(scored["p_win"])
            ev = round(p_win * abs(tp1 - entry) / risk - (1 - p_win), 4)
        if variant.trend is not None:
            trend = (scored or {}).get("trend")
            if (variant.trend == "with" and trend != "with") or (variant.trend == "not_against" and trend == "against"):
                return None
        if variant.min_strength is not None and (strength is None or strength < variant.min_strength):
            return None
        if variant.min_ev is not None and (ev is None or ev < variant.min_ev):
            return None

    sl_cur, be_done = sl, False
    for i in range(start, len(klines)):
        k = klines[i]
        hi, lo = float(k["high"]), float(k["low"])
        if (lo <= sl_cur) if bull else (hi >= sl_cur):
            r = sign * (sl_cur - entry) / risk
            return Trade(variant.name, e_idx, i, entry, sl, tp1, "be" if be_done else "loss", round(r, 4),
                         strength, p_win, ev)
        if i == e_idx:
            # Świeca wejścia przy dotknięciu: jej maksimum (bullish) mogło być przed zejściem do PRZ -
            # liczy się tylko SL (jak w serii produkcyjnej), TP i break-even od następnej świecy.
            continue
        if (hi >= tp1) if bull else (lo <= tp1):
            return Trade(variant.name, e_idx, i, entry, sl, tp1, "win", round(abs(tp1 - entry) / risk, 4),
                         strength, p_win, ev)
        if variant.breakeven_at is not None and not be_done:
            favorable = (hi - entry) if bull else (entry - lo)
            if favorable >= variant.breakeven_at * risk:
                sl_cur, be_done = entry, True
        if i - e_idx >= TRADE_TIMEOUT_FACTOR * span:
            close = float(k["close"])
            return Trade(variant.name, e_idx, i, entry, sl, tp1, "expired", round(sign * (close - entry) / risk, 4),
                         strength, p_win, ev)
    return None   # pozycja wciąż otwarta - nie liczymy


# ─────────────────────────── raport ───────────────────────────

def summarize(trades: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """trades: dict z kluczami r, status, exit_time. Win rate, przedział Wilsona, średnie i łączne R,
    największe obsunięcie w R (po kolei wg czasu wyjścia)."""
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    wins = sum(1 for t in trades if t["status"] == "win")
    rs = [float(t["r"]) for t in sorted(trades, key=lambda t: t["exit_time"])]
    equity = peak = drawdown = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    lo, hi = wilson_interval(wins, n)
    mean = sum(rs) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rs) / (n - 1)) if n > 1 else 0.0
    return {
        "trades": n, "wins": wins, "breakeven": sum(1 for t in trades if t["status"] == "be"),
        "win_rate": round(wins / n, 4), "win_rate_ci95": [lo, hi],
        "avg_r": round(mean, 4), "avg_r_ci95": [round(mean - 1.96 * sd / math.sqrt(n), 4),
                                                round(mean + 1.96 * sd / math.sqrt(n), 4)] if n > 1 else None,
        "total_r": round(sum(rs), 2), "max_drawdown_r": round(drawdown, 2),
    }


def equity_curve(trades: Sequence[Dict[str, Any]], points: int = 200) -> List[List[float]]:
    """Skumulowane R po czasie wyjścia - [[exit_time_ms, cum_r], ...], przerzedzone do `points` punktów."""
    curve, total = [], 0.0
    for t in sorted(trades, key=lambda t: t["exit_time"]):
        total += float(t["r"])
        curve.append([int(t["exit_time"]), round(total, 3)])
    if len(curve) <= points:
        return curve
    step = len(curve) / points
    return [curve[int(i * step)] for i in range(points - 1)] + [curve[-1]]


def breakdown(trades: Sequence[Dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        groups.setdefault(str(t.get(key)), []).append(t)
    return {k: summarize(v) for k, v in sorted(groups.items())}


def report(trades: Iterable[Dict[str, Any]], cutoff_ms: Optional[int], details: bool = True) -> List[Dict[str, Any]]:
    """Wiersz na wariant: wyniki całości, przed cutoff ("in") i po cutoff ("out" - poza próbką modelu
    siły); z details - krzywa kapitału w R i rozbicie na interwały / formacje (dashboard benchmarków)."""
    by_variant: Dict[str, List[Dict[str, Any]]] = {}
    for t in trades:
        by_variant.setdefault(t["variant"], []).append(t)
    rows = []
    for v in VARIANTS:
        ts = by_variant.get(v.name, [])
        row = {"variant": v.name, "label": v.label, "all": summarize(ts)}
        if cutoff_ms is not None:
            row["in"] = summarize([t for t in ts if t["entry_time"] < cutoff_ms])
            row["out"] = summarize([t for t in ts if t["entry_time"] >= cutoff_ms])
        if details:
            row["equity"] = equity_curve(ts)
            row["by_interval"] = breakdown(ts, "interval")
            row["by_pattern"] = breakdown(ts, "pattern_type")
        rows.append(row)
    return rows
