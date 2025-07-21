from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TelegramSignalInterpretationTable(AbstractTable):
    """Klasa do zarządzania tabelą TelegramSignalInterpretation."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS telegram_signal_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            telegram_signal_id INTEGER NOT NULL REFERENCES telegram_signals(id) ON DELETE CASCADE,
            technical_analysis_interpretation_id INTEGER REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            is_scam BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, asset_id: int, telegram_signal_id: int, timestamp: str, content: str, 
                    technical_analysis_interpretation_id: int = None, is_scam: bool = False) -> Optional[int]:
        """Tworzy nową interpretację sygnału Telegram i zwraca jej ID."""
        try:
            interpretation_id = await self.fetch_val(
                """INSERT INTO telegram_signal_interpretation 
                (asset_id, telegram_signal_id, technical_analysis_interpretation_id, timestamp, content, is_scam) 
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                asset_id, telegram_signal_id, technical_analysis_interpretation_id, timestamp, content, is_scam
            )
            logger.info(f"Utworzono interpretację sygnału Telegram z ID: {interpretation_id}")
            return interpretation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia interpretacji sygnału Telegram: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację sygnału Telegram po ID."""
        return await self.fetch_one("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje interpretację sygnału Telegram o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'telegram_signal_id' in kwargs:
                update_fields.append(f"telegram_signal_id = ${param_count}")
                values.append(kwargs['telegram_signal_id'])
                param_count += 1
            
            if 'technical_analysis_interpretation_id' in kwargs:
                update_fields.append(f"technical_analysis_interpretation_id = ${param_count}")
                values.append(kwargs['technical_analysis_interpretation_id'])
                param_count += 1
            
            if 'timestamp' in kwargs:
                update_fields.append(f"timestamp = ${param_count}")
                values.append(kwargs['timestamp'])
                param_count += 1
            
            if 'content' in kwargs:
                update_fields.append(f"content = ${param_count}")
                values.append(kwargs['content'])
                param_count += 1
            
            if 'is_scam' in kwargs:
                update_fields.append(f"is_scam = ${param_count}")
                values.append(kwargs['is_scam'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE telegram_signal_interpretation SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano interpretację sygnału Telegram z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji interpretacji sygnału Telegram: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa interpretację sygnału Telegram o podanym ID."""
        try:
            await self.execute_query("DELETE FROM telegram_signal_interpretation WHERE id = $1", record_id)
            logger.info(f"Usunięto interpretację sygnału Telegram z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania interpretacji sygnału Telegram: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie interpretacje sygnałów Telegram z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        ORDER BY tsi.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje sygnałów Telegram dla konkretnego asset."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.asset_id = $1
        ORDER BY tsi.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_telegram_signal_id(self, telegram_signal_id: int) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnego sygnału Telegram."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.telegram_signal_id = $1
        ORDER BY tsi.id DESC
        """, telegram_signal_id)
    
    async def get_by_technical_analysis_interpretation_id(self, technical_analysis_interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnej interpretacji analizy technicznej."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.technical_analysis_interpretation_id = $1
        ORDER BY tsi.id DESC
        """, technical_analysis_interpretation_id)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.timestamp >= $1 AND tsi.timestamp <= $2
        ORDER BY tsi.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje interpretacje po zawartości."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.content ILIKE $1
        ORDER BY tsi.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
    
    async def get_by_scam_status(self, is_scam: bool, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje według statusu scam."""
        return await self.fetch_all("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.is_scam = $1
        ORDER BY tsi.id DESC LIMIT $2 OFFSET $3
        """, is_scam, limit, offset)
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą interpretację sygnału Telegram dla konkretnego asset."""
        return await self.fetch_one("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        WHERE tsi.asset_id = $1
        ORDER BY tsi.id DESC
        LIMIT 1
        """, asset_id)
    
    async def get_complete_interpretation(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera kompletną interpretację z wszystkimi powiązanymi danymi."""
        return await self.fetch_one("""
        SELECT tsi.id, tsi.asset_id, tsi.telegram_signal_id, tsi.technical_analysis_interpretation_id,
               tsi.timestamp, tsi.content, tsi.is_scam, tsi.created_at,
               a.asset, a.quote,
               ts.content as signal_content, ts.timestamp as signal_timestamp,
               tsc.name as channel_name,
               tai.content as technical_interpretation_content
        FROM telegram_signal_interpretation tsi
        JOIN assets a ON tsi.asset_id = a.id
        JOIN telegram_signals ts ON tsi.telegram_signal_id = ts.id
        JOIN telegram_signal_channels tsc ON ts.telegram_signal_channel_id = tsc.id
        LEFT JOIN technical_analysis_interpretation tai ON tsi.technical_analysis_interpretation_id = tai.id
        WHERE tsi.asset_id = $1
        ORDER BY tsi.id DESC
        LIMIT 1
        """, asset_id) 