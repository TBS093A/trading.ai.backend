"""
Unit testy zapisu formacji harmonicznych: klucz punktów zgodny z unikalnym indeksem (migracja 4),
upsert zamiast "zapisz i usuwaj duplikaty", wersja silnika i reguła janitora - bez bazy.
"""

import asyncio
import json
import re
import unittest
from unittest import mock

from src import harmonic_scan
from src.db.postgresql import migrations
from src.db.postgresql.tables.technical_analysis_harmonic_patterns_table import (
    TechnicalAnalysisHarmonicPatternsTable as Table,
)
from src.sync_technical_analysis import TechnicalAnalysis


def pattern(a=2, d=5, x=1, kind="gartley", price=100.0, asset=1, interval="1h"):
    return {"asset_id": asset, "interval": interval, "x_point_timestamp": x, "a_point_timestamp": a,
            "b_point_timestamp": 3, "c_point_timestamp": 4, "d_point_timestamp": d,
            "ta_object_json": {"pattern_type": kind, "is_bullish": True, "is_formed": True,
                               "completion_min_price": price, "completion_max_price": price + 1},
            "confluences_json": None}


def norm(sql):
    return re.sub(r"\s+", "", sql)


class TestPointsKey(unittest.TestCase):
    def test_null_x_and_d_map_to_minus_one_like_the_index(self):
        self.assertEqual(Table.points_key(pattern(x=None, d=None)), (1, "1h", -1, 2, 3, 4, -1))

    def test_upsert_conflict_target_matches_the_unique_index(self):
        index_sql = next(stmt for m in migrations.MIGRATIONS if m.id == 4 for stmt in m.sql
                         if "CREATE UNIQUE INDEX" in stmt)
        columns = index_sql[index_sql.index("(", index_sql.index(" ON ")) + 1: index_sql.rindex(")")]
        self.assertEqual(norm(columns), norm(Table.POINTS_KEY))

    def test_old_engine_rule_ignores_unversioned_rows(self):
        rule = Table(mock.MagicMock()).cleanup_rules()[0]
        self.assertIn("engine_version IS NOT NULL", rule.where)
        self.assertEqual(rule.args, (harmonic_scan.params_hash(),))


class TestSave(unittest.TestCase):
    def run_save(self, patterns, existing):
        table = mock.MagicMock()
        table.points_key = Table.points_key
        table.get_existing_by_points = mock.AsyncMock(return_value={Table.points_key(e): e for e in existing})
        table.upsert_many = mock.AsyncMock(side_effect=lambda rows, v: len(rows))
        ta = TechnicalAnalysis.__new__(TechnicalAnalysis)
        ta.db = mock.MagicMock()
        ta.db.get_factory.return_value.get_technical_analysis_harmonic_patterns_table.return_value = table
        counts = asyncio.run(ta.save_harmonic_patterns_to_database(patterns))
        written = table.upsert_many.await_args.args[0] if table.upsert_many.await_count else []
        return counts, written, table

    def test_new_changed_restamped_and_unchanged(self):
        v = harmonic_scan.params_hash()
        same = {**pattern(a=10), "engine_version": v}
        old_version = {**pattern(a=11), "engine_version": "old"}
        changed = {**pattern(a=12, price=1.0), "engine_version": v}
        counts, written, table = self.run_save(
            [pattern(a=9), pattern(a=10), pattern(a=11), pattern(a=12, price=2.0)],
            [same, old_version, changed],
        )
        self.assertEqual(counts, {"saved": 1, "updated": 1, "skipped": 2})
        self.assertEqual(sorted(p["a_point_timestamp"] for p in written), [9, 11, 12])
        self.assertEqual(table.upsert_many.await_args.args[1], v)

    def test_duplicates_inside_one_batch_are_written_once(self):
        counts, written, _ = self.run_save([pattern(price=1.0), pattern(price=2.0)], [])
        self.assertEqual(counts["saved"], 1)
        self.assertEqual([p["ta_object_json"]["completion_min_price"] for p in written], [2.0])

    def test_empty_batch_touches_nothing(self):
        counts, written, table = self.run_save([], [])
        self.assertEqual(counts, {"saved": 0, "updated": 0, "skipped": 0})
        table.get_existing_by_points.assert_not_awaited()


class FakeConn:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.fetch = mock.AsyncMock(side_effect=lambda *a: self.rows)
        self.executemany = mock.AsyncMock()


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False

        return Ctx()


class TestTableQueries(unittest.TestCase):
    def test_existing_lookup_is_one_query_with_key_arrays(self):
        row = {**pattern(x=None), "id": 7, "ta_object_json": json.dumps({"pattern_type": "abcd"}), "engine_version": "v"}
        conn = FakeConn([row])
        found = asyncio.run(Table(FakePool(conn)).get_existing_by_points([pattern(x=None), pattern(x=None)]))
        args = conn.fetch.await_args.args
        self.assertEqual(args[1:4], ([1], ["1h"], [-1]))
        self.assertEqual(found[Table.points_key(row)]["ta_object_json"], {"pattern_type": "abcd"})

    def test_upsert_serialises_and_keeps_confluences_when_missing(self):
        conn = FakeConn()
        asyncio.run(Table(FakePool(conn)).upsert_many([pattern()], "v1"))
        sql, args = conn.executemany.await_args.args
        self.assertIn("COALESCE(EXCLUDED.confluences_json", sql)
        self.assertEqual(args[0][-1], "v1")
        self.assertIsNone(args[0][8])
        self.assertEqual(json.loads(args[0][7])["pattern_type"], "gartley")


if __name__ == "__main__":
    unittest.main()
