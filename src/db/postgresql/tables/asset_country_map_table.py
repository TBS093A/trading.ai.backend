from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)


class AssetCountryMapTable(AbstractTable):
    """Tabela łącząca assets <-> countries (wiele-do-wielu)."""

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS asset_country_map (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,
            UNIQUE(asset_id, country_id),
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE
        );
        """

    async def create(self, asset_id: int, country_id: int) -> Optional[int]:
        try:
            return await self.fetch_val(
                "INSERT INTO asset_country_map (asset_id, country_id) VALUES ($1, $2) "
                "ON CONFLICT (asset_id, country_id) DO NOTHING RETURNING id",
                asset_id, country_id,
            )
        except Exception as e:
            logger.error(f"Błąd tworzenia asset_country_map: {e}", exc_info=True)
            return None

    async def create_many(self, pairs: List[Dict[str, int]]) -> int:
        if not pairs:
            return 0
        try:
            values, params, idx = [], [], 1
            for p in pairs:
                values.append(f"(${idx}, ${idx + 1})")
                params.extend([p['asset_id'], p['country_id']])
                idx += 2
            query = (
                f"INSERT INTO asset_country_map (asset_id, country_id) "
                f"VALUES {', '.join(values)} "
                f"ON CONFLICT (asset_id, country_id) DO NOTHING"
            )
            await self.execute_query(query, *params)
            return len(pairs)
        except Exception as e:
            logger.error(f"Błąd tworzenia wielu asset_country_map: {e}", exc_info=True)
            return 0

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one(
            "SELECT acm.id, acm.asset_id, acm.country_id, c.code as country_code, c.name as country_name "
            "FROM asset_country_map acm JOIN countries c ON acm.country_id = c.id "
            "WHERE acm.id = $1",
            record_id,
        )

    async def get_by_asset_id(self, asset_id: int) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT acm.id, acm.asset_id, acm.country_id, c.code as country_code, c.name as country_name "
            "FROM asset_country_map acm JOIN countries c ON acm.country_id = c.id "
            "WHERE acm.asset_id = $1 ORDER BY c.code",
            asset_id,
        )

    async def get_by_country_id(self, country_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT acm.id, acm.asset_id, acm.country_id, a.asset, a.quote "
            "FROM asset_country_map acm JOIN assets a ON acm.asset_id = a.id "
            "WHERE acm.country_id = $1 ORDER BY a.asset LIMIT $2 OFFSET $3",
            country_id, limit, offset,
        )

    async def update(self, record_id: int, **kwargs) -> bool:
        return False

    async def delete(self, record_id: int) -> bool:
        try:
            await self.execute_query("DELETE FROM asset_country_map WHERE id = $1", record_id)
            return True
        except Exception as e:
            logger.error(f"Błąd usuwania asset_country_map: {e}", exc_info=True)
            return False

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT acm.id, acm.asset_id, acm.country_id, c.code as country_code, c.name as country_name, a.asset "
            "FROM asset_country_map acm "
            "JOIN countries c ON acm.country_id = c.id "
            "JOIN assets a ON acm.asset_id = a.id "
            "ORDER BY a.asset LIMIT $1 OFFSET $2",
            limit, offset,
        )
