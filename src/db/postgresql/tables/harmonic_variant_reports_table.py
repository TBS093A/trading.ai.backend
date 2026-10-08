from typing import Any, Dict, List, Optional, Sequence
import json
import logging

from .abstract_table import AbstractTable, CleanupRule

logger = logging.getLogger(__name__)


class HarmonicVariantReportsTable(AbstractTable):
    """Raporty porównania wariantów wejścia / zarządzania (src/setup_variants.py) i ich transakcje."""

    KEEP_REPORTS = 5
    EXTRA_TABLES = ("harmonic_variant_trades",)

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS harmonic_variant_reports (
            id SERIAL PRIMARY KEY,
            params_version VARCHAR(32) NOT NULL,
            params_json JSONB NOT NULL,
            cutoff_ms BIGINT,
            pairs_total INTEGER NOT NULL DEFAULT 0,
            pairs_done INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS harmonic_variant_trades (
            id BIGSERIAL PRIMARY KEY,
            report_id INTEGER NOT NULL REFERENCES harmonic_variant_reports(id) ON DELETE CASCADE,
            variant VARCHAR(40) NOT NULL,
            asset_id INTEGER NOT NULL,
            interval VARCHAR(10) NOT NULL,
            pattern_type VARCHAR(40) NOT NULL,
            entry_time BIGINT NOT NULL,
            exit_time BIGINT NOT NULL,
            status VARCHAR(10) NOT NULL,
            r DOUBLE PRECISION NOT NULL,
            strength INTEGER,
            ev DOUBLE PRECISION
        );
        CREATE INDEX IF NOT EXISTS idx_harmonic_variant_trades_report ON harmonic_variant_trades (report_id, variant);
        """

    def cleanup_rules(self) -> List[CleanupRule]:
        return [CleanupRule(
            name="harmonic_variant_reports.old",
            table="harmonic_variant_reports",
            description=f"raporty wariantów starsze niż {self.KEEP_REPORTS} ostatnich (z transakcjami)",
            where="id NOT IN (SELECT id FROM harmonic_variant_reports ORDER BY id DESC LIMIT $1)",
            args=(self.KEEP_REPORTS,),
        )]

    async def create_report(self, params_version: str, params: Dict[str, Any], cutoff_ms: Optional[int],
                            pairs_total: int) -> Optional[int]:
        return await self.fetch_val(
            """INSERT INTO harmonic_variant_reports (params_version, params_json, cutoff_ms, pairs_total)
            VALUES ($1, $2, $3, $4) RETURNING id""",
            params_version, json.dumps(params), cutoff_ms, pairs_total,
        )

    async def add_trades(self, report_id: int, trades: Sequence[Dict[str, Any]]) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if trades:
                    await conn.executemany(
                        """INSERT INTO harmonic_variant_trades (report_id, variant, asset_id, interval, pattern_type,
                            entry_time, exit_time, status, r, strength, ev)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                        [(report_id, t["variant"], t["asset_id"], t["interval"], t["pattern_type"], t["entry_time"],
                          t["exit_time"], t["status"], t["r"], t.get("strength"), t.get("ev")) for t in trades],
                    )
                await conn.execute(
                    "UPDATE harmonic_variant_reports SET pairs_done = pairs_done + 1 WHERE id = $1", report_id
                )

    async def get_report(self, report_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if report_id is None:
            row = await self.fetch_one("SELECT * FROM harmonic_variant_reports ORDER BY id DESC LIMIT 1")
        else:
            row = await self.fetch_one("SELECT * FROM harmonic_variant_reports WHERE id = $1", report_id)
        if row and isinstance(row.get("params_json"), str):
            row["params_json"] = json.loads(row["params_json"])
        return row

    async def get_trades(self, report_id: int) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT variant, asset_id, interval, pattern_type, entry_time, exit_time, status, r, strength, ev "
            "FROM harmonic_variant_trades WHERE report_id = $1", report_id,
        )

    async def create(self, **kwargs) -> Optional[int]:
        return await self.create_report(kwargs["params_version"], kwargs.get("params") or {},
                                        kwargs.get("cutoff_ms"), kwargs.get("pairs_total", 0))

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_report(record_id)

    async def update(self, record_id: int, **kwargs) -> bool:
        return False

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM harmonic_variant_reports WHERE id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT id, params_version, cutoff_ms, pairs_total, pairs_done, created_at FROM harmonic_variant_reports "
            "ORDER BY id DESC LIMIT $1 OFFSET $2", limit, offset,
        )
