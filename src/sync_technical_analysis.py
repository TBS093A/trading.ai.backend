import logging
import traceback
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .api import ApiFacade
from .db.database_facade import DatabaseFacade
from .technical_analysis.technical_analysis_facade import TechnicalAnalysisFacade

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """
    Klasa odpowiedzialna za analizę techniczną assetów.
    Pobiera assety z bazy danych, generuje wykresy i zapisuje je do storage.
    """
    
    CHART_INTERVALS = {
        #"1m": timedelta(minutes=1),
        #"15m": timedelta(minutes=15),
        #"30m": timedelta(minutes=30),
        #"1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
        "3d": timedelta(days=3),
        "1w": timedelta(weeks=1),
        "1M": timedelta(days=31),
        #"3M": timedelta(days=93),
        #"1Y": timedelta(days=365),
    }
    
    CANDLES_COUNT = 500

    # Konfiguracje HarmonicPatterns
    HARMONIC_PATTERNS_DRAW_CONFIGS = [
        {
            'general_fibonacci_levels': {
                'show': True,
                'retracement': True,
                'extension': True
            },
            'all_points_fibonacci_levels': {
                'show': False,
                'retracement': False,
                'extension': False
            },
            'all_fibonacci_targets': {
                'show': False
            }
        },
        {
            'general_fibonacci_levels': {
                'show': False,
                'retracement': False,
                'extension': False
            },
            'all_points_fibonacci_levels': {
                'show': True,
                'retracement': True,
                'extension': True
            },
            'all_fibonacci_targets': {
                'show': False
            }
        },
        {
            'general_fibonacci_levels': {
                'show': False,
                'retracement': False,
                'extension': False
            },
            'all_points_fibonacci_levels': {
                'show': False,
                'retracement': False,
                'extension': False
            },
            'all_fibonacci_targets': {
                'show': True
            }
        },
        {
            'general_fibonacci_levels': {
                'show': False,
                'retracement': False,
                'extension': False
            },
            'all_points_fibonacci_levels': {
                'show': False,
                'retracement': False,
                'extension': False
            },
            'all_fibonacci_targets': {
                'show': False
            }
        }
    ]
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy TechnicalAnalysis
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges_apis = self.api_facade.get_fabric().get_exchanges_apis()
        self.storage_apis = self.api_facade.get_fabric().get_storage_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
        
        # Inicjalizacja fasady analizy technicznej
        self.technical_analysis_facade = TechnicalAnalysisFacade()
        self.technical_analysis_factory = self.technical_analysis_facade.get_technical_analysis_factory()
    
    def _calculate_time_delta_for_assets(self, interval: str) -> timedelta:
        """
        Oblicza time_delta dla pobierania assetów na podstawie interwału.
        
        Args:
            interval: Interwał czasowy (np. "1h", "1D")
            
        Returns:
            timedelta: Obliczony time_delta
        """
        interval_timedelta = self.CHART_INTERVALS[interval]
        # Pomnóż przez połowę liczby świec
        return interval_timedelta * (self.CANDLES_COUNT // 2)
    
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
    
    def _get_fibonacci_type_name(self, harmonic_patterns_config: Dict[str, Any]) -> str:
        """
        Określa typ Fibonacci na podstawie konfiguracji HarmonicPatterns.
        
        Args:
            harmonic_patterns_config: Konfiguracja HarmonicPatterns
            
        Returns:
            str: Nazwa typu Fibonacci
        """
        if harmonic_patterns_config.get('general_fibonacci_levels', {}).get('show', False):
            return "general_fibonacci_levels"
        elif harmonic_patterns_config.get('all_points_fibonacci_levels', {}).get('show', False):
            return "all_points_fibonacci_levels"
        elif harmonic_patterns_config.get('all_fibonacci_targets', {}).get('show', False):
            return "all_fibonacci_targets"
        else:
            return "None"
    
    def _generate_file_name(self, asset: str, quote: str, interval: str, 
                           start_timestamp: int, end_timestamp: int, 
                           candles_count: int, fibonacci_type: str) -> str:
        """
        Generuje nazwę pliku dla obrazu wykresu.
        
        Args:
            asset: Nazwa assetu
            quote: Nazwa quote
            interval: Interwał czasowy
            start_timestamp: Start timestamp w milisekundach
            end_timestamp: End timestamp w milisekundach
            candles_count: Liczba świec
            fibonacci_type: Typ Fibonacci
            
        Returns:
            str: Nazwa pliku z datami w formacie dzień-miesiąc-rok+godzina-minuta-sekunda
        """
        # Konwertuj timestampy z milisekund na sekundy i formatuj
        start_date = datetime.fromtimestamp(start_timestamp / 1000).strftime('%d-%m-%Y+%H-%M-%S')
        end_date = datetime.fromtimestamp(end_timestamp / 1000).strftime('%d-%m-%Y+%H-%M-%S')
        
        return f"{asset}-{quote}/{interval}/range_from_{start_date}_to_{end_date}.candles_{candles_count}.fibonacci_{fibonacci_type}.png"
    
    async def save_harmonic_patterns_to_database(self, calculated_patterns: List[Dict[str, any]]) -> int:
        """
        Zapisuje wzorce harmoniczne do bazy danych z obiektów HarmonicPatterns.
        
        Args:
            harmonic_patterns_objects: Lista obiektów HarmonicPatterns z obliczonymi wzorcami
            
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
    
    async def sync_technical_analysis(self, limit: int = 1, offset: int = 0, asset_id: Optional[int] = None) -> None:
        """
        Synchronizuje analizę techniczną dla assetów i interwałów.
        
        Args:
            limit: Limit assetów do przetworzenia (ignorowany gdy asset_id != None)
            offset: Offset assetów (ignorowany gdy asset_id != None)
            asset_id: Opcjonalne ID konkretnego assetu do synchronizacji (gdy podane, ignoruje limit/offset)
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            logger.info("=== Rozpoczęcie synchronizacji analizy technicznej ===")
            
            # Pobierz tabele z bazy danych
            assets_table = self.db.get_factory().get_assets_table()
            technical_analysis_harmonic_patterns_table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            chart_images_table = self.db.get_factory().get_chart_images_table()
            chart_images_harmonic_patterns_table = self.db.get_factory().get_chart_images_harmonic_patterns_table()
            
            # Pobierz obiekty wskaźników z fabryki
            indicators = {
                'IndicatorRSI': self.technical_analysis_factory.get_indicator_rsi_class(),
                'IndicatorMACD': self.technical_analysis_factory.get_indicator_macd_class(),
                'IndicatorOBV': self.technical_analysis_factory.get_indicator_obv_class()
            }
            
            processed_count = 0
            error_count = 0
            
            # KROK 1: Pobierz assety z bazy danych
            if asset_id is not None:
                # Tryb pojedynczego assetu - ignoruj limit/offset
                asset = await assets_table.get_by_id(asset_id)
                if not asset:
                    logger.error(f"Asset o ID {asset_id} nie został znaleziony")
                    return
                assets = [asset]
                logger.info(f"Tryb pojedynczego assetu: {asset['asset']}/{asset['quote']} (ID: {asset_id})")
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
                            
                            # KROK 7: Przetwórz przez wszystkie obiekty HarmonicPatterns
                            base64_charts = []
                            fibonacci_types = []
                            
                            try:
                                logger.info(f"Przetwarzam HarmonicPatterns dla assetu {asset['asset']} i interwału {interval}")
                                
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
                                
                                # Zapisz nowoobliczone wzorce harmoniczne do bazy danych
                                calculated_harmonic_patterns = harmonic_patterns.get_calculated_objects()
                                await self.save_harmonic_patterns_to_database(calculated_harmonic_patterns)
                                 
                                # KROK 8: Wygeneruj wykres z określonym congfigiem HarmonicPatterns
                                for config in self.HARMONIC_PATTERNS_DRAW_CONFIGS:
                                    harmonic_patterns.set_general_fibonacci_levels_visibility(config['general_fibonacci_levels']['show'], config['general_fibonacci_levels']['retracement'], config['general_fibonacci_levels']['extension'])
                                    harmonic_patterns.set_all_points_fibonacci_levels_visibility(config['all_points_fibonacci_levels']['show'], config['all_points_fibonacci_levels']['retracement'], config['all_points_fibonacci_levels']['extension'])
                                    harmonic_patterns.set_all_fibonacci_targets_visibility(config['all_fibonacci_targets']['show'])
                                    
                                    chart_base64 = self.technical_analysis_facade.create_candlestick_chart(
                                        klines=klines,
                                        enabled_indicators=indicators,
                                        enabled_objects={'HarmonicPatterns': harmonic_patterns},
                                        title=f"{asset['asset']}/{asset['quote']} - {interval}"
                                    )

                                    if chart_base64:
                                        base64_charts.append(chart_base64)
                                        fibonacci_type = self._get_fibonacci_type_name(config)
                                        fibonacci_types.append(fibonacci_type)
                                        logger.info(f"Wygenerowano wykres dla assetu {asset['asset']} i interwału {interval} z konfiguracją: {config}")
                                    else:
                                        logger.warning(f"Nie udało się wygenerować wykresu dla assetu {asset['asset']} i interwału {interval} z konfiguracją: {config}")
                                
                            except Exception as e:
                                logger.error(f"Błąd podczas przetwarzania HarmonicPatterns dla assetu {asset['asset']} i interwału {interval} z konfiguracją: {config}: {e}")
                                continue
                            
                            # KROK 9: Zapisz obrazy do storage i bazy danych
                            if base64_charts:
                                # Pobierz wzorce harmoniczne z bazy danych dla tego zakresu czasowego
                                harmonic_patterns_from_db = await technical_analysis_harmonic_patterns_table.get_by_timestamp_range_and_asset_id_and_interval(
                                    start_timestamp=start_time,
                                    end_timestamp=end_time,
                                    asset_id=asset['id'],
                                    interval=interval
                                )
                                
                                for i, (chart_base64, fibonacci_type) in enumerate(zip(base64_charts, fibonacci_types)):
                                    try:
                                        # Wygeneruj nazwę pliku
                                        file_name = self._generate_file_name(
                                            asset=asset['asset'],
                                            quote=asset['quote'],
                                            interval=interval,
                                            start_timestamp=start_time,
                                            end_timestamp=end_time,
                                            candles_count=len(klines),
                                            fibonacci_type=fibonacci_type
                                        )
                                        
                                        # Upload do wszystkich dostępnych storage
                                        uploaded_to_storage = None
                                        for storage_api in self.storage_apis:
                                            try:
                                                if storage_api.upload_file(file_name, chart_base64):
                                                    uploaded_to_storage = storage_api.STORAGE
                                                    logger.info(f"Zapisano wykres do {storage_api.STORAGE}: {file_name}")
                                                    break
                                            except Exception as e:
                                                logger.error(f"Błąd podczas uploadu do {storage_api.STORAGE}: {e}")
                                                continue
                                        
                                        if uploaded_to_storage:
                                            # Oblicz timestampy z klines
                                            timestamp_start = int(klines[0]['open_time'])
                                            timestamp_end = int(klines[-1]['close_time'])
                                            
                                            # Zapisz do bazy danych
                                            chart_image_id = await chart_images_table.create(
                                                image_file_path=file_name,
                                                image_file_name=file_name.split('/')[-1],
                                                storage=uploaded_to_storage,
                                                interval=interval,
                                                timestamp_start=timestamp_start,
                                                timestamp_end=timestamp_end
                                            )
                                            
                                            if chart_image_id:
                                                # Utwórz relacje z wzorcami harmonicznymi
                                                for pattern in harmonic_patterns_from_db:
                                                    await chart_images_harmonic_patterns_table.create(
                                                        chart_image_id=chart_image_id,
                                                        harmonic_pattern_id=pattern['id']
                                                    )
                                                
                                                processed_count += 1
                                                logger.info(f"Zapisano wykres {i+1}/4 do bazy danych z ID: {chart_image_id}")
                                            else:
                                                error_count += 1
                                                logger.error(f"Nie udało się zapisać wykresu {i+1}/4 do bazy danych")
                                        else:
                                            error_count += 1
                                            logger.error(f"Nie udało się zapisać wykresu {i+1}/4 do żadnego storage")
                                    
                                    except Exception as e:
                                        error_count += 1
                                        logger.error(f"Błąd podczas zapisywania wykresu {i+1}/4: {e}")
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
            logger.info(f"Przetworzono: {processed_count} wykresów")
            logger.info(f"Błędy: {error_count} wykresów")
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy technicznej: {e}", exc_info=True)
            return None
