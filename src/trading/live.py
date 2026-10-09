"""
Przepływ konta na prawdziwej giełdzie (Binance USDT-M Futures) - te same kroki co paper w engine.py, ale
wypełnienia i wyjścia pochodzą z giełdy, nie ze świec:

- "armed": stan zlecenia wejścia po client order id; zlecenie bez potwierdzenia (błąd sieci przy wystawieniu),
  którego giełda nie zna, jest wystawiane ponownie z tym samym id (idempotentnie); setup invalidated / no_entry
  -> anulowanie; wypełnienie (także częściowe + anulowanie reszty) -> pozycja, potem SL (STOP_MARKET) i TP
  (LIMIT) - oba reduceOnly;
- "entered": stan SL / TP; wypełnione wyjście -> anulowanie drugiego i zamknięcie pozycji; setup expired ->
  anulowanie i zamknięcie MARKET reduceOnly; SL, którego nie da się wystawić -> natychmiastowe zamknięcie MARKET
  (pozycja nigdy nie zostaje bez stopa);
- rekoncyliacja w każdym przebiegu (reconcile): giełda wygrywa - saldo portfela -> gotówka konta, nasze
  zlecenia otwarte na giełdzie, których baza nie uznaje za otwarte -> anulowane, pozycja na giełdzie różna
  od bazy -> baza poprawiana (pozycja zniknęła -> zamknięcie "external"). Każda rozbieżność trafia do
  trading_events (kind "reconcile").
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from .binance_futures import WOULD_TRIGGER_CODE, BinanceError, OrderState, futures_symbol
from .risk import RiskSettings

logger = logging.getLogger(__name__)

TP_ORDER_TYPE = "limit"        # LIMIT reduceOnly (maker, jak TP w symulatorze); "take_profit_market" - algo
MARGIN_BUFFER = 0.95           # wartość pozycji <= saldo × dźwignia × bufor (opłaty, ruch ceny do wypełnienia)
OPEN = ("open", "partially_filled")
CLOSED_BY_EXCHANGE = ("cancelled", "expired", "rejected")


class LiveTrader:
    prefix = "bf"

    def __init__(self, engine, exchange):
        self.engine = engine
        self.table = engine.table
        self.setups = engine.setups
        self.ex = exchange

    def client_id(self, account_id: int, signal_id: int, purpose: str) -> str:
        return f"{self.prefix}{account_id}-s{signal_id}-{purpose}"

    async def _event(self, account, kind: str, message: str, sig=None, order=None, position=None,
                     data: Optional[Dict[str, Any]] = None, now: Optional[int] = None) -> None:
        await self.table.log_event(account["id"], kind, message, sig["id"] if sig else None,
                                   order["id"] if order else None, position["id"] if position else None,
                                   data=data, market_time=now)

    # ─────────── nowy sygnał ───────────

    async def conform(self, account, symbol: str, plan: Dict[str, Any], qty: float,
                      risk: RiskSettings) -> Tuple[Dict[str, Any], float, Optional[str]]:
        """Ceny do tickSize, ilość do stepSize (w dół), limit depozytu, filtry symbolu, jedna pozycja na symbol."""
        rules = await self.ex.rules(symbol)
        if rules is None:
            return plan, 0.0, f"{futures_symbol(symbol)} nie jest notowany na Binance USDT-M Futures"
        if any(s["symbol"] == symbol for s in await self.table.open_signals(account["id"])):
            return plan, 0.0, "już jest pozycja / zlecenie na tym symbolu (tryb one-way: jedna na symbol)"
        long = plan["direction"] == "long"
        entry = rules.price(plan["entry"])
        sl = rules.price(plan["sl"], "down" if long else "up")
        tp = rules.price(plan["tp"], "down" if long else "up")
        max_qty = account["cash"] * risk.leverage * MARGIN_BUFFER / float(entry)
        q = rules.qty(min(qty, max_qty))
        reason = rules.check(q, entry)
        return {**plan, "entry": float(entry), "sl": float(sl), "tp": float(tp)}, float(q), reason

    async def submit_entry(self, account, sig, order, risk: RiskSettings, now: int) -> None:
        _state, error = await self._submit(account, sig, order, risk, now)
        if error is not None:
            await self.table.set_signal_status(sig["id"], "cancelled", f"wejście odrzucone: {error}")

    # ─────────── wystawienie i stan zlecenia ───────────

    async def _submit(self, account, sig, order, risk, now) -> Tuple[Optional[OrderState], Optional[BinanceError]]:
        """Wystawia zlecenie. Odrzucenie przez giełdę -> status "rejected"; błąd sieci -> stan nieznany
        (exchange_order_id zostaje pusty, następny przebieg zapyta giełdę o client order id)."""
        rules = await self.ex.rules(order["symbol"])
        try:
            if order["purpose"] == "entry":
                # przed wystawieniem - błąd tu (hedge mode, dźwignia) znaczy, że zlecenie na pewno nie poszło
                await self.ex.prepare(order["symbol"], risk.leverage)
            state = await self.ex.place(order, rules)
        except (BinanceError, RuntimeError) as e:
            code = getattr(e, "code", None)
            await self.table.update_order(order["id"], status="rejected")
            await self._event(account, "order_rejected", f"{order['purpose']} {order['symbol']}: {e}",
                              sig, order, data={"code": code}, now=now)
            return None, e
        except Exception as e:
            logger.warning(f"Binance: zlecenie {order['client_order_id']} - stan nieznany: {type(e).__name__}")
            await self._event(account, "order_unknown",
                              f"{order['purpose']} {order['symbol']}: brak odpowiedzi giełdy ({type(e).__name__}) - "
                              f"sprawdzenie po client order id w następnym przebiegu", sig, order, now=now)
            return None, None
        await self.table.update_order(order["id"], exchange_order_id=state.exchange_order_id)
        await self._event(account, "order_placed", f"{order['purpose']} {order['symbol']} {order['order_type']} "
                          f"{order['qty']:.8g} @ {order['price'] if order['price'] is not None else 'rynek'}",
                          sig, order, data={"exchange_order_id": state.exchange_order_id}, now=now)
        return state, None

    async def _sync(self, account, sig, order, risk, now) -> Tuple[Optional[OrderState], Any]:
        """Stan zlecenia z giełdy. Zwraca (stan, problem): problem to BinanceError (giełda odrzuciła ponowne
        wystawienie) albo "missing" (giełda nie zna zlecenia, które wcześniej przyjęła)."""
        state = await self.ex.get(order)
        if state is None:
            if order.get("exchange_order_id"):
                await self.table.update_order(order["id"], status="cancelled")
                await self._event(account, "reconcile", f"{order['purpose']} {order['client_order_id']}: giełda nie "
                                  f"zna zlecenia, które przyjęła - uznane za anulowane", sig, order, now=now)
                return None, "missing"
            return await self._submit(account, sig, order, risk, now)
        if not order.get("exchange_order_id"):
            await self.table.update_order(order["id"], exchange_order_id=state.exchange_order_id)
            await self._event(account, "reconcile", f"{order['purpose']} {order['client_order_id']}: zlecenie "
                              f"dotarło na giełdę mimo braku odpowiedzi - przyjęte", sig, order, now=now)
        return state, None

    async def _fee(self, symbol: str, state: OrderState, risk: RiskSettings) -> float:
        try:
            fee = await self.ex.commission(symbol, state.fill_order_id)
        except BinanceError:
            fee = None
        if fee is None:   # inna waluta prowizji (np. BNB) - szacunek z ustawień
            fee = abs(state.avg_price * state.filled_qty) * risk.fee_pct / 100.0
        return fee

    # ─────────── "armed" ───────────

    async def update_armed(self, account, sig, risk: RiskSettings, now: int) -> Optional[str]:
        orders = await self.table.orders_for_signal(sig["id"])
        entry = next((o for o in orders if o["purpose"] == "entry" and o["status"] == "open"), None)
        if entry is None:
            return None
        state, problem = await self._sync(account, sig, entry, risk, now)
        if problem:
            why = "zlecenie zniknęło z giełdy" if problem == "missing" else f"odrzucone ({problem})"
            await self.table.set_signal_status(sig["id"], "cancelled", f"wejście: {why}")
            return "cancelled"
        if state is None:
            return None
        setup = await self.setups.get_by_id(sig["setup_id"]) if sig.get("setup_id") else None
        stop = bool(setup and setup["status"] in ("invalidated", "no_entry"))
        if stop and state.status in OPEN:
            state = await self.ex.cancel(entry) or state
        if state.filled_qty > 0 and state.status not in OPEN:
            return await self._entered(account, sig, entry, state, risk, now)
        if state.status in CLOSED_BY_EXCHANGE:
            reason = f"setup {setup['status']}" if stop else f"giełda: {state.status}"
            await self.table.update_order(entry["id"], status=state.status)
            await self.table.set_signal_status(sig["id"], "cancelled", reason)
            await self._event(account, "entry_cancelled", f"Wejście anulowane - {reason}", sig, entry, now=now)
            return "cancelled"
        return None

    async def _entered(self, account, sig, entry, state: OrderState, risk, now) -> str:
        fee = await self._fee(sig["symbol"], state, risk)
        qty, price = state.filled_qty, state.avg_price
        # przebieg przerwany po zapisie pozycji - ponowienie nie tworzy drugiej (zlecenia SL/TP - po client id)
        position = await self.table.position_for_signal(sig["id"]) or await self.table.open_position(
            account_id=account["id"], signal_id=sig["id"], asset_id=sig["asset_id"], symbol=sig["symbol"],
            direction=sig["direction"], qty=qty, entry_price=price, sl=sig["sl"], tp=sig["tp"],
            risk_amount=abs(price - sig["sl"]) * qty, opened_time=state.update_time or now, fees=fee,
        )
        await self.table.fill_order(entry["id"], price, qty, fee, state.update_time or now, position["id"])
        if state.status != "filled":
            await self.table.update_order(entry["id"], status=state.status)
        exit_side = "sell" if sig["direction"] == "long" else "buy"
        for purpose, otype, level in (("stop_loss", "stop_market", sig["sl"]), ("take_profit", TP_ORDER_TYPE, sig["tp"])):
            await self.table.create_order(
                account_id=account["id"], signal_id=sig["id"], position_id=position["id"],
                client_order_id=self.client_id(account["id"], sig["id"], purpose), symbol=sig["symbol"],
                side=exit_side, position_side=sig["direction"], order_type=otype, purpose=purpose, price=level,
                qty=qty, status="open", placed_time=now,
            )
        await self.table.set_signal_status(sig["id"], "entered")
        await self._event(account, "entry_filled", f"{sig['direction'].upper()} {sig['symbol']} {qty:.8g} @ {price:.8g}",
                          sig, entry, position, data={"fee": fee}, now=state.update_time or now)
        await self.update_entered(account, {**sig, "status": "entered"}, risk, now)
        return "filled"

    # ─────────── "entered" ───────────

    async def update_entered(self, account, sig, risk: RiskSettings, now: int) -> Optional[str]:
        position = await self.table.position_for_signal(sig["id"])
        if position is None or position["status"] != "open":
            return None
        orders = await self.table.orders_for_signal(sig["id"])
        protective = sorted((o for o in orders if o["purpose"] in ("stop_loss", "take_profit") and o["status"] == "open"),
                            key=lambda o: o["purpose"] != "stop_loss")
        for o in protective:
            state, problem = await self._sync(account, sig, o, risk, now)
            if state is not None and state.status == "filled":
                return await self._exit_filled(account, sig, position, o, state, protective, risk)
            gone = problem is not None or (state is not None and state.status in CLOSED_BY_EXCHANGE)
            if gone and state is not None:
                await self.table.update_order(o["id"], status=state.status)
            if gone and o["purpose"] == "stop_loss":
                immediate = isinstance(problem, BinanceError) and problem.code == WOULD_TRIGGER_CODE
                return await self._market_close(account, sig, position, risk, now, "sl" if immediate else "protection")
            if gone:
                await self._event(account, "protection_missing", f"TP {sig['symbol']} nie działa na giełdzie - "
                                  f"pozycja chroniona tylko SL", sig, o, position, now=now)
        setup = await self.setups.get_by_id(sig["setup_id"]) if sig.get("setup_id") else None
        if setup and setup["status"] == "expired":
            return await self._market_close(account, sig, position, risk, now, "timeout")
        pos = await self.ex.position(sig["symbol"])
        if pos.mark_price:
            await self.table.mark_position(position["id"], pos.mark_price, now)
        return None

    async def _cancel_rest(self, orders: List[Dict[str, Any]], keep_id: Optional[int] = None) -> None:
        for o in orders:
            if o["id"] == keep_id or o["status"] != "open":
                continue
            state = await self.ex.cancel(o)
            if state is not None and state.status == "filled":
                # wypełniło się przed anulowaniem - odnotowane; wynik i tak liczy rekoncyliacja pozycji
                await self.table.fill_order(o["id"], state.avg_price, state.filled_qty, 0.0, state.update_time)
            else:
                await self.table.update_order(o["id"], status="cancelled")

    async def _exit_filled(self, account, sig, position, order, state: OrderState, protective, risk) -> str:
        await self._cancel_rest(protective, keep_id=order["id"])
        fee = await self._fee(sig["symbol"], state, risk)
        await self.table.fill_order(order["id"], state.avg_price, state.filled_qty, fee, state.update_time)
        reason = "sl" if order["purpose"] == "stop_loss" else "tp"
        await self.engine._finish_close(account, sig, position, state.avg_price, state.update_time, reason, fee, risk,
                                        qty=state.filled_qty)
        return "closed"

    async def _market_close(self, account, sig, position, risk, now: int, reason: str) -> Optional[str]:
        orders = await self.table.orders_for_signal(sig["id"])
        await self._cancel_rest([o for o in orders if o["purpose"] in ("stop_loss", "take_profit")])
        pos = await self.ex.position(sig["symbol"])
        if pos.amount == 0:
            return await self._close_external(account, sig, position, pos.mark_price or position.get("mark_price")
                                              or position["entry_price"], now)
        client_id = self.client_id(account["id"], sig["id"], "close")
        close = next((o for o in orders if o["client_order_id"] == client_id), None) or await self.table.create_order(
            account_id=account["id"], signal_id=sig["id"], position_id=position["id"], client_order_id=client_id,
            symbol=sig["symbol"], side="sell" if sig["direction"] == "long" else "buy", position_side=sig["direction"],
            order_type="market", purpose="close", price=None, qty=abs(pos.amount), status="open", placed_time=now,
        )
        state, problem = await self._sync(account, sig, close, risk, now)
        if state is None or state.status != "filled":
            await self._event(account, "error", f"Zamknięcie {sig['symbol']} ({reason}) niepotwierdzone: "
                              f"{problem or (state.status if state else 'brak odpowiedzi')} - ponowienie w następnym "
                              f"przebiegu", sig, close, position, now=now)
            return None
        fee = await self._fee(sig["symbol"], state, risk)
        await self.table.fill_order(close["id"], state.avg_price, state.filled_qty, fee, state.update_time)
        await self.engine._finish_close(account, sig, position, state.avg_price, state.update_time, reason, fee, risk,
                                        qty=state.filled_qty)
        return "closed"

    async def _close_external(self, account, sig, position, price: float, now: int) -> str:
        await self._event(account, "reconcile", f"{sig['symbol']}: pozycji nie ma na giełdzie (zamknięta poza "
                          f"silnikiem / likwidacja) - zamknięta w bazie po {price:.8g}", sig, position=position, now=now)
        orders = await self.table.orders_for_signal(sig["id"])
        await self._cancel_rest([o for o in orders if o["purpose"] in ("stop_loss", "take_profit")])
        await self.engine._finish_close(account, sig, position, price, now, "external", 0.0, None)
        return "closed"

    # ─────────── rekoncyliacja (każdy przebieg) ───────────

    async def reconcile(self, account, symbol: str, now: int, last_price: Optional[float]) -> Dict[str, int]:
        """Giełda wygrywa: saldo, osierocone zlecenia, pozycja netto na symbolu. Zwraca liczbę rozbieżności."""
        found = {"cash": 0, "orders": 0, "position": 0}
        balance = await self.ex.balance()
        if abs(balance - account["cash"]) > max(0.01, abs(account["cash"]) * 0.001):
            found["cash"] = 1
            await self._event(account, "reconcile", f"Saldo giełdy {balance:.2f} ≠ baza {account['cash']:.2f} - "
                              f"przyjęte saldo giełdy (opłaty, funding, operacje ręczne)",
                              data={"exchange": balance, "db": account["cash"]}, now=now)
        if balance != account["cash"]:
            await self.table.update_account(account["id"], cash=balance, peak_equity=max(account["peak_equity"], balance))

        signals = [s for s in await self.table.open_signals(account["id"]) if s["symbol"] == symbol]
        open_ids = set()
        for s in signals:
            open_ids |= {o["client_order_id"] for o in await self.table.orders_for_signal(s["id"]) if o["status"] == "open"}
        mine = f"{self.prefix}{account['id']}-s"
        for o in await self.ex.open_orders(symbol):
            if o["client_order_id"].startswith(mine) and o["client_order_id"] not in open_ids:
                found["orders"] += 1
                await self.ex.cancel_by_client_id(symbol, o["client_order_id"], o["algo"])
                await self._event(account, "reconcile", f"{symbol}: zlecenie {o['client_order_id']} otwarte na giełdzie, "
                                  f"a w bazie nie - anulowane", now=now)

        rules = await self.ex.rules(symbol)
        tolerance = float(rules.step_size) / 2 if rules else 1e-9
        pos = await self.ex.position(symbol)
        db_positions = [p for p in await self.table.positions(account["id"], status="open") if p["symbol"] == symbol]
        expected = sum(p["qty"] if p["direction"] == "long" else -p["qty"] for p in db_positions)
        if abs(pos.amount - expected) <= tolerance:
            return found
        found["position"] = 1
        if not db_positions:
            await self._event(account, "reconcile", f"{symbol}: na giełdzie pozycja {pos.amount:+.8g}, w bazie brak - "
                              f"pozycja spoza silnika (nie jest zarządzana)", data={"exchange": pos.amount}, now=now)
        elif pos.amount == 0:
            by_signal = {s["id"]: s for s in signals}
            for p in db_positions:
                sig = by_signal.get(p["signal_id"]) or await self.table.get_signal(p["signal_id"])
                await self._close_external(account, sig, p, last_price or p.get("mark_price") or p["entry_price"], now)
        else:
            p = db_positions[0]
            qty = abs(pos.amount)
            await self.table.update_position(p["id"], qty=qty, entry_price=pos.entry_price or p["entry_price"],
                                             risk_amount=abs((pos.entry_price or p["entry_price"]) - p["sl"]) * qty)
            await self._event(account, "reconcile", f"{symbol}: pozycja na giełdzie {pos.amount:+.8g} ≠ baza "
                              f"{expected:+.8g} - przyjęta wartość giełdy", position=p,
                              data={"exchange": pos.amount, "db": expected}, now=now)
        return found
