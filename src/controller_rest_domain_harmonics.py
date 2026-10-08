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
GET  /harmonics/stats?group_by=pattern_type,interval&pattern_type=&interval=&asset_id=&...
     Skuteczność setupów XABCD (src/harmonic_setups.py): win rate z 95% przedziałem Wilsona,
     średnie R, MFE/MAE, odsetek wejść i TP2.
GET  /harmonics/setups?asset_id=&interval=&status=&limit=
     Setupy jednego assetu/interwału z wynikami (np. do nałożenia na wykres).
GET  /harmonics/setups/tracked
     Assety i interwały, dla których śledzimy setupy (nocny sync aktualizuje je na żywo).
POST /harmonics/setups/backfill  (admin)
     Zleca replay historii dla listy assetów i interwałów.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field

from .auth import AuthUser, require_admin, require_auth
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL
from . import harmonic_scan, harmonic_setups
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


GROUPABLE = ("pattern_type", "interval", "asset_id", "is_bullish", "source", "targets_source", "spacing")
BACKFILL_MAX_TASKS = 100


@router.get("/stats")
async def get_harmonic_setup_stats(
    group_by: str = Query(default="pattern_type", description=f"lista po przecinku z: {', '.join(GROUPABLE)}"),
    pattern_type: Optional[str] = Query(default=None),
    interval: Optional[str] = Query(default=None),
    asset_id: Optional[int] = Query(default=None, ge=1),
    is_bullish: Optional[bool] = Query(default=None),
    source: Optional[str] = Query(default=None, description="live | replay"),
    targets_source: Optional[str] = Query(default=None, description="app | fallback"),
    min_trades: int = Query(default=0, ge=0, description="pomiń grupy z mniejszą liczbą transakcji"),
):
    """Skuteczność setupów: win rate (z przedziałem Wilsona), średnie R, MFE/MAE, entry rate, TP2."""
    groups = [g.strip() for g in group_by.split(",") if g.strip()]
    unknown = [g for g in groups if g not in GROUPABLE]
    if unknown:
        raise HTTPException(status_code=422, detail=f"nieznane group_by: {unknown}")
    filters = {"pattern_type": pattern_type, "interval": interval, "asset_id": asset_id,
               "is_bullish": is_bullish, "source": source, "targets_source": targets_source}
    db = await get_db()
    table = db.get_factory().get_technical_analysis_harmonic_setups_table()
    version = harmonic_setups.params_version()
    rows = [harmonic_setups.stats_row(r) for r in await table.stats(version, groups, filters)]
    rows = [r for r in rows if r["trades"] >= min_trades]
    return {
        "params_version": version,
        "params": harmonic_setups.SETUP_PARAMS,
        "group_by": groups,
        "filters": {k: v for k, v in filters.items() if v is not None},
        "groups": rows,
    }


@router.get("/setups/tracked")
async def get_tracked_harmonic_setups():
    db = await get_db()
    table = db.get_factory().get_technical_analysis_harmonic_setups_table()
    return {"params_version": harmonic_setups.params_version(),
            "tracked": await table.tracked_assets(harmonic_setups.params_version())}


@router.get("/setups")
async def get_harmonic_setups(
    asset_id: int = Query(..., ge=1),
    interval: str = Query(...),
    status: Optional[str] = Query(default=None, description="waiting | open | win | loss | expired | no_entry | invalidated"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    db = await get_db()
    table = db.get_factory().get_technical_analysis_harmonic_setups_table()
    version = harmonic_setups.params_version()
    return {"params_version": version,
            "setups": await table.list(asset_id, interval, version, status=status, limit=limit)}


class BackfillRequest(BaseModel):
    asset_ids: List[int] = Field(..., min_length=1)
    intervals: List[str] = Field(default=["1h", "4h", "1d"])
    candles: int = Field(default=5000, ge=100, le=10000)


def _enqueue_setups(asset_id: int, interval: str, candles: int) -> str:
    from .celery_tasks.analysis_tasks import track_harmonic_setups_task

    return track_harmonic_setups_task.delay(
        asset_id=asset_id, interval=interval, candles=candles, source="replay"
    ).id


@router.post("/setups/backfill")
async def backfill_harmonic_setups(
    request: BackfillRequest = Body(...),
    current_user: AuthUser = Depends(require_admin),
):
    """Replay historii setupów (admin). Wyniki trafiają do bazy; od tej chwili nocny sync śledzi
    te assety/interwały na żywo."""
    for interval in request.intervals:
        try:
            harmonic_scan.interval_ms(interval)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    if len(request.asset_ids) * len(request.intervals) > BACKFILL_MAX_TASKS:
        raise HTTPException(status_code=422, detail=f"najwyżej {BACKFILL_MAX_TASKS} par asset/interwał naraz")
    db = await get_db()
    assets_table = db.get_factory().get_assets_table()
    missing = [a for a in request.asset_ids if not await assets_table.get_by_id(a)]
    if missing:
        raise HTTPException(status_code=404, detail=f"nie ma assetów: {missing}")
    tasks = []
    for asset_id in request.asset_ids:
        for interval in request.intervals:
            task_id = await asyncio.to_thread(_enqueue_setups, asset_id, interval, request.candles)
            tasks.append({"asset_id": asset_id, "interval": interval, "task_id": task_id})
    return {"params_version": harmonic_setups.params_version(), "tasks": tasks}


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
