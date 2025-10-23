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
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS technical_analysis_interpretation_harmonic_patterns (
            id SERIAL PRIMARY KEY,
            technical_analysis_interpretation_id INTEGER NOT NULL REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE,
            harmonic_pattern_id INTEGER NOT NULL REFERENCES technical_analysis_harmonic_patterns(id) ON DELETE CASCADE,
            UNIQUE(technical_analysis_interpretation_id, harmonic_pattern_id)
        );
        """
    
    async def create(self, asset_id: int, harmonic_pattern_ids: List[int], timestamp: str, content: str) -> Optional[int]:
        """Tworzy nową interpretację analizy technicznej i zwraca jej ID."""
        try:
            # Utwórz interpretację
            interpretation_id = await self.fetch_val(
                "INSERT INTO technical_analysis_interpretation (asset_id, timestamp, content) VALUES ($1, $2, $3) RETURNING id",
                asset_id, timestamp, content
            )
            
            # Utwórz powiązania z harmonic patterns
            for harmonic_pattern_id in harmonic_pattern_ids:
                await self.execute_query(
                    "INSERT INTO technical_analysis_interpretation_harmonic_patterns (technical_analysis_interpretation_id, harmonic_pattern_id) VALUES ($1, $2)",
                    interpretation_id, harmonic_pattern_id
                )
            
            logger.info(f"Utworzono interpretację analizy technicznej z ID: {interpretation_id} dla {len(harmonic_pattern_ids)} wzorców harmonicznych")
            return interpretation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia interpretacji analizy technicznej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację analizy technicznej po ID."""
        result = await self.fetch_one("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.id = $1
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        """, record_id)
        
        return result
    
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
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analiz technicznych dla asset."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.asset_id = $1
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        return results
    
    async def get_by_harmonic_pattern_id(self, harmonic_pattern_id: int) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnego wzorca harmonicznego."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tahp.harmonic_pattern_id = $1
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC
        """, harmonic_pattern_id)
        
        return results
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.timestamp >= $1 AND tai.timestamp <= $2
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        return results
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje interpretacje po zawartości."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.content ILIKE $1
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
        
        return results
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą interpretację analizy technicznej dla asset."""
        result = await self.fetch_one("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.asset_id = $1
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC
        LIMIT 1
        """, asset_id)
        
        return result
    
    async def get_with_chart_images(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację analizy technicznej wraz z powiązanymi obrazami wykresów."""
        result = await self.fetch_one("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids,
               ARRAY_AGG(
                   DISTINCT CASE WHEN ci.id IS NOT NULL THEN 
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
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        LEFT JOIN technical_analysis_interpretation_chart_images taici ON tai.id = taici.technical_analysis_interpretation_id
        LEFT JOIN chart_images ci ON taici.chart_image_id = ci.id
        WHERE tai.id = $1
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
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
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids,
               ARRAY_AGG(
                   DISTINCT CASE WHEN ci.id IS NOT NULL THEN 
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
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        LEFT JOIN technical_analysis_interpretation_chart_images taici ON tai.id = taici.technical_analysis_interpretation_id
        LEFT JOIN chart_images ci ON taici.chart_image_id = ci.id
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
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
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        LEFT JOIN technical_analysis_harmonic_patterns ta ON tahp.harmonic_pattern_id = ta.id
        WHERE tai.id = $1 AND ta.interval IS NOT NULL
        ORDER BY ta.interval
        """, record_id)
        
        return [result['interval'] for result in results if result['interval']]
    
    async def get_interpretations_without_general_interpretation_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analizy technicznej które nie mają jeszcze powiązania z interpretacją generalną dla danego assetu."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.asset_id = $1
        AND NOT EXISTS (
            SELECT 1 FROM general_interpretation gi 
            WHERE gi.technical_analysis_interpretation_id = tai.id
        )
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        return results
    
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
    
    async def get_by_timestamp_range_and_asset_id(self, start_timestamp: str, end_timestamp: str, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego i asset."""
        results = await self.fetch_all("""
        SELECT tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at,
               a.asset, a.quote,
               array_agg(DISTINCT tahp.harmonic_pattern_id) as harmonic_pattern_ids
        FROM technical_analysis_interpretation tai
        LEFT JOIN assets a ON tai.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation_harmonic_patterns tahp ON tai.id = tahp.technical_analysis_interpretation_id
        WHERE tai.timestamp >= $1 AND tai.timestamp <= $2 AND tai.asset_id = $3
        GROUP BY tai.id, tai.asset_id, tai.timestamp, tai.content, tai.created_at, a.asset, a.quote
        ORDER BY tai.id DESC LIMIT $4 OFFSET $5
        """, start_timestamp, end_timestamp, asset_id, limit, offset)
        
        return results
    
    async def add_harmonic_pattern_to_interpretation(self, interpretation_id: int, harmonic_pattern_id: int) -> bool:
        """Dodaje wzorzec harmoniczny do interpretacji."""
        try:
            await self.execute_query(
                "INSERT INTO technical_analysis_interpretation_harmonic_patterns (technical_analysis_interpretation_id, harmonic_pattern_id) VALUES ($1, $2)",
                interpretation_id, harmonic_pattern_id
            )
            logger.info(f"Dodano wzorzec harmoniczny {harmonic_pattern_id} do interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas dodawania wzorca harmonicznego do interpretacji: {e}", exc_info=True)
            return False
    
    async def remove_harmonic_pattern_from_interpretation(self, interpretation_id: int, harmonic_pattern_id: int) -> bool:
        """Usuwa wzorzec harmoniczny z interpretacji."""
        try:
            await self.execute_query(
                "DELETE FROM technical_analysis_interpretation_harmonic_patterns WHERE technical_analysis_interpretation_id = $1 AND harmonic_pattern_id = $2",
                interpretation_id, harmonic_pattern_id
            )
            logger.info(f"Usunięto wzorzec harmoniczny {harmonic_pattern_id} z interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania wzorca harmonicznego z interpretacji: {e}", exc_info=True)
            return False
    
    async def get_interpretation_harmonic_patterns(self, interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie wzorce harmoniczne powiązane z interpretacją."""
        return await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, 
               ta.b_point_timestamp, ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN technical_analysis_interpretation_harmonic_patterns tahp ON ta.id = tahp.harmonic_pattern_id
        JOIN assets a ON ta.asset_id = a.id
        WHERE tahp.technical_analysis_interpretation_id = $1
        """, interpretation_id) 