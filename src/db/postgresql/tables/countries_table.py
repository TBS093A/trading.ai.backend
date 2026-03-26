from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

DEFAULT_COUNTRIES = [
    ("US", "United States"),
    ("JP", "Japan"),
    ("CN", "China"),
    ("DE", "Germany"),
    ("GB", "United Kingdom"),
    ("PL", "Poland"),
    ("RU", "Russia"),
    ("IL", "Israel"),
    ("FR", "France"),
    ("CH", "Switzerland"),
    ("EU", "European Union"),
    ("CMDTY", "Commodities"),
    ("FX", "Forex"),
    ("CRYPTO", "Cryptocurrency"),
]


class CountriesTable(AbstractTable):
    """Tabela lookup dla krajów / regionów rynkowych."""

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS countries (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        );
        """

    async def seed_default_records(self) -> Dict[str, Any]:
        existing = await self.fetch_val("SELECT COUNT(*) FROM countries")
        if existing and existing > 0:
            return {
                'table_name': 'countries',
                'seeded': False,
                'created_count': 0,
                'total_count': existing,
                'message': 'Countries already seeded',
            }

        created = 0
        for code, name in DEFAULT_COUNTRIES:
            result = await self.fetch_val(
                "INSERT INTO countries (code, name) VALUES ($1, $2) ON CONFLICT (code) DO NOTHING RETURNING id",
                code, name,
            )
            if result:
                created += 1

        total = await self.fetch_val("SELECT COUNT(*) FROM countries")
        return {
            'table_name': 'countries',
            'seeded': True,
            'created_count': created,
            'total_count': total or 0,
            'message': f'Seeded {created} countries',
        }

    async def create(self, code: str, name: str) -> Optional[int]:
        try:
            return await self.fetch_val(
                "INSERT INTO countries (code, name) VALUES ($1, $2) ON CONFLICT (code) DO NOTHING RETURNING id",
                code, name,
            )
        except Exception as e:
            logger.error(f"Błąd tworzenia country: {e}", exc_info=True)
            return None

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one(
            "SELECT id, code, name FROM countries WHERE id = $1", record_id
        )

    async def get_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        return await self.fetch_one(
            "SELECT id, code, name FROM countries WHERE code = $1", code
        )

    async def get_or_create(self, code: str, name: Optional[str] = None) -> int:
        row = await self.get_by_code(code)
        if row:
            return row['id']
        display_name = name or code
        new_id = await self.create(code, display_name)
        if new_id:
            return new_id
        row = await self.get_by_code(code)
        return row['id']

    async def update(self, record_id: int, **kwargs) -> bool:
        fields, params, idx = [], [], 1
        for f in ('code', 'name'):
            if f in kwargs:
                fields.append(f"{f} = ${idx}")
                params.append(kwargs[f])
                idx += 1
        if not fields:
            return False
        params.append(record_id)
        try:
            await self.execute_query(
                f"UPDATE countries SET {', '.join(fields)} WHERE id = ${idx}", *params
            )
            return True
        except Exception as e:
            logger.error(f"Błąd aktualizacji country: {e}", exc_info=True)
            return False

    async def delete(self, record_id: int) -> bool:
        try:
            await self.execute_query("DELETE FROM countries WHERE id = $1", record_id)
            return True
        except Exception as e:
            logger.error(f"Błąd usuwania country: {e}", exc_info=True)
            return False

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT id, code, name FROM countries ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset,
        )
