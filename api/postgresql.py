import asyncpg
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class PostgreSQL:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
    
    async def init_db(self):
        """Inicjalizuje pulę połączeń i tworzy wszystkie tabele, jeśli nie istnieją."""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(self.database_url)
                logger.info("Utworzono pulę połączeń z bazą danych.")
                async with self.pool.acquire() as connection:
                    await self._create_tables(connection)
                    logger.info("Sprawdzono/utworzono wszystkie tabele.")
            except Exception as e:
                logger.error(f"Błąd podczas inicjalizacji puli połączeń z bazą danych: {e}", exc_info=True)
                self.pool = None
                raise
    
    async def _create_tables(self, connection):
        """Tworzy wszystkie tabele z relacjami."""
        
        # Tabela Assets
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,
            asset TEXT NOT NULL,
            quote TEXT NOT NULL,
            UNIQUE(asset, quote)
        );
        """)
        
        # Tabela Users
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Tabela UserSecrets (relacja 1 user do wielu userSecrets)
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS user_secrets (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, key)
        );
        """)
        
        # Tabela Transactions (relacja z assets i users)
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            exchange TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Tabela FundamentalAnalysis (relacja z assets)
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS fundamental_analysis (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            link TEXT,
            service TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Tabela FundamentalAnalysisInterpretation
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS fundamental_analysis_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            fundamental_analysis_id INTEGER NOT NULL REFERENCES fundamental_analysis(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Tabela TechnicalAnalysis (relacja z assets)
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS technical_analysis (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            x_point_timestamp TEXT NOT NULL,
            ta_object_json JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Tabela TechnicalAnalysisInterpretation
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS technical_analysis_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            technical_analysis_id INTEGER NOT NULL REFERENCES technical_analysis(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Tabela GeneralInterpretation
        await connection.execute("""
        CREATE TABLE IF NOT EXISTS general_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            technical_analysis_interpretation_id INTEGER REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE,
            fundamental_analysis_interpretation_id INTEGER REFERENCES fundamental_analysis_interpretation(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """)
    
    async def get_db_pool(self):
        """Zwraca istniejącą pulę połączeń lub inicjalizuje ją."""
        if self.pool is None:
            await self.init_db()
        if self.pool is None:
            raise ConnectionError("Pula połączeń z bazą danych jest niedostępna.")
        return self.pool
    
    # Metody dla tabeli Assets
    async def create_asset(self, asset: str, quote: str) -> Optional[int]:
        """Tworzy nowy asset i zwraca jego ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                asset_id = await connection.fetchval(
                    "INSERT INTO assets (asset, quote) VALUES ($1, $2) RETURNING id",
                    asset, quote
                )
                logger.info(f"Utworzono asset: {asset}/{quote} z ID: {asset_id}")
                return asset_id
            except asyncpg.UniqueViolationError:
                logger.warning(f"Asset {asset}/{quote} już istnieje")
                return await self.get_asset_id(asset, quote)
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia asset: {e}", exc_info=True)
                return None
    
    async def get_asset_id(self, asset: str, quote: str) -> Optional[int]:
        """Pobiera ID asset na podstawie asset i quote."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                asset_id = await connection.fetchval(
                    "SELECT id FROM assets WHERE asset = $1 AND quote = $2",
                    asset, quote
                )
                return asset_id
            except Exception as e:
                logger.error(f"Błąd podczas pobierania asset ID: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli Users
    async def create_user(self, username: str, password: str, email: str) -> Optional[int]:
        """Tworzy nowego użytkownika i zwraca jego ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                user_id = await connection.fetchval(
                    "INSERT INTO users (username, password, email) VALUES ($1, $2, $3) RETURNING id",
                    username, password, email
                )
                logger.info(f"Utworzono użytkownika: {username} z ID: {user_id}")
                return user_id
            except asyncpg.UniqueViolationError:
                logger.warning(f"Użytkownik {username} lub email {email} już istnieje")
                return None
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia użytkownika: {e}", exc_info=True)
                return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Pobiera użytkownika na podstawie nazwy użytkownika."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                user = await connection.fetchrow(
                    "SELECT id, username, password, email, created_at FROM users WHERE username = $1",
                    username
                )
                return dict(user) if user else None
            except Exception as e:
                logger.error(f"Błąd podczas pobierania użytkownika: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli UserSecrets
    async def save_user_secret(self, user_id: int, key: str, value: str) -> bool:
        """Zapisuje secret użytkownika."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                await connection.execute("""
                INSERT INTO user_secrets (user_id, key, value)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, key) DO UPDATE
                SET value = EXCLUDED.value, created_at = CURRENT_TIMESTAMP
                """, user_id, key, value)
                logger.info(f"Zapisano secret dla użytkownika {user_id}, klucz: {key}")
                return True
            except Exception as e:
                logger.error(f"Błąd podczas zapisywania secret: {e}", exc_info=True)
                return False
    
    async def get_user_secret(self, user_id: int, key: str) -> Optional[str]:
        """Pobiera secret użytkownika."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                value = await connection.fetchval(
                    "SELECT value FROM user_secrets WHERE user_id = $1 AND key = $2",
                    user_id, key
                )
                return value
            except Exception as e:
                logger.error(f"Błąd podczas pobierania secret: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli Transactions
    async def create_transaction(self, asset_id: int, user_id: int, timestamp: str, exchange: str) -> Optional[int]:
        """Tworzy nową transakcję i zwraca jej ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                transaction_id = await connection.fetchval(
                    "INSERT INTO transactions (asset_id, user_id, timestamp, exchange) VALUES ($1, $2, $3, $4) RETURNING id",
                    asset_id, user_id, timestamp, exchange
                )
                logger.info(f"Utworzono transakcję z ID: {transaction_id}")
                return transaction_id
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia transakcji: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli FundamentalAnalysis
    async def create_fundamental_analysis(self, asset_id: int, timestamp: str, content: str, link: str = None, service: str = None) -> Optional[int]:
        """Tworzy nową analizę fundamentalną i zwraca jej ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                analysis_id = await connection.fetchval(
                    "INSERT INTO fundamental_analysis (asset_id, timestamp, content, link, service) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                    asset_id, timestamp, content, link, service
                )
                logger.info(f"Utworzono analizę fundamentalną z ID: {analysis_id}")
                return analysis_id
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia analizy fundamentalnej: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli FundamentalAnalysisInterpretation
    async def create_fundamental_analysis_interpretation(self, asset_id: int, fundamental_analysis_id: int, timestamp: str, content: str) -> Optional[int]:
        """Tworzy nową interpretację analizy fundamentalnej i zwraca jej ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                interpretation_id = await connection.fetchval(
                    "INSERT INTO fundamental_analysis_interpretation (asset_id, fundamental_analysis_id, timestamp, content) VALUES ($1, $2, $3, $4) RETURNING id",
                    asset_id, fundamental_analysis_id, timestamp, content
                )
                logger.info(f"Utworzono interpretację analizy fundamentalnej z ID: {interpretation_id}")
                return interpretation_id
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia interpretacji analizy fundamentalnej: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli TechnicalAnalysis
    async def create_technical_analysis(self, asset_id: int, x_point_timestamp: str, ta_object_json: Dict[str, Any]) -> Optional[int]:
        """Tworzy nową analizę techniczną i zwraca jej ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                analysis_id = await connection.fetchval(
                    "INSERT INTO technical_analysis (asset_id, x_point_timestamp, ta_object_json) VALUES ($1, $2, $3) RETURNING id",
                    asset_id, x_point_timestamp, json.dumps(ta_object_json)
                )
                logger.info(f"Utworzono analizę techniczną z ID: {analysis_id}")
                return analysis_id
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia analizy technicznej: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli TechnicalAnalysisInterpretation
    async def create_technical_analysis_interpretation(self, asset_id: int, technical_analysis_id: int, timestamp: str, content: str) -> Optional[int]:
        """Tworzy nową interpretację analizy technicznej i zwraca jej ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                interpretation_id = await connection.fetchval(
                    "INSERT INTO technical_analysis_interpretation (asset_id, technical_analysis_id, timestamp, content) VALUES ($1, $2, $3, $4) RETURNING id",
                    asset_id, technical_analysis_id, timestamp, content
                )
                logger.info(f"Utworzono interpretację analizy technicznej z ID: {interpretation_id}")
                return interpretation_id
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia interpretacji analizy technicznej: {e}", exc_info=True)
                return None
    
    # Metody dla tabeli GeneralInterpretation
    async def create_general_interpretation(self, asset_id: int, timestamp: str, content: str, 
                                         technical_analysis_interpretation_id: int = None, 
                                         fundamental_analysis_interpretation_id: int = None) -> Optional[int]:
        """Tworzy nową ogólną interpretację i zwraca jej ID."""
        db_pool = await self.get_db_pool()
        async with db_pool.acquire() as connection:
            try:
                interpretation_id = await connection.fetchval(
                    """INSERT INTO general_interpretation 
                    (asset_id, timestamp, content, technical_analysis_interpretation_id, fundamental_analysis_interpretation_id) 
                    VALUES ($1, $2, $3, $4, $5) RETURNING id""",
                    asset_id, timestamp, content, technical_analysis_interpretation_id, fundamental_analysis_interpretation_id
                )
                logger.info(f"Utworzono ogólną interpretację z ID: {interpretation_id}")
                return interpretation_id
            except Exception as e:
                logger.error(f"Błąd podczas tworzenia ogólnej interpretacji: {e}", exc_info=True)
                return None
    
    async def close_db(self):
        """Zamyka pulę połączeń."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Zamknięto pulę połączeń z bazą danych.")
