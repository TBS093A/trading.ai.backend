"""
Silnik tradingu z setupów XABCD: konta paper (wypełnienia na świecach) i Binance USDT-M Futures
(src/trading/live.py + binance_futures.py - ten sam przepływ, wypełnienia z giełdy, rekoncyliacja co przebieg).

Wołany po każdym godzinnym przebiegu śledzenia setupów dla pary (asset, interwał) z zamkniętymi świecami:

1. otwarte sygnały konta na tej parze:
   - "armed" (czeka zlecenie wejścia): dopasowanie limitu na świecach po wystawieniu - do chwili, w której
     setup przestał czekać (invalidated / no_entry -> zlecenie anulowane);
   - "entered" (pozycja): wyjście na SL / TP (src/trading/paper_exchange.py), a gdy setup wygasł (expired)
     - zamknięcie po cenie zamknięcia świecy wygaśnięcia;
2. nowe sygnały: setupy "waiting" z tej pary, jeszcze bez sygnału na koncie -> filtry konta i jakości
   (siła wstępna, EV) -> limity ryzyka -> wielkość pozycji z ryzyka -> sygnał + zlecenie limit na bliższej
   krawędzi PRZ, z SL i TP wg reguł z wykresu (D = wejście, jak w symulacji). Odrzucenie przez limity też
   jest zapisywane (sygnał "rejected" z powodem), żeby było widać, co przepadło i dlaczego.

Wejście "confirm" (świeca odwrócenia) jest w setup_variants; tu konto paper wchodzi przy dotknięciu PRZ -
wariant zgodny z serią produkcyjną i z raportem "baseline". Każda decyzja trafia do trading_events.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .. import harmonic_setups, setup_variants
from ..harmonic_setups import Pivot, Setup
from . import binance_futures
from . import paper_exchange as px
from .live import LiveTrader
from .risk import RiskSettings, position_size

logger = logging.getLogger(__name__)

NEW_SETUP_LOOKBACK_CANDLES = 3   # nowy setup -> sygnał tylko, gdy powstał niedawno (jak alerty)
CONFIRM_WINDOW = 3               # świece po dotknięciu na potwierdzenie (jak wariant "confirm" w raporcie)
TOUCHED_STATUSES = ("open", "win", "loss", "expired")   # setupy, w których cena dotknęła PRZ


def setup_from_row(row: Dict[str, Any]) -> Setup:
    """Setup z wiersza bazy - indeksy nie są potrzebne do reguł SL/TP (liczą się ceny)."""
    pts = row["points_json"]
    points = {n: Pivot(i, float(pts[n]["price"]), n in ("A", "C") if row["is_bullish"] else n in ("X", "B"), i)
              for i, n in enumerate(("X", "A", "B", "C"))}
    return Setup(row["pattern_type"], bool(row["is_bullish"]), points, float(row["prz_min"]), float(row["prz_max"]),
                 created_index=3, spacing=int(row.get("spacing") or 0))


def plan_from_setup(row: Dict[str, Any], targets_fn: Optional[Callable] = None) -> Dict[str, Any]:
    """Wejście na bliższej krawędzi PRZ, SL/TP wg reguł z wykresu (fallback, gdy niespójne)."""
    setup = setup_from_row(row)
    entry = setup.prz_max if setup.is_bullish else setup.prz_min
    sl, tp, _tp2, source = (targets_fn or harmonic_setups.app_targets)(setup, entry)
    if not harmonic_setups._targets_valid(setup.is_bullish, entry, sl, tp, None):
        sl, tp, _tp2, source = harmonic_setups.fallback_targets(setup, entry)
    return {"direction": "long" if setup.is_bullish else "short", "entry": entry, "sl": sl, "tp": tp,
            "targets_source": source}


def setup_on_klines(row: Dict[str, Any], klines: List[Dict]) -> Optional[Setup]:
    """Setup z wiersza bazy z indeksami świec z `klines` (potrzebne do dotknięcia / potwierdzenia)."""
    index = {int(k["open_time"]): i for i, k in enumerate(klines)}
    pts = row["points_json"]
    idx = {n: index.get(int(pts[n]["time"])) for n in ("X", "A", "B", "C")}
    created = index.get(int(row["created_time"]))
    if created is None or any(v is None for v in idx.values()):
        return None
    bull = bool(row["is_bullish"])
    points = {n: Pivot(idx[n], float(pts[n]["price"]), (n in ("A", "C")) if bull else (n in ("X", "B")), idx[n])
              for n in idx}
    return Setup(row["pattern_type"], bull, points, float(row["prz_min"]), float(row["prz_max"]),
                 created_index=created, spacing=int(row.get("spacing") or 0))


def confirm_plan(setup: Setup, entry: float, extreme: float, targets_fn: Optional[Callable] = None
                 ) -> Optional[Dict[str, Any]]:
    """Wejście po potwierdzeniu: SL dalszy z reguł z wykresu i z ekstremum od dotknięcia (jak w raporcie)."""
    bull = setup.is_bullish
    sl, tp, _tp2, source = (targets_fn or harmonic_setups.app_targets)(setup, entry)
    structural = extreme * (1 - setup_variants.SL_BUFFER) if bull else extreme * (1 + setup_variants.SL_BUFFER)
    sl = structural if sl is None else (min(sl, structural) if bull else max(sl, structural))
    if not harmonic_setups._targets_valid(bull, entry, sl, tp, None):
        sl, tp, _tp2, source = harmonic_setups.fallback_targets(setup, entry)
        sl = min(sl, structural) if bull else max(sl, structural)
    if not harmonic_setups._targets_valid(bull, entry, sl, tp, None):
        return None
    return {"direction": "long" if bull else "short", "entry": entry, "sl": sl, "tp": tp, "targets_source": source}


def market_price(direction: str, price: float, slippage_pct: float) -> float:
    slip = slippage_pct / 100.0
    return price * (1 + slip) if direction == "long" else price * (1 - slip)


def _day_start_ms(ms: int) -> int:
    d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


class TradingEngine:
    def __init__(self, db, strength_fn: Optional[Callable] = None, targets_fn: Optional[Callable] = None,
                 exchange_factory: Optional[Callable[[str], Any]] = None,
                 entry_strength_fn: Optional[Callable] = None):
        self.db = db
        self.table = db.get_factory().get_trading_table()
        self.setups = db.get_factory().get_technical_analysis_harmonic_setups_table()
        self.strength_fn = strength_fn
        self.targets_fn = targets_fn
        # siła PEŁNA na zamkniętej świecy wejścia (tryb "confirm"): (setup, indeks, cena, świece) -> score
        self.entry_strength_fn = entry_strength_fn
        self.exchange_factory = exchange_factory or binance_futures.from_env
        self._exchanges: Dict[str, Any] = {}

    def _live(self, exchange: str) -> LiveTrader:
        if exchange not in self._exchanges:
            self._exchanges[exchange] = self.exchange_factory(exchange)
        return LiveTrader(self, self._exchanges[exchange])

    async def process_pair(self, asset_id: int, interval: str, symbol: str, klines: List[Dict]) -> Dict[str, Any]:
        out = {}
        for account in await self.table.list_accounts(enabled_only=True):
            if account["exchange"] != "paper" and account["exchange"] not in binance_futures.LIVE_EXCHANGES:
                continue
            try:
                live = self._live(account["exchange"]) if account["exchange"] != "paper" else None
                out[account["id"]] = await self._process_account(account, asset_id, interval, symbol, klines, live)
            except Exception as e:
                logger.error(f"Trading: konto {account['id']} {symbol} [{interval}] nie powiodło się: {e}", exc_info=True)
                await self.table.log_event(account["id"], "error", f"{symbol} [{interval}]: {e}")
        return out

    # ─────────── konto na parze ───────────

    async def _process_account(self, account: Dict[str, Any], asset_id: int, interval: str, symbol: str,
                               klines: List[Dict], live: Optional[LiveTrader] = None) -> Dict[str, int]:
        risk = RiskSettings.from_dict(account["risk_json"])
        counts = {"filled": 0, "closed": 0, "cancelled": 0, "signals": 0, "rejected": 0}
        now = int(klines[-1]["open_time"]) if klines else 0
        for sig in await self.table.open_signals(account["id"], asset_id, interval):
            if live:
                update = live.update_armed if sig["status"] == "armed" else live.update_entered
                result = await update(account, sig, risk, now)
            elif sig["status"] == "armed":
                result = await self._update_armed(account, sig, klines, risk)
            else:
                result = await self._update_entered(account, sig, klines, risk)
            if result:
                counts[result] += 1
            account = await self.table.get_account(account["id"])
        if live:
            found = await live.reconcile(account, symbol, now, float(klines[-1]["close"]) if klines else None)
            counts["discrepancies"] = sum(found.values())
            account = await self.table.get_account(account["id"])
        if not account["kill_switch"]:
            new = await self._new_signals(account, asset_id, interval, symbol, klines, risk, now, live)
            for key, n in new.items():
                counts[key] += n
        return counts

    async def _update_armed(self, account, sig, klines, risk) -> Optional[str]:
        orders = await self.table.orders_for_signal(sig["id"])
        entry_order = next((o for o in orders if o["purpose"] == "entry" and o["status"] == "open"), None)
        if entry_order is None:
            return None
        setup = await self.setups.get_by_id(sig["setup_id"]) if sig.get("setup_id") else None
        # Świece po wystawieniu zlecenia, a gdy setup przestał czekać - tylko do jego wyjścia.
        end = setup["exit_time"] if setup and setup["status"] in ("invalidated", "no_entry") else None
        candles = [k for k in klines if int(k["open_time"]) > entry_order["placed_time"]
                   and (end is None or int(k["open_time"]) < end)]
        fill = px.match_limit_entry(candles, sig["direction"], entry_order["price"])
        if fill is None:
            if end is not None:
                await self.table.set_order_status(entry_order["id"], "cancelled")
                await self.table.set_signal_status(sig["id"], "cancelled", f"setup {setup['status']}")
                await self.table.log_event(account["id"], "entry_cancelled",
                                           f"Wejście anulowane - setup {setup['status']}", sig["id"],
                                           entry_order["id"], market_time=end)
                return "cancelled"
            return None
        await self._paper_fill(account, sig, entry_order, risk, fill)
        await self._update_entered(account, {**sig, "status": "entered"}, klines, risk)
        return "filled"

    async def _paper_fill(self, account, sig, entry_order, risk, fill) -> None:
        """Wypełnienie wejścia na koncie paper: pozycja + zlecenia SL i TP."""
        fee = px.fee(fill.price, entry_order["qty"], risk.fee_pct)
        position = await self.table.open_position(
            account_id=account["id"], signal_id=sig["id"], asset_id=sig["asset_id"], symbol=sig["symbol"],
            direction=sig["direction"], qty=entry_order["qty"], entry_price=fill.price, sl=sig["sl"], tp=sig["tp"],
            risk_amount=abs(fill.price - sig["sl"]) * entry_order["qty"], opened_time=fill.time, fees=fee,
        )
        await self.table.fill_order(entry_order["id"], fill.price, entry_order["qty"], fee, fill.time, position["id"])
        exit_side = "sell" if sig["direction"] == "long" else "buy"
        for purpose, otype, price in (("stop_loss", "stop_market", sig["sl"]), ("take_profit", "take_profit", sig["tp"])):
            await self.table.create_order(
                account_id=account["id"], signal_id=sig["id"], position_id=position["id"],
                client_order_id=f"pa{account['id']}-s{sig['id']}-{purpose}", symbol=sig["symbol"], side=exit_side,
                position_side=sig["direction"], order_type=otype, purpose=purpose, price=price,
                qty=entry_order["qty"], status="open", placed_time=fill.time,
            )
        await self.table.set_signal_status(sig["id"], "entered")
        await self.table.log_event(account["id"], "entry_filled",
                                   f"{sig['direction'].upper()} {sig['symbol']} {entry_order['qty']:.6g} @ {fill.price:.8g}",
                                   sig["id"], entry_order["id"], position["id"], market_time=fill.time)

    async def _update_entered(self, account, sig, klines, risk) -> Optional[str]:
        position = await self.table.position_for_signal(sig["id"])
        if position is None or position["status"] != "open":
            return None
        entry_order = next((o for o in await self.table.orders_for_signal(sig["id"]) if o["purpose"] == "entry"), None)
        result = px.match_exit(klines, sig["direction"], position["sl"], position["tp"], position["opened_time"],
                               risk.slippage_pct, entered_at_open=bool(entry_order and entry_order["order_type"] == "market"))
        reason = fill = None
        if result:
            reason, fill = result["reason"], result["fill"]
        else:
            setup = await self.setups.get_by_id(sig["setup_id"]) if sig.get("setup_id") else None
            if setup and setup["status"] == "expired" and setup.get("exit_time"):
                candle = next((k for k in klines if int(k["open_time"]) == setup["exit_time"]), None)
                if candle is not None:
                    reason, fill = "timeout", px.Fill(float(candle["close"]), int(candle["open_time"]), 0)
        if fill is None:
            if klines:
                await self.table.mark_position(position["id"], float(klines[-1]["close"]), int(klines[-1]["open_time"]))
            return None
        exit_fee = px.fee(fill.price, position["qty"], risk.fee_pct)
        for o in await self.table.orders_for_signal(sig["id"]):
            if o["status"] != "open":
                continue
            if (reason == "sl" and o["purpose"] == "stop_loss") or (reason == "tp" and o["purpose"] == "take_profit"):
                await self.table.fill_order(o["id"], fill.price, o["qty"], exit_fee, fill.time)
            else:
                await self.table.set_order_status(o["id"], "cancelled")
        if reason == "timeout":
            close = await self.table.create_order(
                account_id=account["id"], signal_id=sig["id"], position_id=position["id"],
                client_order_id=f"pa{account['id']}-s{sig['id']}-close", symbol=sig["symbol"],
                side="sell" if sig["direction"] == "long" else "buy", position_side=sig["direction"],
                order_type="market", purpose="close", price=None, qty=position["qty"], status="open",
                placed_time=fill.time,
            )
            if close:
                await self.table.fill_order(close["id"], fill.price, position["qty"], exit_fee, fill.time)
        await self._finish_close(account, sig, position, fill.price, fill.time, reason, exit_fee, risk)
        return "closed"

    async def _finish_close(self, account, sig, position, price: float, closed_time: int, reason: str,
                            exit_fee: float, risk: Optional[RiskSettings], qty: Optional[float] = None) -> None:
        """Wspólne dla paper i giełdy: wynik, zamknięcie pozycji i sygnału, gotówka, szczyt, kill switch."""
        risk = risk or RiskSettings.from_dict(account["risk_json"])
        qty = position["qty"] if qty is None else qty
        fees = position["fees"] + exit_fee
        pnl = px.pnl(sig["direction"], position["entry_price"], price, qty) - fees
        r_multiple = pnl / position["risk_amount"] if position["risk_amount"] else 0.0
        await self.table.close_position(position["id"], price, reason, closed_time, fees, pnl, round(r_multiple, 4))
        await self.table.set_signal_status(sig["id"], "closed", reason)
        account = await self.table.get_account(account["id"])
        cash = account["cash"] + pnl
        peak = max(account["peak_equity"], cash)
        await self.table.update_account(account["id"], cash=cash, peak_equity=peak)
        await self.table.log_event(account["id"], "position_closed",
                                   f"{sig['symbol']} {reason.upper()} {pnl:+.2f} {account['base_currency']} ({r_multiple:+.2f} R)",
                                   sig["id"], position_id=position["id"], market_time=closed_time,
                                   data={"pnl": pnl, "r": r_multiple, "fees": fees})
        if peak > 0 and (peak - cash) / peak * 100.0 >= risk.max_drawdown_stop_pct and not account["kill_switch"]:
            msg = f"Obsunięcie {(peak - cash) / peak * 100:.1f}% >= {risk.max_drawdown_stop_pct}% - kill switch"
            await self.table.update_account(account["id"], kill_switch=True, kill_reason=msg)
            await self.table.log_event(account["id"], "kill_switch", msg, market_time=closed_time)

    # ─────────── nowe sygnały ───────────

    async def _new_signals(self, account, asset_id, interval, symbol, klines, risk, now,
                           live: Optional[LiveTrader] = None) -> Dict[str, int]:
        counts = {"signals": 0, "rejected": 0}
        if not klines:
            return counts
        filters = account.get("filters_json") or {}
        if filters.get("intervals") and interval not in filters["intervals"]:
            return counts
        if filters.get("asset_ids") and asset_id not in filters["asset_ids"]:
            return counts
        step = int(klines[-1]["open_time"]) - int(klines[-2]["open_time"]) if len(klines) > 1 else 0
        if account.get("entry_mode") == "confirm":
            candidates = await self._confirm_candidates(asset_id, interval, klines, now, step)
        else:
            candidates = await self._touch_candidates(asset_id, interval, now, step)
        if filters.get("patterns"):
            candidates = [c for c in candidates if c["row"]["pattern_type"] in filters["patterns"]]
        if filters.get("direction") in ("long", "short"):
            candidates = [c for c in candidates if c["plan"]["direction"] == filters["direction"]]
        done = await self.table.signaled_setup_ids(account["id"], [c["row"]["id"] for c in candidates])
        for c in candidates:
            if c["row"]["id"] in done:
                continue
            result = await self._open_signal(account, asset_id, interval, symbol, risk, now, live, **c)
            if result:
                counts[result] += 1
        return counts

    async def _touch_candidates(self, asset_id, interval, now, step) -> List[Dict[str, Any]]:
        """Wejście przy dotknięciu: świeże setupy "waiting" -> limit na bliższej krawędzi PRZ, siła wstępna."""
        waiting = await self.setups.list(asset_id, interval, harmonic_setups.params_version(), status="waiting",
                                         limit=200)
        out = []
        for row in sorted(waiting, key=lambda r: r["created_time"]):
            if row["created_time"] < now - NEW_SETUP_LOOKBACK_CANDLES * step:
                continue
            strength = self.strength_fn(row) if self.strength_fn else None
            out.append({"row": row, "plan": plan_from_setup(row, self.targets_fn), "strength": strength,
                        "order_type": "limit", "fill": None})
        return out

    async def _confirm_candidates(self, asset_id, interval, klines, now, step) -> List[Dict[str, Any]]:
        """Wejście po potwierdzeniu (src/setup_variants.py: wariant "confirm"): setupy, w których cena niedawno
        dotknęła PRZ, i świeca odwrócenia zamknęła się w ostatnich NEW_SETUP_LOOKBACK_CANDLES świecach ->
        wejście po jej zamknięciu, SL za ekstremum od dotknięcia, siła PEŁNA na zamkniętej świecy."""
        rows = await self.setups.list(asset_id, interval, harmonic_setups.params_version(), limit=400,
                                      statuses=TOUCHED_STATUSES)
        horizon = now - (CONFIRM_WINDOW + NEW_SETUP_LOOKBACK_CANDLES) * step
        out = []
        for row in rows:
            if row.get("entry_time") is None or row["entry_time"] < horizon:
                continue
            setup = setup_on_klines(row, klines)
            if setup is None:
                continue
            touch = next((i for i, k in enumerate(klines) if int(k["open_time"]) == row["entry_time"]), None)
            confirmed = setup_variants._confirmation(setup, klines, touch, CONFIRM_WINDOW) if touch is not None else None
            if confirmed is None:
                continue
            j, extreme = confirmed
            if int(klines[j]["open_time"]) < now - NEW_SETUP_LOOKBACK_CANDLES * step:
                continue
            plan = confirm_plan(setup, float(klines[j]["close"]), extreme, self.targets_fn)
            if plan is None:
                continue
            strength = self.entry_strength_fn(setup, j, plan["entry"], klines) if self.entry_strength_fn else None
            # Wejście po zamknięciu świecy potwierdzenia = otwarcie następnej; SL/TP od niej.
            opened = int(klines[j]["open_time"]) + step
            out.append({"row": row, "plan": plan, "strength": strength, "order_type": "market",
                        "fill": {"price": plan["entry"], "time": opened}})
        return sorted(out, key=lambda c: c["fill"]["time"])

    async def _open_signal(self, account, asset_id, interval, symbol, risk, now, live, row, plan, strength,
                           order_type, fill) -> Optional[str]:
        score = strength.get("score") if strength else None
        p_win = strength.get("p_win") if strength else None
        rr = abs(plan["tp"] - plan["entry"]) / abs(plan["entry"] - plan["sl"])
        ev = round(p_win * rr - (1 - p_win), 4) if p_win is not None else None
        if risk.min_strength is not None and (score is None or score < risk.min_strength):
            return None   # filtr jakości - nie zapisujemy (to większość setupów)
        if risk.min_ev is not None and (ev is None or ev < risk.min_ev):
            return None
        reason = await self._risk_rejection(account, asset_id, risk, now)
        size = position_size(account["cash"], plan["entry"], plan["sl"], risk)
        if reason is None and size["qty"] <= 0:
            reason = "wielkość pozycji 0 (brak kapitału albo SL w cenie wejścia)"
        if reason is None and live:
            # tickSize / stepSize / min notional / depozyt - sygnał zapisany z cenami, które pójdą na giełdę
            plan, qty, reason = await live.conform(account, symbol, plan, size["qty"], risk)
            size = {**size, "qty": qty, "notional": qty * plan["entry"],
                    "risk_pct": qty * abs(plan["entry"] - plan["sl"]) / account["cash"] * 100.0}
        base = dict(account_id=account["id"], setup_id=row["id"], asset_id=asset_id, symbol=symbol,
                    interval=interval, pattern_type=row["pattern_type"], direction=plan["direction"],
                    entry_price=plan["entry"], sl=plan["sl"], tp=plan["tp"], strength=score, p_win=p_win, ev=ev,
                    setup_created_time=row["created_time"])
        if reason:
            sig = await self.table.create_signal(**base, status="rejected", reason=reason)
            if sig:
                await self.table.log_event(account["id"], "signal_rejected", f"{symbol} [{interval}]: {reason}",
                                           sig["id"], market_time=now)
                return "rejected"
            return None
        sig = await self.table.create_signal(**base, status="armed", reason=None)
        if not sig:
            return None
        order = await self.table.create_order(
            account_id=account["id"], signal_id=sig["id"], position_id=None,
            client_order_id=(live.client_id(account["id"], sig["id"], "entry") if live
                             else f"pa{account['id']}-s{sig['id']}-entry"), symbol=symbol,
            side="buy" if plan["direction"] == "long" else "sell", position_side=plan["direction"],
            order_type=order_type, purpose="entry", price=plan["entry"] if order_type == "limit" else None,
            qty=size["qty"], status="open", placed_time=now,
        )
        how = (f"limit {plan['entry']:.8g}" if order_type == "limit"
               else f"rynek po potwierdzeniu ~{plan['entry']:.8g}")
        await self.table.log_event(
            account["id"], "signal_armed",
            f"{plan['direction'].upper()} {symbol} [{interval}] {row['pattern_type']}: {how}, "
            f"SL {plan['sl']:.8g}, TP {plan['tp']:.8g}, ryzyko {size['risk_pct']:.2f}%",
            sig["id"], order["id"] if order else None, market_time=now,
            data={"strength": score, "p_win": p_win, "ev": ev, "qty": size["qty"], "notional": size["notional"],
                  "targets_source": plan.get("targets_source"), "entry_mode": "confirm" if fill else "touch"},
        )
        if live and order:
            await live.submit_entry(account, sig, order, risk, now)
        elif fill and order:
            await self._paper_fill(account, {**sig, "status": "armed"}, order, risk,
                                   px.Fill(market_price(plan["direction"], fill["price"], risk.slippage_pct),
                                           fill["time"], 0))
        return "signals"

    async def _risk_rejection(self, account, asset_id, risk: RiskSettings, now: int) -> Optional[str]:
        if account["kill_switch"]:
            return f"kill switch: {account.get('kill_reason') or 'włączony ręcznie'}"
        open_sigs = await self.table.open_signals(account["id"])
        if len(open_sigs) >= risk.max_open_positions:
            return f"limit otwartych pozycji ({risk.max_open_positions})"
        if sum(1 for s in open_sigs if s["asset_id"] == asset_id) >= risk.max_positions_per_asset:
            return f"limit pozycji na asset ({risk.max_positions_per_asset})"
        day_pnl = await self.table.realized_pnl_since(account["id"], _day_start_ms(now))
        if day_pnl <= -account["cash"] * risk.daily_loss_limit_pct / 100.0:
            return f"dzienny limit straty ({risk.daily_loss_limit_pct}%): {day_pnl:.2f}"
        return None

    # ─────────── kapitał ───────────

    async def snapshot(self, market_time: int) -> int:
        n = 0
        for account in await self.table.list_accounts():
            open_positions = await self.table.positions(account["id"], status="open")
            unrealized = sum(px.pnl(p["direction"], p["entry_price"], p["mark_price"], p["qty"])
                             for p in open_positions if p.get("mark_price") is not None)
            await self.table.snapshot_equity(account["id"], market_time, account["cash"] + unrealized,
                                             account["cash"], len(open_positions))
            n += 1
        return n
