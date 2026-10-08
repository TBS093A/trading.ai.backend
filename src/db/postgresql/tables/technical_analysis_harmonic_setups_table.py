from typing import Any, Dict, List, Optional, Sequence
import json
import logging

from .abstract_table import AbstractTable, CleanupRule

logger = logging.getLogger(__name__)

FINAL_STATUSES = ("win", "loss", "expired", "no_entry", "invalidated")
COLUMNS = (
    "asset_id", "interval", "params_version", "pattern_type", "is_bullish", "spacing",
    "x_time", "a_time", "b_time", "c_time", "points_json", "prz_min", "prz_max", "created_time",
    "status", "entry_time", "entry_price", "sl", "tp1", "tp2", "targets_source", "exit_time",
    "r_multiple", "tp2_reached", "mfe_r", "mae_r", "confluences_json", "pre_confluences_json", "source",
)
# Pola wyniku - jedyne, które upsert zmienia w istniejącym, jeszcze nierozstrzygniętym setupie.
OUTCOME_COLUMNS = (
    "status", "entry_time", "entry_price", "sl", "tp1", "tp2", "targets_source", "exit_time",
    "r_multiple", "tp2_reached", "mfe_r", "mae_r", "confluences_json", "pre_confluences_json",
)
JSON_COLUMNS = ("points_json", "confluences_json", "pre_confluences_json")
GROUPABLE = ("pattern_type", "interval", "asset_id", "is_bullish", "source", "targets_source", "spacing")


class TechnicalAnalysisHarmonicSetupsTable(AbstractTable):
    """Setupy formacji harmonicznych (X..C + PRZ znane w chwili created_time) i ich wyniki.

    Logika: src/harmonic_setups.py. Jeden wiersz na (asset, interwał, wersja parametrów, typ,
    punkty X..C). Wiersz z wynikiem ostatecznym nie jest już nadpisywany.
    """

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS technical_analysis_harmonic_setups (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            interval VARCHAR(10) NOT NULL,
            params_version VARCHAR(32) NOT NULL,
            pattern_type VARCHAR(40) NOT NULL,
            is_bullish BOOLEAN NOT NULL,
            spacing INTEGER NOT NULL,
            x_time BIGINT NOT NULL,
            a_time BIGINT NOT NULL,
            b_time BIGINT NOT NULL,
            c_time BIGINT NOT NULL,
            points_json JSONB NOT NULL,
            prz_min DOUBLE PRECISION NOT NULL,
            prz_max DOUBLE PRECISION NOT NULL,
            created_time BIGINT NOT NULL,
            status VARCHAR(16) NOT NULL,
            entry_time BIGINT,
            entry_price DOUBLE PRECISION,
            sl DOUBLE PRECISION,
            tp1 DOUBLE PRECISION,
            tp2 DOUBLE PRECISION,
            targets_source VARCHAR(16),
            exit_time BIGINT,
            r_multiple DOUBLE PRECISION,
            tp2_reached BOOLEAN NOT NULL DEFAULT FALSE,
            mfe_r DOUBLE PRECISION,
            mae_r DOUBLE PRECISION,
            confluences_json JSONB,
            pre_confluences_json JSONB,
            source VARCHAR(10) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (asset_id, interval, params_version, pattern_type, x_time, a_time, b_time, c_time)
        );
        CREATE INDEX IF NOT EXISTS idx_harmonic_setups_open
            ON technical_analysis_harmonic_setups (asset_id, interval, params_version, status);
        CREATE INDEX IF NOT EXISTS idx_harmonic_setups_stats
            ON technical_analysis_harmonic_setups (params_version, pattern_type, interval, status);
        """

    # Ile serii (params_version) zostaje: bieżąca + tyle najnowszych poprzednich (do porównań).
    KEEP_PREVIOUS_VERSIONS = 1

    def cleanup_rules(self) -> List[CleanupRule]:
        from ....harmonic_setups import params_version

        return [CleanupRule(
            name="harmonic_setups.old_versions",
            table="technical_analysis_harmonic_setups",
            description=f"setupy ze starych reguł symulacji (zostaje bieżąca i {self.KEEP_PREVIOUS_VERSIONS} poprzednia seria)",
            where="""params_version <> $1 AND params_version NOT IN (
                SELECT params_version FROM technical_analysis_harmonic_setups
                WHERE params_version <> $1 GROUP BY params_version
                ORDER BY MAX(updated_at) DESC LIMIT $2)""",
            args=(params_version(), self.KEEP_PREVIOUS_VERSIONS),
        )]

    async def upsert_many(self, rows: Sequence[Dict[str, Any]]) -> int:
        """Wstawia nowe setupy i aktualizuje wynik tych, które nie są jeszcze rozstrzygnięte."""
        if not rows:
            return 0
        placeholders = ", ".join(f"${i + 1}" for i in range(len(COLUMNS)))
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in OUTCOME_COLUMNS)
        final = ", ".join(f"'{s}'" for s in FINAL_STATUSES)
        query = (
            f"INSERT INTO technical_analysis_harmonic_setups ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT (asset_id, interval, params_version, pattern_type, x_time, a_time, b_time, c_time) "
            f"DO UPDATE SET {updates}, updated_at = NOW() "
            f"WHERE technical_analysis_harmonic_setups.status NOT IN ({final})"
        )  # nosemgrep: nazwy kolumn i statusy to stałe z tego modułu, wartości idą parametrami
        args = [
            tuple(json.dumps(r[c]) if c in JSON_COLUMNS and r.get(c) is not None else r.get(c)
                  for c in COLUMNS)
            for r in rows
        ]
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)
        return len(rows)

    async def get_final_keys(self, asset_id: int, interval: str, params_version: str,
                             since_c_time: int) -> set:
        """Klucze setupów już rozstrzygniętych (nie trzeba ich ponownie symulować)."""
        rows = await self.fetch_all(
            f"""SELECT pattern_type, x_time, a_time, b_time, c_time
            FROM technical_analysis_harmonic_setups
            WHERE asset_id = $1 AND interval = $2 AND params_version = $3 AND c_time >= $4
              AND status IN ({", ".join(f"'{s}'" for s in FINAL_STATUSES)})""",  # nosemgrep: stałe
            asset_id, interval, params_version, since_c_time,
        )
        return {(r["pattern_type"], r["x_time"], r["a_time"], r["b_time"], r["c_time"]) for r in rows}

    async def get_oldest_unresolved_x_time(self, asset_id: int, interval: str, params_version: str) -> Optional[int]:
        return await self.fetch_val(
            f"""SELECT MIN(x_time) FROM technical_analysis_harmonic_setups
            WHERE asset_id = $1 AND interval = $2 AND params_version = $3
              AND status NOT IN ({", ".join(f"'{s}'" for s in FINAL_STATUSES)})""",  # nosemgrep: stałe
            asset_id, interval, params_version,
        )

    async def get_unresolved_statuses(self, asset_id: int, interval: str, params_version: str,
                                      since_c_time: int) -> Dict[tuple, str]:
        """Statusy nierozstrzygniętych setupów (klucz jak w get_final_keys) - do wykrywania zmian."""
        rows = await self.fetch_all(
            f"""SELECT pattern_type, x_time, a_time, b_time, c_time, status
            FROM technical_analysis_harmonic_setups
            WHERE asset_id = $1 AND interval = $2 AND params_version = $3 AND c_time >= $4
              AND status NOT IN ({", ".join(f"'{s}'" for s in FINAL_STATUSES)})""",  # nosemgrep: stałe
            asset_id, interval, params_version, since_c_time,
        )
        return {(r["pattern_type"], r["x_time"], r["a_time"], r["b_time"], r["c_time"]): r["status"] for r in rows}

    async def status_counts(self, asset_id: int, interval: str, params_version: str) -> Dict[str, int]:
        rows = await self.fetch_all(
            """SELECT status, COUNT(*) AS n FROM technical_analysis_harmonic_setups
            WHERE asset_id = $1 AND interval = $2 AND params_version = $3 GROUP BY status""",
            asset_id, interval, params_version,
        )
        return {r["status"]: int(r["n"]) for r in rows}

    async def status_totals(self, params_version: str) -> Dict[str, int]:
        rows = await self.fetch_all(
            "SELECT status, COUNT(*) AS n FROM technical_analysis_harmonic_setups WHERE params_version = $1 "
            "GROUP BY status", params_version,
        )
        return {r["status"]: int(r["n"]) for r in rows}

    async def decided_by_week(self, params_version: str) -> List[Dict[str, Any]]:
        """Dane uczące modelu siły w czasie: rozstrzygnięte setupy na tydzień wejścia."""
        return await self.fetch_all(
            """SELECT date_trunc('week', to_timestamp(entry_time / 1000.0)) AS week,
                      COUNT(*) AS trades,
                      COUNT(*) FILTER (WHERE status = 'win') AS wins,
                      AVG(r_multiple) AS avg_r
            FROM technical_analysis_harmonic_setups
            WHERE params_version = $1 AND status IN ('win', 'loss', 'expired') AND entry_time IS NOT NULL
            GROUP BY 1 ORDER BY 1""",
            params_version,
        )

    async def find_by_points(self, asset_id: int, interval: str, params_version: str,
                             keys: Sequence[tuple]) -> Dict[tuple, Dict[str, Any]]:
        """Setupy o tych samych punktach X..C co formacje z wykresu - klucz (typ, x, a, b, c)."""
        keys = list({tuple(k) for k in keys})
        if not keys:
            return {}
        cols = list(zip(*keys))
        rows = await self.fetch_all(
            """SELECT s.id, s.pattern_type, s.x_time, s.a_time, s.b_time, s.c_time, s.status, s.entry_time,
                      s.entry_price, s.sl, s.tp1, s.tp2, s.exit_time, s.r_multiple, s.created_time,
                      s.prz_min, s.prz_max
            FROM technical_analysis_harmonic_setups s
            JOIN unnest($4::text[], $5::bigint[], $6::bigint[], $7::bigint[], $8::bigint[]) AS k(p, x, a, b, c)
              ON s.pattern_type = k.p AND s.x_time = k.x AND s.a_time = k.a AND s.b_time = k.b AND s.c_time = k.c
            WHERE s.asset_id = $1 AND s.interval = $2 AND s.params_version = $3""",
            asset_id, interval, params_version, *[list(c) for c in cols],
        )
        return {(r["pattern_type"], r["x_time"], r["a_time"], r["b_time"], r["c_time"]): r for r in rows}

    async def tracked_assets(self, params_version: str) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT s.asset_id, a.asset, a.quote, s.interval, COUNT(*) AS setups,
                      MIN(s.created_time) AS first_created, MAX(s.created_time) AS last_created
            FROM technical_analysis_harmonic_setups s JOIN assets a ON a.id = s.asset_id
            WHERE s.params_version = $1
            GROUP BY s.asset_id, a.asset, a.quote, s.interval
            ORDER BY a.asset, s.interval""",
            params_version,
        )

    async def stats(self, params_version: str, group_by: Sequence[str],
                    filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        group = [g for g in group_by if g in GROUPABLE]
        where, args = ["params_version = $1"], [params_version]
        for col in GROUPABLE:
            if filters.get(col) is not None:
                args.append(filters[col])
                where.append(f"{col} = ${len(args)}")
        select_group = ", ".join(group) + ", " if group else ""
        query = f"""
        SELECT {select_group}
               COUNT(*) AS setups,
               COUNT(*) FILTER (WHERE status = 'win') AS wins,
               COUNT(*) FILTER (WHERE status = 'loss') AS losses,
               COUNT(*) FILTER (WHERE status = 'expired') AS expired,
               COUNT(*) FILTER (WHERE status = 'no_entry') AS no_entry,
               COUNT(*) FILTER (WHERE status = 'invalidated') AS invalidated,
               COUNT(*) FILTER (WHERE status IN ('waiting', 'open')) AS pending,
               COUNT(*) FILTER (WHERE status IN ('win', 'loss', 'expired') AND tp2_reached) AS tp2_reached,
               AVG(r_multiple) FILTER (WHERE status IN ('win', 'loss', 'expired')) AS avg_r,
               AVG(mfe_r) FILTER (WHERE status IN ('win', 'loss', 'expired')) AS avg_mfe_r,
               AVG(mae_r) FILTER (WHERE status IN ('win', 'loss', 'expired')) AS avg_mae_r
        FROM technical_analysis_harmonic_setups
        WHERE {" AND ".join(where)}
        {"GROUP BY " + ", ".join(group) if group else ""}
        ORDER BY setups DESC
        """  # nosemgrep: kolumny grupowania z allowlisty GROUPABLE, wartości filtrów parametrami
        return await self.fetch_all(query, *args)

    async def list(self, asset_id: int, interval: str, params_version: str, status: Optional[str] = None,
                   limit: int = 200, statuses: Optional[Sequence[str]] = None, offset: int = 0,
                   newest_exit_first: bool = False) -> List[Dict[str, Any]]:
        args: List[Any] = [asset_id, interval, params_version, limit, offset]
        extra = ""
        if statuses:
            args.append(list(statuses))
            extra = " AND status = ANY($6::text[])"
        elif status:
            args.append(status)
            extra = " AND status = $6"
        # Zamknięte sekcje (wygrane / przegrane / śmieciowe): najświeższe wyjście na górze.
        order = "COALESCE(exit_time, created_time) DESC, id DESC" if newest_exit_first else "created_time DESC, id DESC"
        rows = await self.fetch_all(
            f"""SELECT * FROM technical_analysis_harmonic_setups
            WHERE asset_id = $1 AND interval = $2 AND params_version = $3{extra}
            ORDER BY {order} LIMIT $4 OFFSET $5""",  # nosemgrep: warunek i kolejność ze stałych, wartości parametrami
            *args,
        )
        for r in rows:
            for c in JSON_COLUMNS:
                if isinstance(r.get(c), str):
                    r[c] = json.loads(r[c])
        return rows

    async def create(self, **kwargs) -> Optional[int]:
        await self.upsert_many([kwargs])
        return None

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT * FROM technical_analysis_harmonic_setups WHERE id = $1", record_id)

    async def update(self, record_id: int, **kwargs) -> bool:
        return False  # wyniki zmienia tylko upsert_many

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM technical_analysis_harmonic_setups WHERE id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT * FROM technical_analysis_harmonic_setups ORDER BY id DESC LIMIT $1 OFFSET $2", limit, offset
        )
