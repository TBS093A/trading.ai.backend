from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
import json

logger = logging.getLogger(__name__)

class ChartImagesTable(AbstractTable):
    """Klasa do zarządzania tabelą ChartImages."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS chart_images (
            id SERIAL PRIMARY KEY,
            image_file_path VARCHAR(500) NOT NULL,
            image_file_name VARCHAR(255) NOT NULL,
            storage VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, image_file_path: str, image_file_name: str, storage: str) -> Optional[int]:
        """Tworzy nowy obraz wykresu i zwraca jego ID."""
        try:
            image_id = await self.fetch_val(
                """INSERT INTO chart_images (image_file_path, image_file_name, storage) 
                VALUES ($1, $2, $3) RETURNING id""",
                image_file_path, image_file_name, storage
            )
            logger.info(f"Utworzono obraz wykresu z ID: {image_id}")
            return image_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia obrazu wykresu: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera obraz wykresu po ID."""
        return await self.fetch_one("""
        SELECT id, image_file_path, image_file_name, storage, created_at, updated_at
        FROM chart_images
        WHERE id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje obraz wykresu o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'image_file_path' in kwargs:
                update_fields.append(f"image_file_path = ${param_count}")
                values.append(kwargs['image_file_path'])
                param_count += 1
            
            if 'image_file_name' in kwargs:
                update_fields.append(f"image_file_name = ${param_count}")
                values.append(kwargs['image_file_name'])
                param_count += 1
            
            if 'storage' in kwargs:
                update_fields.append(f"storage = ${param_count}")
                values.append(kwargs['storage'])
                param_count += 1
            
            if not update_fields:
                return False
            
            update_fields.append(f"updated_at = CURRENT_TIMESTAMP")
            values.append(record_id)
            query = f"UPDATE chart_images SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano obraz wykresu z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji obrazu wykresu: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa obraz wykresu o podanym ID."""
        try:
            await self.execute_query("DELETE FROM chart_images WHERE id = $1", record_id)
            logger.info(f"Usunięto obraz wykresu z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania obrazu wykresu: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie obrazy wykresów z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT id, image_file_path, image_file_name, storage, created_at, updated_at
        FROM chart_images
        ORDER BY id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_storage(self, storage: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera obrazy wykresów według storage."""
        return await self.fetch_all("""
        SELECT id, image_file_path, image_file_name, storage, created_at, updated_at
        FROM chart_images
        WHERE storage = $1
        ORDER BY id DESC LIMIT $2 OFFSET $3
        """, storage, limit, offset)
    
    async def get_by_image_file_path(self, image_file_path: str) -> Optional[Dict[str, Any]]:
        """Pobiera obraz wykresu według ścieżki pliku."""
        return await self.fetch_one("""
        SELECT id, image_file_path, image_file_name, storage, created_at, updated_at
        FROM chart_images
        WHERE image_file_path = $1
        """, image_file_path)
    
    async def search_by_image_file_path_pattern(self, pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje obrazy wykresów według wzorca w ścieżce pliku."""
        return await self.fetch_all("""
        SELECT id, image_file_path, image_file_name, storage, created_at, updated_at
        FROM chart_images
        WHERE image_file_path ILIKE $1
        ORDER BY id DESC LIMIT $2 OFFSET $3
        """, f"%{pattern}%", limit, offset)
    
    async def get_latest(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Pobiera najnowsze obrazy wykresów."""
        return await self.fetch_all("""
        SELECT id, image_file_path, image_file_name, storage, created_at, updated_at
        FROM chart_images
        ORDER BY created_at DESC LIMIT $1
        """, limit)
    
    async def check_image_exists(self, image_file_path: str) -> bool:
        """Sprawdza czy obraz o podanej ścieżce już istnieje."""
        result = await self.fetch_one("""
        SELECT COUNT(*) as count
        FROM chart_images 
        WHERE image_file_path = $1
        """, image_file_path)
        
        return result['count'] > 0 if result else False
    
    async def get_with_harmonic_patterns(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera obraz wykresu wraz z powiązanymi wzorcami harmonicznymi."""
        result = await self.fetch_one("""
        SELECT ci.id, ci.image_file_path, ci.image_file_name, ci.storage, ci.created_at, ci.updated_at,
               ARRAY_AGG(
                   CASE WHEN tahp.id IS NOT NULL THEN 
                       json_build_object(
                           'id', tahp.id,
                           'asset_id', tahp.asset_id,
                           'x_point_timestamp', tahp.x_point_timestamp,
                           'a_point_timestamp', tahp.a_point_timestamp,
                           'b_point_timestamp', tahp.b_point_timestamp,
                           'c_point_timestamp', tahp.c_point_timestamp,
                           'd_point_timestamp', tahp.d_point_timestamp,
                           'ta_object_json', tahp.ta_object_json,
                           'asset', a.asset,
                           'quote', a.quote
                       )
                   END
               ) FILTER (WHERE tahp.id IS NOT NULL) as harmonic_patterns
        FROM chart_images ci
        LEFT JOIN chart_images_harmonic_patterns cihp ON ci.id = cihp.chart_image_id
        LEFT JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        LEFT JOIN assets a ON tahp.asset_id = a.id
        WHERE ci.id = $1
        GROUP BY ci.id, ci.image_file_path, ci.image_file_name, ci.storage, ci.created_at, ci.updated_at
        """, record_id)
        
        if result:
            # Konwertuj harmonic_patterns z listy na listę słowników
            if result['harmonic_patterns']:
                result['harmonic_patterns'] = [pattern for pattern in result['harmonic_patterns'] if pattern is not None]
                # Parsuj JSON dla każdego wzorca
                for pattern in result['harmonic_patterns']:
                    if 'ta_object_json' in pattern:
                        pattern['ta_object_json'] = json.loads(pattern['ta_object_json'])
            else:
                result['harmonic_patterns'] = []
        
        return result
    
    async def get_all_with_harmonic_patterns(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie obrazy wykresów wraz z powiązanymi wzorcami harmonicznymi."""
        results = await self.fetch_all("""
        SELECT ci.id, ci.image_file_path, ci.image_file_name, ci.storage, ci.created_at, ci.updated_at,
               ARRAY_AGG(
                   CASE WHEN tahp.id IS NOT NULL THEN 
                       json_build_object(
                           'id', tahp.id,
                           'asset_id', tahp.asset_id,
                           'x_point_timestamp', tahp.x_point_timestamp,
                           'a_point_timestamp', tahp.a_point_timestamp,
                           'b_point_timestamp', tahp.b_point_timestamp,
                           'c_point_timestamp', tahp.c_point_timestamp,
                           'd_point_timestamp', tahp.d_point_timestamp,
                           'ta_object_json', tahp.ta_object_json,
                           'asset', a.asset,
                           'quote', a.quote
                       )
                   END
               ) FILTER (WHERE tahp.id IS NOT NULL) as harmonic_patterns
        FROM chart_images ci
        LEFT JOIN chart_images_harmonic_patterns cihp ON ci.id = cihp.chart_image_id
        LEFT JOIN technical_analysis_harmonic_patterns tahp ON cihp.harmonic_pattern_id = tahp.id
        LEFT JOIN assets a ON tahp.asset_id = a.id
        GROUP BY ci.id, ci.image_file_path, ci.image_file_name, ci.storage, ci.created_at, ci.updated_at
        ORDER BY ci.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            # Konwertuj harmonic_patterns z listy na listę słowników
            if result['harmonic_patterns']:
                result['harmonic_patterns'] = [pattern for pattern in result['harmonic_patterns'] if pattern is not None]
                # Parsuj JSON dla każdego wzorca
                for pattern in result['harmonic_patterns']:
                    if 'ta_object_json' in pattern:
                        pattern['ta_object_json'] = json.loads(pattern['ta_object_json'])
            else:
                result['harmonic_patterns'] = []
        
        return results 