"""
Wykrywanie formacji świecowych na punkcie D wzorców harmonicznych.

Obsługiwane formacje:
- Hammer (młot) — bullish reversal, 1 świeca
- Shooting Star (spadająca gwiazda) — bearish reversal, 1 świeca
- Morning Star (gwiazda poranna) — bullish reversal, 3 świece
- Evening Star (gwiazda wieczorna) — bearish reversal, 3 świece
- Bullish Engulfing — bullish reversal, 2 świece
- Bearish Engulfing — bearish reversal, 2 świece
- Doji — niezdecydowanie / potencjalny reversal, 1 świeca
- Bullish Pin Bar — bullish reversal, 1 świeca
- Bearish Pin Bar — bearish reversal, 1 świeca
"""

import logging
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Progi konfiguracyjne
WICK_BODY_RATIO = 2.0        # Minimalny stosunek knota do body dla hammer/shooting star
MAX_OPPOSING_WICK_RATIO = 0.3 # Maksymalny stosunek przeciwnego knota do całego range
SMALL_BODY_RATIO = 0.3       # Maksymalny stosunek body do range dla środkowej świecy w star patterns
LARGE_BODY_RATIO = 0.5       # Minimalny stosunek body do range dla zewnętrznych świec w star patterns
DOJI_BODY_RATIO = 0.1        # Maksymalny stosunek body do range dla doji
PIN_BAR_WICK_RATIO = 0.66    # Minimalny stosunek dominującego knota do range dla pin bar


def _candle_metrics(kline: Dict) -> Dict[str, float]:
    """Oblicza metryki świecy: body, upper_wick, lower_wick, range."""
    o = float(kline['open'])
    h = float(kline['high'])
    l = float(kline['low'])
    c = float(kline['close'])

    body = abs(c - o)
    full_range = h - l
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    is_bullish_candle = c > o

    if full_range == 0:
        return {
            'open': o, 'high': h, 'low': l, 'close': c,
            'body': 0, 'range': 0,
            'upper_wick': 0, 'lower_wick': 0,
            'body_ratio': 0, 'upper_wick_ratio': 0, 'lower_wick_ratio': 0,
            'is_bullish_candle': is_bullish_candle,
        }

    return {
        'open': o, 'high': h, 'low': l, 'close': c,
        'body': body,
        'range': full_range,
        'upper_wick': upper_wick,
        'lower_wick': lower_wick,
        'body_ratio': body / full_range,
        'upper_wick_ratio': upper_wick / full_range,
        'lower_wick_ratio': lower_wick / full_range,
        'is_bullish_candle': is_bullish_candle,
    }


class CandlestickPatternDetector:
    """Statyczne metody do wykrywania formacji świecowych wokół punktu D."""

    @staticmethod
    def detect_hammer(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Hammer (młot): dolny knot >= 2x body, górny knot mały.
        Sygnał bullish reversal — szukamy go na D bullish patternów.
        """
        if not is_bullish:
            return None
        if d_index < 0 or d_index >= len(klines):
            return None

        m = _candle_metrics(klines[d_index])
        if m['range'] == 0:
            return None

        if m['body'] == 0:
            has_long_lower = m['lower_wick_ratio'] >= 0.66
            has_small_upper = m['upper_wick_ratio'] <= MAX_OPPOSING_WICK_RATIO
        else:
            has_long_lower = m['lower_wick'] >= WICK_BODY_RATIO * m['body']
            has_small_upper = m['upper_wick_ratio'] <= MAX_OPPOSING_WICK_RATIO

        if not (has_long_lower and has_small_upper):
            return None

        confidence = min(1.0, m['lower_wick_ratio'] / 0.66)

        return {
            'type': 'hammer',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'body_ratio': round(m['body_ratio'], 4),
                'lower_wick_ratio': round(m['lower_wick_ratio'], 4),
                'upper_wick_ratio': round(m['upper_wick_ratio'], 4),
            }
        }

    @staticmethod
    def detect_shooting_star(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Shooting Star (spadająca gwiazda): górny knot >= 2x body, dolny knot mały.
        Sygnał bearish reversal — szukamy go na D bearish patternów.
        """
        if is_bullish:
            return None
        if d_index < 0 or d_index >= len(klines):
            return None

        m = _candle_metrics(klines[d_index])
        if m['range'] == 0:
            return None

        if m['body'] == 0:
            has_long_upper = m['upper_wick_ratio'] >= 0.66
            has_small_lower = m['lower_wick_ratio'] <= MAX_OPPOSING_WICK_RATIO
        else:
            has_long_upper = m['upper_wick'] >= WICK_BODY_RATIO * m['body']
            has_small_lower = m['lower_wick_ratio'] <= MAX_OPPOSING_WICK_RATIO

        if not (has_long_upper and has_small_lower):
            return None

        confidence = min(1.0, m['upper_wick_ratio'] / 0.66)

        return {
            'type': 'shooting_star',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'body_ratio': round(m['body_ratio'], 4),
                'upper_wick_ratio': round(m['upper_wick_ratio'], 4),
                'lower_wick_ratio': round(m['lower_wick_ratio'], 4),
            }
        }

    @staticmethod
    def detect_morning_star(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Morning Star (gwiazda poranna): 3-świecowa formacja bullish reversal.
        Świeca -2: duża bearish | Świeca -1: mała body (doji/spinning top) | Świeca 0 (D): duża bullish.
        Szukamy na D bullish patternów.
        """
        if not is_bullish:
            return None
        if d_index < 2 or d_index >= len(klines):
            return None

        c0 = _candle_metrics(klines[d_index])      # D — powinna być duża bullish
        c1 = _candle_metrics(klines[d_index - 1])   # środkowa — mała body
        c2 = _candle_metrics(klines[d_index - 2])   # pierwsza — duża bearish

        if c0['range'] == 0 or c1['range'] == 0 or c2['range'] == 0:
            return None

        first_is_bearish = not c2['is_bullish_candle'] and c2['body_ratio'] >= LARGE_BODY_RATIO
        middle_is_small = c1['body_ratio'] <= SMALL_BODY_RATIO
        third_is_bullish = c0['is_bullish_candle'] and c0['body_ratio'] >= LARGE_BODY_RATIO

        # Trzecia świeca powinna zamknąć się powyżej środka body pierwszej
        first_midpoint = (c2['open'] + c2['close']) / 2
        third_closes_above_mid = c0['close'] > first_midpoint

        if not (first_is_bearish and middle_is_small and third_is_bullish and third_closes_above_mid):
            return None

        confidence = min(1.0, (c0['body_ratio'] + c2['body_ratio'] + (1 - c1['body_ratio'])) / 2.5)

        return {
            'type': 'morning_star',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'first_body_ratio': round(c2['body_ratio'], 4),
                'middle_body_ratio': round(c1['body_ratio'], 4),
                'third_body_ratio': round(c0['body_ratio'], 4),
            }
        }

    @staticmethod
    def detect_evening_star(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Evening Star (gwiazda wieczorna): 3-świecowa formacja bearish reversal.
        Świeca -2: duża bullish | Świeca -1: mała body | Świeca 0 (D): duża bearish.
        Szukamy na D bearish patternów.
        """
        if is_bullish:
            return None
        if d_index < 2 or d_index >= len(klines):
            return None

        c0 = _candle_metrics(klines[d_index])
        c1 = _candle_metrics(klines[d_index - 1])
        c2 = _candle_metrics(klines[d_index - 2])

        if c0['range'] == 0 or c1['range'] == 0 or c2['range'] == 0:
            return None

        first_is_bullish = c2['is_bullish_candle'] and c2['body_ratio'] >= LARGE_BODY_RATIO
        middle_is_small = c1['body_ratio'] <= SMALL_BODY_RATIO
        third_is_bearish = not c0['is_bullish_candle'] and c0['body_ratio'] >= LARGE_BODY_RATIO

        first_midpoint = (c2['open'] + c2['close']) / 2
        third_closes_below_mid = c0['close'] < first_midpoint

        if not (first_is_bullish and middle_is_small and third_is_bearish and third_closes_below_mid):
            return None

        confidence = min(1.0, (c0['body_ratio'] + c2['body_ratio'] + (1 - c1['body_ratio'])) / 2.5)

        return {
            'type': 'evening_star',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'first_body_ratio': round(c2['body_ratio'], 4),
                'middle_body_ratio': round(c1['body_ratio'], 4),
                'third_body_ratio': round(c0['body_ratio'], 4),
            }
        }

    # ──────────────────────────────────────────────
    # Engulfing (2-świecowe)
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_bullish_engulfing(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Bullish Engulfing: poprzednia świeca bearish, bieżąca (D) bullish pochłania ją całkowicie.
        open(D) <= close(prev), close(D) >= open(prev).
        """
        if not is_bullish:
            return None
        if d_index < 1 or d_index >= len(klines):
            return None

        curr = _candle_metrics(klines[d_index])
        prev = _candle_metrics(klines[d_index - 1])

        if curr['range'] == 0 or prev['range'] == 0:
            return None

        prev_is_bearish = not prev['is_bullish_candle'] and prev['body'] > 0
        curr_is_bullish = curr['is_bullish_candle'] and curr['body'] > 0

        if not (prev_is_bearish and curr_is_bullish):
            return None

        # Body bieżącej pochłania body poprzedniej
        engulfs = curr['open'] <= prev['close'] and curr['close'] >= prev['open']
        if not engulfs:
            return None

        # Confidence na podstawie proporcji body bieżącej do poprzedniej
        body_ratio = curr['body'] / max(1e-10, prev['body'])
        confidence = min(1.0, body_ratio / 2.0)

        return {
            'type': 'bullish_engulfing',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'curr_body_ratio': round(curr['body_ratio'], 4),
                'prev_body_ratio': round(prev['body_ratio'], 4),
                'engulfing_ratio': round(body_ratio, 4),
            }
        }

    @staticmethod
    def detect_bearish_engulfing(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Bearish Engulfing: poprzednia świeca bullish, bieżąca (D) bearish pochłania ją całkowicie.
        open(D) >= close(prev), close(D) <= open(prev).
        """
        if is_bullish:
            return None
        if d_index < 1 or d_index >= len(klines):
            return None

        curr = _candle_metrics(klines[d_index])
        prev = _candle_metrics(klines[d_index - 1])

        if curr['range'] == 0 or prev['range'] == 0:
            return None

        prev_is_bullish = prev['is_bullish_candle'] and prev['body'] > 0
        curr_is_bearish = not curr['is_bullish_candle'] and curr['body'] > 0

        if not (prev_is_bullish and curr_is_bearish):
            return None

        engulfs = curr['open'] >= prev['close'] and curr['close'] <= prev['open']
        if not engulfs:
            return None

        body_ratio = curr['body'] / max(1e-10, prev['body'])
        confidence = min(1.0, body_ratio / 2.0)

        return {
            'type': 'bearish_engulfing',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'curr_body_ratio': round(curr['body_ratio'], 4),
                'prev_body_ratio': round(prev['body_ratio'], 4),
                'engulfing_ratio': round(body_ratio, 4),
            }
        }

    # ──────────────────────────────────────────────
    # Doji (1-świecowa)
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_doji(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Doji: bardzo małe body (< 10% range) — sygnał niezdecydowania / potencjalnego odwrócenia.
        Działa zarówno na bullish jak i bearish patternach.
        """
        if d_index < 0 or d_index >= len(klines):
            return None

        m = _candle_metrics(klines[d_index])
        if m['range'] == 0:
            return None

        if m['body_ratio'] > DOJI_BODY_RATIO:
            return None

        # Im mniejsze body, tym silniejszy sygnał doji
        confidence = min(1.0, (DOJI_BODY_RATIO - m['body_ratio']) / DOJI_BODY_RATIO)

        # Podtyp doji na podstawie proporcji knotów
        if m['upper_wick_ratio'] > 0.4 and m['lower_wick_ratio'] > 0.4:
            doji_subtype = 'long_legged'
        elif m['upper_wick_ratio'] > 0.6:
            doji_subtype = 'gravestone'
        elif m['lower_wick_ratio'] > 0.6:
            doji_subtype = 'dragonfly'
        else:
            doji_subtype = 'standard'

        return {
            'type': 'doji',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'body_ratio': round(m['body_ratio'], 4),
                'upper_wick_ratio': round(m['upper_wick_ratio'], 4),
                'lower_wick_ratio': round(m['lower_wick_ratio'], 4),
                'doji_subtype': doji_subtype,
            }
        }

    # ──────────────────────────────────────────────
    # Pin Bar (1-świecowa)
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_bullish_pin_bar(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Bullish Pin Bar: długi dolny knot (>= 66% range), małe body w górnej 1/3 range.
        Niezależny od koloru świecy (bullish lub bearish candle).
        Szukamy na D bullish patternów.
        """
        if not is_bullish:
            return None
        if d_index < 0 or d_index >= len(klines):
            return None

        m = _candle_metrics(klines[d_index])
        if m['range'] == 0:
            return None

        has_long_lower = m['lower_wick_ratio'] >= PIN_BAR_WICK_RATIO
        # Body w górnej 1/3 range
        body_top = max(m['open'], m['close'])
        body_center = (m['open'] + m['close']) / 2
        upper_third_threshold = m['low'] + m['range'] * 0.66
        body_in_upper_third = body_center >= upper_third_threshold
        small_upper_wick = m['upper_wick_ratio'] <= 0.25

        if not (has_long_lower and body_in_upper_third and small_upper_wick):
            return None

        confidence = min(1.0, m['lower_wick_ratio'] / 0.75)

        return {
            'type': 'bullish_pin_bar',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'body_ratio': round(m['body_ratio'], 4),
                'lower_wick_ratio': round(m['lower_wick_ratio'], 4),
                'upper_wick_ratio': round(m['upper_wick_ratio'], 4),
                'is_bullish_candle': m['is_bullish_candle'],
            }
        }

    @staticmethod
    def detect_bearish_pin_bar(klines: List[Dict], d_index: int, is_bullish: bool) -> Optional[Dict]:
        """
        Bearish Pin Bar: długi górny knot (>= 66% range), małe body w dolnej 1/3 range.
        Niezależny od koloru świecy.
        Szukamy na D bearish patternów.
        """
        if is_bullish:
            return None
        if d_index < 0 or d_index >= len(klines):
            return None

        m = _candle_metrics(klines[d_index])
        if m['range'] == 0:
            return None

        has_long_upper = m['upper_wick_ratio'] >= PIN_BAR_WICK_RATIO
        body_center = (m['open'] + m['close']) / 2
        lower_third_threshold = m['low'] + m['range'] * 0.33
        body_in_lower_third = body_center <= lower_third_threshold
        small_lower_wick = m['lower_wick_ratio'] <= 0.25

        if not (has_long_upper and body_in_lower_third and small_lower_wick):
            return None

        confidence = min(1.0, m['upper_wick_ratio'] / 0.75)

        return {
            'type': 'bearish_pin_bar',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'body_ratio': round(m['body_ratio'], 4),
                'upper_wick_ratio': round(m['upper_wick_ratio'], 4),
                'lower_wick_ratio': round(m['lower_wick_ratio'], 4),
                'is_bullish_candle': m['is_bullish_candle'],
            }
        }
