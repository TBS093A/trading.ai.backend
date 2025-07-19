import numpy as np
from typing import List, Dict, Union, Optional, Tuple
import logging
from dataclasses import dataclass
import mplfinance as mpf
import pandas as pd
import base64
from io import BytesIO
import matplotlib.pyplot as plt
import traceback
from abc import ABC, abstractmethod

# Import pyharmonics
try:
    from pyharmonics.marketdata import BinanceCandleData
    from pyharmonics.technicals import Technicals
    from pyharmonics.search import HarmonicSearch
    PYHARMONICS_AVAILABLE = True
except ImportError:
    PYHARMONICS_AVAILABLE = False
    logging.warning("pyharmonics nie jest zainstalowane. Użyj: pip install pyharmonics")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from abstract_indicator import Indicator


class IndicatorRSI(Indicator):
    """Wskaźnik RSI (Relative Strength Index)"""
    
    def __init__(self):
        super().__init__("RSI")
        self.period = 14
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], period: int = 14, **kwargs) -> None:
        """Oblicza wskaźnik RSI"""
        self.period = period
        
        if len(klines) < period + 1:
            self.calculated_data = []
            return

        closes = np.array([float(k['close']) for k in klines])
        deltas = np.diff(closes)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        rsi_values = []
        
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                
            rsi_values.append(rsi)
        
        self.calculated_data = rsi_values
        
        # Dodaj RSI do klines dla kompatybilności
        for i, rsi_val in enumerate(rsi_values):
            kline_index = i + period
            if kline_index < len(klines):
                klines[kline_index]['rsi'] = rsi_val
    
    def draw(self, main_ax, df: pd.DataFrame, add_plots: List, panel: int, **kwargs) -> int:
        """Rysuje RSI na wykresie"""
        if 'rsi' in df.columns and not df['rsi'].isna().all():
            add_plots.append(
                mpf.make_addplot(df['rsi'], panel=panel, color='yellow', ylabel='RSI')
            )
            return panel + 1
        return panel
