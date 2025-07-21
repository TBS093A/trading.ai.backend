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

from .abstract_technical_analysis_object import TechnicalAnalysisObject
from ..draw_utils import DrawUtils


class FibonacciAllHarmonicPatternPointsLevels(TechnicalAnalysisObject):
    """Wszystkie poziomy Fibonacciego dla kombinacji punktów"""
    
    def __init__(self):
        super().__init__("FibonacciAllHarmonicPatternPointsLevels")
    
    def calculate(self, *args, **kwargs) -> None:
        """
        Oblicza wszystkie poziomy Fibonacciego dla kombinacji punktów
        
        Args:
            pattern_points: Słownik punktów wzorca w formacie {point_name: {'index': int, 'price': float}}
        """
        self.calculated_data = self.__calculate_all_points_fibonacci(kwargs.get('pattern_points'))

    def __calculate_all_points_fibonacci(
        self,
        pattern_points: Dict[str, Dict[str, Union[int, float]]]
    ) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Oblicza poziomy Fibonacciego dla wszystkich kombinacji punktów XABCD wzorca harmonicznego.
        
        Args:
            pattern_points: Słownik punktów wzorca w formacie {point_name: {'index': int, 'price': float}}
            
        Returns:
            Słownik zawierający poziomy Fibonacci dla wszystkich kombinacji punktów
            Struktura: {
                'XA': {'retracement': {...}, 'extension': {...}, 'targets': {...}},
                'XB': {'retracement': {...}, 'extension': {...}, 'targets': {...}},
                ...
            }
        """
        all_fibos = {}
        
        # Lista wszystkich dostępnych punktów
        available_points = list(pattern_points.keys())
        
        # Generuj wszystkie kombinacje punktów (każdy z każdym)
        for point1 in available_points:
            for point2 in available_points:
                if point1 != point2:  # Nie obliczaj dla tego samego punktu
                    combination_name = f"{point1}{point2}"
                    
                    # Pobierz ceny punktów
                    start_price = float(pattern_points[point1]['price'])
                    end_price = float(pattern_points[point2]['price'])
                    
                    # Określ czy to trend wzrostowy czy spadkowy
                    is_uptrend = end_price > start_price
                    
                    # Oblicz zakres cenowy
                    price_range = abs(end_price - start_price)
                    
                    if price_range == 0:
                        # Jeśli punkty mają tę samą cenę, pomiń
                        continue
                    
                    # Oblicz poziomy retracementu (od end_price w kierunku start_price)
                    retracement = {}
                    for level_name, level_ratio in [
                        ("0.0", 0.0), ("0.236", 0.236), ("0.382", 0.382), ("0.5", 0.5), 
                        ("0.618", 0.618), ("0.786", 0.786), ("0.886", 0.886), ("1.0", 1.0)
                    ]:
                        if is_uptrend:
                            # Dla trendu wzrostowego: retracement w dół od end_price
                            retracement[level_name] = end_price - (price_range * level_ratio)
                        else:
                            # Dla trendu spadkowego: retracement w górę od end_price
                            retracement[level_name] = end_price + (price_range * level_ratio)
                    
                    # Oblicz poziomy extension (przedłużenie ruchu poza end_price)
                    extension = {}
                    for level_name, level_ratio in [
                        ("1.13", 1.13), ("1.272", 1.272), ("1.414", 1.414), ("1.618", 1.618), 
                        ("2.0", 2.0), ("2.24", 2.24), ("2.618", 2.618), ("3.14", 3.14), ("3.618", 3.618)
                    ]:
                        if is_uptrend:
                            # Dla trendu wzrostowego: extension w górę od end_price
                            extension[level_name] = end_price + (price_range * (level_ratio - 1.0))
                        else:
                            # Dla trendu spadkowego: extension w dół od end_price
                            extension[level_name] = end_price - (price_range * (level_ratio - 1.0))
                    
                    # Oblicz targety (kombinacja retracement i extension)
                    targets = {}
                    for level_name, level_ratio in [
                        ("0.236", 0.236), ("0.382", 0.382), ("0.5", 0.5), ("0.618", 0.618), 
                        ("0.786", 0.786), ("0.886", 0.886), ("1.13", 1.13), ("1.272", 1.272), 
                        ("1.414", 1.414), ("1.618", 1.618), ("2.0", 2.0), ("2.24", 2.24), 
                        ("2.618", 2.618), ("3.14", 3.14), ("3.618", 3.618)
                    ]:
                        if level_ratio <= 1.0:
                            # Poziomy poniżej 100% - jako retracement
                            if is_uptrend:
                                targets[level_name] = end_price - (price_range * level_ratio)
                            else:
                                targets[level_name] = end_price + (price_range * level_ratio)
                        else:
                            # Poziomy powyżej 100% - jako extension
                            if is_uptrend:
                                targets[level_name] = end_price + (price_range * (level_ratio - 1.0))
                            else:
                                targets[level_name] = end_price - (price_range * (level_ratio - 1.0))
                    
                    # Zapisz obliczone poziomy dla tej kombinacji
                    all_fibos[combination_name] = {
                        'retracement': retracement,
                        'extension': extension,
                        'targets': targets,
                        'start_price': start_price,
                        'end_price': end_price,
                        'is_uptrend': is_uptrend,
                        'price_range': price_range
                    }
        
        return all_fibos
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje wszystkie poziomy Fibonacciego używając DrawUtils"""
        if self.calculated_data is None:
            return
        
        show_all_fibonacci_levels = kwargs.get('show_all_fibonacci_levels', True)
        show_all_retracement_levels = kwargs.get('show_all_retracement_levels', True)
        show_all_extension_levels = kwargs.get('show_all_extension_levels', True)
        
        if not show_all_fibonacci_levels:
            return
        
        # Przygotuj dane w formacie wymaganym przez DrawUtils
        fibonacci_data = []
        pattern_groups = {}
        
        # Konwertuj dane do formatu wymaganego przez DrawUtils
        for fib_entry in self.calculated_data:
            all_fibos = fib_entry['all_fibos']
            pattern_id = fib_entry.get('pattern_id', 'unknown')
            pattern_type = fib_entry.get('pattern_type', 'unknown')
            
            # Konwertuj all_fibos do formatu fibonacci
            fibonacci = {
                'retracement': {},
                'extension': {},
                'targets': {}
            }
            
            # Agreguj wszystkie poziomy z all_fibos
            for combination_name, fib_data in all_fibos.items():
                if 'retracement' in fib_data:
                    for level_name, price in fib_data['retracement'].items():
                        if price > 0:
                            fibonacci['retracement'][f"{combination_name}_{level_name}"] = price
                
                if 'extension' in fib_data:
                    for level_name, price in fib_data['extension'].items():
                        if price > 0:
                            fibonacci['extension'][f"{combination_name}_{level_name}"] = price
                
                if 'targets' in fib_data:
                    for level_name, price in fib_data['targets'].items():
                        if price > 0:
                            fibonacci['targets'][f"{combination_name}_{level_name}"] = price
            
            fibonacci_data.append({
                'kline_idx': fib_entry['kline_idx'],
                'pattern_id': pattern_id,
                'fibonacci': fibonacci
            })
            
            # Przygotuj pattern_groups jeśli nie istnieje
            if pattern_id not in pattern_groups:
                pattern_groups[pattern_id] = {
                    'points': {},
                    'pattern_retraces': {},
                    'pattern_name': pattern_type,
                    'pattern_type': pattern_type,
                    'is_bullish': True  # Domyślnie bullish
                }
        
        # Użyj DrawUtils do rysowania
        DrawUtils.draw_fibonacci_lines_with_labels(
            main_ax=main_ax,
            fibonacci_data=fibonacci_data,
            pattern_groups=pattern_groups,
            klines=klines,
            dynamic_font_size_fibo_labels=kwargs.get('dynamic_font_size_fibo_labels', 8),
            df=df,
            show_all_fibo_targets=False,  # FibonacciAllHarmonicPatternPointsLevels - nie targety
            show_fibonacci=False,  # FibonacciAllHarmonicPatternPointsLevels - nie podstawowe poziomy
            show_all_fibonacci_levels=True,  # FibonacciAllHarmonicPatternPointsLevels - włącz wszystkie poziomy
            show_all_retracement_levels=show_all_retracement_levels,  # FibonacciAllHarmonicPatternPointsLevels - włącz retracement
            show_all_extension_levels=show_all_extension_levels  # FibonacciAllHarmonicPatternPointsLevels - włącz extension
        )
