import numpy as np
from typing import List, Dict, Union, Optional, Tuple
import logging
from dataclasses import dataclass
import mplfinance as mpf
import pandas as pd
import base64
from io import BytesIO
import matplotlib.pyplot as plt

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

    @staticmethod
    def _timestamp_to_datetime(timestamp: Union[int, float]) -> str:
        """
        Konwertuje timestamp na czytelny format daty.
        
        Args:
            timestamp: Timestamp w milisekundach
            
        Returns:
            String z datą w formacie YYYY-MM-DD HH:MM:SS
        """
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(timestamp / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(timestamp)

    @classmethod
    def _convert_pyharmonics_pattern(cls, pattern, klines: List[Dict[str, Union[int, float, str]]]) -> HarmonicPattern:
        """
        Konwertuje wzorzec z pyharmonics na nasz format HarmonicPattern.
        
        Args:
            pattern: Wzorzec z pyharmonics
            klines: Oryginalne dane klines
            
        Returns:
            HarmonicPattern w naszym formacie
        """
        try:
            # Pobierz punkty XABCD z wzorca
            x_points = pattern.x
            y_points = pattern.y
            
            # Sprawdź czy mamy wystarczającą liczbę punktów
            if len(y_points) < 3:
                logger.warning(f"Wzorzec ma za mało punktów: {len(y_points)}")
                return None
            
            # Sprawdź typy danych punktów
            logger.debug(f"Typy x_points: {[type(x) for x in x_points]}")
            logger.debug(f"Typy y_points: {[type(y) for y in y_points]}")
            
            # Stwórz DataFrame w tym samym formacie co używa create_candlestick_chart
            df = pd.DataFrame(klines)
            df['date'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('date', inplace=True)
            
            # Funkcja do znajdowania najbliższej świecy w naszych danych
            def find_closest_kline_datetime(x_point):
                """
                Znajduje najbliższą datę świecy w naszych danych klines
                dla punktu x z pyharmonics.
                """
                print(f"Szukam najbliższej świecy dla: {x_point} (typ: {type(x_point)})")
                
                # Konwertuj punkt na datetime jeśli to potrzebne
                if hasattr(x_point, 'timestamp'):
                    # To jest już pandas Timestamp
                    target_datetime = x_point
                    print(f"  -> target datetime (pandas): {target_datetime}")
                elif isinstance(x_point, (int, float)):
                    # To może być timestamp lub indeks
                    if x_point > 1000000000000:  # Timestamp w ms
                        target_datetime = pd.to_datetime(x_point, unit='ms')
                    elif x_point > 1000000000:  # Timestamp w s
                        target_datetime = pd.to_datetime(x_point, unit='s')
                    else:
                        # To może być indeks DataFrame - użyj go bezpośrednio
                        idx = int(x_point)
                        if 0 <= idx < len(df):
                            closest_datetime = df.index[idx]
                            print(f"  -> użyto indeks {idx}: {closest_datetime}")
                            return closest_datetime
                        else:
                            # Poza zakresem - użyj pierwszą lub ostatnią
                            closest_datetime = df.index[0] if idx < 0 else df.index[-1]
                            print(f"  -> indeks {idx} poza zakresem, użyto: {closest_datetime}")
                            return closest_datetime
                    print(f"  -> target datetime (konwersja): {target_datetime}")
                else:
                    # Spróbuj bezpośredniej konwersji
                    try:
                        target_datetime = pd.to_datetime(x_point)
                        print(f"  -> target datetime (bezpośrednia): {target_datetime}")
                    except:
                        # Fallback - użyj pierwszą datę
                        closest_datetime = df.index[0]
                        print(f"  -> fallback na pierwszą datę: {closest_datetime}")
                        return closest_datetime
                
                # Znajdź najbliższą datę w naszych danych klines
                time_diffs = abs(df.index - target_datetime)
                closest_idx = time_diffs.argmin()
                closest_datetime = df.index[closest_idx]
                
                print(f"  -> najbliższa świeca: {closest_datetime} (indeks: {closest_idx})")
                print(f"  -> różnica czasowa: {time_diffs[closest_idx]}")
                
                return closest_datetime
            
            # Znajdź najbliższe daty świec dla każdego punktu wzorca
            x_datetimes = []
            logger.info(f"Mapowanie {len(x_points)} punktów wzorca na daty klines:")
            logger.info(f"Zakres klines: {df.index.min()} do {df.index.max()}")
            logger.info(f"Typ indeksu: {type(df.index[0])}")
            logger.info(f"Przykładowe daty z indeksu: {df.index[:3].tolist()}")
            
            for i, x_point in enumerate(x_points):
                mapped_datetime = find_closest_kline_datetime(x_point)
                x_datetimes.append(mapped_datetime)
                logger.info(f"Punkt {i}: {x_point} -> {mapped_datetime} (typ: {type(mapped_datetime)})")
            
            logger.info(f"Pomyślnie zmapowano wszystkie {len(x_datetimes)} punktów")
            
            # Konwertuj punkty na nasz format w zależności od typu wzorca
            if len(y_points) >= 5:
                # Wzorzec XABCD (5 punktów)
                xabcd_points = {
                    "X": {"price": y_points[0], "time": x_datetimes[0]},
                    "A": {"price": y_points[1], "time": x_datetimes[1]},
                    "B": {"price": y_points[2], "time": x_datetimes[2]},
                    "C": {"price": y_points[3], "time": x_datetimes[3]},
                    "D": {"price": y_points[4], "time": x_datetimes[4]}
                }
                pattern_name = pattern.name
            elif len(y_points) == 4:
                # Wzorzec ABCD (4 punkty)
                xabcd_points = {
                    "X": {"price": y_points[0], "time": x_datetimes[0]},  # A jako X
                    "A": {"price": y_points[1], "time": x_datetimes[1]},  # B jako A
                    "B": {"price": y_points[2], "time": x_datetimes[2]},  # C jako B
                    "C": {"price": y_points[3], "time": x_datetimes[3]},  # D jako C
                    "D": {"price": y_points[3], "time": x_datetimes[3]}   # D jako D (ten sam punkt)
                }
                pattern_name = f"ABCD-{pattern.name}"
            elif len(y_points) == 3:
                # Wzorzec ABC (3 punkty)
                xabcd_points = {
                    "X": {"price": y_points[0], "time": x_datetimes[0]},  # A jako X
                    "A": {"price": y_points[1], "time": x_datetimes[1]},  # B jako A
                    "B": {"price": y_points[2], "time": x_datetimes[2]},  # C jako B
                    "C": {"price": y_points[2], "time": x_datetimes[2]},  # C jako C (ten sam punkt)
                    "D": {"price": y_points[2], "time": x_datetimes[2]}   # C jako D (ten sam punkt)
                }
                # Konwertuj nazwę wzorca ABC na bardziej opisową
                if isinstance(pattern.name, (int, float)):
                    pattern_name = f"ABC-{pattern.name}"
                else:
                    pattern_name = f"ABC-{str(pattern.name)}"
            else:
                logger.warning(f"Nieznany typ wzorca z {len(y_points)} punktami")
                return None
            
            # Określ kierunek wzorca
            direction = "bullish" if pattern.bullish else "bearish"
            
            # Oblicz poziomy Fibonacciego
            fib_levels = cls.calculate_fibonacci_levels(
                xabcd_points["X"]["price"],
                xabcd_points["D"]["price"],
                direction == "bullish"
            )
            
            # Oblicz strefę zakończenia
            completion_zone = (
                pattern.completion_min_price if hasattr(pattern, 'completion_min_price') else xabcd_points["D"]["price"] * 0.99,
                pattern.completion_max_price if hasattr(pattern, 'completion_max_price') else xabcd_points["D"]["price"] * 1.01
            )
            
            # Utwórz wzorzec
            return HarmonicPattern(
                name=pattern_name,
                xabcd_points=xabcd_points,
                fibonacci_levels=fib_levels,
                direction=direction,
                completion_zone=completion_zone,
                formed=pattern.formed,
                tolerance=0.1
            )
            
        except Exception as e:
            logger.error(f"Błąd podczas konwersji wzorca: {e}")
            return None

    @classmethod
    def calculate_harmonic_patterns(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5,
        tolerance: float = 0.1,
        min_quality: float = 0.7
    ) -> int:
        """
        Oblicza formacje harmoniczne XABCD używając biblioteki pyharmonics
        i nanosi punkty wzorców bezpośrednio na odpowiednie świece w klines.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            tolerance: Tolerancja dla wzorca (domyślnie 10%)
            min_quality: Minimalna jakość wzorca (0-1)
            
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
            technicals = Technicals(df, 'BTCUSDT', '1w', peak_spacing=20)
            
            # Wykonaj wyszukiwanie wzorców
            harmonic_search = HarmonicSearch(technicals)
            harmonic_search.search()
            
            # Pobierz wszystkie wzorce
            patterns = harmonic_search.get_patterns()
            
            logger.info(f"Znaleziono wzorce: {list(patterns.keys()) if patterns else 'brak'}")
            
            patterns_count = 0
            
            # Przetwórz wzorce i nanieś punkty na klines
            for pattern_type_key in patterns:
                pattern_list = patterns[pattern_type_key]
                logger.info(f"Przetwarzanie {len(pattern_list)} wzorców typu {pattern_type_key}")
                
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
                            pattern_name = f"{pattern.name}_{patterns_count}"
                        elif len(y_points) == 4:
                            point_names = ["A", "B", "C", "D"]
                            pattern_name = f"ABCD_{pattern.name}_{patterns_count}"
                        elif len(y_points) == 3:
                            point_names = ["A", "B", "C"]
                            pattern_name = f"ABC_{pattern.name}_{patterns_count}"
                        else:
                            continue
                        
                        # Nanieś punkty na odpowiednie świece
                        for i, (x_point, y_point) in enumerate(zip(x_points, y_points)):
                            if i >= len(point_names):
                                break
                                
                            kline_idx = find_kline_index(x_point)
                            point_name = point_names[i]
                            
                            # Dodaj informacje o punkcie do świecy
                            klines[kline_idx][f'pattern_{point_name}_price'] = float(y_point)
                            klines[kline_idx][f'pattern_{point_name}_name'] = pattern_name
                            klines[kline_idx][f'pattern_{point_name}_type'] = str(pattern.name)
                            klines[kline_idx][f'pattern_{point_name}_bullish'] = bool(pattern.bullish)
                            
                            logger.debug(f"Dodano punkt {point_name} wzorca {pattern_name} do świecy {kline_idx}: cena={y_point}")
                        
                        # Oblicz i dodaj poziomy Fibonacciego do pierwszej świecy wzorca
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
                            
                            # Dodaj poziomy do pierwszej świecy wzorca
                            for level_name, level_price in fib_levels.retracement.items():
                                klines[first_kline_idx][f'fib_ret_{level_name}_{pattern_name}'] = float(level_price)
                            
                            for level_name, level_price in fib_levels.extension.items():
                                klines[first_kline_idx][f'fib_ext_{level_name}_{pattern_name}'] = float(level_price)
                            
                            for target_name, target_price in fib_levels.targets.items():
                                klines[first_kline_idx][f'fib_target_{target_name}_{pattern_name}'] = float(target_price)
                        
                        patterns_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Błąd podczas przetwarzania wzorca {pattern_idx}: {e}")
                        continue
            
            logger.info(f"Pomyślnie naniesiono {patterns_count} wzorców na świece")
            return patterns_count
            
        except Exception as e:
            logger.error(f"Błąd podczas wykrywania wzorców harmonicznych: {e}")
            return 0

    @classmethod
    def calculate_harmonic_patterns_forming(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5
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
            technicals = Technicals(df, 'BTCUSDT', '1w', peak_spacing=20)
            
            # Wykonaj wyszukiwanie wzorców w trakcie formowania
            harmonic_search = HarmonicSearch(technicals)
            harmonic_search.forming()
            
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
                            
                            # Dodaj informacje o punkcie do świecy (z prefiksem forming_)
                            klines[kline_idx][f'forming_pattern_{point_name}_price'] = float(y_point)
                            klines[kline_idx][f'forming_pattern_{point_name}_name'] = pattern_name
                            klines[kline_idx][f'forming_pattern_{point_name}_type'] = str(pattern.name)
                            klines[kline_idx][f'forming_pattern_{point_name}_bullish'] = bool(pattern.bullish)
                            
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
    def _find_swing_points(cls, highs: List[float], lows: List[float], window: int = 5) -> Tuple[List[int], List[int]]:
        """
        Znajduje punkty zwrotne (swing points) w danych cenowych.
        
        Args:
            highs: Lista najwyższych cen
            lows: Lista najniższych cen
            window: Okno do analizy punktów zwrotnych
            
        Returns:
            Tuple zawierający listy indeksów punktów zwrotnych (szczyty i dołki)
        """
        peaks = []
        troughs = []
        
        for i in range(window, len(highs) - window):
            # Sprawdź czy jest to szczyt
            if all(highs[i] > highs[i-j] for j in range(1, window+1)) and \
               all(highs[i] > highs[i+j] for j in range(1, window+1)):
                peaks.append(i)
            
            # Sprawdź czy jest to dołek
            if all(lows[i] < lows[i-j] for j in range(1, window+1)) and \
               all(lows[i] < lows[i+j] for j in range(1, window+1)):
                troughs.append(i)
                
        return peaks, troughs

    @classmethod
    def _calculate_ratio(cls, price1: float, price2: float, price3: float) -> float:
        """
        Oblicza stosunek Fibonacciego między trzema cenami.
        
        Args:
            price1: Pierwsza cena
            price2: Druga cena
            price3: Trzecia cena
            
        Returns:
            Stosunek Fibonacciego
        """
        if abs(price2 - price1) == 0:
            return 0
        return abs(price3 - price2) / abs(price2 - price1)

    @classmethod
    def _is_pattern_valid(cls, pattern_name: str, ratios: Dict[str, float]) -> bool:
        """
        Sprawdza czy stosunki Fibonacciego pasują do wzorca.
        
        Args:
            pattern_name: Nazwa wzorca
            ratios: Słownik ze stosunkami Fibonacciego
            
        Returns:
            True jeśli wzorzec jest prawidłowy, False w przeciwnym razie
        """
        pattern_ratios = cls.PATTERN_RATIOS[pattern_name]
        
        for key, (min_ratio, max_ratio) in pattern_ratios.items():
            if not (min_ratio <= ratios[key] <= max_ratio):
                return False
        return True

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
            
        # Dodanie wzorców harmonicznych i poziomów Fibonacciego
        pattern_columns = [col for col in df.columns if col.startswith('pattern_') and col.endswith('_price')]
        forming_pattern_columns = [col for col in df.columns if col.startswith('forming_pattern_') and col.endswith('_price')]
        fib_columns = [col for col in df.columns if col.startswith('fib_')]
        
        logger.info(f"Znalezione kolumny wzorców: {len(pattern_columns)} zwykłych, {len(forming_pattern_columns)} forming")
        logger.info(f"Znalezione kolumny Fibonacci: {len(fib_columns)}")
        logger.debug(f"Szczegóły wzorców: {pattern_columns + forming_pattern_columns}")
        logger.debug(f"Szczegóły Fibonacci: {fib_columns}")
        
        # Dodaj punkty wzorców harmonicznych jako scatter plots
        if show_patterns and (pattern_columns or forming_pattern_columns):
            # Kolory dla punktów wzorców harmonicznych
            point_colors = {
                'X': 'red',
                'A': 'blue', 
                'B': 'green',
                'C': 'orange',
                'D': 'purple'
            }
            
            # Kombinuj wszystkie kolumny wzorców (zwykłe + forming)
            all_pattern_columns = pattern_columns + forming_pattern_columns
            
            # Grupuj punkty według wzorców
            pattern_groups = {}
            for col in all_pattern_columns:
                # Wyciągnij nazwę punktu (X, A, B, C, D)
                parts = col.split('_')
                if len(parts) >= 3:
                    point_name = parts[-2]  # np. 'X', 'A', 'B', 'C', 'D'
                    if point_name not in pattern_groups:
                        pattern_groups[point_name] = []
                    pattern_groups[point_name].append(col)
            
            # Dodaj każdy typ punktu jako osobny scatter plot
            for point_name, columns in pattern_groups.items():
                color = point_colors.get(point_name, 'black')
                for col in columns:
                    # Utwórz series tylko z wartościami nie-NaN i nie-zero
                    series = df[col].replace(0, np.nan).dropna()
                    if not series.empty:
                        # Różne markery dla forming vs zwykłych wzorców
                        marker = '^' if col.startswith('forming_') else 'o'
                        alpha = 0.6 if col.startswith('forming_') else 0.8
                        size = 120 if col.startswith('forming_') else 150
                        
                        add_plots.append(
                            mpf.make_addplot(
                                df[col].replace(0, np.nan),  # Zastąp 0 na NaN żeby nie rysować
                                type='scatter',
                                marker=marker,
                                markersize=size,
                                color=color,
                                alpha=alpha
                            )
                        )
                        pattern_type = "forming" if col.startswith('forming_') else "formed"
                        logger.debug(f"Dodano punkt {point_name} ({pattern_type}) w kolorze {color}")
                
        # Dodaj poziomy Fibonacciego jako linie poziome
        if show_fibonacci and fib_columns:
            # Kolory dla różnych typów poziomów Fibonacci
            fib_type_colors = {
                'ret': ['#FFD700', '#FF8C00', '#FF6347', '#FF1493', '#9932CC'],  # Retracement - złoto do fioletu
                'ext': ['#00CED1', '#00FF7F', '#32CD32', '#228B22'],            # Extension - turkus do zieleni
                'target': ['#FF4500', '#FF6347', '#FF7F50', '#FFA07A']          # Target - czerwono-pomarańczowe
            }
            
            # Grupuj poziomy według typu
            fib_groups = {'ret': [], 'ext': [], 'target': []}
            for col in fib_columns:
                if 'ret_' in col:
                    fib_groups['ret'].append(col)
                elif 'ext_' in col:
                    fib_groups['ext'].append(col)
                elif 'target_' in col:
                    fib_groups['target'].append(col)
            
            # Rysuj każdy typ poziomów
            for fib_type, columns in fib_groups.items():
                colors = fib_type_colors.get(fib_type, ['gray'])
                linestyle = '--' if fib_type == 'ret' else (':' if fib_type == 'ext' else '-')
                alpha = 0.6 if fib_type == 'ret' else (0.5 if fib_type == 'ext' else 0.8)
                
                for i, col in enumerate(columns):
                    color = colors[i % len(colors)]
                    # Utwórz series z poziomem Fibonacciego - tylko dla niepustych wartości
                    fib_level = df[col].replace(0, np.nan).dropna()
                    if not fib_level.empty:
                        # Wypełnij całą serię tym samym poziomem
                        fib_series = pd.Series(fib_level.iloc[0], index=df.index)
                        add_plots.append(
                            mpf.make_addplot(
                                fib_series,
                                type='line',
                                color=color,
                                alpha=alpha,
                                linestyle=linestyle,
                                width=1.5 if fib_type == 'target' else 1
                            )
                        )
                        logger.debug(f"Dodano poziom {fib_type} Fibonacci {col} = {fib_level.iloc[0]:.2f} w kolorze {color}")
        
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
        
        # Podsumowanie tego co zostało narysowane
        total_indicators = sum([
            1 if show_rsi and 'rsi' in df.columns else 0,
            1 if show_macd and all(col in df.columns for col in ['macd', 'signal']) else 0,
            1 if show_obv and 'obv' in df.columns else 0
        ])
        
        total_patterns = len(pattern_columns) + len(forming_pattern_columns) if show_patterns else 0
        total_fib_levels = len(fib_columns) if show_fibonacci else 0
        
        logger.info(f"Wykres wygenerowany: {total_indicators} wskaźników, {total_patterns} punktów wzorców, {total_fib_levels} poziomów Fibonacci")
        
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
