import asyncpg
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
from .postgresql import DatabasePostgreSQL
from src.config import config

logger = logging.getLogger(__name__)

class DatabaseFacade:
    """Klasa do fasady do obsługi bazy danych"""

    def get_database_postgresql(self) -> DatabasePostgreSQL:
        return DatabasePostgreSQL(config.get_database_url())

    def get_test_database_postgresql(self) -> DatabasePostgreSQL:
        return DatabasePostgreSQL(config.get_test_database_url())
