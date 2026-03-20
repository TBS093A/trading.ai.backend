"""
Odpowiedzi dla sond Kubernetes (GET /live, GET /ready).

Logika poza łańcuchem tras FastAPI, żeby nic (np. kolejność routerów)
nie narzucało autentykacji na probe’y.
"""

import logging
from typing import Any, Dict, Tuple
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def normalize_asgi_path(scope: dict) -> str:
    """Ścieżka z ASGI scope (preferowane nad request.url.path przy proxy / edge cases)."""
    path = scope.get("path") or "/"
    if isinstance(path, bytes):
        path = path.decode("utf-8", errors="replace")
    path = unquote(path)
    if "?" in path:
        path = path.split("?", 1)[0]
    while "//" in path:
        path = path.replace("//", "/")
    return path.rstrip("/") or "/"


def is_probe_path(scope: dict, name: str) -> bool:
    """name: 'live' | 'ready' — m.in. /live, /api/live (pełny segment, nie ...healthlive)."""
    p = normalize_asgi_path(scope)
    suffix = f"/{name}"
    if p == suffix:
        return True
    if not p.endswith(suffix):
        return False
    i = len(p) - len(suffix)
    return i > 0 and p[i - 1] == "/"


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
