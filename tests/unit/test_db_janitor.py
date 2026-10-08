"""
Unit testy fundamentu bazy: kolejność tabel z kluczy obcych, migracje wykonywane raz, schemat
przygotowywany raz na proces, janitor (reguły, partie, dry-run, tabele spoza rejestru,
kompaktowanie okien skanów) i endpointy /maintenance - bez bazy (atrapa puli asyncpg).
"""

import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_maintenance as maintenance_api
from src import harmonic_scan
from src.auth import require_admin
from src.db import janitor as janitor_mod
from src.db.janitor import DatabaseJanitor
from src.db.postgresql import migrations
from src.db.postgresql.database_postgresql import DatabasePostgreSQL
from src.db.postgresql.database_postgresql_factory import (
    LEGACY_TABLES, DatabasePostgreSQLFactory, creation_order,
)
from src.db.postgresql.tables.abstract_table import CleanupRule
from src.db.postgresql.tables.technical_analysis_harmonic_scan_windows_table import (
    TechnicalAnalysisHarmonicScanWindowsTable,
)


class FakeConn:
    def __init__(self, fetchval=None, execute=None, fetch=None):
        self.fetchval = mock.AsyncMock(side_effect=fetchval)
        self.execute = mock.AsyncMock(side_effect=execute or (lambda *a: "OK"))
        self.fetch = mock.AsyncMock(side_effect=fetch or (lambda *a: []))

    @asynccontextmanager
    async def _tx(self):
        yield

    def transaction(self):
        return self._tx()


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def _acquire(self):
        yield self.conn

    def acquire(self):
        return self._acquire()


def run(coro):
    return asyncio.run(coro)


class TestTableOrder(unittest.TestCase):
    def setUp(self):
        self.factory = DatabasePostgreSQLFactory(mock.MagicMock())

    def test_every_table_is_created_after_the_tables_it_references(self):
        queries = self.factory.get_create_table_queries()
        order = self.factory.get_creation_order()
        self.assertEqual(sorted(order), sorted(queries))
        position = {name: i for i, name in enumerate(order)}
        for name, sql in queries.items():
            for ref in creation_order.__globals__["_REFERENCES"].findall(sql):
                if ref in position and ref != name:
                    self.assertLess(position[ref], position[name], f"{name} -> {ref}")

    def test_drop_order_is_the_reverse_plus_legacy_tables(self):
        drop = self.factory.get_drop_order()
        n = len(self.factory.get_creation_order())
        self.assertEqual(drop[:n], list(reversed(self.factory.get_creation_order())))
        self.assertEqual(tuple(drop[n:]), LEGACY_TABLES)

    def test_cycles_are_reported(self):
        with self.assertRaises(ValueError):
            creation_order({"a": "x INT REFERENCES b(id)", "b": "y INT REFERENCES a(id)"})


class TestMigrations(unittest.TestCase):
    def test_runs_only_pending_migrations_and_records_them(self):
        conn = FakeConn(fetch=lambda *a: [{"id": 1}])
        ms = [migrations.Migration(1, "one", "SELECT 1"),
              migrations.Migration(2, "two", ["SELECT 2", "SELECT 3"])]
        self.assertEqual(run(migrations.run_pending(conn, ms)), [2])
        sql = [c.args[0] for c in conn.execute.await_args_list]
        self.assertIn("SELECT 2", sql)
        self.assertIn("SELECT 3", sql)
        self.assertNotIn("SELECT 1", sql)
        record = conn.execute.await_args_list[-1].args
        self.assertEqual(record[1:], (2, "two"))

    def test_ids_must_be_unique_and_increasing(self):
        with self.assertRaises(ValueError):
            migrations.validate([migrations.Migration(2, "a", ""), migrations.Migration(1, "b", "")])
        migrations.validate()  # rejestr w kodzie jest poprawny


class TestSchemaPreparedOncePerProcess(unittest.TestCase):
    def test_second_instance_skips_create_and_seed(self):
        url = "postgresql://unit:test@127.0.0.1:1/once"
        DatabasePostgreSQL._schema_ready.discard(url)
        pool = mock.MagicMock()
        with mock.patch("asyncpg.create_pool", mock.AsyncMock(return_value=pool)), \
                mock.patch.object(DatabasePostgreSQL, "_prepare_schema", mock.AsyncMock()) as prepare:
            run(DatabasePostgreSQL(url).init_db())
            run(DatabasePostgreSQL(url).init_db())
        self.assertEqual(prepare.await_count, 1)
        DatabasePostgreSQL._schema_ready.discard(url)

    def test_failed_preparation_is_retried_by_the_next_instance(self):
        url = "postgresql://unit:test@127.0.0.1:1/retry"
        DatabasePostgreSQL._schema_ready.discard(url)
        with mock.patch("asyncpg.create_pool", mock.AsyncMock(return_value=mock.MagicMock())), \
                mock.patch.object(DatabasePostgreSQL, "_prepare_schema",
                                  mock.AsyncMock(side_effect=[RuntimeError("boom"), None])) as prepare:
            with self.assertRaises(RuntimeError):
                run(DatabasePostgreSQL(url).init_db())
            run(DatabasePostgreSQL(url).init_db())
        self.assertEqual(prepare.await_count, 2)
        DatabasePostgreSQL._schema_ready.discard(url)


def janitor_with(conn, rules, known=("users",)):
    table = mock.MagicMock()
    table.cleanup_rules.return_value = rules
    factory = mock.MagicMock()
    factory.get_all_tables.return_value = {"t": table}
    factory.registered_table_names.return_value = list(known)
    factory.get_technical_analysis_harmonic_scan_windows_table.return_value.compact = mock.AsyncMock(return_value=3)
    db = mock.MagicMock(pool=FakePool(conn))
    db.get_factory.return_value = factory
    return DatabaseJanitor(db, batch_size=10, max_batches=5)


RULE = CleanupRule("t.old", "t", "stare", "v <> $1", ("x",))


class TestJanitor(unittest.TestCase):
    def test_dry_run_only_counts(self):
        conn = FakeConn(fetchval=lambda *a: 25)
        report = run(janitor_with(conn, [RULE]).run(dry_run=True))
        self.assertEqual((report.rules[0].matching, report.rules[0].deleted), (25, 0))
        self.assertFalse(any("DELETE" in c.args[0] for c in conn.execute.await_args_list))
        self.assertEqual(report.compaction, {"scan_windows": 3})

    def test_deletes_in_batches_until_a_short_batch(self):
        statuses = iter(["DELETE 10", "DELETE 10", "DELETE 5"])
        conn = FakeConn(fetchval=lambda *a: 25, execute=lambda *a: next(statuses))
        result = run(janitor_with(conn, [RULE]).run(dry_run=False)).rules[0]
        self.assertEqual(result.deleted, 25)
        self.assertEqual(conn.execute.await_count, 3)
        sql, arg = conn.execute.await_args_list[0].args
        self.assertIn("LIMIT 10", sql)
        self.assertEqual(arg, "x")

    def test_batches_are_capped_per_run(self):
        conn = FakeConn(fetchval=lambda *a: 10 ** 6, execute=lambda *a: "DELETE 10")
        result = run(janitor_with(conn, [RULE]).run(dry_run=False)).rules[0]
        self.assertEqual(result.deleted, 50)  # max_batches=5 x batch_size=10

    def test_a_failing_rule_does_not_stop_the_others(self):
        conn = FakeConn(fetchval=[RuntimeError("bad sql"), 0])
        report = run(janitor_with(conn, [RULE, CleanupRule("t.ok", "t", "", "TRUE")]).run(dry_run=False))
        self.assertEqual(report.rules[0].error, "bad sql")
        self.assertIsNone(report.rules[1].error)

    def test_unknown_tables_skip_the_registry_and_flag_legacy_ones(self):
        rows = [{"name": "users", "approx_rows": 1, "bytes": 1},
                {"name": "schema_migrations", "approx_rows": 1, "bytes": 1},
                {"name": "chart_images", "approx_rows": 9, "bytes": 4096},
                {"name": "mystery", "approx_rows": 0, "bytes": 8192}]
        conn = FakeConn(fetchval=lambda *a: 0, fetch=lambda *a: rows)
        unknown = run(janitor_with(conn, []).run(dry_run=True)).unknown_tables
        self.assertEqual([(t["name"], t["legacy"]) for t in unknown], [("chart_images", True), ("mystery", False)])

    def test_table_rules(self):
        factory = DatabasePostgreSQLFactory(mock.MagicMock())
        rules = {r.name: r for t in factory.get_all_tables().values() for r in t.cleanup_rules()}
        self.assertEqual(set(rules), {"user_sessions.expired", "harmonic_scan_windows.old_params",
                                      "harmonic_setups.old_versions"})
        self.assertEqual(rules["harmonic_scan_windows.old_params"].args, (harmonic_scan.params_hash(),))
        for r in rules.values():
            self.assertNotIn("'", r.where.replace("''", ""))  # wartości tylko jako parametry

    def test_enabled_flag_parsing(self):
        self.assertTrue(janitor_mod.janitor_enabled("TRUE"))
        self.assertFalse(janitor_mod.janitor_enabled(None))
        self.assertFalse(janitor_mod.janitor_enabled("no"))


class TestScanWindowCompaction(unittest.TestCase):
    H = 3_600_000

    def make(self, windows):
        rows = [{"id": i, "start_time": s * self.H, "end_time": e * self.H, "patterns_found": p}
                for i, (s, e, p) in enumerate(windows, 1)]

        def fetch(sql, *args):
            return rows

        conn = FakeConn(fetch=fetch)
        table = TechnicalAnalysisHarmonicScanWindowsTable(FakePool(conn))
        table.fetch_all = mock.AsyncMock(return_value=[{"asset_id": 1, "interval": "1h"}])
        return table, conn

    def test_overlapping_windows_become_one_chain(self):
        span = harmonic_scan.MAX_PATTERN_CANDLES
        table, conn = self.make([(0, 1000, 2), (1000 - span, 2000, 3), (5000, 6000, 1)])
        self.assertEqual(run(table.compact(dry_run=True)), 1)
        conn.execute.assert_not_awaited()

        self.assertEqual(run(table.compact(dry_run=False)), 1)
        calls = [c.args for c in conn.execute.await_args_list]
        self.assertIn("DELETE", calls[0][0])
        self.assertEqual(sorted(calls[0][1]), [1, 2, 3])
        inserted = sorted((c[4] // self.H, c[5] // self.H, c[6]) for c in calls[1:])
        self.assertEqual(inserted, [(0, 2000, 5), (5000, 6000, 1)])

    def test_nothing_to_merge(self):
        table, conn = self.make([(0, 1000, 1), (3000, 4000, 1)])
        self.assertEqual(run(table.compact(dry_run=False)), 0)
        conn.execute.assert_not_awaited()


class TestMaintenanceEndpoints(unittest.TestCase):
    def setUp(self):
        report = janitor_mod.JanitorReport(dry_run=True, rules=[janitor_mod.RuleResult("r", "t", "d", matching=7)])
        self.janitor = mock.MagicMock()
        self.janitor.return_value.run = mock.AsyncMock(return_value=report)
        self.enqueue = mock.MagicMock(return_value="task-1")
        for p in [mock.patch.object(maintenance_api, "get_db", mock.AsyncMock(return_value=mock.MagicMock())),
                  mock.patch.object(maintenance_api, "DatabaseJanitor", self.janitor),
                  mock.patch.object(maintenance_api, "_enqueue_janitor", self.enqueue)]:
            p.start()
            self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(maintenance_api.router, prefix=maintenance_api.PREFIX)
        app.dependency_overrides[require_admin] = lambda: None
        self.client = TestClient(app)

    def test_report_is_a_dry_run(self):
        body = self.client.get("/maintenance/db/janitor").json()
        self.janitor.return_value.run.assert_awaited_once_with(dry_run=True)
        self.assertEqual(body["summary"], {"matching": 7, "deleted": 0})

    def test_manual_run_deletes_only_when_enabled(self):
        with mock.patch.object(maintenance_api.config, "db_janitor_enabled", False):
            self.assertTrue(self.client.post("/maintenance/db/janitor").json()["dry_run"])
        with mock.patch.object(maintenance_api.config, "db_janitor_enabled", True):
            self.assertFalse(self.client.post("/maintenance/db/janitor").json()["dry_run"])
            self.assertTrue(self.client.post("/maintenance/db/janitor", params={"dry_run": True}).json()["dry_run"])

    def test_requires_admin(self):
        app = FastAPI()
        app.include_router(maintenance_api.router, prefix=maintenance_api.PREFIX)
        self.assertIn(TestClient(app).get("/maintenance/db/janitor").status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
