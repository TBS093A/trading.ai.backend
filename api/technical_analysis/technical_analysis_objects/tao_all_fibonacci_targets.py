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


class AllTargetsFibonacci(TechnicalAnalysisObject):
    """Wszystkie targety Fibonacciego (PRZ, TP, SL)"""
    
    def __init__(self):
        super().__init__("AllTargetsFibonacci")
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], **kwargs) -> None:
        """Oblicza wszystkie targety Fibonacciego z wzorców harmonicznych"""
        targets_data = []
        
        # Przeiteruj przez wszystkie klines i znajdź targety Fibonacciego
        for kline_idx, kline in enumerate(klines):
            if 'patterns' in kline:
                for pattern_id, pattern_data in kline['patterns'].items():
                    if 'fibonacci' in pattern_data and 'all_targets' in pattern_data['fibonacci']:
                        all_targets = pattern_data['fibonacci']['all_targets']
                        
                        for target_name, target_info in all_targets.items():
                            targets_data.append({
                                'kline_idx': kline_idx,
                                'pattern_id': pattern_id,
                                'target_name': target_name,
                                'target_info': target_info
                            })
        
        self.calculated_data = targets_data
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje targety Fibonacciego (PRZ, TP, SL)"""
        if self.calculated_data is None:
            return
        
        show_all_fibo_targets = kwargs.get('show_all_fibo_targets', False)
        if not show_all_fibo_targets:
            return
        
        for target_data in self.calculated_data:
            target_info = target_data['target_info']
            target_name = target_data['target_name']
            
            if target_info['type'] == 'line':
                color = 'orange' if 'TP' in target_name else 'red' if 'SL' in target_name else 'purple'
                main_ax.axhline(y=target_info['price'], color=color, linestyle='-', alpha=0.8,
                              label=target_name)
            elif target_info['type'] == 'zone':
                main_ax.axhspan(target_info['min_price'], target_info['max_price'], 
                              alpha=0.2, color='purple', label=f'PRZ {target_name}')
