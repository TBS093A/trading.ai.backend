import asyncpg
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
from .db import DatabaseFactory

logger = logging.getLogger(__name__)

class PostgreSQL:
    """Klasa do obsługi połączenia z bazą danych PostgreSQL."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
        self.factory = None
    
    async def init_db(self):
        """Inicjalizuje pulę połączeń i tworzy wszystkie tabele, jeśli nie istnieją."""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(self.database_url)
                logger.info("Utworzono pulę połączeń z bazą danych.")
                
                # Inicjalizuj fabrykę
                self.factory = DatabaseFactory(self.pool)
                
                # Utwórz wszystkie tabele
                await self._create_all_tables()
                logger.info("Sprawdzono/utworzono wszystkie tabele.")
            except Exception as e:
                logger.error(f"Błąd podczas inicjalizacji puli połączeń z bazą danych: {e}", exc_info=True)
                self.pool = None
                self.factory = None
                raise
    
    async def _create_all_tables(self):
        """Tworzy wszystkie tabele używając fabryki."""
        if self.factory is None:
            raise RuntimeError("Fabryka nie została zainicjalizowana")
        
        async with self.pool.acquire() as connection:
            # Pobierz wszystkie zapytania CREATE TABLE
            create_queries = self.factory.get_create_table_queries()
            
            # Wykonaj zapytania w odpowiedniej kolejności (z uwzględnieniem zależności)
            table_order = [
                'assets',
                'users', 
                'user_secrets',
                'transactions',
                'fundamental_analysis',
                'technical_analysis',
                'fundamental_analysis_interpretation',
                'technical_analysis_interpretation',
                'general_interpretation',
                'telegram_signal_channels',
                'telegram_signals',
                'telegram_signal_interpretation'
            ]
            
            for table_name in table_order:
                if table_name in create_queries:
                    await connection.execute(create_queries[table_name])
                    logger.info(f"Sprawdzono/utworzono tabelę: {table_name}")
    
    async def get_db_pool(self):
        """Zwraca istniejącą pulę połączeń lub inicjalizuje ją."""
        if self.pool is None:
            await self.init_db()
        if self.pool is None:
            raise ConnectionError("Pula połączeń z bazą danych jest niedostępna.")
        return self.pool
    
    def get_factory(self) -> DatabaseFactory:
        """Zwraca fabrykę tabel."""
        if self.factory is None:
            raise RuntimeError("Fabryka nie została zainicjalizowana. Wywołaj init_db() najpierw.")
        return self.factory
    
    async def close_db(self):
        """Zamyka pulę połączeń."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.factory = None
            logger.info("Zamknięto pulę połączeń z bazą danych.")
