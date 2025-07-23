from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TelegramSignalChannelsTable(AbstractTable):
    """Klasa do zarządzania tabelą TelegramSignalChannels."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS telegram_signal_channels (
            id SERIAL PRIMARY KEY,
            telegram_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, telegram_id: str, name: str) -> Optional[int]:
        """Tworzy nowy kanał sygnałów Telegram i zwraca jego ID."""
        try:
            channel_id = await self.fetch_val(
                "INSERT INTO telegram_signal_channels (telegram_id, name) VALUES ($1, $2) RETURNING id",
                telegram_id, name
            )
            logger.info(f"Utworzono kanał sygnałów Telegram: {name} z ID: {channel_id}")
            return channel_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia kanału sygnałów Telegram: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera kanał sygnałów Telegram po ID."""
        return await self.fetch_one(
            "SELECT id, telegram_id, name, created_at FROM telegram_signal_channels WHERE id = $1",
            record_id
        )
    
    async def get_by_telegram_id(self, telegram_id: str) -> Optional[Dict[str, Any]]:
        """Pobiera kanał sygnałów Telegram po telegram_id."""
        return await self.fetch_one(
            "SELECT id, telegram_id, name, created_at FROM telegram_signal_channels WHERE telegram_id = $1",
            telegram_id
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje kanał sygnałów Telegram o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'telegram_id' in kwargs:
                update_fields.append(f"telegram_id = ${param_count}")
                values.append(kwargs['telegram_id'])
                param_count += 1
            
            if 'name' in kwargs:
                update_fields.append(f"name = ${param_count}")
                values.append(kwargs['name'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE telegram_signal_channels SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano kanał sygnałów Telegram z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji kanału sygnałów Telegram: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa kanał sygnałów Telegram o podanym ID."""
        try:
            await self.execute_query("DELETE FROM telegram_signal_channels WHERE id = $1", record_id)
            logger.info(f"Usunięto kanał sygnałów Telegram z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania kanału sygnałów Telegram: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie kanały sygnałów Telegram z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, telegram_id, name, created_at FROM telegram_signal_channels ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def search_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Wyszukuje kanały sygnałów Telegram po nazwie."""
        return await self.fetch_all(
            "SELECT id, telegram_id, name, created_at FROM telegram_signal_channels WHERE name ILIKE $1 ORDER BY name",
            f"%{name}%"
        )
    
    async def search_by_telegram_id(self, telegram_id: str) -> List[Dict[str, Any]]:
        """Wyszukuje kanały sygnałów Telegram po telegram_id."""
        return await self.fetch_all(
            "SELECT id, telegram_id, name, created_at FROM telegram_signal_channels WHERE telegram_id ILIKE $1 ORDER BY telegram_id",
            f"%{telegram_id}%"
        )
    
    async def get_channels_with_signal_count(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera kanały z liczbą sygnałów."""
        return await self.fetch_all("""
        SELECT tsc.id, tsc.telegram_id, tsc.name, tsc.created_at,
               COUNT(ts.id) as signal_count
        FROM telegram_signal_channels tsc
        LEFT JOIN telegram_signals ts ON tsc.id = ts.telegram_signal_channel_id
        GROUP BY tsc.id, tsc.telegram_id, tsc.name, tsc.created_at
        ORDER BY signal_count DESC, tsc.id
        LIMIT $1 OFFSET $2
        """, limit, offset) 