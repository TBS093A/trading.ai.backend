import re
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from .abstract_technical_analysis_object import TechnicalAnalysisObject
from ..draw_utils import DrawUtils


class FibonacciTargets(TechnicalAnalysisObject):
    """Wszystkie targety Fibonacciego (PRZ, TP, SL)"""
    
    def __init__(self):
        super().__init__("FibonacciTargets")
    
    def calculate(self, *args, **kwargs) -> None:
        """
        Oblicza wszystkie targety Fibonacciego z wzorców harmonicznych
        
        Args:
            pattern_type: Typ wzorca (np. "Gartley", "Butterfly", "Bat")
            pattern_points: Słownik punktów wzorca
            all_fibos: Obliczone poziomy Fibonacci dla wszystkich kombinacji
            is_bullish: Czy wzorzec jest bullish
            
        """
        self.calculated_data = self.__calculate_all_targets(
            pattern_type=kwargs.get('pattern_type'),
            pattern_points=kwargs.get('pattern_points'),
            all_fibos=kwargs.get('all_fibos'),
            is_bullish=kwargs.get('is_bullish')
        )

    # Bufor SL, gdy żaden poziom strukturalny (X / daleka krawędź PRZ) nie leży za D:
    # ułamek nogi XA (albo AD, gdy brak X), żeby SL nigdy nie wypadł na samym wejściu.
    SL_FALLBACK_BUFFER = 0.13

    @staticmethod
    def _leg(start: float, end: float, ratio: float) -> float:
        """
        Poziom `ratio` nogi start -> end mierzony od `end` z powrotem w stronę `start`
        (0 = end, 1 = start, > 1 = za start). Tak liczone są wszystkie projekcje D:
        D = 1.618 XA -> _leg(X, A, 1.618), CD = 2.24 BC -> _leg(B, C, 2.24),
        TP 38.2% AD -> _leg(A, D, 0.382). Kierunek wynika z cen, więc działa dla obu stron.
        """
        return end - (end - start) * ratio

    def __calculate_all_targets(
        self,
        pattern_type: str,
        pattern_points: Dict[str, Dict[str, Union[int, float]]],
        all_fibos: Optional[Dict[str, Dict[str, Dict[str, float]]]],
        is_bullish: Optional[bool]
    ) -> Dict[str, Dict[str, Union[float, List[float], str]]]:
        """
        Oblicza PRZ (Potential Reversal Zone), TP (Take Profit) oraz SL (Stop Loss)
        dla wzorców harmonicznych.

        Poziomy liczone są bezpośrednio z cen punktów (`_leg`), a nie z `all_fibos`:
        `extension` w all_fibos zawsze wychodzi za punkt końcowy nogi (np. XA 1.618 -> za A),
        a D wzorca leży po stronie X - stąd SL/PRZ po złej stronie wejścia. `all_fibos` jest
        przyjmowane dla zgodności wywołań, ale nieużywane.

        Gwarancje (dla każdego wzorca, o ile jest D):
            bullish: SL < D < TP1 <= TP2,   bearish: SL > D > TP1 >= TP2
        SL leży za X (lub za poziomem SL wzorca) albo za daleką krawędzią PRZ - co dalej
        w kierunku wzorca; jeśli oba są przed D (cena przebiła strukturę), SL = D ∓ bufor.

        Args:
            pattern_type: Typ wzorca (np. "Gartley", "Butterfly", "deep crab")
            pattern_points: Słownik punktów wzorca {'X': {'price': ...}, ...}
            all_fibos: Nieużywane (zgodność wywołań)
            is_bullish: Czy wzorzec jest bullish (None -> z kierunku nogi XA)

        Returns:
            {
                'PRZ': {'type': 'zone', 'min_price': float, 'max_price': float, 'description': str}
                       lub {'type': 'line', 'price': float, 'description': str},
                'TP1': {'type': 'line', 'price': float, 'description': str},
                'TP2': ..., 'TP3': ...,
                'SL': {'type': 'line', 'price': float, 'description': str}
            }
        """
        targets = {}
        pattern_points = pattern_points or {}

        def price(name: str) -> Optional[float]:
            p = pattern_points.get(name)
            return float(p['price']) if p and p.get('price') is not None else None

        x, a, b, c, d = (price(n) for n in ('X', 'A', 'B', 'C', 'D'))
        if d is None:
            # Bez D nie da się ustawić SL/TP względem wejścia (np. wzorce formujące się)
            return targets
        if is_bullish is None:
            if x is None or a is None or x == a:
                return targets
            is_bullish = a > x  # bullish XABCD: X dołek, A szczyt, D dołek
        sign = 1.0 if is_bullish else -1.0  # kierunek zysku
        leg = self._leg

        # Normalizuj nazwę wzorca
        pattern_name = (pattern_type or '').lower().replace('_', '').replace('-', '').replace(' ', '')

        def has(*values) -> bool:
            return all(v is not None for v in values)

        def zone(levels: List[float], description: str) -> None:
            if levels:
                targets['PRZ'] = {'type': 'zone', 'min_price': min(levels), 'max_price': max(levels),
                                  'description': description}

        def line(name: str, value: float, description: str) -> None:
            targets[name] = {'type': 'line', 'price': value, 'description': description}

        def ad_tp(name: str, ratio: float, description: str) -> None:
            if has(a):
                line(name, leg(a, d, ratio), description)

        sl_level, sl_desc = (x, "SL: X level - Stop Loss") if has(x) else (None, None)

        try:
            if pattern_name == 'cypher':
                # Cypher: AB = 0.382–0.618 XA; XC = 1.13–1.414 XA; CD = 0.786 XC
                # PRZ = 0.786 XC + projekcja BC (127.2–141.4%); TP-1 38.2 AD, TP-2 61.8 AD; SL za X
                if has(x, b, c):
                    zone([leg(x, c, 0.786), leg(b, c, 1.272), leg(b, c, 1.414)],
                         "PRZ: XC(78.6%) + BC(127.2-141.4%) - Potential Reversal Zone")
                ad_tp('TP1', 0.382, "TP1: AD(38.2%) - Take Profit 1")
                ad_tp('TP2', 0.618, "TP2: AD(61.8%) - Take Profit 2")
                sl_desc = "SL: X level - Stop Loss (konserwatywny)"

            elif pattern_name in ['shark', 'deepshark']:
                # Shark: AB = 0.382–0.618 XA; BC = 1.13–1.618 AB; CD = 1.618–2.24 BC; D = 0.886 XA
                # Deep Shark: D = 1.13 XA. PRZ = D-owy poziom XA + 161.8–224 BC; TP-1 50% BC;
                # SL za 1.13 XA (Shark) / 1.272 XA (Deep Shark) lub za PRZ
                deep = pattern_name == 'deepshark'
                if has(x, a, b, c):
                    zone([leg(x, a, 1.13 if deep else 0.886), leg(b, c, 1.618), leg(b, c, 2.24)],
                         f"PRZ: XA({'113' if deep else '88.6'}%) + BC(161.8-224%) - Very narrow PRZ")
                if has(b, c):
                    line('TP1', leg(b, c, 0.5), "TP1: BC(50%) - Szybki scalp")
                if has(x, a):
                    sl_level = leg(x, a, 1.272 if deep else 1.13)
                    sl_desc = f"SL: XA({'127.2' if deep else '113'}%) - {'Deep ' if deep else ''}Shark SL"

            elif pattern_name in ['five0', 'fiveo']:
                # Five-0: po zakończonym Sharku: CD = 50% retracement BC; w tle Reciprocal AB = CD
                # PRZ = poziom 50% BC; TP-1 38.2 CD (zwykle rozpoczyna nowy trend); SL za D
                if has(b, c):
                    targets['PRZ'] = {'type': 'line', 'price': leg(b, c, 0.5),
                                      'description': "PRZ: BC(50%) - Reversal po Shark"}
                if has(c):
                    line('TP1', leg(c, d, 0.382), "TP1: CD(38.2%) - Początek nowego trendu")
                sl_level, sl_desc = d, "SL: za D - Stop Loss"

            elif pattern_name in ['crab', 'deepcrab']:
                # Crab: AB = 0.382–0.618 XA; BC = 0.382–0.886 AB; D = 1.618 XA lub 2.24–3.618 BC
                # Deep Crab: B zwykle 0.886 XA → mocniejszy powrót BC
                # PRZ = 1.618 XA (+ 224–361.8 BC); TP-1 38.2 AD, TP-2 61.8 AD, TP-3 161.8 AD; SL za PRZ
                if has(x, a):
                    levels = [leg(x, a, 1.618)]
                    if has(b, c):
                        levels += [leg(b, c, 2.24), leg(b, c, 3.618)]
                    zone(levels, "PRZ: XA(161.8%) + BC(224-361.8%) - Ekstremalna strefa")
                    sl_level, sl_desc = leg(x, a, 1.618), "SL: XA(161.8%) - Stop Loss"
                ad_tp('TP1', 0.382, "TP1: AD(38.2%) - Szybkie wyjście")
                ad_tp('TP2', 0.618, "TP2: AD(61.8%) - Główny cel")
                ad_tp('TP3', 1.618, "TP3: AD(161.8%) - Swing-trading cel")

            elif pattern_name in ['butterfly', 'deepbutterfly']:
                # Butterfly: B = 0.786 XA; D = 1.272–1.618 XA; BC = 1.618 AB
                # Deep Butterfly: B jeszcze głębiej (0.886 XA), a D potrafi dojść do 2.0–2.618 XA
                # PRZ = 1.272/1.618 XA (+ AB=CD); TP-1 61.8 AD (często odwrót V-kształtny); SL za PRZ
                deep = pattern_name == 'deepbutterfly'
                ratios = [2.0, 2.24, 2.618] if deep else [1.272, 1.618]
                if has(x, a):
                    zone([leg(x, a, r) for r in ratios],
                         f"PRZ: XA({ratios[0] * 100:.1f}-{ratios[-1] * 100:.1f}%) + AB=CD - "
                         f"{'Ekstremalna strefa' if deep else 'V-kształtny odwrót'}")
                    sl_level = leg(x, a, ratios[-1])
                    sl_desc = f"SL: XA({ratios[-1] * 100:.1f}%) - Stop Loss"
                ad_tp('TP1', 0.618, "TP1: AD(61.8%) - Powrót do ƒ-strefy" if deep
                      else "TP1: AD(61.8%) - V-kształtny odwrót")

            elif pattern_name in ['bat', 'altbat']:
                # Bat: B = 0.382–0.50 XA; BC = 0.382–0.886 AB; D = 0.886 XA
                # Alt Bat: B = 0.382 XA; BC = 0.382/0.886 AB; D ≈ 1.13 XA oraz 2.0–3.618 BC
                # PRZ = 0.886 XA + proj. 1.618+ BC; TP-1 38.2 AD, TP-2 61.8 AD; SL za X
                alt = pattern_name == 'altbat'
                if has(x, a, b, c):
                    if alt:
                        zone([leg(x, a, 1.13), leg(b, c, 2.0), leg(b, c, 3.618)],
                             "PRZ: XA(113%) + BC(200-361.8%) - Alt Bat PRZ")
                    else:
                        zone([leg(x, a, 0.886), leg(b, c, 1.618), leg(b, c, 2.24), leg(b, c, 2.618)],
                             "PRZ: XA(88.6%) + BC(161.8+%) - Bat PRZ")
                if alt and has(x, a):
                    sl_level, sl_desc = leg(x, a, 1.13), "SL: XA(113%) - Alt Bat SL"
                else:
                    sl_desc = "SL: X level - Konserwatywny SL"
                # Alt Bat to zwykle krótkoterminowy scalp z jednym TP
                ad_tp('TP1', 0.382, "TP1: AD(38.2%) - Scalp exit" if alt else "TP1: AD(38.2%) - Szybkie wyjście")
                if not alt:
                    ad_tp('TP2', 0.618, "TP2: AD(61.8%) - Główny cel")

            elif pattern_name == 'gartley':
                # Gartley: B = 0.618 XA; BC = 0.382–0.886 AB; D = 0.786 XA
                # PRZ = zbieżność 0.786 XA + AB=CD; Klasyczny: TP-1 61.8 AD, TP-2 = 100% AD; SL za X
                if has(x, a):
                    targets['PRZ'] = {'type': 'line', 'price': leg(x, a, 0.786),
                                      'description': "PRZ: XA(78.6%) + AB=CD - Klasyczny Gartley"}
                ad_tp('TP1', 0.618, "TP1: AD(61.8%) - Klasyczny cel 1")
                ad_tp('TP2', 1.0, "TP2: AD(100%) - Klasyczny cel 2")
                sl_desc = "SL: X level - Konserwatywny SL"

            elif pattern_name == 'bartley':
                # Bartley: hybryda Bat-Gartley: AB = 0.618 XA; BC = 0.382–0.886 AB; CD = 1.272–1.618 BC;
                # D ≈ 0.886 XA. PRZ = 0.786–0.886 XA + 1.272–1.618 BC; TP-1 50% AD, TP-2 100% AD; SL za X
                if has(x, a, b, c):
                    zone([leg(x, a, 0.786), leg(x, a, 0.886), leg(b, c, 1.272), leg(b, c, 1.618)],
                         "PRZ: XA(78.6-88.6%) + BC(127.2-161.8%) - Bartley hybrid")
                ad_tp('TP1', 0.5, "TP1: AD(50%) - Bartley cel 1")
                ad_tp('TP2', 1.0, "TP2: AD(100%) - Bartley cel 2")
                sl_desc = "SL: X level - Bartley SL"

            else:
                # Nierozpoznany wzorzec - podstawowe targety
                ad_tp('TP1', 0.382, "TP1: AD(38.2%) - Take Profit 1")
                ad_tp('TP2', 0.618, "TP2: AD(61.8%) - Take Profit 2")
                sl_desc = "SL: X level - Stop Loss" if has(x) else "SL: Default level - Stop Loss"

            self.__place_sl(targets, sl_level, sl_desc, x, a, d, sign)
            self.__sanitize_tps(targets, d, sign)

        except Exception as e:
            logger.warning(f"Błąd podczas obliczania targetów dla wzorca {pattern_type}: {e}")
            targets = {}

        return targets

    def __place_sl(self, targets: Dict, sl_level: Optional[float], sl_desc: Optional[str],
                   x: Optional[float], a: Optional[float], d: float, sign: float) -> None:
        """
        SL = najdalszy w kierunku straty z: poziomu SL wzorca i dalekiej krawędzi PRZ.
        Jeśli żaden nie leży za D (cena przebiła strukturę), SL = D ∓ bufor.
        """
        candidates = [(sl_level, sl_desc)] if sl_level is not None else []
        prz = targets.get('PRZ')
        if prz:
            if prz['type'] == 'zone':
                far_edge = prz['min_price'] if sign > 0 else prz['max_price']
            else:
                far_edge = prz['price']
            candidates.append((far_edge, "SL: za dalszą krawędzią PRZ - Stop Loss"))

        # Odległość "za D" w kierunku straty (> 0 = poprawna strona)
        beyond = [(sign * (d - level), level, desc) for level, desc in candidates if sign * (d - level) > 0]
        if beyond:
            _, level, desc = max(beyond, key=lambda t: t[0])
        else:
            span = abs(a - x) if x is not None and a is not None and a != x else (
                abs(a - d) if a is not None else abs(d))
            level = d - sign * span * self.SL_FALLBACK_BUFFER
            desc = f"SL: D ∓ {self.SL_FALLBACK_BUFFER * 100:.0f}% XA - struktura przebita, bufor za wejściem"
        targets['SL'] = {'type': 'line', 'price': level, 'description': desc}

    @staticmethod
    def __sanitize_tps(targets: Dict, d: float, sign: float) -> None:
        """TP tylko po stronie zysku od D i w kolejności rosnącej odległości (TP1 najbliżej)."""
        names = sorted(n for n in targets if n.startswith('TP'))
        tps = [targets.pop(n) for n in names]
        tps = [t for t in tps if sign * (t['price'] - d) > 0]
        tps.sort(key=lambda t: sign * (t['price'] - d))
        for i, tp in enumerate(tps, start=1):
            tp['description'] = re.sub(r'^TP\d+:', f'TP{i}:', tp['description'])
            targets[f'TP{i}'] = tp

    def draw(self, main_ax, df: pd.DataFrame, klines: List[Dict], **kwargs) -> None:
        """Rysuje targety Fibonacciego (PRZ, TP, SL) używając DrawUtils"""
        if self.calculated_data is None:
            return
        
        show_all_fibo_targets = kwargs.get('show_all_fibo_targets', False)
        if not show_all_fibo_targets:
            return
        
        # Przygotuj dane w formacie wymaganym przez DrawUtils
        fibonacci_data = []
        pattern_groups = {}
        
        # Konwertuj targety do formatu fibonacci wymaganego przez DrawUtils
        for target_data in self.calculated_data:
            targets = target_data['targets']
            pattern_type = target_data['pattern_type']
            pattern_id = target_data['pattern_id']
            
            # Konwertuj targety do formatu fibonacci
            fibonacci = {
                'targets': {}
            }
            
            for target_name, target_info in targets.items():
                if target_info['type'] == 'line':
                    fibonacci['targets'][target_name] = target_info['price']
                elif target_info['type'] == 'zone':
                    # Dla stref używaj średniej ceny
                    avg_price = (target_info['min_price'] + target_info['max_price']) / 2
                    fibonacci['targets'][target_name] = avg_price
            
            fibonacci_data.append({
                'kline_idx': target_data['kline_idx'],
                'pattern_id': pattern_id,
                'fibonacci': fibonacci
            })
            
            # Przygotuj pattern_groups jeśli nie istnieje
            if pattern_id not in pattern_groups:
                pattern_groups[pattern_id] = {
                    'points': {},
                    'pattern_retraces': {},
                    'pattern_name': pattern_type,
                    'pattern_type': pattern_type,
                    'is_bullish': True  # Domyślnie bullish
                }
        
        # Użyj DrawUtils do rysowania
        DrawUtils.draw_fibonacci_lines_with_labels(
            main_ax=main_ax,
            fibonacci_data=fibonacci_data,
            pattern_groups=pattern_groups,
            klines=klines,
            dynamic_font_size_fibo_labels=kwargs.get('dynamic_font_size_fibo_labels', 8),
            df=df,
            show_all_fibo_targets=True,  # FibonacciTargets - włącz targety
            show_fibonacci=False,  # FibonacciTargets - nie podstawowe poziomy
            show_all_fibonacci_levels=False,  # FibonacciTargets - nie wszystkie poziomy
            show_all_retracement_levels=True,  # FibonacciTargets - włącz retracement
            show_all_extension_levels=True  # FibonacciTargets - włącz extension
        )
