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

from ..draw_utils import DrawUtils
from .abstract_technical_analysis_object import TechnicalAnalysisObject, HarmonicPattern
from .tao_fibonacci import Fibonacci
from .tao_fibonacci_all_harmonic_pattern_points_levels import FibonacciAllHarmonicPatternPointsLevels
from .tao_fibonacci_targets import FibonacciTargets


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
        # Usuń chart_config z kwargs przed przekazaniem do __calculate_harmonic_patterns
        calculate_kwargs = {k: v for k, v in kwargs.items() if k != 'chart_config'}
        
        patterns_count = self.__calculate_harmonic_patterns(
            klines, min_points, symbol, interval, find_only_xabcd, **calculate_kwargs
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
            logger.warning(f"Za mało świeczek do wyszukania wzorców harmonicznych: {len(klines)} < {min_points}")
            return 0

        try:
            # Inicjalizuj licznik wzorców
            patterns_count = 0
            
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
                                logger.debug(f"Wygląd Świecy: {str(klines[kline_idx]).replace(',', ',\n')}")

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
        
        # Przygotowanie danych wzorców harmonicznych z nowej zagnieżdżonej struktury
        patterns_data = []
        forming_patterns_data = []
        fibonacci_data = []
        retraces_data = []
        
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
                    
                    # Fibonacci levels
                    if 'fibonacci' in pattern_info:
                        fibonacci_data.append({
                            'index': i,
                            'pattern_id': pattern_id,
                            'fibonacci': pattern_info['fibonacci']
                        })
                    
                    # Pattern retraces (nowa struktura zamiast proportions)
                    if 'pattern_retraces' in pattern_info:
                        retraces_data.append({
                            'index': i,
                            'pattern_id': pattern_id,
                            'pattern_retraces': pattern_info['pattern_retraces']
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
        logger.info(f"Znalezione poziomy Fibonacci: {len(fibonacci_data)}")
        logger.info(f"Znalezione retraces: {len(retraces_data)}")
        
        # Wyświetl szczegółowe informacje o wzorcach
        if patterns_data:
            logger.info("Szczegóły znalezionych wzorców:")
            for pattern in patterns_data[:5]:  # Pokaż pierwsze 5
                logger.info(f"Wzorzec {pattern['pattern_id']}: {pattern['point_name']} @ {pattern['price']:.2f} - {pattern['pattern_name']}")
        
        # Wyświetl informacje o retraces
        if retraces_data:
            logger.info("Znalezione retraces wzorców:")
            for retraces_info in retraces_data[:5]:  # Pokaż pierwsze 5
                for retrace_name, retrace_value in retraces_info['pattern_retraces'].items():
                    logger.info(f"Wzorzec {retraces_info['pattern_id']}: {retrace_name} = {retrace_value:.4f}")
                    break  # Tylko jedna na wzorzec dla czytelności
        
        # Rysuj wzorce harmoniczne
        if patterns_data:
            # Przekaż chart_config z kwargs do metody rysowania
            chart_config = kwargs.get('chart_config', {})
            self.__draw_harmonic_patterns(main_ax, df, klines, patterns_data, fibonacci_data, retraces_data, kwargs, chart_config)
    
    def __draw_harmonic_patterns(self, main_ax, df, klines, patterns_data, fibonacci_data, retraces_data, kwargs, chart_config=None):
        """Implementacja rysowania wzorców harmonicznych"""
        try:
            # Pobierz główny subplot z cenami - obsługa różnych typów axes
            if not main_ax or not hasattr(main_ax, 'plot'):
                logger.error("Nie można znaleźć prawidłowego subplot do rysowania wzorców")
                return
            
            logger.debug(f"Typ main_ax: {type(main_ax)}")
            
            # Grupuj punkty według pattern_id
            pattern_groups = {}
            for pattern in patterns_data:
                pattern_id = pattern['pattern_id']
                if pattern_id not in pattern_groups:
                    pattern_groups[pattern_id] = {
                        'points': {},
                        'pattern_retraces': {},
                        'pattern_name': pattern['pattern_name'],
                        'pattern_type': pattern['pattern_type'],
                        'is_bullish': pattern['is_bullish']
                    }
                
                # Dodaj punkt do grupy
                pattern_groups[pattern_id]['points'][pattern['point_name']] = {
                    'index': pattern['index'],
                    'price': pattern['price']
                }
                
                # Dodaj pattern_retraces (z pierwszego punktu który je ma)
                if not pattern_groups[pattern_id]['pattern_retraces']:
                    # Znajdź pattern_retraces w klines
                    kline = klines[pattern['index']]
                    if 'patterns' in kline and pattern_id in kline['patterns']:
                        if 'pattern_retraces' in kline['patterns'][pattern_id]:
                            pattern_groups[pattern_id]['pattern_retraces'] = kline['patterns'][pattern_id]['pattern_retraces']
            
            logger.info(f"Rysowanie linii i trójkątów dla {len(pattern_groups)} wzorców")
            
            # Inicjalizuj listę etykiet do rysowania w paddingu
            pattern_labels_for_padding = []
            
            # Użyj chart_config jeśli dostępny, w przeciwnym razie oblicz lokalnie
            chart_config = kwargs.get('chart_config', {})
            if chart_config:
                dynamic_font_size_labels = chart_config.get('dynamic_font_size_labels', 12)
                dynamic_font_size_axes = chart_config.get('dynamic_font_size_axes', 14)
                dynamic_font_size_fibo_labels = chart_config.get('dynamic_font_size_fibo_labels', 6)
                dynamic_width = chart_config.get('dynamic_width', 20)
                dynamic_height = chart_config.get('dynamic_height', 20)
                logger.info(f"Użyto chart_config - etykiety: {dynamic_font_size_labels}, osi: {dynamic_font_size_axes}, fibonacci: {dynamic_font_size_fibo_labels}")
            else:
                # Oblicz dynamiczną wielkość czcionki na podstawie rozmiaru wykresu i paddingu
                dynamic_width = kwargs.get('dynamic_width', 20)
                dynamic_height = kwargs.get('dynamic_height', 20)
                
                base_font_size_labels = 12 # wielkosc bazowa dla etykiet
                base_font_size_axes = 14  # Oddzielna wielkość bazowa dla wrtosci na osiach 
                base_font_size_fibo_labels = 6  # Wielkość bazowa dla etykiet Fibonacci
                width_factor = max(0.5, min(2.0, dynamic_width / 15))  # Skalowanie na podstawie szerokości
                height_factor = max(0.5, min(2.0, dynamic_height / 20))  # Skalowanie na podstawie wysokości
                padding_factor = max(0.8, min(1.5, dynamic_height / 30))  # Dodatkowy czynnik dla paddingu
                scaling_ratio = (width_factor + height_factor + padding_factor) / 3  # Wspólny współczynnik skalowania
                
                dynamic_font_size_labels = int(base_font_size_labels * scaling_ratio)  # Dla etykiet
                dynamic_font_size_axes = int(base_font_size_axes * scaling_ratio)  # Dla osi
                dynamic_font_size_fibo_labels = int(base_font_size_fibo_labels * scaling_ratio)  # Dla etykiet Fibonacci
                
                logger.info(f"Obliczono lokalnie - etykiety: {dynamic_font_size_labels}, osi: {dynamic_font_size_axes}, fibonacci: {dynamic_font_size_fibo_labels} (współczynnik: {scaling_ratio:.3f}, szerokość: {width_factor:.2f}, wysokość: {height_factor:.2f}, padding: {padding_factor:.2f})")
            
            # Najpierw przygotuj mapę wszystkich punktów na świecach (dla wszystkich wzorców)
            all_points_by_candle = {}
            for pattern_id, pattern_group in pattern_groups.items():
                for point_name, point_data in pattern_group['points'].items():
                    candle_idx = point_data['index']
                    if candle_idx not in all_points_by_candle:
                        all_points_by_candle[candle_idx] = []
                    all_points_by_candle[candle_idx].append((pattern_id, point_name, point_data))
            
            # Loguj informacje o punktach na świecach dla debugowania
            logger.info(f"Mapa punktów na świecach:")
            for candle_idx, points_list in all_points_by_candle.items():
                if len(points_list) > 1:  # Tylko świece z wieloma punktami
                    point_descriptions = [f"({pid}:{name})" for pid, name, _ in points_list]
                    logger.info(f"Świeca {candle_idx}: {len(points_list)} punktów: {', '.join(point_descriptions)}")
            
            # Rysuj linie i trójkąty dla każdego wzorca
            for pattern_id, pattern_group in pattern_groups.items():
                points = pattern_group['points']
                pattern_retraces = pattern_group['pattern_retraces']
                is_bullish = pattern_group['is_bullish']
                pattern_name = pattern_group['pattern_name'].split('_')[0]  # Tylko nazwa bez parametrów
                
                # Kolory dla wzorców
                line_color = 'green' if is_bullish else 'red'
                triangle_color = 'green' if is_bullish else 'red'
                alpha = 0.7
                triangle_alpha = 0.2
                
                logger.debug(f"Rysowanie wzorca {pattern_name} (ID: {pattern_id}) z punktami: {list(points.keys())}")
                
                # Rysuj oznaczenia literowe punktów (X, A, B, C, D) z inteligentnym rozmieszczeniem
                point_sequence = ['X', 'A', 'B', 'C', 'D']
                for point_name in point_sequence:
                    if point_name in points:
                        point = points[point_name]
                        candle_idx = point['index']
                        
                        # Podstawowy y_offset na podstawie typu wzorca i punktu
                        base_y_offset = 15
                        if is_bullish:
                            if point_name in ['X', 'B', 'D']:
                                base_y_offset = base_y_offset * -1
                            elif point_name in ['A', 'C']:
                                base_y_offset = base_y_offset
                        else:
                            if point_name in ['X', 'B', 'D']:
                                base_y_offset = base_y_offset
                            elif point_name in ['A', 'C']:
                                base_y_offset = base_y_offset * -1
                        
                        # Oblicz x_offset i dodatkowy y_offset na podstawie WSZYSTKICH punktów na świecy
                        points_on_candle = all_points_by_candle.get(candle_idx, [])
                        num_points = len(points_on_candle)
                        
                        # Znajdź pozycję tego punktu w liście wszystkich punktów na świecy
                        point_position = next((i for i, (pid, name, _) in enumerate(points_on_candle) 
                                             if pid == pattern_id and name == point_name), 0)
                        
                        # Oblicz offsety na podstawie liczby punktów
                        x_offset = 0
                        additional_y_offset = 0
                        
                        if num_points == 1:
                            # Jeden punkt: bez przesunięć
                            x_offset = 0
                            additional_y_offset = 0
                        elif num_points == 2:
                            # Dwa punkty: pierwszy +7, drugi -7
                            x_offset = 7 if point_position == 0 else -7
                        elif num_points == 3:
                            # Trzy punkty: pierwszy +7, drugi -7, trzeci nowy wiersz
                            if point_position == 0:
                                x_offset = 7
                            elif point_position == 1:
                                x_offset = -7
                            else:  # point_position == 2
                                x_offset = 0
                                additional_y_offset = 10 if base_y_offset > 0 else -10  # Nowy wiersz
                        elif num_points >= 4:
                            # Więcej punktów: rozłóż równomiernie
                            if point_position < 2:
                                x_offset = 7 if point_position == 0 else -7
                            else:
                                x_offset = 7 if point_position % 2 == 0 else -7
                                row = (point_position - 2) // 2 + 1
                                additional_y_offset = row * (10 if base_y_offset > 0 else -10)
                        
                        final_y_offset = base_y_offset + additional_y_offset
                        
                        logger.debug(f"Punkt {point_name} wzorca {pattern_id}: świeca {candle_idx}, pozycja {point_position+1}/{num_points}, x_offset={x_offset}, y_offset={final_y_offset}")
                        
                        # Rysuj literę zamiast kropki z unikalnymi kolorami dla wzorców
                        main_ax.annotate(point_name, (point['index'], point['price']),
                                       xytext=(x_offset, final_y_offset), textcoords='offset points',
                                       ha='center', va='center', fontsize=9, weight='normal',
                                       color=line_color, 
                                       bbox=dict(boxstyle="circle", 
                                               facecolor='black', alpha=0.5, edgecolor=line_color))
                
                # Zbierz dane wzorca dla etykiety w paddingu (przenieś poza pętlę wzorców)
                if 'D' in points:
                    d_point = points['D']
                    direction_text = "BULLISH" if is_bullish else "BEARISH"
                    
                    # Zbierz wszystkie proporcje wzorca
                    retraces_text = ""
                    if pattern_retraces:
                        retraces_lines = []
                        # Kolejność proporcji zgodna z życzeniem użytkownika
                        for retrace_name in ['XABCD', 'XAB', 'ABC', 'BCD']:
                            if retrace_name in pattern_retraces:
                                retraces_lines.append(f"{retrace_name}: {pattern_retraces[retrace_name]:.3f}")
                        
                        # Dodaj inne proporcje które mogą być dostępne
                        for retrace_name, retrace_value in pattern_retraces.items():
                            if retrace_name not in ['XABCD', 'XAB', 'ABC', 'BCD']:
                                retraces_lines.append(f"{retrace_name}: {retrace_value:.3f}")
                        
                        if retraces_lines:
                            retraces_text = "\n" + "\n".join(retraces_lines)
                    
                    pattern_label = f"ID: {pattern_id} | {pattern_name}\n{direction_text}{retraces_text}"
                    
                    # Zapisz dane etykiety do późniejszego rysowania w paddingu
                    pattern_labels_for_padding.append({
                        'pattern_id': pattern_id,
                        'pattern_name': pattern_name,
                        'pattern_label': pattern_label,
                        'd_point': d_point,
                        'line_color': line_color,
                        'is_bullish': is_bullish
                    })
                    
                    # Dodaj etykietę ID pod punktem D z inteligentnym pozycjonowaniem i stylem jak w paddingu
                    id_label = f"ID: {pattern_id}"
                    
                    # Sprawdź ile wzorców kończy się na tej świecy (punkt D)
                    d_candle_idx = d_point['index']
                    d_patterns_on_candle = [
                        p for p in pattern_labels_for_padding 
                        if p['d_point']['index'] == d_candle_idx
                    ]
                    
                    # Znajdź pozycję tego wzorca w liście wzorców kończących się na tej świecy
                    current_pattern_position = len(d_patterns_on_candle)  # Pozycja tego wzorca (1-based)
                    
                    # Oblicz inteligentny margines górny na podstawie ilości wzorców i wierszy
                    total_d_patterns = len(d_patterns_on_candle) + 1  # +1 dla bieżącego wzorca
                    
                    # Podstawowy margines + dodatkowy na podstawie wielkości czcionki i ilości wzorców
                    base_margin = 30 + (dynamic_font_size_labels * 0.5)  # Margines rośnie z czcionką
                    pattern_spacing = dynamic_font_size_labels + 8  # Odstęp między wzorcami
                    
                    # Oblicz całkowity margines dla wszystkich wzorców na tej świecy
                    total_margin_for_candle = base_margin + (total_d_patterns * pattern_spacing)
                    
                    # Oblicz przesunięcie dla tego konkretnego wzorca
                    final_id_y_offset = -base_margin - (current_pattern_position - 1) * pattern_spacing
                    
                    # Dodaj dodatkowy margines jeśli jest więcej niż 3 wzorce na świecy
                    if total_d_patterns > 3:
                        extra_margin = (total_d_patterns - 3) * (dynamic_font_size_labels * 0.3)
                        final_id_y_offset -= extra_margin
                    
                    main_ax.annotate(
                        id_label,
                        (d_point['index'], d_point['price']),
                        xytext=(0, final_id_y_offset),
                        textcoords='offset points',
                        ha='center',
                        va='top',
                        fontsize=dynamic_font_size_labels,  # Używaj dynamicznej wielkości czcionki
                        weight='bold',  # Taki sam styl jak w paddingu
                        color=line_color,  # Kolor wzorca zamiast białego
                        alpha=0.9,  # Taka sama przezroczystość jak w paddingu
                        bbox=dict(
                            boxstyle="round,pad=0.5",  # Taki sam padding jak w paddingu
                            facecolor='black',
                            alpha=0.7,  # Taka sama przezroczystość jak w paddingu
                            edgecolor=line_color  # Ramka w kolorze wzorca
                        ),
                        zorder=12
                    )
                    
                    logger.debug(f"Dodano etykietę ID {pattern_id} pod punktem D na pozycji {current_pattern_position}/{total_d_patterns} z y_offset={final_id_y_offset}, total_margin={total_margin_for_candle:.1f}, font_size={dynamic_font_size_labels}")
                
                # Rysuj główne linie wzorca harmonicznego (X-A-B-C-D) z pattern_retraces
                available_points = [p for p in point_sequence if p in points]
                for i in range(len(available_points) - 1):
                    p1_name = available_points[i]
                    p2_name = available_points[i + 1]
                    
                    p1 = points[p1_name]
                    p2 = points[p2_name]
                    
                    # Rysuj linię
                    main_ax.plot([p1['index'], p2['index']], [p1['price'], p2['price']], 
                               color=line_color, alpha=alpha, linewidth=2, linestyle='-')
                
                # Rysuj dodatkowe linie wzorca harmonicznego
                # Linia X-D (completion line)
                if 'X' in points and 'D' in points:
                    p_x = points['X']
                    p_d = points['D']
                    main_ax.plot([p_x['index'], p_d['index']], [p_x['price'], p_d['price']], 
                               color=line_color, alpha=alpha*0.7, linewidth=1, linestyle='--')
                
                # Linia A-C (impulse line)
                if 'A' in points and 'C' in points:
                    p_a = points['A']
                    p_c = points['C']
                    main_ax.plot([p_a['index'], p_c['index']], [p_a['price'], p_c['price']], 
                               color=line_color, alpha=alpha*0.5, linewidth=1, linestyle=':')
                
                # Linia B-D (retrace line)
                if 'B' in points and 'D' in points:
                    p_b = points['B']
                    p_d = points['D']
                    main_ax.plot([p_b['index'], p_d['index']], [p_b['price'], p_d['price']], 
                               color=line_color, alpha=alpha*0.5, linewidth=1, linestyle=':')
                
                # Rysuj trójkąty z przezroczystym tłem
                # Trójkąt X-A-B
                if 'X' in points and 'A' in points and 'B' in points:
                    x_coords = [points['X']['index'], points['A']['index'], points['B']['index'], points['X']['index']]
                    y_coords = [points['X']['price'], points['A']['price'], points['B']['price'], points['X']['price']]
                    
                    main_ax.fill(x_coords, y_coords, color=triangle_color, alpha=triangle_alpha, 
                               edgecolor=line_color, linewidth=1)
                    
                
                # Trójkąt B-C-D
                if 'B' in points and 'C' in points and 'D' in points:
                    x_coords = [points['B']['index'], points['C']['index'], points['D']['index'], points['B']['index']]
                    y_coords = [points['B']['price'], points['C']['price'], points['D']['price'], points['B']['price']]
                    
                    main_ax.fill(x_coords, y_coords, color=triangle_color, alpha=triangle_alpha, 
                               edgecolor=line_color, linewidth=1)
                    
                
                # Oblicz ile punktów tego wzorca ma przesunięcia
                displaced_points = sum(1 for point_name in points.keys() 
                                     if len(all_points_by_candle.get(points[point_name]['index'], [])) > 1)
                
                logger.info(f"Narysowano wzorzec {pattern_name} (ID: {pattern_id}) z {len(pattern_retraces)} retraces i {displaced_points} przesuniętymi punktami")
            
            # Rysuj poziomy Fibonacciego i/lub targety jeśli włączone
            show_fibonacci = kwargs.get('show_fibonacci', False)
            show_all_fibo_targets = kwargs.get('show_all_fibo_targets', False)
            show_all_fibonacci_levels = kwargs.get('show_all_fibonacci_levels', True)
            show_all_retracement_levels = kwargs.get('show_all_retracement_levels', True)
            show_all_extension_levels = kwargs.get('show_all_extension_levels', True)
            
            if (show_fibonacci or show_all_fibo_targets or show_all_fibonacci_levels) and fibonacci_data:
                DrawUtils.draw_fibonacci_lines_with_labels(
                    main_ax, fibonacci_data, pattern_groups, klines, 
                    dynamic_font_size_fibo_labels, df, show_all_fibo_targets, show_fibonacci, show_all_fibonacci_levels,
                    show_all_retracement_levels, show_all_extension_levels, chart_config
                )
            
            # Rysuj etykiety wzorców in paddingu po zakończeniu wszystkich wzorców
            if pattern_labels_for_padding:
                DrawUtils.draw_pattern_labels_in_padding(
                    main_ax, pattern_labels_for_padding, df, 
                    dynamic_width, dynamic_height, dynamic_font_size_labels
                )
            
            # Zastosuj skalowaną czcionkę do osi X i Y
            DrawUtils.apply_scaled_font_to_axes(main_ax, [main_ax], dynamic_font_size_axes)
            
        except Exception as e:
            logger.error(f"Błąd podczas rysowania wzorców harmonicznych: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
