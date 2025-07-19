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
    
    def get_panel_ratio(self, **kwargs) -> int:
        """
        Zwraca proporcję panelu dla wskaźnika.
        
        Args:
            **kwargs: Dodatkowe parametry
            
        Returns:
            int: Proporcja panelu (1 = mały panel)
        """
        show_param = kwargs.get(f'show_{self.name.lower()}', True)
        return 1 if show_param else 0
    
    def get_min_height_adjustment(self, **kwargs) -> int:
        """
        Zwraca dodatkową wysokość potrzebną dla wskaźnika.
        
        Args:
            **kwargs: Dodatkowe parametry
            
        Returns:
            int: Dodatkowa wysokość w jednostkach
        """
        show_param = kwargs.get(f'show_{self.name.lower()}', True)
        return 10 if show_param else 0
    
    def get_padding_adjustment(self, **kwargs) -> int:
        """
        Zwraca dodatkowy padding potrzebny dla wskaźnika.
        
        Args:
            **kwargs: Dodatkowe parametry
            
        Returns:
            int: Dodatkowy padding w pikselach
        """
        show_param = kwargs.get(f'show_{self.name.lower()}', True)
        return 5000 if show_param else 0
    
    def is_enabled(self, **kwargs) -> bool:
        """
        Sprawdza czy wskaźnik jest włączony.
        
        Args:
            **kwargs: Parametry konfiguracyjne
            
        Returns:
            bool: True jeśli wskaźnik jest włączony
        """
        show_param = kwargs.get(f'show_{self.name.lower()}', True)
        return show_param
    
    def get_active_panel_name(self, **kwargs) -> str:
        """
        Zwraca nazwę aktywnego panelu dla wskaźnika.
        
        Args:
            **kwargs: Dodatkowe parametry
            
        Returns:
            str: Nazwa panelu (nazwa wskaźnika w małych literach)
        """
        return self.name.lower() if self.is_enabled(**kwargs) else ''
