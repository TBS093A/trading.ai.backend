"""
Post-processing: trend z wyższego timeframe'u w chwili D.

Na pierwszym wyższym interwale (1h -> 4h, 4h -> 1d, 1d -> 1w ...) liczona jest EMA(TREND_EMA_PERIOD) ze świec
ZAMKNIĘTYCH przed D. Trend wzrostowy: zamknięcie powyżej EMA i EMA rosnąca przez TREND_SLOPE_BARS świec;
spadkowy - lustrzanie; inaczej brak konfluencji (trend boczny / niejednoznaczny).

Typy: higher_tf_uptrend (kierunek bullish), higher_tf_downtrend (bearish) - model siły (src/pattern_strength.py)
widzi je jako zgodne albo przeciwne kierunkowi formacji, tak jak pozostałe konfluencje. Trend jest znany
przed dotknięciem PRZ, więc wchodzi też do siły wstępnej (LEVEL_TYPES).
"""

from typing import Dict, List, Optional

from ._common import klines_closed_before
from .fib_confluences import INTERVAL_HIERARCHY
from .structural_confluences import _get_d_timestamp

TREND_EMA_PERIOD = 200
TREND_SLOPE_BARS = 10
TREND_TYPES = ("higher_tf_uptrend", "higher_tf_downtrend")


def ema(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    out = [sum(values[:period]) / period]
    for v in values[period:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def trend_at(klines: List[Dict], period: int = TREND_EMA_PERIOD, slope_bars: int = TREND_SLOPE_BARS) -> Optional[Dict]:
    """{"trend": "up"|"down", "ema", "close", "slope_pct"} albo None (za mało świec / boczny)."""
    closes = [float(k["close"]) for k in klines]
    line = ema(closes, period)
    if len(line) <= slope_bars:
        return None
    now, before, close = line[-1], line[-1 - slope_bars], closes[-1]
    slope_pct = (now - before) / before * 100.0 if before else 0.0
    if close > now and now > before:
        trend = "up"
    elif close < now and now < before:
        trend = "down"
    else:
        return None
    return {"trend": trend, "ema": round(now, 8), "close": round(close, 8), "slope_pct": round(slope_pct, 4)}


class HigherTFTrendDetector:
    """Trend z pierwszego wyższego interwału, dla którego są świece (EMA na świecach zamkniętych przed D)."""

    @staticmethod
    def detect(klines_by_interval: Dict[str, List[Dict]], target_pattern: Dict, target_interval: str) -> Optional[Dict]:
        if target_interval not in INTERVAL_HIERARCHY:
            return None
        d_ts = _get_d_timestamp(target_pattern)
        rank = INTERVAL_HIERARCHY.index(target_interval)
        for interval in INTERVAL_HIERARCHY[rank + 1:]:
            klines = klines_by_interval.get(interval)
            if not klines:
                continue
            closed = klines_closed_before(klines, interval, int(d_ts) if d_ts else None)
            result = trend_at(closed)
            if result is None:
                return None   # najbliższy wyższy TF bez wyraźnego trendu - nie szukamy dalej
            return {
                "type": "higher_tf_uptrend" if result["trend"] == "up" else "higher_tf_downtrend",
                "confidence": round(min(1.0, 0.5 + abs(result["slope_pct"]) / 10.0), 3),
                "candle_index": None,
                "details": {**result, "source_interval": interval, "ema_period": TREND_EMA_PERIOD,
                            "slope_bars": TREND_SLOPE_BARS},
            }
        return None
