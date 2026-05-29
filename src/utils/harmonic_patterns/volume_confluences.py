"""
Konfluencje wolumenowe na punkcie D wzorców harmonicznych.

- Volume Spike — nagły wzrost wolumenu na D (kulminacja ruchu)
- Volume Dry-up — wyschnięcie wolumenu przed D (brak paliwa do kontynuacji)
- Volume Profile (POC/VAH/VAL) — D w obszarze wysokiego wolumenu profilowego
"""

import logging
import numpy as np
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Volume Spike
SPIKE_LOOKBACK = 20          # Okno do obliczenia średniego wolumenu
SPIKE_THRESHOLD = 2.0        # Mnożnik vol vs avg żeby uznać za spike
SPIKE_EXTREME = 4.0          # Mnożnik dla ekstremalnego spike'a (confidence=1.0)

# Volume Dry-up
DRYUP_LOOKBACK = 20          # Bazowe okno porównawcze
DRYUP_RECENT = 5             # Ostatnich N świec przed D
DRYUP_THRESHOLD = 0.5        # Stosunek recent_avg / base_avg (< to dry-up)
DRYUP_EXTREME = 0.2          # Stosunek dla ekstremalnego dry-up

# Volume Profile
VP_LOOKBACK = 100            # Ile świec do budowy profilu
VP_NUM_BINS = 50             # Liczba binów cenowych
VP_VALUE_AREA_PCT = 0.70     # 70% wolumenu = Value Area
VP_TOLERANCE_PCT = 0.3       # Tolerancja D vs POC/VAH/VAL


def _get_volumes(klines: List[Dict], start: int, end: int) -> np.ndarray:
    """Wyciąga wolumeny z klines[start:end] jako numpy array."""
    return np.array([float(k.get('volume', 0)) for k in klines[start:end]])


def _within_tolerance(target: float, candidate: float, tolerance_pct: float) -> bool:
    if target == 0:
        return False
    return abs(candidate - target) / abs(target) * 100 <= tolerance_pct


class VolumeConfluenceDetector:
    """Detektory konfluencji wolumenowych: spike, dry-up, volume profile."""

    # ──────────────────────────────────────────────
    # Volume Spike
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_volume_spike(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Wykrywa nagły wzrost wolumenu na świecy D w porównaniu do średniej
        z ostatnich SPIKE_LOOKBACK świec. Sugeruje kulminację ruchu —
        potencjalny punkt zwrotny.
        """
        if d_index < SPIKE_LOOKBACK + 1:
            return None

        d_vol = float(klines[d_index].get('volume', 0))
        if d_vol <= 0:
            return None

        avg_vols = _get_volumes(klines, d_index - SPIKE_LOOKBACK, d_index)
        avg_vol = np.mean(avg_vols)
        if avg_vol <= 0:
            return None

        ratio = d_vol / avg_vol
        if ratio < SPIKE_THRESHOLD:
            return None

        # Confidence: liniowo od threshold (0.4) do extreme (1.0)
        t = min(1.0, (ratio - SPIKE_THRESHOLD) / (SPIKE_EXTREME - SPIKE_THRESHOLD))
        confidence = 0.4 + t * 0.6

        return {
            'type': 'volume_spike',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'd_volume': round(d_vol, 2),
                'avg_volume': round(float(avg_vol), 2),
                'ratio': round(ratio, 2),
                'lookback': SPIKE_LOOKBACK,
            },
        }

    # ──────────────────────────────────────────────
    # Volume Dry-up
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_volume_dryup(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Wykrywa wyschnięcie wolumenu w okolicach D — ostatnie N świec
        ma istotnie niższy wolumen niż bazowe okno. Brak paliwa
        do kontynuacji ruchu → wsparcie dla odwrócenia.
        """
        total_needed = DRYUP_LOOKBACK + DRYUP_RECENT
        if d_index < total_needed:
            return None

        base_start = d_index - DRYUP_LOOKBACK - DRYUP_RECENT
        base_end = d_index - DRYUP_RECENT
        recent_start = d_index - DRYUP_RECENT
        recent_end = d_index + 1  # włącznie z D

        base_vols = _get_volumes(klines, base_start, base_end)
        recent_vols = _get_volumes(klines, recent_start, recent_end)

        base_avg = np.mean(base_vols)
        recent_avg = np.mean(recent_vols)

        if base_avg <= 0:
            return None

        ratio = recent_avg / base_avg
        if ratio >= DRYUP_THRESHOLD:
            return None

        # Confidence: liniowo od threshold (0.4) do extreme (1.0)
        t = min(1.0, (DRYUP_THRESHOLD - ratio) / (DRYUP_THRESHOLD - DRYUP_EXTREME))
        confidence = 0.4 + t * 0.6

        return {
            'type': 'volume_dryup',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'recent_avg_volume': round(float(recent_avg), 2),
                'base_avg_volume': round(float(base_avg), 2),
                'ratio': round(ratio, 3),
                'recent_candles': DRYUP_RECENT,
                'base_candles': DRYUP_LOOKBACK,
            },
        }

    # ──────────────────────────────────────────────
    # Volume Profile — POC / VAH / VAL
    # ──────────────────────────────────────────────

    @staticmethod
    def detect_volume_profile(
        klines: List[Dict], d_index: int, is_bullish: bool,
        pattern_points: Dict = None,
    ) -> Optional[Dict]:
        """
        Buduje Volume Profile z ostatnich VP_LOOKBACK świec przed D.
        Wyznacza POC (Point of Control), VAH (Value Area High),
        VAL (Value Area Low). Sprawdza czy D wypada blisko tych poziomów.

        Bullish: D blisko VAL lub POC = wsparcie wolumenowe.
        Bearish: D blisko VAH lub POC = opór wolumenowy.
        """
        lookback = min(VP_LOOKBACK, d_index)
        if lookback < 20:
            return None

        d_price = float(klines[d_index]['close'])
        if d_price <= 0:
            return None

        profile_klines = klines[d_index - lookback: d_index]

        highs = np.array([float(k['high']) for k in profile_klines])
        lows = np.array([float(k['low']) for k in profile_klines])
        volumes = np.array([float(k.get('volume', 0)) for k in profile_klines])

        price_min = float(np.min(lows))
        price_max = float(np.max(highs))
        if price_max <= price_min:
            return None

        bin_size = (price_max - price_min) / VP_NUM_BINS
        if bin_size <= 0:
            return None

        # Rozkład wolumenu po binach cenowych
        # Wolumen każdej świecy dzielimy równomiernie między biny, które pokrywa
        vol_bins = np.zeros(VP_NUM_BINS)
        for i in range(len(profile_klines)):
            lo = lows[i]
            hi = highs[i]
            vol = volumes[i]
            if vol <= 0 or hi <= lo:
                continue

            bin_lo = max(0, int((lo - price_min) / bin_size))
            bin_hi = min(VP_NUM_BINS - 1, int((hi - price_min) / bin_size))
            num_bins_covered = bin_hi - bin_lo + 1
            vol_per_bin = vol / num_bins_covered
            for b in range(bin_lo, bin_hi + 1):
                vol_bins[b] += vol_per_bin

        total_vol = np.sum(vol_bins)
        if total_vol <= 0:
            return None

        # POC — bin z największym wolumenem
        poc_bin = int(np.argmax(vol_bins))
        poc_price = price_min + (poc_bin + 0.5) * bin_size

        # Value Area — rozszerzaj od POC aż pokryjesz VP_VALUE_AREA_PCT wolumenu
        va_vol_target = total_vol * VP_VALUE_AREA_PCT
        va_vol = vol_bins[poc_bin]
        lo_idx = poc_bin
        hi_idx = poc_bin

        while va_vol < va_vol_target and (lo_idx > 0 or hi_idx < VP_NUM_BINS - 1):
            expand_lo = vol_bins[lo_idx - 1] if lo_idx > 0 else -1
            expand_hi = vol_bins[hi_idx + 1] if hi_idx < VP_NUM_BINS - 1 else -1

            if expand_lo >= expand_hi:
                lo_idx -= 1
                va_vol += vol_bins[lo_idx]
            else:
                hi_idx += 1
                va_vol += vol_bins[hi_idx]

        val_price = price_min + lo_idx * bin_size
        vah_price = price_min + (hi_idx + 1) * bin_size

        # Sprawdź czy D jest blisko POC, VAH lub VAL
        matches = []
        for level_name, level_price in [('POC', poc_price), ('VAH', vah_price), ('VAL', val_price)]:
            if _within_tolerance(d_price, level_price, VP_TOLERANCE_PCT):
                dev = abs(d_price - level_price) / abs(d_price) * 100
                matches.append((level_name, level_price, dev))

        if not matches:
            return None

        # Filtrowanie — bullish szuka wsparcia (VAL, POC), bearish oporu (VAH, POC)
        if is_bullish:
            preferred = [m for m in matches if m[0] in ('VAL', 'POC')]
        else:
            preferred = [m for m in matches if m[0] in ('VAH', 'POC')]

        relevant = preferred if preferred else matches
        best = min(relevant, key=lambda m: m[2])
        level_name, level_price, deviation = best

        # POC mocniejszy niż VAH/VAL
        base_conf = 0.7 if level_name == 'POC' else 0.5
        proximity_bonus = (VP_TOLERANCE_PCT - deviation) / VP_TOLERANCE_PCT * 0.3
        confidence = min(1.0, base_conf + proximity_bonus)

        return {
            'type': 'volume_profile',
            'confidence': round(confidence, 3),
            'candle_index': d_index,
            'details': {
                'matched_level': level_name,
                'level_price': round(level_price, 6),
                'd_price': round(d_price, 6),
                'deviation_pct': round(deviation, 4),
                'poc': round(poc_price, 6),
                'vah': round(vah_price, 6),
                'val': round(val_price, 6),
                'profile_candles': lookback,
            },
        }
