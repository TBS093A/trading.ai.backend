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

from .indicators import IndicatorRSI, IndicatorMACD, IndicatorOBV
from .technical_analysis_objects import Fibonacci, FibonacciTargets, FibonacciAllHarmonicPatternPointsLevels, HarmonicPatterns, HarmonicPatternsForming, AllMedianLineAndrewsPitchfork, AllAlternatePriceProjection

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
            enabled_indicators: Lista nazw wskaźników do obliczenia (None = nie obliczaj żadnych)
            enabled_objects: Lista nazw obiektów analizy technicznej do obliczenia (None = nie obliczaj żadnych)
            **kwargs: Dodatkowe parametry przekazywane do poszczególnych metod calculate
        """
        # Wyczyść poprzednie obliczenia
        self.indicators.clear()
        self.technical_analysis_objects.clear()
        
        # Oblicz wskaźniki tylko jeśli podano enabled_indicators
        if enabled_indicators is not None:
            for indicator_name in enabled_indicators:
                if indicator_name in self.INDICATORS:
                    indicator_class = self.INDICATORS[indicator_name]
                    indicator_instance = indicator_class()
                    indicator_instance.calculate(klines, **kwargs)
                    self.indicators.append(indicator_instance)
                    logger.info(f"Obliczono wskaźnik: {indicator_name}")
        
        # Oblicz obiekty analizy technicznej tylko jeśli podano enabled_objects
        if enabled_objects is not None:
            for object_name in enabled_objects:
                if object_name in self.TECHNICAL_ANALYSIS_OBJECTS:
                    object_class = self.TECHNICAL_ANALYSIS_OBJECTS[object_name]
                    object_instance = object_class()
                    object_instance.calculate(klines, **kwargs)
                    self.technical_analysis_objects.append(object_instance)
                    logger.info(f"Obliczono obiekt analizy technicznej: {object_name}")
    
    def draw_candlestick_chart(self, klines: List[Dict[str, Union[int, float, str]]], 
                              save_path: Optional[str] = None, title: str = "Wykres świecowy",
                              enabled_indicators: Dict[str, Type] = None,
                              enabled_objects: Dict[str, Type] = None,
                              **kwargs) -> str:
        """
        Tworzy wykres świecowy używając obliczonych indicators i technical analysis objects.
        
        Args:
            klines: Lista świeczek zawierająca dane OHLCV oraz obliczone wskaźniki i wzorce
            save_path: Opcjonalna ścieżka do zapisu wykresu
            title: Tytuł wykresu
            enabled_indicators: Słownik z nazwami wskaźników jako kluczami i klasami jako wartościami
            enabled_objects: Słownik z nazwami obiektów jako kluczami i klasami jako wartościami
            **kwargs: Dodatkowe parametry konfiguracji wykresu
            
        Returns:
            Base64 string z obrazkiem wykresu
        """
        # Inicjalizuj konfigurację wykresu
        chart_config = self.__init_candlestick_chart_config(klines, title, **kwargs)
        
        # Jeśli podano enabled_indicators lub enabled_objects, oblicz je
        if enabled_indicators is not None or enabled_objects is not None:
            # Dodaj chart_config do kwargs
            kwargs_with_config = {**kwargs, 'chart_config': chart_config}
            self.calculate(klines, enabled_indicators, enabled_objects, **kwargs_with_config)
        
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
        
        # Przygotowanie dodatkowych wskaźników
        add_plots = []
        panel = 2  # Licznik paneli dla wskaźników
        active_panels = []
        
        # Dodaj wskaźniki używając metod draw
        for indicator in self.indicators:
            # Przekaż parametry konfiguracyjne do wskaźnika
            indicator_kwargs = {**kwargs, 'dynamic_font_size_axes': chart_config['dynamic_font_size_axes']}
            panel = indicator.draw(None, df, add_plots, panel, **indicator_kwargs)
            if panel > 2:  # Jeśli panel się zwiększył, znaczy że wskaźnik został dodany
                active_panels.append(indicator.get_active_panel_name(**kwargs))
        
        # Oblicz panel_ratios używając metod wskaźników
        panel_ratios = [6]  # Panel 0: główny panel z cenami
        
        if 'volume' in df.columns:
            panel_ratios.append(1)  # Panel 1: volume
        
        # Dodaj proporcje paneli tylko dla aktywnych wskaźników
        for indicator in self.indicators:
            panel_ratio = indicator.get_panel_ratio(**kwargs)
            if panel_ratio > 0 and indicator.get_active_panel_name(**kwargs) in active_panels:
                panel_ratios.append(panel_ratio)
        
        logger.info(f"Panel ratios: {panel_ratios} dla paneli: główny + volume + {active_panels}")
        
        # Utwórz wykres z konfiguracją
        try:
            # Przygotuj parametr addplot - mplfinance nie akceptuje None
            addplot_param = add_plots if add_plots else []
            
            fig, axes = mpf.plot(
                df,
                type='candle',
                style=self.CHART_STYLES["binance_dark"],
                title=chart_config['title'],
                volume='volume' in df.columns,
                addplot=addplot_param,
                returnfig=True,
                figsize=(chart_config['dynamic_width'], chart_config['dynamic_height']),
                yscale='log',  # Skala logarytmiczna dla osi Y
                datetime_format='%H:%M %d/%m/%Y',  # Format daty i czasu na osi X
                xrotation=45,  # Obrót etykiet osi X dla lepszej czytelności
                tight_layout=True,  # Lepsze rozłożenie elementów
                show_nontrading=False,  # Ukryj okresy bez tradingu
                scale_padding=dict(left=0.3, right=1.0, top=1.2, bottom=1.2),  # Zwiększony padding dla etykiet
                panel_ratios=panel_ratios  # Kontrola wysokości paneli
            )
            
            # Pobierz główną oś
            if isinstance(axes, list):
                main_ax = axes[0]
            else:
                main_ax = axes
            
            # Zastosuj dodatkowe ustawienia wykresu
            self.__apply_chart_axis_settings(main_ax, axes, df, chart_config)
            
            # Rysuj obiekty analizy technicznej
            for tech_obj in self.technical_analysis_objects:
                tech_obj.draw(main_ax, df, klines, **kwargs)
            
            # Zapisz wykres jako base64
            buffer = BytesIO()
            fig.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
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
                    style=self.CHART_STYLES["binance_dark"],
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
    
    def __init_candlestick_chart_config(self, klines: List[Dict[str, Union[int, float, str]]], 
                                       title: str, **kwargs) -> Dict:
        """
        Inicjalizuje konfigurację wykresu świecowego.
        
        Args:
            klines: Lista świeczek
            title: Tytuł wykresu
            **kwargs: Parametry konfiguracyjne
            
        Returns:
            Dict: Konfiguracja wykresu
        """
        # Konwersja danych do DataFrame dla obliczeń
        df = pd.DataFrame(klines)
        df['date'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('date', inplace=True)
        
        # Konwersja kolumn na float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        # Oblicz wymiary wykresu
        chart_dimensions = self.__calculate_chart_dimensions(df, **kwargs)
        
        # Oblicz parametry osi
        axis_params = self.__calculate_axis_parameters(df, **kwargs)
        
        # Oblicz parametry paddingu
        padding_params = self.__calculate_padding_parameters(df, chart_dimensions, **kwargs)
        
        # Oblicz parametry czcionek
        font_params = self.__calculate_font_parameters(chart_dimensions, **kwargs)
        
        # Przygotuj dane wzorców
        patterns_data = self.__prepare_patterns_data(klines, **kwargs)
        
        # Zaktualizuj tytuł
        updated_title = self.__update_chart_title(title, patterns_data, **kwargs)
        
        return {
            'dynamic_width': chart_dimensions['dynamic_width'],
            'dynamic_height': chart_dimensions['dynamic_height'],
            'tick_interval': axis_params['tick_interval'],
            'y_format': axis_params['y_format'],
            'base_ticks': axis_params['base_ticks'],
            'padding_ratio': padding_params['padding_ratio'],
            'single_padding_factor': padding_params['single_padding_factor'],
            'dynamic_font_size_labels': font_params['dynamic_font_size_labels'],
            'dynamic_font_size_axes': font_params['dynamic_font_size_axes'],
            'dynamic_font_size_fibo_labels': font_params['dynamic_font_size_fibo_labels'],
            'title': updated_title,
            'patterns_data': patterns_data
        }
    
    def __calculate_chart_dimensions(self, df: pd.DataFrame, **kwargs) -> Dict:
        """Oblicza wymiary wykresu na podstawie danych"""
        candles_count = len(df)
        base_width = 5  # Domyślna szerokość dla 50 świec
        base_candles = 50  # Bazowa liczba świec
        
        # Skalowanie szerokości: na każde 50 świec dodaj 15 jednostek szerokości
        width_multiplier = max(1, candles_count / base_candles)
        dynamic_width = int(base_width * width_multiplier)
        
        # Ustal minimalną i maksymalną szerokość dla praktyczności
        min_width = 10
        max_width = 100
        dynamic_width = max(min_width, min(dynamic_width, max_width))
        
        # Oblicz dynamiczną wysokość wykresu na podstawie zakresu cenowego
        y_min_for_height = df[['low']].min().iloc[0]
        y_max_for_height = df[['high']].max().iloc[0]
        price_range_for_height = y_max_for_height - y_min_for_height
        
        # Bazowa wysokość dla określonego zakresu cenowego
        base_height = 20  # Domyślna wysokość
        
        # Oblicz proporcję cenową i dostosuj wysokość
        if price_range_for_height > 0:
            price_ratio = y_max_for_height / y_min_for_height if y_min_for_height > 0 else 1
            height_multiplier = max(0.8, min(3.0, np.log10(price_ratio) + 1))
            dynamic_height = int(base_height * height_multiplier)
        else:
            dynamic_height = base_height
        
        # Ustal minimalną i maksymalną wysokość dla praktyczności
        min_height = 20
        
        # Użyj metod wskaźników do obliczenia dodatkowej wysokości
        for indicator in self.indicators:
            height_adjustment = indicator.get_min_height_adjustment(**kwargs)
            min_height += height_adjustment
        
        max_height = 100
        dynamic_height = max(min_height, min(dynamic_height, max_height))
        
        logger.info(f"Dynamiczna szerokość wykresu: {dynamic_width} (dla {candles_count} świec, mnożnik: {width_multiplier:.2f})")
        logger.info(f"Dynamiczna wysokość wykresu: {dynamic_height} (dla zakresu {price_range_for_height:.6f}, ratio: {y_max_for_height/y_min_for_height if y_min_for_height > 0 else 1:.2f})")
        
        return {
            'dynamic_width': dynamic_width,
            'dynamic_height': dynamic_height,
            'candles_count': candles_count,
            'width_multiplier': width_multiplier,
            'price_range_for_height': price_range_for_height
        }
    
    def __calculate_axis_parameters(self, df: pd.DataFrame, **kwargs) -> Dict:
        """Oblicza parametry osi X i Y"""
        candles_count = len(df)
        
        # Oblicz interwał dla osi X na podstawie ilości świec
        if candles_count <= 200:
            tick_interval = 1  # Co piąta świeca
        elif candles_count > 200:
            tick_interval = candles_count / 100
            
        logger.info(f"Interwał osi X: co {tick_interval} świeca (dla {candles_count} świec)")
        
        # Oblicz parametry formatowania osi Y
        y_min = df[['low']].min().iloc[0]
        y_max = df[['high']].max().iloc[0]
        price_range = y_max - y_min
        
        # Oblicz liczbę tick-ów dla osi Y
        min_ticks = 16
        max_ticks = 48
        base_ticks = max(min_ticks, min(max_ticks, int(10 * np.log10(y_max/y_min)))) if price_range > 0 else 10
        
        # Określ format liczb na podstawie zakresu wartości
        if y_max < 0.01:
            y_format = '%.6f'
        elif y_max < 1:
            y_format = '%.4f'
        elif y_max < 1000:
            y_format = '%.2f'
        else:
            y_format = '%.0f'
        
        logger.info(f"Parametry osi Y: {base_ticks} tick-ów, format {y_format}, zakres: {y_min:.6f} - {y_max:.6f}")
        
        return {
            'tick_interval': tick_interval,
            'y_format': y_format,
            'base_ticks': base_ticks,
            'y_min': y_min,
            'y_max': y_max,
            'price_range': price_range
        }
    
    def __calculate_padding_parameters(self, df: pd.DataFrame, chart_dimensions: Dict, **kwargs) -> Dict:
        """Oblicza parametry paddingu dla etykiet wzorców harmonicznych"""
        dynamic_height = chart_dimensions['dynamic_height']
        
        # Oblicz dodatkowy padding dla etykiet wzorców harmonicznych
        fig_height_inches = dynamic_height
        dpi = 300
        fig_height_pixels = fig_height_inches * dpi
        
        # Konwersja 5000px na proporcję wysokości wykresu
        padding_pixels = 10000
        
        # Użyj metod wskaźników do obliczenia dodatkowego paddingu
        for indicator in self.indicators:
            padding_adjustment = indicator.get_padding_adjustment(**kwargs)
            padding_pixels += padding_adjustment
        
        padding_ratio = padding_pixels / fig_height_pixels
        
        # Oblicz padding w jednostkach cenowych dla skali logarytmicznej
        single_padding_factor = padding_ratio * 0.15  # Współczynnik dla skali log
        
        logger.info(f"Obliczony padding: {padding_pixels}px = {padding_ratio:.4f} ratio = {single_padding_factor:.4f} factor na stronę")
        
        return {
            'padding_ratio': padding_ratio,
            'single_padding_factor': single_padding_factor,
            'padding_pixels': padding_pixels,
            'fig_height_pixels': fig_height_pixels
        }
    
    def __calculate_font_parameters(self, chart_dimensions: Dict, **kwargs) -> Dict:
        """Oblicza parametry czcionek na podstawie wymiarów wykresu"""
        dynamic_width = chart_dimensions['dynamic_width']
        dynamic_height = chart_dimensions['dynamic_height']
        
        # Oblicz dynamiczną wielkość czcionki na podstawie rozmiaru wykresu i paddingu
        base_font_size_labels = 12  # wielkość bazowa dla etykiet
        base_font_size_axes = 14  # Oddzielna wielkość bazowa dla wartości na osiach 
        base_font_size_fibo_labels = 6  # Wielkość bazowa dla etykiet Fibonacci
        width_factor = max(0.5, min(2.0, dynamic_width / 15))  # Skalowanie na podstawie szerokości
        height_factor = max(0.5, min(2.0, dynamic_height / 20))  # Skalowanie na podstawie wysokości
        padding_factor = max(0.8, min(1.5, dynamic_height / 30))  # Dodatkowy czynnik dla paddingu
        scaling_ratio = (width_factor + height_factor + padding_factor) / 3  # Wspólny współczynnik skalowania
        
        dynamic_font_size_labels = int(base_font_size_labels * scaling_ratio)  # Dla etykiet
        dynamic_font_size_axes = int(base_font_size_axes * scaling_ratio)  # Dla osi
        dynamic_font_size_fibo_labels = int(base_font_size_fibo_labels * scaling_ratio)  # Dla etykiet Fibonacci
        
        logger.info(f"Dynamiczna wielkość czcionki - etykiety: {dynamic_font_size_labels}, osi: {dynamic_font_size_axes}, fibonacci: {dynamic_font_size_fibo_labels} (współczynnik: {scaling_ratio:.3f}, szerokość: {width_factor:.2f}, wysokość: {height_factor:.2f}, padding: {padding_factor:.2f})")
        
        return {
            'dynamic_font_size_labels': dynamic_font_size_labels,
            'dynamic_font_size_axes': dynamic_font_size_axes,
            'dynamic_font_size_fibo_labels': dynamic_font_size_fibo_labels,
            'scaling_ratio': scaling_ratio
        }
    
    def __prepare_patterns_data(self, klines: List[Dict[str, Union[int, float, str]]], **kwargs) -> List:
        """Przygotowuje dane wzorców harmonicznych"""
        show_patterns = kwargs.get('show_patterns', True)
        if not show_patterns:
            return []
        
        patterns_data = []
        forming_patterns_data = []
        
        for i, kline in enumerate(klines):
            # Wzorce formed
            if 'patterns' in kline:
                for pattern_id, pattern_info in kline['patterns'].items():
                    if 'pattern_point_name' in pattern_info and 'pattern_point_price' in pattern_info:
                        patterns_data.append({
                            'index': i,
                            'pattern_id': pattern_id,
                            'point_name': pattern_info['pattern_point_name'],
                            'price': pattern_info['pattern_point_price'],
                            'pattern_name': pattern_info.get('pattern_name', ''),
                            'pattern_type': pattern_info.get('pattern_type', ''),
                            'is_bullish': pattern_info.get('pattern_is_bullish', False),
                            'is_formed': pattern_info.get('pattern_is_formed', False),
                            'tolerance_strategy': pattern_info.get('pattern_fib_tolerance_strategy', ''),
                            'tolerance': pattern_info.get('pattern_fib_tolerance', 0),
                        })
            
            # Wzorce forming
            if 'forming_patterns' in kline:
                for pattern_id, pattern_info in kline['forming_patterns'].items():
                    if 'pattern_point_name' in pattern_info and 'pattern_point_price' in pattern_info:
                        forming_patterns_data.append({
                            'index': i,
                            'pattern_id': pattern_id,
                            'point_name': pattern_info['pattern_point_name'],
                            'price': pattern_info['pattern_point_price'],
                            'pattern_name': pattern_info.get('pattern_name', ''),
                            'pattern_type': pattern_info.get('pattern_type', ''),
                            'is_bullish': pattern_info.get('pattern_is_bullish', False),
                        })
        
        logger.info(f"Znalezione wzorce: {len(patterns_data)} punktów formed, {len(forming_patterns_data)} punktów forming")
        
        return patterns_data + forming_patterns_data
    
    def __update_chart_title(self, title: str, patterns_data: List, **kwargs) -> str:
        """Aktualizuje tytuł wykresu o informacje o wzorcach"""
        show_patterns = kwargs.get('show_patterns', True)
        
        if show_patterns and patterns_data:
            # Znajdź wzorce z ich nazwami do wyświetlenia w tytule wykresu
            pattern_names = set()
            for pattern in patterns_data:
                if pattern['pattern_name']:
                    pattern_names.add(pattern['pattern_name'].split('_')[0])  # Tylko nazwa wzorca bez parametrów
                            
            if pattern_names:
                title += f" | Wzorce: {', '.join(sorted(pattern_names))}"
        
        return title
    
    def __apply_chart_axis_settings(self, main_ax, axes, df: pd.DataFrame, chart_config: Dict):
        """Stosuje ustawienia osi wykresu"""
        # Dodaj dodatkowy padding dla etykiet wzorców harmonicznych (jednakowy górny i dolny)
        try:
            # Pobierz aktualne granice osi Y
            y_min_current, y_max_current = main_ax.get_ylim()
            
            # Oblicz zakres cenowy w skali logarytmicznej
            log_y_min = np.log(y_min_current) if y_min_current > 0 else np.log(0.0001)
            log_y_max = np.log(y_max_current) if y_max_current > 0 else np.log(0.0001)
            log_range = log_y_max - log_y_min
            
            # Oblicz padding w skali logarytmicznej (jednakowy górny i dolny)
            log_padding = log_range * chart_config['single_padding_factor']
            
            # Zastosuj padding symetrycznie w skali logarytmicznej
            log_y_min_padded = log_y_min - log_padding
            log_y_max_padded = log_y_max + log_padding
            
            # Konwertuj z powrotem do skali liniowej
            y_min_padded = np.exp(log_y_min_padded)
            y_max_padded = np.exp(log_y_max_padded)
            
            # Ustaw nowe granice osi Y
            main_ax.set_ylim(y_min_padded, y_max_padded)
            
            # Oblicz faktyczne paddingiem w jednostkach cenowych dla logowania
            bottom_padding = y_min_current - y_min_padded
            top_padding = y_max_padded - y_max_current
            
            logger.info(f"Ustawiono równy padding osi Y:")
            logger.info(f"  Przed: {y_min_current:.6f} - {y_max_current:.6f}")
            logger.info(f"  Po:    {y_min_padded:.6f} - {y_max_padded:.6f}")
            logger.info(f"  Padding dolny: {abs(bottom_padding):.6f}, górny: {top_padding:.6f}")
            
        except Exception as e:
            logger.warning(f"Nie można ustawić paddingu osi Y: {e}")

        # Dostosuj formatowanie osi X po utworzeniu wykresu
        try:
            import matplotlib.ticker as ticker
            # Ustawij locator dla osi X z obliczonym interwałem
            main_ax.xaxis.set_major_locator(ticker.MultipleLocator(chart_config['tick_interval']))
            main_ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
            
            # Poprawa formatowania osi Y dla skali logarytmicznej
            main_ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.4f'))
            main_ax.yaxis.set_minor_formatter(ticker.NullFormatter())

            # Obrócenie Labeli pod bardziej czytelną formę
            for ax in axes:
                for label in ax.get_xticklabels():
                    label.set_rotation(90)
            
            logger.info(f"Ustawiono tick interwał {chart_config['tick_interval']} dla osi X i formatowanie dla skali logarytmicznej")
        except Exception as e:
            logger.warning(f"Nie można ustawić formatowania osi: {e}")
        
        # Dostosuj formatowanie osi bezpośrednio po utworzeniu wykresu
        yticks = np.geomspace(df['low'].min(), df['high'].max(), num=10)
        axes[0].set_yticks(yticks)
        axes[0].get_yaxis().set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:,.0f}'))
