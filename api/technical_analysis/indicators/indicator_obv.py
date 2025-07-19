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


class IndicatorOBV(Indicator):
    """Wskaźnik OBV (On-Balance Volume)"""
    
    def __init__(self):
        super().__init__("OBV")
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], **kwargs) -> None:
        """Oblicza wskaźnik OBV"""
        if len(klines) < 2:
            self.calculated_data = []
            return

        obv_values = [float(klines[0]['volume'])]
        
        for i in range(1, len(klines)):
            current_close = float(klines[i]['close'])
            previous_close = float(klines[i-1]['close'])
            current_volume = float(klines[i]['volume'])
            
            if current_close > previous_close:
                obv_values.append(obv_values[-1] + current_volume)
            elif current_close < previous_close:
                obv_values.append(obv_values[-1] - current_volume)
            else:
                obv_values.append(obv_values[-1])
        
        self.calculated_data = obv_values
        
        # Dodaj OBV do klines dla kompatybilności
        for i, obv_val in enumerate(obv_values):
            if i < len(klines):
                klines[i]['obv'] = obv_val
    
    def draw(self, main_ax, df: pd.DataFrame, add_plots: List, panel: int, **kwargs) -> int:
        """Rysuje OBV na wykresie"""
        if 'obv' in df.columns and not df['obv'].isna().all():
            add_plots.append(
                mpf.make_addplot(df['obv'], panel=panel, color='green', ylabel='OBV')
            )
            return panel + 1
        return panel
