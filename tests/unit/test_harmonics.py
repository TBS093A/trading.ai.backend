"""
Unit testy formacji harmonicznych na żądanie: src/harmonic_scan.py (pokrycie okien, zakresy,
stronicowanie świec), src/harmonic_validation.py (ręczna walidacja XABCD),
TechnicalAnalysis.scan_harmonic_windows (worker) i src/controller_rest_domain_harmonics.py -
bez bazy, sieci i credentiali (PRE-MERGE gate).
"""

import asyncio
import random
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_harmonics as harmonics_api
from src import harmonic_scan as hs
from src.auth import require_auth
from src.harmonic_validation import Point, ValidationError, compute_ratios, validate_xabcd
from src.sync_technical_analysis import TechnicalAnalysis

H = 3_600_000  # 1h w ms
SPAN = hs.max_pattern_span_ms("1h")


def covered_by_one_window(pattern, windows):
    return any(ws <= pattern[0] and pattern[1] <= we for ws, we in windows)


class TestMissingWindows(unittest.TestCase):
    def test_nothing_scanned_means_the_whole_request(self):
        self.assertEqual(hs.missing_windows((0, 100 * H), [], SPAN), [(0, 100 * H)])

    def test_request_inside_one_scanned_window_is_complete(self):
        self.assertEqual(hs.missing_windows((100 * H, 200 * H), [(0, 2000 * H)], SPAN), [])

    def test_windows_overlapping_by_span_form_one_chain(self):
        scanned = [(0, 1000 * H), (500 * H, 2000 * H)]  # zakładka 500 świec = span
        self.assertEqual(hs.missing_windows((0, 2000 * H), scanned, SPAN), [])

    def test_small_overlap_rescans_the_seam_with_span_margin(self):
        scanned = [(0, 1000 * H), (900 * H, 2000 * H)]  # zakładka 100 świec < span
        self.assertEqual(hs.missing_windows((0, 2000 * H), scanned, SPAN), [(500 * H, 1400 * H)])

    def test_gap_in_the_middle_is_rescanned_with_margins(self):
        scanned = [(0, 1000 * H), (1100 * H, 3000 * H)]
        self.assertEqual(hs.missing_windows((0, 3000 * H), scanned, SPAN), [(500 * H, 1600 * H)])

    def test_gaps_at_both_ends_are_clipped_to_the_request(self):
        scanned = [(1000 * H, 1500 * H)]
        self.assertEqual(
            hs.missing_windows((800 * H, 1800 * H), scanned, SPAN),
            [(800 * H, 1800 * H)],  # oba marginesy zlewają się w jedno okno
        )

    def test_after_scanning_the_answer_every_short_pattern_fits_one_window(self):
        rnd = random.Random(7)
        for _ in range(300):
            request = (rnd.randint(0, 500) * H, rnd.randint(1000, 3000) * H)
            scanned = []
            for _ in range(rnd.randint(0, 4)):
                s = rnd.randint(0, 3000)
                scanned.append((s * H, (s + rnd.randint(50, 1500)) * H))
            new = hs.missing_windows(request, scanned, SPAN)
            all_windows = scanned + new
            self.assertEqual(hs.missing_windows(request, all_windows, SPAN), [], (request, scanned, new))
            for _ in range(30):
                length = rnd.randint(1, 500) * H
                start = rnd.randint(request[0] // H, (request[1] - length) // H) * H if request[1] - length >= request[0] else request[0]
                pattern = (start, min(start + length, request[1]))
                self.assertTrue(covered_by_one_window(pattern, all_windows), (request, scanned, new, pattern))


class TestRangesAndHelpers(unittest.TestCase):
    now = 10_000 * H + 123

    def test_default_range_is_last_500_closed_candles(self):
        start, end = hs.resolve_range("1h", None, None, self.now)
        self.assertEqual(end, 9999 * H)  # open_time of the last closed candle
        self.assertEqual(end - start, 499 * H)

    def test_range_is_stable_within_a_candle(self):
        # Regression: the end used to move every millisecond, so every request found a tiny
        # uncovered tail and started a new scan.
        a = hs.resolve_range("4h", None, None, 10_000 * H + 1)
        b = hs.resolve_range("4h", None, None, 10_000 * H + 3 * H)
        self.assertEqual(a, b)
        self.assertEqual(a[1] % (4 * H), 0)

    def test_weekly_and_monthly_alignment(self):
        from datetime import datetime, timezone
        ms = lambda *d: int(datetime(*d, tzinfo=timezone.utc).timestamp() * 1000)
        wed = ms(2026, 10, 7, 13, 30)
        self.assertEqual(hs.align_down("1w", wed), ms(2026, 10, 5))  # Monday
        self.assertEqual(hs.last_closed_open_time("1w", wed), ms(2026, 9, 28))
        self.assertEqual(hs.last_closed_open_time("1M", wed), ms(2026, 9, 1))
        self.assertEqual(hs.last_closed_open_time("1M", ms(2026, 3, 31, 23)), ms(2026, 2, 1))
        self.assertEqual(hs.last_closed_open_time("1d", wed), ms(2026, 10, 6))

    def test_end_is_clipped_to_the_last_closed_candle(self):
        _, end = hs.resolve_range("1h", 9000 * H, self.now + 10 * H, self.now)
        self.assertEqual(end, 9999 * H)

    def test_invalid_ranges(self):
        for args in [("1h", 9000 * H, 8000 * H), ("1h", 1000 * H, 9000 * H), ("7h", None, None)]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    hs.resolve_range(*args, self.now)

    def test_patterns_inside_uses_first_and_last_point(self):
        xabcd = {"x_point_timestamp": 10, "a_point_timestamp": 20, "b_point_timestamp": 30,
                 "c_point_timestamp": 40, "d_point_timestamp": 50}
        abcd = {"x_point_timestamp": None, "a_point_timestamp": 5, "b_point_timestamp": 6,
                "c_point_timestamp": 7, "d_point_timestamp": 60}
        self.assertEqual(hs.patterns_inside([xabcd, abcd], (10, 50)), [xabcd])
        self.assertEqual(hs.patterns_inside([xabcd, abcd], (0, 60)), [xabcd, abcd])

    def test_pick_exchange_follows_klines_priority(self):
        self.assertEqual(hs.pick_exchange(["Yahoo Finance", "Binance"]), "BINANCE")
        self.assertEqual(hs.pick_exchange(["YAHOO"]), "YAHOO")
        self.assertIsNone(hs.pick_exchange(["KUCOIN", None]))

    def test_params_hash_changes_with_engine_settings(self):
        self.assertEqual(hs.params_hash(), hs.params_hash(dict(hs.SCAN_PARAMS)))
        self.assertNotEqual(hs.params_hash(), hs.params_hash({**hs.SCAN_PARAMS, "peak_spacing": [3, 5]}))

    def test_fetch_klines_range_pages_backwards_without_gaps(self):
        candles = [{"open_time": t * H} for t in range(2500)]
        calls = []

        def get_klines(base_currency, quote_currency, interval, start_time, end_time, limit):
            calls.append(end_time)
            page = [c for c in candles if start_time <= c["open_time"] <= end_time]
            return page[-limit:]

        result = hs.fetch_klines_range(get_klines, "BTC", "USDT", "1h", 100 * H, 2400 * H)
        self.assertEqual([c["open_time"] for c in result], [t * H for t in range(100, 2401)])
        self.assertEqual(len(calls), 3)

    def test_fetch_klines_range_handles_exchanges_returning_the_oldest_page(self):
        # Regression: Binance with startTime + endTime returns the OLDEST `limit` candles, so a
        # backwards-only pager stopped after the first page (1000 of 5000 requested candles).
        candles = [{"open_time": t * H} for t in range(6000)]

        def get_klines(base_currency, quote_currency, interval, start_time, end_time, limit):
            return [c for c in candles if start_time <= c["open_time"] <= end_time][:limit]

        result = hs.fetch_klines_range(get_klines, "BTC", "USDT", "1h", 500 * H, 5499 * H)
        self.assertEqual([c["open_time"] for c in result], [t * H for t in range(500, 5500)])

    def test_fetch_klines_range_stops_at_the_request_limit(self):
        get_klines = mock.MagicMock(side_effect=lambda **kw: [{"open_time": kw["start_time"] + i}
                                                              for i in range(hs.KLINES_PAGE)])
        hs.fetch_klines_range(get_klines, "BTC", "USDT", "1h", 0, 10 ** 12)
        self.assertEqual(get_klines.call_count, hs.MAX_KLINES_REQUESTS)


def gartley(bullish=True):
    # XA = 100, B = 0.618 XA, D = 0.786 XA, BCD ~ 1.54
    sign = 1 if bullish else -1
    base = 1000.0
    prices = {"X": base, "A": base + sign * 100, "B": base + sign * 38.2, "C": base + sign * 69.1, "D": base + sign * 21.4}
    return {n: Point(time=i * H, price=p) for i, (n, p) in enumerate(prices.items())}


class TestManualValidation(unittest.TestCase):
    def test_textbook_gartley_matches_both_directions(self):
        for bullish in (True, False):
            with self.subTest(bullish=bullish):
                result = validate_xabcd(gartley(bullish))
                self.assertEqual(result["direction"], "bullish" if bullish else "bearish")
                self.assertIn("gartley", [m["pattern"] for m in result["matches"]])
                best = result["candidates"][0]
                self.assertTrue(best["match"])
                self.assertEqual(best["deviation"], 0)
                g = next(m for m in result["matches"] if m["pattern"] == "gartley")
                d = gartley(bullish)["D"].price
                self.assertLessEqual(g["prz"]["min"], d)
                self.assertGreaterEqual(g["prz"]["max"], d)
                t1 = g["targets"]["T1_0.382"]
                self.assertEqual(t1 > d, bullish)  # cel po D w kierunku odwrócenia

    def test_ratios(self):
        r = compute_ratios(gartley())
        self.assertAlmostEqual(r["XAB"], 0.618, places=3)
        self.assertAlmostEqual(r["XAD"], 0.786, places=3)

    def test_without_d_returns_zones_where_d_would_complete(self):
        points = gartley()
        d = points.pop("D").price
        result = validate_xabcd(points)
        self.assertFalse(result["complete"])
        g = next(c for c in result["candidates"] if c["pattern"] == "gartley")
        self.assertTrue(g["match"])  # XAB pasuje
        self.assertLessEqual(g["prz"]["min"], d)
        self.assertGreaterEqual(g["prz"]["max"], d)
        self.assertNotIn("targets", g)

    def test_broken_inputs_are_rejected(self):
        p = gartley()
        cases = {
            "missing point": {k: v for k, v in p.items() if k != "B"},
            "time order": {**p, "C": Point(time=p["B"].time, price=p["C"].price)},
            "not a zigzag": {**p, "B": Point(time=p["B"].time, price=p["A"].price + 10)},
        }
        for name, pts in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValidationError):
                    validate_xabcd(pts)
        with self.assertRaises(ValidationError):
            validate_xabcd(p, fib_tolerance=0.5)


def kline(t):
    return {"open_time": t, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.0, "volume": 1.0, "close_time": t + H - 1}


class TestWorkerScan(unittest.TestCase):
    def test_saves_patterns_inside_each_window_and_records_every_window(self):
        windows_table = mock.MagicMock()
        windows_table.create = mock.AsyncMock(return_value=1)
        factory = mock.MagicMock()
        factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(return_value={"asset": "BTC", "quote": "USDT"})
        factory.get_asset_exchanges_table.return_value.get_by_asset_id = mock.AsyncMock(
            return_value=[{"exchange_name": "Binance"}])
        factory.get_technical_analysis_harmonic_scan_windows_table.return_value = windows_table

        api = mock.MagicMock()
        api._get_klines.side_effect = lambda **kw: [kline(t * H) for t in range(0, 3000)
                                                    if kw["start_time"] <= t * H <= kw["end_time"]][-kw["limit"]:]

        inside = {"x_point_timestamp": 1100 * H, "a_point_timestamp": 1110 * H, "b_point_timestamp": 1120 * H,
                  "c_point_timestamp": 1130 * H, "d_point_timestamp": 1140 * H}
        crossing = {**inside, "x_point_timestamp": 990 * H}
        hp = mock.MagicMock()
        hp.get_calculated_objects.side_effect = [[inside, crossing], []]

        ta = TechnicalAnalysis.__new__(TechnicalAnalysis)
        ta.db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
        ta.api_facade = mock.MagicMock()
        ta.api_facade.get_fabric.return_value.get_binance_api.return_value = api
        ta.technical_analysis_factory = mock.MagicMock(get_harmonic_patterns=mock.MagicMock(return_value=hp))
        ta.technical_analysis_facade = mock.MagicMock()
        ta.save_harmonic_patterns_to_database = mock.AsyncMock()
        ta._update_fib_cluster_confluences = mock.AsyncMock()

        with mock.patch("src.analysis_services.harmonic_scan_service.datetime") as dt:
            dt.now.return_value.timestamp.return_value = 2900 * H / 1000
            results = asyncio.run(ta.scan_harmonic_windows(7, "1h", [(1000 * H, 1500 * H), (2000 * H, 2200 * H)]))

        self.assertEqual([r["patterns"] for r in results], [1, 0])
        ta.save_harmonic_patterns_to_database.assert_awaited_once_with([inside])
        recorded = [(c.kwargs["start_time"], c.kwargs["end_time"], c.kwargs["patterns_found"])
                    for c in windows_table.create.await_args_list]
        self.assertEqual(recorded, [(1000 * H, 1500 * H, 1), (2000 * H, 2200 * H, 0)])
        first_call = ta.technical_analysis_facade.calculate.call_args_list[0].kwargs
        opens = [k["open_time"] for k in first_call["klines"]]
        self.assertLess(opens[0], 1000 * H - hs.PAD_CANDLES * H)  # zapas świec przed oknem
        self.assertGreater(opens[-1], 1500 * H + hs.PAD_CANDLES * H)  # i po oknie


class TestWorkerDatabaseLifecycle(unittest.TestCase):
    def test_initialises_and_closes_its_own_pool(self):
        # Regression: the first production run failed with "Fabryka nie została zainicjalizowana".
        db = mock.MagicMock(factory=None)
        db.init_db = mock.AsyncMock()
        db.close_db = mock.AsyncMock()
        ta = TechnicalAnalysis.__new__(TechnicalAnalysis)
        ta.db = db
        ta._scan_harmonic_windows = mock.AsyncMock(side_effect=RuntimeError("boom"))
        with self.assertRaises(RuntimeError):
            asyncio.run(ta.scan_harmonic_windows(1, "1h", [(0, H)]))
        db.init_db.assert_awaited_once()
        db.close_db.assert_awaited_once()

    def test_reuses_an_already_open_database(self):
        db = mock.MagicMock()
        db.init_db = mock.AsyncMock()
        db.close_db = mock.AsyncMock()
        ta = TechnicalAnalysis.__new__(TechnicalAnalysis)
        ta.db = db
        ta._scan_harmonic_windows = mock.AsyncMock(return_value=[])
        self.assertEqual(asyncio.run(ta.scan_harmonic_windows(1, "1h", [(0, H)])), [])
        db.init_db.assert_not_awaited()
        db.close_db.assert_not_awaited()


class TestHarmonicsEndpoints(unittest.TestCase):
    def setUp(self):
        self.scanned = []
        self.patterns = [{"id": 1, "x_point_timestamp": 1, "ta_object_json": {"pattern_type": "gartley"}}]
        factory = mock.MagicMock()
        factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(return_value={"id": 1})
        factory.get_technical_analysis_harmonic_scan_windows_table.return_value.get_overlapping = mock.AsyncMock(
            side_effect=lambda *a: [{"start_time": s, "end_time": e} for s, e in self.scanned])
        factory.get_technical_analysis_harmonic_patterns_table.return_value.get_within_range = mock.AsyncMock(
            return_value=self.patterns)
        db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))

        self.enqueue = mock.MagicMock(side_effect=lambda *a: f"task-{self.enqueue.call_count}")
        self.state = mock.MagicMock(return_value=("STARTED", None))
        harmonics_api._inflight.clear()
        for p in [
            mock.patch.object(harmonics_api, "get_db", mock.AsyncMock(return_value=db)),
            mock.patch.object(harmonics_api, "_enqueue_scan", self.enqueue),
            mock.patch.object(harmonics_api, "_task_state", self.state),
        ]:
            p.start()
            self.addCleanup(p.stop)

        app = FastAPI()
        app.include_router(harmonics_api.router, prefix=harmonics_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        self.client = TestClient(app)

    def test_fully_scanned_range_is_served_from_the_database(self):
        self.scanned = [(0, 10 ** 15)]
        r = self.client.get("/harmonics/1/1h")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "complete")
        self.assertEqual(r.json()["patterns"], self.patterns)
        self.assertEqual(r.headers["cache-control"], harmonics_api.CACHE_CONTROL_COMPLETE)
        self.enqueue.assert_not_called()

    def test_missing_fragments_start_one_scan_per_asset_and_interval(self):
        first = self.client.get("/harmonics/1/1h")
        second = self.client.get("/harmonics/1/1h")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()["status"], "computing")
        self.assertEqual(first.json()["patterns"], self.patterns)  # częściowe wyniki od razu
        self.assertEqual(second.json()["task_id"], first.json()["task_id"])
        self.assertEqual(self.enqueue.call_count, 1)
        self.assertEqual(first.headers["cache-control"], "no-store")

    def test_failed_scan_is_reported_then_retried(self):
        self.client.get("/harmonics/1/1h")
        self.state.return_value = ("FAILURE", "binance down")
        failed = self.client.get("/harmonics/1/1h")
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(failed.json()["status"], "failed")
        self.assertEqual(failed.json()["error"], "binance down")
        retried = self.client.get("/harmonics/1/1h")
        self.assertEqual(retried.status_code, 202)
        self.assertEqual(self.enqueue.call_count, 2)

    def test_range_validation(self):
        self.assertEqual(self.client.get("/harmonics/1/1h", params={"start_time": 0, "end_time": 3000 * H}).status_code, 422)
        self.assertEqual(self.client.get("/harmonics/1/7h").status_code, 422)

    def test_validate_endpoint(self):
        body = {"points": {n: {"time": p.time, "price": p.price} for n, p in gartley().items()}}
        r = self.client.post("/harmonics/validate", json=body)
        self.assertEqual(r.status_code, 200)
        self.assertIn("gartley", [m["pattern"] for m in r.json()["matches"]])
        body["points"]["B"]["price"] = 2000.0
        self.assertEqual(self.client.post("/harmonics/validate", json=body).status_code, 422)


if __name__ == "__main__":
    unittest.main()
