"""Konfluencje liczone po zapisie formacji: Fib cluster (ten sam interwał) i wyższe timeframe'y."""

import logging
from typing import Dict, List

from ..utils.harmonic_patterns import (
    FibClusterDetector, HigherTFFibDetector, HigherTFSRDetector, HigherTFTrendlineDetector, merge_confluences,
)

logger = logging.getLogger(__name__)


class ConfluencePostProcessor:
    def __init__(self, db):
        self.db = db

    async def fib_cluster(self, asset_id: int, interval: str) -> int:
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

    async def higher_tf_fib(self, asset_id: int) -> int:
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

    async def higher_tf_sr(self, asset_id: int, klines_cache: Dict[str, List[Dict]]) -> int:
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
