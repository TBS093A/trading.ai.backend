"""
Orkiestrator wykrywania konfluencji dla wzorców harmonicznych.

Zbiera wyniki z poszczególnych detektorów (candlestick patterns, w przyszłości
RSI divergence, volume spike, S/R, Fib cluster itp.) i zwraca zunifikowany dict
gotowy do zapisu w kolumnie confluences_json.
"""

import logging
from typing import Dict, List, Optional, Union

from .candlestick_patterns import CandlestickPatternDetector

logger = logging.getLogger(__name__)


class ConfluenceDetector:
    """Wykrywa konfluencje wzmacniające wzorce harmoniczne w punkcie D."""

    @staticmethod
    def detect(
        klines: List[Dict],
        pattern_points: Dict[str, Dict],
        is_bullish: bool,
        d_kline_index: int,
    ) -> Dict:
        """
        Uruchamia wszystkie detektory konfluencji na punkcie D.

        Args:
            klines: Pełna lista świeczek użytych do wykrycia patternu.
            pattern_points: Słownik punktów patternu {'X': {'index': ..., 'price': ...}, ...}.
            is_bullish: Czy pattern jest bullish.
            d_kline_index: Indeks świecy D w klines.

        Returns:
            {
                "total_score": <int>,       # liczba znalezionych konfluencji
                "confluences": [ ... ]      # lista dicts z wykrytymi konfluencjami
            }
        """
        confluences: List[Dict] = []

        # --- Candlestick patterns na świecy D ---
        detectors = [
            CandlestickPatternDetector.detect_hammer,
            CandlestickPatternDetector.detect_shooting_star,
            CandlestickPatternDetector.detect_morning_star,
            CandlestickPatternDetector.detect_evening_star,
        ]

        for detector_fn in detectors:
            try:
                result = detector_fn(klines, d_kline_index, is_bullish)
                if result is not None:
                    confluences.append(result)
                    logger.debug(
                        f"Confluence found: {result['type']} "
                        f"(confidence={result['confidence']}) at candle {d_kline_index}"
                    )
            except Exception as e:
                logger.warning(f"Error in confluence detector {detector_fn.__name__}: {e}")

        total_score = len(confluences)

        if total_score > 0:
            logger.info(
                f"Detected {total_score} confluence(s) at D "
                f"(index={d_kline_index}, bullish={is_bullish}): "
                f"{[c['type'] for c in confluences]}"
            )

        return {
            'total_score': total_score,
            'confluences': confluences,
        }
