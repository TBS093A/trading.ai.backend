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


class AllFibonacciLevels(TechnicalAnalysisObject):
    """Wszystkie poziomy Fibonacciego dla kombinacji punktów"""
    
    def __init__(self):
        super().__init__("AllFibonacciLevels")
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], **kwargs) -> None:
        """Oblicza wszystkie poziomy Fibonacciego dla kombinacji punktów"""
        fibonacci_data = []
        
        # Przeiteruj przez wszystkie klines i znajdź poziomy Fibonacciego
        for kline_idx, kline in enumerate(klines):
            if 'patterns' in kline:
                for pattern_id, pattern_data in kline['patterns'].items():
                    if 'fibonacci' in pattern_data and 'all_fibos' in pattern_data['fibonacci']:
                        all_fibos = pattern_data['fibonacci']['all_fibos']
                        
                        for combination_name, fib_data in all_fibos.items():
                            fibonacci_data.append({
                                'kline_idx': kline_idx,
                                'pattern_id': pattern_id,
                                'combination_name': combination_name,
                                'fib_data': fib_data
                            })
        
        self.calculated_data = fibonacci_data
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje wszystkie poziomy Fibonacciego"""
        if self.calculated_data is None:
            return
        
        show_all_fibonacci_levels = kwargs.get('show_all_fibonacci_levels', True)
        show_all_retracement_levels = kwargs.get('show_all_retracement_levels', True)
        show_all_extension_levels = kwargs.get('show_all_extension_levels', True)
        
        if not show_all_fibonacci_levels:
            return
        
        self._draw_all_fibonacci_levels(
            main_ax, self.calculated_data, {}, klines, 8, df, len(df),
            float(df.index[0].timestamp()), float(df.index[-1].timestamp()),
            show_all_retracement_levels, show_all_extension_levels
        )
    
    def _draw_all_fibonacci_levels(self, main_ax, fibonacci_data, pattern_groups, klines, 
                                  dynamic_font_fibo_y_labels, df, chart_end_x, x_min, x_max,
                                  show_all_retracement_levels=True, show_all_extension_levels=True):
        """Implementacja rysowania wszystkich poziomów Fibonacciego"""
        try:
            def get_fibonacci_color(fib_type, level_name):
                if fib_type == 'retracement':
                    retracement_colors = {
                        '0.186': '#00ff7f', '0.236': '#32cd32', '0.382': '#90ee90',
                        '0.5': '#98fb98', '0.618': '#adff2f', '0.68': '#7fff00',
                        '0.786': '#9acd32', '0.886': '#6b8e23'
                    }
                    return retracement_colors.get(level_name, '#90EE90')
                else:
                    extension_colors = {
                        '1.13': '#1e90ff', '1.272': '#4169e1', '1.414': '#0000ff',
                        '1.618': '#191970', '2.0': '#000080', '2.24': '#483d8b',
                        '2.618': '#6a5acd', '3.14': '#9370db', '3.618': '#8b008b'
                    }
                    return extension_colors.get(level_name, '#87CEEB')
        
            def should_include_level(combination_name, fib_type, level_name, pattern_type=''):
                crucial_retracement = ['0.236', '0.382', '0.5', '0.618', '0.786', '0.886']
                crucial_extension = ['1.13', '1.272', '1.414', '1.618', '2.0', '2.24', '2.618']
                
                if fib_type == 'retracement':
                    return show_all_retracement_levels and level_name in crucial_retracement
                elif fib_type == 'extension':
                    return show_all_extension_levels and level_name in crucial_extension
                
                return False
            
            # Rysuj linie Fibonacciego
            for fib_entry in fibonacci_data:
                combination_name = fib_entry['combination_name']
                fib_data = fib_entry['fib_data']
                
                for fib_type in ['retracement', 'extension']:
                    if fib_type in fib_data:
                        for level_name, price in fib_data[fib_type].items():
                            if should_include_level(combination_name, fib_type, level_name):
                                color = get_fibonacci_color(fib_type, level_name)
                                
                                main_ax.axhline(y=price, color=color, linestyle='--', alpha=0.6, linewidth=1)
                                
                                # Dodaj etykietę
                                main_ax.text(x_max * 0.98, price, f'{combination_name} {level_name}',
                                           fontsize=dynamic_font_fibo_y_labels, color=color,
                                           ha='right', va='center', alpha=0.8)
        
        except Exception as e:
            logger.error(f"Błąd podczas rysowania poziomów Fibonacciego: {e}")
