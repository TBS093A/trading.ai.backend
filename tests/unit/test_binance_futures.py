"""
Unit testy adaptera Binance USDT-M Futures (src/trading/binance_futures.py) i przepływu konta na giełdzie
(src/trading/live.py) - na atrapie HTTP giełdy (sprawdza podpis, trzyma zlecenia, zlecenia algo, pozycję
i saldo), bez sieci i bez prawdziwych kluczy: wystawienie zleceń, wypełnienia, SL/TP, idempotencja po
client order id i rekoncyliacja.
"""

import asyncio
import hashlib
import hmac
import itertools
import os
import unittest
from decimal import Decimal
from unittest import mock
from urllib.parse import parse_qsl, urlsplit

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_trading as trading_api
from src.auth import require_admin, require_auth
from src.trading import binance_futures as bf
from src.trading import risk as rk
from tests.unit.test_trading import H, TARGETS, FakeSetups, FakeTradingTable, flat, k, waiting_setup

KEY, SECRET = "test-key-not-real", "test-secret-not-real"


class FakeBinance:
    """Atrapa /fapi: zlecenia zwykłe i algo po client id, pozycja netto (one-way), saldo portfela."""

    def __init__(self, balance=10_000.0, price=150.0):
        self.balance = balance
        self.price = price
        self.orders, self.algos = {}, {}
        self.position = {"amt": 0.0, "entry": 0.0}
        self.margin_type, self.leverage, self.dual = "cross", 20, False
        self.calls = []
        self.ids = itertools.count(1000)
        self.fail_next = {}        # (method, path) -> wyjątek sieci (zlecenie mimo to przyjęte, gdy accept=True)
        self.reject_next = {}      # (method, path) -> (code, msg)
        self.clock_skew_once = False

    # ─────────── HTTP ───────────

    async def __call__(self, method, url, headers):
        parts = urlsplit(url)
        params = dict(parse_qsl(parts.query))
        path = parts.path
        if "signature" in params:
            query = parts.query.rsplit("&signature=", 1)[0]
            expected = hmac.new(SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
            assert params.pop("signature") == expected, "zły podpis"
            assert headers.get("X-MBX-APIKEY") == KEY
        self.calls.append((method, path, params))
        if self.clock_skew_once and "timestamp" in params:
            self.clock_skew_once = False
            return 400, {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}
        if (method, path) in self.reject_next:
            code, msg = self.reject_next.pop((method, path))
            return 400, {"code": code, "msg": msg}
        failure = self.fail_next.pop((method, path), None)
        result = getattr(self, f"{method.lower()}_{path.strip('/').replace('/', '_')}")(params)
        if failure:
            raise failure
        return result

    def get_fapi_v1_time(self, p):
        return 200, {"serverTime": 1_700_000_000_000}

    def get_fapi_v1_exchangeInfo(self, p):
        return 200, {"symbols": [
            {"symbol": "BTCUSDT", "status": "TRADING", "contractType": "PERPETUAL", "filters": [
                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001", "maxQty": "1000"},
                {"filterType": "MIN_NOTIONAL", "notional": "100"}]},
            {"symbol": "OLDUSDT", "status": "SETTLING", "contractType": "PERPETUAL", "filters": []},
        ]}

    def get_fapi_v1_positionSide_dual(self, p):
        return 200, {"dualSidePosition": self.dual}

    def get_fapi_v2_positionRisk(self, p):
        return 200, [{"symbol": p["symbol"], "positionAmt": str(self.position["amt"]),
                      "entryPrice": str(self.position["entry"]), "markPrice": str(self.price),
                      "unRealizedProfit": "0", "leverage": str(self.leverage), "marginType": self.margin_type,
                      "positionSide": "BOTH"}]

    def post_fapi_v1_marginType(self, p):
        self.margin_type = p["marginType"].lower()
        return 200, {"code": 200, "msg": "success"}

    def post_fapi_v1_leverage(self, p):
        self.leverage = int(p["leverage"])
        return 200, {"leverage": self.leverage, "symbol": p["symbol"]}

    def get_fapi_v2_balance(self, p):
        return 200, [{"asset": "BNB", "balance": "1"}, {"asset": "USDT", "balance": str(self.balance)}]

    def post_fapi_v1_order(self, p):
        cid = p["newClientOrderId"]
        if cid in self.orders and self.orders[cid]["status"] in ("NEW", "PARTIALLY_FILLED"):
            return 400, {"code": -4116, "msg": "ClientOrderId is duplicated."}
        o = {"orderId": next(self.ids), "clientOrderId": cid, "symbol": p["symbol"], "side": p["side"],
             "type": p["type"], "price": p.get("price", "0"), "origQty": p["quantity"], "executedQty": "0",
             "avgPrice": "0", "status": "NEW", "reduceOnly": p.get("reduceOnly") == "true", "updateTime": 1}
        self.orders[cid] = o
        if p["type"] == "MARKET":
            self._execute(o, self.price)
        return 200, dict(o)

    def get_fapi_v1_order(self, p):
        if "orderId" in p:
            o = next((o for o in self.orders.values() if str(o["orderId"]) == p["orderId"]), None)
        else:
            o = self.orders.get(p["origClientOrderId"])
        return (200, dict(o)) if o else (400, {"code": -2013, "msg": "Order does not exist."})

    def delete_fapi_v1_order(self, p):
        o = self.orders.get(p["origClientOrderId"])
        if not o or o["status"] not in ("NEW", "PARTIALLY_FILLED"):
            return 400, {"code": -2011, "msg": "Unknown order sent."}
        o["status"] = "CANCELED"
        return 200, dict(o)

    def get_fapi_v1_openOrders(self, p):
        return 200, [dict(o) for o in self.orders.values() if o["status"] in ("NEW", "PARTIALLY_FILLED")]

    def post_fapi_v1_algoOrder(self, p):
        assert p["algoType"] == "CONDITIONAL"
        cid = p["clientAlgoId"]
        a = {"algoId": next(self.ids), "clientAlgoId": cid, "orderType": p["type"], "symbol": p["symbol"],
             "side": p["side"], "quantity": p["quantity"], "triggerPrice": p["triggerPrice"], "algoStatus": "NEW",
             "reduceOnly": p.get("reduceOnly") == "true", "workingType": p.get("workingType"),
             "actualOrderId": "", "updateTime": 1}
        self.algos[cid] = a
        return 200, dict(a)

    def get_fapi_v1_algoOrder(self, p):
        a = self.algos.get(p["clientAlgoId"])
        return (200, dict(a)) if a else (400, {"code": -2013, "msg": "Order does not exist."})

    def delete_fapi_v1_algoOrder(self, p):
        a = self.algos.get(p["clientAlgoId"])
        if not a or a["algoStatus"] != "NEW":
            return 400, {"code": -2011, "msg": "Unknown order sent."}
        a["algoStatus"] = "CANCELED"
        return 200, {"algoId": a["algoId"], "clientAlgoId": a["clientAlgoId"], "code": "200", "msg": "success"}

    def get_fapi_v1_openAlgoOrders(self, p):
        return 200, [dict(a) for a in self.algos.values() if a["algoStatus"] == "NEW"]

    def get_fapi_v1_userTrades(self, p):
        o = next((o for o in self.orders.values() if str(o["orderId"]) == p["orderId"]), None)
        if not o or float(o["executedQty"]) == 0:
            return 200, []
        fee = float(o["executedQty"]) * float(o["avgPrice"]) * 0.0004
        return 200, [{"orderId": o["orderId"], "commission": f"{fee:.8f}", "commissionAsset": "USDT"}]

    # ─────────── zdarzenia rynku ───────────

    def _execute(self, o, price, qty=None):
        qty = float(o["origQty"]) if qty is None else qty
        signed = qty if o["side"] == "BUY" else -qty
        amt = self.position["amt"]
        if amt == 0 or (amt > 0) == (signed > 0):
            self.position["entry"] = price
        else:   # zamknięcie - wynik do salda
            closed = min(abs(amt), qty)
            self.balance += (price - self.position["entry"]) * closed * (1 if amt > 0 else -1)
        self.balance -= price * qty * 0.0004
        self.position["amt"] = round(amt + signed, 8)
        o.update(executedQty=str(float(o["executedQty"]) + qty), avgPrice=str(price), updateTime=5 * H,
                 status="FILLED" if float(o["executedQty"]) + qty >= float(o["origQty"]) else "PARTIALLY_FILLED")

    def fill(self, cid, price=None, qty=None):
        o = self.orders[cid]
        self._execute(o, float(o["price"]) if price is None else price, qty)

    def trigger(self, cid, price):
        a = self.algos[cid]
        o = {"orderId": next(self.ids), "clientOrderId": f"autoclose-{a['algoId']}", "symbol": a["symbol"],
             "side": a["side"], "type": "MARKET", "origQty": a["quantity"], "executedQty": "0", "avgPrice": "0",
             "status": "NEW", "updateTime": 1}
        self.orders[o["clientOrderId"]] = o
        self._execute(o, price)
        a.update(algoStatus="FINISHED", actualOrderId=str(o["orderId"]))

    def posted(self, path):
        return [p for m, pth, p in self.calls if m == "POST" and pth == path]


class LiveTable(FakeTradingTable):
    async def update_order(self, i, **f):
        self.orders[i].update(f)

    async def update_position(self, i, **f):
        self.positions_[i].update(f)

    async def get_signal(self, i):
        return dict(self.signals[i])

    async def log_event(self, account_id, kind, message, *a, **kw):
        self.events_.append((kind, message))


def make_live(setups, exchange=None, risk=None, cash=10_000.0):
    from src.trading.engine import TradingEngine
    exchange = exchange or FakeBinance(balance=cash)
    account = {"id": 3, "name": "testnet", "exchange": "binance_futures_testnet", "enabled": True,
               "kill_switch": False, "kill_reason": None, "cash": cash, "peak_equity": cash, "starting_equity": cash,
               "base_currency": "USDT", "risk_json": (risk or rk.RiskSettings()).as_dict(), "filters_json": {}}
    table, fake_setups = LiveTable(account), FakeSetups(setups)
    factory = mock.MagicMock()
    factory.get_trading_table.return_value = table
    factory.get_technical_analysis_harmonic_setups_table.return_value = fake_setups
    db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
    client = bf.BinanceFuturesClient(KEY, SECRET, bf.BASE_URLS["binance_futures_testnet"], transport=exchange,
                                     clock=lambda: 1_700_000_000.0)
    engine = TradingEngine(db, strength_fn=lambda row: {"score": 80, "p_win": 0.5}, targets_fn=TARGETS,
                           exchange_factory=lambda name: bf.BinanceFuturesExchange(client))
    return engine, table, fake_setups, exchange


def run(engine, klines):
    return asyncio.run(engine.process_pair(7, "1h", "BTC/USDT", klines))


def order_by(table, purpose):
    return next(o for o in table.orders.values() if o["purpose"] == purpose)


def kinds(table):
    return [e[0] for e in table.events_]


# ─────────────────────────── klient i filtry ───────────────────────────

class TestClient_(unittest.TestCase):
    def test_signed_request_and_secret_never_exposed(self):
        ex = FakeBinance()
        client = bf.BinanceFuturesClient(KEY, SECRET, "https://x", transport=ex, clock=lambda: 1.0)
        self.assertEqual(asyncio.run(bf.BinanceFuturesExchange(client).balance()), 10_000.0)
        self.assertNotIn(SECRET, repr(client))
        self.assertNotIn(KEY, repr(client))
        ex.reject_next[("GET", "/fapi/v2/balance")] = (-2015, "Invalid API-key, IP, or permissions for action.")
        with self.assertRaises(bf.BinanceError) as ctx:
            asyncio.run(client.request("GET", "/fapi/v2/balance"))
        self.assertEqual(ctx.exception.code, -2015)
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertNotIn("signature", str(ctx.exception))

    def test_clock_skew_resyncs_and_retries_once(self):
        ex = FakeBinance()
        ex.clock_skew_once = True
        client = bf.BinanceFuturesClient(KEY, SECRET, "https://x", transport=ex, clock=lambda: 1.0)
        asyncio.run(client.request("GET", "/fapi/v2/balance"))
        self.assertEqual(client.time_offset_ms, 1_700_000_000_000 - 1000)
        self.assertEqual([c[1] for c in ex.calls], ["/fapi/v2/balance", "/fapi/v1/time", "/fapi/v2/balance"])

    def test_missing_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(bf.credentials_configured("binance_futures_testnet"))
            with self.assertRaises(RuntimeError):
                bf.from_env("binance_futures_testnet")
        with self.assertRaises(ValueError):
            bf.BinanceFuturesClient("", "", "https://x")

    def test_symbol_rules(self):
        ex = bf.BinanceFuturesExchange(bf.BinanceFuturesClient(KEY, SECRET, "https://x", transport=FakeBinance()))
        rules = asyncio.run(ex.rules("BTC/USDT"))
        self.assertIsNone(asyncio.run(ex.rules("OLD/USDT")))                      # nie TRADING
        self.assertEqual(rules.price(122.04), Decimal("122.0"))
        self.assertEqual(rules.price(109.99, "down"), Decimal("109.9"))
        self.assertEqual(rules.price(109.91, "up"), Decimal("110.0"))
        self.assertEqual(rules.qty(4.16666), Decimal("4.166"))
        self.assertIn("min notional", rules.check(Decimal("0.5"), Decimal("100")))
        self.assertIn("minQty", rules.check(Decimal("0"), Decimal("100")))
        self.assertIsNone(rules.check(Decimal("1"), Decimal("100")))
        self.assertEqual(bf.futures_symbol("btc/usdt"), "BTCUSDT")


# ─────────────────────────── przepływ konta ───────────────────────────

class TestLiveFlow(unittest.TestCase):
    def arm(self, **kw):
        engine, table, setups, ex = make_live([waiting_setup()], **kw)
        run(engine, flat(11))
        return engine, table, setups, ex

    def test_entry_is_placed_with_client_id_isolated_margin_and_leverage(self):
        engine, table, _, ex = self.arm(risk=rk.RiskSettings(leverage=2))
        sig = next(iter(table.signals.values()))
        entry = order_by(table, "entry")
        self.assertEqual(sig["status"], "armed")
        self.assertEqual(entry["client_order_id"], f"bf3-s{sig['id']}-entry")
        placed = ex.posted("/fapi/v1/order")[0]
        self.assertEqual((placed["type"], placed["side"], placed["timeInForce"], placed["price"], placed["quantity"]),
                         ("LIMIT", "BUY", "GTC", "122", "4.166"))
        self.assertNotIn("reduceOnly", placed)
        self.assertEqual(placed["newClientOrderId"], entry["client_order_id"])
        self.assertEqual(entry["exchange_order_id"], str(ex.orders[entry["client_order_id"]]["orderId"]))
        self.assertEqual((ex.margin_type, ex.leverage), ("isolated", 2))
        run(engine, flat(12))                                         # nic się nie dzieje - bez duplikatu
        self.assertEqual(len(ex.posted("/fapi/v1/order")), 1)

    def test_fill_attaches_sl_and_tp_then_take_profit_closes(self):
        engine, table, _, ex = self.arm()
        sig_id = next(iter(table.signals))
        entry = order_by(table, "entry")
        ex.fill(entry["client_order_id"])
        run(engine, flat(12))
        self.assertEqual(table.signals[sig_id]["status"], "entered")
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["qty"], pos["entry_price"]), (4.166, 122.0))
        self.assertAlmostEqual(pos["fees"], 4.166 * 122 * 0.0004)            # prowizja z userTrades
        sl = ex.algos[f"bf3-s{sig_id}-stop_loss"]
        self.assertEqual((sl["orderType"], sl["side"], sl["triggerPrice"], sl["reduceOnly"], sl["workingType"]),
                         ("STOP_MARKET", "SELL", "110", True, "MARK_PRICE"))
        tp = ex.orders[f"bf3-s{sig_id}-take_profit"]
        self.assertEqual((tp["type"], tp["side"], tp["price"], tp["reduceOnly"]), ("LIMIT", "SELL", "140", True))
        ex.fill(tp["clientOrderId"])
        run(engine, flat(13))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["status"], pos["exit_reason"], pos["exit_price"]), ("closed", "tp", 140.0))
        self.assertEqual(table.signals[sig_id]["status"], "closed")
        self.assertEqual(sl["algoStatus"], "CANCELED")
        self.assertEqual(ex.position["amt"], 0)
        self.assertAlmostEqual(table.accounts[3]["cash"], ex.balance)       # saldo z giełdy
        statuses = {o["purpose"]: o["status"] for o in table.orders.values()}
        self.assertEqual(statuses, {"entry": "filled", "stop_loss": "cancelled", "take_profit": "filled"})

    def test_stop_loss_trigger_closes_and_cancels_tp(self):
        engine, table, _, ex = self.arm()
        sig_id = next(iter(table.signals))
        ex.fill(order_by(table, "entry")["client_order_id"])
        run(engine, flat(12))
        ex.trigger(f"bf3-s{sig_id}-stop_loss", 109.5)
        run(engine, flat(13))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["exit_reason"], pos["exit_price"]), ("sl", 109.5))
        self.assertLess(pos["r_multiple"], -1.0)                              # poślizg + opłaty
        self.assertEqual(ex.orders[f"bf3-s{sig_id}-take_profit"]["status"], "CANCELED")
        self.assertNotIn("reconcile", kinds(table))                           # baza zgodna z giełdą

    def test_partial_fill_then_invalidated_keeps_filled_part(self):
        engine, table, setups, ex = self.arm()
        entry = order_by(table, "entry")
        ex.fill(entry["client_order_id"], qty=2.0)
        setups.rows[1].update(status="invalidated", exit_time=12 * H)
        run(engine, flat(12))
        self.assertEqual(ex.orders[entry["client_order_id"]]["status"], "CANCELED")
        pos = next(iter(table.positions_.values()))
        self.assertEqual(pos["qty"], 2.0)
        self.assertEqual(ex.algos[f"bf3-s{entry['signal_id']}-stop_loss"]["quantity"], "2")

    def test_entry_cancelled_when_setup_invalidated(self):
        engine, table, setups, ex = self.arm()
        setups.rows[1].update(status="invalidated", exit_time=12 * H)
        run(engine, flat(12))
        sig = next(iter(table.signals.values()))
        self.assertEqual((sig["status"], sig["reason"]), ("cancelled", "setup invalidated"))
        self.assertEqual(ex.orders[order_by(table, "entry")["client_order_id"]]["status"], "CANCELED")

    def test_network_error_after_acceptance_is_adopted_not_duplicated(self):
        ex = FakeBinance()
        ex.fail_next[("POST", "/fapi/v1/order")] = TimeoutError("read timeout")
        engine, table, _, ex = make_live([waiting_setup()], exchange=ex)
        run(engine, flat(11))
        entry = order_by(table, "entry")
        self.assertIsNone(entry.get("exchange_order_id"))
        self.assertIn("order_unknown", kinds(table))
        run(engine, flat(12))
        self.assertEqual(len(ex.posted("/fapi/v1/order")), 1)                 # nie wystawione drugi raz
        self.assertIsNotNone(order_by(table, "entry")["exchange_order_id"])
        self.assertIn("reconcile", kinds(table))

    def test_network_error_before_acceptance_is_retried_with_same_client_id(self):
        ex = FakeBinance()
        engine, table, _, ex = make_live([waiting_setup()], exchange=ex)
        with mock.patch.object(ex, "post_fapi_v1_order", side_effect=ConnectionError("reset")):
            run(engine, flat(11))
        run(engine, flat(12))
        entry = order_by(table, "entry")
        self.assertEqual({p["newClientOrderId"] for p in ex.posted("/fapi/v1/order")}, {entry["client_order_id"]})
        self.assertEqual(list(ex.orders), [entry["client_order_id"]])        # jedno zlecenie na giełdzie
        self.assertIsNotNone(entry["exchange_order_id"])

    def test_entry_rejected_by_exchange_cancels_signal(self):
        ex = FakeBinance()
        ex.reject_next[("POST", "/fapi/v1/order")] = (-2019, "Margin is insufficient.")
        engine, table, _, _ = make_live([waiting_setup()], exchange=ex)
        run(engine, flat(11))
        self.assertEqual(order_by(table, "entry")["status"], "rejected")
        sig = next(iter(table.signals.values()))
        self.assertEqual(sig["status"], "cancelled")
        self.assertIn("-2019", sig["reason"])
        run(engine, flat(12))
        self.assertEqual(len(ex.posted("/fapi/v1/order")), 1)                 # jedna próba, bez ponowienia

    def test_filters_reject_too_small_position(self):
        engine, table, _, ex = make_live([waiting_setup()], cash=150.0)      # 0,5% z 150 -> notional < 100
        run(engine, flat(11))
        sig = next(iter(table.signals.values()))
        self.assertEqual(sig["status"], "rejected")
        self.assertIn("min notional", sig["reason"])
        self.assertEqual(ex.posted("/fapi/v1/order"), [])

    def test_unlisted_symbol_is_rejected(self):
        engine, table, _, ex = make_live([waiting_setup()])
        asyncio.run(engine.process_pair(7, "1h", "OLD/USDT", flat(11)))
        self.assertIn("nie jest notowany", next(iter(table.signals.values()))["reason"])

    def test_leverage_caps_position_by_margin(self):
        risk = rk.RiskSettings(risk_per_trade_pct=5.0, max_position_notional_pct=300.0, leverage=1)
        engine, table, _, ex = make_live([waiting_setup()], risk=risk)
        engine.targets_fn = lambda s, entry: (121.0, 140.0, 155.0, "test")   # SL tuż pod wejściem: 500 szt.
        run(engine, flat(11))
        qty = order_by(table, "entry")["qty"]
        self.assertAlmostEqual(qty, 77.868)                                   # 10 000 × 1x × 0,95 / 122
        engine2, table2, _, _ = make_live([waiting_setup()], risk=rk.RiskSettings(
            risk_per_trade_pct=5.0, max_position_notional_pct=300.0, leverage=2))
        engine2.targets_fn = engine.targets_fn
        run(engine2, flat(11))
        self.assertAlmostEqual(order_by(table2, "entry")["qty"], 155.737)

    def test_sl_that_would_trigger_immediately_closes_at_market(self):
        engine, table, _, ex = self.arm()
        ex.fill(order_by(table, "entry")["client_order_id"])
        ex.reject_next[("POST", "/fapi/v1/algoOrder")] = (-2021, "Order would immediately trigger.")
        ex.price = 109.0
        run(engine, flat(12))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["status"], pos["exit_reason"], pos["exit_price"]), ("closed", "sl", 109.0))
        close = ex.posted("/fapi/v1/order")[-1]
        self.assertEqual((close["type"], close["side"], close["reduceOnly"]), ("MARKET", "SELL", "true"))
        self.assertEqual(ex.position["amt"], 0)

    def test_expired_setup_closes_at_market(self):
        engine, table, setups, ex = self.arm()
        ex.fill(order_by(table, "entry")["client_order_id"])
        run(engine, flat(12))
        setups.rows[1].update(status="expired", exit_time=13 * H)
        ex.price = 130.0
        run(engine, flat(14))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["exit_reason"], pos["exit_price"]), ("timeout", 130.0))
        self.assertTrue(all(a["algoStatus"] == "CANCELED" for a in ex.algos.values()))
        self.assertEqual(ex.position["amt"], 0)

    def test_hedge_mode_is_refused(self):
        ex = FakeBinance()
        ex.dual = True
        engine, table, _, _ = make_live([waiting_setup()], exchange=ex)
        run(engine, flat(11))
        self.assertIn("order_rejected", kinds(table))
        self.assertEqual(next(iter(table.signals.values()))["status"], "cancelled")
        self.assertEqual(ex.posted("/fapi/v1/order"), [])

    def test_missing_credentials_logs_error_for_account(self):
        from src.trading.engine import TradingEngine
        engine, table, _, _ = make_live([waiting_setup()])
        engine.exchange_factory = bf.from_env
        with mock.patch.dict(os.environ, {}, clear=True):
            run(engine, flat(11))
        self.assertEqual(table.signals, {})
        self.assertIn("error", kinds(table))
        self.assertTrue(isinstance(engine, TradingEngine))


# ─────────────────────────── rekoncyliacja ───────────────────────────

class TestReconciliation(unittest.TestCase):
    def entered(self):
        engine, table, setups, ex = make_live([waiting_setup()])
        run(engine, flat(11))
        ex.fill(order_by(table, "entry")["client_order_id"])
        run(engine, flat(12))
        table.events_.clear()
        return engine, table, setups, ex

    def test_cash_follows_exchange_balance(self):
        engine, table, _, ex = make_live([])
        ex.balance = 9_900.0                                                 # funding / opłaty
        run(engine, flat(11))
        self.assertEqual(table.accounts[3]["cash"], 9_900.0)
        self.assertIn("reconcile", kinds(table))

    def test_orphan_order_with_our_prefix_is_cancelled(self):
        engine, table, _, ex = make_live([])
        ex.post_fapi_v1_order({"newClientOrderId": "bf3-s99-entry", "symbol": "BTCUSDT", "side": "BUY",
                               "type": "LIMIT", "quantity": "1", "price": "100"})
        ex.post_fapi_v1_order({"newClientOrderId": "manual-1", "symbol": "BTCUSDT", "side": "BUY",
                               "type": "LIMIT", "quantity": "1", "price": "100"})
        ex.post_fapi_v1_algoOrder({"algoType": "CONDITIONAL", "clientAlgoId": "bf3-s98-stop_loss", "type": "STOP_MARKET",
                                   "symbol": "BTCUSDT", "side": "SELL", "quantity": "1", "triggerPrice": "90"})
        run(engine, flat(11))
        self.assertEqual(ex.orders["bf3-s99-entry"]["status"], "CANCELED")
        self.assertEqual(ex.orders["manual-1"]["status"], "NEW")             # nie nasze - nie ruszamy
        self.assertEqual(ex.algos["bf3-s98-stop_loss"]["algoStatus"], "CANCELED")
        self.assertEqual(kinds(table).count("reconcile"), 2)

    def test_position_closed_outside_engine(self):
        engine, table, _, ex = self.entered()
        ex.position["amt"] = 0.0                                             # zamknięta ręcznie / likwidacja
        for a in ex.algos.values():
            a["algoStatus"] = "NEW"
        run(engine, flat(13))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["status"], pos["exit_reason"]), ("closed", "external"))
        self.assertIn("reconcile", kinds(table))
        self.assertTrue(all(a["algoStatus"] == "CANCELED" for a in ex.algos.values()))
        self.assertEqual(next(iter(table.signals.values()))["status"], "closed")

    def test_position_size_mismatch_takes_exchange_value(self):
        engine, table, _, ex = self.entered()
        ex.position["amt"] = 3.0
        run(engine, flat(13))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["status"], pos["qty"]), ("open", 3.0))
        self.assertIn("reconcile", kinds(table))

    def test_untracked_position_is_reported(self):
        engine, table, _, ex = make_live([])
        ex.position.update(amt=-1.5, entry=150.0)
        run(engine, flat(11))
        self.assertTrue(any(kind == "reconcile" and "spoza silnika" in msg for kind, msg in table.events_))

    def test_stop_loss_cancelled_on_exchange_closes_position(self):
        engine, table, _, ex = self.entered()
        sig_id = next(iter(table.signals))
        ex.algos[f"bf3-s{sig_id}-stop_loss"]["algoStatus"] = "CANCELED"     # ktoś zdjął stop
        run(engine, flat(13))
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["status"], pos["exit_reason"]), ("closed", "protection"))
        self.assertEqual(ex.position["amt"], 0)

    def test_disappeared_entry_is_cancelled_with_discrepancy(self):
        engine, table, _, ex = make_live([waiting_setup()])
        run(engine, flat(11))
        ex.orders.clear()
        run(engine, flat(12))
        self.assertEqual(next(iter(table.signals.values()))["status"], "cancelled")
        self.assertIn("reconcile", kinds(table))


# ─────────────────────────── API ───────────────────────────

class TestLiveApi(unittest.TestCase):
    def setUp(self):
        self.table = mock.MagicMock()
        self.table.create_account = mock.AsyncMock(side_effect=lambda *a: {
            "id": 1, "name": a[0], "exchange": a[1], "starting_equity": a[2], "cash": a[2], "peak_equity": a[2],
            "entry_mode": a[3], "risk_json": a[4], "filters_json": a[5], "kill_switch": False})
        self.table.log_event = mock.AsyncMock()
        self.table.stats = mock.AsyncMock(return_value={"closed": 0})
        self.table.positions = mock.AsyncMock(return_value=[])
        factory = mock.MagicMock()
        factory.get_trading_table.return_value = self.table
        p = mock.patch.object(trading_api, "get_db", mock.AsyncMock(
            return_value=mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))))
        p.start()
        self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(trading_api.router, prefix=trading_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        app.dependency_overrides[require_admin] = lambda: None
        self.client = TestClient(app)

    def test_testnet_needs_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.client.post("/trading/accounts", json={"name": "t", "exchange": "binance_futures_testnet"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/trading/accounts", json={"name": "t", "exchange": "binance_futures"})
        self.assertEqual(r.status_code, 422)                                  # live dopiero po testnecie

    def test_testnet_account_starts_from_exchange_balance(self):
        env = {"BINANCE_FUTURES_TESTNET_API_KEY": KEY, "BINANCE_FUTURES_TESTNET_API_SECRET": SECRET}
        ex = FakeBinance(balance=5_000.0)
        real = bf.from_env
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(bf, "from_env", lambda name: real(name, transport=ex)):
            r = self.client.post("/trading/accounts", json={"name": "t", "exchange": "binance_futures_testnet",
                                                             "starting_equity": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.table.create_account.await_args.args[2], 5_000.0)
        self.assertIn("binance_futures_testnet", self.client.get("/trading/risk/fields").json()["exchanges"])


if __name__ == "__main__":
    unittest.main()
