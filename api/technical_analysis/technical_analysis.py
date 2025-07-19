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

from indicators import IndicatorRSI, IndicatorMACD, IndicatorOBV
from technical_analysis_objects import Fibonacci, FibonacciTargets, FibonacciAllHarmonicPatternPointsLevels, HarmonicPatterns, HarmonicPatternsForming, AllMedianLineAndrewsPitchfork, AllAlternatePriceProjection

class TechnicalAnalysis:
    """Główna klasa analizy technicznej używająca wzorca Strategy Pattern"""
    
    # Słowniki z dostępnymi klasami indicators i technical analysis objects
    INDICATORS = {
        'IndicatorRSI': IndicatorRSI,
        'IndicatorMACD': IndicatorMACD,
        'IndicatorOBV': IndicatorOBV
    }
    
    TECHNICAL_ANALYSIS_OBJECTS = {
        'Fibonacci': Fibonacci,
        'FibonacciTargets': FibonacciTargets,
        'FibonacciAllHarmonicPatternPointsLevels': FibonacciAllHarmonicPatternPointsLevels,
        'HarmonicPatterns': HarmonicPatterns,
        'HarmonicPatternsForming': HarmonicPatternsForming,
        'AllMedianLineAndrewsPitchfork': AllMedianLineAndrewsPitchfork,
        'AllAlternatePriceProjection': AllAlternatePriceProjection
    }

    # candlestick chart style
    CHART_STYLES = {
        "binance_dark": {
            "base_mpl_style": "dark_background",
            "marketcolors": {
                "candle": {"up": "#3dc985", "down": "#ef4f60"},  
                "edge": {"up": "#3dc985", "down": "#ef4f60"},  
                "wick": {"up": "#3dc985", "down": "#ef4f60"},  
                "ohlc": {"up": "green", "down": "red"},
                "volume": {"up": "#247252", "down": "#82333f"},  
                "vcedge": {"up": "green", "down": "red"},  
                "vcdopcod": False,
                "alpha": 1,
            },
            "mavcolors": ("#ad7739", "#a63ab2", "#62b8ba"),
            "facecolor": "#1b1f24",
            "gridcolor": "#2c2e31",
            "gridstyle": "--",
            "y_on_right": True,
            "rc": {
                "axes.grid": True,
                "axes.grid.axis": "y",
                "axes.edgecolor": "#474d56",
                "axes.titlecolor": "red",
                "figure.facecolor": "#161a1e",
                "figure.titlesize": "x-large",
                "figure.titleweight": "semibold",
            },
            "base_mpf_style": "binance-dark",
        }
    }

    def __init__(self):
        """Inicjalizuje obiekty indicators i technical analysis objects"""
        self.indicators = []
        self.technical_analysis_objects = []
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], 
                  enabled_indicators: List[str] = None, 
                  enabled_objects: List[str] = None, **kwargs) -> None:
        """
        Oblicza wszystkie enabled indicators i technical analysis objects.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            enabled_indicators: Lista nazw wskaźników do obliczenia
            enabled_objects: Lista nazw obiektów analizy technicznej do obliczenia
            **kwargs: Dodatkowe parametry przekazywane do poszczególnych metod calculate
        """
        # Jeśli nie podano, włącz wszystkie
        if enabled_indicators is None:
            enabled_indicators = list(self.INDICATORS.keys())
        if enabled_objects is None:
            enabled_objects = list(self.TECHNICAL_ANALYSIS_OBJECTS.keys())
        
        # Wyczyść poprzednie obliczenia
        self.indicators.clear()
        self.technical_analysis_objects.clear()
        
        # Oblicz wskaźniki
        for indicator_name in enabled_indicators:
            if indicator_name in self.INDICATORS:
                indicator_class = self.INDICATORS[indicator_name]
                indicator_instance = indicator_class()
                indicator_instance.calculate(klines, **kwargs)
                self.indicators.append(indicator_instance)
                logger.info(f"Obliczono wskaźnik: {indicator_name}")
        
        # Oblicz obiekty analizy technicznej
        for object_name in enabled_objects:
            if object_name in self.TECHNICAL_ANALYSIS_OBJECTS:
                object_class = self.TECHNICAL_ANALYSIS_OBJECTS[object_name]
                object_instance = object_class()
                object_instance.calculate(klines, **kwargs)
                self.technical_analysis_objects.append(object_instance)
                logger.info(f"Obliczono obiekt analizy technicznej: {object_name}")
    
    def draw_candlestick_chart(self, klines: List[Dict[str, Union[int, float, str]]], 
                              save_path: Optional[str] = None, title: str = "Wykres świecowy",
                              **kwargs) -> str:
        """
        Tworzy wykres świecowy używając obliczonych indicators i technical analysis objects.
        
        Args:
            klines: Lista świeczek zawierająca dane OHLCV oraz obliczone wskaźniki i wzorce
            save_path: Opcjonalna ścieżka do zapisu wykresu
            title: Tytuł wykresu
            **kwargs: Dodatkowe parametry konfiguracji wykresu
            
        Returns:
            Base64 string z obrazkiem wykresu
        """
        # Konwersja danych do formatu pandas DataFrame
        df = pd.DataFrame(klines)
        df['date'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('date', inplace=True)
        
        # Konwersja kolumn na float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        # Filtruj kolumny przed rysowaniem
        columns_to_keep = ['open', 'high', 'low', 'close', 'volume']
        
        # Dodaj kolumny z wskaźnikami technicznymi jeśli istnieją
        for col in df.columns:
            if col in ['rsi', 'macd', 'signal', 'histogram', 'obv']:
                columns_to_keep.append(col)
            elif col.startswith('fib_'):
                columns_to_keep.append(col)
            elif col.startswith('pattern_') and col.endswith('_price'):
                columns_to_keep.append(col)
            elif col.startswith('forming_pattern_') and col.endswith('_price'):
                columns_to_keep.append(col)
        
        # Filtruj DataFrame do tylko potrzebnych kolumn
        df = df[columns_to_keep]
        
        # Sprawdź czy DataFrame nie jest pusty po filtrowaniu
        if df.empty:
            logger.warning("DataFrame jest pusty po filtrowaniu - używam oryginalnych danych")
            df = pd.DataFrame(klines)
            df['date'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('date', inplace=True)
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        
        # Przygotowanie stylu wykresu
        mc = mpf.make_marketcolors(up='green', down='red', edge='inherit', wick='inherit', volume='in')
        s = mpf.make_mpf_style(marketcolors=mc, gridstyle='dotted', y_on_right=False)
        
        # Przygotowanie dodatkowych wskaźników
        add_plots = []
        panel = 2  # Licznik paneli dla wskaźników
        active_panels = []
        
        # Dodaj wskaźniki używając metod draw
        for indicator in self.indicators:
            panel = indicator.draw(None, df, add_plots, panel, **kwargs)
            if panel > 2:  # Jeśli panel się zwiększył, znaczy że wskaźnik został dodany
                active_panels.append(indicator.name)
        
        # Oblicz panel_ratios
        panel_ratios = [6]  # Panel 0: główny panel z cenami
        
        if 'volume' in df.columns:
            panel_ratios.append(1)  # Panel 1: volume
        
        for _ in active_panels:
            panel_ratios.append(1)  # Każdy wskaźnik dostaje małą wysokość
        
        logger.info(f"Panel ratios: {panel_ratios} dla paneli: główny + volume + {active_panels}")
        
        # Utwórz wykres
        try:
            fig, axes = mpf.plot(
                df,
                type='candle',
                style=s,
                volume=True if 'volume' in df.columns else False,
                addplot=add_plots if add_plots else None,
                title=title,
                ylabel='Cena',
                ylabel_lower='Wolumen' if 'volume' in df.columns else None,
                figsize=(16, 12),
                panel_ratios=panel_ratios,
                returnfig=True,
                warn_too_much_data=3000
            )
            
            # Pobierz główną oś
            if isinstance(axes, list):
                main_ax = axes[0]
            else:
                main_ax = axes
            
            # Rysuj obiekty analizy technicznej
            for tech_obj in self.technical_analysis_objects:
                tech_obj.draw(main_ax, df, klines, **kwargs)
            
            # Zapisz wykres jako base64
            buffer = BytesIO()
            fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
            buffer.seek(0)
            chart_base64 = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            if save_path:
                with open(save_path, 'wb') as f:
                    f.write(base64.b64decode(chart_base64))
                logger.info(f"Wykres zapisany w: {save_path}")
            
            logger.info(f"Wykres skonwertowany do base64 ({len(chart_base64)} znaków)")
            return chart_base64
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wykresu: {e}")
            logger.error(traceback.format_exc())
            
            # Fallback - prosty wykres bez dodatkowych elementów
            try:
                fig, axes = mpf.plot(
                    df[['open', 'high', 'low', 'close']],
                    type='candle',
                    style=s,
                    title=f"{title} (tryb awaryjny)",
                    ylabel='Cena',
                    figsize=(12, 8),
                    returnfig=True
                )
                
                buffer = BytesIO()
                fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
                buffer.seek(0)
                chart_base64 = base64.b64encode(buffer.getvalue()).decode()
                plt.close(fig)
                
                logger.info("Utworzono wykres w trybie awaryjnym")
                return chart_base64
                
            except Exception as fallback_error:
                logger.error(f"Błąd nawet w trybie awaryjnym: {fallback_error}")
                return ""
