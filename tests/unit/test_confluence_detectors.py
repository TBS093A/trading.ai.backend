"""
Unit testy detektorów konfluencji formacji harmonicznych (src/utils/harmonic_patterns/) - bez
bazy i sieci. Testy regresyjne opisują błędy znalezione przy przeglądzie (cena D z close świecy,
look-ahead w MACD, normalizacje dywergencji, samopotwierdzanie się formacji itd.).
"""

import unittest
from datetime import datetime, timezone
from unittest import mock

from src.utils.harmonic_patterns import HigherTFSRDetector, indicator_confluences as ind
from src.utils.harmonic_patterns import structural_confluences as st
from src.utils.harmonic_patterns._common import d_point_price, pattern_point_indices
from src.utils.harmonic_patterns.candlestick_patterns import CandlestickPatternDetector as C
from src.utils.harmonic_patterns.confluence_detector import ConfluenceDetector
from src.utils.harmonic_patterns.fib_confluences import FibClusterDetector, HigherTFFibDetector, merge_confluences
from src.utils.harmonic_patterns.indicator_confluences import IndicatorConfluenceDetector as I
from src.utils.harmonic_patterns.structural_confluences import StructuralConfluenceDetector as S
from src.utils.harmonic_patterns.volume_confluences import VolumeConfluenceDetector as V

H = 3_600_000


def k(o, h, l, c, v=100.0, t=0):
    return {"open": o, "high": h, "low": l, "close": c, "volume": v, "open_time": t}


def flat(n, price=100.0, v=100.0, start=0):
    """Spokojne świece wokół `price` (zakres ±0.2%)."""
    return [k(price, price * 1.002, price * 0.998, price, v, (start + i) * H) for i in range(n)]


def points(**named):
    """points(X=(index, price), ...) -> pattern_points jak w tao_harmonic_patterns."""
    return {n: {"index": i, "price": p} for n, (i, p) in named.items()}


class TestCommon(unittest.TestCase):
    def test_d_price_prefers_the_pattern_point(self):
        klines = [k(100, 110, 90, 105)]
        self.assertEqual(d_point_price(klines, 0, True, points(D=(0, 91.5))), 91.5)

    def test_d_price_falls_back_to_the_candle_extreme_not_the_close(self):
        klines = [k(100, 110, 90, 105)]
        self.assertEqual(d_point_price(klines, 0, True), 90)
        self.assertEqual(d_point_price(klines, 0, False), 110)

    def test_pattern_point_indices_excludes_d_and_later(self):
        pp = points(X=(3, 1), A=(7, 1), B=(9, 1), C=(12, 1), D=(15, 1))
        self.assertEqual(pattern_point_indices(pp, 15), {3, 7, 9, 12})
        self.assertEqual(pattern_point_indices(None, 15), set())


class TestCandlesticks(unittest.TestCase):
    def test_hammer_only_for_bullish_patterns(self):
        hammer = [k(100, 100.5, 94, 100.2)]
        self.assertEqual(C.detect_hammer(hammer, 0, True)["type"], "hammer")
        self.assertIsNone(C.detect_hammer(hammer, 0, False))
        self.assertIsNone(C.detect_hammer([k(100, 106, 99.8, 100.2)], 0, True))  # long upper wick

    def test_shooting_star_only_for_bearish_patterns(self):
        star = [k(100.2, 106, 99.8, 100)]
        self.assertEqual(C.detect_shooting_star(star, 0, False)["type"], "shooting_star")
        self.assertIsNone(C.detect_shooting_star(star, 0, True))

    def test_morning_and_evening_star(self):
        morning = [k(110, 110.5, 99.5, 100), k(99.5, 100.5, 98.5, 99.7), k(100, 110.5, 99.5, 109)]
        self.assertEqual(C.detect_morning_star(morning, 2, True)["type"], "morning_star")
        evening = [k(100, 110.5, 99.5, 110), k(110.5, 111.5, 109.5, 110.7), k(110, 110.5, 100.5, 101)]
        self.assertEqual(C.detect_evening_star(evening, 2, False)["type"], "evening_star")
        self.assertIsNone(C.detect_morning_star(morning, 1, True))

    def test_engulfing(self):
        bull = [k(102, 102.5, 99.5, 100), k(99.8, 103.5, 99.5, 103)]
        self.assertEqual(C.detect_bullish_engulfing(bull, 1, True)["type"], "bullish_engulfing")
        bear = [k(100, 102.5, 99.5, 102), k(102.2, 102.5, 98.5, 99)]
        self.assertEqual(C.detect_bearish_engulfing(bear, 1, False)["type"], "bearish_engulfing")
        self.assertIsNone(C.detect_bullish_engulfing([bull[1], bull[0]], 1, True))

    def test_doji_subtypes(self):
        self.assertEqual(C.detect_doji([k(100, 105, 95, 100.1)], 0, True)["details"]["doji_subtype"], "long_legged")
        self.assertEqual(C.detect_doji([k(100, 108, 99.9, 100.1)], 0, True)["details"]["doji_subtype"], "gravestone")
        self.assertEqual(C.detect_doji([k(100, 100.2, 92, 100.1)], 0, True)["details"]["doji_subtype"], "dragonfly")
        self.assertIsNone(C.detect_doji([k(100, 105, 95, 104)], 0, True))

    def test_pin_bars(self):
        self.assertEqual(C.detect_bullish_pin_bar([k(99.6, 100, 90, 99.9)], 0, True)["type"], "bullish_pin_bar")
        self.assertEqual(C.detect_bearish_pin_bar([k(100.4, 110, 100, 100.1)], 0, False)["type"], "bearish_pin_bar")

    def test_degenerate_candles_and_bad_indices(self):
        zero = [k(100, 100, 100, 100)]
        for fn in (C.detect_hammer, C.detect_doji, C.detect_bullish_pin_bar):
            with self.subTest(fn=fn.__name__):
                self.assertIsNone(fn(zero, 0, True))
                self.assertIsNone(fn(zero, 5, True))


class TestIndicators(unittest.TestCase):
    def test_rsi_oversold_and_overbought(self):
        falling = [k(100 - i, 100.5 - i, 99 - i, 99.2 - i, t=i * H) for i in range(40)]
        rising = [k(100 + i, 101 + i, 99.5 + i, 100.8 + i, t=i * H) for i in range(40)]
        self.assertEqual(I.detect_rsi_oversold(falling, 39, True)["type"], "rsi_oversold")
        self.assertIsNone(I.detect_rsi_oversold(falling, 39, False))
        self.assertEqual(I.detect_rsi_overbought(rising, 39, False)["type"], "rsi_overbought")
        self.assertIsNone(I.detect_rsi_overbought(falling, 39, False))

    def test_rsi_divergence_uses_the_d_point_price_not_the_close(self):
        # Regression: D's wick (95) makes a lower low than X (100) but D's close (105) does not.
        klines = flat(30)
        klines[29] = k(104, 106, 95, 105, t=29 * H)
        rsi = [None] * 30
        rsi[5], rsi[29] = 25.0, 35.0
        pp = points(X=(5, 100.0), D=(29, 95.0))
        with mock.patch.object(ind, "_calculate_rsi", return_value=rsi):
            result = I.detect_rsi_divergence(klines, 29, True, pattern_points=pp)
            no_points = I.detect_rsi_divergence(klines, 29, True, pattern_points={"X": pp["X"]})
        self.assertEqual(result["type"], "rsi_bullish_divergence")
        self.assertEqual(result["details"]["price_d"], 95.0)
        # without a D point the candle low (95) is used - also a lower low than X
        self.assertIsNotNone(no_points)

    def test_macd_crossover_ignores_candles_after_d(self):
        klines = flat(60)
        macd = [0.0] * 60
        signal = [0.0] * 60
        for i in range(60):
            macd[i] = -1.0 if i < 52 else 1.0  # bullish cross at 52
        import numpy as np
        with mock.patch.object(ind, "_calculate_macd", return_value=(np.array(macd), np.array(signal), None)):
            self.assertIsNone(I.detect_macd_crossover(klines, 50, True))  # cross 2 candles AFTER D: look-ahead
            hit = I.detect_macd_crossover(klines, 53, True)
        self.assertEqual(hit["type"], "macd_bullish_crossover")
        self.assertEqual(hit["details"]["distance_from_d"], 1)

    def test_macd_divergence_confidence_is_not_maxed_by_a_near_zero_reference(self):
        import numpy as np
        klines = flat(60)
        macd = np.zeros(60)
        macd[10], macd[59] = -0.0001, -0.00005
        pp = points(X=(10, 101.0), D=(59, 99.0))
        with mock.patch.object(ind, "_calculate_macd", return_value=(macd, macd, macd)):
            result = I.detect_macd_divergence(klines, 59, True, pattern_points=pp)
        self.assertEqual(result["type"], "macd_bullish_divergence")
        self.assertAlmostEqual(result["confidence"], 0.333, places=3)  # was 0.5 / 1.0 with |ref| scaling

    def test_obv_divergence_strength_is_relative_to_traded_volume(self):
        klines = flat(30, v=0.0)
        klines[10] = k(100, 100.2, 99.8, 99, v=1000, t=10 * H)    # X: down candle
        for i in range(11, 29):  # up candles carry more volume than down candles -> OBV rises
            klines[i] = k(100, 100.2, 99.8, 100.1 if i % 2 else 100, v=200 if i % 2 else 100, t=i * H)
        klines[29] = k(100, 100.2, 98.0, 98.5, v=50, t=29 * H)    # D: lower low
        pp = points(X=(10, 99.0), D=(29, 98.0))
        result = I.detect_obv_divergence(klines, 29, True, pattern_points=pp)
        obv = ind._calculate_obv(klines)
        traded = sum(c["volume"] for c in klines[11:30])
        self.assertEqual(result["type"], "obv_bullish_divergence")
        self.assertAlmostEqual(result["confidence"], round(min(1.0, abs(obv[29] - obv[10]) / traded), 3))

    def test_macd_histogram_reversal_sign_change(self):
        import numpy as np
        hist = np.zeros(60)
        hist[57], hist[58], hist[59] = -0.3, -0.1, 0.2
        with mock.patch.object(ind, "_calculate_macd", return_value=(hist, hist, hist)):
            r = I.detect_macd_histogram_reversal(flat(60), 59, True)
        self.assertTrue(r["details"]["sign_change"])
        self.assertEqual(r["confidence"], 0.9)

    def test_stochastic_extremes(self):
        falling = [k(100 - i, 100.5 - i, 99 - i, 99.05 - i, t=i * H) for i in range(30)]
        self.assertEqual(I.detect_stochastic_oversold(falling, 29, True)["type"], "stochastic_oversold")
        rising = [k(100 + i, 101 + i, 99.5 + i, 100.95 + i, t=i * H) for i in range(30)]
        self.assertEqual(I.detect_stochastic_overbought(rising, 29, False)["type"], "stochastic_overbought")


class TestStructural(unittest.TestCase):
    def series_with_lows(self, low_indices, low=100.0, n=80, base=110.0):
        klines = flat(n, price=base)
        for i in low_indices:
            klines[i] = k(base, base * 1.002, low, base, t=i * H)
        return klines

    def test_support_zone_from_earlier_swing_lows(self):
        klines = self.series_with_lows([20, 40])
        klines[70] = k(104, 105, 100.1, 104.5, t=70 * H)  # D: wick to the zone, close far above
        r = S.detect_support_resistance(klines, 70, True, pattern_points=points(D=(70, 100.1)))
        self.assertEqual(r["type"], "support_zone")
        self.assertEqual(r["details"]["d_price"], 100.1)

    def test_support_zone_ignores_the_patterns_own_points(self):
        # Regression: the only "support" is X and B of the pattern itself.
        klines = self.series_with_lows([20, 40])
        pp = points(X=(20, 100.0), B=(40, 100.0), D=(70, 100.1))
        self.assertIsNone(S.detect_support_resistance(klines, 70, True, pattern_points=pp))

    def test_trendline(self):
        klines = flat(80, price=120.0)
        for i in (10, 25, 40, 55):
            low = 100 + 0.1 * i
            klines[i] = k(120, 120.2, low, 120, t=i * H)
        d_low = 100 + 0.1 * 70
        r = S.detect_trendline(klines, 70, True, pattern_points=points(D=(70, d_low)))
        self.assertEqual(r["type"], "support_trendline")
        self.assertLess(r["details"]["deviation_pct"], 0.05)

    def test_a_flat_stretch_is_one_swing_point_not_one_per_candle(self):
        # Regression: ties made every candle of a consolidation a swing low.
        highs, lows = st._find_swing_points(flat(40))
        self.assertLessEqual(len(lows), 1)
        self.assertLessEqual(len(highs), 1)
        klines = flat(80, price=110.0)
        r = S.detect_support_resistance(klines, 70, True, pattern_points=points(D=(70, 109.79)))
        self.assertIsNone(r)  # no "support zone" built out of a plateau

    def test_round_level_roundness_beats_level_size(self):
        # Regression: 62500 used to score "rounder" than 60000 because roundness was lvl/magnitude.
        self.assertGreater(st._roundness(60000, 60100), st._roundness(62500, 62480))
        self.assertEqual(st._roundness(100000, 99900), 1.0)
        r = S.detect_round_level([k(60200, 60300, 60050, 60250)], 0, True, pattern_points=points(D=(0, 60050)))
        self.assertEqual(r["details"]["level"], 60000)

    def test_pivot_point_previous_utc_day(self):
        day1 = int(datetime(2026, 10, 5, tzinfo=timezone.utc).timestamp() * 1000)
        klines = [k(100, 110, 90, 100, t=day1 + i * H) for i in range(24)]          # P = 100
        klines += [k(101, 102, 100.05, 101.5, t=day1 + (24 + i) * H) for i in range(5)]
        r = S.detect_pivot_point(klines, 28, True, pattern_points=points(D=(28, 100.05)), interval="1h")
        self.assertEqual(r["details"]["pivot_name"], "P")
        self.assertEqual(r["details"]["prev_ohlc"]["high"], 110)


class TestVolume(unittest.TestCase):
    def test_volume_spike_and_dryup(self):
        klines = flat(40)
        klines[39] = k(100, 100.2, 99.8, 100, v=500, t=39 * H)
        self.assertEqual(V.detect_volume_spike(klines, 39, True)["confidence"], 1.0)
        self.assertIsNone(V.detect_volume_spike(flat(40), 39, True))
        dry = flat(40)
        for i in range(34, 40):
            dry[i] = k(100, 100.2, 99.8, 100, v=10, t=i * H)
        self.assertEqual(V.detect_volume_dryup(dry, 39, True)["type"], "volume_dryup")

    def test_volume_profile_uses_the_d_point_price_not_the_close(self):
        # Heavy volume traded around 100 (POC); D wicks into it but closes 3% higher.
        klines = []
        for i in range(60):
            if i % 3 == 0:
                klines.append(k(100, 100.3, 99.7, 100, v=1000, t=i * H))
            else:
                klines.append(k(104, 106, 102, 104, v=50, t=i * H))
        klines.append(k(103, 103.5, 100.0, 103, v=100, t=60 * H))
        pp = points(D=(60, 100.0))
        r = V.detect_volume_profile(klines, 60, True, pattern_points=pp)
        self.assertEqual(r["details"]["matched_level"], "POC")
        self.assertEqual(r["details"]["d_price"], 100.0)


DAY = 86_400_000


def fib_pattern(pid, d_price, levels, d_ts=None):
    return {
        "id": pid,
        "d_point_timestamp": d_ts,
        "ta_object_json": {
            "points": {"D": {"price": d_price}},
            "fibonacci_levels": {"retracement": {str(i): lvl for i, lvl in enumerate(levels)}},
        },
    }


class TestFibConfluences(unittest.TestCase):
    def test_cluster_from_other_patterns(self):
        target = fib_pattern(1, 100.0, [], d_ts=10)
        others = [fib_pattern(2, 0, [100.1], 1), fib_pattern(3, 0, [99.9], 2), fib_pattern(4, 0, [100.2], 3)]
        r = FibClusterDetector.detect([target] + others, 1)
        self.assertEqual(r["details"]["unique_price_levels"], 3)

    def test_patterns_sharing_d_do_not_confirm_it(self):
        target = fib_pattern(1, 100.0, [], d_ts=10)
        same_d = [fib_pattern(i, 100.0, [100.0, 100.05, 99.95], d_ts=10) for i in (2, 3, 4)]
        self.assertIsNone(FibClusterDetector.detect([target] + same_d, 1))

    def test_duplicate_levels_count_once(self):
        target = fib_pattern(1, 100.0, [], d_ts=10)
        dupes = [fib_pattern(i, 0, [100.1], d_ts=i) for i in (2, 3, 4, 5)]  # one price, four times
        self.assertIsNone(FibClusterDetector.detect([target] + dupes, 1))

    def test_higher_tf_only_counts_higher_intervals(self):
        target = fib_pattern(1, 100.0, [], d_ts=10 * DAY)
        by_iv = {"1h": [fib_pattern(2, 0, [100.0], 2 * DAY)], "1d": [fib_pattern(3, 0, [100.1], 2 * DAY)]}
        r = HigherTFFibDetector.detect(by_iv, target, "4h")
        self.assertEqual(r["details"]["source_intervals"], ["1d"])

    def test_cluster_ignores_patterns_completed_after_d(self):
        # Regression: post-processing used every pattern in the DB, including later ones.
        target = fib_pattern(1, 100.0, [], d_ts=10)
        later = [fib_pattern(i, 0, [100.0 + i / 100], d_ts=20 + i) for i in (2, 3, 4)]
        self.assertIsNone(FibClusterDetector.detect([target] + later, 1))
        earlier = [fib_pattern(i, 0, [100.0 + i / 100], d_ts=i) for i in (2, 3, 4)]
        self.assertIsNotNone(FibClusterDetector.detect([target] + earlier, 1))

    def test_higher_tf_fib_needs_the_higher_candle_closed_before_d(self):
        target = fib_pattern(1, 100.0, [], d_ts=10 * DAY)
        same_day = {"1d": [fib_pattern(2, 0, [100.0], 10 * DAY - 3_600_000)]}   # D wyższego TF w tej samej dobie
        self.assertIsNone(HigherTFFibDetector.detect(same_day, target, "4h"))

    def test_merge_confluences_replaces_types(self):
        merged = merge_confluences({"confluences": [{"type": "fib_cluster"}, {"type": "doji"}]},
                                   [{"type": "fib_cluster", "confidence": 1}], replace_types=["fib_cluster"])
        self.assertEqual([c["type"] for c in merged["confluences"]], ["doji", "fib_cluster"])
        self.assertEqual(merged["total_score"], 2)


class TestConfluenceDetector(unittest.TestCase):
    def test_score_counts_results_and_a_failing_detector_does_not_stop_the_rest(self):
        klines = flat(60)
        klines[59] = k(100, 100.5, 94, 100.2, v=1000, t=59 * H)  # hammer + volume spike
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        with mock.patch.object(I, "detect_rsi_oversold", boom):
            result = ConfluenceDetector.detect(klines, points(D=(59, 94.0)), True, 59, interval="1h")
        types = [c["type"] for c in result["confluences"]]
        self.assertIn("hammer", types)
        self.assertIn("volume_spike", types)
        self.assertEqual(result["total_score"], len(types))


class TestHigherTFStructureCausality(unittest.TestCase):
    """HigherTFSRDetector / HigherTFTrendlineDetector: tylko świece zamknięte przed D, kierunek z is_bullish."""

    H = 3_600_000

    def htf_klines(self, prices, start=0, step=4 * 3_600_000):
        return [{"open_time": start + i * step, "open": p, "high": p * 1.001, "low": p * 0.999, "close": p, "volume": 1}
                for i, p in enumerate(prices)]

    def target(self, d_price, d_ts, bullish):
        return {"id": 1, "d_point_timestamp": d_ts,
                "ta_object_json": {"is_bullish": bullish, "points": {"D": {"price": d_price}}}}

    def zigzag(self, lows_at, highs_at, n=120):
        prices = []
        for i in range(n):
            phase = i % 20
            prices.append(lows_at if phase == 0 else highs_at if phase == 10 else (lows_at + highs_at) / 2)
        return prices

    def test_support_zone_built_only_from_candles_before_d(self):
        kl = self.htf_klines(self.zigzag(100.0, 110.0))
        d_ts = kl[-1]["open_time"] + 4 * self.H
        self.assertIsNotNone(HigherTFSRDetector.detect({"4h": kl}, self.target(100.0, d_ts, True), "1h"))
        # Ta sama strefa, ale cała historia wyższego TF jest po D - nic nie było wtedy znane.
        self.assertIsNone(HigherTFSRDetector.detect({"4h": kl}, self.target(100.0, 1, True), "1h"))

    def test_bearish_pattern_looks_for_resistance(self):
        # Regression: direction was read from "bullish" (missing key -> always True).
        kl = self.htf_klines(self.zigzag(100.0, 110.0))
        d_ts = kl[-1]["open_time"] + 4 * self.H
        r = HigherTFSRDetector.detect({"4h": kl}, self.target(110.0, d_ts, False), "1h")
        self.assertEqual(r["type"], "higher_tf_resistance_zone")
        self.assertIsNone(HigherTFSRDetector.detect({"4h": kl}, self.target(100.0, d_ts, False), "1h"))


if __name__ == "__main__":
    unittest.main()
