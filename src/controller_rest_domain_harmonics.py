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
GET  /harmonics/tracked-assets                  śledzone assety (nocny sync formacji + setupy co godzinę)
PUT  /harmonics/tracked-assets/{asset_id}       (admin) dodaj / zmień; nowe interwały -> backfill setupów
DELETE /harmonics/tracked-assets/{asset_id}     (admin) przestań śledzić (historia zostaje)
GET  /harmonics/strength/model                  aktywny model siły formacji (metryki walidacji, najważniejsze wagi)
POST /harmonics/strength/fit                    (admin) naucz model od nowa na wynikach setupów
POST /harmonics/variants/run                    (admin) raport wariantów wejścia / zarządzania na historii
GET  /harmonics/variants/report?report_id=      wyniki wariantów (całość, przed i po cutoff modelu siły)
GET  /harmonics/alerts/settings                 alerty mailowe zalogowanego użytkownika
PUT  /harmonics/alerts/settings                 zapis (e-mail, statusy, assety, interwały)
GET  /harmonics/alerts/events?asset_id=&interval=&limit=   ostatnie zmiany setupów (historia alertów)
POST /harmonics/alerts/test                     mail testowy na adres użytkownika
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field, field_validator

from .auth import AuthUser, require_admin, require_auth
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL
from . import harmonic_alerts, harmonic_scan, harmonic_setups
from .config import config
from .analysis_services.strength_service import (
    cached_model, pattern_strength_or_none, refresh_cached_model, setup_strength_or_none,
)
from . import pattern_strength
from .harmonic_validation import Point, ValidationError, validate_xabcd
from .db.postgresql.tables.harmonic_setup_alerts_table import ALERT_STATUSES, DEFAULT_ALERT_STATUSES
from .db.postgresql.tables.tracked_assets_table import DEFAULT_SETUP_INTERVALS

logger = logging.getLogger(__name__)

async def _strength_model_cache() -> None:
    await refresh_cached_model(await get_db())


router = APIRouter(dependencies=[Depends(require_auth), Depends(_strength_model_cache)])
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
    active: bool = Query(default=False, description="tylko aktywne: waiting + open (lista w sidebarze)"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    """Setupy z wynikami; strength = siła pełna (od wejścia) albo wstępna (waiting, kind="pre")."""
    db = await get_db()
    table = db.get_factory().get_technical_analysis_harmonic_setups_table()
    version = harmonic_setups.params_version()
    setups = await table.list(asset_id, interval, version, status=status, limit=limit,
                              statuses=("waiting", "open") if active else None)
    for row in setups:
        row["strength"] = setup_strength_or_none(row)
    return {"params_version": version, "setups": setups}


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


def _valid_intervals(intervals: List[str]) -> List[str]:
    for interval in intervals:
        try:
            harmonic_scan.interval_ms(interval)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
    return sorted(set(intervals), key=intervals.index)


def _model_summary(model) -> Optional[Dict[str, Any]]:
    if model is None:
        return None
    return {"trained_at": model.trained_at, "params_version": model.params_version, "kind": model.kind,
            "features": len(model.feature_names), "metrics": model.metrics,
            "top_weights": pattern_strength.top_weights(model, 25)}


@router.get("/strength/model")
async def get_strength_model():
    """Aktywne modele siły: "model" = pełny (od wejścia; formacje z wykresu, setupy open i zamknięte),
    "pre_model" = wstępny (setupy czekające na PRZ, tylko konfluencje poziomowe)."""
    await refresh_cached_model(await get_db(), force=True)
    return {"model": _model_summary(cached_model("entry")), "pre_model": _model_summary(cached_model("pre"))}


def _pattern_setup_key(p: Dict[str, Any]) -> Optional[Tuple]:
    ta = p.get("ta_object_json") or {}
    times = [p.get(f"{n}_point_timestamp") for n in ("x", "a", "b", "c")]
    if not ta.get("pattern_type") or any(t is None for t in times):
        return None   # ABCD / ABC - setupy są tylko dla XABCD
    return (ta["pattern_type"],) + tuple(int(t) for t in times)


async def attach_setups(db, asset_id: int, interval: str, patterns: List[Dict[str, Any]]) -> None:
    """Dokleja do formacji z wykresu setup o tych samych punktach X..C (status, wynik) - pole "setup"."""
    keys = {id(p): _pattern_setup_key(p) for p in patterns}
    try:
        found = await db.get_factory().get_technical_analysis_harmonic_setups_table().find_by_points(
            asset_id, interval, harmonic_setups.params_version(), [k for k in keys.values() if k]
        )
    except Exception as e:
        logger.warning(f"Powiązanie formacji z setupami nie powiodło się: {e}")
        found = {}
    for p in patterns:
        p["setup"] = found.get(keys[id(p)]) if keys[id(p)] else None


def _enqueue_strength_fit() -> str:
    from .celery_tasks.analysis_tasks import fit_strength_model_task

    return fit_strength_model_task.apply_async(queue="analysis_queue").id


@router.post("/strength/fit")
async def fit_strength_model(current_user: AuthUser = Depends(require_admin)):
    return {"task_id": await asyncio.to_thread(_enqueue_strength_fit)}


def _enqueue_variant_pair(report_id: int, asset_id: int, interval: str) -> str:
    from .celery_tasks.analysis_tasks import run_variant_pair_task

    return run_variant_pair_task.apply_async(
        kwargs={"report_id": report_id, "asset_id": asset_id, "interval": interval}, queue="analysis_queue"
    ).id


@router.post("/variants/run")
async def run_variant_report(
    candles: int = Query(default=5000, ge=500, le=10000),
    current_user: AuthUser = Depends(require_admin),
):
    """Porównanie wariantów (src/setup_variants.py) na historii śledzonych par - liczone przez workery."""
    from .analysis_services.variant_report_service import VariantReportService

    created = await VariantReportService(await get_db()).create(candles)
    for t in created["pairs"]:
        await asyncio.to_thread(_enqueue_variant_pair, created["report_id"], t["asset_id"], t["interval"])
    return {"report_id": created["report_id"], "cutoff_ms": created["cutoff_ms"], "pairs": len(created["pairs"])}


@router.get("/variants/report")
async def get_variant_report(report_id: Optional[int] = Query(default=None, ge=1)):
    from .analysis_services.variant_report_service import VariantReportService

    summary = await VariantReportService(await get_db()).summary(report_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="brak raportu wariantów")
    return summary


@router.get("/tracked-assets")
async def get_tracked_assets():
    db = await get_db()
    return {"tracked": await db.get_factory().get_tracked_assets_table().list_with_assets()}


class TrackedAssetIn(BaseModel):
    patterns_sync: bool = Field(default=True, description="nocny sync formacji harmonicznych")
    setup_intervals: List[str] = Field(default=list(DEFAULT_SETUP_INTERVALS),
                                       description="interwały śledzenia setupów (puste = bez setupów)")
    backfill_candles: int = Field(default=5000, ge=100, le=10000)


@router.put("/tracked-assets/{asset_id}")
async def put_tracked_asset(
    asset_id: int = Path(..., ge=1),
    request: TrackedAssetIn = Body(...),
    current_user: AuthUser = Depends(require_admin),
):
    """Dodaje / zmienia śledzony asset. Dla interwałów, których wcześniej nie było, zleca backfill
    setupów (bez alertów) - od następnej pełnej godziny asset jest śledzony na żywo."""
    intervals = _valid_intervals(request.setup_intervals)
    db = await get_db()
    factory = db.get_factory()
    if not await factory.get_assets_table().get_by_id(asset_id):
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")
    table = factory.get_tracked_assets_table()
    before = await table.get_by_id(asset_id)
    row = await table.upsert(asset_id, request.patterns_sync, intervals)
    added = [i for i in intervals if not before or i not in (before.get("setup_intervals") or [])]
    tasks = []
    for interval in added:
        task_id = await asyncio.to_thread(_enqueue_setups, asset_id, interval, request.backfill_candles)
        tasks.append({"asset_id": asset_id, "interval": interval, "task_id": task_id})
    logger.info(f"Śledzony asset {asset_id} zapisany przez {getattr(current_user, 'username', '?')}: "
                f"patterns_sync={request.patterns_sync}, interwały={intervals}, backfill={added}")
    return {"tracked": row, "backfill_tasks": tasks}


@router.delete("/tracked-assets/{asset_id}")
async def delete_tracked_asset(asset_id: int = Path(..., ge=1), current_user: AuthUser = Depends(require_admin)):
    db = await get_db()
    if not await db.get_factory().get_tracked_assets_table().delete(asset_id):
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} nie jest śledzony")
    return {"deleted": asset_id}


class AlertSettingsIn(BaseModel):
    email: Optional[str] = Field(default=None, max_length=254)
    email_enabled: bool = False
    statuses: List[str] = Field(default=list(DEFAULT_ALERT_STATUSES))
    asset_ids: Optional[List[int]] = Field(default=None, description="null = wszystkie śledzone")
    intervals: Optional[List[str]] = Field(default=None, description="null = wszystkie śledzone")

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if v is None or not v.strip():
            return None
        v = v.strip()
        local, _, domain = v.partition("@")
        if not local or "." not in domain or any(c.isspace() for c in v):
            raise ValueError("nieprawidłowy adres e-mail")
        return v

    @field_validator("statuses")
    @classmethod
    def _statuses(cls, v):
        unknown = [s for s in v if s not in ALERT_STATUSES]
        if unknown:
            raise ValueError(f"nieznane statusy: {unknown}")
        return list(dict.fromkeys(v))


@router.get("/alerts/settings")
async def get_alert_settings(current_user: AuthUser = Depends(require_auth)):
    db = await get_db()
    settings = await db.get_factory().get_harmonic_setup_alert_settings_table().get_for_user(current_user.user_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Użytkownik nie istnieje")
    return {**settings, "available_statuses": list(ALERT_STATUSES), "smtp_configured": bool(config.smtp_host)}


@router.put("/alerts/settings")
async def put_alert_settings(request: AlertSettingsIn = Body(...), current_user: AuthUser = Depends(require_auth)):
    if request.email_enabled and not request.email:
        raise HTTPException(status_code=422, detail="włączone alerty wymagają adresu e-mail")
    if request.intervals is not None:
        _valid_intervals(request.intervals)
    db = await get_db()
    saved = await db.get_factory().get_harmonic_setup_alert_settings_table().save_for_user(
        current_user.user_id, request.email, request.email_enabled, request.statuses,
        request.asset_ids, request.intervals,
    )
    return {**saved, "available_statuses": list(ALERT_STATUSES), "smtp_configured": bool(config.smtp_host)}


@router.get("/alerts/events")
async def get_alert_events(
    asset_id: Optional[int] = Query(default=None, ge=1),
    interval: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    db = await get_db()
    events = await db.get_factory().get_harmonic_setup_events_table().recent(
        [asset_id] if asset_id else None, interval, limit
    )
    return {"events": events}


@router.post("/alerts/test")
async def send_test_alert(current_user: AuthUser = Depends(require_auth)):
    smtp = harmonic_alerts.SmtpSettings.from_config(config)
    if smtp is None:
        raise HTTPException(status_code=503, detail="poczta wychodząca nie jest skonfigurowana (SMTP_HOST)")
    db = await get_db()
    settings = await db.get_factory().get_harmonic_setup_alert_settings_table().get_for_user(current_user.user_id)
    if not settings.get("email"):
        raise HTTPException(status_code=422, detail="najpierw zapisz adres e-mail w ustawieniach alertów")
    try:
        _, body, html = harmonic_alerts.render(settings, [harmonic_alerts.sample_event()],
                                               harmonic_alerts.app_url_from_config(config))
        await asyncio.to_thread(harmonic_alerts.send_email, smtp, settings["email"],
                                "[trading.ai] test alertów", "Alerty setupów działają - przykład:\n\n" + body, html)
    except Exception as e:
        logger.error(f"Test alertu dla użytkownika {current_user.user_id} nie powiódł się: {e}")
        raise HTTPException(status_code=502, detail="wysyłka nie powiodła się - sprawdź logi serwera")
    return {"sent_to": settings["email"]}


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
    for p in patterns:
        p["strength"] = pattern_strength_or_none(p)
    await attach_setups(db, asset_id, interval, patterns)

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
