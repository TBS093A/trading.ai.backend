import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .api import ApiFacade
from .db.database_facade import DatabaseFacade
from .technical_analysis.technical_analysis_facade import TechnicalAnalysisFacade

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """
    Klasa odpowiedzialna za analizę techniczną assetów.
    Pobiera assety z bazy danych, oblicza harmonic patterns i zapisuje je do bazy.
    """
    
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
    
    async def save_harmonic_patterns_to_database(self, calculated_patterns: List[Dict[str, any]]) -> int:
        """
        Zapisuje wzorce harmoniczne do bazy danych z obiektów HarmonicPatterns.
        
        Args:
            calculated_patterns: Lista słowników z obliczonymi wzorcami
            
        Returns:
            int: Liczba zapisanych wzorców
        """
        saved_count = 0
        
        try:
            technical_analysis_harmonic_patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
              
            for pattern_data in calculated_patterns:
                try:
                    # Sprawdź czy wzorzec już istnieje w bazie danych
                    pattern_exists = await technical_analysis_harmonic_patterns_table.check_pattern_exists(
                        pattern_data['asset_id'],
                        pattern_data['x_point_timestamp'],
                        pattern_data['a_point_timestamp'],
                        pattern_data['b_point_timestamp'],
                        pattern_data['c_point_timestamp'],
                        pattern_data['d_point_timestamp'],
                        interval=pattern_data['interval']
                    )
                    
                    if pattern_exists:
                        logger.debug(f"Wzorzec już istnieje w bazie danych - pomijam")
                        continue
                    
                    # Zapisz do bazy danych
                    new_pattern_id = await technical_analysis_harmonic_patterns_table.create(**pattern_data)
                    
                    if new_pattern_id:
                        saved_count += 1
                        logger.debug(f"Zapisano wzorzec do bazy danych z ID: {new_pattern_id}")
                    else:
                        logger.error(f"Nie udało się zapisać wzorca do bazy danych")
                        
                except Exception as e:
                    logger.error(f"Błąd podczas zapisywania pojedynczego wzorca do bazy danych: {e}")
                    continue
            
            logger.info(f"Zapisano {saved_count} wzorców harmonicznych do bazy danych")
            return saved_count
            
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania wzorców harmonicznych do bazy danych: {e}")
            return saved_count
    
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
                    
                    # KROK 3: Pętla po interwałach
                    for interval, interval_timedelta in self.CHART_INTERVALS.items():
                        try:
                            logger.info(f"Przetwarzam interwał: {interval} dla assetu {asset['asset']}/{asset['quote']}")
                            
                            # Oblicz czasy dla pobierania klines
                            start_time = self._calculate_start_time(interval)
                            end_time = self._calculate_end_time()
                            
                            # KROK 4: Sprawdź czy są jakiekolwiek harmonic patterns
                            existing_patterns = await technical_analysis_harmonic_patterns_table.get_by_timestamp_range_and_asset_id_and_interval(
                                start_timestamp=start_time,
                                end_timestamp=end_time,
                                asset_id=asset['id'],
                                interval=interval
                            )
                            
                            if existing_patterns and len(existing_patterns) > 0:
                                # Są już patterns - pomijamy
                                logger.info(f"Harmonic patterns już istnieją dla tego zakresu - pomijam interwał {interval}")
                                continue
                            
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
                                patterns_saved = await self.save_harmonic_patterns_to_database(calculated_harmonic_patterns)
                                
                                if patterns_saved > 0:
                                    processed_count += patterns_saved
                                    logger.info(f"Zapisano {patterns_saved} wzorców dla {asset['asset']}/{asset['quote']} i interwału {interval}")
                                else:
                                    logger.info(f"Brak nowych wzorców do zapisania dla {asset['asset']}/{asset['quote']} i interwału {interval}")
                                 
                            except Exception as e:
                                error_count += 1
                                logger.error(f"Błąd podczas obliczania HarmonicPatterns dla assetu {asset['asset']} i interwału {interval}: {e}")
                                continue
                            
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Błąd podczas przetwarzania interwału {interval} dla assetu {asset['asset']}: {e}", exc_info=True)
                            continue
                    
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
