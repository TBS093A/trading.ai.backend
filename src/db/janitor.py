"""
Janitor bazy - codzienne sprzątanie danych, które straciły znaczenie (zmiana parametrów
silnika, wygasłe sesje, rozdrobnione okna skanów).

Reguły (CleanupRule) deklarują tabele - metoda cleanup_rules(); janitor je zbiera, liczy i
(poza trybem dry-run) usuwa partiami, żeby nie trzymać długich blokad. Do tego kompaktowanie
okien skanów i raport tabel, których nie zna rejestr (dawne funkcje) - tych janitor nigdy sam nie
usuwa, robi to jawna migracja.

Tryb: dry-run, dopóki DB_JANITOR_ENABLED nie jest ustawione na true (src/config.py) - najpierw
widać w logach i w GET /maintenance/db/janitor, co by zostało usunięte.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .postgresql.migrations import MIGRATIONS_TABLE
from .postgresql.tables.abstract_table import CleanupRule

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 5000
DEFAULT_MAX_BATCHES = 200  # na regułę w jednym przebiegu: 1 mln wierszy, reszta jutro


@dataclass
class RuleResult:
    name: str
    table: str
    description: str
    matching: int
    deleted: int = 0
    error: Optional[str] = None


@dataclass
class JanitorReport:
    dry_run: bool
    rules: List[RuleResult] = field(default_factory=list)
    compaction: Dict[str, int] = field(default_factory=dict)
    unknown_tables: List[Dict[str, Any]] = field(default_factory=list)
    duration_s: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "rules": [r.__dict__ for r in self.rules],
            "compaction": self.compaction,
            "unknown_tables": self.unknown_tables,
            "duration_s": round(self.duration_s, 2),
        }


class DatabaseJanitor:
    def __init__(self, db, batch_size: int = DEFAULT_BATCH_SIZE, max_batches: int = DEFAULT_MAX_BATCHES):
        self.db = db
        self.batch_size = batch_size
        self.max_batches = max_batches

    def rules(self) -> List[CleanupRule]:
        out: List[CleanupRule] = []
        for table in self.db.get_factory().get_all_tables().values():
            out.extend(table.cleanup_rules())
        return out

    async def run(self, dry_run: bool = True) -> JanitorReport:
        started = time.monotonic()
        report = JanitorReport(dry_run=dry_run)
        for rule in self.rules():
            report.rules.append(await self._apply(rule, dry_run))
        try:
            windows = self.db.get_factory().get_technical_analysis_harmonic_scan_windows_table()
            report.compaction["scan_windows"] = await windows.compact(dry_run=dry_run)
        except Exception as e:
            logger.error(f"Janitor: kompaktowanie okien skanów nie powiodło się: {e}", exc_info=True)
            report.compaction["scan_windows_error"] = str(e)
        report.unknown_tables = await self.unknown_tables()
        report.duration_s = time.monotonic() - started
        self._log(report)
        return report

    async def _apply(self, rule: CleanupRule, dry_run: bool) -> RuleResult:
        # Nazwa tabeli i warunek pochodzą z kodu (cleanup_rules), nie z inputu; wartości - args.
        count_sql = f"SELECT COUNT(*) FROM {rule.table} WHERE {rule.where}"  # nosemgrep
        delete_sql = (
            f"DELETE FROM {rule.table} WHERE ctid = ANY(ARRAY("  # nosemgrep
            f"SELECT ctid FROM {rule.table} WHERE {rule.where} LIMIT {int(self.batch_size)}))"
        )
        result = RuleResult(rule.name, rule.table, rule.description, matching=0)
        try:
            async with self.db.pool.acquire() as conn:
                result.matching = int(await conn.fetchval(count_sql, *rule.args) or 0)  # nosemgrep
                if dry_run or not result.matching:
                    return result
                for _ in range(self.max_batches):
                    status = await conn.execute(delete_sql, *rule.args)  # nosemgrep
                    n = int(status.split()[-1]) if status else 0
                    result.deleted += n
                    if n < self.batch_size:
                        break
        except Exception as e:
            logger.error(f"Janitor: reguła {rule.name} nie powiodła się: {e}", exc_info=True)
            result.error = str(e)
        return result

    async def unknown_tables(self) -> List[Dict[str, Any]]:
        """Tabele w schemacie public, których nie zna rejestr - kandydaci do usunięcia migracją."""
        known = set(self.db.get_factory().registered_table_names()) | {MIGRATIONS_TABLE}
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT c.relname AS name, c.reltuples::BIGINT AS approx_rows,
                          pg_total_relation_size(c.oid) AS bytes
                   FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                   WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                   ORDER BY bytes DESC"""
            )
        return [dict(r) for r in rows if r["name"] not in known]

    @staticmethod
    def _log(report: JanitorReport) -> None:
        mode = "DRY-RUN" if report.dry_run else "DELETE"
        for r in report.rules:
            logger.info(f"Janitor [{mode}] {r.name}: pasuje {r.matching}, usunięto {r.deleted}"
                        + (f", błąd: {r.error}" if r.error else ""))
        if report.compaction:
            logger.info(f"Janitor [{mode}] kompaktowanie: {report.compaction}")
        if report.unknown_tables:
            names = ", ".join(f"{t['name']} ({t['bytes'] // 1024} KiB)" for t in report.unknown_tables)
            logger.info(f"Janitor: tabele spoza rejestru (usuwane tylko migracją): {names}")
        logger.info(f"Janitor [{mode}] zakończony w {report.duration_s:.1f}s")


def janitor_enabled(value: Optional[str]) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def summarize(rules: Sequence[RuleResult]) -> Dict[str, int]:
    return {"matching": sum(r.matching for r in rules), "deleted": sum(r.deleted for r in rules)}
