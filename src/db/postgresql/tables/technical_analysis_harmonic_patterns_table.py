from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

def convert_numpy_types(obj):
    """Konwertuje NumPy typy na standardowe typy Python dla serializacji JSON."""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj

class TechnicalAnalysisHarmonicPatternsTable(AbstractTable):
    """Klasa do zarządzania tabelą TechnicalAnalysisHarmonicPatterns."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS technical_analysis_harmonic_patterns (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            x_point_timestamp BIGINT,
            a_point_timestamp BIGINT,
            b_point_timestamp BIGINT,
            c_point_timestamp BIGINT,
            d_point_timestamp BIGINT,
            ta_object_json JSONB NOT NULL
        );
        """
    
    async def create(self, asset_id: int, ta_object_json: Dict[str, Any], 
                    x_point_timestamp: int = None, a_point_timestamp: int = None, 
                    b_point_timestamp: int = None, c_point_timestamp: int = None, 
                    d_point_timestamp: int = None) -> Optional[int]:
        """Tworzy nową analizę techniczną i zwraca jej ID."""
        try:
            # Konwertuj NumPy typy przed serializacją JSON
            converted_ta_object_json = convert_numpy_types(ta_object_json)
            
            analysis_id = await self.fetch_val(
                """INSERT INTO technical_analysis_harmonic_patterns 
                (asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp, ta_object_json) 
                VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp, json.dumps(converted_ta_object_json)
            )
            logger.info(f"Utworzono analizę techniczną z ID: {analysis_id}")
            return analysis_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia analizy technicznej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera analizę techniczną po ID."""
        result = await self.fetch_one("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.id = $1
        """, record_id)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return result
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje analizę techniczną o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'x_point_timestamp' in kwargs:
                update_fields.append(f"x_point_timestamp = ${param_count}")
                values.append(kwargs['x_point_timestamp'])
                param_count += 1
            
            if 'a_point_timestamp' in kwargs:
                update_fields.append(f"a_point_timestamp = ${param_count}")
                values.append(kwargs['a_point_timestamp'])
                param_count += 1
            
            if 'b_point_timestamp' in kwargs:
                update_fields.append(f"b_point_timestamp = ${param_count}")
                values.append(kwargs['b_point_timestamp'])
                param_count += 1
            
            if 'c_point_timestamp' in kwargs:
                update_fields.append(f"c_point_timestamp = ${param_count}")
                values.append(kwargs['c_point_timestamp'])
                param_count += 1
            
            if 'd_point_timestamp' in kwargs:
                update_fields.append(f"d_point_timestamp = ${param_count}")
                values.append(kwargs['d_point_timestamp'])
                param_count += 1
            
            if 'ta_object_json' in kwargs:
                update_fields.append(f"ta_object_json = ${param_count}")
                # Konwertuj NumPy typy przed serializacją JSON
                converted_ta_object_json = convert_numpy_types(kwargs['ta_object_json'])
                values.append(json.dumps(converted_ta_object_json))
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE technical_analysis_harmonic_patterns SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano analizę techniczną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji analizy technicznej: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa analizę techniczną o podanym ID."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_harmonic_patterns WHERE id = $1", record_id)
            logger.info(f"Usunięto analizę techniczną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania analizy technicznej: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie analizy techniczne z limitem i offsetem."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        ORDER BY ta.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne dla asset."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_timestamp_range(self, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne z określonego zakresu czasowego (używa x_point_timestamp)."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.x_point_timestamp >= $1 AND ta.x_point_timestamp <= $2
        ORDER BY ta.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą analizę techniczną dla asset."""
        result = await self.fetch_one("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1
        ORDER BY ta.id DESC
        LIMIT 1
        """, asset_id)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return result
    
    async def search_by_json_pattern(self, pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje analizy techniczne po wzorcu w JSON."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.ta_object_json::text ILIKE $1
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, f"%{pattern}%", limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_point_timestamp(self, point_type: str, timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne według konkretnego punktu czasowego."""
        if point_type not in ['x', 'a', 'b', 'c', 'd']:
            raise ValueError("point_type musi być jednym z: 'x', 'a', 'b', 'c', 'd'")
        
        column_name = f"{point_type}_point_timestamp"
        results = await self.fetch_all(f"""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.{column_name} = $1
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, timestamp, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_by_point_timestamp_range(self, point_type: str, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne według zakresu czasowego konkretnego punktu."""
        if point_type not in ['x', 'a', 'b', 'c', 'd']:
            raise ValueError("point_type musi być jednym z: 'x', 'a', 'b', 'c', 'd'")
        
        column_name = f"{point_type}_point_timestamp"
        results = await self.fetch_all(f"""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.{column_name} >= $1 AND ta.{column_name} <= $2
        ORDER BY ta.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_complete_patterns(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera kompletne wzorce harmoniczne (wszystkie punkty wypełnione)."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 
        AND ta.x_point_timestamp IS NOT NULL 
        AND ta.a_point_timestamp IS NOT NULL 
        AND ta.b_point_timestamp IS NOT NULL 
        AND ta.c_point_timestamp IS NOT NULL 
        AND ta.d_point_timestamp IS NOT NULL
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results
    
    async def get_incomplete_patterns(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera niekompletne wzorce harmoniczne (przynajmniej jeden punkt jest NULL)."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 
        AND (ta.x_point_timestamp IS NULL 
        OR ta.a_point_timestamp IS NULL 
        OR ta.b_point_timestamp IS NULL 
        OR ta.c_point_timestamp IS NULL 
        OR ta.d_point_timestamp IS NULL)
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results 

    async def get_by_timestamp_range_and_asset_id(self, start_timestamp: int, end_timestamp: int, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne z określonego zakresu czasowego i asset."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.x_point_timestamp >= $1 AND ta.x_point_timestamp <= $2 AND ta.asset_id = $3
        ORDER BY ta.id DESC LIMIT $4 OFFSET $5
        """, start_timestamp, end_timestamp, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return results 
    
    async def check_pattern_exists(self, asset_id: int, x_point_timestamp: int, a_point_timestamp: int, 
                                 b_point_timestamp: int, c_point_timestamp: int, d_point_timestamp: int) -> bool:
        """Sprawdza czy wzorzec o podanych timestampach już istnieje dla danego asset."""
        result = await self.fetch_one("""
        SELECT COUNT(*) as count
        FROM technical_analysis_harmonic_patterns 
        WHERE asset_id = $1 
        AND x_point_timestamp = $2 
        AND a_point_timestamp = $3 
        AND b_point_timestamp = $4 
        AND c_point_timestamp = $5 
        AND d_point_timestamp = $6
        """, asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp)
        
        return result['count'] > 0 if result else False
    
    async def get_by_point_timestamps(self, asset_id: int, x_point_timestamp: int, a_point_timestamp: int, 
                                     b_point_timestamp: int, c_point_timestamp: int, d_point_timestamp: int) -> Optional[Dict[str, Any]]:
        """Pobiera wzorzec o podanych timestampach dla danego asset."""
        result = await self.fetch_one("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 
        AND ta.x_point_timestamp = $2 
        AND ta.a_point_timestamp = $3 
        AND ta.b_point_timestamp = $4 
        AND ta.c_point_timestamp = $5 
        AND ta.d_point_timestamp = $6
        LIMIT 1
        """, asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
        
        return result
    
    async def get_with_chart_images(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera wzorzec harmoniczny wraz z powiązanymi obrazami wykresów."""
        result = await self.fetch_one("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote,
               ARRAY_AGG(
                   CASE WHEN ci.id IS NOT NULL THEN 
                       json_build_object(
                           'id', ci.id,
                           'image_file_path', ci.image_file_path,
                           'image_file_name', ci.image_file_name,
                           'storage', ci.storage,
                           'created_at', ci.created_at,
                           'updated_at', ci.updated_at
                       )
                   END
               ) FILTER (WHERE ci.id IS NOT NULL) as chart_images
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        LEFT JOIN chart_images_harmonic_patterns cihp ON ta.id = cihp.harmonic_pattern_id
        LEFT JOIN chart_images ci ON cihp.chart_image_id = ci.id
        WHERE ta.id = $1
        GROUP BY ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
                 ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
                 a.asset, a.quote
        """, record_id)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            # Konwertuj chart_images z listy na listę słowników
            if result['chart_images']:
                result['chart_images'] = [img for img in result['chart_images'] if img is not None]
            else:
                result['chart_images'] = []
        
        return result
    
    async def get_all_with_chart_images(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie wzorce harmoniczne wraz z powiązanymi obrazami wykresów."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote,
               ARRAY_AGG(
                   CASE WHEN ci.id IS NOT NULL THEN 
                       json_build_object(
                           'id', ci.id,
                           'image_file_path', ci.image_file_path,
                           'image_file_name', ci.image_file_name,
                           'storage', ci.storage,
                           'created_at', ci.created_at,
                           'updated_at', ci.updated_at
                       )
                   END
               ) FILTER (WHERE ci.id IS NOT NULL) as chart_images
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        LEFT JOIN chart_images_harmonic_patterns cihp ON ta.id = cihp.harmonic_pattern_id
        LEFT JOIN chart_images ci ON cihp.chart_image_id = ci.id
        GROUP BY ta.id, ta.asset_id, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
                 ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
                 a.asset, a.quote
        ORDER BY ta.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            # Konwertuj chart_images z listy na listę słowników
            if result['chart_images']:
                result['chart_images'] = [img for img in result['chart_images'] if img is not None]
            else:
                result['chart_images'] = []
        
        return results 