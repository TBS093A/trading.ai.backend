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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from .abstract_technical_analysis_object import TechnicalAnalysisObject, FibonacciLevels
from ..draw_utils import DrawUtils

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
        
        self.calculated_data = self.__calculate_fibonacci_levels(start_price, end_price, is_uptrend)
    
    def __calculate_fibonacci_levels(
        self,
        start_price: float,
        end_price: float,
        is_uptrend: bool
    ) -> FibonacciLevels:
        """
        Oblicza poziomy Fibonacciego dla danego ruchu cenowego.
        
        Args:
            start_price: Cena początkowa
            end_price: Cena końcowa
            is_uptrend: Czy trend jest wzrostowy
            
        Returns:
            Obiekt FibonacciLevels zawierający poziomy retracementu, extension i targety
        """
        price_range = abs(end_price - start_price)
        
        # Poziomy retracementu (wewnętrzne zniesienia): 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 88.6%, 100%
        retracement = {
            "0.0": end_price + (price_range * 0.0 if is_uptrend else -price_range * 0.0),        # 0%
            "0.236": end_price + (price_range * 0.236 if is_uptrend else -price_range * 0.236),  # 23.6%
            "0.382": end_price + (price_range * 0.382 if is_uptrend else -price_range * 0.382),  # 38.2%
            "0.5": end_price + (price_range * 0.5 if is_uptrend else -price_range * 0.5),        # 50%
            "0.618": end_price + (price_range * 0.618 if is_uptrend else -price_range * 0.618),  # 61.8%
            "0.786": end_price + (price_range * 0.786 if is_uptrend else -price_range * 0.786),  # 78.6%
            "0.886": end_price + (price_range * 0.886 if is_uptrend else -price_range * 0.886),  # 88.6%
            "1.0": end_price + (price_range * 1.0 if is_uptrend else -price_range * 1.0)         # 100%
        }
        
        # Poziomy extension (zewnętrzne rozszerzenia): 113%, 127.2%, 141.4%, 161.8%, 200%, 224%, 261.8%, 314%, 361.8%
        extension = {
            "1.13": end_price + (price_range * 1.13 if is_uptrend else -price_range * 1.13),     # 113%
            "1.272": end_price + (price_range * 1.272 if is_uptrend else -price_range * 1.272),  # 127.2%
            "1.414": end_price + (price_range * 1.414 if is_uptrend else -price_range * 1.414),  # 141.4%
            "1.618": end_price + (price_range * 1.618 if is_uptrend else -price_range * 1.618),  # 161.8%
            "2.0": end_price + (price_range * 2.0 if is_uptrend else -price_range * 2.0),        # 200%
            "2.24": end_price + (price_range * 2.24 if is_uptrend else -price_range * 2.24),     # 224%
            "2.618": end_price + (price_range * 2.618 if is_uptrend else -price_range * 2.618),  # 261.8%
            "3.14": end_price + (price_range * 3.14 if is_uptrend else -price_range * 3.14),     # 314%
            "3.618": end_price + (price_range * 3.618 if is_uptrend else -price_range * 3.618)   # 361.8%
        }
        
        # Targety cenowe (kombinacja wewnętrznych i zewnętrznych): 23.6%, 38.2%, 50%, 61.8%, 78.6%, 88.6%, 113%, 127.2%, 141.4%, 161.8%, 200%, 224%, 261.8%, 314%, 361.8%
        targets = {
            "0.236": end_price + (price_range * 0.236 if is_uptrend else -price_range * 0.236),  # 23.6%
            "0.382": end_price + (price_range * 0.382 if is_uptrend else -price_range * 0.382),  # 38.2%
            "0.5": end_price + (price_range * 0.5 if is_uptrend else -price_range * 0.5),        # 50%
            "0.618": end_price + (price_range * 0.618 if is_uptrend else -price_range * 0.618),  # 61.8%
            "0.786": end_price + (price_range * 0.786 if is_uptrend else -price_range * 0.786),  # 78.6%
            "0.886": end_price + (price_range * 0.886 if is_uptrend else -price_range * 0.886),  # 88.6%
            "1.13": end_price + (price_range * 1.13 if is_uptrend else -price_range * 1.13),     # 113%
            "1.272": end_price + (price_range * 1.272 if is_uptrend else -price_range * 1.272),  # 127.2%
            "1.414": end_price + (price_range * 1.414 if is_uptrend else -price_range * 1.414),  # 141.4%
            "1.618": end_price + (price_range * 1.618 if is_uptrend else -price_range * 1.618),  # 161.8%
            "2.0": end_price + (price_range * 2.0 if is_uptrend else -price_range * 2.0),        # 200%
            "2.24": end_price + (price_range * 2.24 if is_uptrend else -price_range * 2.24),     # 224%
            "2.618": end_price + (price_range * 2.618 if is_uptrend else -price_range * 2.618),  # 261.8%
            "3.14": end_price + (price_range * 3.14 if is_uptrend else -price_range * 3.14),     # 314%
            "3.618": end_price + (price_range * 3.618 if is_uptrend else -price_range * 3.618)   # 361.8%
        }
        
        # Puste pole all_fibos - będzie wypełnione przez calculate_all_points_fibonacci
        all_fibos = {}
        
        return FibonacciLevels(retracement, extension, targets, all_fibos)
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje podstawowe poziomy Fibonacciego używając DrawUtils"""
        if self.calculated_data is None:
            return
        
        show_fibonacci = kwargs.get('show_fibonacci', False)
        if not show_fibonacci:
            return
        
        # Przygotuj dane w formacie wymaganym przez DrawUtils
        fibonacci_data = []
        pattern_groups = {}
        
        # Konwertuj dane do formatu wymaganego przez DrawUtils
        for kline_idx, kline in enumerate(klines):
            if 'patterns' in kline:
                for pattern_id, pattern_info in kline['patterns'].items():
                    if 'fibonacci' in pattern_info:
                        fibonacci_data.append({
                            'kline_idx': kline_idx,
                            'pattern_id': pattern_id,
                            'fibonacci': pattern_info['fibonacci']
                        })
                        
                        # Przygotuj pattern_groups jeśli nie istnieje
                        if pattern_id not in pattern_groups:
                            pattern_groups[pattern_id] = {
                                'points': {},
                                'pattern_retraces': {},
                                'pattern_name': pattern_info.get('pattern_name', ''),
                                'pattern_type': pattern_info.get('pattern_type', ''),
                                'is_bullish': pattern_info.get('pattern_is_bullish', False)
                            }
        
        # Użyj DrawUtils do rysowania
        DrawUtils.draw_fibonacci_lines_with_labels(
            main_ax=main_ax,
            fibonacci_data=fibonacci_data,
            pattern_groups=pattern_groups,
            klines=klines,
            dynamic_font_size_fibo_labels=kwargs.get('dynamic_font_size_fibo_labels', 8),
            df=df,
            show_all_fibo_targets=False,  # Fibonacci - tylko podstawowe poziomy
            show_fibonacci=True,  # Fibonacci - włącz podstawowe poziomy
            show_all_fibonacci_levels=False,  # Fibonacci - nie wszystkie poziomy
            show_all_retracement_levels=True,  # Fibonacci - włącz retracement
            show_all_extension_levels=True  # Fibonacci - włącz extension
        )