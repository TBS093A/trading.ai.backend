"""
Unit testy src/setup_variants.py: wejście przy dotknięciu i po potwierdzeniu, SL na wejście, limit
R:R, filtry siły i EV, raport (obsunięcie, podział przed/po cutoff) i endpointy raportu - bez bazy.
"""

import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_harmonics as harmonics_api
from src import harmonic_setups as hs
from src import setup_variants as sv
from src.auth import require_admin, require_auth
from src.db.postgresql.database_postgresql_factory import DatabasePostgreSQLFactory
from src.harmonic_setups import Pivot, Setup

V = sv.VARIANTS_BY_NAME
TARGETS = lambda s, entry: (110.0, 140.0, 155.0, "test")   # SL 110, TP1 140


def k(o, h, l, c, i):
    return {"open": o, "high": h, "low": l, "close": c, "volume": 1.0, "open_time": i}


def gartley(created=40, span=30):
    pts = {"X": Pivot(0, 100.0, False, 5), "A": Pivot(10, 200.0, True, 15),
           "B": Pivot(20, 138.2, False, 25), "C": Pivot(span, 169.1, True, created)}
    return Setup("gartley", True, pts, prz_min=118.0, prz_max=122.0, created_index=created, spacing=5)


def after(closes, created=40):
    base = [k(169, 169, 169, 169, i) for i in range(created + 1)]
    return base + [k(o, h, l, c, created + 1 + j) for j, (o, h, l, c) in enumerate(closes)]


class TestEntries(unittest.TestCase):
    def test_touch_variant_matches_the_production_simulation(self):
        kl = after([(150, 151, 121, 125), (125, 141, 124, 140)])
        t = sv.simulate_variant(gartley(), kl, V["baseline"], TARGETS)
        o = hs.simulate(gartley(), kl, TARGETS)
        self.assertEqual((t.status, t.r, t.entry_price), (o.status, o.r_multiple, o.entry_price))

    def test_confirm_waits_for_a_reversal_close_and_puts_sl_behind_the_extreme(self):
        # dotknięcie (czerwona), potem zielona zamknięta nad 118 -> wejście 121 na zamknięciu
        kl = after([(150, 151, 119, 120), (120, 121.5, 116, 121), (121, 141, 120, 140)])
        t = sv.simulate_variant(gartley(), kl, V["confirm"], lambda s, e: (117.0, 140.0, 150.0, "x"))
        self.assertEqual((t.entry_index, t.entry_price), (42, 121.0))
        self.assertAlmostEqual(t.sl, 116 * (1 - sv.SL_BUFFER))   # dalej niż SL z reguł (117)
        self.assertEqual(t.status, "win")

    def test_touch_candle_high_before_the_touch_is_not_a_win(self):
        # Regression: high 151 of the touch candle came before price fell to the PRZ.
        kl = after([(150, 151, 121, 125)])
        self.assertIsNone(sv.simulate_variant(gartley(), kl, V["baseline"], TARGETS))

    def test_confirm_skips_when_no_reversal_in_the_window(self):
        kl = after([(150, 151, 121, 121), (121, 121, 119, 119.5), (119.5, 120, 117, 117.5), (117.5, 118, 116, 116.5)])
        self.assertIsNone(sv.simulate_variant(gartley(), kl, V["confirm"], TARGETS))

    def test_breakeven_after_one_r(self):
        # wejście 122, ryzyko 12; +1R = 134 -> SL 122; potem spadek do 121 -> wynik 0
        kl = after([(150, 151, 121, 125), (125, 135, 124, 133), (133, 133, 121, 121)])
        t = sv.simulate_variant(gartley(), kl, V["be_1r"], TARGETS)
        self.assertEqual((t.status, t.r), ("be", 0.0))
        self.assertEqual(sv.simulate_variant(gartley(), kl, V["baseline"], TARGETS), None)  # baseline wciąż otwarty

    def test_rr_cap_brings_tp1_closer(self):
        far = lambda s, entry: (110.0, 160.0, 170.0, "test")   # TP1 160 = 3.17R
        kl = after([(150, 151, 121, 125), (125, 141, 124, 140)])
        t = sv.simulate_variant(gartley(), kl, V["rr_cap_1_5"], far)
        self.assertEqual((t.status, t.tp1, t.r), ("win", 122 + 1.5 * 12, 1.5))
        self.assertIsNone(sv.simulate_variant(gartley(), kl, V["baseline"], far))   # bez limitu wciąż otwarta


class TestFilters(unittest.TestCase):
    kl = after([(150, 151, 121, 125), (125, 141, 124, 140)])

    def test_strength_threshold(self):
        weak = lambda *a: {"score": 55, "p_win": 0.3}
        strong = lambda *a: {"score": 85, "p_win": 0.5}
        self.assertIsNone(sv.simulate_variant(gartley(), self.kl, V["strength_60"], TARGETS, weak))
        t = sv.simulate_variant(gartley(), self.kl, V["strength_60"], TARGETS, strong)
        self.assertEqual((t.strength, t.p_win), (85, 0.5))
        self.assertIsNone(sv.simulate_variant(gartley(), self.kl, V["strength_60"], TARGETS, None))

    def test_expected_value_filter(self):
        # R:R = 18/12 = 1.5; EV = p*1.5 - (1-p): p=0.3 -> -0.25, p=0.5 -> +0.25
        self.assertIsNone(sv.simulate_variant(gartley(), self.kl, V["ev_positive"], TARGETS,
                                              lambda *a: {"score": 90, "p_win": 0.3}))
        t = sv.simulate_variant(gartley(), self.kl, V["ev_positive"], TARGETS, lambda *a: {"score": 90, "p_win": 0.5})
        self.assertEqual(t.ev, 0.25)


class TestReport(unittest.TestCase):
    def test_summary_drawdown_and_split(self):
        trades = [{"variant": "baseline", "r": r, "status": "win" if r > 0 else "loss", "exit_time": i,
                   "entry_time": i} for i, r in enumerate([2, -1, -1, -1, 2, -1])]
        s = sv.summarize(trades)
        self.assertEqual((s["trades"], s["wins"], s["total_r"], s["max_drawdown_r"]), (6, 2, 0, 3))
        rows = sv.report(trades, cutoff_ms=3)
        base = next(r for r in rows if r["variant"] == "baseline")
        self.assertEqual((base["in"]["trades"], base["out"]["trades"]), (3, 3))
        self.assertEqual(next(r for r in rows if r["variant"] == "confirm")["all"], {"trades": 0})

    def test_trades_table_is_known_to_the_janitor(self):
        self.assertIn("harmonic_variant_trades", DatabasePostgreSQLFactory.registered_table_names())


class TestEndpoints(unittest.TestCase):
    def setUp(self):
        self.service = mock.MagicMock()
        self.service.create = mock.AsyncMock(return_value={"report_id": 3, "cutoff_ms": 99,
                                                           "pairs": [{"asset_id": 1, "interval": "1h"},
                                                                     {"asset_id": 2, "interval": "4h"}]})
        self.service.summary = mock.AsyncMock(return_value=None)
        self.enqueue = mock.MagicMock(return_value="t")
        for p in [mock.patch("src.analysis_services.variant_report_service.VariantReportService",
                             mock.MagicMock(return_value=self.service)),
                  mock.patch.object(harmonics_api, "get_db", mock.AsyncMock(return_value=mock.MagicMock())),
                  mock.patch.object(harmonics_api, "_enqueue_variant_pair", self.enqueue)]:
            p.start()
            self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(harmonics_api.router, prefix=harmonics_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        app.dependency_overrides[require_admin] = lambda: None
        self.client = TestClient(app)

    def test_run_enqueues_one_task_per_pair(self):
        body = self.client.post("/harmonics/variants/run").json()
        self.assertEqual((body["report_id"], body["pairs"]), (3, 2))
        self.enqueue.assert_any_call(3, 2, "4h")

    def test_missing_report_is_404(self):
        self.assertEqual(self.client.get("/harmonics/variants/report").status_code, 404)


if __name__ == "__main__":
    unittest.main()
