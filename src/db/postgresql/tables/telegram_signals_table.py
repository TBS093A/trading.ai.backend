from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TelegramSignalsTable(AbstractTable):
    """Klasa do zarządzania tabelą TelegramSignals."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS telegram_signals (
            id SERIAL PRIMARY KEY,
            telegram_signal_channel_id INTEGER NOT NULL REFERENCES telegram_signal_channels(id) ON DELETE CASCADE,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, telegram_signal_channel_id: int, asset_id: int, timestamp: str, content: str) -> Optional[int]:
        """Tworzy nowy sygnał Telegram i zwraca jego ID."""
        try:
            signal_id = await self.fetch_val(
                "INSERT INTO telegram_signals (telegram_signal_channel_id, asset_id, timestamp, content) VALUES ($1, $2, $3, $4) RETURNING id",
                telegram_signal_channel_id, asset_id, timestamp, content
            )
            logger.info(f"Utworzono sygnał Telegram z ID: {signal_id}")
            return signal_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia sygnału Telegram: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera sygnał Telegram po ID."""
        return await self.fetch_one("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje sygnał Telegram o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'telegram_signal_channel_id' in kwargs:
                update_fields.append(f"telegram_signal_channel_id = ${param_count}")
                values.append(kwargs['telegram_signal_channel_id'])
                param_count += 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'timestamp' in kwargs:
                update_fields.append(f"timestamp = ${param_count}")
                values.append(kwargs['timestamp'])
                param_count += 1
            
            if 'content' in kwargs:
                update_fields.append(f"content = ${param_count}")
                values.append(kwargs['content'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE telegram_signals SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano sygnał Telegram z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji sygnału Telegram: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa sygnał Telegram o podanym ID."""
        try:
            await self.execute_query("DELETE FROM telegram_signals WHERE id = $1", record_id)
            logger.info(f"Usunięto sygnał Telegram z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania sygnału Telegram: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie sygnały Telegram z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        ORDER BY ts.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_channel_id(self, channel_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera sygnały z konkretnego kanału."""
        return await self.fetch_all("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.telegram_signal_channel_id = $1
        ORDER BY ts.id DESC LIMIT $2 OFFSET $3
        """, channel_id, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera sygnały dla konkretnego asset."""
        return await self.fetch_all("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.asset_id = $1
        ORDER BY ts.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera sygnały z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.timestamp >= $1 AND ts.timestamp <= $2
        ORDER BY ts.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje sygnały po zawartości."""
        return await self.fetch_all("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.content ILIKE $1
        ORDER BY ts.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszy sygnał dla konkretnego asset."""
        return await self.fetch_one("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.asset_id = $1
        ORDER BY ts.id DESC
        LIMIT 1
        """, asset_id)
    
    async def get_signals_by_asset_and_channel(self, asset_id: int, channel_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera sygnały dla konkretnego asset i kanału."""
        return await self.fetch_all("""
        SELECT ts.id, ts.telegram_signal_channel_id, ts.asset_id, ts.timestamp, ts.content, ts.created_at,
               tsc.name as channel_name, tsc.telegram_id as channel_telegram_id,
               a.asset, a.quote
        FROM telegram_signals ts
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        JOIN assets a ON ts.asset_id = a.id
        WHERE ts.asset_id = $1 AND ts.telegram_signal_channel_id = $2
        ORDER BY ts.id DESC LIMIT $3 OFFSET $4
        """, asset_id, channel_id, limit, offset) 