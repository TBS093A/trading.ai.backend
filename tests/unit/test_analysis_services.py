"""
Unit testy src/analysis_services (podział TechnicalAnalysis): wybór giełdy i świec (KlinesSource)
oraz orkiestracja nocnego syncu - bez bazy i sieci.
"""

import asyncio
import unittest
from unittest import mock

from src.analysis_services import KlinesSource, ResolvedAsset
from src.sync_technical_analysis import TechnicalAnalysis


class Binance:
    def __init__(self, klines=()):
        self.klines = list(klines)
        self._get_klines = mock.MagicMock(side_effect=lambda **kw: self.klines)


class Kucoin(Binance):
    pass


def source(exchanges, all_apis=(), asset=None):
    factory = mock.MagicMock()
    factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(
        return_value=asset if asset is not None else {"id": 1, "asset": "BTC", "quote": "USDT"})
    factory.get_asset_exchanges_table.return_value.get_by_asset_id = mock.AsyncMock(
        return_value=[{"exchange_name": e} for e in exchanges])
    facade = mock.MagicMock()
    facade.get_fabric.return_value.get_exchanges_apis.return_value = list(all_apis)
    return KlinesSource(facade, factory), facade


class TestKlinesSource(unittest.TestCase):
    def test_resolves_the_exchange_like_the_chart(self):
        src, facade = source(["KuCoin", "Binance"])
        resolved = asyncio.run(src.resolve(1))
        self.assertEqual((resolved.exchange, resolved.symbol), ("BINANCE", "BTC/USDT"))
        self.assertIs(resolved.api, facade.get_fabric.return_value.get_binance_api.return_value)

    def test_unsupported_exchange_has_no_api_and_range_fetch_refuses(self):
        src, _ = source(["MEXC"])
        resolved = asyncio.run(src.resolve(1))
        self.assertIsNone(resolved.api)
        with self.assertRaises(ValueError):
            src.fetch_range(resolved, "1h", 0, 1)

    def test_missing_asset(self):
        src, _ = source([], asset={})
        with self.assertRaises(ValueError):
            asyncio.run(src.resolve(9))

    def test_recent_prefers_the_asset_exchange_then_falls_back(self):
        own = Binance(klines=[])
        other = Kucoin(klines=[{"open_time": 1}])
        src, facade = source([], all_apis=[Binance(), other])
        resolved = ResolvedAsset({"asset": "X", "quote": "Y"}, "BINANCE", own)
        self.assertEqual(src.fetch_recent(resolved, "1h", 0, 10, 500), [{"open_time": 1}])
        own._get_klines.assert_called_once()
        # Binance z listy wszystkich giełd jest pomijany - to ten sam typ co giełda assetu
        self.assertEqual(facade.get_fabric.return_value.get_exchanges_apis.call_count, 1)

    def test_recent_without_asset_exchange_tries_all_and_survives_errors(self):
        broken = Binance()
        broken._get_klines.side_effect = RuntimeError("down")
        src, _ = source([], all_apis=[broken, Kucoin(klines=[{"open_time": 2}])])
        resolved = ResolvedAsset({"asset": "X", "quote": "Y"}, None, None)
        self.assertEqual(src.fetch_recent(resolved, "1h", 0, 10, 500), [{"open_time": 2}])


class TestNightlySync(unittest.TestCase):
    def make(self, tracked=(1, 2)):
        factory = mock.MagicMock()
        factory.get_tracked_assets_table.return_value.get_patterns_sync_asset_ids = mock.AsyncMock(
            return_value=list(tracked))
        factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(
            side_effect=lambda i: {"id": i, "asset": f"A{i}", "quote": "USDT"} if i != 404 else None)
        ta = TechnicalAnalysis.__new__(TechnicalAnalysis)
        ta.db = mock.MagicMock(factory=factory, get_factory=mock.MagicMock(return_value=factory))
        ta.api_facade = mock.MagicMock()
        ta.technical_analysis_facade = mock.MagicMock()
        ta.technical_analysis_factory = mock.MagicMock()
        ta._sync_asset_interval = mock.AsyncMock(return_value=([{"open_time": 1}], 2))
        ta._update_higher_tf_fib_confluences = mock.AsyncMock()
        ta._update_higher_tf_sr_confluences = mock.AsyncMock()
        return ta

    def run_sync(self, ta, **kw):
        with mock.patch("src.sync_technical_analysis.KlinesSource") as ks:
            ks.return_value.resolve = mock.AsyncMock(side_effect=lambda i: ResolvedAsset({"id": i}, "BINANCE", object()))
            asyncio.run(ta.sync_technical_analysis(**kw))

    def test_syncs_tracked_assets_on_every_interval_then_higher_tf(self):
        ta = self.make()
        self.run_sync(ta, limit=10, offset=0)
        self.assertEqual(ta._sync_asset_interval.await_count, 2 * len(TechnicalAnalysis.CHART_INTERVALS))
        self.assertEqual([c.args[0] for c in ta._update_higher_tf_fib_confluences.await_args_list], [1, 2])
        cache = ta._update_higher_tf_sr_confluences.await_args_list[0].args[1]
        self.assertEqual(set(cache), set(TechnicalAnalysis.CHART_INTERVALS))

    def test_limit_offset_page_through_tracked_assets(self):
        ta = self.make(tracked=(1, 2, 3))
        self.run_sync(ta, limit=1, offset=1)
        self.assertEqual([c.args[0] for c in ta._update_higher_tf_fib_confluences.await_args_list], [2])

    def test_explicit_asset_ids_skip_missing_ones(self):
        ta = self.make()
        self.run_sync(ta, asset_ids=[404, 7])
        self.assertEqual([c.args[0] for c in ta._update_higher_tf_fib_confluences.await_args_list], [7])

    def test_one_failing_interval_does_not_stop_the_asset(self):
        ta = self.make(tracked=(1,))
        ta._sync_asset_interval.side_effect = [RuntimeError("bad")] + [([{"open_time": 1}], 0)] * 20
        self.run_sync(ta, limit=10, offset=0)
        self.assertEqual(ta._sync_asset_interval.await_count, len(TechnicalAnalysis.CHART_INTERVALS))
        ta._update_higher_tf_sr_confluences.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
