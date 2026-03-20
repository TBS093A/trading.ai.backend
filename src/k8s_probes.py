"""
Odpowiedzi dla sond Kubernetes (GET /live, GET /ready).

Logika poza łańcuchem tras FastAPI, żeby nic (np. kolejność routerów)
nie narzucało autentykacji na probe’y.
"""

import logging
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)


async def live_body() -> Dict[str, str]:
    return {"status": "ok"}


async def ready_body() -> Tuple[int, Dict[str, Any]]:
    from src.auth import get_app_database

    db = await get_app_database()
    result = await db.test_connection()
    if result.get("test_passed"):
        return 200, {
            "status": "ready",
            "database": result.get("connection", "OK"),
        }
    return 503, {
        "status": "not_ready",
        "database": result.get("connection", "FAILED"),
        "error": result.get("error"),
    }
