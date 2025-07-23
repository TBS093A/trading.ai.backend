from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class FundamentalAnalysisTable(AbstractTable):
    """Klasa do zarządzania tabelą FundamentalAnalysis."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS fundamental_analysis (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            link TEXT,
            service TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, asset_id: int, timestamp: str, content: str, link: str = None, service: str = None) -> Optional[int]:
        """Tworzy nową analizę fundamentalną i zwraca jej ID."""
        try:
            analysis_id = await self.fetch_val(
                "INSERT INTO fundamental_analysis (asset_id, timestamp, content, link, service) VALUES ($1, $2, $3, $4, $5) RETURNING id",
                asset_id, timestamp, content, link, service
            )
            logger.info(f"Utworzono analizę fundamentalną z ID: {analysis_id}")
            return analysis_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia analizy fundamentalnej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera analizę fundamentalną po ID."""
        return await self.fetch_one("""
        SELECT fa.id, fa.asset_id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               a.asset, a.quote
        FROM fundamental_analysis fa
        JOIN assets a ON fa.asset_id = a.id
        WHERE fa.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje analizę fundamentalną o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
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
            
            if 'link' in kwargs:
                update_fields.append(f"link = ${param_count}")
                values.append(kwargs['link'])
                param_count += 1
            
            if 'service' in kwargs:
                update_fields.append(f"service = ${param_count}")
                values.append(kwargs['service'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE fundamental_analysis SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano analizę fundamentalną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji analizy fundamentalnej: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa analizę fundamentalną o podanym ID."""
        try:
            await self.execute_query("DELETE FROM fundamental_analysis WHERE id = $1", record_id)
            logger.info(f"Usunięto analizę fundamentalną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania analizy fundamentalnej: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie analizy fundamentalne z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT fa.id, fa.asset_id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               a.asset, a.quote
        FROM fundamental_analysis fa
        JOIN assets a ON fa.asset_id = a.id
        ORDER BY fa.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne dla asset."""
        return await self.fetch_all("""
        SELECT fa.id, fa.asset_id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               a.asset, a.quote
        FROM fundamental_analysis fa
        JOIN assets a ON fa.asset_id = a.id
        WHERE fa.asset_id = $1
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_service(self, service: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne z określonego serwisu."""
        return await self.fetch_all("""
        SELECT fa.id, fa.asset_id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               a.asset, a.quote
        FROM fundamental_analysis fa
        JOIN assets a ON fa.asset_id = a.id
        WHERE fa.service = $1
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, service, limit, offset)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT fa.id, fa.asset_id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               a.asset, a.quote
        FROM fundamental_analysis fa
        JOIN assets a ON fa.asset_id = a.id
        WHERE fa.timestamp >= $1 AND fa.timestamp <= $2
        ORDER BY fa.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje analizy fundamentalne po zawartości."""
        return await self.fetch_all("""
        SELECT fa.id, fa.asset_id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               a.asset, a.quote
        FROM fundamental_analysis fa
        JOIN assets a ON fa.asset_id = a.id
        WHERE fa.content ILIKE $1
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset) 