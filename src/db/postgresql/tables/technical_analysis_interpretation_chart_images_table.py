from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalysisInterpretationChartImagesTable(AbstractTable):
    """Klasa do zarządzania tabelą łączącą TechnicalAnalysisInterpretation z ChartImages."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS technical_analysis_interpretation_chart_images (
            id SERIAL PRIMARY KEY,
            technical_analysis_interpretation_id INTEGER NOT NULL REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE,
            chart_image_id INTEGER NOT NULL REFERENCES chart_images(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(technical_analysis_interpretation_id, chart_image_id)
        );
        """
    
    async def create(self, technical_analysis_interpretation_id: int, chart_image_id: int) -> Optional[int]:
        """Tworzy nowe powiązanie między interpretacją analizy technicznej a obrazem wykresu i zwraca jego ID."""
        try:
            relation_id = await self.fetch_val(
                """INSERT INTO technical_analysis_interpretation_chart_images (technical_analysis_interpretation_id, chart_image_id) 
                VALUES ($1, $2) RETURNING id""",
                technical_analysis_interpretation_id, chart_image_id
            )
            logger.info(f"Utworzono powiązanie interpretacja-obraz z ID: {relation_id}")
            return relation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia powiązania interpretacja-obraz: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera powiązanie po ID."""
        return await self.fetch_one("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        WHERE taici.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje powiązanie o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'technical_analysis_interpretation_id' in kwargs:
                update_fields.append(f"technical_analysis_interpretation_id = ${param_count}")
                values.append(kwargs['technical_analysis_interpretation_id'])
                param_count += 1
            
            if 'chart_image_id' in kwargs:
                update_fields.append(f"chart_image_id = ${param_count}")
                values.append(kwargs['chart_image_id'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE technical_analysis_interpretation_chart_images SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano powiązanie interpretacja-obraz z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji powiązania interpretacja-obraz: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa powiązanie o podanym ID."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_interpretation_chart_images WHERE id = $1", record_id)
            logger.info(f"Usunięto powiązanie interpretacja-obraz z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązania interpretacja-obraz: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania z limitem i offsetem."""
        results = await self.fetch_all("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        ORDER BY taici.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        return results
    
    async def get_by_interpretation_id(self, interpretation_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie obrazy wykresów dla danej interpretacji analizy technicznej."""
        results = await self.fetch_all("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        WHERE taici.technical_analysis_interpretation_id = $1
        ORDER BY taici.id DESC LIMIT $2 OFFSET $3
        """, interpretation_id, limit, offset)
        
        return results
    
    async def get_by_chart_image_id(self, chart_image_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie interpretacje analizy technicznej dla danego obrazu wykresu."""
        results = await self.fetch_all("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        WHERE taici.chart_image_id = $1
        ORDER BY taici.id DESC LIMIT $2 OFFSET $3
        """, chart_image_id, limit, offset)
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania dla danego asset."""
        results = await self.fetch_all("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        WHERE tai.asset_id = $1
        ORDER BY taici.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        return results
    
    async def check_relation_exists(self, interpretation_id: int, chart_image_id: int) -> bool:
        """Sprawdza czy powiązanie między interpretacją a obrazem już istnieje."""
        result = await self.fetch_one("""
        SELECT COUNT(*) as count
        FROM technical_analysis_interpretation_chart_images 
        WHERE technical_analysis_interpretation_id = $1 AND chart_image_id = $2
        """, interpretation_id, chart_image_id)
        
        return result['count'] > 0 if result else False
    
    async def delete_by_interpretation_id(self, interpretation_id: int) -> bool:
        """Usuwa wszystkie powiązania dla danej interpretacji analizy technicznej."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_interpretation_chart_images WHERE technical_analysis_interpretation_id = $1", interpretation_id)
            logger.info(f"Usunięto wszystkie powiązania dla interpretacji z ID: {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązań dla interpretacji: {e}", exc_info=True)
            return False
    
    async def delete_by_chart_image_id(self, chart_image_id: int) -> bool:
        """Usuwa wszystkie powiązania dla danego obrazu wykresu."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_interpretation_chart_images WHERE chart_image_id = $1", chart_image_id)
            logger.info(f"Usunięto wszystkie powiązania dla obrazu wykresu z ID: {chart_image_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązań dla obrazu wykresu: {e}", exc_info=True)
            return False
    
    async def get_by_storage(self, storage: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera powiązania według storage obrazów."""
        results = await self.fetch_all("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        WHERE ci.storage = $1
        ORDER BY taici.id DESC LIMIT $2 OFFSET $3
        """, storage, limit, offset)
        
        return results
    
    async def get_by_interval(self, interval: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera powiązania według interwału obrazów."""
        results = await self.fetch_all("""
        SELECT taici.id, taici.technical_analysis_interpretation_id, taici.chart_image_id, taici.created_at,
               tai.asset_id, tai.timestamp, tai.content,
               ci.image_file_path, ci.image_file_name, ci.storage, ci.interval,
               a.asset, a.quote
        FROM technical_analysis_interpretation_chart_images taici
        JOIN technical_analysis_interpretation tai ON taici.technical_analysis_interpretation_id = tai.id
        JOIN chart_images ci ON taici.chart_image_id = ci.id
        JOIN assets a ON tai.asset_id = a.id
        WHERE ci.interval = $1
        ORDER BY taici.id DESC LIMIT $2 OFFSET $3
        """, interval, limit, offset)
        
        return results 