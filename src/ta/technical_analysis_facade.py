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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from .technical_analysis import TechnicalAnalysis
from .technical_analysis_factory import TechnicalAnalysisFactory
from .draw_utils import DrawUtils


class TechnicalAnalysisFacade:

    def __init__(self):
        self.technical_analysis = TechnicalAnalysis()
        self.draw_utils = DrawUtils()
        self.factory = TechnicalAnalysisFactory()

    def get_technical_analysis_factory(self) -> TechnicalAnalysisFactory:
        """Zwraca fabrykę obiektów analizy technicznej"""
        return self.factory

    async def calculate(self, klines: List[Dict[str, Union[int, float, str]]], 
                  enabled_indicators: Dict[str, Union[Type, object]] = None, 
                  enabled_objects: Dict[str, Union[Type, object]] = None, **kwargs) -> None:
        """
        Oblicza wskaźniki i obiekty analizy technicznej.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            enabled_indicators: Słownik z nazwami wskaźników jako kluczami i klasami jako wartościami (None = nie obliczaj żadnych)
            enabled_objects: Słownik z nazwami obiektów jako kluczami i klasami jako wartościami (None = nie obliczaj żadnych)
            **kwargs: Dodatkowe parametry przekazywane do poszczególnych metod calculate
        """
        await self.technical_analysis.calculate(klines, enabled_indicators, enabled_objects, **kwargs)

    async def create_candlestick_chart(self, klines: List[Dict[str, Union[int, float, str]]], 
                                save_path: Optional[str] = None, title: str = "Wykres świecowy",
                                enabled_indicators: Dict[str, Union[Type, object]] = None,
                                enabled_objects: Dict[str, Union[Type, object]] = None,
                                **kwargs) -> str:
        return await self.technical_analysis.draw_candlestick_chart(
            klines, save_path, title, enabled_indicators, enabled_objects, **kwargs
        )
