"""
Migracje schematu wykonywane raz (tabela schema_migrations).

Tabele nadal powstają przez CREATE TABLE IF NOT EXISTS z klas tabel - migracje są dla zmian,
których tak się nie da zrobić: nowe kolumny w istniejących tabelach, dane startowe, usuwanie
starych tabel. Każda migracja ma stały numer i nazwę; raz wykonana nie wykona się ponownie,
więc jej treści nie zmieniamy - poprawki to nowa migracja.

Całe przygotowanie schematu (CREATE TABLE + migracje + seed) idzie pod blokadą doradczą
Postgresa, bo init_db woła każdy proces API i każde zadanie Celery naraz.
"""

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)

# Stały klucz blokady doradczej przygotowania schematu (dowolna liczba bigint, byle stała).
SCHEMA_LOCK_KEY = 7_406_317_201

MIGRATIONS_TABLE = "schema_migrations"
CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


@dataclass(frozen=True)
class Migration:
    id: int
    name: str
    # SQL (jedno polecenie albo lista) albo async funkcja (connection) -> None
    sql: Union[str, Sequence[str], Callable]


MIGRATIONS: List[Migration] = [
    # Dawne _run_migrations - na istniejących bazach już wykonane, IF NOT EXISTS to uwzględnia.
    Migration(1, "assets_full_name", "ALTER TABLE assets ADD COLUMN IF NOT EXISTS full_name TEXT"),
    # Janitor bazy (src/db/janitor.py) jako proces schedulera, codziennie 03:30 UTC.
    # Cron można wyłączyć / przestawić w istniejącym panelu cron jobów.
    Migration(2, "db_janitor_cron", [
        "INSERT INTO system_sync_job (process) VALUES ('_run_db_janitor') ON CONFLICT (process) DO NOTHING",
        """INSERT INTO cron_system_sync_job (name, system_sync_job_id, hour, minute, timezone, enabled)
           SELECT 'Daily database cleanup - _run_db_janitor', id, 3, 30, 'UTC', TRUE
           FROM system_sync_job WHERE process = '_run_db_janitor'
             AND NOT EXISTS (SELECT 1 FROM cron_system_sync_job c
                             WHERE c.system_sync_job_id = system_sync_job.id)""",
    ]),
    # Śledzone assety i alerty setupów: e-mail użytkownika, startowa lista śledzonych = assety,
    # które mają już setupy (backfill z 2026-10-08), oraz godzinny proces śledzenia setupów.
    Migration(3, "tracked_assets_and_setup_alerts", [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT",
        """INSERT INTO tracked_assets (asset_id, patterns_sync, setup_intervals)
           SELECT asset_id, TRUE, array_agg(DISTINCT interval ORDER BY interval)
           FROM technical_analysis_harmonic_setups GROUP BY asset_id
           ON CONFLICT (asset_id) DO NOTHING""",
        "INSERT INTO system_sync_job (process) VALUES ('_run_harmonic_setups_tracking') ON CONFLICT (process) DO NOTHING",
        """INSERT INTO cron_system_sync_job (name, system_sync_job_id, minute, timezone, enabled)
           SELECT 'Hourly harmonic setups tracking - _run_harmonic_setups_tracking', id, 3, 'UTC', TRUE
           FROM system_sync_job WHERE process = '_run_harmonic_setups_tracking'
             AND NOT EXISTS (SELECT 1 FROM cron_system_sync_job c
                             WHERE c.system_sync_job_id = system_sync_job.id)""",
    ]),
    # Formacje: wersja silnika i jeden wiersz na klucz punktów. Duplikaty usuwamy tą samą regułą co
    # dotychczasowe remove_duplicates przy każdym syncu (zostaje najstarszy wiersz), potem unikalny
    # indeks - od teraz zapis to upsert (ON CONFLICT), nie "zapisz i sprzątaj".
    Migration(4, "harmonic_patterns_engine_version_unique_points", [
        "ALTER TABLE technical_analysis_harmonic_patterns ADD COLUMN IF NOT EXISTS engine_version VARCHAR(32)",
        "ALTER TABLE technical_analysis_harmonic_patterns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        """DELETE FROM technical_analysis_harmonic_patterns WHERE id IN (
             SELECT id FROM (
               SELECT id, row_number() OVER (
                 PARTITION BY asset_id, interval, COALESCE(x_point_timestamp, -1), a_point_timestamp,
                              b_point_timestamp, c_point_timestamp, COALESCE(d_point_timestamp, -1)
                 ORDER BY id) AS rn
               FROM technical_analysis_harmonic_patterns) ranked
             WHERE rn > 1)""",
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_harmonic_patterns_points
           ON technical_analysis_harmonic_patterns (asset_id, interval, COALESCE(x_point_timestamp, -1),
              a_point_timestamp, b_point_timestamp, c_point_timestamp, COALESCE(d_point_timestamp, -1))""",
    ]),
    # Model siły formacji (src/pattern_strength.py) uczony co tydzień na wynikach setupów.
    Migration(5, "strength_model_weekly_fit", [
        "INSERT INTO system_sync_job (process) VALUES ('_run_strength_model_fit') ON CONFLICT (process) DO NOTHING",
        """INSERT INTO cron_system_sync_job (name, system_sync_job_id, day_of_week, hour, minute, timezone, enabled)
           SELECT 'Weekly pattern strength model fit - _run_strength_model_fit', id, 'sun', 4, 0, 'UTC', TRUE
           FROM system_sync_job WHERE process = '_run_strength_model_fit'
             AND NOT EXISTS (SELECT 1 FROM cron_system_sync_job c
                             WHERE c.system_sync_job_id = system_sync_job.id)""",
    ]),
]


def validate(migrations: Sequence[Migration] = MIGRATIONS) -> None:
    ids = [m.id for m in migrations]
    if ids != sorted(set(ids)):
        raise ValueError(f"numery migracji muszą być unikalne i rosnące: {ids}")


async def applied_ids(connection) -> set:
    rows = await connection.fetch("SELECT id FROM schema_migrations")
    return {r["id"] for r in rows}


async def run_pending(connection, migrations: Optional[Sequence[Migration]] = None) -> List[int]:
    """Wykonuje brakujące migracje, każdą w osobnej transakcji. Zwraca numery wykonanych.

    Wołane pod blokadą doradczą (DatabasePostgreSQL._prepare_schema). Błąd migracji przerywa
    kolejne - schemat w połowie migracji jest gorszy niż brak migracji.
    """
    migrations = MIGRATIONS if migrations is None else migrations
    validate(migrations)
    await connection.execute(CREATE_MIGRATIONS_TABLE)
    done = await applied_ids(connection)
    executed = []
    for m in migrations:
        if m.id in done:
            continue
        async with connection.transaction():
            if callable(m.sql):
                await m.sql(connection)
            else:
                for statement in ([m.sql] if isinstance(m.sql, str) else m.sql):
                    await connection.execute(statement)
            await connection.execute(
                "INSERT INTO schema_migrations (id, name) VALUES ($1, $2)", m.id, m.name
            )
        executed.append(m.id)
        logger.info(f"Migracja {m.id} ({m.name}) wykonana")
    return executed
