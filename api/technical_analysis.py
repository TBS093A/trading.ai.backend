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
                                        }
                                    
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

                                # Teraz dodaj fibonacci do każdego punktu tego wzorca (pattern_retraces już są dodane w linii 301)
                                for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                                    if i >= len(point_names):
                                        break
                                        
                                    kline_idx = find_kline_index(x_point)
                                    
                                    # Dodaj fibonacci do tego punktu wzorca
                                    if fibonacci_levels:
                                        klines[kline_idx]['patterns'][f'{patterns_count}']['fibonacci'] = fibonacci_levels

                                    logger.info(f"Dodano punkt {point_name} wzorca {pattern_name} do świecy {kline_idx}: {str(klines[kline_idx]).replace(',', ',\n')}")
                                
                                
                                logger.info(f"Dodano wzorzec {pattern_name} (ID: {patterns_count}) z pattern_retraces i {len(fibonacci_levels)} poziomami Fibonacci")

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
        
        # Poziomy retracementu: 0%, 18.6%, 23.6%, 38.2%, 50%, 61.8%, 68.5%, 78.6%, 88.6%, 100%
        retracement = {
            "0.0": end_price + (price_range * 0.0 if is_uptrend else -price_range * 0.0),        # 0%
            "0.186": end_price + (price_range * 0.186 if is_uptrend else -price_range * 0.186),  # 18.6%
            "0.236": end_price + (price_range * 0.236 if is_uptrend else -price_range * 0.236),  # 23.6%
            "0.382": end_price + (price_range * 0.382 if is_uptrend else -price_range * 0.382),  # 38.2%
            "0.5": end_price + (price_range * 0.5 if is_uptrend else -price_range * 0.5),        # 50%
            "0.618": end_price + (price_range * 0.618 if is_uptrend else -price_range * 0.618),  # 61.8%
            "0.685": end_price + (price_range * 0.685 if is_uptrend else -price_range * 0.685),  # 68.5%
            "0.786": end_price + (price_range * 0.786 if is_uptrend else -price_range * 0.786),  # 78.6%
            "0.886": end_price + (price_range * 0.886 if is_uptrend else -price_range * 0.886),  # 88.6%
            "1.0": end_price + (price_range * 1.0 if is_uptrend else -price_range * 1.0)         # 100%
        }
        
        # Poziomy extension: 113%, 127.2%, 146%, 161.8%, 223.6%, 261.8%
        extension = {
            "1.13": end_price + (price_range * 1.13 if is_uptrend else -price_range * 1.13),     # 113%
            "1.272": end_price + (price_range * 1.272 if is_uptrend else -price_range * 1.272),  # 127.2%
            "1.46": end_price + (price_range * 1.46 if is_uptrend else -price_range * 1.46),     # 146%
            "1.618": end_price + (price_range * 1.618 if is_uptrend else -price_range * 1.618),  # 161.8%
            "2.236": end_price + (price_range * 2.236 if is_uptrend else -price_range * 2.236),  # 223.6%
            "2.618": end_price + (price_range * 2.618 if is_uptrend else -price_range * 2.618)   # 261.8%
        }
        
        # Targety cenowe: 18.6%, 23.6%, 38.2%, 61.8%, 68.5%, 78.6%, 88.6%, 113%, 127.2%, 146%, 161.8%, 223.6%, 261.8%
        targets = {
            "0.186": end_price + (price_range * 0.186 if is_uptrend else -price_range * 0.186),  # 18.6%
            "0.236": end_price + (price_range * 0.236 if is_uptrend else -price_range * 0.236),  # 23.6%
            "0.382": end_price + (price_range * 0.382 if is_uptrend else -price_range * 0.382),  # 38.2%
            "0.618": end_price + (price_range * 0.618 if is_uptrend else -price_range * 0.618),  # 61.8%
            "0.685": end_price + (price_range * 0.685 if is_uptrend else -price_range * 0.685),  # 68.5%
            "0.786": end_price + (price_range * 0.786 if is_uptrend else -price_range * 0.786),  # 78.6%
            "0.886": end_price + (price_range * 0.886 if is_uptrend else -price_range * 0.886),  # 88.6%
            "1.13": end_price + (price_range * 1.13 if is_uptrend else -price_range * 1.13),     # 113%
            "1.272": end_price + (price_range * 1.272 if is_uptrend else -price_range * 1.272),  # 127.2%
            "1.46": end_price + (price_range * 1.46 if is_uptrend else -price_range * 1.46),     # 146%
            "1.618": end_price + (price_range * 1.618 if is_uptrend else -price_range * 1.618),  # 161.8%
            "2.236": end_price + (price_range * 2.236 if is_uptrend else -price_range * 2.236),  # 223.6%
            "2.618": end_price + (price_range * 2.618 if is_uptrend else -price_range * 2.618)   # 261.8%
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
        panel = 2  # Licznik paneli dla wskaźników
        active_panels = []  # Lista aktywnych paneli do obliczenia panel_ratios
        
        # Dynamiczne wykrywanie i dodawanie wskaźników
        if show_rsi and 'rsi' in df.columns:
            add_plots.append(
                mpf.make_addplot(df['rsi'], panel=panel, color='yellow', ylabel='RSI')
            )
            active_panels.append('rsi')
            panel += 1
            
        if show_macd and all(col in df.columns for col in ['macd', 'signal']):
            add_plots.append(
                mpf.make_addplot(df['macd'], panel=panel, color='blue', ylabel='MACD')
            )
            add_plots.append(
                mpf.make_addplot(df['signal'], panel=panel, color='red')
            )
            if 'histogram' in df.columns:
                add_plots.append(
                    mpf.make_addplot(df['histogram'], panel=panel, type='bar', color='gray', alpha=0.8)
                )
            active_panels.append('macd')
            panel += 1
            
        if show_obv and 'obv' in df.columns:
            add_plots.append(
                mpf.make_addplot(df['obv'], panel=panel, color='green', ylabel='OBV')
            )
            active_panels.append('obv')
            panel += 1
        
        # Oblicz panel_ratios - główny panel (ceny) dostaje najwięcej miejsca
        panel_ratios = [6]  # Panel 0: główny panel z cenami - duży
        
        # Panel 1: volume (jeśli włączony) - mały
        if 'volume' in df.columns:
            panel_ratios.append(1)
        
        # Panele 2+: wskaźniki techniczne - bardzo małe
        for _ in active_panels:
            panel_ratios.append(1)  # Każdy wskaźnik dostaje małą wysokość
        
        logger.info(f"Panel ratios: {panel_ratios} dla paneli: główny + volume + {active_panels}")
            
        # Przygotowanie danych wzorców harmonicznych z nowej zagnieżdżonej struktury
        # Przeszukaj klines aby znaleźć wzorce w nowej strukturze
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
        
        # Poziomy Fibonacciego będą rysowane jako linie w sekcji wzorców harmonicznych
        
        # Oblicz dynamiczną szerokość wykresu na podstawie ilości świec
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
            # Używamy logarytmu cenowej proporcji dla lepszego skalowania
            import numpy as np  # Import numpy dla obliczenia logarytmu
            price_ratio = y_max_for_height / y_min_for_height if y_min_for_height > 0 else 1
            # Skalowanie na podstawie logarytmu - większy zakres = wyższy wykres
            height_multiplier = max(0.8, min(3.0, np.log10(price_ratio) + 1))
            dynamic_height = int(base_height * height_multiplier)
        else:
            dynamic_height = base_height
        
        # Ustal minimalną i maksymalną wysokość dla praktyczności
        min_height = 20
        if show_rsi and 'rsi' in df.columns:
            min_height += 10
        if show_macd and 'macd' in df.columns:
            min_height += 10
        if show_obv and 'obv' in df.columns:
            min_height += 10
        max_height = 100
        dynamic_height = max(min_height, min(dynamic_height, max_height))
        
        logger.info(f"Dynamiczna szerokość wykresu: {dynamic_width} (dla {candles_count} świec, mnożnik: {width_multiplier:.2f})")
        logger.info(f"Dynamiczna wysokość wykresu: {dynamic_height} (dla zakresu {price_range_for_height:.6f}, ratio: {y_max_for_height/y_min_for_height if y_min_for_height > 0 else 1:.2f})")
        
        # Oblicz interwał dla osi X na podstawie ilości świec
        candles_count = len(df)
        if candles_count <= 200:
            tick_interval = 1  # Co piąta świeca
        elif candles_count > 200:
            tick_interval = candles_count / 100
            
        logger.info(f"Interwał osi X: co {tick_interval} świeca (dla {candles_count} świec)")
        
        # Oblicz parametry formatowania osi Y PRZED wywołaniem mpf.plot
        import matplotlib.ticker as ticker
        import numpy as np
        
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
        
        # Oblicz dodatkowy padding dla etykiet wzorców harmonicznych
        # Jednakowy padding górny i dolny w pikselach
        fig_height_inches = dynamic_height
        dpi = 300
        fig_height_pixels = fig_height_inches * dpi
        
        # Konwersja 5000px na proporcję wysokości wykresu
        padding_pixels = 10000
        if show_rsi and 'rsi' in df.columns:
            padding_pixels += 5000
        if show_macd and 'macd' in df.columns:
            padding_pixels += 5000
        if show_obv and 'obv' in df.columns:
            padding_pixels += 5000
        padding_ratio = padding_pixels / fig_height_pixels
        
        # Oblicz padding w jednostkach cenowych dla skali logarytmicznej
        # Każdy padding (górny i dolny) to padding_ratio * współczynnik
        single_padding_factor = padding_ratio * 0.15  # Współczynnik dla skali log
        
        logger.info(f"Obliczony padding: {padding_pixels}px = {padding_ratio:.4f} ratio = {single_padding_factor:.4f} factor na stronę")
        
        # Tworzenie wykresu z dynamiczną szerokością i wysokością, skalą logarytmiczną i lepszym formatowaniem osi X
        fig, axes = mpf.plot(
            df,
            type='candle',
            style=cls.CHART_STYLES["binance_dark"],
            title=title,
            volume='volume' in df.columns,
            addplot=add_plots,
            returnfig=True,
            figsize=(dynamic_width, dynamic_height),
            yscale='log',  # Skala logarytmiczna dla osi Y
            datetime_format='%H:%M %d/%m/%Y',  # Format daty i czasu na osi X
            xrotation=45,  # Obrót etykiet osi X dla lepszej czytelności
            tight_layout=True,  # Lepsze rozłożenie elementów
            show_nontrading=False,  # Ukryj okresy bez tradingu
            scale_padding=dict(left=0.3, right=1.0, top=1.2, bottom=1.2),  # Zwiększony padding dla etykiet
            panel_ratios=panel_ratios  # Kontrola wysokości paneli
        )

        # Dodaj dodatkowy padding dla etykiet wzorców harmonicznych (jednakowy górny i dolny)
        try:
            # Pobierz główną oś cenową
            main_ax = axes[0] if hasattr(axes, '__len__') and len(axes) > 0 else axes
            
            # Pobierz aktualne granice osi Y
            y_min_current, y_max_current = main_ax.get_ylim()
            
            # Oblicz zakres cenowy w skali logarytmicznej
            log_y_min = np.log(y_min_current) if y_min_current > 0 else np.log(0.0001)
            log_y_max = np.log(y_max_current) if y_max_current > 0 else np.log(0.0001)
            log_range = log_y_max - log_y_min
            
            # Oblicz padding w skali logarytmicznej (jednakowy górny i dolny)
            log_padding = log_range * single_padding_factor
            
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
        if hasattr(axes, '__len__') and len(axes) > 0:
            main_ax = axes[0]
        elif hasattr(axes, 'plot'):
            main_ax = axes
        else:
            main_ax = axes
            
        # Ustaw interwał tick-ów na osi X
        try:
            import matplotlib.ticker as ticker
            # Ustawij locator dla osi X z obliczonym interwałem
            main_ax.xaxis.set_major_locator(ticker.MultipleLocator(tick_interval))
            main_ax.xaxis.set_minor_locator(ticker.MultipleLocator(1))
            
            # Poprawa formatowania osi Y dla skali logarytmicznej
            main_ax.yaxis.set_major_formatter(ticker.FormatStrFormatter('%.4f'))
            main_ax.yaxis.set_minor_formatter(ticker.NullFormatter())

            # Obrócenie Labeli pod bardziej czytelną formę
            for ax in axes:
                for label in ax.get_xticklabels():
                    label.set_rotation(90)
            
            logger.info(f"Ustawiono tick interwał {tick_interval} dla osi X i formatowanie dla skali logarytmicznej")
        except Exception as e:
            logger.warning(f"Nie można ustawić formatowania osi: {e}")
        
        # Dostosuj formatowanie osi bezpośrednio po utworzeniu wykresu
        yticks = np.geomspace(df['low'].min(), df['high'].max(), num=10)
        axes[0].set_yticks(yticks)
        axes[0].get_yaxis().set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:,.0f}'))
        
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
                    
                    # Oblicz dynamiczną wielkość czcionki na podstawie rozmiaru wykresu i paddingu
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
                    
                    logger.info(f"Dynamiczna wielkość czcionki - etykiety: {dynamic_font_size_labels}, osi: {dynamic_font_size_axes}, fibonacci: {dynamic_font_size_fibo_labels} (współczynnik: {scaling_ratio:.3f}, szerokość: {width_factor:.2f}, wysokość: {height_factor:.2f}, padding: {padding_factor:.2f})")
                    
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
                    
                    # Rysuj poziomy Fibonacciego jako linie z etykietami jeśli włączone
                    if show_fibonacci and fibonacci_data:
                        cls._draw_fibonacci_lines_with_labels(
                            main_ax, fibonacci_data, pattern_groups, klines, 
                            dynamic_font_size_fibo_labels, df
                        )
                    
                    # Rysuj etykiety wzorców in paddingu po zakończeniu wszystkich wzorców
                    if pattern_labels_for_padding:
                        cls._draw_pattern_labels_in_padding(
                            main_ax, pattern_labels_for_padding, df, 
                            dynamic_width, dynamic_height, dynamic_font_size_labels
                        )
                    
                    # Zastosuj skalowaną czcionkę do osi X i Y
                    cls._apply_scaled_font_to_axes(main_ax, axes, dynamic_font_size_axes)
                
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
        total_retraces = sum(len(retrace['pattern_retraces']) for retrace in retraces_data) if show_patterns else 0
        
        logger.info(f"Wykres wygenerowany: {total_indicators} wskaźników, {total_patterns} punktów wzorców, {total_fib_levels} poziomów Fibonacci, {total_retraces} retraces")
        
        # Dodaj informacje o retraces do tytułu jeśli są dostępne
        if total_retraces > 0:
            title += f" | Retraces: {total_retraces}"
        
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
    
    @classmethod
    def _draw_pattern_labels_in_padding(
        cls,
        main_ax,
        pattern_labels_for_padding: List[Dict],
        df: pd.DataFrame,
        chart_width: int,
        chart_height: int,
        dynamic_font_size_labels: int
    ):
        """
        Rysuje etykiety wzorców harmonicznych w strefie paddingu.
        
        Args:
            main_ax: Główna oś wykresu
            pattern_labels_for_padding: Lista danych etykiet wzorców
            df: DataFrame z danymi cenowymi
            chart_width: Szerokość wykresu
            chart_height: Wysokość wykresu
            dynamic_font_size_labels: Dynamiczna wielkość czcionki
        """
        try:
            # Pobierz granice osi
            y_min, y_max = main_ax.get_ylim()
            x_min, x_max = main_ax.get_xlim()
            
            logger.info(f"Używanie dynamicznej wielkości czcionki w paddingu: {dynamic_font_size_labels}")
            
            # Oblicz pozycje stref paddingu w skali logarytmicznej
            import numpy as np
            log_y_min = np.log(y_min) if y_min > 0 else np.log(0.0001)
            log_y_max = np.log(y_max) if y_max > 0 else np.log(0.0001)
            log_range = log_y_max - log_y_min
            
            # Strefy paddingu (w skali logarytmicznej)
            padding_height_log = log_range * 0.15  # 15% zakresu jako strefa paddingu
            
            # Górna strefa paddingu
            top_padding_center_log = log_y_max - (padding_height_log / 2)
            top_padding_center = np.exp(top_padding_center_log)
            
            # Dolna strefa paddingu
            bottom_padding_center_log = log_y_min + (padding_height_log / 2)
            bottom_padding_center = np.exp(bottom_padding_center_log)
            
            logger.info(f"Strefy paddingu: górna={top_padding_center:.6f}, dolna={bottom_padding_center:.6f}")
            
            # Podziel etykiety na górne i dolne na podstawie pozycji punktu D
            top_labels = []
            bottom_labels = []
            
            for label_data in pattern_labels_for_padding:
                d_point = label_data['d_point']
                d_price = d_point['price']
                
                # Oblicz odległości do stref paddingu w skali logarytmicznej
                if d_price > 0:
                    log_d_price = np.log(d_price)
                    dist_to_top = abs(log_d_price - top_padding_center_log)
                    dist_to_bottom = abs(log_d_price - bottom_padding_center_log)
                    
                    if dist_to_top <= dist_to_bottom:
                        top_labels.append(label_data)
                    else:
                        bottom_labels.append(label_data)
                else:
                    bottom_labels.append(label_data)  # Fallback dla nieprawidłowych cen
            
            logger.info(f"Rozmieszczenie etykiet: {len(top_labels)} górnych, {len(bottom_labels)} dolnych")
            
            # Rysuj etykiety w górnej strefie paddingu
            if top_labels:
                cls._draw_labels_in_zone(
                    main_ax, top_labels, top_padding_center, 
                    x_min, x_max, dynamic_font_size_labels, 'top'
                )
            
            # Rysuj etykiety w dolnej strefie paddingu
            if bottom_labels:
                cls._draw_labels_in_zone(
                    main_ax, bottom_labels, bottom_padding_center, 
                    x_min, x_max, dynamic_font_size_labels, 'bottom'
                )
                
        except Exception as e:
            logger.error(f"Błąd podczas rysowania etykiet w paddingu: {e}")
            logger.error(traceback.format_exc())
    
    @classmethod
    def _draw_labels_in_zone(
        cls,
        main_ax,
        labels: List[Dict],
        zone_y: float,
        x_min: float,
        x_max: float,
        font_size: int,
        zone_type: str
    ):
        """
        Rysuje etykiety w określonej strefie paddingu z równomiernym rozmieszczeniem.
        
        Args:
            main_ax: Główna oś wykresu
            labels: Lista etykiet do narysowania
            zone_y: Pozycja Y strefy paddingu
            x_min, x_max: Granice osi X
            font_size: Wielkość czcionki
            zone_type: 'top' lub 'bottom'
        """
        if not labels:
            return
        
        try:
            # Oblicz pozycje X dla etykiet (równomiernie rozłożone)
            available_width = x_max - x_min
            if len(labels) == 1:
                x_positions = [(x_min + x_max) / 2]  # Środek dla jednej etykiety
            else:
                # Równomierne rozłożenie z marginesami
                margin = available_width * 0.05  # 5% margines z każdej strony
                usable_width = available_width - 2 * margin
                step = usable_width / (len(labels) - 1) if len(labels) > 1 else 0
                x_positions = [x_min + margin + i * step for i in range(len(labels))]
            
            # Rysuj każdą etykietę bez linii łączących
            for i, (label_data, x_pos) in enumerate(zip(labels, x_positions)):
                pattern_label = label_data['pattern_label']
                line_color = label_data['line_color']
                
                # Rysuj etykietę
                va = 'center'
                main_ax.annotate(
                    pattern_label,
                    (x_pos, zone_y),
                    ha='center', 
                    va=va,
                    fontsize=font_size, 
                    weight='bold',
                    color=line_color, 
                    alpha=0.9,
                    bbox=dict(
                        boxstyle="round,pad=0.5", 
                        facecolor='black', 
                        alpha=0.7, 
                        edgecolor=line_color
                    ),
                    zorder=11
                )
                
                logger.debug(f"Narysowano etykietę wzorca w strefie {zone_type}: x={x_pos:.2f}, y={zone_y:.6f}")
                
        except Exception as e:
            logger.error(f"Błąd podczas rysowania etykiet w strefie {zone_type}: {e}")
            logger.error(traceback.format_exc()) 
    
    @classmethod
    def _apply_scaled_font_to_axes(
        cls,
        main_ax,
        axes,
        dynamic_font_size_axes: int
    ):
        """
        Stosuje skalowaną czcionkę do osi X i Y oraz ylabel.
        
        Args:
            main_ax: Główna oś wykresu
            axes: Wszystkie osie wykresu
            dynamic_font_size_axes: Dynamiczna wielkość czcionki dla osi
        """
        try:
            logger.info(f"Stosowanie skalowanej czcionki {dynamic_font_size_axes}px do osi X i Y")
            
            # Zastosuj czcionkę do głównej osi (main_ax)
            if main_ax:
                # Skala osi X
                main_ax.tick_params(axis='x', labelsize=dynamic_font_size_axes)
                main_ax.tick_params(axis='y', labelsize=dynamic_font_size_axes)
                
                # ylabel dla głównej osi
                if hasattr(main_ax, 'set_ylabel'):
                    current_ylabel = main_ax.get_ylabel()
                    if current_ylabel:
                        main_ax.set_ylabel(current_ylabel, fontsize=dynamic_font_size_axes)
                
                # xlabel dla głównej osi
                if hasattr(main_ax, 'set_xlabel'):
                    current_xlabel = main_ax.get_xlabel()
                    if current_xlabel:
                        main_ax.set_xlabel(current_xlabel, fontsize=dynamic_font_size_axes)
            
            # Zastosuj czcionkę do wszystkich osi (w przypadku paneli)
            if hasattr(axes, '__len__'):
                for ax in axes:
                    if hasattr(ax, 'tick_params'):
                        ax.tick_params(axis='x', labelsize=dynamic_font_size_axes)
                        ax.tick_params(axis='y', labelsize=dynamic_font_size_axes)
                        
                        # ylabel dla każdej osi
                        if hasattr(ax, 'set_ylabel'):
                            current_ylabel = ax.get_ylabel()
                            if current_ylabel:
                                ax.set_ylabel(current_ylabel, fontsize=dynamic_font_size_axes)
                        
                        # xlabel dla każdej osi
                        if hasattr(ax, 'set_xlabel'):
                            current_xlabel = ax.get_xlabel()
                            if current_xlabel:
                                ax.set_xlabel(current_xlabel, fontsize=dynamic_font_size_axes)
            elif hasattr(axes, 'tick_params'):
                # axes jest pojedynczą osią
                axes.tick_params(axis='x', labelsize=dynamic_font_size_axes)
                axes.tick_params(axis='y', labelsize=dynamic_font_size_axes)
                
                # ylabel dla pojedynczej osi
                if hasattr(axes, 'set_ylabel'):
                    current_ylabel = axes.get_ylabel()
                    if current_ylabel:
                        axes.set_ylabel(current_ylabel, fontsize=dynamic_font_size_axes)
                
                # xlabel dla pojedynczej osi
                if hasattr(axes, 'set_xlabel'):
                    current_xlabel = axes.get_xlabel()
                    if current_xlabel:
                        axes.set_xlabel(current_xlabel, fontsize=dynamic_font_size_axes)
            
            logger.info(f"Pomyślnie zastosowano czcionkę {dynamic_font_size_axes}px do osi")
            
        except Exception as e:
            logger.error(f"Błąd podczas stosowania skalowanej czcionki do osi: {e}")
            logger.error(traceback.format_exc())
    
    @classmethod
    def _draw_fibonacci_lines_with_labels(
        cls,
        main_ax,
        fibonacci_data: List[Dict],
        pattern_groups: Dict,
        klines: List[Dict],
        dynamic_font_size_fibo_labels: int,
        df: pd.DataFrame
    ):
        """
        Rysuje poziomy Fibonacciego jako linie z etykietami.
        
        Args:
            main_ax: Główna oś wykresu
            fibonacci_data: Lista danych poziomów Fibonacci
            pattern_groups: Grupy wzorców harmonicznych
            klines: Lista świeczek
            dynamic_font_size_fibo_labels: Wielkość czcionki dla etykiet Fibonacci
            df: DataFrame z danymi cenowymi
        """
        try:
            # Funkcja do określania koloru na podstawie poziomu Fibonacci
            def get_fibonacci_color(fib_type, level_name):
                # Zielone linie dla retracement: 18.6%, 23.6%, 38.2%, 61.8%, 68.5%, 78.6%, 88.6%
                green_retracement = ['0.186', '0.236', '0.382', '0.618', '0.685', '0.786', '0.886']
                # Zielone linie dla extension: 113%, 127.2%, 146%, 161.8%, 223.6%, 261.8%
                green_extension = ['1.13', '1.272', '1.46', '1.618', '2.236', '2.618']
                # Szare linie dla 0% i 100%
                gray_levels = ['0.0', '1.0']
                
                if level_name in gray_levels:
                    return '#808080'  # Szary
                elif (fib_type == 'retracement' and level_name in green_retracement) or \
                     (fib_type == 'extension' and level_name in green_extension) or \
                     (fib_type == 'targets' and (level_name in green_retracement or level_name in green_extension)):
                    return '#00FF00'  # Zielony
                else:
                    return '#FFFFFF'  # Biały dla pozostałych
            
            # Pobierz granice wykresu
            x_min, x_max = main_ax.get_xlim()
            chart_end_x = len(df) - 1  # Ostatnia świeca
            
            logger.info(f"Rysowanie {len(fibonacci_data)} poziomów Fibonacci jako linie z etykietami")
            
            # Iteruj od tyłu po klines aby współmiernie oznaczyć linie
            processed_patterns = set()  # Żeby uniknąć duplikowania wzorców
            
            for kline_idx in range(len(klines) - 1, -1, -1):  # Od końca do początku
                kline = klines[kline_idx]
                
                # Sprawdź czy ta świeca zawiera wzorce z poziomami Fibonacci
                if 'patterns' not in kline:
                    continue
                
                for pattern_id, pattern_info in kline['patterns'].items():
                    # Sprawdź czy już przetwarzaliśmy ten wzorzec
                    if pattern_id in processed_patterns:
                        continue
                    
                    # Sprawdź czy ten wzorzec ma poziomy Fibonacci
                    if 'fibonacci' not in pattern_info:
                        continue
                    
                    fibonacci = pattern_info['fibonacci']
                    processed_patterns.add(pattern_id)
                    
                    # Znajdź punkty X i D tego wzorca
                    pattern_group = pattern_groups.get(pattern_id, {})
                    points = pattern_group.get('points', {})
                    
                    x_point = points.get('X')
                    d_point = points.get('D')
                    
                    logger.info(f"Rysowanie poziomów Fibonacci dla wzorca {pattern_id}")
                    
                                         # Przetwórz każdy typ poziomów Fibonacciego
                    for fib_type, levels in fibonacci.items():
                        linestyle = '--' if fib_type == 'retracement' else (':' if fib_type == 'extension' else '-')
                        alpha = 0.8  # Jednolita przezroczystość
                        linewidth = 1.5 if fib_type == 'targets' else 1
                        
                        # Określ punkt startowy linii
                        start_point = None
                        if fib_type in ['retracement', 'extension']:
                            start_point = x_point  # Linie retracement i extension od punktu X
                        elif fib_type == 'targets':
                            start_point = d_point  # Linie targets od punktu D
                        
                        if start_point is None:
                            logger.warning(f"Brak punktu startowego dla {fib_type} wzorca {pattern_id}")
                            continue
                        
                        start_x = start_point['index']
                        
                        # Rysuj każdy poziom Fibonacci
                        for level_name, level_price in levels.items():
                            if level_price == 0 or pd.isna(level_price):
                                continue
                            
                            # Określ kolor na podstawie poziomu i typu
                            color = get_fibonacci_color(fib_type, level_name)
                            
                            # Rysuj linię od punktu startowego do końca wykresu
                            main_ax.plot(
                                [start_x, chart_end_x], 
                                [level_price, level_price],
                                color=color,
                                alpha=alpha,
                                linestyle=linestyle,
                                linewidth=linewidth,
                                zorder=5  # Nad świecami, ale pod wzorcami
                            )
                            
                            # Oblicz procent poziomu Fibonacci
                            try:
                                # Poziomy liczbowe (0.236, 1.618, itp.)
                                fib_value = float(level_name)
                                fib_percent = f"{fib_value * 100:.1f}%"
                            except ValueError:
                                # Fallback jeśli nie da się przekonwertować
                                fib_percent = level_name
                            
                            # Tekst etykiety
                            label_text = f"ID: {pattern_id} | {fib_percent} | {level_price:.6f}"
                            
                            # Pozycja etykiety - lewa górna krawędź linii
                            label_x = start_x + 2  # Przesunięcie od początku linii
                            label_y = level_price
                            
                            # Dodaj etykietę z transparentnym tłem
                            main_ax.annotate(
                                label_text,
                                (label_x, label_y),
                                xytext=(0, 3),  # Małe przesunięcie w górę
                                textcoords='offset points',
                                ha='left',
                                va='bottom',
                                fontsize=dynamic_font_size_fibo_labels,
                                color=color,
                                alpha=0.9,
                                bbox=dict(
                                    boxstyle="round,pad=0.2",
                                    facecolor='black',
                                    alpha=0.1,  # Maksymalnie transparentne tło
                                    edgecolor='none'  # Bez borderów
                                ),
                                zorder=6  # Nad liniami Fibonacci
                            )
                            
                            logger.debug(f"Narysowano linię {fib_type} Fibonacci {level_name} = {level_price:.6f} dla wzorca {pattern_id}")
            
            logger.info(f"Pomyślnie narysowano linie Fibonacci dla {len(processed_patterns)} wzorców")
            
        except Exception as e:
            logger.error(f"Błąd podczas rysowania linii Fibonacci: {e}")
            logger.error(traceback.format_exc())
