"""
Orkiestrator wykrywania konfluencji dla wzorców harmonicznych.

Zbiera wyniki z detektorów:
- Candlestick patterns (hammer, shooting star, morning/evening star, engulfing, doji, pin bar)
- RSI (oversold/overbought, divergence)
- MACD (crossover, histogram reversal, divergence)
- OBV (divergence)
- Stochastic (oversold/overbought)
- Structural (support/resistance, trendline, round levels, pivot points)

Zwraca zunifikowany dict gotowy do zapisu w kolumnie confluences_json.
"""

import logging
from typing import Dict, List, Optional, Union

from .candlestick_patterns import CandlestickPatternDetector
from .indicator_confluences import IndicatorConfluenceDetector
from .structural_confluences import StructuralConfluenceDetector

logger = logging.getLogger(__name__)


class ConfluenceDetector:
    """Wykrywa konfluencje wzmacniające wzorce harmoniczne w punkcie D."""

    @staticmethod
    def detect(
        klines: List[Dict],
        pattern_points: Dict[str, Dict],
        is_bullish: bool,
        d_kline_index: int,
        interval: str = None,
    ) -> Dict:
        """
        Uruchamia wszystkie detektory konfluencji na punkcie D.

        Args:
            klines: Pełna lista świeczek użytych do wykrycia patternu.
            pattern_points: Słownik punktów patternu {'X': {'index': ..., 'price': ...}, ...}.
            is_bullish: Czy pattern jest bullish.
            d_kline_index: Indeks świecy D w klines.
            interval: Interwał (potrzebny do pivot points).

        Returns:
            {
                "total_score": <int>,       # liczba znalezionych konfluencji
                "confluences": [ ... ]      # lista dicts z wykrytymi konfluencjami
            }
        """
        confluences: List[Dict] = []

        # --- Candlestick patterns na świecy D ---
        candlestick_detectors = [
            CandlestickPatternDetector.detect_hammer,
            CandlestickPatternDetector.detect_shooting_star,
            CandlestickPatternDetector.detect_morning_star,
            CandlestickPatternDetector.detect_evening_star,
            CandlestickPatternDetector.detect_bullish_engulfing,
            CandlestickPatternDetector.detect_bearish_engulfing,
            CandlestickPatternDetector.detect_doji,
            CandlestickPatternDetector.detect_bullish_pin_bar,
            CandlestickPatternDetector.detect_bearish_pin_bar,
        ]

        for detector_fn in candlestick_detectors:
            try:
                result = detector_fn(klines, d_kline_index, is_bullish)
                if result is not None:
                    confluences.append(result)
                    logger.debug(
                        f"Confluence found: {result['type']} "
                        f"(confidence={result['confidence']}) at candle {d_kline_index}"
                    )
            except Exception as e:
                logger.warning(f"Error in candlestick detector {detector_fn.__name__}: {e}")

        # --- RSI, MACD, OBV (wymagają pattern_points do divergence) ---
        indicator_detectors = [
            IndicatorConfluenceDetector.detect_rsi_oversold,
            IndicatorConfluenceDetector.detect_rsi_overbought,
            IndicatorConfluenceDetector.detect_rsi_divergence,
            IndicatorConfluenceDetector.detect_macd_crossover,
            IndicatorConfluenceDetector.detect_macd_histogram_reversal,
            IndicatorConfluenceDetector.detect_macd_divergence,
            IndicatorConfluenceDetector.detect_obv_divergence,
            IndicatorConfluenceDetector.detect_stochastic_oversold,
            IndicatorConfluenceDetector.detect_stochastic_overbought,
        ]

        for detector_fn in indicator_detectors:
            try:
                result = detector_fn(
                    klines, d_kline_index, is_bullish,
                    pattern_points=pattern_points,
                )
                if result is not None:
                    confluences.append(result)
                    logger.debug(
                        f"Confluence found: {result['type']} "
                        f"(confidence={result['confidence']}) at candle {d_kline_index}"
                    )
            except Exception as e:
                logger.warning(f"Error in indicator detector {detector_fn.__name__}: {e}")

        # --- Structural (S/R, trendline, round levels, pivot points) ---
        structural_detectors = [
            StructuralConfluenceDetector.detect_support_resistance,
            StructuralConfluenceDetector.detect_trendline,
            StructuralConfluenceDetector.detect_round_level,
        ]

        for detector_fn in structural_detectors:
            try:
                result = detector_fn(
                    klines, d_kline_index, is_bullish,
                    pattern_points=pattern_points,
                )
                if result is not None:
                    confluences.append(result)
                    logger.debug(
                        f"Confluence found: {result['type']} "
                        f"(confidence={result['confidence']}) at candle {d_kline_index}"
                    )
            except Exception as e:
                logger.warning(f"Error in structural detector {detector_fn.__name__}: {e}")

        # Pivot Points — wymaga interval
        try:
            pivot_result = StructuralConfluenceDetector.detect_pivot_point(
                klines, d_kline_index, is_bullish,
                pattern_points=pattern_points,
                interval=interval,
            )
            if pivot_result is not None:
                confluences.append(pivot_result)
                logger.debug(
                    f"Confluence found: {pivot_result['type']} "
                    f"(confidence={pivot_result['confidence']}) at candle {d_kline_index}"
                )
        except Exception as e:
            logger.warning(f"Error in pivot point detector: {e}")

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
