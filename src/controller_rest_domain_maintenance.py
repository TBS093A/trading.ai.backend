"""
REST API Controller - utrzymanie bazy (tylko administrator).

GET  /maintenance/db/janitor   raport dry-run: ile wierszy pasuje do każdej reguły janitora, ile
                               okien skanów dałoby się scalić i jakie tabele są spoza rejestru
                               (dawne funkcje) wraz z rozmiarem. Niczego nie usuwa.
POST /maintenance/db/janitor   zleca przebieg janitora (Celery). Usuwa tylko, gdy włączone
                               DB_JANITOR_ENABLED; w przeciwnym razie to też dry-run.
GET  /maintenance/db/migrations  wykonane i oczekujące migracje schematu.
"""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .auth import AuthUser, require_admin
from .config import config
from .db.database_facade import DatabaseFacade
from .db.janitor import DatabaseJanitor, summarize
from .db.postgresql import migrations
from .db.postgresql.database_postgresql import DatabasePostgreSQL

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_admin)])
PREFIX = "/maintenance"
TAGS = ["Maintenance"]

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


def _enqueue_janitor(dry_run: bool) -> str:
    from .celery_tasks.maintenance_tasks import db_janitor_task

    return db_janitor_task.apply_async(kwargs={"dry_run": dry_run}, queue="sync_queue").id


@router.get("/db/janitor")
async def janitor_report():
    """Co janitor by usunął - liczone na żywo, bez usuwania."""
    report = await DatabaseJanitor(await get_db()).run(dry_run=True)
    body = report.as_dict()
    body["deletion_enabled"] = config.db_janitor_enabled
    body["summary"] = summarize(report.rules)
    return body


@router.post("/db/janitor")
async def run_janitor(
    dry_run: bool = Query(default=False, description="true = tylko policz, nawet gdy usuwanie jest włączone"),
    current_user: AuthUser = Depends(require_admin),
):
    task_id = await asyncio.to_thread(_enqueue_janitor, dry_run)
    effective_dry_run = dry_run or not config.db_janitor_enabled
    logger.info(f"Janitor zlecony ręcznie (dry_run={effective_dry_run}), task {task_id}")
    return {"task_id": task_id, "dry_run": effective_dry_run, "deletion_enabled": config.db_janitor_enabled}


@router.get("/db/migrations")
async def list_migrations():
    db = await get_db()
    async with db.pool.acquire() as conn:
        applied = {r["id"]: r for r in await conn.fetch(
            "SELECT id, name, applied_at FROM schema_migrations ORDER BY id"
        )}
    return {
        "migrations": [
            {"id": m.id, "name": m.name, "applied": m.id in applied,
             "applied_at": applied[m.id]["applied_at"] if m.id in applied else None}
            for m in migrations.MIGRATIONS
        ],
    }
