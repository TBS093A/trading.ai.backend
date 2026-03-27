"""
Wykrywanie konfluencji wskaźnikowych (RSI, MACD) na punkcie D wzorców harmonicznych.

Wskaźniki są obliczane wewnętrznie — detektor nie wymaga zewnętrznych obliczeń.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

CROSSOVER_LOOKBACK = 3


def _calculate_rsi(klines: List[Dict], period: int = RSI_PERIOD) -> List[Optional[float]]:
    """Oblicza RSI i zwraca listę wartości (None dla pierwszych `period` świec)."""
    if len(klines) < period + 1:
        return [None] * len(klines)

    closes = np.array([float(k['close']) for k in klines])
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    rsi = [None] * (period + 1)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100.0 - (100.0 / (1.0 + rs)))

    return rsi


def _calculate_ema(data: np.ndarray, period: int) -> np.ndarray:
    alpha = 2.0 / (period + 1)
    ema = np.zeros_like(data, dtype=float)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def _calculate_macd(
    klines: List[Dict],
    fast: int = MACD_FAST,
    slow: int = MACD_SLOW,
    signal: int = MACD_SIGNAL,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zwraca (macd_line, signal_line, histogram) jako numpy arrays o długości len(klines)."""
    closes = np.array([float(k['close']) for k in klines])
    ema_fast = _calculate_ema(closes, fast)
    ema_slow = _calculate_ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


class IndicatorConfluenceDetector:
    """Detektory konfluencji oparte na RSI i MACD."""

    # ──────────────────────────────────────────────
    # RSI
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_rsi_oversold(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """RSI < 30 na świecy D → potwierdza bullish reversal."""
        if not is_bullish:
            return None

        rsi = _calculate_rsi(klines)
        rsi_d = rsi[d_index] if d_index < len(rsi) else None
        if rsi_d is None:
            return None
        if rsi_d >= RSI_OVERSOLD:
            return None

        confidence = min(1.0, (RSI_OVERSOLD - rsi_d) / RSI_OVERSOLD)

        return {
            'type': 'rsi_oversold',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'rsi_value': round(rsi_d, 2),
                'threshold': RSI_OVERSOLD,
            },
        }

    @staticmethod
    def detect_rsi_overbought(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """RSI > 70 na świecy D → potwierdza bearish reversal."""
        if is_bullish:
            return None

        rsi = _calculate_rsi(klines)
        rsi_d = rsi[d_index] if d_index < len(rsi) else None
        if rsi_d is None:
            return None
        if rsi_d <= RSI_OVERBOUGHT:
            return None

        confidence = min(1.0, (rsi_d - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT))

        return {
            'type': 'rsi_overbought',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'rsi_value': round(rsi_d, 2),
                'threshold': RSI_OVERBOUGHT,
            },
        }

    @staticmethod
    def detect_rsi_divergence(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        RSI divergence między punktami patternu a D.

        Bullish: cena D <= cena ref (X lub B) ale RSI(D) > RSI(ref) → bullish divergence.
        Bearish: cena D >= cena ref ale RSI(D) < RSI(ref) → bearish divergence.
        """
        if pattern_points is None:
            return None

        rsi = _calculate_rsi(klines)
        rsi_d = rsi[d_index] if d_index < len(rsi) else None
        if rsi_d is None:
            return None

        # Punkty referencyjne do porównania (dołki dla bullish, szczyty dla bearish)
        if is_bullish:
            ref_points = ['X', 'B']
        else:
            ref_points = ['X', 'B']

        best_divergence = None

        for ref_name in ref_points:
            if ref_name not in pattern_points:
                continue
            ref = pattern_points[ref_name]
            ref_idx = ref['index']
            ref_price = ref['price']
            ref_rsi = rsi[ref_idx] if ref_idx < len(rsi) else None
            if ref_rsi is None:
                continue

            d_price = float(klines[d_index]['close'])

            if is_bullish:
                # Bullish divergence: cena robi niższy dołek, RSI robi wyższy dołek
                price_lower = d_price <= ref_price
                rsi_higher = rsi_d > ref_rsi
                if price_lower and rsi_higher:
                    strength = (rsi_d - ref_rsi) / max(1, abs(ref_rsi))
                    confidence = min(1.0, abs(strength))
                    candidate = {
                        'type': 'rsi_bullish_divergence',
                        'confidence': round(confidence, 3),
                        'candle_index': d_index,
                        'details': {
                            'reference_point': ref_name,
                            'rsi_d': round(rsi_d, 2),
                            'rsi_ref': round(ref_rsi, 2),
                            'price_d': round(d_price, 6),
                            'price_ref': round(ref_price, 6),
                        },
                    }
                    if best_divergence is None or confidence > best_divergence['confidence']:
                        best_divergence = candidate
            else:
                # Bearish divergence: cena robi wyższy szczyt, RSI robi niższy szczyt
                price_higher = d_price >= ref_price
                rsi_lower = rsi_d < ref_rsi
                if price_higher and rsi_lower:
                    strength = (ref_rsi - rsi_d) / max(1, abs(ref_rsi))
                    confidence = min(1.0, abs(strength))
                    candidate = {
                        'type': 'rsi_bearish_divergence',
                        'confidence': round(confidence, 3),
                        'candle_index': d_index,
                        'details': {
                            'reference_point': ref_name,
                            'rsi_d': round(rsi_d, 2),
                            'rsi_ref': round(ref_rsi, 2),
                            'price_d': round(d_price, 6),
                            'price_ref': round(ref_price, 6),
                        },
                    }
                    if best_divergence is None or confidence > best_divergence['confidence']:
                        best_divergence = candidate

        return best_divergence

    # ──────────────────────────────────────────────
    # MACD
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_macd_crossover(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        MACD crossover w okolicach D (±CROSSOVER_LOOKBACK świec).

        Bullish: MACD przecina sygnał w górę.
        Bearish: MACD przecina sygnał w dół.
        """
        if len(klines) < MACD_SLOW + MACD_SIGNAL:
            return None

        macd_line, signal_line, _ = _calculate_macd(klines)

        start = max(1, d_index - CROSSOVER_LOOKBACK)
        end = min(len(klines), d_index + CROSSOVER_LOOKBACK + 1)

        best_cross = None

        for i in range(start, end):
            prev_diff = macd_line[i - 1] - signal_line[i - 1]
            curr_diff = macd_line[i] - signal_line[i]

            if is_bullish and prev_diff <= 0 and curr_diff > 0:
                distance = abs(i - d_index)
                confidence = max(0.3, 1.0 - distance * 0.2)
                candidate = {
                    'type': 'macd_bullish_crossover',
                    'confidence': round(confidence, 3),
                    'candle_index': i,
                    'details': {
                        'macd_value': round(float(macd_line[i]), 6),
                        'signal_value': round(float(signal_line[i]), 6),
                        'distance_from_d': distance,
                    },
                }
                if best_cross is None or confidence > best_cross['confidence']:
                    best_cross = candidate

            elif not is_bullish and prev_diff >= 0 and curr_diff < 0:
                distance = abs(i - d_index)
                confidence = max(0.3, 1.0 - distance * 0.2)
                candidate = {
                    'type': 'macd_bearish_crossover',
                    'confidence': round(confidence, 3),
                    'candle_index': i,
                    'details': {
                        'macd_value': round(float(macd_line[i]), 6),
                        'signal_value': round(float(signal_line[i]), 6),
                        'distance_from_d': distance,
                    },
                }
                if best_cross is None or confidence > best_cross['confidence']:
                    best_cross = candidate

        return best_cross

    @staticmethod
    def detect_macd_histogram_reversal(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Odwrócenie histogramu MACD w okolicach D.

        Bullish: histogram przechodzi z ujemnego w dodatni LUB zmniejsza się (staje się mniej ujemny).
        Bearish: histogram przechodzi z dodatniego w ujemny LUB zmniejsza się (staje się mniej dodatni).
        """
        if len(klines) < MACD_SLOW + MACD_SIGNAL:
            return None
        if d_index < 2 or d_index >= len(klines):
            return None

        _, _, histogram = _calculate_macd(klines)

        h_d = histogram[d_index]
        h_prev = histogram[d_index - 1]
        h_prev2 = histogram[d_index - 2]

        if is_bullish:
            # Zmiana znaku z - na + lub malejąca ujemność (trend do góry)
            sign_change = h_prev <= 0 and h_d > 0
            shrinking = h_prev2 < h_prev < 0 and h_prev < h_d
            if not (sign_change or shrinking):
                return None
            confidence = 0.9 if sign_change else 0.5
        else:
            sign_change = h_prev >= 0 and h_d < 0
            shrinking = h_prev2 > h_prev > 0 and h_prev > h_d
            if not (sign_change or shrinking):
                return None
            confidence = 0.9 if sign_change else 0.5

        return {
            'type': 'macd_histogram_reversal',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'histogram_d': round(float(h_d), 6),
                'histogram_prev': round(float(h_prev), 6),
                'histogram_prev2': round(float(h_prev2), 6),
                'sign_change': bool(sign_change),
            },
        }

    @staticmethod
    def detect_macd_divergence(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        MACD divergence między punktami patternu a D.

        Bullish: cena D <= cena ref ale MACD(D) > MACD(ref) → bullish divergence.
        Bearish: cena D >= cena ref ale MACD(D) < MACD(ref) → bearish divergence.
        """
        if pattern_points is None:
            return None
        if len(klines) < MACD_SLOW + MACD_SIGNAL:
            return None

        macd_line, _, _ = _calculate_macd(klines)

        ref_points = ['X', 'B']
        best_divergence = None

        macd_d = float(macd_line[d_index]) if d_index < len(macd_line) else None
        if macd_d is None:
            return None

        for ref_name in ref_points:
            if ref_name not in pattern_points:
                continue
            ref = pattern_points[ref_name]
            ref_idx = ref['index']
            ref_price = ref['price']

            if ref_idx >= len(macd_line):
                continue
            macd_ref = float(macd_line[ref_idx])

            d_price = float(klines[d_index]['close'])

            if is_bullish:
                price_lower = d_price <= ref_price
                macd_higher = macd_d > macd_ref
                if price_lower and macd_higher:
                    strength = abs(macd_d - macd_ref) / max(1e-10, abs(macd_ref))
                    confidence = min(1.0, strength)
                    candidate = {
                        'type': 'macd_bullish_divergence',
                        'confidence': round(confidence, 3),
                        'candle_index': d_index,
                        'details': {
                            'reference_point': ref_name,
                            'macd_d': round(macd_d, 6),
                            'macd_ref': round(macd_ref, 6),
                            'price_d': round(d_price, 6),
                            'price_ref': round(ref_price, 6),
                        },
                    }
                    if best_divergence is None or confidence > best_divergence['confidence']:
                        best_divergence = candidate
            else:
                price_higher = d_price >= ref_price
                macd_lower = macd_d < macd_ref
                if price_higher and macd_lower:
                    strength = abs(macd_ref - macd_d) / max(1e-10, abs(macd_ref))
                    confidence = min(1.0, strength)
                    candidate = {
                        'type': 'macd_bearish_divergence',
                        'confidence': round(confidence, 3),
                        'candle_index': d_index,
                        'details': {
                            'reference_point': ref_name,
                            'macd_d': round(macd_d, 6),
                            'macd_ref': round(macd_ref, 6),
                            'price_d': round(d_price, 6),
                            'price_ref': round(ref_price, 6),
                        },
                    }
                    if best_divergence is None or confidence > best_divergence['confidence']:
                        best_divergence = candidate

        return best_divergence
