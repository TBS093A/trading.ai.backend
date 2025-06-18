import numpy as np
from typing import List, Dict, Union, Optional, Tuple
import logging
from dataclasses import dataclass
import mplfinance as mpf
import pandas as pd
import base64
from io import BytesIO
import matplotlib.pyplot as plt

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
    xabcd_points: Dict[str, float] # Punkty XABCD z cenami
    fibonacci_levels: FibonacciLevels
    direction: str                 # "bullish" lub "bearish"
    completion_zone: Tuple[float, float]  # Zakres cenowy dla zakończenia formacji

class TechnicalAnalysis:
    # Stałe dla wzorców harmonicznych
    PATTERN_RATIOS = {
        "Gartley": {
            "AB": (0.618, 0.786),  # AB powinno być 61.8% - 78.6% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (1.272, 1.618),  # CD powinno być 127.2% - 161.8% BC
            "AD": (0.786, 0.786)   # AD powinno być 78.6% XA
        },
        "Butterfly": {
            "AB": (0.786, 0.786),  # AB powinno być 78.6% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (1.618, 2.618),  # CD powinno być 161.8% - 261.8% BC
            "AD": (1.272, 1.618)   # AD powinno być 127.2% - 161.8% XA
        },
        "Bat": {
            "AB": (0.382, 0.5),    # AB powinno być 38.2% - 50% XA
            "BC": (0.382, 0.886),  # BC powinno być 38.2% - 88.6% AB
            "CD": (1.618, 2.618),  # CD powinno być 161.8% - 261.8% BC
            "AD": (0.886, 0.886)   # AD powinno być 88.6% XA
        }
    }

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
    def calculate_harmonic_patterns(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        min_points: int = 5
    ) -> List[HarmonicPattern]:
        """
        Oblicza formacje harmoniczne XABCD na podstawie danych świeczek.
        
        Args:
            klines: Lista świeczek w formacie zwracanym przez _get_klines
            min_points: Minimalna liczba punktów potrzebna do identyfikacji formacji
            
        Returns:
            Lista znalezionych formacji harmonicznych
        """
        if len(klines) < min_points:
            return []

        patterns = []
        closes = [float(k['close']) for k in klines]
        highs = [float(k['high']) for k in klines]
        lows = [float(k['low']) for k in klines]

        # Znajdź punkty zwrotne
        peaks, troughs = cls._find_swing_points(highs, lows)
        
        # Połącz punkty zwrotne w kolejności
        swing_points = sorted(peaks + troughs)
        
        # Sprawdź każdą możliwą kombinację 5 punktów
        for i in range(len(swing_points) - 4):
            points = swing_points[i:i+5]
            
            # Pobierz ceny dla punktów XABCD
            x_price = highs[points[0]] if points[0] in peaks else lows[points[0]]
            a_price = lows[points[1]] if points[1] in troughs else highs[points[1]]
            b_price = highs[points[2]] if points[2] in peaks else lows[points[2]]
            c_price = lows[points[3]] if points[3] in troughs else highs[points[3]]
            d_price = highs[points[4]] if points[4] in peaks else lows[points[4]]
            
            # Oblicz stosunki Fibonacciego
            ratios = {
                "AB": cls._calculate_ratio(x_price, a_price, b_price),
                "BC": cls._calculate_ratio(a_price, b_price, c_price),
                "CD": cls._calculate_ratio(b_price, c_price, d_price),
                "AD": cls._calculate_ratio(x_price, a_price, d_price)
            }
            
            # Sprawdź każdy wzorzec
            for pattern_name in cls.PATTERN_RATIOS.keys():
                if cls._is_pattern_valid(pattern_name, ratios):
                    # Określ kierunek wzorca
                    direction = "bullish" if x_price > a_price else "bearish"
                    
                    # Oblicz poziomy Fibonacciego
                    fib_levels = cls.calculate_fibonacci_levels(
                        x_price,
                        d_price,
                        direction == "bullish"
                    )
                    
                    # Oblicz strefę zakończenia
                    completion_zone = (
                        d_price * 0.99,  # 1% poniżej punktu D
                        d_price * 1.01   # 1% powyżej punktu D
                    )
                    
                    # Utwórz wzorzec
                    pattern = HarmonicPattern(
                        name=pattern_name,
                        xabcd_points={
                            "X": x_price,
                            "A": a_price,
                            "B": b_price,
                            "C": c_price,
                            "D": d_price
                        },
                        fibonacci_levels=fib_levels,
                        direction=direction,
                        completion_zone=completion_zone
                    )
                    
                    patterns.append(pattern)
        
        return patterns

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
        title: str = "Wykres świecowy"
    ) -> str:
        """
        Tworzy wykres świecowy z dodatkowymi wskaźnikami technicznymi na podstawie dostępnych danych.
        
        Args:
            klines: Lista świeczek zawierająca dane OHLCV oraz opcjonalnie wskaźniki techniczne
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
        pattern_columns = [col for col in df.columns if col.startswith('pattern_')]
        fib_columns = [col for col in df.columns if col.startswith('fib_')]
        
        if pattern_columns:
            for col in pattern_columns:
                add_plots.append(
                    mpf.make_addplot(
                        df[col],
                        type='scatter',
                        marker='o',
                        markersize=100,
                        color='blue'
                    )
                )
                
        if fib_columns:
            for col in fib_columns:
                add_plots.append(
                    mpf.make_addplot(
                        df[col],
                        type='scatter',
                        marker='_',
                        markersize=100,
                        color='orange'
                    )
                )
        
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
        
        # Zapisywanie wykresu
        if save_path:
            plt.savefig(save_path)
        
        # Konwersja do base64
        buf = BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)
        return base64.b64encode(buf.getvalue()).decode('utf-8') 
        return base64.b64encode(buf.getvalue()).decode('utf-8') 