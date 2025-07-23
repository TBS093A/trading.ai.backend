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

    def __calculate_all_targets(
        self,
        pattern_type: str,
        pattern_points: Dict[str, Dict[str, Union[int, float]]],
        all_fibos: Dict[str, Dict[str, Dict[str, float]]],
        is_bullish: bool
    ) -> Dict[str, Dict[str, Union[float, List[float], str]]]:
        """
        Oblicza PRZ (Potential Reversal Zone), TP (Take Profit) oraz SL (Stop Loss) 
        dla wzorców harmonicznych na podstawie all_fibos.
        
        Args:
            pattern_type: Typ wzorca (np. "Gartley", "Butterfly", "Bat")
            pattern_points: Słownik punktów wzorca
            all_fibos: Obliczone poziomy Fibonacci dla wszystkich kombinacji
            is_bullish: Czy wzorzec jest bullish
            
        Returns:
            Słownik zawierający obliczone targety:
            {
                'PRZ': {'type': 'zone', 'min_price': float, 'max_price': float, 'description': str},
                'TP1': {'type': 'line', 'price': float, 'description': str},
                'TP2': {'type': 'line', 'price': float, 'description': str},
                'SL': {'type': 'line', 'price': float, 'description': str}
            }
        """
        targets = {}
        
        # Pobierz punkty wzorca
        x_price = pattern_points.get('X', {}).get('price', 0) if 'X' in pattern_points else 0
        a_price = pattern_points.get('A', {}).get('price', 0) if 'A' in pattern_points else 0
        b_price = pattern_points.get('B', {}).get('price', 0) if 'B' in pattern_points else 0
        c_price = pattern_points.get('C', {}).get('price', 0) if 'C' in pattern_points else 0
        d_price = pattern_points.get('D', {}).get('price', 0) if 'D' in pattern_points else 0
        
        # Normalizuj nazwę wzorca
        pattern_name = pattern_type.lower().replace('_', '').replace('-', '').replace(' ', '')
        
        try:
            if pattern_name == 'cypher':
                # Cypher: AB = 0.382–0.618 XA; BC = 1.272–1.414 AB; CD = 0.786 XC
                # PRZ = kumulacja 0.786 XC + projekcja BC; TP-1 38.2 AD, TP-2 61.8 AD; SL > X
                if 'XC' in all_fibos and 'BC' in all_fibos and 'AD' in all_fibos:
                    xc_786 = all_fibos['XC']['retracement'].get('0.786', 0)
                    bc_1272 = all_fibos['BC']['extension'].get('1.272', 0)  # Projekcja BC 127.2%
                    bc_1414 = all_fibos['BC']['extension'].get('1.414', 0)  # Projekcja BC 141.4%
                    
                    # PRZ jako strefa między XC 0.786 a projekcjami BC (1.272-1.414)
                    prz_levels = [xc_786, bc_1272, bc_1414]
                    prz_levels = [p for p in prz_levels if p > 0]
                    if prz_levels:
                        targets['PRZ'] = {
                            'type': 'zone',
                            'min_price': min(prz_levels),
                            'max_price': max(prz_levels),
                            'description': f"PRZ: XC(78.6%) + BC(127.2-141.4%) - Potential Reversal Zone"
                        }
                    
                    # TP1 i TP2 - szybkie wyjścia zgodnie z wytycznymi
                    ad_382 = all_fibos['AD']['retracement'].get('0.382', 0)
                    ad_618 = all_fibos['AD']['retracement'].get('0.618', 0)
                    if ad_382:
                        targets['TP1'] = {'type': 'line', 'price': ad_382, 'description': "TP1: AD(38.2%) - Take Profit 1"}
                    if ad_618:
                        targets['TP2'] = {'type': 'line', 'price': ad_618, 'description': "TP2: AD(61.8%) - Take Profit 2"}
                    
                    # SL konserwatywny kilka pipsów poza X
                    targets['SL'] = {'type': 'line', 'price': x_price, 'description': "SL: X level - Stop Loss (konserwatywny)"}
                        
            elif pattern_name in ['shark', 'deepshark']:
                # Shark: AB = 1.13–1.618 XA; BC ≈ 1.13 OX; CD ≈ 0.886 OX
                # PRZ = konfluencja 0.886 OX + 1.13 AB; Szybki scalp: TP-1 50% BC; SL powyżej PRZ
                if 'XA' in all_fibos and 'AB' in all_fibos and 'BC' in all_fibos:  # Używamy XA jako OX
                    ox_886 = all_fibos['XA']['retracement'].get('0.886', 0)  # OX = XA przy 88.6%
                    ab_113 = all_fibos['AB']['extension'].get('1.13', 0)
                    ab_1618 = all_fibos['AB']['extension'].get('1.618', 0)
                    
                    # PRZ jako bardzo wąska strefa przy 0.886 OX + 1.13 AB
                    prz_levels = [ox_886, ab_113]
                    if pattern_name == 'deepshark' and ab_1618 > 0:
                        prz_levels.append(ab_1618)  # Deep Shark sięga do 1.618 XA
                        
                    prz_levels = [p for p in prz_levels if p > 0]
                    if prz_levels:
                        targets['PRZ'] = {
                            'type': 'zone',
                            'min_price': min(prz_levels),
                            'max_price': max(prz_levels),
                            'description': f"PRZ: XA(88.6%) + AB(113-161.8%) - Very narrow PRZ"
                        }
                    
                    # TP1 - 50% BC (szybki scalp)
                    bc_50 = all_fibos['BC']['retracement'].get('0.5', 0)
                    if bc_50:
                        targets['TP1'] = {'type': 'line', 'price': bc_50, 'description': "TP1: BC(50%) - Szybki scalp"}
                    
                    # SL powyżej PRZ lub 1.272 OX dla Deep Shark
                    if pattern_name == 'deepshark':
                        ox_1272 = all_fibos['XA']['extension'].get('1.272', 0)
                        targets['SL'] = {'type': 'line', 'price': ox_1272, 'description': "SL: XA(127.2%) - Deep Shark SL"}
                    else:
                        # SL powyżej PRZ dla regularnego Shark
                        if prz_levels:
                            prz_max = max(prz_levels)
                            targets['SL'] = {'type': 'line', 'price': prz_max * 1.001, 'description': "SL: Above PRZ - Stop Loss"}
                        
            elif pattern_name == 'five0' or pattern_name == 'five-0':
                # Five-0: Po zakończonym Sharku: leg C-D = 50% retracement B-C; w tle Reciprocal AB = CD
                # PRZ = poziom 50% BC; TP-1 38.2 CD, zwykle rozpoczyna nowy trend; SL za D
                if 'BC' in all_fibos and 'CD' in all_fibos:
                    bc_50 = all_fibos['BC']['retracement'].get('0.5', 0)
                    
                    # PRZ na poziomie 50% BC (pojedynczy poziom)
                    if bc_50 > 0:
                        targets['PRZ'] = {
                            'type': 'line',  # Pojedynczy poziom
                            'price': bc_50,
                            'description': f"PRZ: BC(50%) - Reversal po Shark"
                        }
                    
                    # TP1 - 38.2% CD (zwykle rozpoczyna nowy trend)
                    cd_382 = all_fibos['CD']['retracement'].get('0.382', 0)
                    if cd_382:
                        targets['TP1'] = {'type': 'line', 'price': cd_382, 'description': "TP1: CD(38.2%) - Początek nowego trendu"}
                    
                    # SL za D
                    targets['SL'] = {'type': 'line', 'price': d_price, 'description': "SL: D level - Stop Loss"}
                        
            elif pattern_name in ['crab', 'deepcrab']:
                # Crab: AB = 0.382–0.618 XA; BC = 0.382–0.886 AB; D = 1.618 XA lub 2.24–3.618 BC
                # Deep Crab: B zwykle 0.886 XA → mocniejszy powrót BC
                # PRZ = 1.618 XA (+ 224–361.8 BC); TP-1 38.2 AD, TP-2 61.8 AD; SL > 1.618 XA
                if 'XA' in all_fibos and 'BC' in all_fibos and 'AD' in all_fibos:
                    xa_1618 = all_fibos['XA']['extension'].get('1.618', 0)
                    bc_224 = all_fibos['BC']['extension'].get('2.24', 0)   # 224%
                    bc_3618 = all_fibos['BC']['extension'].get('3.618', 0) # 361.8%
                    
                    # PRZ jako strefa między 1.618 XA a projekcjami BC (224-361.8%)
                    prz_levels = [xa_1618]
                    if bc_224 > 0:
                        prz_levels.append(bc_224)
                    if bc_3618 > 0:
                        prz_levels.append(bc_3618)
                    
                    prz_levels = [p for p in prz_levels if p > 0]
                    if prz_levels:
                        targets['PRZ'] = {
                            'type': 'zone',
                            'min_price': min(prz_levels),
                            'max_price': max(prz_levels),
                            'description': f"PRZ: XA(161.8%) + BC(224-361.8%) - Ekstremalna strefa"
                        }
                    
                    # TP1 i TP2 dla swing-trading (cele tygodniowe)
                    ad_382 = all_fibos['AD']['retracement'].get('0.382', 0)
                    ad_618 = all_fibos['AD']['retracement'].get('0.618', 0)
                    ad_1618 = all_fibos['AD']['extension'].get('1.618', 0)  # Odległy TP dla swing
                    
                    if ad_382:
                        targets['TP1'] = {'type': 'line', 'price': ad_382, 'description': "TP1: AD(38.2%) - Szybkie wyjście"}
                    if ad_618:
                        targets['TP2'] = {'type': 'line', 'price': ad_618, 'description': "TP2: AD(61.8%) - Główny cel"}
                    if ad_1618:
                        targets['TP3'] = {'type': 'line', 'price': ad_1618, 'description': "TP3: AD(161.8%) - Swing-trading cel"}
                    
                    # SL powyżej 1.618 XA
                    targets['SL'] = {'type': 'line', 'price': xa_1618, 'description': "SL: XA(161.8%) - Stop Loss"}
                        
            elif pattern_name in ['butterfly', 'deepbutterfly']:
                # Butterfly: B = 0.786 XA; D = 1.272–1.618 XA; BC = 1.618 AB
                # Deep Butterfly: B jeszcze głębiej (0.886 XA), a D potrafi dojść do 2.24–2.618 XA
                # PRZ = 1.272/1.618 XA + równość AB=CD; TP-1 61.8 AD (często odwrót V-kształtny); SL > 1.618 XA
                if 'XA' in all_fibos and 'AD' in all_fibos:
                    xa_1272 = all_fibos['XA']['extension'].get('1.272', 0)
                    xa_1618 = all_fibos['XA']['extension'].get('1.618', 0)
                    
                    if pattern_name == 'deepbutterfly':
                        # Deep Butterfly: ekstremalna 2.0-2.618 XA (głównie jednokrotowy TP)
                        xa_20 = all_fibos['XA']['extension'].get('2.0', 0)
                        xa_224 = all_fibos['XA']['extension'].get('2.24', 0)
                        xa_2618 = all_fibos['XA']['extension'].get('2.618', 0)
                        prz_levels = [p for p in [xa_20, xa_224, xa_2618] if p > 0]
                        sl_level = xa_2618 if xa_2618 > 0 else max(prz_levels) if prz_levels else 0
                    else:
                        # Regular Butterfly: 1.272-1.618 XA
                        prz_levels = [p for p in [xa_1272, xa_1618] if p > 0]
                        sl_level = xa_1618
                    
                    if prz_levels:
                        targets['PRZ'] = {
                            'type': 'zone',
                            'min_price': min(prz_levels),
                            'max_price': max(prz_levels),
                            'description': f"PRZ: XA(127.2-261.8%) + AB=CD - {'Ekstremalna strefa' if pattern_name == 'deepbutterfly' else 'V-kształtny odwrót'}"
                        }
                    
                    # TP1 - 61.8% AD (często odwrót V-kształtny)
                    ad_618 = all_fibos['AD']['retracement'].get('0.618', 0)
                    if ad_618:
                        description = "TP1: AD(61.8%) - Powrót do ƒ-strefy" if pattern_name == 'deepbutterfly' else "TP1: AD(61.8%) - V-kształtny odwrót"
                        targets['TP1'] = {'type': 'line', 'price': ad_618, 'description': description}
                    
                    # SL powyżej ekstremum
                    if sl_level > 0:
                        targets['SL'] = {'type': 'line', 'price': sl_level, 'description': f"SL: XA({sl_level:.1f}) - Stop Loss"}
                        
            elif pattern_name in ['bat', 'altbat']:
                # Bat: B = 0.382–0.50 XA; BC = 0.382–0.886 AB; D = 0.886 XA
                # Alt Bat: B = 0.382 XA; BC = 0.382/0.886 AB; D ≈ 1.13 XA oraz 2.0–3.618 BC
                # PRZ = 0.886 XA + proj. 1.618+ BC; TP-1 38.2 AD, TP-2 61.8 AD; SL za X
                if 'XA' in all_fibos and 'BC' in all_fibos and 'AD' in all_fibos:
                    if pattern_name == 'altbat':
                        # Alt Bat: PRZ = 1.13 XA + rozszerzona BC (2.0-3.618)
                        xa_113 = all_fibos['XA']['extension'].get('1.13', 0)
                        bc_20 = all_fibos['BC']['extension'].get('2.0', 0)
                        bc_3618 = all_fibos['BC']['extension'].get('3.618', 0)
                        prz_levels = [p for p in [xa_113, bc_20, bc_3618] if p > 0]
                        sl_level = xa_113
                        prz_desc = "PRZ: XA(113%) + BC(200-361.8%) - Alt Bat PRZ"
                        sl_desc = "SL: XA(113%) - Alt Bat SL"
                        is_scalp = True  # Alt Bat często krótkoterminowy scalp
                    else:
                        # Regular Bat: PRZ = 0.886 XA + proj. 1.618+ BC
                        xa_886 = all_fibos['XA']['retracement'].get('0.886', 0)
                        bc_1618 = all_fibos['BC']['extension'].get('1.618', 0)
                        bc_224 = all_fibos['BC']['extension'].get('2.24', 0)
                        bc_2618 = all_fibos['BC']['extension'].get('2.618', 0)
                        prz_levels = [p for p in [xa_886, bc_1618, bc_224, bc_2618] if p > 0]
                        sl_level = x_price
                        prz_desc = "PRZ: XA(88.6%) + BC(161.8+%) - Bat PRZ"
                        sl_desc = "SL: X level - Konserwatywny SL"
                        is_scalp = False
                    
                    if prz_levels:
                        targets['PRZ'] = {
                            'type': 'zone',
                            'min_price': min(prz_levels),
                            'max_price': max(prz_levels),
                            'description': prz_desc
                        }
                    
                    # TP1 i TP2 (dla Alt Bat często krótkoterminowy scalp)
                    ad_382 = all_fibos['AD']['retracement'].get('0.382', 0)
                    ad_618 = all_fibos['AD']['retracement'].get('0.618', 0)
                    
                    if ad_382:
                        tp1_desc = "TP1: AD(38.2%) - Scalp exit" if is_scalp else "TP1: AD(38.2%) - Szybkie wyjście"
                        targets['TP1'] = {'type': 'line', 'price': ad_382, 'description': tp1_desc}
                    
                    if ad_618 and not is_scalp:  # Alt Bat ma zazwyczaj jeden TP
                        targets['TP2'] = {'type': 'line', 'price': ad_618, 'description': "TP2: AD(61.8%) - Główny cel"}
                    
                    # SL
                    targets['SL'] = {'type': 'line', 'price': sl_level, 'description': sl_desc}
                        
            elif pattern_name == 'gartley':
                # Gartley: B = 0.618 XA; BC = 0.382–0.886 AB; D = 0.786 XA
                # PRZ = zbieżność 0.786 XA + AB=CD; Klasyczny: TP-1 61.8 AD, TP-2 = 100% AD; SL za X
                if 'XA' in all_fibos and 'AD' in all_fibos:
                    xa_786 = all_fibos['XA']['retracement'].get('0.786', 0)
                    
                    # PRZ na poziomie 0.786 XA (+ AB=CD confluence)
                    if xa_786 > 0:
                        targets['PRZ'] = {
                            'type': 'line',  # Pojedynczy poziom głównie
                            'price': xa_786,
                            'description': f"PRZ: XA(78.6%) + AB=CD - Klasyczny Gartley"
                        }
                    
                    # TP1 i TP2 (klasyczne cele)
                    ad_618 = all_fibos['AD']['retracement'].get('0.618', 0)
                    ad_100 = all_fibos['AD']['retracement'].get('1.0', 0)  # 100% AD
                    if ad_618:
                        targets['TP1'] = {'type': 'line', 'price': ad_618, 'description': "TP1: AD(61.8%) - Klasyczny cel 1"}
                    if ad_100:
                        targets['TP2'] = {'type': 'line', 'price': ad_100, 'description': "TP2: AD(100%) - Klasyczny cel 2"}
                    
                    # SL za X (konserwatywny)
                    targets['SL'] = {'type': 'line', 'price': x_price, 'description': "SL: X level - Konserwatywny SL"}
                        
            elif pattern_name == 'bartley':
                # Bartley: Hybryda Bat-Gartley: XB = 0.618 XA; AC = 0.382–0.886 AB; DB = 1.272–1.618 BC; XD ≈ 0.786
                # („max Bartley" ma spłyconą XD = 0.618); PRZ = 0.786 XD + 1.27 BC; TP-1 50% AD, TP-2 100% AD; SL ≥ 0.786 XD
                if 'XD' in all_fibos and 'BC' in all_fibos and 'AD' in all_fibos:
                    xd_786 = all_fibos['XD']['retracement'].get('0.786', 0)
                    xd_618 = all_fibos['XD']['retracement'].get('0.618', 0)  # Max Bartley
                    bc_1272 = all_fibos['BC']['extension'].get('1.272', 0)  # 127.2%
                    bc_1618 = all_fibos['BC']['extension'].get('1.618', 0)  # 161.8%
                    
                    # PRZ jako strefa między XD (0.786 lub 0.618) a BC (1.272-1.618)
                    prz_levels = []
                    if xd_786 > 0:
                        prz_levels.append(xd_786)
                    if xd_618 > 0:  # Max Bartley option
                        prz_levels.append(xd_618)
                    if bc_1272 > 0:
                        prz_levels.append(bc_1272)
                    if bc_1618 > 0:
                        prz_levels.append(bc_1618)
                    
                    if prz_levels:
                        targets['PRZ'] = {
                            'type': 'zone',
                            'min_price': min(prz_levels),
                            'max_price': max(prz_levels),
                            'description': f"PRZ: XD(61.8-78.6%) + BC(127.2-161.8%) - Bartley hybrid"
                        }
                    
                    # TP1 i TP2
                    ad_50 = all_fibos['AD']['retracement'].get('0.5', 0)
                    ad_100 = all_fibos['AD']['retracement'].get('1.0', 0)
                    if ad_50:
                        targets['TP1'] = {'type': 'line', 'price': ad_50, 'description': "TP1: AD(50%) - Bartley cel 1"}
                    if ad_100:
                        targets['TP2'] = {'type': 'line', 'price': ad_100, 'description': "TP2: AD(100%) - Bartley cel 2"}
                    
                    # SL ≥ 0.786 XD (lub 0.618 dla max Bartley)
                    sl_level = xd_786 if xd_786 > 0 else xd_618
                    if sl_level > 0:
                        targets['SL'] = {'type': 'line', 'price': sl_level, 'description': f"SL: XD({sl_level:.1f}) - Bartley SL"}
            
            # Jeśli wzorzec nie został rozpoznany, dodaj podstawowe targety
            if not targets and 'AD' in all_fibos:
                # Podstawowe targety dla nierozpoznanych wzorców
                ad_382 = all_fibos['AD']['retracement'].get('0.382', 0)
                ad_618 = all_fibos['AD']['retracement'].get('0.618', 0)
                if ad_382:
                    targets['TP1'] = {'type': 'line', 'price': ad_382, 'description': "TP1: AD(38.2%) - Take Profit 1"}
                if ad_618:
                    targets['TP2'] = {'type': 'line', 'price': ad_618, 'description': "TP2: AD(61.8%) - Take Profit 2"}
                
                # Podstawowy SL na poziomie X lub poza wzorcem
                targets['SL'] = {'type': 'line', 'price': x_price if x_price else d_price, 'description': "SL: Default level - Stop Loss"}
                
        except Exception as e:
            logger.warning(f"Błąd podczas obliczania targetów dla wzorca {pattern_type}: {e}")
        
        return targets
    
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
