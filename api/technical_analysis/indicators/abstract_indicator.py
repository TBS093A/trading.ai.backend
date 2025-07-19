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

# Klasy abstrakcyjne
class Indicator(ABC):
    """Abstrakcyjna klasa bazowa dla wszystkich wskaźników technicznych"""
    
    def __init__(self, name: str):
        self.name = name
        self.calculated_data = None
    
    @abstractmethod
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], **kwargs) -> None:
        """Oblicza dane wskaźnika"""
        pass
    
    @abstractmethod
    def draw(self, main_ax, df: pd.DataFrame, add_plots: List, panel: int, **kwargs) -> int:
        """Rysuje wskaźnik na wykresie. Zwraca numer następnego dostępnego panelu"""
        pass
