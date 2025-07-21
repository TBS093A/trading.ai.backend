from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class FundamentalAnalysisInterpretationTable(AbstractTable):
    """Klasa do zarządzania tabelą FundamentalAnalysisInterpretation."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS fundamental_analysis_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            fundamental_analysis_id INTEGER NOT NULL REFERENCES fundamental_analysis(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, asset_id: int, fundamental_analysis_id: int, timestamp: str, content: str) -> Optional[int]:
        """Tworzy nową interpretację analizy fundamentalnej i zwraca jej ID."""
        try:
            interpretation_id = await self.fetch_val(
                "INSERT INTO fundamental_analysis_interpretation (asset_id, fundamental_analysis_id, timestamp, content) VALUES ($1, $2, $3, $4) RETURNING id",
                asset_id, fundamental_analysis_id, timestamp, content
            )
            logger.info(f"Utworzono interpretację analizy fundamentalnej z ID: {interpretation_id}")
            return interpretation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia interpretacji analizy fundamentalnej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację analizy fundamentalnej po ID."""
        return await self.fetch_one("""
        SELECT fai.id, fai.asset_id, fai.fundamental_analysis_id, fai.timestamp, fai.content, fai.created_at,
               a.asset, a.quote, fa.content as analysis_content
        FROM fundamental_analysis_interpretation fai
        JOIN assets a ON fai.asset_id = a.id
        JOIN fundamental_analysis fa ON fai.fundamental_analysis_id = fa.id
        WHERE fai.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje interpretację analizy fundamentalnej o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'fundamental_analysis_id' in kwargs:
                update_fields.append(f"fundamental_analysis_id = ${param_count}")
                values.append(kwargs['fundamental_analysis_id'])
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
            query = f"UPDATE fundamental_analysis_interpretation SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano interpretację analizy fundamentalnej z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji interpretacji analizy fundamentalnej: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa interpretację analizy fundamentalnej o podanym ID."""
        try:
            await self.execute_query("DELETE FROM fundamental_analysis_interpretation WHERE id = $1", record_id)
            logger.info(f"Usunięto interpretację analizy fundamentalnej z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania interpretacji analizy fundamentalnej: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie interpretacje analiz fundamentalnych z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT fai.id, fai.asset_id, fai.fundamental_analysis_id, fai.timestamp, fai.content, fai.created_at,
               a.asset, a.quote, fa.content as analysis_content
        FROM fundamental_analysis_interpretation fai
        JOIN assets a ON fai.asset_id = a.id
        JOIN fundamental_analysis fa ON fai.fundamental_analysis_id = fa.id
        ORDER BY fai.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analiz fundamentalnych dla asset."""
        return await self.fetch_all("""
        SELECT fai.id, fai.asset_id, fai.fundamental_analysis_id, fai.timestamp, fai.content, fai.created_at,
               a.asset, a.quote, fa.content as analysis_content
        FROM fundamental_analysis_interpretation fai
        JOIN assets a ON fai.asset_id = a.id
        JOIN fundamental_analysis fa ON fai.fundamental_analysis_id = fa.id
        WHERE fai.asset_id = $1
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_fundamental_analysis_id(self, fundamental_analysis_id: int) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnej analizy fundamentalnej."""
        return await self.fetch_all("""
        SELECT fai.id, fai.asset_id, fai.fundamental_analysis_id, fai.timestamp, fai.content, fai.created_at,
               a.asset, a.quote, fa.content as analysis_content
        FROM fundamental_analysis_interpretation fai
        JOIN assets a ON fai.asset_id = a.id
        JOIN fundamental_analysis fa ON fai.fundamental_analysis_id = fa.id
        WHERE fai.fundamental_analysis_id = $1
        ORDER BY fai.id DESC
        """, fundamental_analysis_id)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT fai.id, fai.asset_id, fai.fundamental_analysis_id, fai.timestamp, fai.content, fai.created_at,
               a.asset, a.quote, fa.content as analysis_content
        FROM fundamental_analysis_interpretation fai
        JOIN assets a ON fai.asset_id = a.id
        JOIN fundamental_analysis fa ON fai.fundamental_analysis_id = fa.id
        WHERE fai.timestamp >= $1 AND fai.timestamp <= $2
        ORDER BY fai.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje interpretacje po zawartości."""
        return await self.fetch_all("""
        SELECT fai.id, fai.asset_id, fai.fundamental_analysis_id, fai.timestamp, fai.content, fai.created_at,
               a.asset, a.quote, fa.content as analysis_content
        FROM fundamental_analysis_interpretation fai
        JOIN assets a ON fai.asset_id = a.id
        JOIN fundamental_analysis fa ON fai.fundamental_analysis_id = fa.id
        WHERE fai.content ILIKE $1
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset) 