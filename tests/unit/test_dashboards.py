"""
Unit testy pod dashboardy: sekcje setupów w sidebarze (aktywne / wygrane / przegrane / śmieciowe),
monitoring uczenia modelu siły (historia, kalibracja, dane uczące) i benchmarki wariantów (krzywa
kapitału, rozbicia, lista raportów) - bez bazy.
"""

import random
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_harmonics as harmonics_api
from src import pattern_strength as ps
from src import setup_variants as sv
from src.auth import require_auth


class TestSections(unittest.TestCase):
    def setUp(self):
        self.table = mock.MagicMock()
        self.table.list = mock.AsyncMock(return_value=[])
        self.table.status_counts = mock.AsyncMock(return_value={"win": 3, "loss": 5, "waiting": 2, "open": 1,
                                                                "invalidated": 7, "no_entry": 2})
        self.table.decided_by_week = mock.AsyncMock(return_value=[{"week": "2026-10-05", "trades": 4, "wins": 1,
                                                                   "avg_r": -0.2}])
        self.table.status_totals = mock.AsyncMock(return_value={"win": 1})
        self.models = mock.MagicMock()
        self.models.history = mock.AsyncMock(return_value=[{"id": 1, "kind": "entry", "created_at": "t", "active": True,
                                                            "params_version": "v", "metrics_json": {"auc_test": 0.7}}])
        factory = mock.MagicMock()
        factory.get_technical_analysis_harmonic_setups_table.return_value = self.table
        factory.get_harmonic_strength_models_table.return_value = self.models
        for p in [mock.patch.object(harmonics_api, "get_db", mock.AsyncMock(
                return_value=mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))))]:
            p.start()
            self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(harmonics_api.router, prefix=harmonics_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        self.client = TestClient(app)

    def test_section_counts(self):
        body = self.client.get("/harmonics/setups/sections", params={"asset_id": 1, "interval": "1h"}).json()
        counts = {k: v["count"] for k, v in body["sections"].items()}
        self.assertEqual(counts, {"active": 3, "won": 3, "lost": 5, "junk": 9})

    def test_section_list_maps_statuses_and_orders_by_exit(self):
        self.client.get("/harmonics/setups", params={"asset_id": 1, "interval": "1h", "section": "junk", "offset": 50})
        kw = self.table.list.await_args.kwargs
        self.assertEqual((kw["statuses"], kw["offset"], kw["newest_exit_first"]),
                         (("expired", "no_entry", "invalidated"), 50, True))
        self.client.get("/harmonics/setups", params={"asset_id": 1, "interval": "1h", "section": "active"})
        self.assertFalse(self.table.list.await_args.kwargs["newest_exit_first"])
        self.assertEqual(self.client.get("/harmonics/setups", params={"asset_id": 1, "interval": "1h",
                                                                      "section": "x"}).status_code, 422)

    def test_model_history_and_training_data(self):
        runs = self.client.get("/harmonics/strength/history", params={"kind": "entry"}).json()["runs"]
        self.assertEqual(runs[0]["metrics"], {"auc_test": 0.7})
        self.assertEqual(self.client.get("/harmonics/strength/history", params={"kind": "x"}).status_code, 422)
        data = self.client.get("/harmonics/strength/data").json()
        self.assertEqual(data["weeks"][0]["win_rate"], 0.25)
        self.assertEqual(data["totals"], {"win": 1})


class TestCalibration(unittest.TestCase):
    def test_fit_reports_calibration_by_decile(self):
        rnd = random.Random(5)
        samples = []
        for i in range(2000):
            good = rnd.random() < 0.5
            f = ps.features("bat", True, "1h", 8, [{"type": "hammer"}] if good else [], 0.0)
            win = int(rnd.random() < (0.5 if good else 0.15))
            samples.append((f, win, 1.0 if win else -1.0, i))
        cal = ps.fit(samples).metrics["calibration_test"]
        self.assertEqual(len(cal), 10)
        self.assertLess(cal[0]["actual"], cal[-1]["actual"])
        self.assertTrue(all(0 <= c["predicted"] <= 1 for c in cal))


class TestBenchmarks(unittest.TestCase):
    trades = [{"variant": "baseline", "r": r, "status": "win" if r > 0 else "loss", "exit_time": i, "entry_time": i,
               "interval": iv, "pattern_type": p}
              for i, (r, iv, p) in enumerate([(2, "1h", "bat"), (-1, "4h", "bat"), (-1, "1h", "crab"), (2, "1h", "bat")])]

    def test_equity_curve_and_breakdowns(self):
        self.assertEqual(sv.equity_curve(self.trades), [[0, 2.0], [1, 1.0], [2, 0.0], [3, 2.0]])
        thin = sv.equity_curve([{"r": 1, "exit_time": i} for i in range(1000)], points=50)
        self.assertEqual((len(thin), thin[-1]), (50, [999, 1000.0]))
        base = next(r for r in sv.report(self.trades, cutoff_ms=None) if r["variant"] == "baseline")
        self.assertEqual(base["by_interval"]["1h"]["trades"], 3)
        self.assertEqual(base["by_pattern"]["crab"]["total_r"], -1)


if __name__ == "__main__":
    unittest.main()
