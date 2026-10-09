"""
Ustawienia ryzyka konta tradingowego: pola z opisem, gotowe warianty i podgląd skutków na historii.

Każde pole ma opis (co robi i co znaczy zmiana), zakres i wartość domyślną - dashboard buduje formularz
z RISK_FIELDS. Warianty (RISK_PRESETS) to gotowe zestawy z opisem, dla kogo są. preview() przelicza
wybrane ustawienia na transakcjach z raportu wariantów (src/setup_variants.py) - krzywa kapitału,
obsunięcie, serie strat, dni zatrzymane limitem dziennym i szansa ruiny z losowania kolejności.
"""

import math
import random
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence


@dataclass
class RiskSettings:
    risk_per_trade_pct: float = 0.5
    max_open_positions: int = 5
    max_positions_per_asset: int = 1
    daily_loss_limit_pct: float = 2.0
    max_drawdown_stop_pct: float = 15.0
    max_position_notional_pct: float = 100.0
    min_strength: Optional[int] = 60
    min_ev: Optional[float] = None
    fee_pct: float = 0.04
    slippage_pct: float = 0.02

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "RiskSettings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


RISK_FIELDS: List[Dict[str, Any]] = [
    {"key": "risk_per_trade_pct", "label": "Ryzyko na transakcję (% kapitału)", "min": 0.05, "max": 5.0, "step": 0.05,
     "description": "Ile kapitału tracisz, gdy transakcja dojdzie do SL. Wielkość pozycji = kapitał × ryzyko / "
                    "odległość wejścia od SL. 0,5% oznacza, że 10 strat z rzędu to ok. −4,9% kapitału; 2% - ok. −18%."},
    {"key": "max_open_positions", "label": "Maks. otwartych pozycji", "min": 1, "max": 50, "step": 1,
     "description": "Łącznie z czekającymi zleceniami wejścia. Ogranicza ryzyko naraz: 5 pozycji × 0,5% = 2,5% "
                    "kapitału, gdy wszystkie trafią w SL jednocześnie (np. przy krachu całego rynku)."},
    {"key": "max_positions_per_asset", "label": "Maks. pozycji na jeden asset", "min": 1, "max": 5, "step": 1,
     "description": "Kilka setupów na tym samym assecie zwykle gra ten sam ruch - 1 chroni przed podwójnym ryzykiem."},
    {"key": "daily_loss_limit_pct", "label": "Dzienny limit straty (% kapitału)", "min": 0.5, "max": 20.0, "step": 0.5,
     "description": "Po przekroczeniu (zrealizowana strata od północy UTC) nowe sygnały są odrzucane do końca dnia, "
                    "otwarte pozycje prowadzone dalej. Przerywa serie złych decyzji w złym dniu rynku."},
    {"key": "max_drawdown_stop_pct", "label": "Wyłącznik przy obsunięciu (% od szczytu)", "min": 2.0, "max": 60.0,
     "step": 1.0,
     "description": "Gdy kapitał spadnie o tyle od najwyższego punktu, konto włącza kill switch: żadnych nowych "
                    "transakcji, dopóki go ręcznie nie wyłączysz. Ostatnia linia obrony przed zepsutą strategią."},
    {"key": "max_position_notional_pct", "label": "Maks. wartość pozycji (% kapitału)", "min": 10.0, "max": 300.0,
     "step": 10.0,
     "description": "Limit dźwigni: przy bardzo bliskim SL wielkość z ryzyka wyszłaby ogromna. 100% = bez dźwigni, "
                    "200% = najwyżej 2x. Pozycja jest wtedy zmniejszana (ryzyko spada poniżej ustawionego)."},
    {"key": "min_strength", "label": "Minimalna siła setupu (0-100)", "min": 0, "max": 100, "step": 5, "nullable": True,
     "description": "Filtr jakości: sygnał tylko dla setupów z siłą (wstępną dla czekających na PRZ) od tego progu. "
                    "Wyżej = mniej transakcji, ale lepszych - porównaj warianty strength_60/80 w Benchmarkach."},
    {"key": "min_ev", "label": "Minimalna wartość oczekiwana (R)", "min": -0.5, "max": 1.0, "step": 0.05,
     "nullable": True,
     "description": "EV = szansa TP1 × R:R − (1 − szansa). 0 = tylko setupy z dodatnią wartością oczekiwaną "
                    "według modelu; puste = bez filtra."},
    {"key": "fee_pct", "label": "Opłata za zlecenie (%)", "min": 0.0, "max": 0.5, "step": 0.01,
     "description": "Na wejściu i wyjściu. Binance USDT-M: 0,02% maker / 0,05% taker (bez zniżek)."},
    {"key": "slippage_pct", "label": "Poślizg na zleceniach stop / market (%)", "min": 0.0, "max": 1.0, "step": 0.01,
     "description": "Ile gorzej od ceny SL / rynku realnie wypełnia się zlecenie. Tylko konto paper - na giełdzie "
                    "poślizg wynika z wypełnień."},
]

RISK_PRESETS: List[Dict[str, Any]] = [
    {"key": "conservative", "label": "Ostrożny",
     "description": "Na start i na live z prawdziwymi pieniędzmi: małe ryzyko, mało pozycji naraz, wcześnie "
                    "zatrzymuje zły dzień. Wolny wzrost, małe obsunięcia.",
     "settings": RiskSettings(0.25, 3, 1, 1.0, 10.0, 100.0, 70, 0.0).as_dict()},
    {"key": "balanced", "label": "Zrównoważony",
     "description": "Domyślny dla paper: 0,5% na transakcję, do 5 pozycji, filtr siły 60. Kompromis między "
                    "liczbą transakcji a stabilnością.",
     "settings": RiskSettings().as_dict()},
    {"key": "aggressive", "label": "Agresywny",
     "description": "Do testów na paper: 1% na transakcję, do 10 pozycji, bez filtra siły. Szybciej pokazuje, "
                    "jak strategia zachowuje się przy dużej liczbie transakcji - obsunięcia będą głębokie.",
     "settings": RiskSettings(1.0, 10, 1, 4.0, 30.0, 200.0, None, None).as_dict()},
]


def validate(settings: Dict[str, Any]) -> RiskSettings:
    out = RiskSettings.from_dict(settings)
    for f in RISK_FIELDS:
        value = getattr(out, f["key"])
        if value is None:
            if not f.get("nullable"):
                raise ValueError(f"{f['label']}: wymagane")
            continue
        if not (f["min"] <= value <= f["max"]):
            raise ValueError(f"{f['label']}: {value} poza zakresem {f['min']}..{f['max']}")
    return out


def position_size(equity: float, entry: float, sl: float, settings: RiskSettings) -> Dict[str, float]:
    """Ilość z ryzyka, przycięta limitem wartości pozycji. Zwraca qty, notional i faktyczne ryzyko %."""
    risk_per_unit = abs(entry - sl)
    if equity <= 0 or risk_per_unit <= 0 or entry <= 0:
        return {"qty": 0.0, "notional": 0.0, "risk_pct": 0.0}
    qty = equity * settings.risk_per_trade_pct / 100.0 / risk_per_unit
    max_qty = equity * settings.max_position_notional_pct / 100.0 / entry
    qty = min(qty, max_qty)
    return {"qty": qty, "notional": qty * entry, "risk_pct": qty * risk_per_unit / equity * 100.0}


# ─────────────────────────── podgląd na historii ───────────────────────────

def _day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _replay(trades: Sequence[Dict[str, Any]], s: RiskSettings, start_equity: float) -> Dict[str, Any]:
    """Transakcje (r, entry_time, exit_time, strength, ev, asset_id) z ograniczeniami konta: równoległe
    pozycje, jedna na asset, dzienny limit, wyłącznik obsunięcia. Wynik w walucie konta."""
    events = sorted(trades, key=lambda t: t["entry_time"])
    equity = peak = start_equity
    max_dd = 0.0
    open_pos: List[Dict[str, Any]] = []
    day_pnl: Dict[str, float] = {}
    stopped_days = set()
    taken = skipped = 0
    streak = worst_streak = 0
    killed_at = None
    curve: List[List[float]] = []
    fee_r = 2 * s.fee_pct / 100.0

    def close_until(t_ms: int) -> None:
        nonlocal equity, peak, max_dd, streak, worst_streak, killed_at
        for p in sorted([p for p in open_pos if p["exit_time"] <= t_ms], key=lambda p: p["exit_time"]):
            open_pos.remove(p)
            pnl = p["risk_amount"] * p["r"] - p["notional"] * fee_r
            equity += pnl
            day_pnl[_day(p["exit_time"])] = day_pnl.get(_day(p["exit_time"]), 0.0) + pnl
            streak = streak + 1 if pnl < 0 else 0
            worst_streak = max(worst_streak, streak)
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak * 100.0 if peak > 0 else 0.0)
            curve.append([p["exit_time"], round(equity, 2)])
            if killed_at is None and peak > 0 and (peak - equity) / peak * 100.0 >= s.max_drawdown_stop_pct:
                killed_at = p["exit_time"]

    for t in events:
        close_until(t["entry_time"])
        if killed_at is not None:
            skipped += 1
            continue
        if s.min_strength is not None and (t.get("strength") is None or t["strength"] < s.min_strength):
            skipped += 1
            continue
        if s.min_ev is not None and (t.get("ev") is None or t["ev"] < s.min_ev):
            skipped += 1
            continue
        day = _day(t["entry_time"])
        if day_pnl.get(day, 0.0) <= -equity * s.daily_loss_limit_pct / 100.0:
            stopped_days.add(day)
            skipped += 1
            continue
        if len(open_pos) >= s.max_open_positions or \
                sum(1 for p in open_pos if p["asset_id"] == t.get("asset_id")) >= s.max_positions_per_asset:
            skipped += 1
            continue
        risk_amount = equity * s.risk_per_trade_pct / 100.0
        open_pos.append({**t, "risk_amount": risk_amount,
                         # bez cen w raporcie: wartość pozycji szacowana jako ryzyko / 1% odległości do SL
                         "notional": min(risk_amount * 100.0, equity * s.max_position_notional_pct / 100.0)})
        taken += 1
    close_until(2 ** 62)
    return {"final_equity": round(equity, 2), "return_pct": round((equity / start_equity - 1) * 100.0, 2),
            "max_drawdown_pct": round(max_dd, 2), "trades_taken": taken, "trades_skipped": skipped,
            "worst_losing_streak": worst_streak, "days_stopped_by_daily_limit": len(stopped_days),
            "kill_switch_at": killed_at, "equity_curve": curve}


def preview(trades: Sequence[Dict[str, Any]], settings: RiskSettings, start_equity: float = 10_000.0,
            simulations: int = 300, ruin_drawdown_pct: float = 50.0, seed: int = 7) -> Dict[str, Any]:
    """Wynik ustawień na historii + rozkład z losowania kolejności wyników (bootstrap z zachowaniem
    częstości transakcji): mediana i 5. percentyl zwrotu, typowe obsunięcie, szansa ruiny (obsunięcie
    >= ruin_drawdown_pct)."""
    base = _replay(trades, settings, start_equity)
    if len(trades) < 20 or simulations <= 0:
        return {**base, "bootstrap": None}
    rnd = random.Random(seed)
    rs = [t["r"] for t in trades]
    returns, drawdowns, ruins = [], [], 0
    for _ in range(simulations):
        shuffled = [{**t, "r": rnd.choice(rs)} for t in trades]
        sim = _replay(shuffled, settings, start_equity)
        returns.append(sim["return_pct"])
        drawdowns.append(sim["max_drawdown_pct"])
        ruins += sim["max_drawdown_pct"] >= ruin_drawdown_pct
    returns.sort()
    drawdowns.sort()
    pct = lambda xs, q: xs[min(len(xs) - 1, max(0, int(math.floor(q * len(xs)))))]
    return {**base, "bootstrap": {
        "simulations": simulations,
        "return_pct_median": pct(returns, 0.5), "return_pct_p5": pct(returns, 0.05),
        "max_drawdown_pct_median": pct(drawdowns, 0.5), "max_drawdown_pct_p95": pct(drawdowns, 0.95),
        "ruin_probability": round(ruins / simulations, 4), "ruin_drawdown_pct": ruin_drawdown_pct,
    }}
