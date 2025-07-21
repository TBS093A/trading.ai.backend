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

from .abstract_technical_analysis_object import TechnicalAnalysisObject, HarmonicPattern
from .tao_fibonacci import Fibonacci
from .tao_fibonacci_all_harmonic_pattern_points_levels import FibonacciAllHarmonicPatternPointsLevels
from .tao_fibonacci_targets import FibonacciTargets


class HarmonicPatternsForming(TechnicalAnalysisObject):
    """Wzorce harmoniczne w trakcie formowania"""
    
    def __init__(self):
        super().__init__("HarmonicPatternsForming")
        # Inicjalizuj obiekty Fibonacci do współpracy
        self.fibonacci = Fibonacci()
        self.fibonacci_all_levels = FibonacciAllHarmonicPatternPointsLevels()
        self.fibonacci_targets = FibonacciTargets()
    
    def calculate(self, klines: List[Dict[str, Union[int, float, str]]], 
                  min_points: int = 5, symbol: str = '', interval: str = '',
                  find_only_xabcd: bool = True, **kwargs) -> None:
        """Oblicza wzorce harmoniczne w trakcie formowania"""
        patterns_count = self.calculate_harmonic_patterns_forming(
            klines, min_points, symbol, interval, find_only_xabcd, **kwargs
        )
        self.calculated_data = patterns_count
    
    def calculate_harmonic_patterns_forming(
        self,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5,
        symbol: str = '',
        interval: str = '',
        find_only_xabcd: bool = True,
        **kwargs
    ) -> int:
        """
        Oblicza wzorce harmoniczne w trakcie formowania się (forming patterns)
        i nanosi punkty bezpośrednio na odpowiednie świece w klines.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            symbol: Symbol krypto
            interval: Interwał czasowy
            find_only_xabcd: Czy szukać tylko wzorców XABCD
            
        Returns:
            Liczba znalezionych wzorców w trakcie formowania
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
            technicals = Technicals(df, symbol, interval)
            
            # Wykonaj wyszukiwanie wzorców w trakcie formowania
            harmonic_search = HarmonicSearch(technicals)
            harmonic_search.forming()
            
            if find_only_xabcd:
                # Pobierz wzorce w trakcie formowania (formed=False)
                patterns = harmonic_search.get_patterns(formed=False, family=harmonic_search.XABCD)
            else:
                # Pobierz wzorce w trakcie formowania (formed=False)
                patterns = harmonic_search.get_patterns(formed=False)
            
            patterns_count = 0
            
            # Przetwórz wzorce i nanieś punkty na klines
            for pattern_type_key in patterns:
                pattern_list = patterns[pattern_type_key]
                logger.info(f"Przetwarzanie {len(pattern_list)} wzorców forming typu {pattern_type_key}")
                
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
                        
                        # Określ nazwę wzorca (dodaj prefix 'forming_')
                        if len(y_points) >= 5:
                            point_names = ["X", "A", "B", "C", "D"]
                            pattern_name = f"forming_{pattern.name}_{patterns_count}"
                        elif len(y_points) == 4:
                            point_names = ["A", "B", "C", "D"]
                            pattern_name = f"forming_ABCD_{pattern.name}_{patterns_count}"
                        elif len(y_points) == 3:
                            point_names = ["A", "B", "C"]
                            pattern_name = f"forming_ABC_{pattern.name}_{patterns_count}"
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
                            
                            # Dodaj informacje o punkcie do świecy w nowej zagnieżdżonej strukturze
                            if 'forming_patterns' not in klines[kline_idx]:
                                klines[kline_idx]['forming_patterns'] = {}
                            
                            klines[kline_idx]['forming_patterns'][f'{patterns_count}'] = {
                                'pattern_id': patterns_count,
                                'pattern_point_name': point_name,
                                'pattern_point_price': float(y_point),
                                'pattern_name': pattern_name,
                                'pattern_type': str(pattern.name),
                                'pattern_is_bullish': bool(pattern.bullish),
                                'points': pattern_points,  # Dodaj punkty wzorca
                                'is_bullish': bool(pattern.bullish)  # Dodaj informację o kierunku
                            }
                            
                            logger.debug(f"Dodano forming punkt {point_name} wzorca {pattern_name} do świecy {kline_idx}: cena={y_point}")
                        
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
                                logger.info(f"Forming wzorzec {patterns_count}: obliczono poziomy Fibonacci dla kombinacji: {', '.join(example_combinations)} (i {len(all_points_fibonacci) - len(example_combinations)} więcej)")
                            
                            if all_targets:
                                targets_info = [f"{k}({v['type']})" for k, v in all_targets.items()]
                                logger.info(f"Forming wzorzec {patterns_count}: obliczono targety: {', '.join(targets_info)}")

                            # Upewnij się że istnieje struktura forming_patterns
                            if 'forming_patterns' not in klines[first_kline_idx]:
                                klines[first_kline_idx]['forming_patterns'] = {}
                            if f'{patterns_count}' not in klines[first_kline_idx]['forming_patterns']:
                                klines[first_kline_idx]['forming_patterns'][f'{patterns_count}'] = {}

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
                            if 'forming_patterns' in klines[kline_idx] and f'{patterns_count}' in klines[kline_idx]['forming_patterns']:
                                klines[kline_idx]['forming_patterns'][f'{patterns_count}']['fibonacci'] = fibonacci_levels

                        total_fib_levels = len(fibonacci_levels.get('retracement', {})) + len(fibonacci_levels.get('extension', {})) + len(fibonacci_levels.get('targets', {}))
                        total_all_fibos = len(fibonacci_levels.get('all_fibos', {}))
                        total_all_targets = len(fibonacci_levels.get('all_targets', {}))
                        logger.info(f"Dodano forming wzorzec {pattern_name} (ID: {patterns_count}) z {total_fib_levels} ogólnymi poziomami Fibonacci, {total_all_fibos} kombinacjami punktów XABCD i {total_all_targets} targetami")
                        
                        patterns_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Błąd podczas przetwarzania forming wzorca {pattern_idx}: {e}")
                        logger.error(traceback.format_exc())
                        continue
            
            logger.info(f"Pomyślnie naniesiono {patterns_count} forming wzorców na świece")
            return patterns_count
            
        except Exception as e:
            logger.error(f"Błąd podczas wykrywania forming wzorców harmonicznych: {e}")
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
        """Rysuje wzorce w trakcie formowania"""
        show_forming_patterns = kwargs.get('show_forming_patterns', True)
        if not show_forming_patterns:
            return
        
        # Implementacja rysowania forming patterns (podobna do HarmonicPatterns ale z innym stylem)
        self.__draw_forming_patterns(main_ax, df, klines, kwargs)
    
    def __draw_forming_patterns(self, main_ax, df, klines, kwargs):
        """Implementacja rysowania wzorców w trakcie formowania"""
        # Znajdź wszystkie forming wzorce w klines i narysuj je
        for kline_idx, kline in enumerate(klines):
            if 'forming_patterns' in kline:
                for pattern_id, pattern_data in kline['forming_patterns'].items():
                    if 'points' in pattern_data:
                        self.__draw_single_forming_pattern(main_ax, pattern_data, kline_idx)
    
    def __draw_single_forming_pattern(self, main_ax, pattern_data, kline_idx):
        """Rysuje pojedynczy wzorzec w trakcie formowania"""
        points = pattern_data.get('points', {})
        pattern_name = pattern_data.get('pattern_name', 'Unknown')
        
        # Rysuj linie łączące punkty XABCD (przerywane linie dla forming patterns)
        point_names = ['X', 'A', 'B', 'C', 'D']
        colors = ['red', 'blue', 'green', 'orange', 'purple']
        
        for i in range(len(point_names) - 1):
            if point_names[i] in points and point_names[i+1] in points:
                point1 = points[point_names[i]]
                point2 = points[point_names[i+1]]
                
                # Rysuj przerywaną linię między punktami dla forming patterns
                main_ax.plot([point1['index'], point2['index']], 
                           [point1['price'], point2['price']], 
                           color=colors[i], linewidth=2, alpha=0.5, linestyle='--')
                
                # Dodaj etykietę punktu
                main_ax.annotate(f"{point_names[i]}*", 
                               (point1['index'], point1['price']),
                               xytext=(5, 5), textcoords='offset points',
                               fontsize=8, color=colors[i])