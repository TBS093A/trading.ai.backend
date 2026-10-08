import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from .api import ApiFacade
from .db.database_facade import DatabaseFacade
from .technical_analysis.technical_analysis_facade import TechnicalAnalysisFacade
from .analysis_services import (
    ConfluencePostProcessor, HarmonicScanService, KlinesSource, PatternStore, SetupTrackingService,
)
from .analysis_services import setup_tracking_service

logger = logging.getLogger(__name__)


class TechnicalAnalysis:
    """
    Nocny sync formacji harmonicznych (śledzone assety) i fasada dla zadań Celery / kontrolerów.

    Logika siedzi w src/analysis_services: świece (KlinesSource), zapis formacji (PatternStore),
    konfluencje po zapisie (ConfluencePostProcessor), skan zakresów (HarmonicScanService) i setupy
    (SetupTrackingService). Serwisy powstają przy użyciu z bieżących self.db / self.api_facade.
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
    SETUP_LIVE_CANDLES = setup_tracking_service.SETUP_LIVE_CANDLES
    SETUP_MAX_CANDLES = setup_tracking_service.SETUP_MAX_CANDLES

    def __init__(self, test_mode: bool = False):
        """
        Args:
            test_mode: Czy uruchamiać w trybie testowym (testowa baza)
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()

        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()

        self.technical_analysis_facade = TechnicalAnalysisFacade()
        self.technical_analysis_factory = self.technical_analysis_facade.get_technical_analysis_factory()

    # ─────────────────────────── serwisy ───────────────────────────

    def _klines_source(self) -> KlinesSource:
        return KlinesSource(self.api_facade, self.db.get_factory())

    def _scan_service(self) -> HarmonicScanService:
        return HarmonicScanService(
            self.db, self._klines_source(), self.technical_analysis_facade, self.technical_analysis_factory,
            save_patterns=self.save_harmonic_patterns_to_database,
            post_fib_cluster=self._update_fib_cluster_confluences,
        )

    async def _with_db(self, coro_fn, *args):
        # Każda instancja TechnicalAnalysis ma własne DatabasePostgreSQL - pula powstaje dopiero w
        # init_db() i należy do pętli zdarzeń zadania Celery, więc ją też tu zamykamy.
        opened_here = getattr(self.db, 'factory', None) is None
        if opened_here:
            await self.db.init_db()
        try:
            return await coro_fn(*args)
        finally:
            if opened_here:
                await self.db.close_db()

    # ─────────────────────────── fasada ───────────────────────────

    async def scan_harmonic_windows(self, asset_id: int, interval: str,
                                    windows: List[Tuple[int, int]]) -> List[Dict[str, Any]]:
        """Formacje w brakujących fragmentach zakresu z GET /harmonics/{asset_id}/{interval}
        (zadanie Celery analysis_tasks.scan_harmonic_windows)."""
        return await self._with_db(self._scan_harmonic_windows, asset_id, interval, windows)

    async def _scan_harmonic_windows(self, asset_id: int, interval: str,
                                     windows: List[Tuple[int, int]]) -> List[Dict[str, Any]]:
        return await self._scan_service().scan_windows(asset_id, interval, windows)

    async def track_harmonic_setups(self, asset_id: int, interval: str, candles: int = SETUP_LIVE_CANDLES,
                                    source: str = 'live') -> Dict[str, Any]:
        """Setupy XABCD i ich wyniki (SetupTrackingService.track)."""
        return await self._with_db(self._track_harmonic_setups, asset_id, interval, candles, source)

    async def _track_harmonic_setups(self, asset_id: int, interval: str, candles: int,
                                     source: str) -> Dict[str, Any]:
        return await SetupTrackingService(self.db, self._klines_source()).track(asset_id, interval, candles, source)

    async def record_harmonic_scan_window(self, asset_id: int, interval: str, klines: List[Dict[str, Any]],
                                          patterns_found: int, source: str = 'sync') -> None:
        await self._scan_service().record_window(asset_id, interval, klines, patterns_found, source)

    async def save_harmonic_patterns_to_database(self, calculated_patterns: List[Dict[str, Any]]) -> Dict[str, int]:
        return await PatternStore(self.db).save(calculated_patterns)

    _patterns_differ = staticmethod(PatternStore.patterns_differ)

    async def _update_fib_cluster_confluences(self, asset_id: int, interval: str) -> int:
        return await ConfluencePostProcessor(self.db).fib_cluster(asset_id, interval)

    async def _update_higher_tf_fib_confluences(self, asset_id: int) -> int:
        return await ConfluencePostProcessor(self.db).higher_tf_fib(asset_id)

    async def _update_higher_tf_sr_confluences(self, asset_id: int, klines_cache: Dict[str, List[Dict]]) -> int:
        return await ConfluencePostProcessor(self.db).higher_tf_sr(asset_id, klines_cache)

    # ─────────────────────────── nocny sync ───────────────────────────

    def _calculate_start_time(self, interval: str) -> int:
        """Początek pobierania świec: teraz - CANDLES_COUNT interwałów (ms)."""
        start_datetime = datetime.now() - (self.CHART_INTERVALS[interval] * self.CANDLES_COUNT)
        return int(start_datetime.timestamp() * 1000)

    def _calculate_end_time(self) -> int:
        """Koniec pobierania świec: teraz (ms)."""
        return int(datetime.now().timestamp() * 1000)

    async def _assets_to_sync(self, limit: int, offset: int, asset_ids: Optional[List[int]]) -> List[Dict[str, Any]]:
        factory = self.db.get_factory()
        assets_table = factory.get_assets_table()
        if asset_ids:
            # Tryb bulk - assety po ID z listy, limit/offset ignorowane
            ids = asset_ids
        else:
            # Nocny sync liczy tylko śledzone assety (tracked_assets.patterns_sync, ustawiane w UI);
            # pozostałe liczy skan zakresu na żądanie z wykresu.
            ids = (await factory.get_tracked_assets_table().get_patterns_sync_asset_ids())[offset:offset + limit]
        assets, missing = [], []
        for asset_id in ids:
            asset = await assets_table.get_by_id(asset_id)
            if asset:
                assets.append(asset)
            else:
                missing.append(asset_id)
        if missing:
            logger.warning(f"Nie znaleziono assetów o ID: {missing}")
        return assets

    async def _sync_asset_interval(self, asset: Dict[str, Any], resolved, interval: str, scan: HarmonicScanService,
                                   source: KlinesSource) -> Tuple[Optional[List[Dict]], int]:
        """Jeden (asset, interwał): świece -> formacje -> zapis -> Fib cluster -> okno pokrycia.
        Zwraca (świece do post-processingu wyższych TF, liczba nowych/zmienionych formacji)."""
        klines = source.fetch_recent(
            resolved, interval, self._calculate_start_time(interval), self._calculate_end_time(), self.CANDLES_COUNT
        )
        if not klines:
            logger.warning(f"Nie udało się pobrać klines dla {resolved.symbol} [{interval}]")
            return None, 0
        patterns = scan.calculate_patterns(klines, asset['id'], resolved.symbol, interval)
        result = await self.save_harmonic_patterns_to_database(patterns)
        changed = result.get('saved', 0) + result.get('updated', 0)
        logger.info(f"{resolved.symbol} [{interval}]: {result.get('saved', 0)} nowych, "
                    f"{result.get('updated', 0)} zaktualizowanych, {result.get('skipped', 0)} bez zmian")
        await self._update_fib_cluster_confluences(asset['id'], interval)
        # Okno przeszukane przez sync jako pokrycie dla GET /harmonics
        await scan.record_window(asset['id'], interval, klines, len(patterns))
        return klines, changed

    async def sync_technical_analysis(self, limit: int = 1, offset: int = 0, asset_ids: Optional[List[int]] = None) -> None:
        """
        Synchronizuje formacje harmoniczne dla śledzonych assetów (albo `asset_ids`) na wszystkich
        interwałach CHART_INTERVALS, potem konfluencje z wyższych timeframe'ów.

        Args:
            limit: Limit assetów do przetworzenia (ignorowany gdy asset_ids != None)
            offset: Offset assetów (ignorowany gdy asset_ids != None)
            asset_ids: Opcjonalna lista ID assetów do synchronizacji (gdy podana, ignoruje limit/offset)
        """
        try:
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            logger.info("=== Rozpoczęcie synchronizacji analizy technicznej ===")

            assets = await self._assets_to_sync(limit, offset, asset_ids)
            if not assets:
                logger.info("Brak assetów do przetworzenia")
                return
            names = ", ".join(f"{a['asset']}/{a['quote']}" for a in assets)
            logger.info(f"Assety do przetworzenia ({len(assets)}): {names}")

            scan = self._scan_service()
            source = self._klines_source()
            processed_count = 0
            error_count = 0
            for asset in assets:
                try:
                    resolved = await source.resolve(asset['id'])
                    # Świece per interwał - do post-processingu cross-TF S/R
                    klines_cache: Dict[str, List[Dict]] = {}
                    for interval in self.CHART_INTERVALS:
                        try:
                            klines, changed = await self._sync_asset_interval(asset, resolved, interval, scan, source)
                            if klines:
                                klines_cache[interval] = klines
                            processed_count += changed
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Błąd podczas przetwarzania interwału {interval} dla assetu "
                                         f"{asset['asset']}: {e}", exc_info=True)
                    # Post-processing cross-interval, po wszystkich interwałach assetu
                    await self._update_higher_tf_fib_confluences(asset['id'])
                    await self._update_higher_tf_sr_confluences(asset['id'], klines_cache)
                except Exception as e:
                    error_count += 1
                    logger.error(f"Błąd podczas przetwarzania assetu {asset['asset']}: {e}", exc_info=True)

            logger.info(f"=== Synchronizacja analizy technicznej zakończona: {processed_count} nowych/zmienionych "
                        f"wzorców, błędy: {error_count} ===")
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy technicznej: {e}", exc_info=True)
            return None
