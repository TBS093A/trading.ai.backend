"""
Silnik tradingu z setupów XABCD (konta paper; prawdziwe giełdy - ten sam przepływ, inny adapter).

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

from .. import harmonic_setups
from ..harmonic_setups import Pivot, Setup
from . import paper_exchange as px
from .risk import RiskSettings, position_size

logger = logging.getLogger(__name__)

NEW_SETUP_LOOKBACK_CANDLES = 3   # nowy setup -> sygnał tylko, gdy powstał niedawno (jak alerty)


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


def _day_start_ms(ms: int) -> int:
    d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


class TradingEngine:
    def __init__(self, db, strength_fn: Optional[Callable] = None, targets_fn: Optional[Callable] = None):
        self.db = db
        self.table = db.get_factory().get_trading_table()
        self.setups = db.get_factory().get_technical_analysis_harmonic_setups_table()
        self.strength_fn = strength_fn
        self.targets_fn = targets_fn

    async def process_pair(self, asset_id: int, interval: str, symbol: str, klines: List[Dict]) -> Dict[str, Any]:
        out = {}
        for account in await self.table.list_accounts(enabled_only=True):
            if account["exchange"] != "paper":
                continue   # prawdziwe giełdy - osobny adapter (kolejny PR)
            try:
                out[account["id"]] = await self._process_account(account, asset_id, interval, symbol, klines)
            except Exception as e:
                logger.error(f"Trading: konto {account['id']} {symbol} [{interval}] nie powiodło się: {e}", exc_info=True)
                await self.table.log_event(account["id"], "error", f"{symbol} [{interval}]: {e}")
        return out

    # ─────────── konto na parze ───────────

    async def _process_account(self, account: Dict[str, Any], asset_id: int, interval: str, symbol: str,
                               klines: List[Dict]) -> Dict[str, int]:
        risk = RiskSettings.from_dict(account["risk_json"])
        counts = {"filled": 0, "closed": 0, "cancelled": 0, "signals": 0, "rejected": 0}
        now = int(klines[-1]["open_time"]) if klines else 0
        for sig in await self.table.open_signals(account["id"], asset_id, interval):
            if sig["status"] == "armed":
                result = await self._update_armed(account, sig, klines, risk)
            else:
                result = await self._update_entered(account, sig, klines, risk)
            if result:
                counts[result] += 1
            account = await self.table.get_account(account["id"])
        if not account["kill_switch"]:
            for key, n in (await self._new_signals(account, asset_id, interval, symbol, klines, risk, now)).items():
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
        await self._update_entered(account, {**sig, "status": "entered"}, klines, risk)
        return "filled"

    async def _update_entered(self, account, sig, klines, risk) -> Optional[str]:
        position = await self.table.position_for_signal(sig["id"])
        if position is None or position["status"] != "open":
            return None
        result = px.match_exit(klines, sig["direction"], position["sl"], position["tp"], position["opened_time"],
                               risk.slippage_pct)
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
        fees = position["fees"] + exit_fee
        pnl = px.pnl(sig["direction"], position["entry_price"], fill.price, position["qty"]) - fees
        r_multiple = pnl / position["risk_amount"] if position["risk_amount"] else 0.0
        await self.table.close_position(position["id"], fill.price, reason, fill.time, fees, pnl, round(r_multiple, 4))
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
        await self.table.set_signal_status(sig["id"], "closed", reason)
        cash = account["cash"] + pnl
        peak = max(account["peak_equity"], cash)
        await self.table.update_account(account["id"], cash=cash, peak_equity=peak)
        await self.table.log_event(account["id"], "position_closed",
                                   f"{sig['symbol']} {reason.upper()} {pnl:+.2f} {account['base_currency']} ({r_multiple:+.2f} R)",
                                   sig["id"], position_id=position["id"], market_time=fill.time,
                                   data={"pnl": pnl, "r": r_multiple, "fees": fees})
        if peak > 0 and (peak - cash) / peak * 100.0 >= risk.max_drawdown_stop_pct and not account["kill_switch"]:
            msg = f"Obsunięcie {(peak - cash) / peak * 100:.1f}% >= {risk.max_drawdown_stop_pct}% - kill switch"
            await self.table.update_account(account["id"], kill_switch=True, kill_reason=msg)
            await self.table.log_event(account["id"], "kill_switch", msg, market_time=fill.time)
        return "closed"

    # ─────────── nowe sygnały ───────────

    async def _new_signals(self, account, asset_id, interval, symbol, klines, risk, now) -> Dict[str, int]:
        counts = {"signals": 0, "rejected": 0}
        if not klines:
            return counts
        filters = account.get("filters_json") or {}
        if filters.get("intervals") and interval not in filters["intervals"]:
            return counts
        if filters.get("asset_ids") and asset_id not in filters["asset_ids"]:
            return counts
        step = int(klines[-1]["open_time"]) - int(klines[-2]["open_time"]) if len(klines) > 1 else 0
        waiting = await self.setups.list(asset_id, interval, harmonic_setups.params_version(), status="waiting",
                                         limit=200)
        fresh = [r for r in waiting if r["created_time"] >= now - NEW_SETUP_LOOKBACK_CANDLES * step]
        if filters.get("patterns"):
            fresh = [r for r in fresh if r["pattern_type"] in filters["patterns"]]
        if filters.get("direction") in ("long", "short"):
            fresh = [r for r in fresh if (r["is_bullish"] == (filters["direction"] == "long"))]
        done = await self.table.signaled_setup_ids(account["id"], [r["id"] for r in fresh])
        for row in sorted(fresh, key=lambda r: r["created_time"]):
            if row["id"] in done:
                continue
            plan = plan_from_setup(row, self.targets_fn)
            strength = self.strength_fn(row) if self.strength_fn else None
            score = strength.get("score") if strength else None
            p_win = strength.get("p_win") if strength else None
            rr = abs(plan["tp"] - plan["entry"]) / abs(plan["entry"] - plan["sl"])
            ev = round(p_win * rr - (1 - p_win), 4) if p_win is not None else None
            if risk.min_strength is not None and (score is None or score < risk.min_strength):
                continue   # filtr jakości - nie zapisujemy (to większość setupów)
            if risk.min_ev is not None and (ev is None or ev < risk.min_ev):
                continue
            base = dict(account_id=account["id"], setup_id=row["id"], asset_id=asset_id, symbol=symbol,
                        interval=interval, pattern_type=row["pattern_type"], direction=plan["direction"],
                        entry_price=plan["entry"], sl=plan["sl"], tp=plan["tp"], strength=score, p_win=p_win, ev=ev,
                        setup_created_time=row["created_time"])
            reason = await self._risk_rejection(account, asset_id, risk, now)
            size = position_size(account["cash"], plan["entry"], plan["sl"], risk)
            if reason is None and size["qty"] <= 0:
                reason = "wielkość pozycji 0 (brak kapitału albo SL w cenie wejścia)"
            if reason:
                sig = await self.table.create_signal(**base, status="rejected", reason=reason)
                if sig:
                    counts["rejected"] += 1
                    await self.table.log_event(account["id"], "signal_rejected", f"{symbol} [{interval}]: {reason}",
                                               sig["id"], market_time=now)
                continue
            sig = await self.table.create_signal(**base, status="armed", reason=None)
            if not sig:
                continue
            order = await self.table.create_order(
                account_id=account["id"], signal_id=sig["id"], position_id=None,
                client_order_id=f"pa{account['id']}-s{sig['id']}-entry", symbol=symbol,
                side="buy" if plan["direction"] == "long" else "sell", position_side=plan["direction"],
                order_type="limit", purpose="entry", price=plan["entry"], qty=size["qty"], status="open",
                placed_time=now,
            )
            counts["signals"] += 1
            await self.table.log_event(
                account["id"], "signal_armed",
                f"{plan['direction'].upper()} {symbol} [{interval}] {row['pattern_type']}: limit {plan['entry']:.8g}, "
                f"SL {plan['sl']:.8g}, TP {plan['tp']:.8g}, ryzyko {size['risk_pct']:.2f}%",
                sig["id"], order["id"] if order else None, market_time=now,
                data={"strength": score, "p_win": p_win, "ev": ev, "qty": size["qty"], "notional": size["notional"],
                      "targets_source": plan["targets_source"]},
            )
        return counts

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
