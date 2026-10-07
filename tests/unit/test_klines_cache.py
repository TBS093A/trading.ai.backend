"""
Unit testy cache'u klines (src/klines_cache.py), endpointu GET /exchanges/klines/{asset_id}/{interval}
i zakresu czasu w yahoofinance._get_klines - bez bazy, sieci i credentiali (PRE-MERGE gate).
"""

import asyncio
import gzip
import threading
import time
import unittest
from unittest import mock

import pandas as pd
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import controller_rest_domain_exchanges as exchanges
from src.auth import require_auth
from src.klines_cache import (
    CACHE_CONTROL_HEAD,
    CACHE_CONTROL_HISTORY,
    COMPACT_FIELDS,
    KLINE_FIELDS,
    KlinesGZipMiddleware,
    KlinesPageCache,
    is_closed_history,
    to_compact,
    to_objects,
    to_rows,
)

HOUR = 3600 * 1000


def binance_kline(open_time, close=1.0):
    return {
        "open_time": open_time, "open": 1.0, "high": 2.0, "low": 0.5, "close": close,
        "volume": 10.0, "close_time": open_time + HOUR - 1, "quote_volume": 10.0,
        "trades": 3, "taker_buy_base_volume": 4.0, "taker_buy_quote_volume": 4.0,
    }


def yahoo_kline(open_time):
    return {
        "open_time": open_time, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
        "volume": 10.0, "close_time": open_time, "quote_volume": 15.0,
    }


def run(coro):
    return asyncio.run(coro)


class TestConversions(unittest.TestCase):
    def test_object_format_round_trips_for_both_exchanges(self):
        for klines in ([binance_kline(0), binance_kline(HOUR)], [yahoo_kline(0)]):
            with self.subTest(fields=len(klines[0])):
                self.assertEqual(to_objects(to_rows(klines)), klines)

    def test_compact_format(self):
        rows = to_rows([binance_kline(0, close=1.25)])
        self.assertEqual(to_compact(rows), [[0, 1.0, 2.0, 0.5, 1.25, 10.0]])
        self.assertEqual(COMPACT_FIELDS, KLINE_FIELDS[:6])


class TestClosedHistory(unittest.TestCase):
    now = 100 * HOUR + HOUR // 2  # in the middle of the candle opened at 100h

    def rows(self, *open_times):
        return to_rows([binance_kline(t) for t in open_times])

    def test_head_page_without_end_time_is_never_immutable(self):
        self.assertFalse(is_closed_history(self.rows(0, HOUR), None, self.now))

    def test_page_with_all_candles_closed_is_immutable(self):
        self.assertTrue(is_closed_history(self.rows(0, HOUR), 2 * HOUR, self.now))

    def test_page_reaching_the_open_candle_is_not_immutable(self):
        self.assertFalse(is_closed_history(self.rows(99 * HOUR, 100 * HOUR), self.now, self.now))
        # end_time already in the past, but the candle it falls into is still open
        self.assertFalse(is_closed_history(self.rows(100 * HOUR), 100 * HOUR + 10, self.now))
        # the candle that closed just before "now" is final
        self.assertTrue(is_closed_history(self.rows(99 * HOUR), 99 * HOUR + 10, self.now))

    def test_empty_page_before_now_is_immutable(self):
        self.assertTrue(is_closed_history([], HOUR, self.now))


class FakeClock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class TestKlinesPageCache(unittest.TestCase):
    def test_concurrent_identical_requests_hit_upstream_once(self):
        cache = KlinesPageCache()
        calls = []

        def fetch():
            calls.append(1)
            time.sleep(0.05)
            return [binance_kline(0)]

        async def scenario():
            return await asyncio.gather(*[
                cache.get_page(key="k", exchange="BINANCE", fetch=fetch, end_time=None) for _ in range(20)
            ])

        pages = run(scenario())
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(p is pages[0] for p in pages))

    def test_errors_reach_every_waiter_and_are_not_cached(self):
        cache = KlinesPageCache()
        attempts = []

        def failing():
            attempts.append(1)
            time.sleep(0.02)
            raise RuntimeError("binance down")

        async def scenario():
            return await asyncio.gather(*[
                cache.get_page(key="k", exchange="BINANCE", fetch=failing, end_time=None) for _ in range(5)
            ], return_exceptions=True)

        results = run(scenario())
        self.assertEqual(len(attempts), 1)
        self.assertTrue(all(isinstance(r, RuntimeError) for r in results))
        page = run(cache.get_page(key="k", exchange="BINANCE", fetch=lambda: [binance_kline(0)], end_time=None))
        self.assertEqual(len(page.rows), 1)

    def test_head_pages_expire_quickly_history_pages_do_not(self):
        clock = FakeClock()
        cache = KlinesPageCache(head_ttl=5, history_ttl=3600, clock=clock)
        now_ms = int(clock() * 1000)
        old = now_ms - 10 * HOUR

        run(cache.get_page(key="head", exchange="B", fetch=lambda: [binance_kline(old)], end_time=None))
        hist = run(cache.get_page(key="hist", exchange="B", fetch=lambda: [binance_kline(old)], end_time=old + HOUR))
        self.assertTrue(hist.immutable)
        self.assertEqual(cache.upstream_calls, 2)

        clock.t += 6
        run(cache.get_page(key="head", exchange="B", fetch=lambda: [binance_kline(old)], end_time=None))
        run(cache.get_page(key="hist", exchange="B", fetch=lambda: [binance_kline(old)], end_time=old + HOUR))
        self.assertEqual(cache.upstream_calls, 3)  # head refetched, history served from cache

    def test_lru_eviction_by_candle_count(self):
        cache = KlinesPageCache(max_candles=3)
        page = lambda n: (lambda: [binance_kline(i * HOUR) for i in range(n)])
        run(cache.get_page(key="a", exchange="B", fetch=page(2), end_time=None))
        run(cache.get_page(key="b", exchange="B", fetch=page(2), end_time=None))
        run(cache.get_page(key="b", exchange="B", fetch=page(2), end_time=None))
        self.assertEqual(cache.upstream_calls, 2)
        run(cache.get_page(key="a", exchange="B", fetch=page(2), end_time=None))
        self.assertEqual(cache.upstream_calls, 3)  # "a" was evicted to fit "b"

    def test_upstream_runs_in_a_thread_and_does_not_block_the_event_loop(self):
        cache = KlinesPageCache()
        loop_thread = []

        def slow_fetch():
            loop_thread.append(threading.current_thread() is threading.main_thread())
            time.sleep(0.3)
            return []

        async def scenario():
            ticks = 0

            async def ticker():
                nonlocal ticks
                for _ in range(10):
                    await asyncio.sleep(0.02)
                    ticks += 1

            await asyncio.gather(
                cache.get_page(key="k", exchange="B", fetch=slow_fetch, end_time=None), ticker()
            )
            return ticks

        self.assertEqual(run(scenario()), 10)
        self.assertEqual(loop_thread, [False])

    def test_upstream_concurrency_is_limited_per_exchange(self):
        cache = KlinesPageCache(upstream_concurrency=2)
        lock = threading.Lock()
        active, peak = [0], [0]

        def fetch():
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return []

        async def scenario():
            await asyncio.gather(*[
                cache.get_page(key=i, exchange="BINANCE", fetch=fetch, end_time=None) for i in range(8)
            ])

        run(scenario())
        self.assertEqual(peak[0], 2)


class FakeExchangeApi:
    def __init__(self, klines):
        self.klines = klines
        self.calls = []

    def _get_klines(self, **kwargs):
        self.calls.append(kwargs)
        return self.klines


class TestKlinesEndpoint(unittest.TestCase):
    def setUp(self):
        now_ms = int(time.time() * 1000)
        self.old = now_ms - 100 * HOUR
        self.api = FakeExchangeApi([binance_kline(self.old + i * HOUR) for i in range(40)])

        assets = mock.MagicMock()
        assets.get_by_id = mock.AsyncMock(return_value={"asset": "BTC", "quote": "USDT", "full_name": "Bitcoin"})
        asset_exchanges = mock.MagicMock()
        asset_exchanges.get_by_asset_id = mock.AsyncMock(return_value=[{"exchange_name": "Binance"}])
        db = mock.MagicMock()
        db.get_factory.return_value.get_assets_table.return_value = assets
        db.get_factory.return_value.get_asset_exchanges_table.return_value = asset_exchanges
        facade = mock.MagicMock()
        facade.get_fabric.return_value.get_binance_api.return_value = self.api

        patches = [
            mock.patch.object(exchanges, "get_db", mock.AsyncMock(return_value=db)),
            mock.patch.object(exchanges, "get_api_facade", mock.MagicMock(return_value=facade)),
            mock.patch.object(exchanges, "klines_cache", KlinesPageCache()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        app = FastAPI()
        app.include_router(exchanges.router, prefix=exchanges.PREFIX)
        app.dependency_overrides[require_auth] = lambda: None
        app.add_middleware(KlinesGZipMiddleware, path_prefix="/exchanges/klines/", minimum_size=1000)

        @app.get("/other")
        def other():
            return {"x": "y" * 5000}

        self.client = TestClient(app)

    def test_default_format_is_unchanged_and_head_page_is_short_lived(self):
        r = self.client.get("/exchanges/klines/1/1h")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["exchange"], "BINANCE")
        self.assertEqual(body["klines"][0], binance_kline(self.old))
        self.assertNotIn("fields", body)
        self.assertEqual(r.headers["cache-control"], CACHE_CONTROL_HEAD)

    def test_compact_format(self):
        body = self.client.get("/exchanges/klines/1/1h", params={"compact": "true"}).json()
        self.assertEqual(body["fields"], list(COMPACT_FIELDS))
        self.assertEqual(body["klines"][0], [self.old, 1.0, 2.0, 0.5, 1.0, 10.0])

    def test_historical_page_is_immutable_and_cached(self):
        params = {"end_time": self.old + 50 * HOUR, "limit": 1000}
        first = self.client.get("/exchanges/klines/1/1h", params=params)
        second = self.client.get("/exchanges/klines/1/1h", params=params)
        self.assertEqual(first.headers["cache-control"], CACHE_CONTROL_HISTORY)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(len(self.api.calls), 1)
        self.assertEqual(self.api.calls[0]["end_time"], self.old + 50 * HOUR)
        self.assertEqual(self.api.calls[0]["limit"], 1000)

    def test_gzip_only_for_klines(self):
        klines = self.client.get("/exchanges/klines/1/1h", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(klines.headers.get("content-encoding"), "gzip")
        other = self.client.get("/other", headers={"Accept-Encoding": "gzip"})
        self.assertNotIn("content-encoding", other.headers)

    def test_limit_validation_still_applies(self):
        self.assertEqual(self.client.get("/exchanges/klines/1/1h", params={"limit": 1001}).status_code, 422)


class TestYahooKlinesRange(unittest.TestCase):
    def setUp(self):
        from src.api.exchanges.yahoofinance import YahooFinanceAPI

        self.api = YahooFinanceAPI.__new__(YahooFinanceAPI)
        idx = pd.date_range("2024-01-01", periods=10, freq="D", tz="America/New_York")
        self.history = pd.DataFrame(
            {"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 10.0}, index=idx
        )
        self.opens = [int(ts.timestamp() * 1000) for ts in idx]

    def fetch(self, **kwargs):
        ticker = mock.MagicMock()
        ticker.history.return_value = self.history
        with mock.patch("src.api.exchanges.yahoofinance.yf.Ticker", return_value=ticker):
            result = self.api._get_klines(base_currency="AAPL", quote_currency="USD", interval="1d", **kwargs)
        return result, ticker.history.call_args.kwargs

    def test_paging_with_end_time_does_not_skip_or_repeat_candles(self):
        newest, _ = self.fetch(limit=4)
        self.assertEqual([k["open_time"] for k in newest], self.opens[-4:])
        older, kwargs = self.fetch(end_time=newest[0]["open_time"] - 1, limit=4)
        self.assertEqual([k["open_time"] for k in older], self.opens[2:6])
        # yfinance's end date is exclusive - one day of margin, exact cut done locally
        self.assertEqual(kwargs["end"], "2024-01-08")

    def test_start_time_is_exact(self):
        result, _ = self.fetch(start_time=self.opens[7], limit=1000)
        self.assertEqual([k["open_time"] for k in result], self.opens[7:])


if __name__ == "__main__":
    unittest.main()
