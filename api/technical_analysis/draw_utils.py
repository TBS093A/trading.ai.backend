import logging
import traceback
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)


class DrawUtils:
    """Klasa zawierająca narzędzia do rysowania elementów na wykresach"""
    
    @staticmethod
    def draw_pattern_labels_in_padding(
        main_ax,
        pattern_labels_for_padding: list,
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
                DrawUtils.draw_labels_in_zone(
                    main_ax, top_labels, top_padding_center, 
                    x_min, x_max, dynamic_font_size_labels, 'top'
                )
            
            # Rysuj etykiety w dolnej strefie paddingu
            if bottom_labels:
                DrawUtils.draw_labels_in_zone(
                    main_ax, bottom_labels, bottom_padding_center, 
                    x_min, x_max, dynamic_font_size_labels, 'bottom'
                )
                
        except Exception as e:
            logger.error(f"Błąd podczas rysowania etykiet w paddingu: {e}")
            logger.error(traceback.format_exc())
    
    @staticmethod
    def draw_labels_in_zone(
        main_ax,
        labels: list,
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
    
    @staticmethod
    def apply_scaled_font_to_axes(
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
            else:
                # Pojedyncza oś
                if hasattr(axes, 'tick_params'):
                    axes.tick_params(axis='x', labelsize=dynamic_font_size_axes)
                    axes.tick_params(axis='y', labelsize=dynamic_font_size_axes)
                    
                    # ylabel
                    if hasattr(axes, 'set_ylabel'):
                        current_ylabel = axes.get_ylabel()
                        if current_ylabel:
                            axes.set_ylabel(current_ylabel, fontsize=dynamic_font_size_axes)
                    
                    # xlabel
                    if hasattr(axes, 'set_xlabel'):
                        current_xlabel = axes.get_xlabel()
                        if current_xlabel:
                            axes.set_xlabel(current_xlabel, fontsize=dynamic_font_size_axes)
            
            logger.info(f"Pomyślnie zastosowano skalowaną czcionkę {dynamic_font_size_axes}px do wszystkich osi")
            
        except Exception as e:
            logger.error(f"Błąd podczas stosowania skalowanej czcionki do osi: {e}")
            logger.error(traceback.format_exc())
    
    @staticmethod
    def draw_fibonacci_lines_with_labels(
        main_ax,
        fibonacci_data: list,
        pattern_groups: dict,
        klines: list,
        dynamic_font_size_fibo_labels: int,
        df: pd.DataFrame,
        show_all_fibo_targets: bool = True,
        show_fibonacci: bool = True,
        show_all_fibonacci_levels: bool = False,
        show_all_retracement_levels: bool = True,
        show_all_extension_levels: bool = True
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
            show_all_fibo_targets: Czy rysować targety (PRZ, TP, SL)
            show_fibonacci: Czy rysować standardowe poziomy Fibonacci
            show_all_fibonacci_levels: Czy rysować wszystkie poziomy z all_fibo
            show_all_retracement_levels: Filtr dla zniesień wewnętrznych
            show_all_extension_levels: Filtr dla zniesień zewnętrznych
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
            
            # Oblicz dynamiczną wielkość czcionki dla etykiet na osi Y
            base_font_fibo_y_labels = 6  # Wielkość bazowa dla etykiet osi Y
            dynamic_font_fibo_y_labels = int(base_font_fibo_y_labels * (dynamic_font_size_fibo_labels / 6))  # Skalowanie względem Fibonacci
            
            if show_fibonacci:
                logger.info(f"Rysowanie {len(fibonacci_data)} poziomów Fibonacci jako linie z etykietami")
            else:
                logger.info(f"Poziomy Fibonacci pomijane (show_fibonacci=False), rysowanie tylko targetów")
            
            if show_all_fibonacci_levels:
                logger.info(f"Rysowanie wszystkich poziomów z all_fibo ze standardowymi etykietami (czcionka: {dynamic_font_fibo_y_labels}px)")
            
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
                    
                    # Przetwórz każdy typ poziomów Fibonacciego (tylko jeśli show_fibonacci=True)
                    for fib_type, levels in fibonacci.items():
                        # Pomijaj rysowanie linii Fibonacci jeśli show_fibonacci=False
                        if fib_type in ['retracement', 'extension', 'targets'] and not show_fibonacci:
                            continue
                            
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
            
            if show_fibonacci:
                logger.info(f"Pomyślnie narysowano linie Fibonacci dla {len(processed_patterns)} wzorców")
            else:
                logger.info(f"Linie Fibonacci pominięte dla {len(processed_patterns)} wzorców (show_fibonacci=False)")
            
            # Rysuj wszystkie poziomy z all_fibo jako standardowe linie (jeśli włączone)
            if show_all_fibonacci_levels:
                DrawUtils.draw_all_fibonacci_levels(
                    main_ax, fibonacci_data, pattern_groups, klines, 
                    dynamic_font_fibo_y_labels, df, chart_end_x, x_min, x_max,
                    show_all_retracement_levels, show_all_extension_levels
                )
            
            # Teraz rysuj targety (PRZ, TP, SL) - ponownie iteruj od tyłu po klines (tylko jeśli włączone)
            if show_all_fibo_targets:
                processed_targets = set()  # Żeby uniknąć duplikowania wzorców
                
                # Oblicz dynamiczną wielkość czcionki dla targetów
                base_font_size_fibo_targets_labels = 8
                dynamic_font_size_fibo_targets_labels = int(base_font_size_fibo_targets_labels * (dynamic_font_size_fibo_labels / 6))  # Skalowanie względem Fibonacci
                
                logger.info(f"Rysowanie targetów z czcionką {dynamic_font_size_fibo_targets_labels}px (show_all_fibo_targets=True)")
                
                for kline_idx in range(len(klines) - 1, -1, -1):  # Od końca do początku
                    kline = klines[kline_idx]
                    
                    # Sprawdź czy ta świeca zawiera wzorce z targetami
                    if 'patterns' not in kline:
                        continue
                    
                    for pattern_id, pattern_info in kline['patterns'].items():
                        # Sprawdź czy już przetwarzaliśmy ten wzorzec
                        if pattern_id in processed_targets:
                            continue
                        
                        # Sprawdź czy ten wzorzec ma targety
                        if 'fibonacci' not in pattern_info or 'all_targets' not in pattern_info['fibonacci']:
                            continue
                        
                        all_targets = pattern_info['fibonacci']['all_targets']
                        if not all_targets:
                            continue
                        
                        processed_targets.add(pattern_id)
                        
                        # Znajdź punkt D tego wzorca dla pozycji startowej
                        pattern_group = pattern_groups.get(pattern_id, {})
                        points = pattern_group.get('points', {})
                        d_point = points.get('D')
                        
                        if not d_point:
                            continue
                        
                        start_x = d_point['index']
                        logger.info(f"Rysowanie targetów dla wzorca {pattern_id} od punktu D na świecy {start_x}")
                        
                        # Definiuj kolory dla różnych typów targetów
                        target_colors = {
                            'PRZ': '#FF6B6B',    # Czerwony dla PRZ
                            'TP1': '#4ECDC4',    # Cyan dla TP1
                            'TP2': '#45B7D1',    # Niebieski dla TP2
                            'TP3': '#9B59B6',    # Fioletowy dla TP3
                            'SL': '#FFA07A'      # Łososiowy dla SL
                        }
                        
                        # Rysuj każdy target
                        for target_name, target_data in all_targets.items():
                            target_type = target_data.get('type', 'line')
                            original_description = target_data.get('description', f"{target_name}")
                            description = f"ID: {pattern_id} | {original_description}"
                            color = target_colors.get(target_name, '#FFFFFF')  # Biały fallback
                            
                            if target_type == 'zone':
                                # Rysuj prostokąt dla stref (PRZ)
                                min_price = target_data.get('min_price', 0)
                                max_price = target_data.get('max_price', 0)
                                
                                if min_price > 0 and max_price > 0 and min_price != max_price:
                                    # Rysuj prostokąt od punktu D do końca wykresu
                                    rect_width = chart_end_x - start_x
                                    rect_height = max_price - min_price
                                    
                                    rect = plt.Rectangle(
                                        (start_x, min_price), 
                                        rect_width, 
                                        rect_height,
                                        facecolor=color,
                                        alpha=0.2,  # Transparentny prostokąt
                                        edgecolor=color,
                                        linewidth=1,
                                        zorder=4  # Pod liniami Fibonacci
                                    )
                                    main_ax.add_patch(rect)
                                    
                                    # Dodaj etykietę w lewym górnym rogu prostokątu
                                    label_x = start_x + 2  # Małe przesunięcie od lewej krawędzi
                                    label_y = max_price - (rect_height * 0.1)  # 10% od góry prostokątu
                                    
                                    main_ax.annotate(
                                        description,
                                        (label_x, label_y),
                                        ha='left',
                                        va='top',
                                        fontsize=dynamic_font_size_fibo_targets_labels,
                                        color=color,
                                        alpha=0.9,
                                        bbox=dict(
                                            boxstyle="round,pad=0.2",
                                            facecolor='black',
                                            alpha=0.0,  # Maksymalnie transparentne tło
                                            edgecolor='none'  # Bez borderów
                                        ),
                                        zorder=7  # Nad prostokątem
                                    )
                                    
                                    logger.debug(f"Narysowano prostokąt {target_name} dla wzorca {pattern_id}: {min_price:.6f} - {max_price:.6f}")
                            
                            elif target_type == 'line':
                                # Rysuj linię dla pojedynczych targetów (TP, SL)
                                price = target_data.get('price', 0)
                                
                                if price > 0:
                                    # Rysuj linię od punktu D do końca wykresu
                                    main_ax.plot(
                                        [start_x, chart_end_x], 
                                        [price, price],
                                        color=color,
                                        alpha=0.8,
                                        linestyle='-',
                                        linewidth=2,
                                        zorder=5  # Nad świecami, ale pod wzorcami
                                    )
                                    
                                    # Dodaj etykietę nad lewą górną krawędzią linii
                                    label_x = start_x + 2  # Przesunięcie od początku linii
                                    label_y = price
                                    
                                    main_ax.annotate(
                                        description,
                                        (label_x, label_y),
                                        xytext=(0, 3),  # Małe przesunięcie w górę
                                        textcoords='offset points',
                                        ha='left',
                                        va='bottom',
                                        fontsize=dynamic_font_size_fibo_targets_labels,
                                        color=color,
                                        alpha=0.9,
                                        bbox=dict(
                                            boxstyle="round,pad=0.2",
                                            facecolor='black',
                                            alpha=0.0,  # Maksymalnie transparentne tło
                                            edgecolor='none'  # Bez borderów
                                        ),
                                        zorder=6  # Nad liniami targetów
                                    )
                                    
                                    logger.debug(f"Narysowano linię {target_name} dla wzorca {pattern_id}: {price:.6f}")

                logger.info(f"Pomyślnie narysowano targety dla {len(processed_targets)} wzorców")
            else:
                logger.info(f"Rysowanie targetów pominięte (show_all_fibo_targets=False)")
            
        except Exception as e:
            logger.error(f"Błąd podczas rysowania linii Fibonacci i targetów: {e}")
            logger.error(traceback.format_exc())
    
    @staticmethod
    def draw_all_fibonacci_levels(
        main_ax,
        fibonacci_data: list,
        pattern_groups: dict,
        klines: list,
        dynamic_font_fibo_y_labels: int,
        df: pd.DataFrame,
        chart_end_x: int,
        x_min: float,
        x_max: float,
        show_all_retracement_levels: bool = True,
        show_all_extension_levels: bool = True
    ):
        """
        Rysuje wszystkie poziomy z all_fibo jako standardowe linie z etykietami.
        
        Args:
            main_ax: Główna oś wykresu
            fibonacci_data: Lista danych poziomów Fibonacci
            pattern_groups: Grupy wzorców harmonicznych
            klines: Lista świeczek
            dynamic_font_fibo_y_labels: Wielkość czcionki dla etykiet osi Y
            df: DataFrame z danymi cenowymi
            chart_end_x: Pozycja X końca wykresu
            x_min, x_max: Granice osi X
            show_all_retracement_levels: Filtr dla zniesień wewnętrznych (XA 38.2-78.6%, AB 38.2-88.6%)
            show_all_extension_levels: Filtr dla zniesień zewnętrznych (XA 127.2-161.8%, BC 161.8-261.8%, AB 113-161.8%)
        """
        # Zielone linie dla retracement: 18.6%, 23.6%, 38.2%, 61.8%, 68.5%, 78.6%, 88.6%
        green_retracement = ['0.186', '0.236', '0.382', '0.618', '0.685', '0.786', '0.886']
        # Zielone linie dla extension: 113%, 127.2%, 146%, 161.8%, 223.6%, 261.8%
        green_extension = ['1.13', '1.272', '1.46', '1.618', '2.236', '2.618']
        # Szare linie dla 0% i 100%
        gray_levels = ['0.0', '1.0']
        try:
            # Funkcja do określania koloru na podstawie poziomu Fibonacci
            def get_fibonacci_color(fib_type, level_name):
                if level_name in gray_levels:
                    return '#808080'  # Szary
                elif (fib_type == 'retracement' and level_name in green_retracement) or \
                     (fib_type == 'extension' and level_name in green_extension) or \
                     (fib_type == 'targets' and (level_name in green_retracement or level_name in green_extension)):
                    return '#00FF00'  # Zielony
                else:
                    return '#FFFFFF'  # Biały dla pozostałych
            
            # Funkcja do filtrowania poziomów na podstawie kombinacji punktów i typu
            def should_include_level(combination_name, fib_type, level_name, pattern_type=''):
                """
                Filtruje poziomy Fibonacci według kryteriów użytkownika.
                
                Args:
                    combination_name: Nazwa kombinacji punktów (np. 'XA', 'BC', 'AB')
                    fib_type: Typ poziomy ('retracement', 'extension', 'targets')
                    level_name: Nazwa poziomu (np. '0.382', '1.618')
                    pattern_type: Typ wzorca (np. 'Gartley', 'Bat') - opcjonalny
                    
                Returns:
                    bool: True jeśli poziom powinien być uwzględniony
                """
                try:
                    level_value = float(level_name)
                except ValueError:
                    return False
                
                pat = pattern_type.lower().strip()
                comb = combination_name.upper().strip()
                
                # ---------------------------
                # 1. RETRACEMENT (0‑1.0)
                # ---------------------------
                if fib_type == 'retracement' and show_all_retracement_levels:
                    if comb == 'XA':
                        if pat in ('bat',):
                            return 0.382 <= level_value <= 0.618 or level_value == 0.886
                        elif pat in ('alt bat',):
                            return level_value <= 0.382
                        elif pat in ('gartley',):
                            return 0.618 <= level_value <= 0.786
                        elif pat in ('cypher',):
                            return 0.382 <= level_value <= 0.618
                        elif pat in ('butterfly',):
                            return level_value == 0.786
                        elif pat in ('deep butterfly',):
                            return level_value == 0.886
                        elif pat in ('crab',):
                            return 0.382 <= level_value <= 0.618
                        elif pat in ('deep crab',):
                            return level_value == 0.886
                        # Shark / Deep Shark use >1.0 XA, handled in extension branch
                    elif comb == 'AB':
                        # Wspólny przedział dla większości struktur
                        return 0.382 <= level_value <= 0.886
                    elif comb == 'BC' and pat in ('five-0',):
                        # Five‑0 szuka dokładnie 50 % cofki BC
                        return abs(level_value - 0.50) < 1e-6
                
                # ---------------------------
                # 2. EXTENSION / PROJECTION (>1.0)
                # ---------------------------
                elif fib_type == 'extension' and show_all_extension_levels:
                    if comb == 'XA':
                        if pat in ('butterfly', 'deep butterfly', 'crab', 'deep crab'):
                            return level_value in (1.272, 1.618)
                        elif pat in ('alt bat',):
                            return 1.13 <= level_value <= 1.618 and level_value != 1.272
                        elif pat in ('shark',):
                            return 1.13 <= level_value <= 1.618
                        elif pat in ('deep shark',):
                            return 1.618 <= level_value <= 2.24
                    elif comb == 'BC':
                        if pat in ('bat', 'gartley', 'butterfly'):
                            return 1.618 <= level_value <= 2.618
                        elif pat in ('alt bat',):
                            return 2.0 <= level_value <= 3.0
                        elif pat in ('crab',):
                            return 2.618 <= level_value <= 3.618
                        elif pat in ('deep crab',):
                            return 2.24 <= level_value <= 3.618
                        elif pat in ('shark',):
                            return 1.13 <= level_value <= 1.618
                        elif pat in ('deep shark',):
                            return 1.618 <= level_value <= 2.24
                    elif comb == 'AB':
                        # Klasyczne projekcje AB=CD / external 113‑161.8 %
                        return 1.13 <= level_value <= 1.618
                
                # ---------------------------
                # 3. TARGETS - rekurencyjne wywołanie dla retracement/extension
                # ---------------------------
                elif fib_type == 'targets':
                    if show_all_retracement_levels and level_value < 1.0:
                        return should_include_level(combination_name, 'retracement', level_name, pattern_type)
                    elif show_all_extension_levels and level_value >= 1.0:
                        return should_include_level(combination_name, 'extension', level_name, pattern_type)
                
                # ---------------------------
                # 4. Fallback – nic nie pasuje
                # ---------------------------
                return False
            
            # Zbierz wszystkie poziomy z wszystkich wzorców wraz z nazwami punktów
            all_levels_data = []
            processed_patterns = set()
            
            logger.info(f"Zbieranie poziomów z all_fibo dla standardowych etykiet (retracement: {show_all_retracement_levels}, extension: {show_all_extension_levels})")
            
            for kline_idx in range(len(klines) - 1, -1, -1):  # Od końca do początku
                kline = klines[kline_idx]
                
                if 'patterns' not in kline:
                    continue
                
                for pattern_id, pattern_info in kline['patterns'].items():
                    # Sprawdź czy już przetwarzaliśmy ten wzorzec
                    if pattern_id in processed_patterns:
                        continue
                    
                    # Sprawdź czy ten wzorzec ma all_fibo
                    if 'fibonacci' not in pattern_info or 'all_fibos' not in pattern_info['fibonacci']:
                        continue
                    
                    all_fibos = pattern_info['fibonacci']['all_fibos']
                    if not all_fibos:
                        continue
                    
                    processed_patterns.add(pattern_id)
                    
                    # Znajdź punkty wzorca i typ wzorca
                    pattern_group = pattern_groups.get(pattern_id, {})
                    points = pattern_group.get('points', {})
                    pattern_type = pattern_group.get('pattern_type', '')
                    
                    logger.debug(f"Przetwarzanie all_fibo dla wzorca {pattern_id} typu {pattern_type}")
                    
                    # Iteruj przez wszystkie kombinacje punktów w all_fibos
                    for combination_name, combination_data in all_fibos.items():
                        start_price = combination_data.get('start_price', 0)
                        end_price = combination_data.get('end_price', 0)
                        is_uptrend = combination_data.get('is_uptrend', True)
                        
                        # Znajdź punkty startowy i końcowy dla tej kombinacji
                        point1_name = combination_name[0] if len(combination_name) >= 1 else 'X'
                        point2_name = combination_name[1] if len(combination_name) >= 2 else 'A'
                        
                        point1 = points.get(point1_name)
                        point2 = points.get(point2_name)
                        
                        if not point1 or not point2:
                            continue
                        
                        start_x = point1['index']
                        
                        # Przetwórz każdy typ poziomów dla tej kombinacji
                        for fib_type, levels in combination_data.items():
                            if fib_type not in ['retracement', 'extension', 'targets'] or not isinstance(levels, dict):
                                continue
                            
                            linestyle = '--' if fib_type == 'retracement' else (':' if fib_type == 'extension' else '-')
                            alpha = 0.6  # Trochę mniej przezroczyste niż zwykłe Fibonacci
                            linewidth = 1
                            
                            # Dodaj każdy poziom do listy (z filtrowaniem)
                            for level_name, level_price in levels.items():
                                if level_price == 0 or pd.isna(level_price):
                                    continue
                                
                                # Sprawdź czy poziom powinien być uwzględniony według filtrów
                                if should_include_level(combination_name, fib_type, level_name, pattern_type):
                                    color = get_fibonacci_color(fib_type, level_name)
                                    
                                    all_levels_data.append({
                                        'pattern_id': pattern_id,
                                        'combination_name': combination_name,
                                        'fib_type': fib_type,
                                        'level_name': level_name,
                                        'level_price': level_price,
                                        'color': color,
                                        'linestyle': linestyle,
                                        'alpha': alpha,
                                        'linewidth': linewidth,
                                        'start_x': start_x,
                                        'pattern_type': pattern_type
                                    })
                                    
                                    logger.debug(f"Uwzględniono poziom {combination_name} {level_name} ({level_price:.6f}) dla wzorca {pattern_type} ID:{pattern_id}")
                                else:
                                    logger.debug(f"Pominięto poziom {combination_name} {level_name} ({level_price:.6f}) dla wzorca {pattern_type} ID:{pattern_id} - nie spełnia filtrów")
            
            logger.info(f"Zebrano {len(all_levels_data)} poziomów z all_fibo z {len(processed_patterns)} wzorców")
            
            if not all_levels_data:
                logger.info("Brak poziomów do narysowania z all_fibo")
                return
            
            # Sortuj poziomy według ceny dla lepszego pozycjonowania etykiet
            all_levels_data.sort(key=lambda x: x['level_price'])
            
            # Rysuj linie ze standardowymi etykietami
            for level_data in all_levels_data:
                # Rysuj linię od punktu startowego do końca wykresu
                main_ax.plot(
                    [level_data['start_x'], chart_end_x], 
                    [level_data['level_price'], level_data['level_price']],
                    color=level_data['color'],
                    alpha=level_data['alpha'],
                    linestyle=level_data['linestyle'],
                    linewidth=level_data['linewidth'],
                    zorder=3  # Pod wzorcami harmonicznymi
                )
                
                # Oblicz procent poziomu Fibonacci
                try:
                    fib_value = float(level_data['level_name'])
                    fib_percent = f"{fib_value * 100:.1f}%"
                except ValueError:
                    fib_percent = level_data['level_name']
                
                # Tekst etykiety
                label_text = f"ID: {level_data['pattern_id']} | {level_data['combination_name']} {fib_percent} | {level_data['level_price']:.6f}"
                
                # Pozycja etykiety - lewa górna krawędź linii
                label_x = level_data['start_x'] + 2  # Przesunięcie od początku linii
                label_y = level_data['level_price']
                
                # Dodaj etykietę z transparentnym tłem
                main_ax.annotate(
                    label_text,
                    (label_x, label_y),
                    xytext=(0, 3),  # Małe przesunięcie w górę
                    textcoords='offset points',
                    ha='left',
                    va='bottom',
                    fontsize=dynamic_font_fibo_y_labels,
                    color=level_data['color'],
                    alpha=0.9,
                    bbox=dict(
                        boxstyle="round,pad=0.2",
                        facecolor='black',
                        alpha=0.1,  # Maksymalnie transparentne tło
                        edgecolor='none'  # Bez borderów
                    ),
                    zorder=6  # Nad liniami Fibonacci
                )
                
                logger.debug(f"Narysowano all_fibo linię {level_data['combination_name']} {level_data['level_name']} = {level_data['level_price']:.6f}")
            
            
            # Loguj statystyki filtrowania
            retracement_count = sum(1 for level in all_levels_data if level['fib_type'] == 'retracement')
            extension_count = sum(1 for level in all_levels_data if level['fib_type'] == 'extension')
            targets_count = sum(1 for level in all_levels_data if level['fib_type'] == 'targets')
            
            logger.info(f"Pomyślnie narysowano {len(all_levels_data)} poziomów z all_fibo ze standardowymi etykietami:")
            logger.info(f"  - Retracement: {retracement_count} poziomów")
            logger.info(f"  - Extension: {extension_count} poziomów") 
            logger.info(f"  - Targets: {targets_count} poziomów")
            
        except Exception as e:
            logger.error(f"Błąd podczas rysowania poziomów z all_fibo: {e}")
            logger.error(traceback.format_exc())