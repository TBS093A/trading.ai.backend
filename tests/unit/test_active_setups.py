"""
Unit testy bloku "aktywne setupy": konfluencje i siła wstępna setupów czekających na PRZ, dwa
modele siły (entry / pre), powiązanie formacji z wykresu z setupem, filtr aktywnych setupów,
siła i link do wykresu w alertach - bez bazy, sieci i serwera poczty.
"""

import asyncio
import random
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_harmonics as harmonics_api
from src import harmonic_alerts as ha
from src import harmonic_setups as hs
from src import pattern_strength as ps
from src.analysis_services import strength_service as svc
from src.auth import require_auth

POINTS = {"X": {"time": 1, "price": 100.0}, "A": {"time": 2, "price": 200.0},
          "B": {"time": 3, "price": 138.2}, "C": {"time": 4, "price": 169.1}}


def conf(*types):
    return {"confluences": [{"type": t} for t in types]}


def setup_row(**kw):
    row = {"pattern_type": "gartley", "is_bullish": True, "interval": "1h", "spacing": 8, "points_json": POINTS,
           "status": "waiting", "entry_time": None, "entry_price": None, "prz_min": 118.0, "prz_max": 122.0,
           "created_time": 5, "confluences_json": None, "pre_confluences_json": None}
    row.update(kw)
    return row


def synthetic(n=800, seed=2):
    rnd = random.Random(seed)
    rows = []
    for i in range(n):
        good = rnd.random() < 0.4
        types = (["support_zone"] if good else []) + (["bullish_engulfing"] if rnd.random() < 0.3 else [])
        win = rnd.random() < (0.45 if good else 0.2)
        rows.append(setup_row(status="win" if win else "loss", entry_time=10 + i, entry_price=121.0,
                              r_multiple=2.0 if win else -1.0, confluences_json=conf(*types)))
    return rows


class TestPreFeatures(unittest.TestCase):
    def test_pre_features_keep_only_level_confluences(self):
        row = setup_row(status="win", entry_time=6, entry_price=121.0,
                        confluences_json=conf("support_zone", "bullish_engulfing", "rsi_oversold", "fib_cluster"))
        pre = ps.setup_features(row, "pre")
        self.assertIn("conf:support_zone:with", pre)
        self.assertIn("conf:fib_cluster:neutral", pre)
        self.assertNotIn("conf:bullish_engulfing:with", pre)
        self.assertNotIn("conf:rsi_oversold:with", pre)
        self.assertIn("conf:bullish_engulfing:with", ps.setup_features(row, "entry"))

    def test_waiting_setup_uses_pre_confluences_and_the_near_prz_edge(self):
        row = setup_row(pre_confluences_json=conf("support_zone"))
        f = ps.setup_features(row, "pre")
        self.assertIn("conf:support_zone:with", f)
        self.assertIn("ratio_deviation", f)   # D = bliższa krawędź PRZ (122) w chwili created_time
        self.assertEqual(ps.LEVEL_TYPES & {"hammer", "rsi_oversold", "volume_spike"}, set())


class TestTwoModels(unittest.TestCase):
    def setUp(self):
        self.entry = ps.fit(ps.training_samples(synthetic(), "entry"), kind="entry")
        self.pre = ps.fit(ps.training_samples(synthetic(), "pre"), kind="pre")
        self.addCleanup(svc.set_cached_model, None, "entry")
        self.addCleanup(svc.set_cached_model, None, "pre")
        svc.set_cached_model(self.entry, "entry")
        svc.set_cached_model(self.pre, "pre")

    def test_pre_model_never_sees_reaction_features(self):
        self.assertFalse([n for n in self.pre.feature_names if "engulfing" in n])
        self.assertTrue([n for n in self.entry.feature_names if "engulfing" in n])

    def test_setup_strength_kind_follows_status(self):
        waiting = svc.setup_strength_or_none(setup_row(pre_confluences_json=conf("support_zone")))
        self.assertEqual(waiting["kind"], "pre")
        opened = svc.setup_strength_or_none(setup_row(status="open", entry_time=6, entry_price=121.0))
        self.assertEqual(opened["kind"], "entry")
        self.assertIsNone(svc.setup_strength_or_none(setup_row(status="invalidated")))

    def test_fit_and_activate_stores_both_kinds(self):
        table = mock.MagicMock()
        table.save = mock.AsyncMock(side_effect=[11, 12])
        db = mock.MagicMock()
        db.get_factory.return_value.get_harmonic_strength_models_table.return_value = table
        service = svc.StrengthService(db)
        service._decided_setups = mock.AsyncMock(return_value=synthetic())
        res = asyncio.run(service.fit_and_activate())
        self.assertEqual([c.args[3] for c in table.save.await_args_list], ["entry", "pre"])
        self.assertEqual((res["model_id"], res["models"]["pre"]["model_id"]), (11, 12))
        self.assertEqual(svc.cached_model("pre").kind, "pre")


class TestEvaluateAndEvents(unittest.TestCase):
    def test_pre_confluences_only_for_waiting_setups(self):
        rnd = random.Random(3)
        prices = [100.0]
        for _ in range(800):
            prices.append(max(1.0, prices[-1] * (1 + rnd.uniform(-0.03, 0.03))))
        kl = [{"open": p, "high": p * 1.002, "low": p * 0.998, "close": p, "volume": 1, "open_time": i * 3_600_000}
              for i, p in enumerate(prices)]
        calls = []
        rows = hs.evaluate(kl, 1, "1h", "replay", pre_confluences_fn=lambda s, k: calls.append(s) or conf("round_level"))
        waiting = [r for r in rows if r["status"] == "waiting"]
        self.assertEqual(len(calls), len(waiting))
        self.assertTrue(all(r["pre_confluences_json"] for r in waiting))
        self.assertTrue(all(r["pre_confluences_json"] is None for r in rows if r["status"] != "waiting"))

    def test_events_carry_strength(self):
        r = {"asset_id": 1, "interval": "1h", "params_version": "v", "pattern_type": "bat", "is_bullish": True,
             "x_time": 1, "a_time": 2, "b_time": 3, "c_time": 4, "points_json": {}, "prz_min": 1, "prz_max": 2,
             "created_time": 100, "status": "waiting", "entry_time": None, "entry_price": None, "sl": None,
             "tp1": None, "tp2": None, "exit_time": None, "r_multiple": None, "targets_source": None}
        ev = hs.status_events([r], {}, "X/Y", new_since=0, strength_fn=lambda row: {"score": 77, "kind": "pre"})
        self.assertEqual(ev[0]["payload"]["strength"], {"score": 77, "kind": "pre"})


class TestAlertMail(unittest.TestCase):
    def event(self, strength=None):
        return {"id": 1, "asset_id": 5, "interval": "4h", "pattern_type": "bat", "is_bullish": True,
                "from_status": None, "to_status": "waiting", "event_time": 1_700_000_000_000,
                "x_time": 1_699_000_000_000, "c_time": 1_699_500_000_000,
                "payload": {"symbol": "ETH/USDT", "prz": [1.0, 2.0], "strength": strength}}

    def test_chart_link_points_at_the_setup(self):
        url = ha.chart_link("https://app.test", self.event())
        self.assertTrue(url.startswith("https://app.test/?view=chart&asset_id=5&interval=4h&t=1700000000000"))
        self.assertIn("pattern=bat", url)
        self.assertIn("x=1699000000000", url)
        self.assertIsNone(ha.chart_link(None, self.event()))

    def test_strength_chip_and_link_in_both_versions(self):
        e = self.event({"score": 64, "p_win": 0.31, "kind": "pre", "factors": [{"label": "support zone (zgodna z kierunkiem)"}]})
        _, text, html = ha.render({}, [e], "https://app.test")
        self.assertIn("SIŁA 64/100", html)
        self.assertIn("wstępna", html)
        self.assertIn("Pokaż na wykresie", html)
        self.assertIn("rgba(0,255,136,0.28)", html)
        self.assertIn("siła (wstępna): 64/100, szansa TP1 31%", text)
        self.assertIn("wykres: https://app.test/?view=chart", text)
        _, text, html = ha.render({}, [self.event()], None)
        self.assertNotIn("SIŁA", html)
        self.assertNotIn("Pokaż na wykresie", html)


class TestApi(unittest.TestCase):
    def setUp(self):
        self.setups = mock.MagicMock()
        self.setups.list = mock.AsyncMock(return_value=[setup_row(id=1)])
        self.setups.find_by_points = mock.AsyncMock(return_value={("bat", 1, 2, 3, 4): {"id": 9, "status": "open"}})
        factory = mock.MagicMock()
        factory.get_technical_analysis_harmonic_setups_table.return_value = self.setups
        self.db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
        p = mock.patch.object(harmonics_api, "get_db", mock.AsyncMock(return_value=self.db))
        p.start()
        self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(harmonics_api.router, prefix=harmonics_api.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        self.client = TestClient(app)

    def test_active_filter(self):
        self.client.get("/harmonics/setups", params={"asset_id": 1, "interval": "1h", "active": True})
        self.assertEqual(self.setups.list.await_args.kwargs["statuses"], ("waiting", "open"))
        self.client.get("/harmonics/setups", params={"asset_id": 1, "interval": "1h"})
        self.assertIsNone(self.setups.list.await_args.kwargs["statuses"])

    def test_patterns_get_their_setup_and_abcd_none(self):
        xabcd = {"ta_object_json": {"pattern_type": "bat"}, "x_point_timestamp": 1, "a_point_timestamp": 2,
                 "b_point_timestamp": 3, "c_point_timestamp": 4}
        abcd = {"ta_object_json": {"pattern_type": "abcd"}, "x_point_timestamp": None, "a_point_timestamp": 2,
                "b_point_timestamp": 3, "c_point_timestamp": 4}
        asyncio.run(harmonics_api.attach_setups(self.db, 1, "1h", [xabcd, abcd]))
        self.assertEqual(xabcd["setup"], {"id": 9, "status": "open"})
        self.assertIsNone(abcd["setup"])
        keys = self.setups.find_by_points.await_args.args[3]
        self.assertEqual(keys, [("bat", 1, 2, 3, 4)])

    def test_model_endpoint_reports_both_kinds(self):
        body = self.client.get("/harmonics/strength/model").json()
        self.assertEqual(set(body), {"model", "pre_model"})


if __name__ == "__main__":
    unittest.main()
