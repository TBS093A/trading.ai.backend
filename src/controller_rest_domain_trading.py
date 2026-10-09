"""
REST API Controller - trading z sygnałów setupów (src/trading), dashboard „Trading”.

Konta (paper; binance_futures_testnet - Binance USDT-M Futures testnet, saldo startowe z giełdy):
GET    /trading/accounts                         lista kont z podsumowaniem (kapitał, wynik, otwarte pozycje)
POST   /trading/accounts                         (admin) nowe konto: nazwa, kapitał, wariant ryzyka albo własne
PATCH  /trading/accounts/{id}                    (admin) ryzyko, filtry, włącz / wyłącz
POST   /trading/accounts/{id}/kill-switch        (admin) włącz / wyłącz wyłącznik awaryjny
GET    /trading/accounts/{id}/equity             krzywa kapitału (migawki co godzinę)
GET    /trading/accounts/{id}/signals|positions|orders|events   dzienniki konta
GET    /trading/accounts/{id}/compare            wynik konta vs backtest tych samych setupów
GET    /trading/signals/{id}/trace               ścieżka sygnału: setup -> sygnał -> zlecenia -> pozycja -> zdarzenia
Ryzyko:
GET    /trading/risk/fields                      pola ustawień z opisem i zakresem + gotowe warianty
POST   /trading/risk/preview                     skutki ustawień na transakcjach z raportu wariantów (+ bootstrap)
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from .auth import AuthUser, require_admin, require_auth
from .db.database_facade import DatabaseFacade
from .db.postgresql.database_postgresql import DatabasePostgreSQL
from .trading import binance_futures
from .trading import risk as risk_mod
from .trading.paper_exchange import pnl as position_pnl

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_auth)])
PREFIX = "/trading"
TAGS = ["Trading"]

EXCHANGES = ("paper", "binance_futures_testnet")   # "binance_futures" (live) - po próbie na testnecie
ENTRY_MODES = ("touch",)          # "confirm" - po wyborze wariantu z raportu Benchmarków

db_instance: Optional[DatabasePostgreSQL] = None
db_lock: asyncio.Lock = asyncio.Lock()


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


async def _table():
    return (await get_db()).get_factory().get_trading_table()


async def _account_or_404(table, account_id: int) -> Dict[str, Any]:
    account = await table.get_account(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail=f"konto {account_id} nie istnieje")
    return account


async def _summary(table, account: Dict[str, Any]) -> Dict[str, Any]:
    stats = await table.stats(account["id"])
    open_positions = await table.positions(account["id"], status="open")
    unrealized = sum(position_pnl(p["direction"], p["entry_price"], p["mark_price"], p["qty"])
                     for p in open_positions if p.get("mark_price") is not None)
    equity = account["cash"] + unrealized
    return {
        **account, "stats": stats, "unrealized_pnl": round(unrealized, 2), "equity": round(equity, 2),
        "return_pct": round((equity / account["starting_equity"] - 1) * 100.0, 2) if account["starting_equity"] else None,
        "drawdown_pct": round((account["peak_equity"] - equity) / account["peak_equity"] * 100.0, 2)
        if account["peak_equity"] else None,
    }


# ─────────────────────────── ryzyko ───────────────────────────

@router.get("/risk/fields")
async def get_risk_fields():
    return {"fields": risk_mod.RISK_FIELDS, "presets": risk_mod.RISK_PRESETS,
            "defaults": risk_mod.RiskSettings().as_dict(), "exchanges": list(EXCHANGES), "entry_modes": list(ENTRY_MODES)}


class RiskPreviewRequest(BaseModel):
    settings: Dict[str, Any] = Field(default_factory=dict)
    preset: Optional[str] = Field(default=None, description="conservative | balanced | aggressive (zamiast settings)")
    report_id: Optional[int] = Field(default=None, description="raport wariantów; brak = najnowszy")
    variant: str = Field(default="baseline")
    start_equity: float = Field(default=10_000.0, gt=0)
    simulations: int = Field(default=300, ge=0, le=2000)


def _settings_from(preset: Optional[str], settings: Dict[str, Any]) -> risk_mod.RiskSettings:
    if preset:
        found = next((p for p in risk_mod.RISK_PRESETS if p["key"] == preset), None)
        if found is None:
            raise HTTPException(status_code=422, detail=f"nieznany wariant ryzyka: {preset}")
        settings = {**found["settings"], **(settings or {})}
    try:
        return risk_mod.validate(settings)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/risk/preview")
async def preview_risk(request: RiskPreviewRequest = Body(...)):
    """Skutki ustawień na transakcjach wybranego wariantu z raportu Benchmarków."""
    settings = _settings_from(request.preset, request.settings)
    reports = (await get_db()).get_factory().get_harmonic_variant_reports_table()
    report = await reports.get_report(request.report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="brak raportu wariantów - uruchom go w Benchmarkach")
    trades = [t for t in await reports.get_trades(report["id"]) if t["variant"] == request.variant]
    if not trades:
        raise HTTPException(status_code=422, detail=f"raport {report['id']} nie ma transakcji wariantu {request.variant}")
    result = await asyncio.to_thread(risk_mod.preview, trades, settings, request.start_equity, request.simulations)
    return {"report_id": report["id"], "variant": request.variant, "settings": settings.as_dict(), **result}


# ─────────────────────────── konta ───────────────────────────

class AccountIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    exchange: str = Field(default="paper")
    starting_equity: float = Field(default=10_000.0, gt=0)
    entry_mode: str = Field(default="touch")
    preset: Optional[str] = Field(default="balanced")
    risk: Dict[str, Any] = Field(default_factory=dict, description="nadpisania pól wariantu")
    filters: Dict[str, Any] = Field(default_factory=dict,
                                    description="asset_ids[], intervals[], patterns[], direction long|short")


@router.get("/accounts")
async def list_accounts():
    table = await _table()
    return {"accounts": [await _summary(table, a) for a in await table.list_accounts()]}


@router.post("/accounts")
async def create_account(request: AccountIn = Body(...), current_user: AuthUser = Depends(require_admin)):
    if request.exchange not in EXCHANGES:
        raise HTTPException(status_code=422, detail=f"giełda {request.exchange} jeszcze nieobsługiwana: {EXCHANGES}")
    if request.entry_mode not in ENTRY_MODES:
        raise HTTPException(status_code=422, detail=f"tryb wejścia: {ENTRY_MODES}")
    settings = _settings_from(request.preset, request.risk)
    starting_equity = request.starting_equity
    if request.exchange in binance_futures.LIVE_EXCHANGES:
        if not binance_futures.credentials_configured(request.exchange):
            raise HTTPException(status_code=422, detail=f"{request.exchange}: brak klucza API w konfiguracji serwera")
        try:
            starting_equity = await binance_futures.from_env(request.exchange).balance()
        except Exception as e:
            logger.warning(f"Trading: saldo {request.exchange} niedostępne: {type(e).__name__}")
            raise HTTPException(status_code=502, detail=f"{request.exchange}: nie udało się pobrać salda")
        if starting_equity <= 0:
            raise HTTPException(status_code=422, detail=f"{request.exchange}: saldo konta futures jest zerowe")
    table = await _table()
    try:
        account = await table.create_account(request.name, request.exchange, starting_equity,
                                             request.entry_mode, settings.as_dict(), request.filters)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"nie udało się utworzyć konta: {e}")
    await table.log_event(account["id"], "account_created",
                          f"Konto {request.name} ({request.exchange}), kapitał {starting_equity}",
                          data={"risk": settings.as_dict(), "filters": request.filters})
    return await _summary(table, account)


class AccountPatch(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    preset: Optional[str] = None
    risk: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None


@router.patch("/accounts/{account_id}")
async def patch_account(account_id: int = Path(..., ge=1), request: AccountPatch = Body(...),
                        current_user: AuthUser = Depends(require_admin)):
    table = await _table()
    account = await _account_or_404(table, account_id)
    fields: Dict[str, Any] = {}
    if request.name is not None:
        fields["name"] = request.name
    if request.enabled is not None:
        fields["enabled"] = request.enabled
    if request.preset is not None or request.risk is not None:
        base = account["risk_json"] if request.preset is None else {}
        fields["risk_json"] = _settings_from(request.preset, {**base, **(request.risk or {})}).as_dict()
    if request.filters is not None:
        fields["filters_json"] = request.filters
    updated = await table.update_account(account_id, **fields)
    await table.log_event(account_id, "account_updated", f"Zmienione: {', '.join(fields) or 'nic'}",
                          data={k: v for k, v in fields.items()})
    return await _summary(table, updated)


class KillSwitchIn(BaseModel):
    on: bool
    reason: Optional[str] = Field(default=None, max_length=500)


@router.post("/accounts/{account_id}/kill-switch")
async def kill_switch(account_id: int = Path(..., ge=1), request: KillSwitchIn = Body(...),
                      current_user: AuthUser = Depends(require_admin)):
    table = await _table()
    await _account_or_404(table, account_id)
    reason = request.reason or ("włączony ręcznie" if request.on else None)
    updated = await table.update_account(account_id, kill_switch=request.on, kill_reason=reason)
    who = getattr(current_user, "username", "?")
    await table.log_event(account_id, "kill_switch" if request.on else "kill_switch_off",
                          f"{'Włączony' if request.on else 'Wyłączony'} przez {who}" + (f": {reason}" if reason else ""))
    return await _summary(table, updated)


@router.get("/accounts/{account_id}")
async def get_account(account_id: int = Path(..., ge=1)):
    table = await _table()
    return await _summary(table, await _account_or_404(table, account_id))


@router.get("/accounts/{account_id}/equity")
async def get_equity(account_id: int = Path(..., ge=1), limit: int = Query(default=2000, ge=1, le=10000)):
    table = await _table()
    await _account_or_404(table, account_id)
    return {"equity": await table.equity_series(account_id, limit)}


@router.get("/accounts/{account_id}/signals")
async def get_signals(account_id: int = Path(..., ge=1), status: Optional[str] = Query(default=None),
                      limit: int = Query(default=100, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    table = await _table()
    await _account_or_404(table, account_id)
    return {"signals": await table.list_signals(account_id, status, limit, offset)}


@router.get("/accounts/{account_id}/positions")
async def get_positions(account_id: int = Path(..., ge=1), status: Optional[str] = Query(default=None),
                        limit: int = Query(default=200, ge=1, le=1000), offset: int = Query(default=0, ge=0)):
    table = await _table()
    await _account_or_404(table, account_id)
    return {"positions": await table.positions(account_id, status, limit, offset)}


@router.get("/accounts/{account_id}/orders")
async def get_orders(account_id: int = Path(..., ge=1), limit: int = Query(default=100, ge=1, le=1000),
                     offset: int = Query(default=0, ge=0)):
    table = await _table()
    await _account_or_404(table, account_id)
    return {"orders": await table.list_orders(account_id, limit, offset)}


@router.get("/accounts/{account_id}/events")
async def get_events(account_id: int = Path(..., ge=1), limit: int = Query(default=200, ge=1, le=1000)):
    table = await _table()
    await _account_or_404(table, account_id)
    return {"events": await table.events(account_id, limit=limit)}


@router.get("/accounts/{account_id}/compare")
async def compare_with_backtest(account_id: int = Path(..., ge=1)):
    """Zamknięte pozycje konta vs wynik tych samych setupów w symulacji (seria produkcyjna):
    różnica średniego R = koszt wykonania (opłaty, poślizg, odrzucenia przez limity)."""
    db = await get_db()
    table = db.get_factory().get_trading_table()
    await _account_or_404(table, account_id)
    rows = await table.closed_vs_backtest(account_id)
    paired = [r for r in rows if r["backtest_r"] is not None]
    avg = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
    account_avg = avg([float(r["account_r"]) for r in paired])
    backtest_avg = avg([float(r["backtest_r"]) for r in paired])
    return {"trades": len(rows), "paired": len(paired), "account_avg_r": account_avg, "backtest_avg_r": backtest_avg,
            "execution_cost_r": round(backtest_avg - account_avg, 4) if paired else None}


@router.get("/signals/{signal_id}/trace")
async def signal_trace(signal_id: int = Path(..., ge=1)):
    """Pełna ścieżka sygnału: setup (punkty, PRZ, siła) -> sygnał -> zlecenia -> pozycja -> zdarzenia."""
    db = await get_db()
    table = db.get_factory().get_trading_table()
    signal = await table.get_signal(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail=f"sygnał {signal_id} nie istnieje")
    setup = None
    if signal.get("setup_id"):
        setup = await db.get_factory().get_technical_analysis_harmonic_setups_table().get_by_id(signal["setup_id"])
        for c in ("points_json", "confluences_json", "pre_confluences_json"):
            if setup and isinstance(setup.get(c), str):
                setup[c] = json.loads(setup[c])
    return {"signal": signal, "setup": setup, "orders": await table.orders_for_signal(signal_id),
            "position": await table.position_for_signal(signal_id),
            "events": list(reversed(await table.events(signal["account_id"], signal_id=signal_id)))}
