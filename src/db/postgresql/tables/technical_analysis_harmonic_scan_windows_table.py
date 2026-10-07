from typing import Any, Dict, List, Optional
import logging

from .abstract_table import AbstractTable

logger = logging.getLogger(__name__)


class TechnicalAnalysisHarmonicScanWindowsTable(AbstractTable):
    """Okna czasu, w których silnik formacji harmonicznych już szukał (trwały cache skanów).

    Jeden wiersz = "dla asset/interwału i parametrów silnika (params_hash) przeszukano świece z
    [start_time, end_time]; znalezione formacje są w technical_analysis_harmonic_patterns".
    Wiersz zapisuje worker, który liczył - również gdy nie znalazł żadnej formacji, bo "pusto"
    też jest wynikiem, którego nie trzeba liczyć drugi raz. Logika łączenia okien: src/harmonic_scan.py.
    """

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS technical_analysis_harmonic_scan_windows (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            interval VARCHAR(10) NOT NULL,
            params_hash VARCHAR(32) NOT NULL,
            start_time BIGINT NOT NULL,
            end_time BIGINT NOT NULL,
            patterns_found INTEGER NOT NULL DEFAULT 0,
            source VARCHAR(20) NOT NULL DEFAULT 'range',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (start_time < end_time)
        );
        CREATE INDEX IF NOT EXISTS idx_harmonic_scan_windows_lookup
            ON technical_analysis_harmonic_scan_windows (asset_id, interval, params_hash, start_time, end_time);
        """

    async def create(self, asset_id: int, interval: str, params_hash: str, start_time: int, end_time: int,
                     patterns_found: int = 0, source: str = "range") -> Optional[int]:
        try:
            return await self.fetch_val(
                """INSERT INTO technical_analysis_harmonic_scan_windows
                (asset_id, interval, params_hash, start_time, end_time, patterns_found, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                asset_id, interval, params_hash, start_time, end_time, patterns_found, source,
            )
        except Exception as e:
            logger.error(f"Błąd zapisu okna skanu formacji harmonicznych: {e}", exc_info=True)
            return None

    async def get_overlapping(self, asset_id: int, interval: str, params_hash: str,
                              start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """Okna nachodzące na [start_time, end_time] (wołający rozszerza zakres o rozpiętość formacji)."""
        return await self.fetch_all(
            """SELECT id, start_time, end_time, patterns_found, source, created_at
            FROM technical_analysis_harmonic_scan_windows
            WHERE asset_id = $1 AND interval = $2 AND params_hash = $3
              AND start_time <= $5 AND end_time >= $4
            ORDER BY start_time""",
            asset_id, interval, params_hash, start_time, end_time,
        )

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one(
            "SELECT * FROM technical_analysis_harmonic_scan_windows WHERE id = $1", record_id
        )

    async def update(self, record_id: int, **kwargs) -> bool:
        allowed = {"patterns_found", "end_time", "start_time"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(fields))
        await self.execute_query(
            f"UPDATE technical_analysis_harmonic_scan_windows SET {sets} WHERE id = $1",  # nosemgrep: kolumny z allowlisty powyżej
            record_id, *fields.values(),
        )
        return True

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM technical_analysis_harmonic_scan_windows WHERE id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT * FROM technical_analysis_harmonic_scan_windows ORDER BY id DESC LIMIT $1 OFFSET $2",
            limit, offset,
        )
