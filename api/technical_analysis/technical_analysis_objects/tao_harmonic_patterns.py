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

from abstract_technical_analysis_object import TechnicalAnalysisObject, HarmonicPattern
from tao_fibonacci import Fibonacci
from tao_fibonacci_all_harmonic_pattern_points_levels import FibonacciAllHarmonicPatternPointsLevels
from tao_fibonacci_targets import FibonacciTargets


class HarmonicPatterns(TechnicalAnalysisObject):
    """Wzorce harmoniczne XABCD"""
    
    def __init__(self):
        super().__init__("HarmonicPatterns")
        # Inicjalizuj obiekty Fibonacci do współpracy
        self.fibonacci = Fibonacci()
        self.fibonacci_all_levels = FibonacciAllHarmonicPatternPointsLevels()
        self.fibonacci_targets = FibonacciTargets()
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], 
                  min_points: int = 5, symbol: str = '', interval: str = '',
                  find_only_xabcd: bool = True, **kwargs) -> None:
        """Oblicza wzorce harmoniczne XABCD"""
        patterns_count = self.__calculate_harmonic_patterns(
            klines, min_points, symbol, interval, find_only_xabcd, kwargs
        )
        self.calculated_data = patterns_count
    
    def __calculate_harmonic_patterns(
        self,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5,
        symbol: str = '',
        interval: str = '',
        find_only_xabcd: bool = True,
        fib_tolerance_strategy: dict[str, float] = {
            'hard_restricted': 0.03,
        },
        peak_spacing_strategy: dict[str, int] = {
            'extra_huge_30': 30,
            'extra_huge_29': 29,
            'extra_huge_28': 28,
            'extra_huge_27': 27,
            'extra_huge_26': 26,
            'extra_huge_25': 25,
            'extra_huge_24': 24,
            'extra_huge_23': 23,
            'extra_huge_22': 22,
            'extra_huge_21': 21,
            'extra_huge_20': 20,
            'extra_huge_19': 19,
            'extra_huge_18': 18,
            'extra_huge_17': 17,
            'extra_huge_16': 16,
            'extra_huge_15': 15,
            'extra_huge_14': 14,
            'extra_huge_13': 13,
            'very_huge': 12,
            'middle-very_huge-huge': 11,
            'huge': 10,
            'middle-huge-large': 9,
            'large': 8,
            'middle-large-medium': 7,
            'medium': 6,
            'middle-medium-small': 5,
            'small': 4,
            'middle-small-tiny': 3,
        },
        check_anchor: bool = True
    ) -> int:
        """
        Oblicza formacje harmoniczne XABCD używając biblioteki pyharmonics
        i nanosi punkty wzorców bezpośrednio na odpowiednie świece w klines.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            symbol: Symbol krypto
            interval: Interwał czasowy
            find_only_xabcd: Czy szukać tylko wzorców XABCD
            fib_tolerance_strategy: Strategia tolerancji dla poziomów Fibonacciego
            peak_spacing_strategy: Strategia spacji między punktami wzorca
            check_anchor: Czy sprawdzać punkt anker
            
        Returns:
            Liczba znalezionych wzorców
        """
        if not PYHARMONICS_AVAILABLE:
            logger.error("pyharmonics nie jest dostępne. Zainstaluj: pip install pyharmonics")
            return 0
        
        if len(klines) < min_points:
            return 0

        try:
            # Konwertuj dane na DataFrame wymagany przez pyharmonics
            df = self._convert_klines_to_dataframe(klines)
            
            # Inicjalizuj Technicals z pyharmonics
            for peak_spacing_strategy_name, peak_spacing in peak_spacing_strategy.items():
                technicals = Technicals(
                    df, 
                    symbol, 
                    interval,
                    peak_spacing=peak_spacing
                )

                # Wykonaj wyszukiwanie wzorców
                for fib_tolerance_strategy_name, fib_tolerance in fib_tolerance_strategy.items():
                    logger.info(f"Wyszukiwanie wzorców z tolerancją {fib_tolerance_strategy_name}: {fib_tolerance} i spacji {peak_spacing_strategy_name}: {peak_spacing}")
                    harmonic_search = HarmonicSearch(
                        technicals,
                        fib_tolerance=fib_tolerance, 
                        check_anchor=check_anchor
                    )
                    harmonic_search.search()

                    # Pobierz wszystkie wzorce
                    if find_only_xabcd:
                        patterns = harmonic_search.get_patterns(
                            family=harmonic_search.XABCD
                        )
                    else:
                        patterns = harmonic_search.get_patterns()

                    logger.info(f"Znaleziono wzorce dla tolerancji {fib_tolerance_strategy_name} i spacji {peak_spacing_strategy_name}: {list(patterns.keys()) if patterns else 'brak'}")

                    patterns_count = 0

                    # Przetwórz wzorce i nanieś punkty na klines
                    for pattern_type_key in patterns:
                        pattern_list = patterns[pattern_type_key]
                        logger.info(f"Przetwarzanie {len(pattern_list)} wzorców typu {pattern_type_key} dla tolerancji {fib_tolerance_strategy_name} i spacji {peak_spacing_strategy_name}")

                        for pattern_idx, pattern in enumerate(pattern_list):
                            try:
                                # Pobierz punkty z wzorca
                                x_points = pattern.x
                                y_points = pattern.y

                                if len(y_points) < 3:
                                    continue

                                # Utwórz DataFrame dla mapowania
                                df_map = pd.DataFrame(klines)
                                df_map['date'] = pd.to_datetime(df_map['open_time'], unit='ms')
                                df_map.set_index('date', inplace=True)

                                # Funkcja do znajdowania indeksu świecy w klines
                                def find_kline_index(x_point):
                                    if hasattr(x_point, 'timestamp'):
                                        target_datetime = x_point
                                    elif isinstance(x_point, (int, float)):
                                        if x_point > 1000000000000:
                                            target_datetime = pd.to_datetime(x_point, unit='ms')
                                        elif x_point > 1000000000:
                                            target_datetime = pd.to_datetime(x_point, unit='s')
                                        else:
                                            idx = int(x_point)
                                            return max(0, min(idx, len(klines) - 1))
                                    else:
                                        try:
                                            target_datetime = pd.to_datetime(x_point)
                                        except:
                                            return 0

                                    # Znajdź najbliższą datę
                                    time_diffs = abs(df_map.index - target_datetime)
                                    closest_idx = time_diffs.argmin()
                                    return closest_idx

                                # Określ nazwę wzorca
                                if len(y_points) >= 5:
                                    point_names = ["X", "A", "B", "C", "D"]
                                    pattern_name = f"{pattern.name}_{patterns_count}/fib_tolerance_{fib_tolerance_strategy_name}:{fib_tolerance}/peak_spacing_{peak_spacing_strategy_name}:{peak_spacing}"
                                elif len(y_points) == 4:
                                    point_names = ["A", "B", "C", "D"]
                                    pattern_name = f"ABCD_{pattern.name}_{patterns_count}/fib_tolerance_{fib_tolerance_strategy_name}:{fib_tolerance}/peak_spacing_{peak_spacing_strategy_name}:{peak_spacing}"
                                elif len(y_points) == 3:
                                    point_names = ["A", "B", "C"]
                                    pattern_name = f"ABC_{pattern.name}_{patterns_count}/fib_tolerance_{fib_tolerance_strategy_name}:{fib_tolerance}/peak_spacing_{peak_spacing_strategy_name}:{peak_spacing}"
                                else:
                                    continue

                                # Nanieś punkty na odpowiednie świece
                                pattern_points = {}  # Zbieranie punktów dla obliczenia proporcji i fibonacci
                                
                                for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                                    if i >= len(point_names):
                                        break

                                    kline_idx = find_kline_index(x_point)
                                    point_name = point_names[i]
                                    
                                    # Zapisz punkt do obliczenia proporcji i fibonacci dla wszystkich kombinacji
                                    pattern_points[point_name] = {
                                        'index': kline_idx,
                                        'price': float(y_point)
                                    }

                                    # Dodaj informacje o punkcie do świecy w nowej strukturze + kompatybilnej ze starą
                                    if 'patterns' not in klines[kline_idx]:
                                        klines[kline_idx]['patterns'] = {}

                                    if f'{patterns_count}' not in klines[kline_idx]['patterns']:
                                        klines[kline_idx]['patterns'][f'{patterns_count}'] = {
                                            f'pattern_id': patterns_count,
                                            f'pattern_point_name': point_name,
                                            f'pattern_point_price': float(y_point),
                                            f'pattern_name': pattern_name,
                                            f'pattern_type': str(pattern.name),
                                            f'pattern_is_bullish': bool(pattern.bullish),
                                            f'pattern_is_formed': bool(pattern.formed),
                                            f'pattern_completion_max_price': float(pattern.completion_max_price),
                                            f'pattern_completion_min_price': float(pattern.completion_min_price),
                                            f'pattern_fib_tolerance_strategy': fib_tolerance_strategy_name,
                                            f'pattern_fib_tolerance': fib_tolerance,
                                            f'pattern_peak_spacing_strategy': peak_spacing_strategy_name,
                                            f'pattern_peak_spacing': peak_spacing,
                                            f'pattern_retraces': pattern.retraces,
                                            'points': pattern_points,  # Dodaj punkty wzorca
                                            'is_bullish': bool(pattern.bullish)  # Dodaj informację o kierunku
                                        }
                                    
                                # Oblicz i dodaj poziomy Fibonacciego używając zrefaktoryzowanych klas
                                fibonacci_levels = {}
                                if len(y_points) >= 2:
                                    first_kline_idx = find_kline_index(x_points[0])

                                    # Znajdź najwyższą i najniższą cenę wzorca
                                    max_price = max(y_points)
                                    min_price = min(y_points)
                                    is_uptrend = bool(pattern.bullish)

                                    # Użyj klasy Fibonacci do obliczenia podstawowych poziomów
                                    self.fibonacci.calculate(
                                        klines, 
                                        start_price=max_price if is_uptrend else min_price,
                                        end_price=min_price if is_uptrend else max_price,
                                        is_uptrend=is_uptrend
                                    )
                                    fib_levels = self.fibonacci.calculated_data

                                    # Użyj klasy FibonacciAllHarmonicPatternPointsLevels do obliczenia wszystkich kombinacji
                                    self.fibonacci_all_levels.calculate(
                                        klines,
                                        pattern_points=pattern_points
                                    )
                                    all_points_fibonacci = self.fibonacci_all_levels.calculated_data
                                    
                                    # Użyj klasy FibonacciTargets do obliczenia targetów
                                    self.fibonacci_targets.calculate(
                                        klines,
                                        pattern_points=pattern_points,
                                        pattern_type=str(pattern.name),
                                        is_bullish=bool(pattern.bullish)
                                    )
                                    all_targets = self.fibonacci_targets.calculated_data
                                    
                                    # Loguj przykłady obliczonych kombinacji i targetów
                                    if all_points_fibonacci:
                                        example_combinations = list(all_points_fibonacci.keys())[:5]  # Pierwsze 5 kombinacji
                                        logger.info(f"Wzorzec {patterns_count}: obliczono poziomy Fibonacci dla kombinacji: {', '.join(example_combinations)} (i {len(all_points_fibonacci) - len(example_combinations)} więcej)")
                                    
                                    if all_targets:
                                        targets_info = [f"{k}({v['type']})" for k, v in all_targets.items()]
                                        logger.info(f"Wzorzec {patterns_count}: obliczono targety: {', '.join(targets_info)}")

                                    # Upewnij się że istnieje struktura patterns
                                    if 'patterns' not in klines[first_kline_idx]:
                                        klines[first_kline_idx]['patterns'] = {}
                                    if f'{patterns_count}' not in klines[first_kline_idx]['patterns']:
                                        klines[first_kline_idx]['patterns'][f'{patterns_count}'] = {}

                                    # Dodaj poziomy Fibonacciego do wzorca w zagnieżdżonej strukturze
                                    fibonacci_levels = {
                                        'retracement': fib_levels.retracement,
                                        'extension': fib_levels.extension, 
                                        'targets': fib_levels.targets,
                                        'all_fibos': all_points_fibonacci,  # Nowe pole z wszystkimi kombinacjami
                                        'all_targets': all_targets  # Nowe pole z PRZ, TP, SL
                                    }

                                # Teraz dodaj fibonacci do każdego punktu tego wzorca
                                for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                                    if i >= len(point_names):
                                        break

                                    kline_idx = find_kline_index(x_point)
                                    point_name = point_names[i]

                                    # Dodaj fibonacci do punktu
                                    if 'patterns' in klines[kline_idx] and f'{patterns_count}' in klines[kline_idx]['patterns']:
                                        klines[kline_idx]['patterns'][f'{patterns_count}']['fibonacci'] = fibonacci_levels

                                total_fib_levels = len(fibonacci_levels.get('retracement', {})) + len(fibonacci_levels.get('extension', {})) + len(fibonacci_levels.get('targets', {}))
                                total_all_fibos = len(fibonacci_levels.get('all_fibos', {}))
                                total_all_targets = len(fibonacci_levels.get('all_targets', {}))
                                logger.info(f"Dodano wzorzec {pattern_name} (ID: {patterns_count}) z pattern_retraces, {total_fib_levels} ogólnymi poziomami Fibonacci, {total_all_fibos} kombinacjami punktów XABCD i {total_all_targets} targetami")
                                logger.info(f"Wygląd Świecy: {str(klines[kline_idx]).replace(',', ',\n')}")

                                patterns_count += 1

                            except Exception as e:
                                logger.warning(f"Błąd podczas przetwarzania wzorca {pattern_idx}: {e}")
                                logger.error(traceback.format_exc())
                                continue

            logger.info(f"Pomyślnie naniesiono {patterns_count} wzorców na świece")
            return patterns_count

        except Exception as e:
            logger.error(f"Błąd podczas wykrywania wzorców harmonicznych: {e}")
            logger.error(traceback.format_exc())
            return 0
    
    def _convert_klines_to_dataframe(self, klines):
        """Konwertuje dane klines na DataFrame wymagany przez pyharmonics"""
        df = pd.DataFrame(klines)
        df['date'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('date', inplace=True)
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        columns_to_keep = ['open', 'high', 'low', 'close', 'volume']
        df = df[columns_to_keep]
        return df
    
    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje wzorce harmoniczne"""
        show_patterns = kwargs.get('show_patterns', True)
        if not show_patterns:
            return
        
        # Implementacja rysowania wzorców harmonicznych
        self.__draw_harmonic_patterns(main_ax, df, klines, kwargs)
    
    def __draw_harmonic_patterns(self, main_ax, df, klines, kwargs):
        """Implementacja rysowania wzorców harmonicznych"""
        # Znajdź wszystkie wzorce w klines i narysuj je
        for kline_idx, kline in enumerate(klines):
            if 'patterns' in kline:
                for pattern_id, pattern_data in kline['patterns'].items():
                    if 'points' in pattern_data:
                        self.__draw_single_pattern(main_ax, pattern_data, kline_idx)
    
    def __draw_single_pattern(self, main_ax, pattern_data, kline_idx):
        """Rysuje pojedynczy wzorzec harmoniczny"""
        points = pattern_data.get('points', {})
        pattern_name = pattern_data.get('name', 'Unknown')
        
        # Rysuj linie łączące punkty XABCD
        point_names = ['X', 'A', 'B', 'C', 'D']
        colors = ['red', 'blue', 'green', 'orange', 'purple']
        
        for i in range(len(point_names) - 1):
            if point_names[i] in points and point_names[i+1] in points:
                point1 = points[point_names[i]]
                point2 = points[point_names[i+1]]
                
                # Rysuj linię między punktami
                main_ax.plot([point1['index'], point2['index']], 
                           [point1['price'], point2['price']], 
                           color=colors[i], linewidth=2, alpha=0.7)
                
                # Dodaj etykietę punktu
                main_ax.annotate(point_names[i], 
                               (point1['index'], point1['price']),
                               xytext=(5, 5), textcoords='offset points',
                               fontsize=8, color=colors[i])