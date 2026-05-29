"""
Konfluencje strukturalne na punkcie D wzorców harmonicznych.

Inline (same-interval):
- Support/Resistance — D na historycznym wsparciu/oporze
- Trend Line — D dotyka linii trendu (regresja na swing pointach)
- Round Levels (psychologiczne) — D blisko okrągłego poziomu
- Pivot Points — D na dziennym/tygodniowym pivocie

Post-processing (cross-timeframe):
- HigherTFSRDetector — D na S/R z wyższego timeframe'u
- HigherTFTrendlineDetector — D na linii trendu z wyższego timeframe'u
"""

import logging
import math
import numpy as np
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .fib_confluences import (
    INTERVAL_HIERARCHY, HIGHER_TF_CONFIDENCE_MAP, _get_d_price,
)

logger = logging.getLogger(__name__)

SR_SWING_LOOKBACK = 5       # Ile świec po obu stronach do wykrycia swing high/low
SR_CLUSTER_PCT = 0.3        # Tolerancja klastrowania S/R (% ceny)
SR_MIN_TOUCHES = 2          # Minimum dotknięć żeby stworzyć strefę S/R
SR_TOLERANCE_PCT = 0.5      # Tolerancja D vs strefa S/R
TRENDLINE_MIN_POINTS = 3    # Minimum swing pointów do regresji
TRENDLINE_TOLERANCE_PCT = 0.5
ROUND_LEVEL_TOLERANCE_PCT = 0.3
PIVOT_TOLERANCE_PCT = 0.3

INTRADAY_INTERVALS = {'1m', '15m', '30m', '1h', '4h'}


def _find_swing_points(
    klines: List[Dict], lookback: int = SR_SWING_LOOKBACK,
) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
    """
    Znajduje swing highs i swing lows.
    Zwraca (swing_highs[(index, price)], swing_lows[(index, price)]).
    """
    highs = np.array([float(k['high']) for k in klines])
    lows = np.array([float(k['low']) for k in klines])
    n = len(klines)

    swing_highs: List[Tuple[int, float]] = []
    swing_lows: List[Tuple[int, float]] = []

    for i in range(lookback, n - lookback):
        window_highs = highs[i - lookback: i + lookback + 1]
        if highs[i] == np.max(window_highs):
            swing_highs.append((i, float(highs[i])))

        window_lows = lows[i - lookback: i + lookback + 1]
        if lows[i] == np.min(window_lows):
            swing_lows.append((i, float(lows[i])))

    return swing_highs, swing_lows


def _cluster_levels(
    points: List[Tuple[int, float]], cluster_pct: float = SR_CLUSTER_PCT,
) -> List[Dict]:
    """
    Grupuje swing points w strefy cenowe (klastry).
    Zwraca listę {price, touches, indices}.
    """
    if not points:
        return []

    sorted_pts = sorted(points, key=lambda x: x[1])
    clusters: List[Dict] = []
    current_cluster = [sorted_pts[0]]

    for i in range(1, len(sorted_pts)):
        ref_price = current_cluster[0][1]
        if ref_price == 0:
            current_cluster.append(sorted_pts[i])
            continue
        deviation = abs(sorted_pts[i][1] - ref_price) / abs(ref_price) * 100
        if deviation <= cluster_pct:
            current_cluster.append(sorted_pts[i])
        else:
            if len(current_cluster) >= SR_MIN_TOUCHES:
                prices = [p[1] for p in current_cluster]
                clusters.append({
                    'price': sum(prices) / len(prices),
                    'touches': len(current_cluster),
                    'indices': [p[0] for p in current_cluster],
                })
            current_cluster = [sorted_pts[i]]

    if len(current_cluster) >= SR_MIN_TOUCHES:
        prices = [p[1] for p in current_cluster]
        clusters.append({
            'price': sum(prices) / len(prices),
            'touches': len(current_cluster),
            'indices': [p[0] for p in current_cluster],
        })

    return clusters


def _within_tolerance(target: float, candidate: float, tolerance_pct: float) -> bool:
    if target == 0:
        return False
    return abs(candidate - target) / abs(target) * 100 <= tolerance_pct


def _get_round_levels_near(price: float) -> List[Tuple[float, str]]:
    """
    Generuje okrągłe poziomy w okolicach danej ceny.
    Zwraca [(level, label), ...].
    """
    if price <= 0:
        return []

    magnitude = 10 ** math.floor(math.log10(price))
    steps = [
        magnitude * 10,
        magnitude * 5,
        magnitude * 2,
        magnitude,
        magnitude * 0.5,
        magnitude * 0.25,
    ]

    levels = []
    for step in steps:
        if step < price * 0.001:
            continue
        nearest = round(price / step) * step
        for offset in [-1, 0, 1]:
            lvl = nearest + offset * step
            if lvl > 0:
                levels.append((lvl, f"{lvl:g}"))

    # Deduplikuj
    seen = set()
    unique = []
    for lvl, label in levels:
        rounded = round(lvl, 8)
        if rounded not in seen:
            seen.add(rounded)
            unique.append((lvl, label))

    return unique


def _calculate_pivot_points(
    prev_high: float, prev_low: float, prev_close: float,
) -> Dict[str, float]:
    """Standard Pivot Points: P, S1, S2, S3, R1, R2, R3."""
    p = (prev_high + prev_low + prev_close) / 3
    return {
        'P': p,
        'S1': 2 * p - prev_high,
        'S2': p - (prev_high - prev_low),
        'S3': prev_low - 2 * (prev_high - p),
        'R1': 2 * p - prev_low,
        'R2': p + (prev_high - prev_low),
        'R3': prev_high + 2 * (p - prev_low),
    }


def _get_previous_period_ohlc(
    klines: List[Dict], d_index: int, interval: str,
) -> Optional[Dict[str, float]]:
    """
    Oblicza OHLC poprzedniego okresu (dzień dla intraday, tydzień dla daily+).
    """
    if not klines or d_index < 1:
        return None

    use_daily = interval in INTRADAY_INTERVALS

    d_time_ms = klines[d_index].get('open_time', 0)
    if d_time_ms == 0:
        return None

    d_dt = datetime.fromtimestamp(d_time_ms / 1000)

    if use_daily:
        d_date = d_dt.date()
        prev_candles = []
        for i in range(d_index):
            t = klines[i].get('open_time', 0)
            if t == 0:
                continue
            dt = datetime.fromtimestamp(t / 1000)
            if dt.date() < d_date:
                prev_candles.append(klines[i])
        # Weź tylko świece z ostatniego pełnego dnia
        if not prev_candles:
            return None
        last_date = datetime.fromtimestamp(prev_candles[-1]['open_time'] / 1000).date()
        day_candles = [c for c in prev_candles
                       if datetime.fromtimestamp(c['open_time'] / 1000).date() == last_date]
    else:
        # Dla daily+ weź ostatnie 5-7 świec jako "tydzień"
        lookback = min(7, d_index)
        day_candles = klines[d_index - lookback: d_index]

    if not day_candles:
        return None

    return {
        'high': max(float(c['high']) for c in day_candles),
        'low': min(float(c['low']) for c in day_candles),
        'close': float(day_candles[-1]['close']),
        'open': float(day_candles[0]['open']),
    }


class StructuralConfluenceDetector:
    """Detektory konfluencji strukturalnych: S/R, trendline, round levels, pivot points."""

    # ──────────────────────────────────────────────
    # Support / Resistance
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_support_resistance(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Sprawdza czy D wypada na historycznej strefie wsparcia (bullish) lub oporu (bearish).
        Strefy budowane ze swing pointów sklasteryzowanych cenowo.
        """
        if d_index < SR_SWING_LOOKBACK * 2:
            return None

        d_price = float(klines[d_index]['close'])
        if d_price == 0:
            return None

        swing_highs, swing_lows = _find_swing_points(klines[:d_index])

        if is_bullish:
            # Bullish: szukamy wsparcia (swing lows)
            zones = _cluster_levels(swing_lows)
            zone_type = 'support'
        else:
            # Bearish: szukamy oporu (swing highs)
            zones = _cluster_levels(swing_highs)
            zone_type = 'resistance'

        if not zones:
            return None

        best_zone = None
        best_dev = float('inf')

        for zone in zones:
            if _within_tolerance(d_price, zone['price'], SR_TOLERANCE_PCT):
                dev = abs(d_price - zone['price']) / abs(d_price) * 100
                if dev < best_dev:
                    best_dev = dev
                    best_zone = zone

        if best_zone is None:
            return None

        confidence = min(1.0, best_zone['touches'] / 5.0)
        proximity_bonus = max(0, (SR_TOLERANCE_PCT - best_dev) / SR_TOLERANCE_PCT * 0.2)
        confidence = min(1.0, confidence + proximity_bonus)
        # Same-interval S/R — obniżony confidence (cross-TF wersja ma pełny)
        confidence = round(confidence * 0.6, 3)

        return {
            'type': f'{zone_type}_zone',
            'confidence': confidence,
            'candle_index': d_index,
            'details': {
                'zone_price': round(best_zone['price'], 6),
                'touches': best_zone['touches'],
                'deviation_pct': round(best_dev, 4),
                'd_price': round(d_price, 6),
                'zone_type': zone_type,
                'source': 'same_interval',
            },
        }

    # ──────────────────────────────────────────────
    # Trend Line
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_trendline(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Regresja liniowa na swing pointach → linia trendu (timestamp-based).
        Bullish: linia trendu wsparcia (swing lows).
        Bearish: linia trendu oporu (swing highs).
        Sprawdza czy D wypada blisko tej linii.
        Używa open_time (ms) jako osi X — umożliwia ekstrapolację cross-TF.
        """
        if d_index < SR_SWING_LOOKBACK * 2 + TRENDLINE_MIN_POINTS:
            return None

        d_price = float(klines[d_index]['close'])
        if d_price == 0:
            return None

        d_timestamp = float(klines[d_index].get('open_time', 0))
        if d_timestamp == 0:
            return None

        swing_highs, swing_lows = _find_swing_points(klines[:d_index])

        if is_bullish:
            points = swing_lows
            line_type = 'support_trendline'
        else:
            points = swing_highs
            line_type = 'resistance_trendline'

        if len(points) < TRENDLINE_MIN_POINTS:
            return None

        recent = points[-15:]

        x = np.array([float(klines[p[0]].get('open_time', 0)) for p in recent], dtype=float)
        y = np.array([p[1] for p in recent], dtype=float)

        if np.any(x == 0) or len(x) < 2:
            return None

        # Normalizacja timestampów (duże wartości ms → polyfit niestabilny)
        x_min = x[0]
        x_norm = x - x_min
        d_norm = d_timestamp - x_min

        coeffs = np.polyfit(x_norm, y, 1)
        slope, intercept = coeffs[0], coeffs[1]

        trendline_at_d = slope * d_norm + intercept

        if not _within_tolerance(d_price, trendline_at_d, TRENDLINE_TOLERANCE_PCT):
            return None

        deviation = abs(d_price - trendline_at_d) / abs(d_price) * 100

        y_pred = slope * x_norm + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

        confidence = min(1.0, max(0.2, r_squared))
        proximity_bonus = max(0, (TRENDLINE_TOLERANCE_PCT - deviation) / TRENDLINE_TOLERANCE_PCT * 0.2)
        confidence = min(1.0, confidence + proximity_bonus)
        # Same-interval trendline — obniżony confidence (cross-TF wersja ma pełny)
        confidence = round(confidence * 0.6, 3)

        return {
            'type': line_type,
            'confidence': confidence,
            'candle_index': d_index,
            'details': {
                'trendline_price_at_d': round(trendline_at_d, 6),
                'd_price': round(d_price, 6),
                'deviation_pct': round(deviation, 4),
                'slope_per_ms': round(float(slope), 14),
                'r_squared': round(float(r_squared), 4),
                'swing_points_used': len(recent),
                'source': 'same_interval',
            },
        }

    # ──────────────────────────────────────────────
    # Round / Psychological Levels
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_round_level(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Sprawdza czy D jest blisko okrągłego poziomu psychologicznego
        (np. 100, 50, 1000, 0.5 itp. — w zależności od rzędu wielkości ceny).
        """
        if d_index < 0 or d_index >= len(klines):
            return None

        d_price = float(klines[d_index]['close'])
        if d_price <= 0:
            return None

        candidates = _get_round_levels_near(d_price)
        if not candidates:
            return None

        best_match = None
        best_dev = float('inf')

        for lvl, label in candidates:
            if _within_tolerance(d_price, lvl, ROUND_LEVEL_TOLERANCE_PCT):
                dev = abs(d_price - lvl) / abs(d_price) * 100
                if dev < best_dev:
                    best_dev = dev
                    best_match = (lvl, label)

        if best_match is None:
            return None

        lvl, label = best_match
        # "Okrągłość" — im większy krok round level vs cena, tym silniejszy
        magnitude = 10 ** math.floor(math.log10(d_price)) if d_price > 0 else 1
        roundness = abs(lvl) / max(magnitude, 1e-10)
        confidence = min(1.0, roundness / 10.0 * 0.5 + (ROUND_LEVEL_TOLERANCE_PCT - best_dev) / ROUND_LEVEL_TOLERANCE_PCT * 0.5)
        confidence = max(0.2, min(1.0, confidence))

        return {
            'type': 'round_level',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'level': round(lvl, 8),
                'label': label,
                'd_price': round(d_price, 6),
                'deviation_pct': round(best_dev, 4),
            },
        }

    # ──────────────────────────────────────────────
    # Pivot Points
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_pivot_point(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None, interval: str = None,
    ) -> Optional[Dict]:
        """
        Sprawdza czy D wypada na pivocie (P, S1-S3, R1-R3)
        obliczonym z OHLC poprzedniego okresu (dzień/tydzień).
        """
        if d_index < 2 or d_index >= len(klines):
            return None

        d_price = float(klines[d_index]['close'])
        if d_price <= 0:
            return None

        prev_ohlc = _get_previous_period_ohlc(klines, d_index, interval or '1d')
        if prev_ohlc is None:
            return None

        pivots = _calculate_pivot_points(prev_ohlc['high'], prev_ohlc['low'], prev_ohlc['close'])

        best_pivot = None
        best_dev = float('inf')

        # Bullish: szukamy wsparcia (P, S1, S2, S3)
        # Bearish: szukamy oporu (P, R1, R2, R3)
        if is_bullish:
            relevant = {k: v for k, v in pivots.items() if k in ('P', 'S1', 'S2', 'S3')}
        else:
            relevant = {k: v for k, v in pivots.items() if k in ('P', 'R1', 'R2', 'R3')}

        for name, price in relevant.items():
            if _within_tolerance(d_price, price, PIVOT_TOLERANCE_PCT):
                dev = abs(d_price - price) / abs(d_price) * 100
                if dev < best_dev:
                    best_dev = dev
                    best_pivot = (name, price)

        if best_pivot is None:
            return None

        name, price = best_pivot
        confidence = min(1.0, 0.6 + (PIVOT_TOLERANCE_PCT - best_dev) / PIVOT_TOLERANCE_PCT * 0.4)

        return {
            'type': 'pivot_point',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'pivot_name': name,
                'pivot_price': round(price, 6),
                'd_price': round(d_price, 6),
                'deviation_pct': round(best_dev, 4),
                'all_pivots': {k: round(v, 6) for k, v in pivots.items()},
                'prev_ohlc': {k: round(v, 6) for k, v in prev_ohlc.items()},
            },
        }


# ═══════════════════════════════════════════════════════
# Post-processing: Cross-TF S/R i Trendline
# ═══════════════════════════════════════════════════════

HIGHER_TF_SR_TOLERANCE_PCT = 0.5
HIGHER_TF_TRENDLINE_TOLERANCE_PCT = 0.5


def _get_d_timestamp(pattern: Dict) -> Optional[float]:
    """Wyciąga timestamp (open_time ms) punktu D z rekordu DB lub ta_object_json."""
    # Najpierw sprawdź top-level DB field
    d_ts = pattern.get('d_point_timestamp')
    if d_ts and d_ts > 0:
        return float(d_ts)
    # Fallback: ta_object_json.points.D.open_time
    ta = pattern.get('ta_object_json', {})
    points = ta.get('points', {})
    d = points.get('D')
    if d and 'open_time' in d:
        return float(d['open_time'])
    return None


class HigherTFSRDetector:
    """
    Post-processing: sprawdza czy D patternu wypada na strefie S/R
    z wyższego timeframe'u. Wymaga klines_by_interval (cache z sync loop).
    """

    @staticmethod
    def detect(
        klines_by_interval: Dict[str, List[Dict]],
        target_pattern: Dict,
        target_interval: str,
        tolerance_pct: float = HIGHER_TF_SR_TOLERANCE_PCT,
    ) -> Optional[Dict]:
        d_price = _get_d_price(target_pattern)
        if d_price is None or d_price == 0:
            return None

        if target_interval not in INTERVAL_HIERARCHY:
            return None
        target_rank = INTERVAL_HIERARCHY.index(target_interval)

        is_bullish = target_pattern.get('ta_object_json', {}).get('bullish', True)

        matches: List[Dict[str, Any]] = []

        for interval, klines in klines_by_interval.items():
            if interval not in INTERVAL_HIERARCHY:
                continue
            interval_rank = INTERVAL_HIERARCHY.index(interval)
            if interval_rank <= target_rank:
                continue

            if not klines or len(klines) < SR_SWING_LOOKBACK * 2 + 1:
                continue

            base_confidence = HIGHER_TF_CONFIDENCE_MAP.get(interval, 0.5)

            swing_highs, swing_lows = _find_swing_points(klines)

            if is_bullish:
                zones = _cluster_levels(swing_lows)
                zone_type = 'support'
            else:
                zones = _cluster_levels(swing_highs)
                zone_type = 'resistance'

            for zone in zones:
                if _within_tolerance(d_price, zone['price'], tolerance_pct):
                    dev = abs(d_price - zone['price']) / abs(d_price) * 100
                    matches.append({
                        'source_interval': interval,
                        'zone_type': zone_type,
                        'zone_price': round(zone['price'], 6),
                        'touches': zone['touches'],
                        'deviation_pct': round(dev, 4),
                        'tf_confidence': base_confidence,
                    })

        if not matches:
            return None

        best_tf_confidence = max(m['tf_confidence'] for m in matches)
        best_touches = max(m['touches'] for m in matches)
        touch_factor = min(1.0, best_touches / 5.0)
        confidence = round(min(1.0, best_tf_confidence * 0.6 + touch_factor * 0.4), 3)

        by_interval: Dict[str, List] = {}
        for m in matches:
            by_interval.setdefault(m['source_interval'], []).append(m)

        summary = {}
        for iv, zones_list in by_interval.items():
            zones_list.sort(key=lambda x: x['deviation_pct'])
            summary[iv] = zones_list[:5]

        zone_type_result = matches[0]['zone_type']

        return {
            'type': f'higher_tf_{zone_type_result}_zone',
            'confidence': confidence,
            'candle_index': None,
            'details': {
                'total_matching_zones': len(matches),
                'd_price': round(d_price, 6),
                'tolerance_pct': tolerance_pct,
                'target_interval': target_interval,
                'source_intervals': list(by_interval.keys()),
                'zones_by_interval': summary,
            },
        }


class HigherTFTrendlineDetector:
    """
    Post-processing: sprawdza czy D patternu wypada na linii trendu
    z wyższego timeframe'u. Regresja timestamp-based na swing pointach.
    Wymaga klines_by_interval (cache z sync loop).
    """

    @staticmethod
    def detect(
        klines_by_interval: Dict[str, List[Dict]],
        target_pattern: Dict,
        target_interval: str,
        tolerance_pct: float = HIGHER_TF_TRENDLINE_TOLERANCE_PCT,
    ) -> Optional[Dict]:
        d_price = _get_d_price(target_pattern)
        if d_price is None or d_price == 0:
            return None

        # Timestamp D — próbujemy wyciągnąć z ta_object_json
        d_timestamp = _get_d_timestamp(target_pattern)

        if target_interval not in INTERVAL_HIERARCHY:
            return None
        target_rank = INTERVAL_HIERARCHY.index(target_interval)

        is_bullish = target_pattern.get('ta_object_json', {}).get('bullish', True)

        matches: List[Dict[str, Any]] = []

        for interval, klines in klines_by_interval.items():
            if interval not in INTERVAL_HIERARCHY:
                continue
            interval_rank = INTERVAL_HIERARCHY.index(interval)
            if interval_rank <= target_rank:
                continue

            min_candles = SR_SWING_LOOKBACK * 2 + TRENDLINE_MIN_POINTS
            if not klines or len(klines) < min_candles:
                continue

            base_confidence = HIGHER_TF_CONFIDENCE_MAP.get(interval, 0.5)

            swing_highs, swing_lows = _find_swing_points(klines)

            if is_bullish:
                points = swing_lows
                line_type = 'support_trendline'
            else:
                points = swing_highs
                line_type = 'resistance_trendline'

            if len(points) < TRENDLINE_MIN_POINTS:
                continue

            recent = points[-15:]

            x = np.array([float(klines[p[0]].get('open_time', 0)) for p in recent], dtype=float)
            y = np.array([p[1] for p in recent], dtype=float)

            if np.any(x == 0) or len(x) < 2:
                continue

            x_min = x[0]
            x_norm = x - x_min

            try:
                coeffs = np.polyfit(x_norm, y, 1)
            except (np.linalg.LinAlgError, ValueError):
                continue
            slope, intercept = coeffs[0], coeffs[1]

            # Ekstrapolacja do D: używamy timestampu D lub ostatniej świecy wyższego TF
            if d_timestamp and d_timestamp > 0:
                d_norm = d_timestamp - x_min
            else:
                d_norm = float(klines[-1].get('open_time', 0)) - x_min

            if d_norm <= 0:
                continue

            trendline_at_d = slope * d_norm + intercept

            if not _within_tolerance(d_price, trendline_at_d, tolerance_pct):
                continue

            deviation = abs(d_price - trendline_at_d) / abs(d_price) * 100

            y_pred = slope * x_norm + intercept
            ss_res = np.sum((y - y_pred) ** 2)
            ss_tot = np.sum((y - np.mean(y)) ** 2)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

            matches.append({
                'source_interval': interval,
                'line_type': line_type,
                'trendline_price_at_d': round(trendline_at_d, 6),
                'deviation_pct': round(deviation, 4),
                'r_squared': round(float(r_squared), 4),
                'swing_points_used': len(recent),
                'tf_confidence': base_confidence,
            })

        if not matches:
            return None

        best_match = max(matches, key=lambda m: m['tf_confidence'])
        r2_factor = min(1.0, max(0.2, best_match['r_squared']))
        confidence = round(min(1.0, best_match['tf_confidence'] * 0.6 + r2_factor * 0.4), 3)

        line_type_result = matches[0]['line_type']

        by_interval: Dict[str, List] = {}
        for m in matches:
            by_interval.setdefault(m['source_interval'], []).append(m)

        return {
            'type': f'higher_tf_{line_type_result}',
            'confidence': confidence,
            'candle_index': None,
            'details': {
                'total_matching_trendlines': len(matches),
                'd_price': round(d_price, 6),
                'tolerance_pct': tolerance_pct,
                'target_interval': target_interval,
                'source_intervals': list(by_interval.keys()),
                'trendlines_by_interval': by_interval,
            },
        }
