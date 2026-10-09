"""
Unit testy tradingu z sygnałów (src/trading): ustawienia ryzyka i podgląd, giełda symulowana (te same
reguły co symulator setupów) i silnik na atrapie bazy - sygnał -> zlecenie -> pozycja -> wynik, odrzucenia
przez limity, anulowanie przy unieważnionym setupie, kill switch; endpointy - bez bazy i sieci.
"""

import asyncio
import itertools
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_trading as trading_api
from src.auth import require_admin, require_auth
from src.db.postgresql.database_postgresql_factory import DatabasePostgreSQLFactory
from src.trading import paper_exchange as px
from src.trading import risk as rk
from src.trading.engine import TradingEngine, plan_from_setup

H = 3_600_000


def k(o, h, l, c, t):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1.0, "open_time": t}


# ─────────────────────────── ryzyko ───────────────────────────

class TestRisk(unittest.TestCase):
    def test_presets_are_valid_and_described(self):
        for p in rk.RISK_PRESETS:
            rk.validate(p["settings"])
            self.assertTrue(p["description"])
        self.assertEqual({f["key"] for f in rk.RISK_FIELDS}, set(rk.RiskSettings().as_dict()))
        self.assertTrue(all(f["description"] for f in rk.RISK_FIELDS))

    def test_validation(self):
        with self.assertRaises(ValueError):
            rk.validate({"risk_per_trade_pct": 9})
        with self.assertRaises(ValueError):
            rk.validate({"max_open_positions": None})
        self.assertIsNone(rk.validate({"min_strength": None}).min_strength)

    def test_position_size_from_risk_capped_by_notional(self):
        s = rk.RiskSettings(risk_per_trade_pct=1.0, max_position_notional_pct=100.0)
        self.assertAlmostEqual(rk.position_size(10_000, 100.0, 95.0, s)["qty"], 20.0)       # 100 / 5
        tight = rk.position_size(10_000, 100.0, 99.9, s)                                     # 1000 szt. > 100 szt.
        self.assertAlmostEqual(tight["qty"], 100.0)
        self.assertAlmostEqual(tight["risk_pct"], 0.1)
        self.assertEqual(rk.position_size(10_000, 100.0, 100.0, s)["qty"], 0.0)

    def trades(self, rs, gap=H):
        return [{"r": r, "entry_time": i * gap, "exit_time": i * gap + gap // 2, "asset_id": i % 3, "strength": 70,
                 "ev": 0.1} for i, r in enumerate(rs)]

    def test_preview_scales_with_risk_and_counts_streaks(self):
        rs = [2, -1, -1, -1, -1, 2, -1, 2, -1, -1] * 4
        low = rk.preview(self.trades(rs), rk.RiskSettings(risk_per_trade_pct=0.25, min_strength=None,
                                                          daily_loss_limit_pct=20, fee_pct=0), simulations=50)
        high = rk.preview(self.trades(rs), rk.RiskSettings(risk_per_trade_pct=2.0, min_strength=None,
                                                           daily_loss_limit_pct=20, fee_pct=0), simulations=50)
        self.assertGreater(high["max_drawdown_pct"], low["max_drawdown_pct"])
        self.assertEqual(low["worst_losing_streak"], 4)
        self.assertEqual(set(low["bootstrap"]), {"simulations", "return_pct_median", "return_pct_p5",
                                                 "max_drawdown_pct_median", "max_drawdown_pct_p95", "ruin_probability",
                                                 "ruin_drawdown_pct"})

    def test_preview_daily_limit_and_kill_switch(self):
        same_day = self.trades([-1] * 10, gap=60_000)
        r = rk.preview(same_day, rk.RiskSettings(risk_per_trade_pct=1.0, daily_loss_limit_pct=2.0, min_strength=None,
                                                 max_open_positions=50, max_positions_per_asset=50, fee_pct=0),
                       simulations=0)
        self.assertEqual(r["trades_taken"], 2)
        self.assertEqual(r["days_stopped_by_daily_limit"], 1)
        r = rk.preview(self.trades([-1] * 30), rk.RiskSettings(risk_per_trade_pct=2.0, max_drawdown_stop_pct=10.0,
                                                               daily_loss_limit_pct=20, min_strength=None, fee_pct=0),
                       simulations=0)
        self.assertIsNotNone(r["kill_switch_at"])
        self.assertLess(r["trades_taken"], 30)


# ─────────────────────────── giełda symulowana ───────────────────────────

class TestPaperExchange(unittest.TestCase):
    def test_limit_entry_and_gap(self):
        c = [k(105, 106, 101, 104, 0), k(104, 104, 99, 100, H), k(95, 96, 94, 95, 2 * H)]
        self.assertEqual(px.match_limit_entry(c, "long", 100.0), px.Fill(100.0, H, 1))
        self.assertEqual(px.match_limit_entry(c[2:], "long", 100.0).price, 95)            # luka - po otwarciu
        self.assertEqual(px.match_limit_entry(c, "short", 105.5).price, 105.5)

    def test_exit_rules(self):
        c = [k(100, 112, 99, 101, 0), k(101, 111, 100, 110, H), k(110, 111, 89, 90, 2 * H)]
        self.assertEqual(px.match_exit(c, "long", 90, 110, 0)["reason"], "tp")             # nie w świecy wejścia
        both = [k(100, 101, 99, 100, 0), k(100, 111, 89, 95, H)]
        self.assertEqual(px.match_exit(both, "long", 90, 110, 0)["reason"], "sl")          # SL przed TP
        slip = px.match_exit(both, "long", 90, 110, 0, slippage_pct=0.1)["fill"].price
        self.assertAlmostEqual(slip, 90 * 0.999)
        self.assertEqual(px.match_exit(c, "short", 112.5, 95, 0)["reason"], "tp")
        self.assertIsNone(px.match_exit(c[:1], "long", 90, 110, 0))

    def test_pnl_and_fee(self):
        self.assertEqual(px.pnl("long", 100, 110, 2), 20)
        self.assertEqual(px.pnl("short", 100, 110, 2), -20)
        self.assertAlmostEqual(px.fee(100, 2, 0.05), 0.1)


# ─────────────────────────── silnik na atrapie bazy ───────────────────────────

class FakeTradingTable:
    def __init__(self, account):
        self.accounts = {account["id"]: account}
        self.signals, self.orders, self.positions_, self.events_ = {}, {}, {}, []
        self.ids = itertools.count(1)

    async def list_accounts(self, enabled_only=False):
        return [dict(a) for a in self.accounts.values() if a["enabled"] or not enabled_only]

    async def get_account(self, i):
        return dict(self.accounts[i])

    async def update_account(self, i, **f):
        self.accounts[i].update(f)
        return dict(self.accounts[i])

    async def create_signal(self, **s):
        if any(x["account_id"] == s["account_id"] and x["setup_id"] == s["setup_id"] for x in self.signals.values()):
            return None
        s = {**s, "id": next(self.ids)}
        self.signals[s["id"]] = s
        return dict(s)

    async def set_signal_status(self, i, status, reason=None):
        self.signals[i]["status"] = status
        if reason:
            self.signals[i]["reason"] = reason

    async def signaled_setup_ids(self, account_id, ids):
        return {s["setup_id"] for s in self.signals.values() if s["account_id"] == account_id and s["setup_id"] in ids}

    async def open_signals(self, account_id, asset_id=None, interval=None):
        return [dict(s) for s in self.signals.values() if s["account_id"] == account_id
                and s["status"] in ("armed", "entered") and (asset_id is None or s["asset_id"] == asset_id)
                and (interval is None or s["interval"] == interval)]

    async def create_order(self, **o):
        if any(x["client_order_id"] == o["client_order_id"] for x in self.orders.values()):
            return None
        o = {**o, "id": next(self.ids), "filled_qty": 0, "avg_fill_price": None, "fee": 0}
        self.orders[o["id"]] = o
        return dict(o)

    async def fill_order(self, i, price, qty, fee, t, position_id=None):
        self.orders[i].update(status="filled", avg_fill_price=price, filled_qty=qty, fee=fee, filled_time=t)
        if position_id:
            self.orders[i]["position_id"] = position_id

    async def set_order_status(self, i, status):
        self.orders[i]["status"] = status

    async def orders_for_signal(self, signal_id):
        return [dict(o) for o in self.orders.values() if o["signal_id"] == signal_id]

    async def open_position(self, **p):
        p = {**p, "id": next(self.ids), "status": "open", "mark_price": None}
        self.positions_[p["id"]] = p
        return dict(p)

    async def close_position(self, i, exit_price, reason, t, fees, pnl, r):
        self.positions_[i].update(status="closed", exit_price=exit_price, exit_reason=reason, closed_time=t,
                                  fees=fees, pnl=pnl, r_multiple=r)

    async def mark_position(self, i, price, t):
        self.positions_[i].update(mark_price=price, mark_time=t)

    async def position_for_signal(self, signal_id):
        return next((dict(p) for p in self.positions_.values() if p["signal_id"] == signal_id), None)

    async def positions(self, account_id, status=None, limit=200, offset=0):
        return [dict(p) for p in self.positions_.values() if p["account_id"] == account_id
                and (status is None or p["status"] == status)]

    async def realized_pnl_since(self, account_id, since):
        return sum(p["pnl"] for p in self.positions_.values()
                   if p["account_id"] == account_id and p["status"] == "closed" and p["closed_time"] >= since)

    async def snapshot_equity(self, *a):
        self.events_.append(("snapshot", a))

    async def log_event(self, account_id, kind, message, *a, **kw):
        self.events_.append((kind, message))


GARTLEY = {"X": {"time": 0, "price": 100.0}, "A": {"time": H, "price": 200.0},
           "B": {"time": 2 * H, "price": 138.2}, "C": {"time": 3 * H, "price": 169.1}}


def waiting_setup(sid=1, created=10 * H, status="waiting", exit_time=None, asset_id=7):
    return {"id": sid, "asset_id": asset_id, "pattern_type": "gartley", "is_bullish": True, "points_json": GARTLEY,
            "prz_min": 118.0, "prz_max": 122.0, "created_time": created, "status": status, "exit_time": exit_time,
            "spacing": 5, "pre_confluences_json": None}


TARGETS = lambda s, entry: (110.0, 140.0, 155.0, "test")   # SL 110, TP 140 przy wejściu 122


class FakeSetups:
    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}

    async def list(self, asset_id, interval, version, status=None, limit=200):
        return [dict(r) for r in self.rows.values() if r["status"] == status and r["asset_id"] == asset_id]

    async def get_by_id(self, i):
        return dict(self.rows[i]) if i in self.rows else None


def make_engine(setups, risk=None, strength=80, cash=10_000.0):
    account = {"id": 1, "name": "paper", "exchange": "paper", "enabled": True, "kill_switch": False,
               "kill_reason": None, "cash": cash, "peak_equity": cash, "starting_equity": cash,
               "base_currency": "USDT", "risk_json": (risk or rk.RiskSettings(fee_pct=0, slippage_pct=0)).as_dict(),
               "filters_json": {}}
    table, fake_setups = FakeTradingTable(account), FakeSetups(setups)
    factory = mock.MagicMock()
    factory.get_trading_table.return_value = table
    factory.get_technical_analysis_harmonic_setups_table.return_value = fake_setups
    db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
    engine = TradingEngine(db, strength_fn=lambda row: {"score": strength, "p_win": 0.5}, targets_fn=TARGETS)
    return engine, table, fake_setups


def flat(n, start=0):
    return [k(150, 151, 149, 150, (start + i) * H) for i in range(n)]


class TestEngine(unittest.TestCase):
    def run_pair(self, engine, klines):
        return asyncio.run(engine.process_pair(7, "1h", "BTC/USDT", klines))

    def test_plan_uses_near_prz_edge_and_rules(self):
        plan = plan_from_setup(waiting_setup(), TARGETS)
        self.assertEqual((plan["direction"], plan["entry"], plan["sl"], plan["tp"]), ("long", 122.0, 110.0, 140.0))

    def test_full_chain_signal_fill_and_take_profit(self):
        engine, table, _ = make_engine([waiting_setup()])
        self.run_pair(engine, flat(11))                                   # sygnał + zlecenie limit
        sig = next(iter(table.signals.values()))
        self.assertEqual(sig["status"], "armed")
        entry = next(o for o in table.orders.values() if o["purpose"] == "entry")
        self.assertEqual((entry["side"], entry["position_side"], entry["price"]), ("buy", "long", 122.0))
        self.assertAlmostEqual(entry["qty"], 10_000 * 0.005 / 12)          # 0,5% ryzyka / 12 do SL
        later = flat(11) + [k(150, 151, 121, 125, 11 * H), k(125, 141, 124, 140, 12 * H)]
        self.run_pair(engine, later)
        self.assertEqual(table.signals[sig["id"]]["status"], "closed")
        pos = next(iter(table.positions_.values()))
        self.assertEqual((pos["exit_reason"], pos["entry_price"], pos["exit_price"]), ("tp", 122.0, 140.0))
        self.assertAlmostEqual(pos["r_multiple"], 1.5)
        self.assertAlmostEqual(table.accounts[1]["cash"], 10_000 + 50 * 1.5)
        purposes = {o["purpose"]: o["status"] for o in table.orders.values()}
        self.assertEqual(purposes, {"entry": "filled", "stop_loss": "cancelled", "take_profit": "filled"})

    def test_weak_setups_are_skipped_without_a_record(self):
        engine, table, _ = make_engine([waiting_setup()], strength=40)
        self.run_pair(engine, flat(11))
        self.assertEqual(table.signals, {})

    def test_risk_limits_reject_with_reason(self):
        setups = [waiting_setup(1), waiting_setup(2, asset_id=7)]
        engine, table, _ = make_engine(setups, rk.RiskSettings(max_positions_per_asset=1, fee_pct=0))
        self.run_pair(engine, flat(11))
        statuses = sorted(s["status"] for s in table.signals.values())
        self.assertEqual(statuses, ["armed", "rejected"])
        rejected = next(s for s in table.signals.values() if s["status"] == "rejected")
        self.assertIn("limit pozycji na asset", rejected["reason"])

    def test_entry_cancelled_when_setup_is_invalidated(self):
        engine, table, setups = make_engine([waiting_setup()])
        self.run_pair(engine, flat(11))
        setups.rows[1].update(status="invalidated", exit_time=12 * H)
        self.run_pair(engine, flat(14))
        sig = next(iter(table.signals.values()))
        self.assertEqual((sig["status"], sig["reason"]), ("cancelled", "setup invalidated"))

    def test_drawdown_stop_turns_the_kill_switch_on(self):
        risk = rk.RiskSettings(risk_per_trade_pct=5.0, max_drawdown_stop_pct=4.0, fee_pct=0, slippage_pct=0)
        engine, table, _ = make_engine([waiting_setup()], risk)
        self.run_pair(engine, flat(11))
        self.run_pair(engine, flat(11) + [k(150, 151, 121, 125, 11 * H), k(125, 126, 105, 106, 12 * H)])
        self.assertTrue(table.accounts[1]["kill_switch"])
        self.assertIn("kill_switch", [e[0] for e in table.events_])

    def test_tables_are_known_to_the_janitor(self):
        names = DatabasePostgreSQLFactory.registered_table_names()
        for t in ("trading_accounts", "trading_signals", "trading_orders", "trading_positions", "trading_events"):
            self.assertIn(t, names)


# ─────────────────────────── API ───────────────────────────

class TestApi(unittest.TestCase):
    def setUp(self):
        self.table = mock.MagicMock()
        self.table.create_account = mock.AsyncMock(side_effect=lambda *a: {
            "id": 1, "name": a[0], "exchange": a[1], "starting_equity": a[2], "cash": a[2], "peak_equity": a[2],
            "entry_mode": a[3], "risk_json": a[4], "filters_json": a[5], "kill_switch": False})
        self.table.log_event = mock.AsyncMock()
        self.table.stats = mock.AsyncMock(return_value={"closed": 0})
        self.table.positions = mock.AsyncMock(return_value=[])
        self.reports = mock.MagicMock()
        self.reports.get_report = mock.AsyncMock(return_value={"id": 4})
        self.reports.get_trades = mock.AsyncMock(return_value=[
            {"variant": "baseline", "r": r, "entry_time": i * H, "exit_time": i * H + 1, "asset_id": 1,
             "strength": 70, "ev": 0.1} for i, r in enumerate([2, -1, -1] * 10)])
        factory = mock.MagicMock()
        factory.get_trading_table.return_value = self.table
        factory.get_harmonic_variant_reports_table.return_value = self.reports
        p = mock.patch.object(trading_api, "get_db", mock.AsyncMock(
            return_value=mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))))
        p.start()
        self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(trading_api.router, prefix=trading_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        app.dependency_overrides[require_admin] = lambda: None
        self.client = TestClient(app)

    def test_fields_and_presets(self):
        body = self.client.get("/trading/risk/fields").json()
        self.assertEqual([p["key"] for p in body["presets"]], ["conservative", "balanced", "aggressive"])

    def test_create_account_from_preset_with_override(self):
        r = self.client.post("/trading/accounts", json={"name": "paper-1", "preset": "conservative",
                                                         "risk": {"max_open_positions": 4}})
        self.assertEqual(r.status_code, 200)
        risk = self.table.create_account.await_args.args[4]
        self.assertEqual((risk["risk_per_trade_pct"], risk["max_open_positions"]), (0.25, 4))
        self.assertEqual(self.client.post("/trading/accounts", json={"name": "x", "exchange": "binance"}).status_code, 422)
        self.assertEqual(self.client.post("/trading/accounts", json={"name": "x", "risk": {"risk_per_trade_pct": 50}}
                                          ).status_code, 422)

    def test_preview_on_report_trades(self):
        body = self.client.post("/trading/risk/preview", json={"preset": "balanced", "simulations": 20,
                                                               "settings": {"min_strength": None}}).json()
        self.assertEqual((body["report_id"], body["variant"]), (4, "baseline"))
        self.assertEqual(body["trades_taken"] + body["trades_skipped"], 30)
        self.assertIn("ruin_probability", body["bootstrap"])


if __name__ == "__main__":
    unittest.main()
