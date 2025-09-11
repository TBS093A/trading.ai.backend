from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalysisInterpretationTable(AbstractTable):
    """Klasa do zarządzania tabelą TechnicalAnalysisInterpretation."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS technical_analysis_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            technical_analysis_id INTEGER NOT NULL REFERENCES technical_analysis_harmonic_patterns(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, asset_id: int, technical_analysis_id: int, timestamp: str, content: str) -> Optional[int]:
        """Tworzy nową interpretację analizy technicznej i zwraca jej ID."""
        try:
            interpretation_id = await self.fetch_val(
                "INSERT INTO technical_analysis_interpretation (asset_id, technical_analysis_id, timestamp, content) VALUES ($1, $2, $3, $4) RETURNING id",
                asset_id, technical_analysis_id, timestamp, content
            )
            logger.info(f"Utworzono interpretację analizy technicznej z ID: {interpretation_id}")
            return interpretation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia interpretacji analizy technicznej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację analizy technicznej po ID."""
        return await self.fetch_one("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje interpretację analizy technicznej o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'technical_analysis_id' in kwargs:
                update_fields.append(f"technical_analysis_id = ${param_count}")
                values.append(kwargs['technical_analysis_id'])
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
            query = f"UPDATE technical_analysis_interpretation SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano interpretację analizy technicznej z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji interpretacji analizy technicznej: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa interpretację analizy technicznej o podanym ID."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_interpretation WHERE id = $1", record_id)
            logger.info(f"Usunięto interpretację analizy technicznej z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania interpretacji analizy technicznej: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie interpretacje analiz technicznych z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        ORDER BY tai.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analiz technicznych dla asset."""
        return await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.asset_id = $1
        ORDER BY tai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_technical_analysis_id(self, technical_analysis_id: int) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnej analizy technicznej."""
        return await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.technical_analysis_id = $1
        ORDER BY tai.id DESC
        """, technical_analysis_id)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.timestamp >= $1 AND tai.timestamp <= $2
        ORDER BY tai.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje interpretacje po zawartości."""
        return await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.content ILIKE $1
        ORDER BY tai.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą interpretację analizy technicznej dla asset."""
        return await self.fetch_one("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.asset_id = $1
        ORDER BY tai.id DESC
        LIMIT 1
        """, asset_id)
    
    async def get_with_chart_images(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację analizy technicznej wraz z powiązanymi obrazami wykresów."""
        result = await self.fetch_one("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp,
               ARRAY_AGG(
                   CASE WHEN ci.id IS NOT NULL THEN 
                       json_build_object(
                           'id', ci.id,
                           'image_file_path', ci.image_file_path,
                           'image_file_name', ci.image_file_name,
                           'storage', ci.storage,
                           'interval', ci.interval,
                           'created_at', ci.created_at,
                           'updated_at', ci.updated_at
                       )
                   END
               ) FILTER (WHERE ci.id IS NOT NULL) as chart_images
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        LEFT JOIN technical_analysis_interpretation_chart_images taici ON tai.id = taici.technical_analysis_interpretation_id
        LEFT JOIN chart_images ci ON taici.chart_image_id = ci.id
        WHERE tai.id = $1
        GROUP BY tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
                 a.asset, a.quote, ta.x_point_timestamp
        """, record_id)
        
        if result:
            # Konwertuj chart_images z listy na listę słowników
            if result['chart_images']:
                result['chart_images'] = [img for img in result['chart_images'] if img is not None]
            else:
                result['chart_images'] = []
        
        return result
    
    async def get_all_with_chart_images(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie interpretacje analiz technicznych wraz z powiązanymi obrazami wykresów."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp,
               ARRAY_AGG(
                   CASE WHEN ci.id IS NOT NULL THEN 
                       json_build_object(
                           'id', ci.id,
                           'image_file_path', ci.image_file_path,
                           'image_file_name', ci.image_file_name,
                           'storage', ci.storage,
                           'interval', ci.interval,
                           'created_at', ci.created_at,
                           'updated_at', ci.updated_at
                       )
                   END
               ) FILTER (WHERE ci.id IS NOT NULL) as chart_images
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        LEFT JOIN technical_analysis_interpretation_chart_images taici ON tai.id = taici.technical_analysis_interpretation_id
        LEFT JOIN chart_images ci ON taici.chart_image_id = ci.id
        GROUP BY tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
                 a.asset, a.quote, ta.x_point_timestamp
        ORDER BY tai.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            # Konwertuj chart_images z listy na listę słowników
            if result['chart_images']:
                result['chart_images'] = [img for img in result['chart_images'] if img is not None]
            else:
                result['chart_images'] = []
        
        return results
    
    async def get_all_intervals_of_used_harmonic_patterns(self, record_id: int) -> List[str]:
        """Zwraca wszystkie interwały wzorców harmonicznych powiązanych z daną interpretacją analizy technicznej."""
        results = await self.fetch_all("""
        SELECT DISTINCT ta.interval 
        FROM technical_analysis_interpretation tai
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.id = $1 AND ta.interval IS NOT NULL
        ORDER BY ta.interval
        """, record_id)
        
        return [result['interval'] for result in results if result['interval']]
    
    async def get_interpretations_without_general_interpretation_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analizy technicznej które nie mają jeszcze powiązania z interpretacją generalną dla danego assetu."""
        return await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.technical_analysis_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote, ta.x_point_timestamp
        FROM technical_analysis_interpretation tai
        JOIN assets a ON tai.asset_id = a.id
        JOIN technical_analysis_harmonic_patterns ta ON tai.technical_analysis_id = ta.id
        WHERE tai.asset_id = $1
        AND NOT EXISTS (
            SELECT 1 FROM general_interpretation gi 
            WHERE gi.technical_analysis_interpretation_id = tai.id
        )
        ORDER BY tai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def count_all(self) -> int:
        """Zlicza wszystkie interpretacje analiz technicznych."""
        result = await self.fetch_val("""
        SELECT COUNT(*) FROM technical_analysis_interpretation
        """)
        
        return result or 0
    
    async def count_by_asset(self, asset_id: int) -> int:
        """Zlicza interpretacje analiz technicznych dla konkretnego assetu."""
        result = await self.fetch_val("""
        SELECT COUNT(*) FROM technical_analysis_interpretation WHERE asset_id = $1
        """, asset_id)
        
        return result or 0 