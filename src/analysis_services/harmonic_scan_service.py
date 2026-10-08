"""Skan formacji w zakresie czasu (GET /harmonics/{asset_id}/{interval}) i okna pokrycia - src/harmonic_scan.py."""

import logging
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from .. import harmonic_scan
from .klines_source import KlinesSource

logger = logging.getLogger(__name__)

SavePatterns = Callable[[List[Dict[str, Any]]], Awaitable[Dict[str, int]]]
PostFibCluster = Callable[[int, str], Awaitable[int]]


class HarmonicScanService:
    def __init__(self, db, klines: KlinesSource, ta_facade, ta_factory, save_patterns: SavePatterns,
                 post_fib_cluster: PostFibCluster):
        self.db = db
        self.klines = klines
        self.ta_facade = ta_facade
        self.ta_factory = ta_factory
        self.save_patterns = save_patterns
        self.post_fib_cluster = post_fib_cluster

    def indicators(self) -> Dict[str, Any]:
        return {
            'IndicatorRSI': self.ta_factory.get_indicator_rsi_class(),
            'IndicatorMACD': self.ta_factory.get_indicator_macd_class(),
            'IndicatorOBV': self.ta_factory.get_indicator_obv_class()
        }

    def calculate_patterns(self, klines: List[Dict[str, Any]], asset_id: int, symbol: str,
                           interval: str) -> List[Dict[str, Any]]:
        """Formacje XABCD / ABCD dla świec (silnik HarmonicPatterns) - ta sama ścieżka dla syncu i skanu."""
        harmonic_patterns = self.ta_factory.get_harmonic_patterns(asset_id=asset_id, interval=interval)
        self.ta_facade.calculate(
            klines=klines,
            enabled_indicators=self.indicators(),
            enabled_objects={'HarmonicPatterns': harmonic_patterns},
            symbol=symbol,
            interval=interval,
            find_xabcd=True,
            find_abcd=True,
            find_abc=False
        )
        return harmonic_patterns.get_calculated_objects()

    async def record_window(self, asset_id: int, interval: str, klines: List[Dict[str, Any]],
                            patterns_found: int, source: str = 'sync') -> None:
        """Zapisuje okno, które nocny sync przeszukał, jako pokrycie (patrz src/harmonic_scan.py).

        Sync liczy na ostatnich CANDLES_COUNT świecach bez zapasu po lewej, więc pokrycie zaczyna się
        PAD_CANDLES świec później; kończy się na ostatniej zamkniętej świecy.
        """
        try:
            step = harmonic_scan.interval_ms(interval)
        except ValueError:
            return
        now_ms = int(datetime.now().timestamp() * 1000)
        closed = [k['open_time'] for k in klines if k['open_time'] <= now_ms - step]
        if len(closed) <= harmonic_scan.PAD_CANDLES + 1:
            return
        windows_table = self.db.get_factory().get_technical_analysis_harmonic_scan_windows_table()
        await windows_table.create(
            asset_id=asset_id, interval=interval, params_hash=harmonic_scan.params_hash(),
            start_time=closed[harmonic_scan.PAD_CANDLES], end_time=closed[-1],
            patterns_found=patterns_found, source=source,
        )

    async def scan_windows(self, asset_id: int, interval: str,
                           windows: List[Tuple[int, int]]) -> List[Dict[str, Any]]:
        """Liczy formacje w zadanych oknach (z zapasem świec), zapisuje je i zapisuje okna jako pokryte."""
        resolved = await self.klines.resolve(asset_id)
        self.klines.require_api(resolved)
        windows_table = self.db.get_factory().get_technical_analysis_harmonic_scan_windows_table()
        phash = harmonic_scan.params_hash()

        results = []
        for window_start, window_end in windows:
            now_ms = int(datetime.now().timestamp() * 1000)
            fetch_start, fetch_end = harmonic_scan.padded_window(interval, (window_start, window_end), now_ms)
            klines = self.klines.fetch_range(resolved, interval, fetch_start, fetch_end)
            found: List[Dict[str, Any]] = []
            if klines:
                found = harmonic_scan.patterns_inside(
                    self.calculate_patterns(klines, asset_id, resolved.symbol, interval), (window_start, window_end)
                )
                if found:
                    await self.save_patterns(found)
            # "Pusto" też jest wynikiem - okno zapisujemy zawsze, żeby nie liczyć go drugi raz.
            await windows_table.create(
                asset_id=asset_id, interval=interval, params_hash=phash,
                start_time=window_start, end_time=window_end, patterns_found=len(found), source='range',
            )
            results.append({'window': [window_start, window_end], 'klines': len(klines), 'patterns': len(found)})
            logger.info(f"Skan formacji {resolved.symbol} [{interval}] {window_start}..{window_end}: "
                        f"{len(klines)} świec, {len(found)} formacji")

        if any(r['patterns'] for r in results):
            try:
                await self.post_fib_cluster(asset_id, interval)
            except Exception as e:
                logger.warning(f"Fib cluster confluences po skanie zakresu nie powiodły się: {e}")
        return results
