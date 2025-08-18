from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
import json

logger = logging.getLogger(__name__)

class ChartImagesHarmonicPatternsTable(AbstractTable):
    """Klasa do zarządzania tabelą łączącą ChartImagesHarmonicPatterns."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS chart_images_harmonic_patterns (
            id SERIAL PRIMARY KEY,
            chart_image_id INTEGER NOT NULL REFERENCES chart_images(id) ON DELETE CASCADE,
            harmonic_pattern_id INTEGER NOT NULL REFERENCES technical_analysis_harmonic_patterns(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chart_image_id, harmonic_pattern_id)
        );
        """
    
    async def create(self, chart_image_id: int, harmonic_pattern_id: int) -> Optional[int]:
        """Tworzy nowe powiązanie między obrazem wykresu a wzorcem harmonicznym i zwraca jego ID."""
        try:
            relation_id = await self.fetch_val(
                """INSERT INTO chart_images_harmonic_patterns (chart_image_id, harmonic_pattern_id) 
                VALUES ($1, $2) RETURNING id""",
                chart_image_id, harmonic_pattern_id
            )
            logger.info(f"Utworzono powiązanie obraz-wzorzec z ID: {relation_id}")
            return relation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia powiązania obraz-wzorzec: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera powiązanie po ID."""
        result = await self.fetch_one("""
        SELECT cihp.id, cihp.chart_image_id, cihp.harmonic_pattern_id, cihp.created_at,
               ci.image_file_path, ci.image_file_name, ci.storage,
               tahp.asset_id, tahp.x_point_timestamp, tahp.a_point_timestamp, 
               tahp.b_point_timestamp, tahp.c_point_timestamp, tahp.d_point_timestamp,
               tahp.ta_object_json,
               a.asset, a.quote
        FROM chart_images_harmonic_patterns cihp
        JOIN chart_images ci ON cihp.chart_image_id = ci.id
        JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        JOIN assets a ON tahp.asset_id = a.id
        WHERE cihp.id = $1
        """, record_id)
        
        # Parsuj JSON jeśli istnieje
        if result and 'ta_object_json' in result and result['ta_object_json']:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return result
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje powiązanie o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'chart_image_id' in kwargs:
                update_fields.append(f"chart_image_id = ${param_count}")
                values.append(kwargs['chart_image_id'])
                param_count += 1
            
            if 'harmonic_pattern_id' in kwargs:
                update_fields.append(f"harmonic_pattern_id = ${param_count}")
                values.append(kwargs['harmonic_pattern_id'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE chart_images_harmonic_patterns SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano powiązanie obraz-wzorzec z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji powiązania obraz-wzorzec: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa powiązanie o podanym ID."""
        try:
            await self.execute_query("DELETE FROM chart_images_harmonic_patterns WHERE id = $1", record_id)
            logger.info(f"Usunięto powiązanie obraz-wzorzec z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązania obraz-wzorzec: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania z limitem i offsetem."""
        results = await self.fetch_all("""
        SELECT cihp.id, cihp.chart_image_id, cihp.harmonic_pattern_id, cihp.created_at,
               ci.image_file_path, ci.image_file_name, ci.storage,
               tahp.asset_id, tahp.x_point_timestamp, tahp.a_point_timestamp, 
               tahp.b_point_timestamp, tahp.c_point_timestamp, tahp.d_point_timestamp,
               tahp.ta_object_json,
               a.asset, a.quote
        FROM chart_images_harmonic_patterns cihp
        JOIN chart_images ci ON cihp.chart_image_id = ci.id
        JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        JOIN assets a ON tahp.asset_id = a.id
        ORDER BY cihp.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        # Parsuj JSON dla każdego wzorca
        for result in results:
            if 'ta_object_json' in result and result['ta_object_json']:
                result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_chart_image_id(self, chart_image_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie wzorce harmoniczne dla danego obrazu wykresu."""
        results = await self.fetch_all("""
        SELECT cihp.id, cihp.chart_image_id, cihp.harmonic_pattern_id, cihp.created_at,
               ci.image_file_path, ci.image_file_name, ci.storage,
               tahp.asset_id, tahp.x_point_timestamp, tahp.a_point_timestamp, 
               tahp.b_point_timestamp, tahp.c_point_timestamp, tahp.d_point_timestamp,
               tahp.ta_object_json,
               a.asset, a.quote
        FROM chart_images_harmonic_patterns cihp
        JOIN chart_images ci ON cihp.chart_image_id = ci.id
        JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        JOIN assets a ON tahp.asset_id = a.id
        WHERE cihp.chart_image_id = $1
        ORDER BY cihp.id DESC LIMIT $2 OFFSET $3
        """, chart_image_id, limit, offset)
        
        # Parsuj JSON dla każdego wzorca
        for result in results:
            if 'ta_object_json' in result and result['ta_object_json']:
                result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_harmonic_pattern_id(self, harmonic_pattern_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie obrazy wykresów dla danego wzorca harmonicznego."""
        results = await self.fetch_all("""
        SELECT cihp.id, cihp.chart_image_id, cihp.harmonic_pattern_id, cihp.created_at,
               ci.image_file_path, ci.image_file_name, ci.storage,
               tahp.asset_id, tahp.x_point_timestamp, tahp.a_point_timestamp, 
               tahp.b_point_timestamp, tahp.c_point_timestamp, tahp.d_point_timestamp,
               tahp.ta_object_json,
               a.asset, a.quote
        FROM chart_images_harmonic_patterns cihp
        JOIN chart_images ci ON cihp.chart_image_id = ci.id
        JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        JOIN assets a ON tahp.asset_id = a.id
        WHERE cihp.harmonic_pattern_id = $1
        ORDER BY cihp.id DESC LIMIT $2 OFFSET $3
        """, harmonic_pattern_id, limit, offset)
        
        # Parsuj JSON dla każdego wzorca
        for result in results:
            if 'ta_object_json' in result and result['ta_object_json']:
                result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania dla danego asset."""
        results = await self.fetch_all("""
        SELECT cihp.id, cihp.chart_image_id, cihp.harmonic_pattern_id, cihp.created_at,
               ci.image_file_path, ci.image_file_name, ci.storage,
               tahp.asset_id, tahp.x_point_timestamp, tahp.a_point_timestamp, 
               tahp.b_point_timestamp, tahp.c_point_timestamp, tahp.d_point_timestamp,
               tahp.ta_object_json,
               a.asset, a.quote
        FROM chart_images_harmonic_patterns cihp
        JOIN chart_images ci ON cihp.chart_image_id = ci.id
        JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        JOIN assets a ON tahp.asset_id = a.id
        WHERE tahp.asset_id = $1
        ORDER BY cihp.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        # Parsuj JSON dla każdego wzorca
        for result in results:
            if 'ta_object_json' in result and result['ta_object_json']:
                result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def check_relation_exists(self, chart_image_id: int, harmonic_pattern_id: int) -> bool:
        """Sprawdza czy powiązanie między obrazem a wzorcem już istnieje."""
        result = await self.fetch_one("""
        SELECT COUNT(*) as count
        FROM chart_images_harmonic_patterns 
        WHERE chart_image_id = $1 AND harmonic_pattern_id = $2
        """, chart_image_id, harmonic_pattern_id)
        
        return result['count'] > 0 if result else False
    
    async def delete_by_chart_image_id(self, chart_image_id: int) -> bool:
        """Usuwa wszystkie powiązania dla danego obrazu wykresu."""
        try:
            await self.execute_query("DELETE FROM chart_images_harmonic_patterns WHERE chart_image_id = $1", chart_image_id)
            logger.info(f"Usunięto wszystkie powiązania dla obrazu wykresu z ID: {chart_image_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązań dla obrazu wykresu: {e}", exc_info=True)
            return False
    
    async def delete_by_harmonic_pattern_id(self, harmonic_pattern_id: int) -> bool:
        """Usuwa wszystkie powiązania dla danego wzorca harmonicznego."""
        try:
            await self.execute_query("DELETE FROM chart_images_harmonic_patterns WHERE harmonic_pattern_id = $1", harmonic_pattern_id)
            logger.info(f"Usunięto wszystkie powiązania dla wzorca harmonicznego z ID: {harmonic_pattern_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązań dla wzorca harmonicznego: {e}", exc_info=True)
            return False
    
    async def get_by_storage(self, storage: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera powiązania według storage obrazów."""
        results = await self.fetch_all("""
        SELECT cihp.id, cihp.chart_image_id, cihp.harmonic_pattern_id, cihp.created_at,
               ci.image_file_path, ci.image_file_name, ci.storage,
               tahp.asset_id, tahp.x_point_timestamp, tahp.a_point_timestamp, 
               tahp.b_point_timestamp, tahp.c_point_timestamp, tahp.d_point_timestamp,
               a.asset, a.quote
        FROM chart_images_harmonic_patterns cihp
        JOIN chart_images ci ON cihp.chart_image_id = ci.id
        JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        JOIN assets a ON tahp.asset_id = a.id
        WHERE ci.storage = $1
        ORDER BY cihp.id DESC LIMIT $2 OFFSET $3
        """, storage, limit, offset)
        
        return results 