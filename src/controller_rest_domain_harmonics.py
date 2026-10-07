"""
REST API Controller - formacje harmoniczne na żądanie (zakres czasu z wykresu) i ręczna walidacja XABCD.

GET  /harmonics/{asset_id}/{interval}?start_time=&end_time=
     Formacje XABCD/ABCD, których wszystkie punkty leżą w zakresie (domyślnie ostatnie 500
     zamkniętych świec, najwyżej 2000 świec). Wyniki są w bazie na stałe: brakujące fragmenty
     zakresu liczy worker Celery i zapisuje (src/harmonic_scan.py). Odpowiedź:
       200 status=complete  - cały zakres przeszukany, `patterns` kompletne,
       202 status=computing - worker liczy brakujące fragmenty; `patterns` to to, co już jest w
                              bazie; ponów request po `retry_after_ms`,
       200 status=failed    - ostatni skan się nie powiódł (`error`); kolejny request ponawia.
POST /harmonics/validate
     Punkty X, A, B, C (+ opcjonalnie D) zaznaczone ręcznie -> proporcje, pasujące formacje,
     strefa D (PRZ) i cele (src/harmonic_validation.py). Czysta matematyka, bez bazy.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field

from .auth import require_auth
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL
from . import harmonic_scan
from .harmonic_validation import Point, ValidationError, validate_xabcd

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])
PREFIX = "/harmonics"
TAGS = ["Harmonics"]

RETRY_AFTER_MS = 2000
# Zadanie, o którym nic nie wiadomo dłużej niż tyle, uznajemy za zgubione (np. restart workera).
INFLIGHT_STALE_SECONDS = 600
CACHE_CONTROL_COMPLETE = "private, max-age=60"

db_instance: Optional[DatabasePostgreSQL] = None
db_lock: asyncio.Lock = asyncio.Lock()

# Jeden skan naraz na (asset_id, interval) - kolejne requesty dostają ten sam task_id.
# API ma jedną replikę, więc wystarczy pamięć procesu.
_inflight: Dict[Tuple[int, str], Tuple[str, float]] = {}


async def get_db() -> DatabasePostgreSQL:
    global db_instance
    if db_instance is not None:
        return db_instance
    async with db_lock:
        if db_instance is None:
            new_instance = DatabaseFacade().get_database_postgresql()
            await new_instance.init_db()
            db_instance = new_instance
    return db_instance


def _enqueue_scan(asset_id: int, interval: str, windows) -> str:
    # Import tutaj: moduł zadań ciągnie konfigurację Celery, niepotrzebną przy samym odczycie.
    from .celery_tasks.analysis_tasks import scan_harmonic_windows_task

    return scan_harmonic_windows_task.delay(
        asset_id=asset_id, interval=interval, windows=[list(w) for w in windows]
    ).id


def _task_state(task_id: str) -> Tuple[str, Optional[str]]:
    from .controller_rest_celery_worker import celery

    result = celery.AsyncResult(task_id)
    error = str(result.result) if result.state == "FAILURE" else None
    return result.state, error


async def _ensure_scan(asset_id: int, interval: str, windows) -> Dict[str, Any]:
    """Zwraca stan skanu dla (asset, interval); zleca nowy, jeśli żaden nie trwa."""
    key = (asset_id, interval)
    current = _inflight.get(key)
    if current:
        task_id, started = current
        state, error = await asyncio.to_thread(_task_state, task_id)
        if state in ("PENDING", "RECEIVED", "STARTED", "RETRY") and time.time() - started < INFLIGHT_STALE_SECONDS:
            return {"status": "computing", "task_id": task_id}
        _inflight.pop(key, None)
        if state == "FAILURE":
            logger.error(f"Skan formacji {asset_id}/{interval} ({task_id}) nie powiódł się: {error}")
            return {"status": "failed", "task_id": task_id, "error": error}
        # SUCCESS, a nadal czegoś brakuje (np. przybyła nowa zamknięta świeca) - liczymy dalej.
    task_id = await asyncio.to_thread(_enqueue_scan, asset_id, interval, windows)
    _inflight[key] = (task_id, time.time())
    return {"status": "computing", "task_id": task_id}


@router.get("/{asset_id}/{interval}")
async def get_harmonic_patterns_in_range(
    response: Response,
    asset_id: int = Path(..., ge=1),
    interval: str = Path(...),
    start_time: Optional[int] = Query(default=None, description="open_time pierwszej świecy zakresu (ms)"),
    end_time: Optional[int] = Query(default=None, description="open_time ostatniej świecy zakresu (ms)"),
):
    """Formacje harmoniczne w zakresie czasu - z bazy, a brakujące fragmenty liczy worker."""
    now_ms = int(time.time() * 1000)
    try:
        start, end = harmonic_scan.resolve_range(interval, start_time, end_time, now_ms)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db = await get_db()
    factory = db.get_factory()
    if not await factory.get_assets_table().get_by_id(asset_id):
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    span = harmonic_scan.max_pattern_span_ms(interval)
    scanned = await factory.get_technical_analysis_harmonic_scan_windows_table().get_overlapping(
        asset_id, interval, harmonic_scan.params_hash(), start - span, end + span
    )
    missing = harmonic_scan.missing_windows((start, end), [(w["start_time"], w["end_time"]) for w in scanned], span)
    patterns = await factory.get_technical_analysis_harmonic_patterns_table().get_within_range(
        asset_id, interval, start, end
    )

    body: Dict[str, Any] = {
        "asset_id": asset_id,
        "interval": interval,
        "start_time": start,
        "end_time": end,
        "max_pattern_candles": harmonic_scan.MAX_PATTERN_CANDLES,
        "missing_windows": [list(w) for w in missing],
        "patterns": patterns,
    }
    if not missing:
        body["status"] = "complete"
        response.headers["Cache-Control"] = CACHE_CONTROL_COMPLETE
        return body

    body.update(await _ensure_scan(asset_id, interval, missing))
    response.headers["Cache-Control"] = "no-store"
    if body["status"] == "computing":
        response.status_code = 202
        body["retry_after_ms"] = RETRY_AFTER_MS
    return body


class PointIn(BaseModel):
    time: int = Field(..., description="open_time świecy punktu (ms)")
    price: float = Field(..., gt=0)


class ValidateRequest(BaseModel):
    points: Dict[str, PointIn] = Field(..., description="X, A, B, C oraz opcjonalnie D")
    fib_tolerance: float = Field(default=0.03, ge=0, le=0.2)


@router.post("/validate")
async def validate_manual_xabcd(request: ValidateRequest = Body(...)):
    """Sprawdza ręcznie zaznaczone punkty względem definicji formacji (te same co w wyszukiwaniu)."""
    try:
        points = {name.upper(): Point(time=p.time, price=p.price) for name, p in request.points.items()}
        return validate_xabcd(points, fib_tolerance=request.fib_tolerance)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
