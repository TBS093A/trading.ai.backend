import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .api import ApiFacade
from .db.database_facade import DatabaseFacade
from .technical_analysis.technical_analysis_facade import TechnicalAnalysisFacade
from .utils.harmonic_patterns import (
    FibClusterDetector, HigherTFFibDetector, merge_confluences,
    HigherTFSRDetector, HigherTFTrendlineDetector,
)

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """
    Klasa odpowiedzialna za analizę techniczną assetów.
    Pobiera assety z bazy danych, oblicza harmonic patterns i zapisuje je do bazy.
    """
    
    async def cleanup_all_duplicates(self) -> Dict[str, int]:
        """
        Usuwa wszystkie duplikaty wzorców harmonicznych z bazy danych.
        
        Duplikat jest definiowany jako wzorzec o tych samych:
        - asset_id, interval, x/a/b/c/d_point_timestamp
        
        Zachowuje najstarszy rekord (najniższe ID), usuwa nowsze duplikaty.
        
        Returns:
            Dict z liczbą usuniętych duplikatów
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            logger.info("=== Rozpoczęcie czyszczenia duplikatów ===")
            
            ta_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            
            # Policz duplikaty przed usunięciem
            duplicates_count = await ta_table.count_duplicates()
            logger.info(f"Znaleziono {duplicates_count} duplikatów do usunięcia")
            
            if duplicates_count == 0:
                logger.info("Brak duplikatów - baza jest czysta")
                return {'duplicates_removed': 0}
            
            # Usuń duplikaty
            removed = await ta_table.remove_duplicates()
            
            logger.info(f"=== Czyszczenie duplikatów zakończone: usunięto {removed} rekordów ===")
            
            return {'duplicates_removed': removed}
            
        except Exception as e:
            logger.error(f"Błąd podczas czyszczenia duplikatów: {e}", exc_info=True)
            return {'duplicates_removed': 0, 'error': str(e)}
    
    CHART_INTERVALS = {
        "1m": timedelta(minutes=1),
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
        "3d": timedelta(days=3),
        "1w": timedelta(weeks=1),
        "1M": timedelta(days=31),
        "3M": timedelta(days=93),
        "1Y": timedelta(days=365),
    }
    
    CANDLES_COUNT = 500
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy TechnicalAnalysis
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges_apis = self.api_facade.get_fabric().get_exchanges_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
        
        # Inicjalizacja fasady analizy technicznej
        self.technical_analysis_facade = TechnicalAnalysisFacade()
        self.technical_analysis_factory = self.technical_analysis_facade.get_technical_analysis_factory()
    
    def _calculate_start_time(self, interval: str) -> int:
        """
        Oblicza start_time dla pobierania klines.
        
        Args:
            interval: Interwał czasowy (np. "1h", "1D")
            
        Returns:
            int: Start time w milisekundach
        """
        interval_timedelta = self.CHART_INTERVALS[interval]
        # Oblicz czas startowy: teraz - (liczba świec * interwał)
        start_datetime = datetime.now() - (interval_timedelta * self.CANDLES_COUNT)
        return int(start_datetime.timestamp() * 1000)
    
    def _calculate_end_time(self) -> int:
        """
        Oblicza end_time dla pobierania klines.
        
        Returns:
            int: End time w milisekundach (aktualny czas)
        """
        return int(datetime.now().timestamp() * 1000)
    
    async def save_harmonic_patterns_to_database(self, calculated_patterns: List[Dict[str, any]]) -> Dict[str, int]:
        """
        Zapisuje lub aktualizuje wzorce harmoniczne w bazie danych.
        
        Jeśli wzorzec o tych samych punktach (X, A, B, C, D) i interwale już istnieje,
        porównuje ta_object_json i aktualizuje jeśli obliczenia się różnią.
        
        Args:
            calculated_patterns: Lista słowników z obliczonymi wzorcami
            
        Returns:
            Dict[str, int]: Słownik z liczbą zapisanych i zaktualizowanych wzorców
        """
        saved_count = 0
        updated_count = 0
        skipped_count = 0
        
        try:
            technical_analysis_harmonic_patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
              
            for pattern_data in calculated_patterns:
                try:
                    # Pobierz istniejący wzorzec (jeśli istnieje)
                    existing_pattern = await technical_analysis_harmonic_patterns_table.get_by_point_timestamps(
                        pattern_data['asset_id'],
                        pattern_data['x_point_timestamp'],
                        pattern_data['a_point_timestamp'],
                        pattern_data['b_point_timestamp'],
                        pattern_data['c_point_timestamp'],
                        pattern_data['d_point_timestamp'],
                        interval=pattern_data['interval']
                    )
                    
                    if existing_pattern:
                        # Wzorzec istnieje - sprawdź czy ta_object_json się różni
                        existing_ta_json = existing_pattern.get('ta_object_json', {})
                        new_ta_json = pattern_data.get('ta_object_json', {})
                        
                        # Porównaj kluczowe pola (pomijamy niektóre dynamiczne pola)
                        if self._patterns_differ(existing_ta_json, new_ta_json):
                            # Aktualizuj istniejący wzorzec
                            new_confluences = pattern_data.get('confluences_json')
                            update_kwargs = {'ta_object_json': new_ta_json}
                            if new_confluences:
                                update_kwargs['confluences_json'] = new_confluences
                            update_success = await technical_analysis_harmonic_patterns_table.update(
                                existing_pattern['id'],
                                **update_kwargs
                            )
                            if update_success:
                                updated_count += 1
                                logger.debug(f"Zaktualizowano wzorzec ID {existing_pattern['id']} - obliczenia się zmieniły")
                            else:
                                logger.error(f"Nie udało się zaktualizować wzorca ID {existing_pattern['id']}")
                        else:
                            skipped_count += 1
                            logger.debug(f"Wzorzec ID {existing_pattern['id']} - bez zmian, pomijam")
                    else:
                        # Nowy wzorzec - zapisz do bazy danych
                        new_pattern_id = await technical_analysis_harmonic_patterns_table.create(**pattern_data)
                        
                        if new_pattern_id:
                            saved_count += 1
                            logger.debug(f"Zapisano nowy wzorzec do bazy danych z ID: {new_pattern_id}")
                        else:
                            logger.error(f"Nie udało się zapisać wzorca do bazy danych")
                        
                except Exception as e:
                    logger.error(f"Błąd podczas zapisywania/aktualizacji pojedynczego wzorca: {e}")
                    continue
            
            logger.info(f"Sync wynik: {saved_count} nowych, {updated_count} zaktualizowanych, {skipped_count} bez zmian")
            return {
                'saved': saved_count,
                'updated': updated_count,
                'skipped': skipped_count
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania wzorców harmonicznych do bazy danych: {e}")
            return {
                'saved': saved_count,
                'updated': updated_count,
                'skipped': skipped_count
            }
    
    def _patterns_differ(self, existing_json: Dict, new_json: Dict) -> bool:
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

    async def _update_fib_cluster_confluences(self, asset_id: int, interval: str) -> int:
        """
        Post-processing: wykrywa klastry Fibonacci na tym samym interwale.
        Aktualizuje confluences_json patternów, przy których D wypada w zbieżności
        wielu poziomów Fib z innych patternów.

        Returns:
            Liczba zaktualizowanych rekordów.
        """
        updated = 0
        try:
            table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            all_patterns = await table.get_by_asset_id_and_interval(asset_id, interval, limit=500)
            if not all_patterns or len(all_patterns) < 2:
                return 0

            for pattern in all_patterns:
                result = FibClusterDetector.detect(all_patterns, pattern['id'])
                if result is None:
                    continue

                merged = merge_confluences(
                    pattern.get('confluences_json'),
                    [result],
                    replace_types=['fib_cluster'],
                )
                await table.update(pattern['id'], confluences_json=merged)
                updated += 1

            if updated:
                logger.info(f"Fib Cluster: zaktualizowano {updated} patternów (asset_id={asset_id}, interval={interval})")
        except Exception as e:
            logger.error(f"Błąd Fib Cluster (asset_id={asset_id}, interval={interval}): {e}", exc_info=True)
        return updated

    async def _update_higher_tf_fib_confluences(self, asset_id: int) -> int:
        """
        Post-processing: wykrywa pokrycia D z poziomami Fib z wyższych timeframe'ów.
        Uruchamiany po przetworzeniu WSZYSTKICH interwałów danego assetu.

        Returns:
            Liczba zaktualizowanych rekordów.
        """
        updated = 0
        try:
            table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            all_patterns = await table.get_by_asset_id(asset_id, limit=2000)
            if not all_patterns:
                return 0

            # Grupuj po interwale
            by_interval: Dict[str, List] = {}
            for p in all_patterns:
                iv = p.get('interval')
                if iv:
                    by_interval.setdefault(iv, []).append(p)

            if len(by_interval) < 2:
                return 0

            for pattern in all_patterns:
                iv = pattern.get('interval')
                if not iv:
                    continue
                result = HigherTFFibDetector.detect(by_interval, pattern, iv)
                if result is None:
                    continue

                merged = merge_confluences(
                    pattern.get('confluences_json'),
                    [result],
                    replace_types=['higher_tf_fib'],
                )
                await table.update(pattern['id'], confluences_json=merged)
                updated += 1

            if updated:
                logger.info(f"Higher TF Fib: zaktualizowano {updated} patternów (asset_id={asset_id})")
        except Exception as e:
            logger.error(f"Błąd Higher TF Fib (asset_id={asset_id}): {e}", exc_info=True)
        return updated

    async def _update_higher_tf_sr_confluences(self, asset_id: int, klines_cache: Dict[str, List[Dict]]) -> int:
        """
        Post-processing: wykrywa S/R i trendline z wyższych timeframe'ów.
        Wymaga klines_cache zebranego podczas sync loop.

        Returns:
            Liczba zaktualizowanych rekordów.
        """
        updated = 0
        if not klines_cache or len(klines_cache) < 2:
            return 0

        try:
            table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            all_patterns = await table.get_by_asset_id(asset_id, limit=2000)
            if not all_patterns:
                return 0

            replace_types = [
                'higher_tf_support_zone', 'higher_tf_resistance_zone',
                'higher_tf_support_trendline', 'higher_tf_resistance_trendline',
            ]

            for pattern in all_patterns:
                iv = pattern.get('interval')
                if not iv:
                    continue

                new_entries = []

                sr_result = HigherTFSRDetector.detect(klines_cache, pattern, iv)
                if sr_result is not None:
                    new_entries.append(sr_result)

                tl_result = HigherTFTrendlineDetector.detect(klines_cache, pattern, iv)
                if tl_result is not None:
                    new_entries.append(tl_result)

                if not new_entries:
                    continue

                merged = merge_confluences(
                    pattern.get('confluences_json'),
                    new_entries,
                    replace_types=replace_types,
                )
                await table.update(pattern['id'], confluences_json=merged)
                updated += 1

            if updated:
                logger.info(f"Higher TF S/R: zaktualizowano {updated} patternów (asset_id={asset_id})")
        except Exception as e:
            logger.error(f"Błąd Higher TF S/R (asset_id={asset_id}): {e}", exc_info=True)
        return updated

    async def sync_technical_analysis(self, limit: int = 1, offset: int = 0, asset_ids: Optional[List[int]] = None) -> None:
        """
        Synchronizuje analizę techniczną dla assetów i interwałów.
        Oblicza harmonic patterns i zapisuje je do bazy danych.
        
        Args:
            limit: Limit assetów do przetworzenia (ignorowany gdy asset_ids != None)
            offset: Offset assetów (ignorowany gdy asset_ids != None)
            asset_ids: Opcjonalna lista ID assetów do synchronizacji (gdy podana, ignoruje limit/offset)
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            logger.info("=== Rozpoczęcie synchronizacji analizy technicznej ===")
            
            # Pobierz tabele z bazy danych
            assets_table = self.db.get_factory().get_assets_table()
            technical_analysis_harmonic_patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            
            # Pobierz obiekty wskaźników z fabryki (używane w calculate)
            indicators = {
                'IndicatorRSI': self.technical_analysis_factory.get_indicator_rsi_class(),
                'IndicatorMACD': self.technical_analysis_factory.get_indicator_macd_class(),
                'IndicatorOBV': self.technical_analysis_factory.get_indicator_obv_class()
            }
            
            processed_count = 0
            error_count = 0
            
            # KROK 1: Pobierz assety z bazy danych
            if asset_ids is not None and len(asset_ids) > 0:
                # Tryb bulk - pobierz assety po ID z listy, ignoruj limit/offset
                assets = []
                not_found_ids = []
                for asset_id in asset_ids:
                    asset = await assets_table.get_by_id(asset_id)
                    if asset:
                        assets.append(asset)
                    else:
                        not_found_ids.append(asset_id)
                
                if not_found_ids:
                    logger.warning(f"Nie znaleziono assetów o ID: {not_found_ids}")
                
                if assets:
                    asset_names = [f"{a['asset']}/{a['quote']} (ID: {a['id']})" for a in assets]
                    logger.info(f"Tryb bulk - {len(assets)} assetów: {', '.join(asset_names)}")
            else:
                # Tryb wielu assetów - użyj limit/offset
                assets = await assets_table.get_all(limit=limit, offset=offset)
            
            if not assets:
                logger.info("Brak assetów do przetworzenia")
                return
            
            logger.info(f"Znaleziono {len(assets)} assetów do przetworzenia")
            
            # KROK 2: Pętla po assetach
            for asset in assets:
                try:
                    logger.info(f"=== Przetwarzam asset: {asset['asset']}/{asset['quote']} ===")
                    
                    # KROK 2.5: Usuń duplikaty dla tego assetu (cleanup przed sync)
                    duplicates_removed = await technical_analysis_harmonic_patterns_table.remove_duplicates(asset['id'])
                    if duplicates_removed > 0:
                        logger.info(f"Usunięto {duplicates_removed} duplikatów dla {asset['asset']}/{asset['quote']}")
                    
                    # Cache klines per interval — do post-processingu cross-TF S/R
                    klines_cache: Dict[str, List[Dict]] = {}
                    
                    # KROK 3: Pętla po interwałach
                    for interval, interval_timedelta in self.CHART_INTERVALS.items():
                        try:
                            logger.info(f"Przetwarzam interwał: {interval} dla assetu {asset['asset']}/{asset['quote']}")
                            
                            # Oblicz czasy dla pobierania klines
                            start_time = self._calculate_start_time(interval)
                            end_time = self._calculate_end_time()
                            
                            # KROK 4: Sprawdź czy są jakiekolwiek harmonic patterns (info only)
                            existing_patterns = await technical_analysis_harmonic_patterns_table.get_by_timestamp_range_and_asset_id_and_interval(
                                start_timestamp=start_time,
                                end_timestamp=end_time,
                                asset_id=asset['id'],
                                interval=interval
                            )
                            
                            existing_count = len(existing_patterns) if existing_patterns else 0
                            if existing_count > 0:
                                # Są już patterns - obliczamy i aktualizujemy jeśli się zmieniły
                                logger.info(f"Znaleziono {existing_count} istniejących patternów - sprawdzam aktualizacje dla interwału {interval}")
                            else:
                                # Brak patterns - generujemy nowe
                                logger.info(f"Brak harmonic patterns - generuję nowe dla interwału {interval}")
                            
                            # KROK 5: Pobierz klines z giełd
                            klines = None
                            for exchange in self.exchanges_apis:
                                try:
                                    logger.info(f"Pobieram klines z {exchange.__class__.__name__} dla {asset['asset']}/{asset['quote']}")
                                    klines = exchange._get_klines(
                                        base_currency=asset['asset'],
                                        quote_currency=asset['quote'],
                                        interval=interval,
                                        start_time=start_time,
                                        end_time=end_time,
                                        limit=self.CANDLES_COUNT
                                    )
                                    
                                    if klines and len(klines) > 0:
                                        logger.info(f"Pobrano {len(klines)} klines z {exchange.__class__.__name__}")
                                        break
                                    else:
                                        logger.warning(f"Brak klines z {exchange.__class__.__name__}")
                                        
                                except Exception as e:
                                    logger.error(f"Błąd podczas pobierania klines z {exchange.__class__.__name__}: {e}")
                                    continue
                            
                            if not klines or len(klines) == 0:
                                logger.warning(f"Nie udało się pobrać klines dla assetu {asset['asset']}/{asset['quote']} i interwału {interval}")
                                continue
                            
                            klines_cache[interval] = klines
                            
                            # KROK 6: Stwórz obiekty HarmonicPatterns
                            harmonic_patterns = self.technical_analysis_factory.get_harmonic_patterns(
                                asset_id=asset['id'], 
                                interval=interval
                            )
                            
                            # KROK 7: Oblicz harmonic patterns
                            try:
                                logger.info(f"Obliczam HarmonicPatterns dla assetu {asset['asset']} i interwału {interval}")
                                
                                # Oblicz wskaźniki i obiekty analizy technicznej
                                self.technical_analysis_facade.calculate(
                                    klines=klines,
                                    enabled_indicators=indicators,
                                    enabled_objects={'HarmonicPatterns': harmonic_patterns},
                                    symbol=f"{asset['asset']}/{asset['quote']}",
                                    interval=interval,
                                    find_xabcd=True,
                                    find_abcd=True,
                                    find_abc=False
                                )
                                
                                # KROK 8: Zapisz obliczone wzorce harmoniczne do bazy danych
                                calculated_harmonic_patterns = harmonic_patterns.get_calculated_objects()
                                sync_result = await self.save_harmonic_patterns_to_database(calculated_harmonic_patterns)
                                
                                saved = sync_result.get('saved', 0)
                                updated = sync_result.get('updated', 0)
                                skipped = sync_result.get('skipped', 0)
                                
                                if saved > 0 or updated > 0:
                                    processed_count += saved + updated
                                    logger.info(f"{asset['asset']}/{asset['quote']} [{interval}]: {saved} nowych, {updated} zaktualizowanych, {skipped} bez zmian")
                                else:
                                    logger.info(f"{asset['asset']}/{asset['quote']} [{interval}]: brak zmian ({skipped} wzorców bez zmian)")
                                
                                # KROK 8.1: Post-processing — Fib Cluster (same interval)
                                await self._update_fib_cluster_confluences(asset['id'], interval)
                                 
                            except Exception as e:
                                error_count += 1
                                logger.error(f"Błąd podczas obliczania HarmonicPatterns dla assetu {asset['asset']} i interwału {interval}: {e}")
                                continue
                            
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Błąd podczas przetwarzania interwału {interval} dla assetu {asset['asset']}: {e}", exc_info=True)
                            continue
                    
                    # KROK 9: Post-processing — Higher TF Fib (cross-interval, po wszystkich interwałach)
                    await self._update_higher_tf_fib_confluences(asset['id'])
                    
                    # KROK 10: Post-processing — Higher TF S/R i Trendline (cross-interval, wymaga klines cache)
                    await self._update_higher_tf_sr_confluences(asset['id'], klines_cache)
                    
                except Exception as e:
                    error_count += 1
                    logger.error(f"Błąd podczas przetwarzania assetu {asset['asset']}: {e}", exc_info=True)
                    continue
            
            logger.info(f"=== Synchronizacja analizy technicznej zakończona ===")
            logger.info(f"Zapisano: {processed_count} wzorców harmonicznych")
            logger.info(f"Błędy: {error_count}")
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy technicznej: {e}", exc_info=True)
            return None
