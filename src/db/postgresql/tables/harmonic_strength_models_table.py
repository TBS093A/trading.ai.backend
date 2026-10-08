from typing import Any, Dict, List, Optional
import json
import logging

from .abstract_table import AbstractTable, CleanupRule

logger = logging.getLogger(__name__)


class HarmonicStrengthModelsTable(AbstractTable):
    """Modele siły formacji (src/pattern_strength.py). Aktywny jest najnowszy wiersz z active = TRUE."""

    KEEP_MODELS = 20   # 10 przebiegów uczenia x (entry, pre)

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS harmonic_strength_models (
            id SERIAL PRIMARY KEY,
            params_version VARCHAR(32) NOT NULL,
            kind VARCHAR(10) NOT NULL DEFAULT 'entry',
            model_json JSONB NOT NULL,
            metrics_json JSONB,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """

    def cleanup_rules(self) -> List[CleanupRule]:
        return [CleanupRule(
            name="harmonic_strength_models.old",
            table="harmonic_strength_models",
            description=f"modele siły starsze niż {self.KEEP_MODELS} ostatnich (każdego rodzaju razem)",
            where="id NOT IN (SELECT id FROM harmonic_strength_models ORDER BY id DESC LIMIT $1)",
            args=(self.KEEP_MODELS,),
        )]

    async def save(self, params_version: str, model: Dict[str, Any], metrics: Dict[str, Any],
                   kind: str = "entry") -> Optional[int]:
        return await self.fetch_val(
            """INSERT INTO harmonic_strength_models (params_version, kind, model_json, metrics_json)
            VALUES ($1, $2, $3, $4) RETURNING id""",
            params_version, kind, json.dumps(model), json.dumps(metrics),
        )

    async def get_active(self, kind: str = "entry") -> Optional[Dict[str, Any]]:
        row = await self.fetch_one(
            "SELECT id, params_version, kind, model_json, metrics_json, created_at FROM harmonic_strength_models "
            "WHERE active AND kind = $1 ORDER BY id DESC LIMIT 1", kind,
        )
        if row:
            for c in ("model_json", "metrics_json"):
                if isinstance(row.get(c), str):
                    row[c] = json.loads(row[c])
        return row

    async def create(self, **kwargs) -> Optional[int]:
        return await self.save(kwargs["params_version"], kwargs["model"], kwargs.get("metrics") or {},
                               kwargs.get("kind", "entry"))

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT * FROM harmonic_strength_models WHERE id = $1", record_id)

    async def update(self, record_id: int, **kwargs) -> bool:
        if "active" in kwargs:
            await self.execute_query("UPDATE harmonic_strength_models SET active = $2 WHERE id = $1",
                                     record_id, bool(kwargs["active"]))
            return True
        return False

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM harmonic_strength_models WHERE id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT id, params_version, metrics_json, active, created_at FROM harmonic_strength_models "
            "ORDER BY id DESC LIMIT $1 OFFSET $2", limit, offset,
        )
