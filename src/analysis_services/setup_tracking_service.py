"""Setupy XABCD (X..C + PRZ znane w danej chwili) i ich wyniki - src/harmonic_setups.py."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .. import harmonic_scan, harmonic_setups
from ..utils.harmonic_patterns import ConfluenceDetector, merge_confluences
from ..utils.harmonic_patterns.fib_confluences import INTERVAL_HIERARCHY
from .confluence_postprocessor import HIGHER_TF_KLINES_WINDOW, POST_PROCESSING_TYPES, post_processing_entries
from .strength_service import cached_model, refresh_cached_model, setup_strength_or_none
from ..pattern_strength import setup_features
from ..pattern_strength import LEVEL_TYPES
from .klines_source import KlinesSource

logger = logging.getLogger(__name__)

SETUP_LIVE_CANDLES = 600              # przebieg godzinny: ostatnie świece (+ pokrycie otwartych setupów)
SETUP_MAX_CANDLES = 10000             # górna granica jednego przebiegu (backfill)
HIGHER_TF_COUNT = 3                   # ile wyższych interwałów do konfluencji S/R / trendline (np. 1h -> 4h, 1d, 3d)
PATTERNS_FOR_CONFLUENCES = 5000       # formacje assetu do Fib cluster / Fib z wyższego TF


def entry_confluences(setup, entry_index: int, entry_price: float, klines_to_entry, interval: str,
                      context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ten sam zestaw co w sidebarze, w chwili wejścia: detektory w punkcie D (= wejście) +
    post-processing (Fib cluster, wyższe TF). klines_to_entry kończy się świecą wejścia."""
    pp = {n: {'index': p.index, 'price': p.price} for n, p in setup.points.items()}
    pp['D'] = {'index': entry_index, 'price': entry_price}
    try:
        base = ConfluenceDetector.detect(klines_to_entry, pp, setup.is_bullish, entry_index, interval)
    except Exception as e:  # konfluencje są dodatkiem - nie blokują zapisu wyniku
        logger.debug(f"Konfluencje setupu {setup.key} nie powiodły się: {e}")
        return None
    entry_ts = int(klines_to_entry[-1]['open_time'])
    target = {
        'id': -1, 'interval': interval, 'd_point_timestamp': entry_ts,
        'c_point_timestamp': int(klines_to_entry[setup.points['C'].index]['open_time']),
        'ta_object_json': {'is_bullish': setup.is_bullish, 'pattern_type': setup.pattern,
                           'points': {'D': {'price': entry_price, 'open_time': entry_ts}},
                           'fibonacci_levels': {}},
    }
    try:
        extra = post_processing_entries(target, interval, context['patterns'], context['klines'])
    except Exception as e:
        logger.debug(f"Post-processing konfluencji setupu {setup.key} nie powiódł się: {e}")
        extra = []
    return merge_confluences(base, extra, replace_types=POST_PROCESSING_TYPES)


def pre_entry_confluences(setup, klines_known, interval: str, context: Dict[str, Any],
                          step: int) -> Optional[Dict[str, Any]]:
    """Setup czeka na PRZ: tylko konfluencje poziomowe (LEVEL_TYPES), D = bliższa krawędź PRZ,
    dane do ostatniej świecy w klines_known (zamkniętej przed chwilą oceny)."""
    near_edge = setup.prz_max if setup.is_bullish else setup.prz_min
    last = len(klines_known) - 1
    pp = {n: {'index': p.index, 'price': p.price} for n, p in setup.points.items()}
    pp['D'] = {'index': last, 'price': near_edge}
    try:
        base = ConfluenceDetector.detect(klines_known, pp, setup.is_bullish, last, interval) or {}
    except Exception as e:
        logger.debug(f"Konfluencje wstępne setupu {setup.key} nie powiodły się: {e}")
        base = {'total_score': 0, 'confluences': []}
    now_ts = int(klines_known[-1]['open_time']) + step   # zamknięcie ostatniej znanej świecy
    target = {
        'id': -1, 'interval': interval, 'd_point_timestamp': now_ts,
        'c_point_timestamp': int(klines_known[setup.points['C'].index]['open_time']),
        'ta_object_json': {'is_bullish': setup.is_bullish, 'pattern_type': setup.pattern,
                           'points': {'D': {'price': near_edge, 'open_time': now_ts}},
                           'fibonacci_levels': {}},
    }
    try:
        extra = post_processing_entries(target, interval, context['patterns'], context['klines'])
    except Exception as e:
        logger.debug(f"Post-processing wstępny setupu {setup.key} nie powiódł się: {e}")
        extra = []
    levels = [c for c in base.get('confluences', []) if c.get('type') in LEVEL_TYPES]
    return merge_confluences({'confluences': levels}, extra, replace_types=POST_PROCESSING_TYPES)


class SetupTrackingService:
    def __init__(self, db, klines: KlinesSource):
        self.db = db
        self.klines = klines

    async def track(self, asset_id: int, interval: str, candles: int = SETUP_LIVE_CANDLES,
                    source: str = 'live') -> Dict[str, Any]:
        """source='live' (co godzinę, proces _run_harmonic_setups_tracking) dokłada świece wstecz, żeby
        objąć najstarszy nierozstrzygnięty setup, i zapisuje zdarzenia zmian statusów (alerty);
        source='replay' (backfill) liczy historię z `candles` ostatnich świec, bez zdarzeń."""
        factory = self.db.get_factory()
        resolved = await self.klines.resolve(asset_id)
        self.klines.require_api(resolved)
        asset = resolved.asset
        table = factory.get_technical_analysis_harmonic_setups_table()
        version = harmonic_setups.params_version()

        step = harmonic_scan.interval_ms(interval)
        now_ms = int(datetime.now().timestamp() * 1000)
        end = harmonic_scan.last_closed_open_time(interval, now_ms)
        candles = max(100, min(int(candles), SETUP_MAX_CANDLES))
        # Yahoo: weekendy / sesje - zapas kalendarzowy, potem przycinamy do `candles` świec.
        start = end - candles * step * (harmonic_scan.PAD_CALENDAR_FACTOR if resolved.exchange == 'YAHOO' else 1)
        oldest_open = await table.get_oldest_unresolved_x_time(asset_id, interval, version)
        cover_from = None
        if oldest_open is not None:
            # Zygzak potrzebuje kilku pivotów przed X, żeby odtworzyć ten sam setup.
            cover_from = oldest_open - 4 * max(harmonic_setups.SPACINGS) * step
            start = max(min(start, cover_from), end - SETUP_MAX_CANDLES * step)
        klines = self.klines.fetch_range(resolved, interval, start, end)
        first = max(0, len(klines) - candles)
        if cover_from is not None:
            first = min(first, next((i for i, k in enumerate(klines) if k['open_time'] >= cover_from), first))
        klines = klines[first:]
        if len(klines) < 100:
            return {'klines': len(klines), 'setups': 0, 'saved': 0}

        final_keys = await table.get_final_keys(asset_id, interval, version, int(klines[0]['open_time']))

        context = await self._confluence_context(resolved, asset_id, interval, klines)

        def confluences_fn(setup, outcome, klines_to_entry):
            return entry_confluences(setup, outcome.entry_index, outcome.entry_price, klines_to_entry, interval,
                                     context)

        def pre_confluences_fn(setup, all_klines):
            return pre_entry_confluences(setup, all_klines, interval, context, step)

        rows = harmonic_setups.evaluate(
            klines, asset_id, interval, source, skip_keys=final_keys,
            targets_fn=harmonic_setups.app_targets, confluences_fn=confluences_fn,
            pre_confluences_fn=pre_confluences_fn,
        )
        events = []
        if source == 'live':
            # Statusy sprzed tego przebiegu - zdarzenie = setup nowy albo ze zmienionym statusem.
            previous = await table.get_unresolved_statuses(asset_id, interval, version, int(klines[0]['open_time']))
            await refresh_cached_model(self.db)   # siła w treści alertu (worker ma własny cache)
            events = harmonic_setups.status_events(
                rows, previous, symbol=resolved.symbol,
                new_since=int(klines[-1]['open_time']) - harmonic_setups.EVENT_LOOKBACK_CANDLES * step,
                strength_fn=setup_strength_or_none,
            )
        saved = await table.upsert_many(rows)
        if events:
            await factory.get_harmonic_setup_events_table().add_many(events)
        if source == 'live':
            # Konta paper: sygnały z setupów, wypełnienia i wyjścia na tych samych świecach (src/trading).
            try:
                from ..trading.engine import TradingEngine

                def entry_strength_fn(setup, j, entry, kl):
                    # Tryb "confirm": siła pełna na zamkniętej świecy potwierdzenia (ta sama co w raporcie).
                    model = cached_model("entry")
                    if model is None:
                        return None
                    row = {"pattern_type": setup.pattern, "is_bullish": setup.is_bullish, "interval": interval,
                           "spacing": setup.spacing,
                           "points_json": {n: {"time": int(kl[p.index]["open_time"]), "price": p.price}
                                           for n, p in setup.points.items()},
                           "entry_time": int(kl[j]["open_time"]), "entry_price": entry,
                           "confluences_json": entry_confluences(setup, j, entry, kl[: j + 1], interval, context)}
                    return model.score(setup_features(row, "entry"))

                await TradingEngine(self.db, strength_fn=setup_strength_or_none,
                                    entry_strength_fn=entry_strength_fn).process_pair(
                    asset_id, interval, resolved.symbol, klines)
            except Exception as e:
                logger.error(f"Trading po śledzeniu {resolved.symbol} [{interval}] nie powiódł się: {e}", exc_info=True)
        by_status: Dict[str, int] = {}
        for r in rows:
            by_status[r['status']] = by_status.get(r['status'], 0) + 1
        logger.info(f"Setupy {asset['asset']}/{asset['quote']} [{interval}] ({source}): {len(klines)} świec, "
                    f"{len(rows)} nowych/otwartych, {len(final_keys)} już rozstrzygniętych, {by_status}")
        return {'klines': len(klines), 'setups': len(rows), 'saved': saved,
                'already_final': len(final_keys), 'by_status': by_status, 'events': len(events)}

    async def _confluence_context(self, resolved, asset_id: int, interval: str, klines) -> Dict[str, Any]:
        """Dane do konfluencji post-processingu: formacje assetu (wg interwału) i świece wyższych TF
        od HIGHER_TF_KLINES_WINDOW świec przed początkiem zakresu do jego końca."""
        patterns_by_interval: Dict[str, list] = {}
        try:
            table = self.db.get_factory().get_technical_analysis_harmonic_patterns_table()
            for p in await table.get_by_asset_id(asset_id, limit=PATTERNS_FOR_CONFLUENCES):
                if p.get('interval'):
                    patterns_by_interval.setdefault(p['interval'], []).append(p)
        except Exception as e:
            logger.warning(f"Formacje do konfluencji setupów niedostępne: {e}")
        higher = []
        if interval in INTERVAL_HIERARCHY:
            higher = [iv for iv in INTERVAL_HIERARCHY[INTERVAL_HIERARCHY.index(interval) + 1:]
                      if iv in harmonic_scan.INTERVAL_MS][:HIGHER_TF_COUNT]
        klines_by_interval: Dict[str, list] = {}
        for iv in higher:
            step = harmonic_scan.interval_ms(iv)
            start = int(klines[0]['open_time']) - HIGHER_TF_KLINES_WINDOW * step
            try:
                klines_by_interval[iv] = self.klines.fetch_range(resolved, iv, start, int(klines[-1]['open_time']))
            except Exception as e:
                logger.warning(f"Świece {iv} do konfluencji setupów niedostępne: {e}")
        return {'patterns': patterns_by_interval, 'klines': klines_by_interval}

