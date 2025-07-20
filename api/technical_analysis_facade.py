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

from .technical_analysis.technical_analysis import TechnicalAnalysis
from .technical_analysis.draw_utils import DrawUtils

class TechnicalAnalysisFacade:

    def __init__(self):
        self.technical_analysis = TechnicalAnalysis()
        self.draw_utils = DrawUtils()

    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], 
                  enabled_indicators: List[str] = None, 
                  enabled_objects: List[str] = None, **kwargs) -> None:
        self.technical_analysis.calculate(klines, enabled_indicators, enabled_objects, **kwargs)

    def create_candlestick_chart(self, klines: List[Dict[str, Union[int, float, str]]], 
                                save_path: Optional[str] = None, title: str = "Wykres świecowy",
                                **kwargs) -> str:
        return self.technical_analysis.draw_candlestick_chart(klines, save_path, title, **kwargs)
