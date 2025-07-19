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

from abstract_technical_analysis_object import TechnicalAnalysisObject

class Fibonacci(TechnicalAnalysisObject):
    """Podstawowe poziomy Fibonacciego"""
    
    def __init__(self):
        super().__init__("Fibonacci")
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], start_price: float = None, 
                  end_price: float = None, is_uptrend: bool = True, **kwargs) -> None:
        """Oblicza podstawowe poziomy Fibonacciego"""
        if start_price is None or end_price is None:
            # Znajdź min i max z klines jeśli nie podano
            prices = [float(k['high']) for k in klines] + [float(k['low']) for k in klines]
            start_price = min(prices)
            end_price = max(prices)
        
        self.calculated_data = self._calculate_fibonacci_levels(start_price, end_price, is_uptrend)
    
    def _calculate_fibonacci_levels(self, start_price: float, end_price: float, is_uptrend: bool) -> FibonacciLevels:
        """Oblicza podstawowe poziomy Fibonacciego"""
        price_range = abs(end_price - start_price)
        
        retracement = {}
        extension = {}
        targets = {}
        
        # Poziomy retracementu
        for level_name, level_ratio in [("0.236", 0.236), ("0.382", 0.382), ("0.5", 0.5), 
                                      ("0.618", 0.618), ("0.786", 0.786)]:
            if is_uptrend:
                retracement[level_name] = end_price - (price_range * level_ratio)
            else:
                retracement[level_name] = end_price + (price_range * level_ratio)
        
        # Poziomy extension
        for level_name, level_ratio in [("1.272", 1.272), ("1.618", 1.618), ("2.0", 2.0), ("2.618", 2.618)]:
            if is_uptrend:
                extension[level_name] = end_price + (price_range * (level_ratio - 1.0))
            else:
                extension[level_name] = end_price - (price_range * (level_ratio - 1.0))
        
        # Targety (kombinacja retracement i extension)
        targets.update(retracement)
        targets.update(extension)
        
        return FibonacciLevels(
            retracement=retracement,
            extension=extension,
            targets=targets,
            all_fibos={}
        )
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje podstawowe poziomy Fibonacciego"""
        if self.calculated_data is None:
            return
        
        show_fibonacci = kwargs.get('show_fibonacci', False)
        if not show_fibonacci:
            return
        
        fib_levels = self.calculated_data
        for level_name, price in fib_levels.retracement.items():
            main_ax.axhline(y=price, color='green', linestyle='--', alpha=0.7, 
                          label=f'Fib {level_name}' if level_name in ['0.382', '0.618'] else None)
        
        for level_name, price in fib_levels.extension.items():
            main_ax.axhline(y=price, color='red', linestyle='--', alpha=0.7,
                          label=f'Fib Ext {level_name}' if level_name in ['1.272', '1.618'] else None)