"""
Unit testy src/harmonic_setups.py - pivoty bez patrzenia w przyszłość, generator setupów i
symulacja wyniku (wejście, SL/TP, limity czasu, warianty konserwatywne). Bez bazy i sieci.
"""

import asyncio
import random
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_harmonics as harmonics_api
from src import harmonic_setups as hs
from src.auth import require_admin, require_auth
from src.harmonic_setups import Pivot, Setup
from src.sync_technical_analysis import TechnicalAnalysis


def k(o, h, l, c, i):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1.0, "open_time": i}


def path(prices):
    """Świece przechodzące przez kolejne ceny (high/low = max/min sąsiednich close)."""
    out, prev = [], prices[0]
    for i, p in enumerate(prices):
        out.append(k(prev, max(prev, p), min(prev, p), p, i))
        prev = p
    return out


def interp(waypoints, step=10):
    prices = []
    for (a, b) in zip(waypoints, waypoints[1:]):
        prices += [a + (b - a) * j / step for j in range(step)]
    return prices + [waypoints[-1]]


def gartley_setup(created=40, span=30):
    # bullish: X 100, A 200, B 138.2, C 169.1 -> D ~121.4 (0.786 XA)
    pts = {"X": Pivot(0, 100.0, False, 5), "A": Pivot(10, 200.0, True, 15),
           "B": Pivot(20, 138.2, False, 25), "C": Pivot(span, 169.1, True, created)}
    return Setup("gartley", True, pts, prz_min=118.0, prz_max=122.0, created_index=created, spacing=5)


def candles_after(created, closes):
    """Świece 0..created płaskie na C (169), potem zadane ceny jako (open, high, low, close)."""
    base = [k(169, 169, 169, 169, i) for i in range(created + 1)]
    return base + [k(o, h, l, c, created + 1 + j) for j, (o, h, l, c) in enumerate(closes)]


FIXED = lambda s, entry: (110.0, 140.0, 155.0, "test")  # SL 110, TP1 140, TP2 155


class TestPivots(unittest.TestCase):
    def test_pivot_is_known_only_after_spacing_candles(self):
        kl = path(interp([100, 150, 110, 160], step=10))
        for p in hs.confirmed_pivots(kl, 3):
            self.assertEqual(p.confirmed_at, p.index + 3)

    def test_setups_known_at_t_do_not_depend_on_later_candles(self):
        # The causality property that matters: replaying history yields exactly the setups a live
        # run at time t would have seen - no repainting, no look-ahead.
        rnd = random.Random(3)
        prices = [100.0]
        for _ in range(500):
            prices.append(max(1.0, prices[-1] * (1 + rnd.uniform(-0.03, 0.03))))
        kl = path(prices)
        full = hs.generate_setups(kl, 5)
        self.assertTrue(full)
        for t in (150, 260, 333, 480):
            live = hs.generate_setups(kl[: t + 1], 5)
            key = lambda s: (s.key, s.created_index)
            self.assertEqual(sorted(map(key, live)), sorted(key(s) for s in full if s.created_index <= t))

    def test_zigzag_alternates(self):
        kl = path(interp([100, 150, 140, 160, 110, 130, 90], step=8))
        piv = hs.confirmed_pivots(kl, 2)
        self.assertTrue(all(a.is_high != b.is_high for a, b in zip(piv, piv[1:])))


class TestGenerator(unittest.TestCase):
    def test_textbook_gartley_structure_produces_a_bullish_setup(self):
        kl = path(interp([110, 100, 200, 138.2, 169.1, 150, 160], step=10))
        setups = hs.generate_all_setups(kl, spacings=(3,))
        gartleys = [s for s in setups if s.pattern == "gartley"]
        self.assertTrue(gartleys)
        g = gartleys[0]
        self.assertTrue(g.is_bullish)
        self.assertEqual(g.points["C"].price, 169.1)
        self.assertLess(g.prz_max, 169.1)
        self.assertGreaterEqual(g.created_index, g.points["C"].index + 3)

    def test_setups_are_deduplicated_across_spacings(self):
        kl = path(interp([110, 100, 200, 138.2, 169.1, 150, 160], step=12))
        setups = hs.generate_all_setups(kl, spacings=(3, 4))
        self.assertEqual(len(setups), len({s.key for s in setups}))


class TestSimulation(unittest.TestCase):
    def test_win_when_tp1_comes_first(self):
        s = gartley_setup()
        kl = candles_after(40, [(160, 161, 150, 151), (150, 151, 121, 125), (125, 141, 124, 140)])
        o = hs.simulate(s, kl, FIXED)
        self.assertEqual(o.status, "win")
        self.assertEqual(o.entry_price, 122.0)       # near PRZ edge
        self.assertAlmostEqual(o.r_multiple, (140 - 122) / (122 - 110), places=4)
        self.assertEqual(o.exit_index, 43)

    def test_loss_when_sl_comes_first(self):
        o = hs.simulate(gartley_setup(), candles_after(40, [(150, 151, 121, 125), (125, 126, 109, 112)]), FIXED)
        self.assertEqual((o.status, o.r_multiple), ("loss", -1.0))

    def test_same_candle_tp_and_sl_counts_as_loss(self):
        o = hs.simulate(gartley_setup(), candles_after(40, [(150, 151, 121, 125), (125, 141, 109, 130)]), FIXED)
        self.assertEqual(o.status, "loss")

    def test_sl_inside_the_entry_candle_is_a_loss(self):
        o = hs.simulate(gartley_setup(), candles_after(40, [(150, 151, 105, 125)]), FIXED)
        self.assertEqual((o.status, o.exit_index), ("loss", 41))

    def test_gap_through_the_zone_fills_at_the_open(self):
        o = hs.simulate(gartley_setup(), candles_after(40, [(119, 125, 118, 124)]), FIXED)
        self.assertEqual(o.entry_price, 119)

    def test_breaking_c_before_entry_invalidates(self):
        o = hs.simulate(gartley_setup(), candles_after(40, [(169, 175, 160, 170)]), FIXED)
        self.assertEqual(o.status, "invalidated")

    def test_no_entry_after_span_candles(self):
        flat = [(160, 161, 159, 160)] * 40
        o = hs.simulate(gartley_setup(created=40, span=30), candles_after(40, flat), FIXED)
        self.assertEqual((o.status, o.exit_index), ("no_entry", 71))  # deadline 40 + 30

    def test_expired_after_twice_the_span_in_trade(self):
        drift = [(150, 151, 121, 125)] + [(126, 130, 120, 128)] * 70
        o = hs.simulate(gartley_setup(span=30), candles_after(40, drift), FIXED)
        self.assertEqual(o.status, "expired")
        self.assertEqual(o.exit_index, 41 + 60)
        self.assertAlmostEqual(o.r_multiple, (128 - 122) / 12, places=4)

    def test_open_when_data_runs_out(self):
        o = hs.simulate(gartley_setup(), candles_after(40, [(150, 151, 121, 125)]), FIXED)
        self.assertEqual(o.status, "open")
        self.assertIsNone(o.r_multiple)

    def test_tp2_reached_is_recorded(self):
        kl = candles_after(40, [(150, 151, 121, 125), (125, 141, 124, 140), (140, 156, 139, 155)])
        o = hs.simulate(gartley_setup(), kl, FIXED)
        self.assertEqual(o.status, "win")
        self.assertTrue(o.tp2_reached)

    def test_invalid_targets_fall_back(self):
        wrong_side = lambda s, entry: (entry + 5, entry + 10, entry + 20, "app")  # SL above a long entry
        o = hs.simulate(gartley_setup(), candles_after(40, [(150, 151, 121, 125)]), wrong_side)
        self.assertEqual(o.targets_source, "fallback")
        self.assertLess(o.sl, o.entry_price)
        self.assertGreater(o.tp1, o.entry_price)

    def test_bearish_mirror(self):
        pts = {"X": Pivot(0, 200.0, True, 5), "A": Pivot(10, 100.0, False, 15),
               "B": Pivot(20, 161.8, True, 25), "C": Pivot(30, 130.9, False, 40)}
        s = Setup("gartley", False, pts, prz_min=178.0, prz_max=182.0, created_index=40, spacing=5)
        base = [k(131, 131, 131, 131, i) for i in range(41)]
        kl = base + [k(140, 179, 139, 175, 41), k(175, 176, 159, 160, 42)]
        o = hs.simulate(s, kl, lambda s, e: (190.0, 160.0, 145.0, "test"))
        self.assertEqual((o.status, o.entry_price), ("win", 178.0))


def random_walk(n=1500, seed=3):
    rnd = random.Random(seed)
    prices = [100.0]
    for _ in range(n - 1):
        prices.append(max(1.0, prices[-1] * (1 + rnd.uniform(-0.03, 0.03))))
    kl = path(prices)
    for i, x in enumerate(kl):
        x["open_time"] = 1_000_000 + i * 3_600_000
    return kl


class TestEvaluate(unittest.TestCase):
    def test_rows_use_candle_times_and_skip_already_final_setups(self):
        kl = random_walk()
        rows = hs.evaluate(kl, 7, "1h", "replay")
        self.assertTrue(rows)
        r = rows[0]
        self.assertEqual((r["asset_id"], r["interval"], r["source"], r["params_version"]),
                         (7, "1h", "replay", hs.params_version()))
        times = {x["open_time"] for x in kl}
        self.assertTrue({r["x_time"], r["a_time"], r["b_time"], r["c_time"], r["created_time"]} <= times)
        self.assertLess(r["c_time"], r["created_time"])
        final = {(x["pattern_type"], x["x_time"], x["a_time"], x["b_time"], x["c_time"])
                 for x in rows if x["status"] in hs.FINAL_STATUSES}
        again = hs.evaluate(kl, 7, "1h", "replay", skip_keys=final)
        self.assertEqual(len(again), len(rows) - len(final))
        self.assertTrue(all(x["status"] not in hs.FINAL_STATUSES for x in again))

    def test_confluences_see_candles_only_up_to_the_entry(self):
        seen = []

        def conf(setup, outcome, klines):
            seen.append(len(klines) == outcome.entry_index + 1)
            return {"total_score": 1, "confluences": []}

        rows = hs.evaluate(random_walk(), 1, "1h", "replay", confluences_fn=conf)
        entered = [r for r in rows if r["entry_time"] is not None]
        self.assertTrue(entered and all(seen) and len(seen) == len(entered))
        self.assertTrue(all(r["confluences_json"] for r in entered))
        self.assertTrue(all(r["confluences_json"] is None for r in rows if r["entry_time"] is None))


class TestStats(unittest.TestCase):
    def test_wilson_interval(self):
        self.assertEqual(hs.wilson_interval(0, 0), (None, None))
        lo, hi = hs.wilson_interval(20, 100)
        self.assertAlmostEqual(lo, 0.1333, places=3)
        self.assertAlmostEqual(hi, 0.2888, places=3)
        lo, hi = hs.wilson_interval(1, 3)  # mała próbka -> szeroki przedział
        self.assertLess(lo, 0.07)
        self.assertGreater(hi, 0.79)

    def test_stats_row(self):
        row = hs.stats_row({"pattern_type": "gartley", "setups": 20, "wins": 3, "losses": 6, "expired": 1,
                            "no_entry": 4, "invalidated": 5, "pending": 1, "tp2_reached": 2,
                            "avg_r": -0.12345, "avg_mfe_r": 1.0, "avg_mae_r": None})
        self.assertEqual(row["trades"], 10)
        self.assertEqual(row["win_rate"], 0.3)
        self.assertEqual(row["tp2_rate"], 0.2)
        self.assertEqual(row["entry_rate"], round(10 / 19, 4))
        self.assertEqual(row["avg_r"], -0.1235)
        self.assertEqual(len(row["win_rate_ci95"]), 2)
        empty = hs.stats_row({"setups": 2, "wins": 0, "losses": 0, "expired": 0, "no_entry": 2, "invalidated": 0})
        self.assertIsNone(empty["win_rate"])
        self.assertEqual(empty["entry_rate"], 0.0)


class TestWorker(unittest.TestCase):
    def make(self, oldest_unresolved=None, final_keys=()):
        H = 3_600_000
        all_klines = random_walk(4000)
        table = mock.MagicMock()
        table.get_oldest_unresolved_x_time = mock.AsyncMock(return_value=oldest_unresolved)
        table.get_final_keys = mock.AsyncMock(return_value=set(final_keys))
        table.upsert_many = mock.AsyncMock(side_effect=lambda rows: len(rows))
        table.get_unresolved_statuses = mock.AsyncMock(return_value={})
        factory = mock.MagicMock()
        factory.get_harmonic_setup_events_table.return_value.add_many = mock.AsyncMock(side_effect=len)
        factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(return_value={"asset": "BTC", "quote": "USDT"})
        factory.get_asset_exchanges_table.return_value.get_by_asset_id = mock.AsyncMock(
            return_value=[{"exchange_name": "Binance"}])
        factory.get_technical_analysis_harmonic_setups_table.return_value = table
        api = mock.MagicMock()
        api._get_klines.side_effect = lambda **kw: [k for k in all_klines
                                                    if kw["start_time"] <= k["open_time"] <= kw["end_time"]][-kw["limit"]:]
        ta = TechnicalAnalysis.__new__(TechnicalAnalysis)
        ta.db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
        ta.api_facade = mock.MagicMock()
        ta.api_facade.get_fabric.return_value.get_binance_api.return_value = api
        now = all_klines[-1]["open_time"] + H + 10  # ostatnia świeca właśnie się zamknęła
        return ta, table, all_klines, now

    def run_track(self, ta, now, **kw):
        with mock.patch("src.analysis_services.setup_tracking_service.datetime") as dt, \
                mock.patch.object(hs, "app_targets", hs.fallback_targets), \
                mock.patch("src.analysis_services.setup_tracking_service.ConfluenceDetector.detect", return_value=None):
            dt.now.return_value.timestamp.return_value = now / 1000
            return asyncio.run(ta._track_harmonic_setups(5, "1h", source="live", **kw))

    def test_uses_the_last_closed_candles_and_saves_rows(self):
        ta, table, kl, now = self.make()
        res = self.run_track(ta, now, candles=600)
        self.assertEqual(res["klines"], 600)
        rows = table.upsert_many.await_args.args[0]
        self.assertEqual(res["saved"], len(rows))
        self.assertTrue(all(r["source"] == "live" and r["asset_id"] == 5 for r in rows))
        self.assertTrue(all(r["c_time"] >= kl[-600]["open_time"] for r in rows))

    def test_live_run_records_status_changes_as_events(self):
        ta, table, kl, now = self.make()
        first = self.run_track(ta, now, candles=600)
        rows = table.upsert_many.await_args.args[0]
        unresolved = [r for r in rows if r["status"] in ("waiting", "open")]
        self.assertTrue(unresolved)
        # Ten sam przebieg, ale baza "pamięta" otwarte setupy jako waiting -> zmiany open/final to zdarzenia.
        table.get_unresolved_statuses.return_value = {
            (r["pattern_type"], r["x_time"], r["a_time"], r["b_time"], r["c_time"]): "waiting" for r in rows
        }
        second = self.run_track(ta, now, candles=600)
        changed = [r for r in rows if r["status"] != "waiting"]
        self.assertEqual(second["events"], len(changed))
        events = ta.db.get_factory().get_harmonic_setup_events_table().add_many.await_args.args[0]
        self.assertTrue(all(e["from_status"] == "waiting" for e in events))
        self.assertLessEqual(first["events"], len(rows))

    def test_setup_confluences_include_the_sidebar_post_processing(self):
        ta, table, kl, now = self.make()
        ta.db.get_factory().get_technical_analysis_harmonic_patterns_table.return_value.get_by_asset_id = \
            mock.AsyncMock(return_value=[])
        seen = []

        def fake_post(target, interval, patterns, klines):
            seen.append((target["d_point_timestamp"], sorted(klines)))
            return [{"type": "fib_cluster", "confidence": 0.5}]

        with mock.patch("src.analysis_services.setup_tracking_service.post_processing_entries", fake_post), \
                mock.patch("src.analysis_services.setup_tracking_service.ConfluenceDetector.detect",
                           return_value={"total_score": 1, "confluences": [{"type": "doji"}]}), \
                mock.patch("src.analysis_services.setup_tracking_service.datetime") as dt, \
                mock.patch.object(hs, "app_targets", hs.fallback_targets):
            dt.now.return_value.timestamp.return_value = now / 1000
            asyncio.run(ta._track_harmonic_setups(5, "1h", 600, "replay"))
        rows = table.upsert_many.await_args.args[0]
        entered = [r for r in rows if r["entry_time"] is not None]
        self.assertTrue(entered)
        self.assertEqual({tuple(c["type"] for c in r["confluences_json"]["confluences"]) for r in entered},
                         {("doji", "fib_cluster")})
        self.assertEqual(entered[0]["confluences_json"]["total_score"], 2)
        # D = świeca wejścia; wyższe TF dla 1h: 4h, 1d, 3d
        self.assertEqual(seen[0][1], ["1d", "3d", "4h"])
        self.assertIn(seen[0][0], {r["entry_time"] for r in entered})

    def test_replay_records_no_events(self):
        ta, table, kl, now = self.make()
        with mock.patch("src.analysis_services.setup_tracking_service.datetime") as dt, \
                mock.patch.object(hs, "app_targets", hs.fallback_targets), \
                mock.patch("src.analysis_services.setup_tracking_service.ConfluenceDetector.detect", return_value=None):
            dt.now.return_value.timestamp.return_value = now / 1000
            res = asyncio.run(ta._track_harmonic_setups(5, "1h", 600, "replay"))
        self.assertEqual(res["events"], 0)
        table.get_unresolved_statuses.assert_not_awaited()

    def test_extends_history_to_cover_the_oldest_unresolved_setup(self):
        ta, table, kl, now = self.make(oldest_unresolved=kl_time(2000))
        res = self.run_track(ta, now, candles=600)
        self.assertGreater(res["klines"], 4000 - 2000)
        since = table.get_final_keys.await_args.args[3]
        self.assertLess(since, kl_time(2000))


def kl_time(i):
    return 1_000_000 + i * 3_600_000


class TestSetupEndpoints(unittest.TestCase):
    def setUp(self):
        self.table = mock.MagicMock()
        self.table.stats = mock.AsyncMock(return_value=[
            {"pattern_type": "gartley", "setups": 30, "wins": 6, "losses": 12, "expired": 2, "no_entry": 5,
             "invalidated": 5, "pending": 0, "tp2_reached": 3, "avg_r": -0.1, "avg_mfe_r": 1.2, "avg_mae_r": 0.8},
            {"pattern_type": "crab", "setups": 3, "wins": 1, "losses": 0, "expired": 0, "no_entry": 1,
             "invalidated": 1, "pending": 0, "tp2_reached": 0, "avg_r": 1.5, "avg_mfe_r": 2.0, "avg_mae_r": 0.1},
        ])
        self.table.list = mock.AsyncMock(return_value=[{"id": 1}])
        factory = mock.MagicMock()
        factory.get_technical_analysis_harmonic_setups_table.return_value = self.table
        factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(side_effect=lambda i: {"id": i} if i < 100 else None)
        db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
        self.enqueue = mock.MagicMock(side_effect=lambda *a: f"task-{a[0]}-{a[1]}")
        for p in [mock.patch.object(harmonics_api, "get_db", mock.AsyncMock(return_value=db)),
                  mock.patch.object(harmonics_api, "_enqueue_setups", self.enqueue)]:
            p.start()
            self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(harmonics_api.router, prefix=harmonics_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        app.dependency_overrides[require_admin] = lambda: None
        self.client = TestClient(app)

    def test_stats_adds_win_rate_and_filters_small_groups(self):
        r = self.client.get("/harmonics/stats", params={"group_by": "pattern_type", "interval": "1h", "min_trades": 5})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual([g["pattern_type"] for g in body["groups"]], ["gartley"])
        self.assertEqual(body["groups"][0]["win_rate"], 0.3)
        self.assertEqual(body["filters"], {"interval": "1h"})
        args = self.table.stats.await_args.args
        self.assertEqual((args[0], args[1]), (hs.params_version(), ["pattern_type"]))

    def test_stats_rejects_unknown_grouping(self):
        self.assertEqual(self.client.get("/harmonics/stats", params={"group_by": "x; drop"}).status_code, 422)

    def test_setups_list_is_not_shadowed_by_the_range_route(self):
        r = self.client.get("/harmonics/setups", params={"asset_id": 1, "interval": "1h", "status": "win"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["setups"], [{"id": 1, "strength": None}])

    def test_backfill_enqueues_one_task_per_asset_and_interval(self):
        r = self.client.post("/harmonics/setups/backfill", json={"asset_ids": [1, 2], "intervals": ["1h", "4h"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()["tasks"]), 4)
        self.enqueue.assert_any_call(2, "4h", 5000)

    def test_backfill_validation(self):
        self.assertEqual(self.client.post("/harmonics/setups/backfill",
                                          json={"asset_ids": [1], "intervals": ["7x"]}).status_code, 422)
        self.assertEqual(self.client.post("/harmonics/setups/backfill",
                                          json={"asset_ids": [1, 500]}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
