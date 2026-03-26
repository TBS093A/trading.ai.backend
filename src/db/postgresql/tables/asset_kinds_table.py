from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

DEFAULT_ASSET_KINDS = [
    # Sektory giełdowe
    "IT",
    "FINANCE",
    "HEALTHCARE",
    "ENERGY",
    "DEFENSE",
    "INDUSTRIAL",
    "CONSUMER",
    "AUTOMOTIVE",
    "TELECOM",
    "MINING",
    "CHEMICALS",
    "LUXURY",
    "CONGLOMERATE",
    "MEDIA",
    # Indeksy
    "INDEX",
    # ETF per resource
    "ETF_INDEX",
    "ETF_TECH",
    "ETF_BONDS",
    "ETF_OIL",
    "ETF_GOLD",
    "ETF_SILVER",
    "ETF_PLATINUM",
    "ETF_PALLADIUM",
    "ETF_NATGAS",
    "ETF_AGRICULTURE",
    "ETF_MULTI_COMMODITY",
    "ETF_COPPER",
    "ETF_URANIUM",
    "ETF_LITHIUM",
    "ETF_TIMBER",
    "ETF_WATER",
    "ETF_REAL_ESTATE",
    # Futures per resource
    "FUTURES_OIL",
    "FUTURES_GOLD",
    "FUTURES_SILVER",
    "FUTURES_PLATINUM",
    "FUTURES_PALLADIUM",
    "FUTURES_COPPER",
    "FUTURES_NATGAS",
    "FUTURES_CORN",
    "FUTURES_WHEAT",
    "FUTURES_SOYBEAN",
    "FUTURES_COFFEE",
    "FUTURES_SUGAR",
    "FUTURES_COCOA",
    "FUTURES_COTTON",
    "FUTURES_LUMBER",
    "FUTURES_CATTLE",
    "FUTURES_HOGS",
    # Forex i Crypto
    "FOREX",
    "CRYPTO",
]


class AssetKindsTable(AbstractTable):
    """Tabela lookup dla rodzajów assetów (sektory, ETF_*, FUTURES_*, INDEX, FOREX, CRYPTO)."""

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS asset_kinds (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        );
        """

    async def seed_default_records(self) -> Dict[str, Any]:
        existing = await self.fetch_val("SELECT COUNT(*) FROM asset_kinds")
        if existing and existing > 0:
            return {
                'table_name': 'asset_kinds',
                'seeded': False,
                'created_count': 0,
                'total_count': existing,
                'message': 'Asset kinds already seeded',
            }

        created = 0
        for name in DEFAULT_ASSET_KINDS:
            result = await self.fetch_val(
                "INSERT INTO asset_kinds (name) VALUES ($1) ON CONFLICT (name) DO NOTHING RETURNING id",
                name,
            )
            if result:
                created += 1

        total = await self.fetch_val("SELECT COUNT(*) FROM asset_kinds")
        return {
            'table_name': 'asset_kinds',
            'seeded': True,
            'created_count': created,
            'total_count': total or 0,
            'message': f'Seeded {created} asset kinds',
        }

    async def create(self, name: str) -> Optional[int]:
        try:
            return await self.fetch_val(
                "INSERT INTO asset_kinds (name) VALUES ($1) ON CONFLICT (name) DO NOTHING RETURNING id",
                name,
            )
        except Exception as e:
            logger.error(f"Błąd tworzenia asset_kind: {e}", exc_info=True)
            return None

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT id, name FROM asset_kinds WHERE id = $1", record_id)

    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT id, name FROM asset_kinds WHERE name = $1", name)

    async def get_or_create(self, name: str) -> int:
        row = await self.get_by_name(name)
        if row:
            return row['id']
        new_id = await self.create(name)
        if new_id:
            return new_id
        row = await self.get_by_name(name)
        return row['id']

    async def update(self, record_id: int, **kwargs) -> bool:
        if 'name' not in kwargs:
            return False
        try:
            await self.execute_query(
                "UPDATE asset_kinds SET name = $1 WHERE id = $2", kwargs['name'], record_id
            )
            return True
        except Exception as e:
            logger.error(f"Błąd aktualizacji asset_kind: {e}", exc_info=True)
            return False

    async def delete(self, record_id: int) -> bool:
        try:
            await self.execute_query("DELETE FROM asset_kinds WHERE id = $1", record_id)
            return True
        except Exception as e:
            logger.error(f"Błąd usuwania asset_kind: {e}", exc_info=True)
            return False

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT id, name FROM asset_kinds ORDER BY id LIMIT $1 OFFSET $2", limit, offset
        )
