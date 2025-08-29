from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import json
import logging

logger = logging.getLogger(__name__)

def convert_numpy_types(obj):
    """Konwertuje NumPy typy na standardowe typy Python dla serializacji JSON."""
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    elif hasattr(obj, 'tolist'):  # NumPy arrays
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return str(obj)

class FundamentalAnalysisInterpretationTable(AbstractTable):
    """Klasa do zarządzania tabelą FundamentalAnalysisInterpretation."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS fundamental_analysis_interpretation (
            id SERIAL PRIMARY KEY,
            timestamp BIGINT NOT NULL,
            content JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS fundamental_analysis_interpretation_assets (
            id SERIAL PRIMARY KEY,
            fundamental_analysis_interpretation_id INTEGER NOT NULL REFERENCES fundamental_analysis_interpretation(id) ON DELETE CASCADE,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(fundamental_analysis_interpretation_id, asset_id)
        );
        
        CREATE TABLE IF NOT EXISTS fundamental_analysis_interpretation_analyses (
            id SERIAL PRIMARY KEY,
            fundamental_analysis_interpretation_id INTEGER NOT NULL REFERENCES fundamental_analysis_interpretation(id) ON DELETE CASCADE,
            fundamental_analysis_id INTEGER NOT NULL REFERENCES fundamental_analysis(id) ON DELETE CASCADE,
            UNIQUE(fundamental_analysis_interpretation_id, fundamental_analysis_id)
        );
        """
    
    async def create(self, asset_ids: List[int], fundamental_analysis_ids: List[int], timestamp: int, content: Dict[str, Any]) -> Optional[int]:
        """Tworzy nową interpretację analizy fundamentalnej i zwraca jej ID."""
        try:
            # Konwertuj NumPy typy przed serializacją JSON
            converted_content = convert_numpy_types(content)
            
            # Utwórz interpretację
            interpretation_id = await self.fetch_val(
                "INSERT INTO fundamental_analysis_interpretation (timestamp, content) VALUES ($1, $2) RETURNING id",
                timestamp, json.dumps(converted_content)
            )
            
            # Utwórz powiązania z assetami
            for asset_id in asset_ids:
                await self.execute_query(
                    "INSERT INTO fundamental_analysis_interpretation_assets (fundamental_analysis_interpretation_id, asset_id) VALUES ($1, $2)",
                    interpretation_id, asset_id
                )
            
            # Utwórz powiązania z analizami fundamentalnymi
            for fundamental_analysis_id in fundamental_analysis_ids:
                await self.execute_query(
                    "INSERT INTO fundamental_analysis_interpretation_analyses (fundamental_analysis_interpretation_id, fundamental_analysis_id) VALUES ($1, $2)",
                    interpretation_id, fundamental_analysis_id
                )
            
            logger.info(f"Utworzono interpretację analizy fundamentalnej z ID: {interpretation_id} dla {len(asset_ids)} assetów i {len(fundamental_analysis_ids)} analiz")
            return interpretation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia interpretacji analizy fundamentalnej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera interpretację analizy fundamentalnej po ID."""
        result = await self.fetch_one("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE fai.id = $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        """, record_id)
        
        if result:
            result['content'] = json.loads(result['content'])
        
        return result
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje interpretację analizy fundamentalnej o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'timestamp' in kwargs:
                update_fields.append(f"timestamp = ${param_count}")
                values.append(kwargs['timestamp'])
                param_count += 1
            
            if 'content' in kwargs:
                update_fields.append(f"content = ${param_count}")
                # Konwertuj NumPy typy przed serializacją JSON
                converted_content = convert_numpy_types(kwargs['content'])
                values.append(json.dumps(converted_content))
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
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analiz fundamentalnych dla asset."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE faia.asset_id = $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_fundamental_analysis_id(self, fundamental_analysis_id: int) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnej analizy fundamentalnej."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE faian.fundamental_analysis_id = $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC
        """, fundamental_analysis_id)
    
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_timestamp_range(self, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE fai.timestamp >= $1 AND fai.timestamp <= $2
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje interpretacje po zawartości (w JSON)."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE fai.content::text ILIKE $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def add_asset_to_interpretation(self, interpretation_id: int, asset_id: int) -> bool:
        """Dodaje asset do interpretacji."""
        try:
            await self.execute_query(
                "INSERT INTO fundamental_analysis_interpretation_assets (fundamental_analysis_interpretation_id, asset_id) VALUES ($1, $2)",
                interpretation_id, asset_id
            )
            logger.info(f"Dodano asset {asset_id} do interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas dodawania asset do interpretacji: {e}", exc_info=True)
            return False
    
    async def remove_asset_from_interpretation(self, interpretation_id: int, asset_id: int) -> bool:
        """Usuwa asset z interpretacji."""
        try:
            await self.execute_query(
                "DELETE FROM fundamental_analysis_interpretation_assets WHERE fundamental_analysis_interpretation_id = $1 AND asset_id = $2",
                interpretation_id, asset_id
            )
            logger.info(f"Usunięto asset {asset_id} z interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania asset z interpretacji: {e}", exc_info=True)
            return False
    
    async def add_analysis_to_interpretation(self, interpretation_id: int, fundamental_analysis_id: int) -> bool:
        """Dodaje analizę fundamentalną do interpretacji."""
        try:
            await self.execute_query(
                "INSERT INTO fundamental_analysis_interpretation_analyses (fundamental_analysis_interpretation_id, fundamental_analysis_id) VALUES ($1, $2)",
                interpretation_id, fundamental_analysis_id
            )
            logger.info(f"Dodano analizę {fundamental_analysis_id} do interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas dodawania analizy do interpretacji: {e}", exc_info=True)
            return False
    
    async def remove_analysis_from_interpretation(self, interpretation_id: int, fundamental_analysis_id: int) -> bool:
        """Usuwa analizę fundamentalną z interpretacji."""
        try:
            await self.execute_query(
                "DELETE FROM fundamental_analysis_interpretation_analyses WHERE fundamental_analysis_interpretation_id = $1 AND fundamental_analysis_id = $2",
                interpretation_id, fundamental_analysis_id
            )
            logger.info(f"Usunięto analizę {fundamental_analysis_id} z interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania analizy z interpretacji: {e}", exc_info=True)
            return False
    
    async def get_interpretation_assets(self, interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie assety powiązane z interpretacją."""
        return await self.fetch_all("""
        SELECT a.id, a.asset, a.quote
        FROM assets a
        JOIN fundamental_analysis_interpretation_assets faia ON a.id = faia.asset_id
        WHERE faia.fundamental_analysis_interpretation_id = $1
        """, interpretation_id)
    
    async def get_interpretation_analyses(self, interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie analizy fundamentalne powiązane z interpretacją."""
        return await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_interpretation_analyses faian ON fa.id = faian.fundamental_analysis_id
        WHERE faian.fundamental_analysis_interpretation_id = $1
        """, interpretation_id)
    
    async def check_interpretation_exists(self, asset_ids: List[int], fundamental_analysis_ids: List[int], timestamp: int) -> bool:
        """Sprawdza czy interpretacja o podanych parametrach już istnieje."""
        result = await self.fetch_one("""
        SELECT fai.id
        FROM fundamental_analysis_interpretation fai
        JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        WHERE fai.timestamp = $1 
        AND faia.asset_id = ANY($2) 
        AND faian.fundamental_analysis_id = ANY($3)
        LIMIT 1
        """, timestamp, asset_ids, fundamental_analysis_ids)
        
        return result is not None
    
    async def get_by_timestamp(self, timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje dla konkretnego timestamp."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE fai.timestamp = $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, timestamp, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą interpretację dla asset."""
        result = await self.fetch_one("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE faia.asset_id = $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.timestamp DESC
        LIMIT 1
        """, asset_id)
        
        if result:
            result['content'] = json.loads(result['content'])
        
        return result
    
    async def get_by_timestamp_range_and_asset_id(self, start_timestamp: int, end_timestamp: int, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje z określonego zakresu czasowego i asset."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE fai.timestamp >= $1 AND fai.timestamp <= $2 AND faia.asset_id = $3
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $4 OFFSET $5
        """, start_timestamp, end_timestamp, asset_id, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def search_by_json_pattern(self, pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje interpretacje po wzorcu w JSON."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE fai.content::text ILIKE $1
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, f"%{pattern}%", limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_interpretations_without_general_interpretation_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera interpretacje analizy fundamentalnej które nie mają jeszcze powiązania z interpretacją generalną dla danego assetu."""
        results = await self.fetch_all("""
        SELECT fai.id, fai.timestamp, fai.content, fai.created_at,
               array_agg(DISTINCT a.asset) as assets, 
               array_agg(DISTINCT a.quote) as quotes, 
               array_agg(DISTINCT a.id) as asset_ids,
               array_agg(DISTINCT fa.id) as fundamental_analysis_ids
        FROM fundamental_analysis_interpretation fai
        LEFT JOIN fundamental_analysis_interpretation_assets faia ON fai.id = faia.fundamental_analysis_interpretation_id
        LEFT JOIN assets a ON faia.asset_id = a.id
        LEFT JOIN fundamental_analysis_interpretation_analyses faian ON fai.id = faian.fundamental_analysis_interpretation_id
        LEFT JOIN fundamental_analysis fa ON faian.fundamental_analysis_id = fa.id
        WHERE faia.asset_id = $1 
        AND NOT EXISTS (
            SELECT 1 FROM general_interpretation gi 
            WHERE gi.fundamental_analysis_interpretation_id = fai.id
        )
        GROUP BY fai.id, fai.timestamp, fai.content, fai.created_at
        ORDER BY fai.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results 