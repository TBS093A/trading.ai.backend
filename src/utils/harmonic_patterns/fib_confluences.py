"""
Post-processing: konfluencje oparte na zbieżności poziomów Fibonacci.

- FibClusterDetector  — klaster Fib z wielu patternów na tym samym interwale
- HigherTFFibDetector — D pokrywa się z Fib z wyższego timeframe'u
- merge_confluences   — bezpieczne mergowanie nowych wpisów do istniejącego confluences_json
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FIB_CLUSTER_TOLERANCE_PCT = 0.5   # ±0.5% ceny D
FIB_CLUSTER_MIN_SIZE = 3          # minimum zbiegających się poziomów z obcych patternów
HIGHER_TF_TOLERANCE_PCT = 0.5    # ±0.5% ceny D

INTERVAL_HIERARCHY = [
    '1m', '15m', '30m', '1h', '4h',
    '1d', '3d', '1w', '1M', '3M', '1Y',
]

HIGHER_TF_CONFIDENCE_MAP = {
    '1h': 0.4, '4h': 0.5,
    '1d': 0.6, '3d': 0.7,
    '1w': 0.8, '1M': 0.9,
    '3M': 0.95, '1Y': 1.0,
}


def _get_d_price(pattern: Dict) -> Optional[float]:
    """Wyciąga cenę punktu D z ta_object_json."""
    ta = pattern.get('ta_object_json', {})
    points = ta.get('points', {})
    d = points.get('D')
    if d and 'price' in d:
        return float(d['price'])
    return None


def _collect_fib_prices(pattern: Dict) -> List[Tuple[str, float]]:
    """
    Zbiera wszystkie obliczone ceny Fibonacci z patternu.
    Zwraca listę (label, price).
    """
    ta = pattern.get('ta_object_json', {})
    fib = ta.get('fibonacci_levels', {})
    pid = pattern.get('id', '?')
    prices: List[Tuple[str, float]] = []

    # fe_extensions — najkonkretniejsze poziomy
    for name, fe in fib.get('fe_extensions', {}).items():
        if isinstance(fe, dict) and 'price' in fe:
            prices.append((f"P#{pid} {name}", float(fe['price'])))

    # all_fibos — per-pair retracement/extension
    for pair_name, pair_data in fib.get('all_fibos', {}).items():
        if not isinstance(pair_data, dict):
            continue
        for section in ('retracement', 'extension'):
            for level_str, price in pair_data.get(section, {}).items():
                if price is not None:
                    prices.append((f"P#{pid} {pair_name} {section} {level_str}", float(price)))

    # general retracement / extension
    for section in ('retracement', 'extension'):
        for level_str, price in fib.get(section, {}).items():
            if price is not None:
                prices.append((f"P#{pid} swing {section} {level_str}", float(price)))

    return prices


def _within_tolerance(target: float, candidate: float, tolerance_pct: float) -> bool:
    if target == 0:
        return False
    return abs(candidate - target) / abs(target) * 100 <= tolerance_pct


# ─────────────────────────────────────────────────────
# Merge helper
# ─────────────────────────────────────────────────────

def merge_confluences(
    existing_json: Optional[Dict],
    new_entries: List[Dict],
    replace_types: Optional[List[str]] = None,
) -> Dict:
    """
    Merguje nowe konfluencje do istniejącego confluences_json.
    Usuwa stare wpisy o typach z `replace_types` (żeby odświeżyć),
    potem dodaje `new_entries`.
    """
    if existing_json is None:
        existing_json = {'total_score': 0, 'confluences': []}

    confluences = list(existing_json.get('confluences', []))

    if replace_types:
        confluences = [c for c in confluences if c.get('type') not in replace_types]

    confluences.extend(new_entries)

    return {
        'total_score': len(confluences),
        'confluences': confluences,
    }


# ─────────────────────────────────────────────────────
# Fib Cluster (same interval)
# ─────────────────────────────────────────────────────

class FibClusterDetector:
    """Wykrywa klaster Fib — punkt D w miejscu zbieżności wielu poziomów z innych patternów."""

    @staticmethod
    def detect(
        all_patterns: List[Dict],
        target_pattern_id: int,
        tolerance_pct: float = FIB_CLUSTER_TOLERANCE_PCT,
        min_cluster_size: int = FIB_CLUSTER_MIN_SIZE,
    ) -> Optional[Dict]:
        """
        Args:
            all_patterns: Patterny z DB dla asset+interval (zawierają id, ta_object_json, confluences_json).
            target_pattern_id: ID patternu do analizy.
            tolerance_pct: Tolerancja procentowa.
            min_cluster_size: Minimalna liczba zbiegających się poziomów.

        Returns:
            Dict konfluencji lub None.
        """
        target = None
        others = []
        for p in all_patterns:
            if p['id'] == target_pattern_id:
                target = p
            else:
                others.append(p)

        if target is None or not others:
            return None

        d_price = _get_d_price(target)
        if d_price is None or d_price == 0:
            return None

        matching_levels: List[Dict[str, Any]] = []

        for other in others:
            fib_prices = _collect_fib_prices(other)
            for label, price in fib_prices:
                if _within_tolerance(d_price, price, tolerance_pct):
                    matching_levels.append({
                        'label': label,
                        'price': round(price, 6),
                        'deviation_pct': round(abs(price - d_price) / abs(d_price) * 100, 4),
                    })

        if len(matching_levels) < min_cluster_size:
            return None

        confidence = min(1.0, len(matching_levels) / 6.0)

        # Deduplikuj po cenie (±0.01%) — wiele Fib levels mogą wylądować na tej samej cenie
        seen_prices = set()
        unique_levels = []
        for lvl in matching_levels:
            rounded = round(lvl['price'], 4)
            if rounded not in seen_prices:
                seen_prices.add(rounded)
                unique_levels.append(lvl)

        # Top 10 najbliższych
        unique_levels.sort(key=lambda x: x['deviation_pct'])
        top_levels = unique_levels[:10]

        return {
            'type': 'fib_cluster',
            'confidence': round(confidence, 3),
            'candle_index': None,
            'details': {
                'total_converging_levels': len(matching_levels),
                'unique_price_levels': len(unique_levels),
                'd_price': round(d_price, 6),
                'tolerance_pct': tolerance_pct,
                'levels': top_levels,
            },
        }


# ─────────────────────────────────────────────────────
# Higher TF Fib
# ─────────────────────────────────────────────────────

class HigherTFFibDetector:
    """Wykrywa pokrycie D z ważnymi Fib z wyższego timeframe'u."""

    @staticmethod
    def detect(
        patterns_by_interval: Dict[str, List[Dict]],
        target_pattern: Dict,
        target_interval: str,
        tolerance_pct: float = HIGHER_TF_TOLERANCE_PCT,
    ) -> Optional[Dict]:
        """
        Args:
            patterns_by_interval: {interval_str: [patterns from DB]} dla tego samego assetu.
            target_pattern: Pattern do analizy (z DB).
            target_interval: Interwał tego patternu.
            tolerance_pct: Tolerancja procentowa.

        Returns:
            Dict konfluencji lub None.
        """
        d_price = _get_d_price(target_pattern)
        if d_price is None or d_price == 0:
            return None

        if target_interval not in INTERVAL_HIERARCHY:
            return None

        target_rank = INTERVAL_HIERARCHY.index(target_interval)

        matches: List[Dict[str, Any]] = []

        for interval, patterns in patterns_by_interval.items():
            if interval not in INTERVAL_HIERARCHY:
                continue
            interval_rank = INTERVAL_HIERARCHY.index(interval)
            if interval_rank <= target_rank:
                continue

            base_confidence = HIGHER_TF_CONFIDENCE_MAP.get(interval, 0.5)

            for p in patterns:
                if p['id'] == target_pattern.get('id'):
                    continue

                fib_prices = _collect_fib_prices(p)
                for label, price in fib_prices:
                    if _within_tolerance(d_price, price, tolerance_pct):
                        matches.append({
                            'source_interval': interval,
                            'label': label,
                            'price': round(price, 6),
                            'deviation_pct': round(abs(price - d_price) / abs(d_price) * 100, 4),
                            'tf_confidence': base_confidence,
                        })

        if not matches:
            return None

        # Najwyższy confidence z najwyższego TF
        best_tf_confidence = max(m['tf_confidence'] for m in matches)
        count_factor = min(1.0, len(matches) / 5.0)
        confidence = round(min(1.0, best_tf_confidence * 0.7 + count_factor * 0.3), 3)

        # Grupuj po interwale źródłowym
        by_interval: Dict[str, List] = {}
        for m in matches:
            by_interval.setdefault(m['source_interval'], []).append(m)

        # Top 5 per interwał, posortowane po deviation
        summary = {}
        for iv, lvls in by_interval.items():
            lvls.sort(key=lambda x: x['deviation_pct'])
            summary[iv] = lvls[:5]

        return {
            'type': 'higher_tf_fib',
            'confidence': confidence,
            'candle_index': None,
            'details': {
                'total_matching_levels': len(matches),
                'd_price': round(d_price, 6),
                'tolerance_pct': tolerance_pct,
                'target_interval': target_interval,
                'source_intervals': list(by_interval.keys()),
                'levels_by_interval': summary,
            },
        }
