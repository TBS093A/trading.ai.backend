"""Model siły formacji: uczenie z setupów w bazie i cache w procesie (src/pattern_strength.py)."""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from .. import harmonic_setups, pattern_strength
from ..pattern_strength import StrengthModel

logger = logging.getLogger(__name__)

CACHE_TTL_S = 600
_cache: Dict[str, Any] = {"model": None, "loaded_at": 0.0}


def cached_model() -> Optional[StrengthModel]:
    return _cache["model"]


def set_cached_model(model: Optional[StrengthModel]) -> None:
    _cache["model"], _cache["loaded_at"] = model, time.monotonic()


async def refresh_cached_model(db, force: bool = False) -> Optional[StrengthModel]:
    """Wczytuje aktywny model, gdy cache jest starszy niż CACHE_TTL_S (zależność routerów API)."""
    if not force and _cache["loaded_at"] and time.monotonic() - _cache["loaded_at"] < CACHE_TTL_S:
        return _cache["model"]
    try:
        row = await db.get_factory().get_harmonic_strength_models_table().get_active()
        set_cached_model(StrengthModel.from_dict(row["model_json"]) if row else None)
    except Exception as e:  # siła to dodatek - bez modelu endpointy działają jak dotąd
        logger.warning(f"Model siły formacji niedostępny: {e}")
        _cache["loaded_at"] = time.monotonic()
    return _cache["model"]


def pattern_strength_or_none(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model = cached_model()
    if model is None:
        return None
    try:
        return model.score(pattern_strength.pattern_features(row))
    except Exception as e:
        logger.debug(f"Siła formacji {row.get('id')} nie policzona: {e}")
        return None


def setup_strength_or_none(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    model = cached_model()
    if model is None or row.get("entry_time") is None:
        return None
    try:
        return model.score(pattern_strength.setup_features(row))
    except Exception as e:
        logger.debug(f"Siła setupu nie policzona: {e}")
        return None


class StrengthService:
    def __init__(self, db):
        self.db = db

    async def _decided_setups(self, params_version: str) -> List[Dict[str, Any]]:
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT pattern_type, is_bullish, interval, spacing, points_json, entry_time, entry_price,
                          status, r_multiple, confluences_json
                FROM technical_analysis_harmonic_setups
                WHERE params_version = $1 AND status IN ('win', 'loss', 'expired') AND entry_time IS NOT NULL""",
                params_version,
            )
        out = []
        for r in rows:
            d = dict(r)
            for c in ("points_json", "confluences_json"):
                if isinstance(d.get(c), str):
                    d[c] = json.loads(d[c])
            out.append(d)
        return out

    async def fit_and_activate(self) -> Dict[str, Any]:
        version = harmonic_setups.params_version()
        rows = await self._decided_setups(version)
        model = pattern_strength.fit(pattern_strength.training_samples(rows), params_version=version)
        model_id = await self.db.get_factory().get_harmonic_strength_models_table().save(
            version, model.as_dict(), model.metrics
        )
        set_cached_model(model)
        logger.info(f"Model siły #{model_id}: {len(model.feature_names)} cech, metryki {model.metrics}")
        return {"model_id": model_id, "features": len(model.feature_names), "metrics": model.metrics,
                "top_weights": pattern_strength.top_weights(model)}
