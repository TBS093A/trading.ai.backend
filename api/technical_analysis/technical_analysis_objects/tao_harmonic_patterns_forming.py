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


class HarmonicPatternsForming(TechnicalAnalysisObject):
    """Wzorce harmoniczne w trakcie formowania"""
    
    def __init__(self):
        super().__init__("HarmonicPatternsForming")
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], 
                  min_points: int = 5, symbol: str = '', interval: str = '',
                  find_only_xabcd: bool = True, **kwargs) -> None:
        """Oblicza wzorce harmoniczne w trakcie formowania"""
        patterns_count = self._calculate_forming_patterns(
            klines, min_points, symbol, interval, find_only_xabcd
        )
        self.calculated_data = patterns_count
    
    def _calculate_forming_patterns(self, klines, min_points, symbol, interval, find_only_xabcd):
        """Implementacja obliczania wzorców w trakcie formowania"""
        if not PYHARMONICS_AVAILABLE:
            logger.error("pyharmonics nie jest dostępne. Zainstaluj: pip install pyharmonics")
            return 0
        
        if len(klines) < min_points:
            return 0

        try:
            # Analogiczna implementacja jak w HarmonicPatterns, ale dla forming patterns
            df = self._convert_klines_to_dataframe(klines)
            technicals = Technicals(df, symbol, interval)
            harmonic_search = HarmonicSearch(technicals)
            harmonic_search.forming()
            
            if find_only_xabcd:
                patterns = harmonic_search.get_patterns(formed=False, family=harmonic_search.XABCD)
            else:
                patterns = harmonic_search.get_patterns(formed=False)
            
            patterns_count = 0
            
            for pattern_type_key in patterns:
                pattern_list = patterns[pattern_type_key]
                patterns_count += len(pattern_list)
                # Przetworz wzorce forming (implementacja analogiczna do HarmonicPatterns)
            
            return patterns_count

        except Exception as e:
            logger.error(f"Błąd podczas wykrywania wzorców forming: {e}")
            return 0
    
    def _convert_klines_to_dataframe(self, klines):
        """Konwertuje dane klines na DataFrame wymagany przez pyharmonics"""
        # Identyczna implementacja jak w HarmonicPatterns
        df = pd.DataFrame(klines)
        df['date'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('date', inplace=True)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        columns_to_keep = ['open', 'high', 'low', 'close', 'volume']
        df = df[columns_to_keep]
        return df
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje wzorce w trakcie formowania"""
        # Implementacja rysowania forming patterns (podobna do HarmonicPatterns ale z innym stylem)
        pass