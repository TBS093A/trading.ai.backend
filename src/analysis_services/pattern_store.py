"""Zapis formacji harmonicznych - jeden wiersz na klucz punktów (migracja 4), wersja silnika."""

import logging
from typing import Any, Dict, List, Tuple

from .. import harmonic_scan

logger = logging.getLogger(__name__)


class PatternStore:
    def __init__(self, db):
        self.db = db

    async def save(self, calculated_patterns: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Zapisuje lub aktualizuje wzorce harmoniczne w bazie danych.

        Klucz formacji = asset, interwał i punkty X..D (unikalny indeks, migracja 4). Istniejący wiersz
        nadpisujemy, gdy obliczenia się zmieniły (patterns_differ) albo policzyła go inna wersja
        silnika (engine_version = harmonic_scan.params_hash()) - wtedy tylko podbijamy wersję.

        Returns:
            Dict[str, int]: saved (nowe), updated (zmienione), skipped (bez zmian)
        """
        counts = {'saved': 0, 'updated': 0, 'skipped': 0}
        if not calculated_patterns:
            return counts
        try:
            table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            engine_version = harmonic_scan.params_hash()
            existing = await table.get_existing_by_points(calculated_patterns)
            to_write: Dict[Tuple, Dict[str, Any]] = {}
            for pattern in calculated_patterns:
                key = table.points_key(pattern)
                current = existing.get(key)
                if current is None:
                    counts['saved'] += key not in to_write
                elif self.patterns_differ(current.get('ta_object_json') or {}, pattern.get('ta_object_json') or {}):
                    counts['updated'] += key not in to_write
                elif current.get('engine_version') != engine_version:
                    counts['skipped'] += key not in to_write   # te same obliczenia - tylko nowa wersja
                else:
                    counts['skipped'] += 1
                    continue
                to_write[key] = pattern  # ta sama formacja dwa razy w paczce - wygrywa ostatnia
            await table.upsert_many(list(to_write.values()), engine_version)
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania wzorców harmonicznych do bazy danych: {e}", exc_info=True)
        logger.info(f"Sync wynik: {counts['saved']} nowych, {counts['updated']} zaktualizowanych, "
                    f"{counts['skipped']} bez zmian")
        return counts

    @staticmethod
    def patterns_differ(existing_json: Dict, new_json: Dict) -> bool:
        """
        Porównuje dwa ta_object_json i sprawdza czy się różnią w kluczowych polach.
        
        Porównywane pola:
        - fibonacci_levels (retracement, extension, fe_extensions, all_targets)
        - points (X, A, B, C, D ceny i indeksy)
        - pattern_type, is_bullish, is_formed
        - retraces
        - completion_min_price, completion_max_price
        
        Args:
            existing_json: Istniejący ta_object_json z bazy danych
            new_json: Nowo obliczony ta_object_json
            
        Returns:
            bool: True jeśli się różnią, False jeśli są identyczne
        """
        # Kluczowe pola do porównania
        key_fields = [
            'pattern_type',
            'is_bullish',
            'is_formed',
            'completion_min_price',
            'completion_max_price',
        ]
        
        # Sprawdź proste pola
        for field in key_fields:
            if existing_json.get(field) != new_json.get(field):
                logger.debug(f"Różnica w polu '{field}': {existing_json.get(field)} vs {new_json.get(field)}")
                return True
        
        # Porównaj fibonacci_levels
        existing_fib = existing_json.get('fibonacci_levels', {})
        new_fib = new_json.get('fibonacci_levels', {})
        
        fib_sections = ['retracement', 'extension', 'fe_extensions', 'all_targets']
        for section in fib_sections:
            existing_section = existing_fib.get(section, {})
            new_section = new_fib.get(section, {})
            
            # Sprawdź czy mają te same klucze
            if set(existing_section.keys()) != set(new_section.keys()):
                logger.debug(f"Różnica w kluczach fibonacci_levels.{section}")
                return True
            
            # Sprawdź wartości (z tolerancją dla float)
            for key in new_section.keys():
                existing_val = existing_section.get(key)
                new_val = new_section.get(key)
                
                # Dla słowników (jak fe_extensions) porównaj zagnieżdżone wartości
                if isinstance(new_val, dict) and isinstance(existing_val, dict):
                    if existing_val.get('price') != new_val.get('price'):
                        logger.debug(f"Różnica w fibonacci_levels.{section}.{key}.price")
                        return True
                    if existing_val.get('level') != new_val.get('level'):
                        logger.debug(f"Różnica w fibonacci_levels.{section}.{key}.level")
                        return True
                    # Nowe pole - leg
                    if existing_val.get('leg') != new_val.get('leg'):
                        logger.debug(f"Różnica w fibonacci_levels.{section}.{key}.leg")
                        return True
                elif existing_val != new_val:
                    logger.debug(f"Różnica w fibonacci_levels.{section}.{key}")
                    return True
        
        # Porównaj retraces
        existing_retraces = existing_json.get('retraces', {})
        new_retraces = new_json.get('retraces', {})
        if existing_retraces != new_retraces:
            logger.debug(f"Różnica w retraces")
            return True
        
        return False
