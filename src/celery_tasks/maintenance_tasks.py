"""
Celery Tasks - Maintenance

Sprzątanie bazy (src/db/janitor.py). Uruchamiane przez scheduler (proces _run_db_janitor,
cron z migracji 2) albo ręcznie przez POST /maintenance/db/janitor.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from ..config import config
from ..controller_rest_celery_worker import celery
from ..db.database_facade import DatabaseFacade
from ..db.janitor import DatabaseJanitor
from .utils import run_async_task_safely

logger = logging.getLogger(__name__)


async def _run_janitor(dry_run: bool) -> Dict[str, Any]:
    db = DatabaseFacade().get_database_postgresql()
    await db.init_db()
    try:
        return (await DatabaseJanitor(db).run(dry_run=dry_run)).as_dict()
    finally:
        await db.close_db()


@celery.task(bind=True, name='maintenance_tasks.db_janitor')
def db_janitor_task(self, dry_run: Optional[bool] = None) -> Dict[str, Any]:
    """dry_run=None -> wg DB_JANITOR_ENABLED (domyślnie dry-run). Ręcznie można wymusić dry-run,
    ale nie usuwanie - usuwanie włącza tylko konfiguracja."""
    effective_dry_run = True if dry_run else not config.db_janitor_enabled
    logger.info(f"🧹 db_janitor dry_run={effective_dry_run} (ID: {self.request.id})")
    start = datetime.now()
    report = run_async_task_safely(_run_janitor, dry_run=effective_dry_run)
    return {'success': True, 'task_id': self.request.id, 'report': report,
            'duration': str(datetime.now() - start)}
