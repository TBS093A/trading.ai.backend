"""
Unit testy siły formacji (src/pattern_strength.py, analysis_services/strength_service.py): cechy z
konfluencji sidebara (kierunek, kategorie), proporcje, regresja logistyczna z walidacją w czasie,
percentyl, cache modelu i pole strength w odpowiedziach API - bez bazy.
"""

import asyncio
import random
import unittest
from unittest import mock

from src import pattern_strength as ps
from src.analysis_services import strength_service as svc
from src.controller_rest_domain_technical_analysis import TechnicalAnalysisResponse

GARTLEY = {"X": (1, 100.0), "A": (2, 200.0), "B": (3, 138.2), "C": (4, 169.1), "D": (5, 121.4)}


def conf(*types):
    return [{"type": t, "confidence": 0.5} for t in types]


class TestFeatures(unittest.TestCase):
    def test_direction_alignment_follows_the_sidebar_catalog(self):
        bull = ps.features("bat", True, "1h", 8, conf("rsi_overbought", "hammer", "doji"), None)
        self.assertIn("conf:rsi_overbought:against", bull)
        self.assertIn("conf:hammer:with", bull)
        self.assertIn("conf:doji:neutral", bull)
        bear = ps.features("bat", False, "1h", 8, conf("rsi_overbought"), None)
        self.assertIn("conf:rsi_overbought:with", bear)

    def test_counts_categories_and_shape(self):
        f = ps.features("gartley", True, "4h", 30, conf("hammer", "support_zone", "rsi_overbought", "fib_cluster"), 0.2)
        self.assertEqual(f["pattern:gartley"], 1.0)
        self.assertEqual(f["interval:4h"], 1.0)
        self.assertAlmostEqual(f["structure_size"], 1.0)
        self.assertEqual(f["ratio_deviation"], 0.2)
        self.assertEqual(f["confluences_with"], 2 / 8)
        self.assertEqual(f["confluences_against"], 1 / 8)
        self.assertEqual({k for k in f if k.startswith("category:")},
                         {"category:candles", "category:structure", "category:fibonacci"})

    def test_ratio_deviation(self):
        self.assertEqual(ps.ratio_deviation(GARTLEY, "gartley"), 0.0)
        self.assertGreater(ps.ratio_deviation({**GARTLEY, "D": (5, 150.0)}, "gartley"), 0)
        self.assertIsNone(ps.ratio_deviation({k: v for k, v in GARTLEY.items() if k != "X"}, "gartley"))

    def test_setup_and_pattern_rows_give_the_same_features(self):
        setup = {"pattern_type": "gartley", "is_bullish": True, "interval": "1h", "spacing": 8,
                 "points_json": {k: {"time": t, "price": p} for k, (t, p) in GARTLEY.items() if k != "D"},
                 "entry_time": 5, "entry_price": 121.4, "confluences_json": {"confluences": conf("hammer")}}
        pattern = {"interval": "1h", "confluences_json": {"confluences": conf("hammer")},
                   "ta_object_json": {"pattern_type": "gartley", "is_bullish": True, "peak_spacing": 8,
                                      "points": {k: {"timestamp": t, "price": p} for k, (t, p) in GARTLEY.items()}}}
        self.assertEqual(ps.setup_features(setup), ps.pattern_features(pattern))


def synthetic(n=3000, seed=1):
    """Engulfing zgodny z kierunkiem podnosi szansę TP1, RSI przeciw kierunkowi ją obniża."""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        types = []
        good, bad = rnd.random() < 0.3, rnd.random() < 0.3
        if good:
            types.append("bullish_engulfing")
        if bad:
            types.append("rsi_overbought")
        p = 0.3 + (0.35 if good else 0) - (0.2 if bad else 0)
        win = 1 if rnd.random() < p else 0
        f = ps.features(rnd.choice(["bat", "crab"]), True, "1h", 8, conf(*types), rnd.random() * 0.3)
        out.append((f, win, 2.0 if win else -1.0, 1_000 + i))
    return out


class TestModel(unittest.TestCase):
    def test_learns_signs_validates_out_of_time_and_ranks(self):
        model = ps.fit(synthetic())
        w = dict(zip(model.feature_names, model.weights))
        self.assertGreater(w["conf:bullish_engulfing:with"], 0.5)
        self.assertLess(w["conf:rsi_overbought:against"], -0.3)
        m = model.metrics
        self.assertEqual((m["train"], m["test"]), (2100, 900))
        self.assertGreater(m["auc_test"], 0.6)
        q = m["quintiles_test"]
        self.assertGreater(q[-1]["win_rate"], q[0]["win_rate"])
        strong = model.score(ps.features("bat", True, "1h", 8, conf("bullish_engulfing"), 0.0))
        weak = model.score(ps.features("bat", True, "1h", 8, conf("rsi_overbought"), 0.0))
        self.assertGreater(strong["score"], weak["score"])
        self.assertTrue(0 <= weak["score"] <= strong["score"] <= 100)
        # Engulfing zawsze idzie w parze z kategorią "świece" - wpływ dzieli się między obie cechy.
        top = {f["feature"]: f for f in strong["factors"]}
        self.assertIn("conf:bullish_engulfing:with", top)
        self.assertGreater(top["conf:bullish_engulfing:with"]["impact"], 0)
        self.assertIn("zgodna z kierunkiem", top["conf:bullish_engulfing:with"]["label"])

    def test_roundtrip_and_too_few_samples(self):
        model = ps.fit(synthetic(400))
        again = ps.StrengthModel.from_dict(model.as_dict())
        f = ps.features("bat", True, "1h", 8, conf("bullish_engulfing"), 0.0)
        self.assertEqual(model.score(f), again.score(f))
        with self.assertRaises(ValueError):
            ps.fit(synthetic(50))

    def test_training_samples_use_only_decided_setups_with_entry(self):
        rows = [{"status": s, "entry_time": e, "r_multiple": 1.0, "pattern_type": "bat", "is_bullish": True,
                 "points_json": {}, "entry_price": 1.0, "confluences_json": None}
                for s, e in (("win", 1), ("loss", 2), ("expired", 3), ("open", 4), ("invalidated", None))]
        self.assertEqual([(s[1], s[3]) for s in ps.training_samples(rows)], [(1, 1), (0, 2), (0, 3)])


class TestServiceAndApi(unittest.TestCase):
    def setUp(self):
        self.model = ps.fit(synthetic(600))
        self.addCleanup(svc.set_cached_model, None)

    def test_cache_refreshes_from_the_active_model(self):
        db = mock.MagicMock()
        db.get_factory().get_harmonic_strength_models_table().get_active = mock.AsyncMock(
            return_value={"model_json": self.model.as_dict()})
        svc._cache["loaded_at"] = 0.0
        loaded = asyncio.run(svc.refresh_cached_model(db))
        self.assertEqual(loaded.feature_names, self.model.feature_names)

    def test_missing_model_means_no_strength(self):
        svc.set_cached_model(None)
        self.assertIsNone(svc.pattern_strength_or_none({"ta_object_json": {}}))

    def test_sidebar_response_carries_strength(self):
        svc.set_cached_model(self.model)
        r = TechnicalAnalysisResponse(id=1, asset_id=1, interval="1h",
                                      ta_object_json={"pattern_type": "bat", "is_bullish": True, "peak_spacing": 8},
                                      confluences_json={"confluences": conf("bullish_engulfing")})
        self.assertIsNotNone(r.strength)
        self.assertIn("score", r.model_dump()["strength"])
        svc.set_cached_model(None)
        r = TechnicalAnalysisResponse(id=1, asset_id=1, ta_object_json={})
        self.assertIsNone(r.strength)

    def test_setup_strength_only_after_entry(self):
        svc.set_cached_model(self.model)
        row = {"pattern_type": "bat", "is_bullish": True, "interval": "1h", "spacing": 8, "points_json": {},
               "entry_time": None, "entry_price": None, "confluences_json": None}
        self.assertIsNone(svc.setup_strength_or_none(row))
        self.assertIsNotNone(svc.setup_strength_or_none({**row, "entry_time": 5, "entry_price": 1.0}))


if __name__ == "__main__":
    unittest.main()
