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


class TechnicalAnalysis:

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
    def create_candlestick_chart(
        cls,
        klines: List[Dict[str, Union[int, float, str]]],
        save_path: Optional[str] = None,
        title: str = "Wykres świecowy",
        show_fibonacci: bool = False, # Show general single fibonacci of patterns(from max / min to max / min point) 
        show_all_fibo_targets: bool = False, # Show all fibonacci PRZ (Potential Reversal Zone), TP (Take Profit), SL (Stop Loss)
        show_all_fibonacci_levels: bool = True, # Show crucial fibonacci levels for each point pair in patterns (need to set which should be mapped with show_all_retracement_levels & show_all_extension_levels)
        show_all_retracement_levels: bool = True, # Shows all point pairs retracement fibonacci levels
        show_all_extension_levels: bool = True, # Shows all point pairs extension fibonacci levels
        # TODO show_all_median_line_andrews_pitchfork: bool = True, # Shows all point pairs median line andrews pitchfork levels
        # TODO show_all_alternate_price_projection: bool = True, # Shows all point pairs alternate price projection levels
        show_patterns: bool = True, # Show patterns on chart
        show_rsi: bool = True, # Show RSI on chart
        show_macd: bool = True, # Show MACD on chart
        show_obv: bool = True, # Show OBV on chart
    ) -> str:
        """
        Tworzy wykres świecowy z dodatkowymi wskaźnikami technicznymi oraz wzorcami harmonicznymi
        używając nowej architektury Strategy Pattern.
        
        Args:
            klines: Lista świeczek zawierająca dane OHLCV, wskaźniki techniczne oraz punkty wzorców harmonicznych
            save_path: Opcjonalna ścieżka do zapisu wykresu
            title: Tytuł wykresu
            show_*: Parametry kontrolujące wyświetlanie poszczególnych elementów
            
        Returns:
            Base64 string z obrazkiem wykresu
        """
        # Utwórz instancję głównej klasy TechnicalAnalysis
        ta = cls()
        
        # Określ które wskaźniki mają być włączone
        enabled_indicators = []
        if show_rsi:
            enabled_indicators.append('IndicatorRSI')
        if show_macd:
            enabled_indicators.append('IndicatorMACD')
        if show_obv:
            enabled_indicators.append('IndicatorOBV')
            
        # Określ które obiekty analizy technicznej mają być włączone
        enabled_objects = []
        if show_fibonacci:
            enabled_objects.append('Fibonacci')
        if show_all_fibo_targets:
            enabled_objects.append('AllTargetsFibonacci')
        if show_all_fibonacci_levels:
            enabled_objects.append('AllFibonacciLevels')
        if show_patterns:
            enabled_objects.append('HarmonicPatterns')
        # TODO: Dodaj pozostałe obiekty gdy będą zaimplementowane
        # if show_all_median_line_andrews_pitchfork:
        #     enabled_objects.append('AllMedianLineAndrewsPitchfork')
        # if show_all_alternate_price_projection:
        #     enabled_objects.append('AllAlternatePriceProjection')
        
        # Oblicz wskaźniki i obiekty analizy technicznej
        ta.calculate(
            klines, 
            enabled_indicators=enabled_indicators,
            enabled_objects=enabled_objects,
            show_fibonacci=show_fibonacci,
            show_all_fibo_targets=show_all_fibo_targets,
            show_all_fibonacci_levels=show_all_fibonacci_levels,
            show_all_retracement_levels=show_all_retracement_levels,
            show_all_extension_levels=show_all_extension_levels,
            show_patterns=show_patterns,
            show_rsi=show_rsi,
            show_macd=show_macd,
            show_obv=show_obv
        )
        
        # Utwórz wykres używając nowej metody
        return ta.draw_candlestick_chart(
            klines,
            save_path=save_path,
            title=title,
            show_fibonacci=show_fibonacci,
            show_all_fibo_targets=show_all_fibo_targets,
            show_all_fibonacci_levels=show_all_fibonacci_levels,
            show_all_retracement_levels=show_all_retracement_levels,
            show_all_extension_levels=show_all_extension_levels,
            show_patterns=show_patterns,
            show_rsi=show_rsi,
            show_macd=show_macd,
            show_obv=show_obv
                 )
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
                    
                    # Rysuj poziomy Fibonacciego i/lub targety jeśli włączone
                    if (show_fibonacci or show_all_fibo_targets or show_all_fibonacci_levels) and fibonacci_data:
                        cls._draw_fibonacci_lines_with_labels(
                            main_ax, fibonacci_data, pattern_groups, klines, 
                            dynamic_font_size_fibo_labels, df, show_all_fibo_targets, show_fibonacci, show_all_fibonacci_levels,
                            show_all_retracement_levels, show_all_extension_levels
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