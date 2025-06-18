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
            
            # Konwertuj timestampy na int jeśli są pandas Timestamp
            def convert_timestamp(ts):
                if hasattr(ts, 'timestamp'):
                    # pandas Timestamp
                    return int(ts.timestamp() * 1000)
                elif isinstance(ts, (int, float)):
                    # już w formacie timestamp
                    return int(ts)
                else:
                    # nieznany typ, spróbuj konwersji
                    return int(ts)
            
            # Konwertuj x_points na timestampy
            x_timestamps = [convert_timestamp(x) for x in x_points]
            
            # Konwertuj punkty na nasz format w zależności od typu wzorca
            if len(y_points) >= 5:
                # Wzorzec XABCD (5 punktów)
                xabcd_points = {
                    "X": {"price": y_points[0], "time": x_timestamps[0]},
                    "A": {"price": y_points[1], "time": x_timestamps[1]},
                    "B": {"price": y_points[2], "time": x_timestamps[2]},
                    "C": {"price": y_points[3], "time": x_timestamps[3]},
                    "D": {"price": y_points[4], "time": x_timestamps[4]}
                }
                pattern_name = pattern.name
            elif len(y_points) == 4:
                # Wzorzec ABCD (4 punkty)
                xabcd_points = {
                    "X": {"price": y_points[0], "time": x_timestamps[0]},  # A jako X
                    "A": {"price": y_points[1], "time": x_timestamps[1]},  # B jako A
                    "B": {"price": y_points[2], "time": x_timestamps[2]},  # C jako B
                    "C": {"price": y_points[3], "time": x_timestamps[3]},  # D jako C
                    "D": {"price": y_points[3], "time": x_timestamps[3]}   # D jako D (ten sam punkt)
                }
                pattern_name = f"ABCD-{pattern.name}"
            elif len(y_points) == 3:
                # Wzorzec ABC (3 punkty)
                xabcd_points = {
                    "X": {"price": y_points[0], "time": x_timestamps[0]},  # A jako X
                    "A": {"price": y_points[1], "time": x_timestamps[1]},  # B jako A
                    "B": {"price": y_points[2], "time": x_timestamps[2]},  # C jako B
                    "C": {"price": y_points[2], "time": x_timestamps[2]},  # C jako C (ten sam punkt)
                    "D": {"price": y_points[2], "time": x_timestamps[2]}   # C jako D (ten sam punkt)
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
    ) -> List[HarmonicPattern]:
        """
        Oblicza formacje harmoniczne XABCD używając biblioteki pyharmonics.
        Implementacja bazująca na algorytmie pyharmonics z optymalizacją O(n²/2).
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            tolerance: Tolerancja dla wzorca (domyślnie 10%)
            min_quality: Minimalna jakość wzorca (0-1)
            
        Returns:
            Lista znalezionych formacji harmonicznych
        """
        if not PYHARMONICS_AVAILABLE:
            logger.error("pyharmonics nie jest dostępne. Zainstaluj: pip install pyharmonics")
            return []
        
        if len(klines) < min_points:
            return []

        try:
            # Konwertuj dane na DataFrame wymagany przez pyharmonics
            df = cls._convert_klines_to_dataframe(klines)
            
            # Inicjalizuj Technicals z pyharmonics
            # Używamy symbolu BTCUSDT jako domyślnego
            technicals = Technicals(df, 'BTCUSDT', '1w', peak_spacing=20)
            
            # Wykonaj wyszukiwanie wzorców
            harmonic_search = HarmonicSearch(technicals)
            harmonic_search.search()
            
            # Pobierz wszystkie wzorce
            patterns = harmonic_search.get_patterns()
            
            logger.info(f"Znaleziono wzorce: {list(patterns.keys()) if patterns else 'brak'}")
            
            # Konwertuj wzorce XABCD na nasz format
            harmonic_patterns = []
            
            # Sprawdź wzorce XABCD
            if hasattr(harmonic_search, 'XABCD') and harmonic_search.XABCD in patterns:
                logger.info(f"Przetwarzanie {len(patterns[harmonic_search.XABCD])} wzorców XABCD")
                for pattern in patterns[harmonic_search.XABCD]:
                    harmonic_pattern = cls._convert_pyharmonics_pattern(pattern, klines)
                    if harmonic_pattern is not None:
                        harmonic_patterns.append(harmonic_pattern)
            
            # Sprawdź wzorce ABCD
            if hasattr(harmonic_search, 'ABCD') and harmonic_search.ABCD in patterns:
                logger.info(f"Przetwarzanie {len(patterns[harmonic_search.ABCD])} wzorców ABCD")
                for pattern in patterns[harmonic_search.ABCD]:
                    harmonic_pattern = cls._convert_pyharmonics_pattern(pattern, klines)
                    if harmonic_pattern is not None:
                        harmonic_patterns.append(harmonic_pattern)
            
            # Sprawdź wzorce ABC
            if hasattr(harmonic_search, 'ABC') and harmonic_search.ABC in patterns:
                logger.info(f"Przetwarzanie {len(patterns[harmonic_search.ABC])} wzorców ABC")
                for pattern in patterns[harmonic_search.ABC]:
                    logger.debug(f"Wzorzec ABC: nazwa={pattern.name}, typ={type(pattern.name)}")
                    harmonic_pattern = cls._convert_pyharmonics_pattern(pattern, klines)
                    if harmonic_pattern is not None:
                        harmonic_patterns.append(harmonic_pattern)
                        logger.debug(f"Skonwertowano wzorzec: {harmonic_pattern.name}")
            
            logger.info(f"Pomyślnie skonwertowano {len(harmonic_patterns)} wzorców")
            
            return harmonic_patterns
            
        except Exception as e:
            logger.error(f"Błąd podczas wykrywania wzorców harmonicznych: {e}")
            return []

    @classmethod
    def calculate_harmonic_patterns_forming(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5
    ) -> List[HarmonicPattern]:
        """
        Oblicza wzorce harmoniczne w trakcie formowania się (forming patterns).
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            
        Returns:
            Lista wzorców w trakcie formowania się
        """
        if not PYHARMONICS_AVAILABLE:
            logger.error("pyharmonics nie jest dostępne. Zainstaluj: pip install pyharmonics")
            return []
        
        if len(klines) < min_points:
            return []

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
            
            # Konwertuj wzorce na nasz format
            harmonic_patterns = []
            
            # Sprawdź wszystkie typy wzorców
            for pattern_type in patterns:
                for pattern in patterns[pattern_type]:
                    harmonic_pattern = cls._convert_pyharmonics_pattern(pattern, klines)
                    if harmonic_pattern is not None:
                        harmonic_patterns.append(harmonic_pattern)
            
            return harmonic_patterns
            
        except Exception as e:
            logger.error(f"Błąd podczas wykrywania wzorców w trakcie formowania: {e}")
            return []

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
    ) -> List[Dict[str, Union[HarmonicPattern, FibonacciLevels]]]:
        """
        Oblicza formacje harmoniczne XABCD wraz z poziomami Fibonacciego dla każdego wzorca.
        Poziomy Fibonacciego są obliczane od najwyższego do najniższego punktu w zakresie cenowym.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            
        Returns:
            Lista słowników zawierających wzorzec harmoniczny i odpowiadające mu poziomy Fibonacciego
        """
        # Znajdź wzorce harmoniczne
        patterns = cls.calculate_harmonic_patterns(klines)
        results = []
        
        for pattern in patterns:
            # Pobierz wszystkie ceny z wzorca
            prices = list(pattern.xabcd_points.values())
            
            # Znajdź najwyższą i najniższą cenę
            max_price = max(prices)
            min_price = min(prices)
            
            # Określ kierunek trendu na podstawie wzorca
            is_uptrend = pattern.direction == "bullish"
            
            # Oblicz poziomy Fibonacciego
            fib_levels = cls.calculate_fibonacci_levels(
                start_price=max_price if is_uptrend else min_price,
                end_price=min_price if is_uptrend else max_price,
                is_uptrend=is_uptrend
            )
            
            # Dodaj wynik do listy
            results.append({
                "pattern": pattern,
                "fibonacci_levels": fib_levels
            })
            
        return results

    @classmethod
    def create_candlestick_chart(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        save_path: Optional[str] = None,
        title: str = "Wykres świecowy",
        show_harmonic_patterns: bool = True,
        harmonic_patterns: Optional[List[HarmonicPattern]] = None
    ) -> str:
        """
        Tworzy wykres świecowy z dodatkowymi wskaźnikami technicznymi na podstawie dostępnych danych.
        
        Args:
            klines: Lista świeczek zawierająca dane OHLCV oraz opcjonalnie wskaźniki techniczne
            save_path: Opcjonalna ścieżka do zapisu wykresu
            title: Tytuł wykresu
            show_harmonic_patterns: Czy pokazać wzorce harmoniczne na wykresie
            harmonic_patterns: Lista wzorców harmonicznych do narysowania
            
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
            if col != 'volume':  # volume może być NaN
                # Usuń wiersze z NaN dla kolumn cenowych
                df = df.dropna(subset=[col])
            else:
                # Dla volume zastąp NaN zerami
                df[col] = df[col].fillna(0)
        
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
        if 'rsi' in df.columns:
            add_plots.append(
                mpf.make_addplot(df['rsi'], panel=panel, color='blue', title='RSI')
            )
            panel += 1
            
        if all(col in df.columns for col in ['macd', 'signal']):
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
            
        if 'obv' in df.columns:
            add_plots.append(
                mpf.make_addplot(df['obv'], panel=panel, color='purple', title='OBV')
            )
            panel += 1
            
        # Dodanie wzorców harmonicznych i poziomów Fibonacciego
        pattern_columns = [col for col in df.columns if col.startswith('pattern_') and col.endswith('_price')]
        fib_columns = [col for col in df.columns if col.startswith('fib_')]
        
        logger.debug(f"Znalezione kolumny wzorców: {pattern_columns}")
        logger.debug(f"Znalezione kolumny Fibonacci: {fib_columns}")
        
        # Dodaj punkty wzorców harmonicznych jako scatter plots
        if pattern_columns:
            # Grupuj punkty według wzorców
            pattern_groups = {}
            for col in pattern_columns:
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
                    # Utwórz series tylko z wartościami nie-NaN
                    series = df[col].dropna()
                    if not series.empty:
                        add_plots.append(
                            mpf.make_addplot(
                                df[col],
                                type='scatter',
                                marker='o',
                                markersize=150,
                                color=color,
                                alpha=0.8
                            )
                        )
                        logger.debug(f"Dodano punkt {point_name} ({col}) w kolorze {color}")
                
        # Dodaj poziomy Fibonacciego jako linie poziome
        if fib_columns:
            fib_colors = ['orange', 'yellow', 'cyan', 'magenta', 'brown']
            for i, col in enumerate(fib_columns):
                color = fib_colors[i % len(fib_colors)]
                # Utwórz series z poziomem Fibonacciego dla całego zakresu
                fib_level = df[col].dropna()
                if not fib_level.empty:
                    # Wypełnij całą serię tym samym poziomem
                    fib_series = pd.Series(fib_level.iloc[0], index=df.index)
                    add_plots.append(
                        mpf.make_addplot(
                            fib_series,
                            type='line',
                            color=color,
                            alpha=0.6,
                            linestyle='--',
                            width=1
                        )
                    )
                    logger.debug(f"Dodano poziom Fibonacci {col} = {fib_level.iloc[0]} w kolorze {color}")
        
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
        
        # Dodaj linie łączące punkty wzorców harmonicznych jeśli dostępne
        if show_harmonic_patterns and harmonic_patterns:
            main_ax = axes[0] if isinstance(axes, list) else axes
            
            for pattern in harmonic_patterns:
                try:
                    # Pobierz punkty wzorca
                    points = pattern.xabcd_points
                    
                    # Konwertuj timestampy na daty
                    dates = []
                    prices = []
                    
                    for point_name in ['X', 'A', 'B', 'C', 'D']:
                        if point_name in points:
                            timestamp = points[point_name]['time']
                            price = points[point_name]['price']
                            
                            # Konwertuj timestamp na datetime
                            if isinstance(timestamp, (int, float)):
                                date = pd.to_datetime(timestamp, unit='ms')
                            else:
                                date = pd.to_datetime(timestamp)
                            
                            dates.append(date)
                            prices.append(price)
                    
                    # Narysuj linie łączące punkty wzorca
                    if len(dates) >= 2:
                        # Narysuj linie łączące punkty
                        main_ax.plot(dates, prices, 
                                   color='blue', 
                                   linewidth=2, 
                                   alpha=0.7,
                                   linestyle='-')
                        
                        # Narysuj punkty w różnych kolorach
                        point_colors = {
                            'X': 'red',
                            'A': 'blue', 
                            'B': 'green',
                            'C': 'orange',
                            'D': 'purple'
                        }
                        
                        # Dodaj kolorowe punkty
                        for i, (date, price) in enumerate(zip(dates, prices)):
                            point_names = ['X', 'A', 'B', 'C', 'D']
                            if i < len(point_names):
                                point_name = point_names[i]
                                color = point_colors.get(point_name, 'black')
                                main_ax.scatter(date, price, 
                                              color=color, 
                                              s=100, 
                                              alpha=0.9,
                                              zorder=5,
                                              edgecolors='white',
                                              linewidth=2)
                                
                                # Dodaj etykietę punktu
                                main_ax.text(date, price, 
                                           f' {point_name}',
                                           fontsize=8,
                                           ha='left',
                                           va='bottom',
                                           color=color,
                                           weight='bold')
                        
                        # Dodaj etykietę wzorca
                        if dates and prices:
                            main_ax.text(dates[-1], prices[-1], 
                                       f' {pattern.name}',
                                       fontsize=10,
                                       ha='left',
                                       va='top',
                                       bbox=dict(boxstyle="round,pad=0.3", 
                                               facecolor='lightblue', 
                                               alpha=0.8,
                                               edgecolor='blue'))
                    
                    # Dodaj poziomy Fibonacciego jako linie poziome
                    if pattern.fibonacci_levels:
                        # Pobierz zakres dat dla linii poziomych
                        x_min = df.index.min()
                        x_max = df.index.max()
                        
                        # Kolory dla poziomów retracementu
                        retracement_colors = {
                            '0.236': '#FFD700',  # złoty
                            '0.382': '#FF8C00',  # pomarańczowy
                            '0.5': '#FF6347',    # czerwony
                            '0.618': '#FF1493',  # różowy
                            '0.786': '#9932CC'   # fioletowy
                        }
                        
                        # Rysuj poziomy retracementu
                        for level_name, level_price in pattern.fibonacci_levels.retracement.items():
                            color = retracement_colors.get(level_name, '#808080')
                            main_ax.axhline(y=level_price, 
                                          color=color, 
                                          linestyle='--', 
                                          alpha=0.7,
                                          linewidth=1.5)
                            
                            # Dodaj etykietę poziomu
                            main_ax.text(x_max, level_price, 
                                       f' Fib {level_name} ({level_price:.0f})',
                                       fontsize=8,
                                       ha='left',
                                       va='center',
                                       color=color,
                                       bbox=dict(boxstyle="round,pad=0.2", 
                                               facecolor='white', 
                                               alpha=0.8,
                                               edgecolor=color))
                        
                        # Kolory dla poziomów extension
                        extension_colors = {
                            '1.272': '#00CED1',  # turkusowy
                            '1.618': '#00FF7F',  # zielony
                            '2.0': '#32CD32',    # limonkowy
                            '2.618': '#228B22'   # ciemnozielony
                        }
                        
                        # Rysuj poziomy extension
                        for level_name, level_price in pattern.fibonacci_levels.extension.items():
                            color = extension_colors.get(level_name, '#696969')
                            main_ax.axhline(y=level_price, 
                                          color=color, 
                                          linestyle=':', 
                                          alpha=0.7,
                                          linewidth=1.5)
                            
                            # Dodaj etykietę poziomu extension
                            main_ax.text(x_max, level_price, 
                                       f' Ext {level_name} ({level_price:.0f})',
                                       fontsize=8,
                                       ha='left',
                                       va='center',
                                       color=color,
                                       bbox=dict(boxstyle="round,pad=0.2", 
                                               facecolor='white', 
                                               alpha=0.8,
                                               edgecolor=color))
                        
                        # Kolory dla targetów
                        target_colors = {
                            'T1': '#FF4500',  # czerwono-pomarańczowy
                            'T2': '#FF6347',  # pomidorowy
                            'T3': '#FF7F50',  # koralowy
                            'T4': '#FFA07A'   # łososiowy
                        }
                        
                        # Rysuj targety
                        for target_name, target_price in pattern.fibonacci_levels.targets.items():
                            color = target_colors.get(target_name, '#B22222')
                            main_ax.axhline(y=target_price, 
                                          color=color, 
                                          linestyle='-', 
                                          alpha=0.8,
                                          linewidth=2)
                            
                            # Dodaj etykietę targetu
                            main_ax.text(x_min, target_price, 
                                       f'{target_name} ({target_price:.0f}) ',
                                       fontsize=9,
                                       ha='right',
                                       va='center',
                                       color=color,
                                       weight='bold',
                                       bbox=dict(boxstyle="round,pad=0.3", 
                                               facecolor='yellow', 
                                               alpha=0.9,
                                               edgecolor=color))
                
                except Exception as e:
                    logger.warning(f"Nie udało się narysować wzorca {pattern.name}: {e}")
        
        # Zapisywanie wykresu
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        
        # Konwersja do base64
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode('utf-8') 
