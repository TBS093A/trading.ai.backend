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

@dataclass
class FibonacciLevels:
    retracement: Dict[str, float]  # Poziomy retracementu (0.236, 0.382, 0.5, 0.618, 0.786)
    extension: Dict[str, float]    # Poziomy extension (1.272, 1.618, 2.0, 2.618)
    targets: Dict[str, float]      # Poziomy targetów (T1, T2, T3, T4)

@dataclass
class HarmonicPattern:
    name: str                      # Nazwa formacji (np. Gartley, Butterfly, Bat)
    xabcd_points: Dict[str, Dict[str, Union[float, int]]] # Punkty XABCD z cenami i czasami
    fibonacci_levels: FibonacciLevels
    direction: str                 # "bullish" lub "bearish"
    completion_zone: Tuple[float, float]  # Zakres cenowy dla zakończenia formacji
    formed: bool                   # Czy wzorzec jest w pełni uformowany
    tolerance: float               # Tolerancja dla wzorca (domyślnie 0.1 = 10%)

class TechnicalAnalysis:
    # Stałe dla wzorców harmonicznych zgodne z pyharmonics
    PATTERN_RATIOS = {
        "Gartley": {
            "AB": (0.618, 0.618),  # AB powinno być 61.8% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (1.272, 1.618),  # CD powinno być 127.2% - 161.8% BC
            "AD": (0.786, 0.786)   # AD powinno być 78.6% XA
        },
        "Butterfly": {
            "AB": (0.786, 0.786),  # AB powinno być 78.6% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (1.618, 2.618),  # CD powinno być 161.8% - 261.8% BC
            "AD": (1.270, 1.612)   # AD powinno być 127% - 161.2% XA
        },
        "Crab": {
            "AB": (0.382, 0.618),  # AB powinno być 38.2% lub 61.8% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (2.240, 3.618),  # CD powinno być 224% - 361.8% BC
            "AD": (1.618, 1.618)   # AD powinno być 161.8% XA
        },
        "Bat": {
            "AB": (0.382, 0.5),    # AB powinno być 38.2% lub 50% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (1.618, 2.618),  # CD powinno być 161.8% - 261.8% BC
            "AD": (0.886, 0.886)   # AD powinno być 88.6% XA
        },
        "Cypher": {
            "AB": (0.382, 0.618),
            "BC": (1.272, 1.414),
            "CD": (0.786, 0.786),
            "AD": (0.786, 0.786)
        },
        "Shark": {
            "AB": (1.13, 1.618),
            "BC": (1.618, 2.24),
            "AD": (0.886, 1.13)
        }
    }

    @classmethod
    def _convert_klines_to_dataframe(cls, klines: List[Dict[str, Union[int, float, str]]]) -> pd.DataFrame:
        """
        Konwertuje dane klines na DataFrame wymagany przez pyharmonics.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            
        Returns:
            DataFrame w formacie wymaganym przez pyharmonics
        """
        df = pd.DataFrame(klines)
        
        # Konwersja timestamp na datetime
        df['date'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('date', inplace=True)
        
        # Konwersja kolumn na float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = df[col].astype(float)
        
        # Usuń niepotrzebne kolumny
        columns_to_keep = ['open', 'high', 'low', 'close', 'volume']
        df = df[columns_to_keep]
        
        return df

    @classmethod
    def calculate_harmonic_patterns(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5,
        symbol: str = '',
        interval: str = '',
        find_only_xabcd: bool = True,
        fib_tolerance_strategy: dict[str, float] = {
            'hard_restricted': 0.03,
            #'restricted': 0.05,
            #'normal': 0.1,
            #'loose': 0.15
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
            #'middle-huge-large': 9,
            #'large': 8,
            #'middle-large-medium': 7,
            #'medium': 6,
            #'middle-medium-small': 5,
            #'small': 4,
            #'middle-small-tiny': 3,
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
            fib_tolerance: Tolerancja dla poziomów Fibonacciego w wyznaczaniu wzorcow harmonicznych
            peak_spacing_strategy: Strategia spacji między punktami wzorca (ilością świec między punktami)
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
            df = cls._convert_klines_to_dataframe(klines)
            
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
                                pattern_points = {}  # Zbieranie punktów dla obliczenia proporcji
                                
                                for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                                    if i >= len(point_names):
                                        break

                                    kline_idx = find_kline_index(x_point)
                                    point_name = point_names[i]
                                    
                                    # Zapisz punkt do obliczenia proporcji
                                    pattern_points[point_name] = float(y_point)

                                    # Dodaj informacje o punkcie do świecy w nowej strukturze + kompatybilnej ze starą
                                    klines[kline_idx]['patterns'] = {
                                        f'{patterns_count}': {
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
                                        }
                                    }

                                # Oblicz proporcje między punktami
                                proportions = {}
                                if len(pattern_points) >= 4:  # Przynajmniej ABCD
                                    
                                    # Oblicz proporcje dla wzorców XABCD
                                    if 'X' in pattern_points and 'A' in pattern_points and 'B' in pattern_points:
                                        xa_distance = abs(pattern_points['A'] - pattern_points['X'])
                                        ab_distance = abs(pattern_points['B'] - pattern_points['A'])
                                        if xa_distance != 0:
                                            proportions['AB_XA_ratio'] = ab_distance / xa_distance
                                    
                                    if 'A' in pattern_points and 'B' in pattern_points and 'C' in pattern_points:
                                        ab_distance = abs(pattern_points['B'] - pattern_points['A'])
                                        bc_distance = abs(pattern_points['C'] - pattern_points['B'])
                                        if ab_distance != 0:
                                            proportions['BC_AB_ratio'] = bc_distance / ab_distance
                                    
                                    if 'B' in pattern_points and 'C' in pattern_points and 'D' in pattern_points:
                                        bc_distance = abs(pattern_points['C'] - pattern_points['B'])
                                        cd_distance = abs(pattern_points['D'] - pattern_points['C'])
                                        if bc_distance != 0:
                                            proportions['CD_BC_ratio'] = cd_distance / bc_distance
                                    
                                    if 'X' in pattern_points and 'A' in pattern_points and 'D' in pattern_points:
                                        xa_distance = abs(pattern_points['X'] - pattern_points['A'])
                                        xd_distance = abs(pattern_points['X'] - pattern_points['D'])
                                        if xa_distance != 0:
                                            proportions['XD_XA_ratio'] = xd_distance / xa_distance
                                    
                                    # Oblicz proporcje dla wzorców ABCD (bez X)
                                    elif len(pattern_points) == 4 and 'A' in pattern_points and 'B' in pattern_points and 'C' in pattern_points and 'D' in pattern_points:
                                        ab_distance = abs(pattern_points['B'] - pattern_points['A'])
                                        bc_distance = abs(pattern_points['C'] - pattern_points['B'])
                                        cd_distance = abs(pattern_points['D'] - pattern_points['C'])
                                        ad_distance = abs(pattern_points['D'] - pattern_points['A'])
                                        
                                        if ab_distance != 0:
                                            proportions['BC_AB_ratio'] = bc_distance / ab_distance
                                        if bc_distance != 0:
                                            proportions['CD_BC_ratio'] = cd_distance / bc_distance
                                        if ab_distance != 0:
                                            proportions['AD_AB_ratio'] = ad_distance / ab_distance
                                    
                                    # Dodaj proporcje do wzorca w zagnieżdżonej strukturze
                                    if proportions:
                                        first_kline_idx = find_kline_index(x_points[0])
                                        
                                        # Upewnij się że istnieje struktura patterns
                                        if 'patterns' not in klines[first_kline_idx]:
                                            klines[first_kline_idx]['patterns'] = {}
                                        if f'{patterns_count}' not in klines[first_kline_idx]['patterns']:
                                            klines[first_kline_idx]['patterns'][f'{patterns_count}'] = {}
                                        
                                        for prop_name, prop_value in proportions.items():
                                            logger.info(f"Dodano proporcję {prop_name} = {prop_value:.4f} do wzorca {patterns_count}")
                                
                                # Alternatywne obliczanie proporcji na podstawie już dodanych punktów w klines
                                # Wykorzystuje pattern_id i pattern_point_name do znajdowania punktów tego samego wzorca
                                if not proportions and len(pattern_points) >= 3:  # Jeśli nie udało się wcześniej obliczyć
                                    logger.info(f"Obliczanie proporcji na podstawie dodanych punktów w klines dla wzorca {patterns_count}")
                                    
                                    # Znajdź wszystkie punkty tego wzorca w klines
                                    pattern_kline_points = {}
                                    for kline_idx, kline in enumerate(klines):
                                        if 'patterns' in kline:
                                            for pattern_id, pattern_info in kline['patterns'].items():
                                                if pattern_id == f'{patterns_count}' and 'pattern_point_name' in pattern_info and 'pattern_point_price' in pattern_info:
                                                    point_name = pattern_info['pattern_point_name']
                                                    point_price = pattern_info['pattern_point_price']
                                                    pattern_kline_points[point_name] = point_price
                                    
                                    logger.debug(f"Znalezione punkty w klines dla wzorca {patterns_count}: {pattern_kline_points}")
                                    
                                    # Oblicz proporcje na podstawie znalezionych punktów
                                    if len(pattern_kline_points) >= 4:
                                        # Proporcje XABCD
                                        if 'X' in pattern_kline_points and 'A' in pattern_kline_points and 'B' in pattern_kline_points:
                                            xa_distance = abs(pattern_kline_points['A'] - pattern_kline_points['X'])
                                            ab_distance = abs(pattern_kline_points['B'] - pattern_kline_points['A'])
                                            if xa_distance != 0:
                                                proportions['AB_XA_ratio'] = ab_distance / xa_distance
                                        
                                        if 'A' in pattern_kline_points and 'B' in pattern_kline_points and 'C' in pattern_kline_points:
                                            ab_distance = abs(pattern_kline_points['B'] - pattern_kline_points['A'])
                                            bc_distance = abs(pattern_kline_points['C'] - pattern_kline_points['B'])
                                            if ab_distance != 0:
                                                proportions['BC_AB_ratio'] = bc_distance / ab_distance
                                        
                                        if 'B' in pattern_kline_points and 'C' in pattern_kline_points and 'D' in pattern_kline_points:
                                            bc_distance = abs(pattern_kline_points['C'] - pattern_kline_points['B'])
                                            cd_distance = abs(pattern_kline_points['D'] - pattern_kline_points['C'])
                                            if bc_distance != 0:
                                                proportions['CD_BC_ratio'] = cd_distance / bc_distance
                                        
                                        if 'X' in pattern_kline_points and 'A' in pattern_kline_points and 'D' in pattern_kline_points:
                                            xa_distance = abs(pattern_kline_points['X'] - pattern_kline_points['A'])
                                            xd_distance = abs(pattern_kline_points['X'] - pattern_kline_points['D'])
                                            if xa_distance != 0:
                                                proportions['XD_XA_ratio'] = xd_distance / xa_distance
                                        
                                        logger.info(f"Obliczono {len(proportions)} proporcji na podstawie klines dla wzorca {patterns_count}")
                                        for prop_name, prop_value in proportions.items():
                                            logger.info(f"Proporcja z klines: {prop_name} = {prop_value:.4f}")
                                elif len(pattern_points) >= 3:
                                    logger.debug(f"Wzorzec {patterns_count} ma tylko {len(pattern_points)} punktów - za mało dla proporcji")

                                # Oblicz i dodaj poziomy Fibonacciego do pierwszej świecy wzorca
                                fibonacci_levels = {}
                                if len(y_points) >= 2:
                                    first_kline_idx = find_kline_index(x_points[0])

                                    # Znajdź najwyższą i najniższą cenę wzorca
                                    max_price = max(y_points)
                                    min_price = min(y_points)
                                    is_uptrend = bool(pattern.bullish)

                                    # Oblicz poziomy Fibonacciego
                                    fib_levels = cls.calculate_fibonacci_levels(
                                        start_price=max_price if is_uptrend else min_price,
                                        end_price=min_price if is_uptrend else max_price,
                                        is_uptrend=is_uptrend
                                    )

                                    # Upewnij się że istnieje struktura patterns
                                    if 'patterns' not in klines[first_kline_idx]:
                                        klines[first_kline_idx]['patterns'] = {}
                                    if f'{patterns_count}' not in klines[first_kline_idx]['patterns']:
                                        klines[first_kline_idx]['patterns'][f'{patterns_count}'] = {}

                                    # Dodaj poziomy Fibonacciego do wzorca w zagnieżdżonej strukturze
                                    fibonacci_levels = {
                                        'retracement': fib_levels.retracement,
                                        'extension': fib_levels.extension, 
                                        'targets': fib_levels.targets
                                    }

                                # Teraz dodaj proporcje i fibonacci do każdego punktu tego wzorca
                                for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                                    if i >= len(point_names):
                                        break
                                        
                                    kline_idx = find_kline_index(x_point)
                                    
                                    # Dodaj proporcje do tego punktu wzorca
                                    if proportions:
                                        klines[kline_idx]['patterns'][f'{patterns_count}']['proportions'] = proportions
                                    
                                    # Dodaj fibonacci do tego punktu wzorca
                                    if fibonacci_levels:
                                        klines[kline_idx]['patterns'][f'{patterns_count}']['fibonacci'] = fibonacci_levels

                                    logger.info(f"Dodano punkt {point_name} wzorca {pattern_name} do świecy {kline_idx}: {str(klines[kline_idx]).replace(',', ',\n')}")
                                
                                
                                logger.info(f"Dodano wzorzec {pattern_name} (ID: {patterns_count}) z {len(proportions)} proporcjami i {len(fibonacci_levels)} poziomami Fibonacci")

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

    @classmethod
    def calculate_harmonic_patterns_forming(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5,
        symbol: str = '',
        interval: str = '',
        find_only_xabcd: bool = True
    ) -> int:
        """
        Oblicza wzorce harmoniczne w trakcie formowania się (forming patterns)
        i nanosi punkty bezpośrednio na odpowiednie świece w klines.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            
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
            df = cls._convert_klines_to_dataframe(klines)
            
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
                        for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                            if i >= len(point_names):
                                break
                                
                            kline_idx = find_kline_index(x_point)
                            point_name = point_names[i]
                            
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
                            }
                            
                            logger.debug(f"Dodano forming punkt {point_name} wzorca {pattern_name} do świecy {kline_idx}: cena={y_point}")
                        
                        patterns_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Błąd podczas przetwarzania forming wzorca {pattern_idx}: {e}")
                        continue
            
            logger.info(f"Pomyślnie naniesiono {patterns_count} forming wzorców na świece")
            return patterns_count
            
        except Exception as e:
            logger.error(f"Błąd podczas wykrywania forming wzorców harmonicznych: {e}")
            return 0

    @classmethod
    def calculate_fibonacci_levels(
        cls,
        start_price: float,
        end_price: float,
        is_uptrend: bool
    ) -> FibonacciLevels:
        """
        Oblicza poziomy Fibonacciego dla danego ruchu cenowego.
        
        Args:
            start_price: Cena początkowa
            end_price: Cena końcowa
            is_uptrend: Czy trend jest wzrostowy
            
        Returns:
            Obiekt FibonacciLevels zawierający poziomy retracementu, extension i targety
        """
        price_range = abs(end_price - start_price)
        
        # Poziomy retracementu
        retracement = {
            "0.236": end_price + (price_range * 0.236 if is_uptrend else -price_range * 0.236),
            "0.382": end_price + (price_range * 0.382 if is_uptrend else -price_range * 0.382),
            "0.5": end_price + (price_range * 0.5 if is_uptrend else -price_range * 0.5),
            "0.618": end_price + (price_range * 0.618 if is_uptrend else -price_range * 0.618),
            "0.786": end_price + (price_range * 0.786 if is_uptrend else -price_range * 0.786)
        }
        
        # Poziomy extension
        extension = {
            "1.272": end_price + (price_range * 1.272 if is_uptrend else -price_range * 1.272),
            "1.618": end_price + (price_range * 1.618 if is_uptrend else -price_range * 1.618),
            "2.0": end_price + (price_range * 2.0 if is_uptrend else -price_range * 2.0),
            "2.618": end_price + (price_range * 2.618 if is_uptrend else -price_range * 2.618)
        }
        
        # Targety cenowe
        targets = {
            "T1": extension["1.272"],
            "T2": extension["1.618"],
            "T3": extension["2.0"],
            "T4": extension["2.618"]
        }
        
        return FibonacciLevels(retracement, extension, targets)

    @classmethod
    def calculate_rsi(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        period: int = 14
    ) -> List[float]:
        """
        Oblicza wskaźnik RSI (Relative Strength Index).
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            period: Okres obliczania RSI (domyślnie 14)
            
        Returns:
            Lista wartości RSI
        """
        if len(klines) < period + 1:
            return []

        closes = np.array([float(k['close']) for k in klines])
        deltas = np.diff(closes)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        rsi_values = []
        
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            
            if avg_loss == 0:
                rsi = 100
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                
            rsi_values.append(rsi)
            
        return rsi_values

    @classmethod
    def calculate_macd(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, List[float]]:
        """
        Oblicza wskaźnik MACD (Moving Average Convergence Divergence).
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            fast_period: Okres szybkiej średniej (domyślnie 12)
            slow_period: Okres wolnej średniej (domyślnie 26)
            signal_period: Okres linii sygnałowej (domyślnie 9)
            
        Returns:
            Słownik zawierający:
            - macd_line: Wartości linii MACD
            - signal_line: Wartości linii sygnałowej
            - histogram: Wartości histogramu
        """
        if len(klines) < slow_period + signal_period:
            return {"macd_line": [], "signal_line": [], "histogram": []}

        closes = np.array([float(k['close']) for k in klines])
        
        # Obliczanie EMA
        ema_fast = cls._calculate_ema(closes, fast_period)
        ema_slow = cls._calculate_ema(closes, slow_period)
        
        # Linia MACD
        macd_line = ema_fast - ema_slow
        
        # Linia sygnałowa
        signal_line = cls._calculate_ema(macd_line, signal_period)
        
        # Histogram
        histogram = macd_line - signal_line
        
        return {
            "macd_line": macd_line.tolist(),
            "signal_line": signal_line.tolist(),
            "histogram": histogram.tolist()
        }

    @classmethod
    def calculate_obv(
        cls,
        klines: List[Dict[str, Union[int, float, str]]]
    ) -> List[float]:
        """
        Oblicza wskaźnik OBV (On-Balance Volume).
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            
        Returns:
            Lista wartości OBV
        """
        if len(klines) < 2:
            return []

        obv_values = [float(klines[0]['volume'])]
        
        for i in range(1, len(klines)):
            current_close = float(klines[i]['close'])
            previous_close = float(klines[i-1]['close'])
            current_volume = float(klines[i]['volume'])
            
            if current_close > previous_close:
                obv_values.append(obv_values[-1] + current_volume)
            elif current_close < previous_close:
                obv_values.append(obv_values[-1] - current_volume)
            else:
                obv_values.append(obv_values[-1])
                
        return obv_values

    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> np.ndarray:
        """
        Oblicza wykładniczą średnią ruchomą (EMA).
        
        Args:
            data: Tablica danych
            period: Okres EMA
            
        Returns:
            Tablica wartości EMA
        """
        alpha = 2 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
            
        return ema

    @classmethod
    def calculate_harmonic_patterns_with_fibonacci(
        cls,
        klines: List[Dict[str, Union[int, float, str]]]
    ) -> int:
        """
        Oblicza formacje harmoniczne XABCD wraz z poziomami Fibonacciego.
        Wzorce i poziomy są dodawane bezpośrednio do klines.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            
        Returns:
            Liczba znalezionych wzorców z poziomami Fibonacciego
        """
        # Znajdź wzorce harmoniczne (dodaje punkty i poziomy Fibonacci do klines)
        patterns_count = cls.calculate_harmonic_patterns(klines)
        
        logger.info(f"Obliczono {patterns_count} wzorców harmonicznych z poziomami Fibonacciego")
        return patterns_count

    @classmethod
    def create_candlestick_chart(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        save_path: Optional[str] = None,
        title: str = "Wykres świecowy",
        show_fibonacci: bool = True,
        show_patterns: bool = True,
        show_rsi: bool = True,
        show_macd: bool = True,
        show_obv: bool = True,
    ) -> str:
        """
        Tworzy wykres świecowy z dodatkowymi wskaźnikami technicznymi oraz wzorcami harmonicznymi
        na podstawie danych zawartych w klines.
        
        Args:
            klines: Lista świeczek zawierająca dane OHLCV, wskaźniki techniczne oraz punkty wzorców harmonicznych
            save_path: Opcjonalna ścieżka do zapisu wykresu
            title: Tytuł wykresu
            
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
            
        # Filtruj kolumny przed rysowaniem - usuń kolumny z czasami i inne niepotrzebne
        columns_to_keep = ['open', 'high', 'low', 'close', 'volume']
        
        logger.debug(f"Wszystkie kolumny w DataFrame: {list(df.columns)}")
        
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
        
        logger.debug(f"Kolumny po filtrowaniu: {list(df.columns)}")
        
        # Sprawdź i napraw typy danych - upewnij się że wszystkie kolumny są numeryczne
        for col in df.columns:
            if col in ['open', 'high', 'low', 'close']:  # Kolumny podstawowe - wymagane
                df = df.dropna(subset=[col])
            elif col == 'volume':  # Volume może być NaN
                df[col] = df[col].fillna(0)
            elif col.startswith(('pattern_', 'forming_pattern_', 'fib_')):  # Kolumny wzorców - nie usuwaj wierszy
                df[col] = df[col].fillna(0)  # Wypełnij zerami dla brakujących wartości
            else:  # Wskaźniki techniczne
                pass  # Zostaw NaN dla wskaźników - będą obsłużone w add_plots
        
        # Sprawdź czy DataFrame nie jest pusty po filtrowaniu
        if df.empty:
            logger.warning("DataFrame jest pusty po filtrowaniu - używam oryginalnych danych")
            df = pd.DataFrame(klines)
            df['date'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('date', inplace=True)
            df = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
        
        # Sprawdź typy danych przed rysowaniem
        logger.debug(f"Typy danych w DataFrame: {df.dtypes.to_dict()}")
        logger.debug(f"Rozmiar DataFrame: {df.shape}")
        
        # Sprawdź czy są jakieś problematyczne wartości
        for col in df.columns:
            if df[col].dtype == 'object':
                logger.warning(f"Kolumna {col} ma typ object: {df[col].dtype}")
            if df[col].isna().any():
                logger.warning(f"Kolumna {col} ma wartości NaN: {df[col].isna().sum()}")
        
        # Przygotowanie stylu wykresu
        mc = mpf.make_marketcolors(
            up='green',
            down='red',
            edge='inherit',
            wick='inherit',
            volume='in'
        )
        
        s = mpf.make_mpf_style(
            marketcolors=mc,
            gridstyle='dotted',
            y_on_right=False
        )
        
        # Przygotowanie dodatkowych wskaźników
        add_plots = []
        panel = 1  # Licznik paneli dla wskaźników
        
        # Dynamiczne wykrywanie i dodawanie wskaźników
        if show_rsi and 'rsi' in df.columns:
            add_plots.append(
                mpf.make_addplot(df['rsi'], panel=panel, color='blue', title='RSI')
            )
            panel += 1
            
        if show_macd and all(col in df.columns for col in ['macd', 'signal']):
            add_plots.append(
                mpf.make_addplot(df['macd'], panel=panel, color='blue', title='MACD')
            )
            add_plots.append(
                mpf.make_addplot(df['signal'], panel=panel, color='red')
            )
            if 'histogram' in df.columns:
                add_plots.append(
                    mpf.make_addplot(df['histogram'], panel=panel, type='bar', color='gray', alpha=0.5)
                )
            panel += 1
            
        if show_obv and 'obv' in df.columns:
            add_plots.append(
                mpf.make_addplot(df['obv'], panel=panel, color='purple', title='OBV')
            )
            panel += 1
            
        # Przygotowanie danych wzorców harmonicznych z nowej zagnieżdżonej struktury
        # Przeszukaj klines aby znaleźć wzorce w nowej strukturze
        patterns_data = []
        forming_patterns_data = []
        fibonacci_data = []
        proportions_data = []
        
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
                    
                    # Proportions
                    if 'proportions' in pattern_info:
                        proportions_data.append({
                            'index': i,
                            'pattern_id': pattern_id,
                            'proportions': pattern_info['proportions']
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
        logger.info(f"Znalezione proporcje: {len(proportions_data)}")
        
        # Wyświetl szczegółowe informacje o wzorcach
        if patterns_data:
            logger.info("Szczegóły znalezionych wzorców:")
            for pattern in patterns_data[:5]:  # Pokaż pierwsze 5
                logger.info(f"Wzorzec {pattern['pattern_id']}: {pattern['point_name']} @ {pattern['price']:.2f} - {pattern['pattern_name']}")
        
        # Wyświetl informacje o proporcjach
        if proportions_data:
            logger.info("Znalezione proporcje wzorców:")
            for prop_data in proportions_data[:5]:  # Pokaż pierwsze 5
                for prop_name, prop_value in prop_data['proportions'].items():
                    logger.info(f"Wzorzec {prop_data['pattern_id']}: {prop_name} = {prop_value:.4f}")
                    break  # Tylko jedna na wzorzec dla czytelności
        
        # Wzorce będą teraz rysowane jako litery bezpośrednio na wykresie
        # zamiast scatter plots - sekcja usunięta
        
        # Dodaj legendę/adnotacje dla wzorców
        if show_patterns and patterns_data:
            # Znajdź wzorce z ich nazwami do wyświetlenia w tytule wykresu
            pattern_names = set()
            for pattern in patterns_data:
                if pattern['pattern_name']:
                    pattern_names.add(pattern['pattern_name'].split('_')[0])  # Tylko nazwa wzorca bez parametrów
                            
            if pattern_names:
                title += f" | Wzorce: {', '.join(sorted(pattern_names))}"
        
        # Dodaj poziomy Fibonacciego jako linie poziome
        if show_fibonacci and fibonacci_data:
            # Kolory dla różnych typów poziomów Fibonacci
            fib_type_colors = {
                'retracement': ['#FFD700', '#FF8C00', '#FF6347', '#FF1493', '#9932CC'],  # Retracement - złoto do fioletu
                'extension': ['#00CED1', '#00FF7F', '#32CD32', '#228B22'],              # Extension - turkus do zieleni
                'targets': ['#FF4500', '#FF6347', '#FF7F50', '#FFA07A']                # Target - czerwono-pomarańczowe
            }
            
            # Przetwórz wszystkie poziomy Fibonacciego
            for fib_data in fibonacci_data:
                fibonacci = fib_data['fibonacci']
                
                # Przetwórz każdy typ poziomów Fibonacciego
                for fib_type, levels in fibonacci.items():
                    colors = fib_type_colors.get(fib_type, ['gray'])
                    linestyle = '--' if fib_type == 'retracement' else (':' if fib_type == 'extension' else '-')
                    alpha = 0.6 if fib_type == 'retracement' else (0.5 if fib_type == 'extension' else 0.8)
                    
                    for i, (level_name, level_price) in enumerate(levels.items()):
                        if level_price != 0 and not pd.isna(level_price):
                            color = colors[i % len(colors)]
                            # Wypełnij całą serię tym samym poziomem
                            fib_series = pd.Series(level_price, index=df.index)
                            add_plots.append(
                                mpf.make_addplot(
                                    fib_series,
                                    type='line',
                                    color=color,
                                    alpha=alpha,
                                    linestyle=linestyle,
                                    width=1.5 if fib_type == 'targets' else 1
                                )
                            )
                            logger.debug(f"Dodano poziom {fib_type} Fibonacci {level_name} = {level_price:.2f} w kolorze {color}")
        
        # Tworzenie wykresu
        fig, axes = mpf.plot(
            df,
            type='candle',
            style=s,
            title=title,
            volume='volume' in df.columns,
            addplot=add_plots,
            returnfig=True,
            figsize=(15, 10)
        )
        
        # Dodaj linie łączące punkty wzorców harmonicznych i trójkąty
        if show_patterns and patterns_data:
            # Pobierz główny subplot z cenami - obsługa różnych typów axes
            main_ax = None
            try:
                if hasattr(axes, '__len__') and len(axes) > 0:
                    # axes jest listą lub tablicą
                    main_ax = axes[0]  # Pierwszy subplot to zawsze ceny
                elif hasattr(axes, 'plot'):
                    # axes jest pojedynczym subplot
                    main_ax = axes
                else:
                    # Próba znalezienia prawidłowego subplot
                    for ax in axes:
                        if hasattr(ax, 'plot'):
                            main_ax = ax
                            break
                
                logger.debug(f"Typ axes: {type(axes)}, Użyto main_ax: {type(main_ax)}")
                
                if main_ax and hasattr(main_ax, 'plot'):
                    # Grupuj punkty według pattern_id
                    pattern_groups = {}
                    for pattern in patterns_data:
                        pattern_id = pattern['pattern_id']
                        if pattern_id not in pattern_groups:
                            pattern_groups[pattern_id] = {
                                'points': {},
                                'proportions': {},
                                'pattern_name': pattern['pattern_name'],
                                'pattern_type': pattern['pattern_type'],
                                'is_bullish': pattern['is_bullish']
                            }
                        
                        # Dodaj punkt do grupy
                        pattern_groups[pattern_id]['points'][pattern['point_name']] = {
                            'index': pattern['index'],
                            'price': pattern['price']
                        }
                        
                        # Dodaj proporcje (z pierwszego punktu który je ma)
                        if not pattern_groups[pattern_id]['proportions']:
                            # Znajdź proporcje w klines
                            kline = klines[pattern['index']]
                            if 'patterns' in kline and pattern_id in kline['patterns']:
                                if 'proportions' in kline['patterns'][pattern_id]:
                                    pattern_groups[pattern_id]['proportions'] = kline['patterns'][pattern_id]['proportions']
                    
                    logger.info(f"Rysowanie linii i trójkątów dla {len(pattern_groups)} wzorców")
                    
                    # Rysuj linie i trójkąty dla każdego wzorca
                    for pattern_id, pattern_group in pattern_groups.items():
                        points = pattern_group['points']
                        proportions = pattern_group['proportions']
                        is_bullish = pattern_group['is_bullish']
                        pattern_name = pattern_group['pattern_name'].split('_')[0]  # Tylko nazwa bez parametrów
                        
                        # Kolory dla wzorców
                        line_color = 'green' if is_bullish else 'red'
                        triangle_color = 'green' if is_bullish else 'red'
                        alpha = 0.7
                        triangle_alpha = 0.2
                        
                        logger.debug(f"Rysowanie wzorca {pattern_name} (ID: {pattern_id}) z punktami: {list(points.keys())}")
                        
                        # Rysuj oznaczenia literowe punktów (X, A, B, C, D)
                        point_sequence = ['X', 'A', 'B', 'C', 'D']
                        for point_name in point_sequence:
                            if point_name in points:
                                point = points[point_name]
                                # Rysuj literę zamiast kropki
                                main_ax.annotate(point_name, (point['index'], point['price']), 
                                               ha='center', va='center', fontsize=12, weight='bold',
                                               color='white', 
                                               bbox=dict(boxstyle="circle,pad=0.3", 
                                                       facecolor=line_color, alpha=0.8, edgecolor='black'))
                        
                        # Dodaj dużą etykietę wzorca przy punkcie D
                        if 'D' in points:
                            d_point = points['D']
                            direction_text = "BULLISH" if is_bullish else "BEARISH"
                            pattern_label = f"{pattern_name}\n{direction_text}"
                            
                            # Pozycjonowanie etykiety - pod punktem D dla bullish, nad dla bearish
                            if is_bullish:
                                y_offset = -20  # Pod punktem
                                va = 'top'
                            else:
                                y_offset = 20   # Nad punktem
                                va = 'bottom'
                            
                            main_ax.annotate(pattern_label, (d_point['index'], d_point['price']), 
                                           xytext=(0, y_offset), textcoords='offset points',
                                           ha='center', va=va, fontsize=14, weight='bold',
                                           color=line_color, alpha=0.9,
                                           bbox=dict(boxstyle="round,pad=0.5", 
                                                   facecolor='white', alpha=0.8, edgecolor=line_color))
                        
                        # Rysuj linie łączące punkty zgodnie z kolejnością XABCD
                        available_points = [p for p in point_sequence if p in points]
                        
                        # Rysuj główne linie wzorca harmonicznego (X-A-B-C-D)
                        for i in range(len(available_points) - 1):
                            p1_name = available_points[i]
                            p2_name = available_points[i + 1]
                            
                            p1 = points[p1_name]
                            p2 = points[p2_name]
                            
                            # Rysuj linię
                            main_ax.plot([p1['index'], p2['index']], [p1['price'], p2['price']], 
                                       color=line_color, alpha=alpha, linewidth=2, linestyle='-')
                            
                            # Dodaj etykietę z proporcją na środku linii
                            mid_x = (p1['index'] + p2['index']) / 2
                            mid_y = (p1['price'] + p2['price']) / 2
                            
                            # Znajdź odpowiednią proporcję
                            prop_text = ""
                            if p1_name == 'A' and p2_name == 'B' and 'AB_XA_ratio' in proportions:
                                prop_text = f"AB/XA: {proportions['AB_XA_ratio']:.3f}"
                            elif p1_name == 'B' and p2_name == 'C' and 'BC_AB_ratio' in proportions:
                                prop_text = f"BC/AB: {proportions['BC_AB_ratio']:.3f}"
                            elif p1_name == 'C' and p2_name == 'D' and 'CD_BC_ratio' in proportions:
                                prop_text = f"CD/BC: {proportions['CD_BC_ratio']:.3f}"
                            
                            if prop_text:
                                main_ax.annotate(prop_text, (mid_x, mid_y), 
                                               xytext=(5, 5), textcoords='offset points',
                                               fontsize=8, color=line_color, alpha=0.8,
                                               bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
                        
                        # Rysuj dodatkowe linie wzorca harmonicznego
                        # Linia X-D (completion line)
                        if 'X' in points and 'D' in points:
                            p_x = points['X']
                            p_d = points['D']
                            main_ax.plot([p_x['index'], p_d['index']], [p_x['price'], p_d['price']], 
                                       color=line_color, alpha=alpha*0.7, linewidth=1, linestyle='--')
                            
                            # Dodaj proporcję XD/XA
                            if 'XD_XA_ratio' in proportions:
                                mid_x = (p_x['index'] + p_d['index']) / 2
                                mid_y = (p_x['price'] + p_d['price']) / 2
                                prop_text = f"XD/XA: {proportions['XD_XA_ratio']:.3f}"
                                main_ax.annotate(prop_text, (mid_x, mid_y), 
                                               xytext=(5, -15), textcoords='offset points',
                                               fontsize=8, color=line_color, alpha=0.8,
                                               bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.7))
                        
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
                            
                            # Dodaj etykietę trójkąta XAB
                            center_x = sum(x_coords[:3]) / 3
                            center_y = sum(y_coords[:3]) / 3
                            main_ax.annotate(f'{pattern_name} XAB', (center_x, center_y), 
                                           ha='center', va='center', fontsize=9, 
                                           color=line_color, alpha=0.9, weight='bold')
                        
                        # Trójkąt B-C-D
                        if 'B' in points and 'C' in points and 'D' in points:
                            x_coords = [points['B']['index'], points['C']['index'], points['D']['index'], points['B']['index']]
                            y_coords = [points['B']['price'], points['C']['price'], points['D']['price'], points['B']['price']]
                            
                            main_ax.fill(x_coords, y_coords, color=triangle_color, alpha=triangle_alpha, 
                                       edgecolor=line_color, linewidth=1)
                            
                            # Dodaj etykietę trójkąta BCD
                            center_x = sum(x_coords[:3]) / 3
                            center_y = sum(y_coords[:3]) / 3
                            main_ax.annotate(f'{pattern_name} BCD', (center_x, center_y), 
                                           ha='center', va='center', fontsize=9, 
                                           color=line_color, alpha=0.9, weight='bold')
                        
                        logger.info(f"Narysowano wzorzec {pattern_name} (ID: {pattern_id}) z {len(proportions)} proporcjami")
                
                else:
                    logger.error("Nie można znaleźć prawidłowego subplot do rysowania wzorców")
                    
            except Exception as e:
                logger.error(f"Błąd podczas rysowania wzorców harmonicznych: {e}")
                logger.error(traceback.format_exc())
        
        # Podsumowanie tego co zostało narysowane
        total_indicators = sum([
            1 if show_rsi and 'rsi' in df.columns else 0,
            1 if show_macd and all(col in df.columns for col in ['macd', 'signal']) else 0,
            1 if show_obv and 'obv' in df.columns else 0
        ])
        
        total_patterns = len(patterns_data) + len(forming_patterns_data) if show_patterns else 0
        total_fib_levels = sum(len(fib['fibonacci']['retracement']) + len(fib['fibonacci']['extension']) + len(fib['fibonacci']['targets']) for fib in fibonacci_data) if show_fibonacci else 0
        total_proportions = sum(len(prop['proportions']) for prop in proportions_data) if show_patterns else 0
        
        logger.info(f"Wykres wygenerowany: {total_indicators} wskaźników, {total_patterns} punktów wzorców, {total_fib_levels} poziomów Fibonacci, {total_proportions} proporcji")
        
        # Dodaj informacje o proporcjach do tytułu jeśli są dostępne
        if total_proportions > 0:
            title += f" | Proporcje: {total_proportions}"
        
        # Zapisywanie wykresu
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            logger.info(f"Wykres zapisany: {save_path}")
        
        # Konwersja do base64
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        chart_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
        logger.info(f"Wykres skonwertowany do base64 ({len(chart_base64)} znaków)")
        return chart_base64 
