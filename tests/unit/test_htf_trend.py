"""
Unit testy filtra trendu z wyższego TF: detektor (EMA 200 + nachylenie na świecach zamkniętych przed D),
wyrównanie z kierunkiem formacji, warianty raportu i ustawienie konta - bez bazy.
"""

import unittest

from src import pattern_strength as ps
from src import setup_variants as sv
from src.trading import risk as rk
from src.utils.harmonic_patterns.trend_confluences import HigherTFTrendDetector, ema, trend_at

H4 = 4 * 3_600_000


def series(prices, step=H4):
    return [{"open": p, "high": p * 1.001, "low": p * 0.999, "close": p, "volume": 1, "open_time": i * step}
            for i, p in enumerate(prices)]


def target(d_ts, bullish=True):
    return {"id": 1, "d_point_timestamp": d_ts, "ta_object_json": {"is_bullish": bullish, "points": {"D": {"price": 1}}}}


class TestDetector(unittest.TestCase):
    up = series([100 + i * 0.5 for i in range(260)])
    down = series([300 - i * 0.5 for i in range(260)])

    def test_ema(self):
        self.assertEqual(ema([1, 2, 3], 5), [])
        self.assertAlmostEqual(ema([2.0] * 10, 3)[-1], 2.0)

    def test_up_down_and_flat(self):
        self.assertEqual(trend_at(self.up)["trend"], "up")
        self.assertEqual(trend_at(self.down)["trend"], "down")
        self.assertIsNone(trend_at(series([100.0] * 260)))
        self.assertIsNone(trend_at(self.up[:150]))   # za mało świec na EMA 200

    def test_uses_the_next_higher_interval_and_only_candles_before_d(self):
        d_ts = self.up[-1]["open_time"] + H4
        r = HigherTFTrendDetector.detect({"4h": self.up, "1d": self.down}, target(d_ts), "1h")
        self.assertEqual((r["type"], r["details"]["source_interval"]), ("higher_tf_uptrend", "4h"))
        # D przed historią wyższego TF - nic nie było znane
        self.assertIsNone(HigherTFTrendDetector.detect({"4h": self.up}, target(H4), "1h"))
        # wzrost do świecy 200, potem spadek: przy D w środku trend wzrostowy (późniejsze świece niewidoczne)
        mixed = series([100 + i for i in range(230)] + [330 - i * 3 for i in range(100)])
        r = HigherTFTrendDetector.detect({"4h": mixed}, target(229 * H4 + H4), "1h")
        self.assertEqual(r["type"], "higher_tf_uptrend")


class TestAlignment(unittest.TestCase):
    def test_trend_alignment_and_strength_category(self):
        up = {"confluences": [{"type": "higher_tf_uptrend"}]}
        self.assertEqual(ps.trend_alignment(up, True), "with")
        self.assertEqual(ps.trend_alignment(up, False), "against")
        self.assertIsNone(ps.trend_alignment({"confluences": []}, True))
        f = ps.features("bat", False, "1h", 8, [{"type": "higher_tf_downtrend"}], None)
        self.assertIn("conf:higher_tf_downtrend:with", f)
        self.assertIn("category:trend", f)
        self.assertIn("higher_tf_uptrend", ps.LEVEL_TYPES)   # znany przed dotknięciem - siła wstępna


class TestVariantsAndAccount(unittest.TestCase):
    def test_trend_variants_filter(self):
        from tests.unit.test_setup_variants import TARGETS, after, gartley
        kl = after([(150, 151, 121, 125), (125, 141, 124, 140)])
        with_trend = lambda *a: {"trend": "with"}
        against = lambda *a: {"trend": "against"}
        none = lambda *a: {"trend": None}
        V = sv.VARIANTS_BY_NAME
        self.assertIsNotNone(sv.simulate_variant(gartley(), kl, V["baseline_trend"], TARGETS, with_trend))
        self.assertIsNone(sv.simulate_variant(gartley(), kl, V["baseline_trend"], TARGETS, none))
        self.assertIsNotNone(sv.simulate_variant(gartley(), kl, V["baseline_not_against"], TARGETS, none))
        self.assertIsNone(sv.simulate_variant(gartley(), kl, V["baseline_not_against"], TARGETS, against))

    def test_account_setting(self):
        self.assertEqual(rk.validate({"trend_filter": "with"}).trend_filter, "with")
        with self.assertRaises(ValueError):
            rk.validate({"trend_filter": "sideways"})
        field = next(f for f in rk.RISK_FIELDS if f["key"] == "trend_filter")
        self.assertEqual([o["value"] for o in field["options"]], ["off", "with", "not_against"])


if __name__ == "__main__":
    unittest.main()
