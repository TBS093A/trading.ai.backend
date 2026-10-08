from typing import Any, Dict, List, Optional, Sequence
import logging

from .abstract_table import AbstractTable

logger = logging.getLogger(__name__)

DEFAULT_SETUP_INTERVALS = ("1h", "4h", "1d")


class TrackedAssetsTable(AbstractTable):
    """Assety, które aplikacja liczy sama (ustawiane przez admina w UI).

    patterns_sync    - nocny sync formacji harmonicznych (sync_technical_analysis) liczy ten asset;
                       pozostałe assety liczy tylko skan zakresu na żądanie (GET /harmonics/{id}/{interval}).
    setup_intervals  - interwały, na których co godzinę śledzimy setupy XABCD i ich wyniki
                       (src/harmonic_setups.py) - z nich idą alerty mailowe.
    """

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS tracked_assets (
            asset_id INTEGER PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
            patterns_sync BOOLEAN NOT NULL DEFAULT TRUE,
            setup_intervals TEXT[] NOT NULL DEFAULT ARRAY['1h', '4h', '1d'],
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """

    async def upsert(self, asset_id: int, patterns_sync: bool = True,
                     setup_intervals: Sequence[str] = DEFAULT_SETUP_INTERVALS) -> Optional[Dict[str, Any]]:
        return await self.fetch_one(
            """INSERT INTO tracked_assets (asset_id, patterns_sync, setup_intervals)
            VALUES ($1, $2, $3)
            ON CONFLICT (asset_id) DO UPDATE SET patterns_sync = EXCLUDED.patterns_sync,
                setup_intervals = EXCLUDED.setup_intervals, updated_at = NOW()
            RETURNING asset_id, patterns_sync, setup_intervals, created_at, updated_at""",
            asset_id, patterns_sync, list(setup_intervals),
        )

    async def list_with_assets(self) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT t.asset_id, a.asset, a.quote, a.full_name, t.patterns_sync, t.setup_intervals,
                      t.created_at, t.updated_at
            FROM tracked_assets t JOIN assets a ON a.id = t.asset_id
            ORDER BY a.asset, a.quote"""
        )

    async def get_patterns_sync_asset_ids(self) -> List[int]:
        rows = await self.fetch_all(
            "SELECT asset_id FROM tracked_assets WHERE patterns_sync ORDER BY asset_id"
        )
        return [r["asset_id"] for r in rows]

    async def get_setup_targets(self) -> List[Dict[str, Any]]:
        """Pary (asset, interwał) do śledzenia setupów."""
        return await self.fetch_all(
            """SELECT asset_id, unnest(setup_intervals) AS interval FROM tracked_assets
            WHERE cardinality(setup_intervals) > 0 ORDER BY asset_id"""
        )

    async def create(self, **kwargs) -> Optional[int]:
        row = await self.upsert(**kwargs)
        return row["asset_id"] if row else None

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT * FROM tracked_assets WHERE asset_id = $1", record_id)

    async def update(self, record_id: int, **kwargs) -> bool:
        current = await self.get_by_id(record_id)
        if not current:
            return False
        await self.upsert(record_id, kwargs.get("patterns_sync", current["patterns_sync"]),
                          kwargs.get("setup_intervals", current["setup_intervals"]))
        return True

    async def delete(self, record_id: int) -> bool:
        status = await self.execute_query("DELETE FROM tracked_assets WHERE asset_id = $1", record_id)
        return bool(status) and str(status).endswith(" 1")

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT * FROM tracked_assets ORDER BY asset_id LIMIT $1 OFFSET $2", limit, offset
        )
