"""
Unit testy FibonacciTargets - PRZ/SL/TP po właściwej stronie wejścia (D) dla każdego wzorca
w obu kierunkach: bullish SL < D < TP1 <= TP2, bearish SL > D > TP1 >= TP2. Bez bazy i sieci.
"""

import unittest

from src.technical_analysis.technical_analysis_objects.tao_fibonacci_all_harmonic_pattern_points_levels import (
    FibonacciAllHarmonicPatternPointsLevels,
)
from src.technical_analysis.technical_analysis_objects.tao_fibonacci_targets import FibonacciTargets

X, A = 1000.0, 1100.0  # bullish: X dołek, A szczyt; XA = 100
XA = A - X


def retrace(start, end, ratio):
    return end - (end - start) * ratio


def bull_points(b_xa, c, d_xa):
    """B jako retracement XA, C podane wprost, D jako retracement XA (> 1 = za X)."""
    return {"X": X, "A": A, "B": retrace(X, A, b_xa), "C": c, "D": retrace(X, A, d_xa)}


def bc(b_xa, ab_ratio):
    """C jako retracement AB (ab_ratio > 1 = C za A)."""
    b = retrace(X, A, b_xa)
    return retrace(A, b, ab_ratio)


# Kanoniczne geometrie bullish (pyharmonics XABCD); bearish = lustro.
BULLISH = {
    "gartley": bull_points(0.618, bc(0.618, 0.618), 0.786),
    "bat": bull_points(0.5, bc(0.5, 0.5), 0.886),
    "alt bat": bull_points(0.382, bc(0.382, 0.5), 1.13),
    "butterfly": bull_points(0.786, bc(0.786, 0.618), 1.272),
    "deep butterfly": bull_points(0.786, bc(0.786, 0.618), 1.414),
    "crab": bull_points(0.5, bc(0.5, 0.618), 1.618),
    "deep crab": bull_points(0.886, bc(0.886, 0.5), 1.618),
    "shark": bull_points(0.5, bc(0.5, 1.3), 0.886),
    "deep shark": bull_points(0.618, bc(0.618, 1.3), 1.13),
    "cypher": {"X": X, "A": A, "B": retrace(X, A, 0.5), "C": X + 1.272 * XA,
               "D": retrace(X, X + 1.272 * XA, 0.786)},
    "bartley": bull_points(0.618, bc(0.618, 0.618), 0.886),
    "five-0": {"X": X, "A": A, "B": 1050.0, "C": 1075.0, "D": 1062.5},
    "unknown pattern": bull_points(0.618, bc(0.618, 0.618), 0.786),
}
MIRROR = 2 * A  # bearish: cena -> MIRROR - cena (wszystko zostaje dodatnie)


def to_points(prices):
    return {n: {"index": i * 10, "price": p} for i, (n, p) in enumerate(prices.items())}


def calc(pattern, prices, is_bullish, with_all_fibos=True):
    """Jak harmonic_setups.app_targets: poziomy wszystkich par punktów + FibonacciTargets."""
    pp = to_points(prices)
    all_fibos = None
    if with_all_fibos:
        levels = FibonacciAllHarmonicPatternPointsLevels()
        levels.calculate([], pattern_points=pp)
        all_fibos = levels.calculated_data
    targets = FibonacciTargets()
    targets.calculate([], pattern_points=pp, pattern_type=pattern, all_fibos=all_fibos, is_bullish=is_bullish)
    return targets.calculated_data


def cases():
    for pattern, prices in BULLISH.items():
        yield pattern, prices, True
        yield pattern, {n: MIRROR - p for n, p in prices.items()}, False


class TestFibonacciTargetsDirection(unittest.TestCase):

    def assert_valid(self, t, prices, is_bullish, check_x=True):
        sign = 1 if is_bullish else -1
        d = prices["D"]
        self.assertIn("SL", t)
        self.assertIn("TP1", t)
        sl, tp1 = t["SL"]["price"], t["TP1"]["price"]
        self.assertGreater(sign * (d - sl), 0, f"SL {sl} not beyond D {d}")
        self.assertGreater(sign * (tp1 - d), 0, f"TP1 {tp1} not on the profit side of D {d}")
        prev = tp1
        for name in ("TP2", "TP3"):
            if name in t:
                tp = t[name]["price"]
                self.assertGreaterEqual(sign * (tp - prev), 0, f"{name} {tp} before previous TP {prev}")
                prev = tp
        prz = t.get("PRZ")
        if prz:
            far = (prz["min_price"] if is_bullish else prz["max_price"]) if prz["type"] == "zone" else prz["price"]
            self.assertGreaterEqual(sign * (far - sl), 0, f"SL {sl} inside PRZ (far edge {far})")
            near = (prz["max_price"] if is_bullish else prz["min_price"]) if prz["type"] == "zone" else prz["price"]
            self.assertGreater(sign * (prices["A"] - near), 0, f"PRZ {prz} on the A side of the pattern")
        if check_x:
            self.assertGreaterEqual(sign * (prices["X"] - sl), 0, f"SL {sl} not beyond X {prices['X']}")

    def test_every_pattern_both_directions(self):
        for pattern, prices, is_bullish in cases():
            for with_all_fibos in (True, False):
                with self.subTest(pattern=pattern, bullish=is_bullish, all_fibos=with_all_fibos):
                    t = calc(pattern, prices, is_bullish, with_all_fibos)
                    # Five-0: SL za D (bufor), D leży nad X - X nie jest punktem odniesienia
                    self.assert_valid(t, prices, is_bullish, check_x=pattern != "five-0")

    def test_bearish_is_exact_mirror_of_bullish(self):
        for pattern, prices in BULLISH.items():
            with self.subTest(pattern=pattern):
                bull = calc(pattern, prices, True)
                bear = calc(pattern, {n: MIRROR - p for n, p in prices.items()}, False)
                self.assertEqual(set(bull), set(bear))
                for name in bull:
                    if bull[name]["type"] == "line":
                        self.assertAlmostEqual(bear[name]["price"], MIRROR - bull[name]["price"], places=6)
                    else:
                        self.assertAlmostEqual(bear[name]["min_price"], MIRROR - bull[name]["max_price"], places=6)
                        self.assertAlmostEqual(bear[name]["max_price"], MIRROR - bull[name]["min_price"], places=6)

    def test_entry_beyond_structure_still_gets_sl_beyond_entry(self):
        # app_targets podstawia D = cena wejścia; może ona przebić X i całe PRZ
        for pattern, prices, is_bullish in cases():
            sign = 1 if is_bullish else -1
            moved = dict(prices, D=prices["D"] - sign * 5 * XA)
            with self.subTest(pattern=pattern, bullish=is_bullish):
                self.assert_valid(calc(pattern, moved, is_bullish), moved, is_bullish, check_x=False)

    def test_regression_bullish_deep_butterfly(self):
        # Zaobserwowane: bullish deep butterfly, D = 63285.6 -> SL 71286.2 (nad wejściem)
        prices = {"X": 66000.0, "A": 72000.0, "B": 67284.0, "C": 70200.0, "D": 63285.6}
        t = calc("deep butterfly", prices, True)
        self.assertLess(t["SL"]["price"], 63285.6)
        self.assertGreater(t["TP1"]["price"], 63285.6)
        self.assertLess(t["PRZ"]["max_price"], prices["X"])

    def test_known_levels(self):
        # Gartley bullish: SL = X, TP1 = 61.8% AD, TP2 = A, PRZ = 0.786 XA
        prices = BULLISH["gartley"]
        t = calc("Gartley", prices, True)
        self.assertAlmostEqual(t["SL"]["price"], X)
        self.assertAlmostEqual(t["PRZ"]["price"], retrace(X, A, 0.786))
        self.assertAlmostEqual(t["TP1"]["price"], retrace(A, prices["D"], 0.618))
        self.assertAlmostEqual(t["TP2"]["price"], A)
        # Crab bullish: PRZ zawiera 1.618 XA (pod X); D leży na dalszej krawędzi PRZ,
        # więc SL nie może być na niej (= wejście) - idzie za D o bufor
        crab = calc("crab", BULLISH["crab"], True)
        self.assertAlmostEqual(crab["PRZ"]["min_price"], retrace(X, A, 1.618))
        self.assertAlmostEqual(crab["SL"]["price"],
                               BULLISH["crab"]["D"] - XA * FibonacciTargets.SL_FALLBACK_BUFFER)
        # Ta sama geometria z D w środku PRZ: SL na dalszej krawędzi PRZ
        inside = dict(BULLISH["crab"], D=retrace(X, A, 1.5))
        crab = calc("crab", inside, True)
        self.assertAlmostEqual(crab["SL"]["price"], crab["PRZ"]["min_price"])

    def test_pattern_name_variants(self):
        prices = BULLISH["deep shark"]
        expected = calc("deep shark", prices, True)
        for name in ("Deep Shark", "deep_shark", "DEEP-SHARK", "deepshark"):
            with self.subTest(name=name):
                self.assertEqual(calc(name, prices, True), expected)

    def test_direction_inferred_when_missing(self):
        prices = {n: MIRROR - p for n, p in BULLISH["bat"].items()}
        self.assertEqual(calc("bat", prices, None), calc("bat", prices, False))

    def test_no_d_returns_empty(self):
        prices = {n: p for n, p in BULLISH["bat"].items() if n != "D"}
        self.assertEqual(calc("bat", prices, True), {})


if __name__ == "__main__":
    unittest.main()
