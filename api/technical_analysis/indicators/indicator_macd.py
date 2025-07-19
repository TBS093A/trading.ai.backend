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
from ..draw_utils import DrawUtils


class IndicatorMACD(Indicator):
    """Wskaźnik MACD (Moving Average Convergence Divergence)"""
    
    def __init__(self):
        super().__init__("MACD")
        self.fast_period = 12
        self.slow_period = 26
        self.signal_period = 9
    
    def calculate(
        self, 
        klines: List[Dict[str, Union[int, float, str]]], 
        fast_period: int = 12, 
        slow_period: int = 26, 
        signal_period: int = 9, 
        **kwargs
    ) -> None:
        """
        Oblicza wskaźnik MACD (Moving Average Convergence Divergence):
            - macd_line: Wartości linii MACD
            - signal_line: Wartości linii sygnałowej
            - histogram: Wartości histogramu
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            fast_period: Okres szybkiej średniej (domyślnie 12)
            slow_period: Okres wolnej średniej (domyślnie 26)
            signal_period: Okres linii sygnałowej (domyślnie 9)
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        
        if len(klines) < slow_period + signal_period:
            self.calculated_data = {"macd_line": [], "signal_line": [], "histogram": []}
            return

        closes = np.array([float(k['close']) for k in klines])
        
        # Obliczanie EMA
        ema_fast = self._calculate_ema(closes, fast_period)
        ema_slow = self._calculate_ema(closes, slow_period)
        
        # Linia MACD
        macd_line = ema_fast - ema_slow
        
        # Linia sygnałowa
        signal_line = self._calculate_ema(macd_line, signal_period)
        
        # Histogram
        histogram = macd_line - signal_line
        
        self.calculated_data = {
            "macd_line": macd_line.tolist(),
            "signal_line": signal_line.tolist(),
            "histogram": histogram.tolist()
        }
        
        # Dodaj MACD do klines dla kompatybilności
        for i, (macd_val, signal_val, hist_val) in enumerate(zip(macd_line, signal_line, histogram)):
            if i < len(klines):
                klines[i]['macd'] = macd_val
                klines[i]['signal'] = signal_val
                klines[i]['histogram'] = hist_val
    
    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> np.ndarray:
        """Oblicza wykładniczą średnią ruchomą (EMA)"""
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
            
        return ema
    
    def draw(self, main_ax, df: pd.DataFrame, add_plots: List, panel: int, **kwargs) -> int:
        """
        Rysuje MACD na wykresie.
        
        Args:
            main_ax: Główna oś wykresu
            df: DataFrame z danymi cenowymi
            add_plots: Lista dodatkowych wykresów
            panel: Numer panelu do rysowania
            **kwargs: Dodatkowe parametry (show_macd, dynamic_font_size_axes)
            
        Returns:
            int: Numer następnego dostępnego panelu
        """
        show_macd = kwargs.get('show_macd', True)
        dynamic_font_size_axes = kwargs.get('dynamic_font_size_axes', 14)
        
        if not show_macd:
            logger.debug("MACD pominięte (show_macd=False)")
            return panel
        
        if not all(col in df.columns for col in ['macd', 'signal']):
            logger.warning("Brak danych MACD w DataFrame")
            return panel
        
        try:
            # Dodaj linię MACD
            add_plots.append(
                mpf.make_addplot(df['macd'], panel=panel, color='blue', ylabel='MACD')
            )
            
            # Dodaj linię sygnałową
            add_plots.append(
                mpf.make_addplot(df['signal'], panel=panel, color='red')
            )
            
            # Dodaj histogram jeśli dostępny
            if 'histogram' in df.columns:
                add_plots.append(
                    mpf.make_addplot(df['histogram'], panel=panel, type='bar', color='gray', alpha=0.8)
                )
            
            logger.info(f"MACD dodane do panelu {panel}")
            
            # Zastosuj skalowaną czcionkę do osi MACD jeśli dostępne
            if hasattr(main_ax, '__len__') and len(main_ax) > panel:
                macd_ax = main_ax[panel]
                DrawUtils.apply_scaled_font_to_axes(macd_ax, [macd_ax], dynamic_font_size_axes)
                logger.debug(f"Zastosowano skalowaną czcionkę {dynamic_font_size_axes}px do osi MACD")
            
            return panel + 1
            
        except Exception as e:
            logger.error(f"Błąd podczas rysowania MACD: {e}")
            logger.error(traceback.format_exc())
            return panel
