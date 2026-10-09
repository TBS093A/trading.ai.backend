"""Raport wariantów wejścia / zarządzania (src/setup_variants.py) na historii śledzonych assetów."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .. import harmonic_scan, harmonic_setups, pattern_strength, setup_variants
from ..pattern_strength import StrengthModel
from .klines_source import KlinesSource
from .setup_tracking_service import SetupTrackingService, entry_confluences, pre_entry_confluences
from .strength_service import StrengthService, cached_model, refresh_cached_model

logger = logging.getLogger(__name__)

DEFAULT_CANDLES = 5000


class VariantReportService:
    def __init__(self, db, klines: Optional[KlinesSource] = None):
        self.db = db
        self.klines = klines

    async def create(self, candles: int = DEFAULT_CANDLES) -> Dict[str, Any]:
        """Zakłada raport: model siły uczony tylko na setupach sprzed cutoff (= początek zbioru
        testowego aktywnego modelu) i lista par (asset, interwał) do przeliczenia."""
        factory = self.db.get_factory()
        await refresh_cached_model(self.db, force=True)
        active = cached_model("entry")
        cutoff_iso = (active.metrics or {}).get("test_from") if active else None
        cutoff_ms = int(datetime.fromisoformat(cutoff_iso).timestamp() * 1000) if cutoff_iso else None
        models_json: Dict[str, Any] = {}
        if cutoff_ms is not None:
            rows = await StrengthService(self.db)._decided_setups(harmonic_setups.params_version())
            for kind in pattern_strength.KINDS:
                model = pattern_strength.fit_before(pattern_strength.training_samples(rows, kind), cutoff_ms, kind)
                models_json[kind] = model.as_dict()
        targets = await factory.get_tracked_assets_table().get_setup_targets()
        params = {"candles": candles, "variants": [v.__dict__ for v in setup_variants.VARIANTS],
                  "strength_models": models_json}
        report_id = await factory.get_harmonic_variant_reports_table().create_report(
            harmonic_setups.params_version(), params, cutoff_ms, len(targets)
        )
        return {"report_id": report_id, "cutoff_ms": cutoff_ms, "pairs": targets}

    async def run_pair(self, report_id: int, asset_id: int, interval: str) -> Dict[str, Any]:
        table = self.db.get_factory().get_harmonic_variant_reports_table()
        report = await table.get_report(report_id)
        params = report["params_json"]
        models = {kind: StrengthModel.from_dict(m) for kind, m in (params.get("strength_models") or {}).items()}
        resolved = await self.klines.resolve(asset_id)
        self.klines.require_api(resolved)
        step = harmonic_scan.interval_ms(interval)
        now_ms = int(datetime.now().timestamp() * 1000)
        end = harmonic_scan.last_closed_open_time(interval, now_ms)
        candles = int(params.get("candles", DEFAULT_CANDLES))
        start = end - candles * step * (harmonic_scan.PAD_CALENDAR_FACTOR if resolved.exchange == 'YAHOO' else 1)
        klines = self.klines.fetch_range(resolved, interval, start, end)[-candles:]
        if len(klines) < 100:
            await table.add_trades(report_id, [])
            return {"klines": len(klines), "trades": 0}
        context = await SetupTrackingService(self.db, self.klines)._confluence_context(resolved, asset_id, interval, klines)
        score_cache: Dict[tuple, Optional[Dict[str, Any]]] = {}

        def score_fn(setup, e_idx, entry, sl, tp1, kind):
            # {"score", "p_win"} z modelu danego rodzaju (jeśli jest) + "trend" (with / against / None)
            # z tych samych konfluencji - filtr trendu działa także bez modelu.
            key = (setup.key, e_idx, round(entry, 10), kind)
            if key not in score_cache:
                points = {n: {"time": int(klines[p.index]["open_time"]), "price": p.price}
                          for n, p in setup.points.items()}
                row = {"pattern_type": setup.pattern, "is_bullish": setup.is_bullish, "interval": interval,
                       "spacing": setup.spacing, "points_json": points,
                       "prz_min": setup.prz_min, "prz_max": setup.prz_max}
                if kind == "pre":
                    # Wejście przy dotknięciu: znamy tylko świece przed świecą wejścia.
                    known = klines[:e_idx]
                    confluences = pre_entry_confluences(setup, known, interval, context, step)
                    row.update(status="waiting", entry_time=None, entry_price=None,
                               created_time=int(known[-1]["open_time"]), pre_confluences_json=confluences)
                else:
                    confluences = entry_confluences(setup, e_idx, entry, klines[: e_idx + 1], interval, context)
                    row.update(entry_time=int(klines[e_idx]["open_time"]), entry_price=entry,
                               confluences_json=confluences)
                model = models.get(kind)
                scored = dict(model.score(pattern_strength.setup_features(row, kind))) if model else {}
                scored["trend"] = pattern_strength.trend_alignment(confluences, setup.is_bullish)
                score_cache[key] = scored
            return score_cache[key]

        trades: List[Dict[str, Any]] = []
        for setup in harmonic_setups.generate_all_setups(klines):
            for variant in setup_variants.VARIANTS:
                t = setup_variants.simulate_variant(setup, klines, variant, harmonic_setups.app_targets, score_fn)
                if t is None:
                    continue
                trades.append({**t.as_dict(), "asset_id": asset_id, "interval": interval,
                               "pattern_type": setup.pattern,
                               "entry_time": int(klines[t.entry_index]["open_time"]),
                               "exit_time": int(klines[t.exit_index]["open_time"])})
        await table.add_trades(report_id, trades)
        logger.info(f"Raport wariantów #{report_id} {resolved.symbol} [{interval}]: {len(klines)} świec, "
                    f"{len(trades)} transakcji")
        return {"klines": len(klines), "trades": len(trades)}

    async def reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        rows = await self.db.get_factory().get_harmonic_variant_reports_table().get_all(limit=limit)
        return [{**r, "complete": r["pairs_done"] >= r["pairs_total"]} for r in rows]

    async def summary(self, report_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        table = self.db.get_factory().get_harmonic_variant_reports_table()
        report = await table.get_report(report_id)
        if report is None:
            return None
        trades = await table.get_trades(report["id"])
        return {
            "report_id": report["id"], "created_at": report["created_at"], "params_version": report["params_version"],
            "cutoff_ms": report["cutoff_ms"], "pairs_total": report["pairs_total"], "pairs_done": report["pairs_done"],
            "complete": report["pairs_done"] >= report["pairs_total"],
            "variants": setup_variants.report(trades, report["cutoff_ms"]),
        }
