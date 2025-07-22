import numpy as np
from typing import List, Dict, Union, Optional, Tuple, Type
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

from .technical_analysis.indicators import IndicatorRSI, IndicatorMACD, IndicatorOBV
from .technical_analysis.technical_analysis_objects import (
    Fibonacci, FibonacciTargets, FibonacciAllHarmonicPatternPointsLevels,
    HarmonicPatterns, HarmonicPatternsForming, AllMedianLineAndrewsPitchfork,
    AllAlternatePriceProjection
)

class TechnicalAnalysisFactory:
    """Fabryka obiektów analizy technicznej"""
    
    def __init__(self):
        pass
    
    # Metody zwracające obiekty wskaźników
    def get_indicator_rsi(self) -> IndicatorRSI:
        """Zwraca obiekt wskaźnika RSI"""
        return IndicatorRSI()
    
    def get_indicator_macd(self) -> IndicatorMACD:
        """Zwraca obiekt wskaźnika MACD"""
        return IndicatorMACD()
    
    def get_indicator_obv(self) -> IndicatorOBV:
        """Zwraca obiekt wskaźnika OBV"""
        return IndicatorOBV()
    
    # Metody zwracające klasy wskaźników
    def get_indicator_rsi_class(self) -> Type[IndicatorRSI]:
        """Zwraca klasę wskaźnika RSI"""
        return IndicatorRSI
    
    def get_indicator_macd_class(self) -> Type[IndicatorMACD]:
        """Zwraca klasę wskaźnika MACD"""
        return IndicatorMACD
    
    def get_indicator_obv_class(self) -> Type[IndicatorOBV]:
        """Zwraca klasę wskaźnika OBV"""
        return IndicatorOBV
    
    # Metody zwracające obiekty analizy technicznej
    def get_fibonacci(self) -> Fibonacci:
        """Zwraca obiekt Fibonacci"""
        return Fibonacci()
    
    def get_fibonacci_targets(self) -> FibonacciTargets:
        """Zwraca obiekt FibonacciTargets"""
        return FibonacciTargets()
    
    def get_fibonacci_all_harmonic_pattern_points_levels(self) -> FibonacciAllHarmonicPatternPointsLevels:
        """Zwraca obiekt FibonacciAllHarmonicPatternPointsLevels"""
        return FibonacciAllHarmonicPatternPointsLevels()
    
    def get_harmonic_patterns(self, 
                             general_fibonacci_levels: dict[str, bool] = None,
                             all_points_fibonacci_levels: dict[str, bool] = None,
                             all_fibonacci_targets: dict[str, bool] = None,
                             use_database: bool = False,
                             database_factory = None,
                             asset_id: int = None) -> HarmonicPatterns:
        """Zwraca obiekt HarmonicPatterns z opcjonalnymi parametrami konfiguracyjnymi"""
        # Użyj domyślnych wartości jeśli parametry są None
        if general_fibonacci_levels is None:
            general_fibonacci_levels = {
                'show': False,
                'retracement': False,
                'extension': False
            }
        if all_points_fibonacci_levels is None:
            all_points_fibonacci_levels = {
                'show': False,
                'retracement': False,
                'extension': False
            }
        if all_fibonacci_targets is None:
            all_fibonacci_targets = {
                'show': False
            }
        
        return HarmonicPatterns(
            general_fibonacci_levels=general_fibonacci_levels,
            all_points_fibonacci_levels=all_points_fibonacci_levels,
            all_fibonacci_targets=all_fibonacci_targets,
            use_database=use_database,
            database_factory=database_factory,
            asset_id=asset_id
        )
    
    def get_harmonic_patterns_forming(self,
                                     general_fibonacci_levels: dict[str, bool] = None,
                                     all_points_fibonacci_levels: dict[str, bool] = None,
                                     all_fibonacci_targets: dict[str, bool] = None) -> HarmonicPatternsForming:
        """Zwraca obiekt HarmonicPatternsForming z opcjonalnymi parametrami konfiguracyjnymi"""
        # Użyj domyślnych wartości jeśli parametry są None
        if general_fibonacci_levels is None:
            general_fibonacci_levels = {
                'show': False,
                'retracement': False,
                'extension': False
            }
        if all_points_fibonacci_levels is None:
            all_points_fibonacci_levels = {
                'show': False,
                'retracement': False,
                'extension': False
            }
        if all_fibonacci_targets is None:
            all_fibonacci_targets = {
                'show': False
            }
        
        return HarmonicPatternsForming(
            general_fibonacci_levels=general_fibonacci_levels,
            all_points_fibonacci_levels=all_points_fibonacci_levels,
            all_fibonacci_targets=all_fibonacci_targets
        )
    
    def get_all_median_line_andrews_pitchfork(self) -> AllMedianLineAndrewsPitchfork:
        """Zwraca obiekt AllMedianLineAndrewsPitchfork"""
        return AllMedianLineAndrewsPitchfork()
    
    def get_all_alternate_price_projection(self) -> AllAlternatePriceProjection:
        """Zwraca obiekt AllAlternatePriceProjection"""
        return AllAlternatePriceProjection()
    
    # Metody zwracające klasy analizy technicznej
    def get_fibonacci_class(self) -> Type[Fibonacci]:
        """Zwraca klasę Fibonacci"""
        return Fibonacci
    
    def get_fibonacci_targets_class(self) -> Type[FibonacciTargets]:
        """Zwraca klasę FibonacciTargets"""
        return FibonacciTargets
    
    def get_fibonacci_all_harmonic_pattern_points_levels_class(self) -> Type[FibonacciAllHarmonicPatternPointsLevels]:
        """Zwraca klasę FibonacciAllHarmonicPatternPointsLevels"""
        return FibonacciAllHarmonicPatternPointsLevels
    
    def get_harmonic_patterns_class(self) -> Type[HarmonicPatterns]:
        """Zwraca klasę HarmonicPatterns"""
        return HarmonicPatterns
    
    def get_harmonic_patterns_forming_class(self) -> Type[HarmonicPatternsForming]:
        """Zwraca klasę HarmonicPatternsForming"""
        return HarmonicPatternsForming
    
    def get_all_median_line_andrews_pitchfork_class(self) -> Type[AllMedianLineAndrewsPitchfork]:
        """Zwraca klasę AllMedianLineAndrewsPitchfork"""
        return AllMedianLineAndrewsPitchfork
    
    def get_all_alternate_price_projection_class(self) -> Type[AllAlternatePriceProjection]:
        """Zwraca klasę AllAlternatePriceProjection"""
        return AllAlternatePriceProjection
    
    # Metody pomocnicze
    def get_all_indicators(self) -> Dict[str, object]:
        """Zwraca słownik wszystkich obiektów wskaźników"""
        return {
            'IndicatorRSI': self.get_indicator_rsi(),
            'IndicatorMACD': self.get_indicator_macd(),
            'IndicatorOBV': self.get_indicator_obv()
        }
    
    def get_all_indicator_classes(self) -> Dict[str, Type]:
        """Zwraca słownik wszystkich klas wskaźników"""
        return {
            'IndicatorRSI': self.get_indicator_rsi_class(),
            'IndicatorMACD': self.get_indicator_macd_class(),
            'IndicatorOBV': self.get_indicator_obv_class()
        }
    
    def get_all_technical_analysis_objects(self, 
                                          harmonic_patterns_config: dict = None,
                                          harmonic_patterns_forming_config: dict = None) -> Dict[str, object]:
        """Zwraca słownik wszystkich obiektów analizy technicznej z opcjonalną konfiguracją"""
        # Domyślna konfiguracja dla HarmonicPatterns
        if harmonic_patterns_config is None:
            harmonic_patterns_config = {
                'general_fibonacci_levels': {'show': False, 'retracement': False, 'extension': False},
                'all_points_fibonacci_levels': {'show': False, 'retracement': False, 'extension': False},
                'all_fibonacci_targets': {'show': False}
            }
        
        # Domyślna konfiguracja dla HarmonicPatternsForming
        if harmonic_patterns_forming_config is None:
            harmonic_patterns_forming_config = {
                'general_fibonacci_levels': {'show': False, 'retracement': False, 'extension': False},
                'all_points_fibonacci_levels': {'show': False, 'retracement': False, 'extension': False},
                'all_fibonacci_targets': {'show': False}
            }
        
        return {
            'Fibonacci': self.get_fibonacci(),
            'FibonacciTargets': self.get_fibonacci_targets(),
            'FibonacciAllHarmonicPatternPointsLevels': self.get_fibonacci_all_harmonic_pattern_points_levels(),
            'HarmonicPatterns': self.get_harmonic_patterns(**harmonic_patterns_config),
            'HarmonicPatternsForming': self.get_harmonic_patterns_forming(**harmonic_patterns_forming_config),
            'AllMedianLineAndrewsPitchfork': self.get_all_median_line_andrews_pitchfork(),
            'AllAlternatePriceProjection': self.get_all_alternate_price_projection()
        }
    
    def get_all_technical_analysis_object_classes(self) -> Dict[str, Type]:
        """Zwraca słownik wszystkich klas analizy technicznej"""
        return {
            'Fibonacci': self.get_fibonacci_class(),
            'FibonacciTargets': self.get_fibonacci_targets_class(),
            'FibonacciAllHarmonicPatternPointsLevels': self.get_fibonacci_all_harmonic_pattern_points_levels_class(),
            'HarmonicPatterns': self.get_harmonic_patterns_class(),
            'HarmonicPatternsForming': self.get_harmonic_patterns_forming_class(),
            'AllMedianLineAndrewsPitchfork': self.get_all_median_line_andrews_pitchfork_class(),
            'AllAlternatePriceProjection': self.get_all_alternate_price_projection_class()
        } 