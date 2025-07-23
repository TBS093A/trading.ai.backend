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

class FundamentalAnalysisTable(AbstractTable):
    """Klasa do zarządzania tabelą FundamentalAnalysis."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS fundamental_analysis (
            id SERIAL PRIMARY KEY,
            timestamp BIGINT NOT NULL,
            content JSONB NOT NULL,
            link TEXT,
            service TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS fundamental_analysis_assets (
            id SERIAL PRIMARY KEY,
            fundamental_analysis_id INTEGER NOT NULL REFERENCES fundamental_analysis(id) ON DELETE CASCADE,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(fundamental_analysis_id, asset_id)
        );
        """
    
    async def create(self, asset_ids: List[int], timestamp: int, content: Dict[str, Any], link: str = None, service: str = None) -> Optional[int]:
        """Tworzy nową analizę fundamentalną i zwraca jej ID."""
        try:
            # Konwertuj NumPy typy przed serializacją JSON
            converted_content = convert_numpy_types(content)
            
            # Utwórz analizę fundamentalną
            analysis_id = await self.fetch_val(
                "INSERT INTO fundamental_analysis (timestamp, content, link, service) VALUES ($1, $2, $3, $4) RETURNING id",
                timestamp, json.dumps(converted_content), link, service
            )
            
            # Utwórz powiązania z assetami
            for asset_id in asset_ids:
                await self.execute_query(
                    "INSERT INTO fundamental_analysis_assets (fundamental_analysis_id, asset_id) VALUES ($1, $2)",
                    analysis_id, asset_id
                )
            
            logger.info(f"Utworzono analizę fundamentalną z ID: {analysis_id} dla {len(asset_ids)} assetów")
            return analysis_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia analizy fundamentalnej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera analizę fundamentalną po ID."""
        result = await self.fetch_one("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.id = $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        """, record_id)
        
        if result:
            result['content'] = json.loads(result['content'])
        
        return result
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje analizę fundamentalną o podanym ID."""
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
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne dla asset."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE faa.asset_id = $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_service(self, service: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne z określonego serwisu."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.service = $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, service, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_timestamp_range(self, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne z określonego zakresu czasowego."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.timestamp >= $1 AND fa.timestamp <= $2
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_timestamp(self, timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne dla konkretnego timestamp."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.timestamp = $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, timestamp, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą analizę fundamentalną dla asset."""
        result = await self.fetch_one("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE faa.asset_id = $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.timestamp DESC
        LIMIT 1
        """, asset_id)
        
        if result:
            result['content'] = json.loads(result['content'])
        
        return result
    
    async def get_by_timestamp_range_and_asset_id(self, start_timestamp: int, end_timestamp: int, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne z określonego zakresu czasowego i asset."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.timestamp >= $1 AND fa.timestamp <= $2 AND faa.asset_id = $3
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $4 OFFSET $5
        """, start_timestamp, end_timestamp, asset_id, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def get_by_timestamp_range_and_service(self, start_timestamp: int, end_timestamp: int, service: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne z określonego zakresu czasowego i serwisu."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.timestamp >= $1 AND fa.timestamp <= $2 AND fa.service = $3
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $4 OFFSET $5
        """, start_timestamp, end_timestamp, service, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def search_by_json_pattern(self, pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje analizy fundamentalne po wzorcu w JSON."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.content::text ILIKE $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, f"%{pattern}%", limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje analizy fundamentalne po zawartości (w JSON)."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.content::text ILIKE $1
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def check_analysis_exists(self, asset_ids: List[int], timestamp: int, service: str) -> bool:
        """Sprawdza czy analiza o podanych parametrach już istnieje."""
        # Sprawdź czy istnieje analiza z tym samym timestamp i service
        result = await self.fetch_one("""
        SELECT fa.id
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        WHERE fa.timestamp = $1 AND fa.service = $2 AND faa.asset_id = ANY($3)
        LIMIT 1
        """, timestamp, service, asset_ids)
        
        return result is not None
    
    async def get_by_timestamp_and_service(self, timestamp: int, service: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy fundamentalne dla konkretnego timestamp i serwisu."""
        results = await self.fetch_all("""
        SELECT fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at,
               array_agg(a.asset) as assets, array_agg(a.quote) as quotes, array_agg(a.id) as asset_ids
        FROM fundamental_analysis fa
        JOIN fundamental_analysis_assets faa ON fa.id = faa.fundamental_analysis_id
        JOIN assets a ON faa.asset_id = a.id
        WHERE fa.timestamp = $1 AND fa.service = $2
        GROUP BY fa.id, fa.timestamp, fa.content, fa.link, fa.service, fa.created_at
        ORDER BY fa.id DESC LIMIT $3 OFFSET $4
        """, timestamp, service, limit, offset)
        
        for result in results:
            result['content'] = json.loads(result['content'])
        
        return results
    
    async def add_asset_to_analysis(self, analysis_id: int, asset_id: int) -> bool:
        """Dodaje asset do istniejącej analizy fundamentalnej."""
        try:
            await self.execute_query(
                "INSERT INTO fundamental_analysis_assets (fundamental_analysis_id, asset_id) VALUES ($1, $2)",
                analysis_id, asset_id
            )
            logger.info(f"Dodano asset {asset_id} do analizy {analysis_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas dodawania asset do analizy: {e}", exc_info=True)
            return False
    
    async def remove_asset_from_analysis(self, analysis_id: int, asset_id: int) -> bool:
        """Usuwa asset z analizy fundamentalnej."""
        try:
            await self.execute_query(
                "DELETE FROM fundamental_analysis_assets WHERE fundamental_analysis_id = $1 AND asset_id = $2",
                analysis_id, asset_id
            )
            logger.info(f"Usunięto asset {asset_id} z analizy {analysis_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania asset z analizy: {e}", exc_info=True)
            return False
    
    async def get_analysis_assets(self, analysis_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie assety powiązane z analizą fundamentalną."""
        return await self.fetch_all("""
        SELECT a.id, a.asset, a.quote
        FROM assets a
        JOIN fundamental_analysis_assets faa ON a.id = faa.asset_id
        WHERE faa.fundamental_analysis_id = $1
        """, analysis_id) 