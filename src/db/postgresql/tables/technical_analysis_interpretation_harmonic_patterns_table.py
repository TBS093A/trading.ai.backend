from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class TechnicalAnalysisInterpretationHarmonicPatternsTable(AbstractTable):
    """Klasa do zarządzania tabelą pośrednią między interpretacjami analizy technicznej a wzorcami harmonicznymi."""
    
    def create_table(self) -> str:
        return """
        -- Tabela już jest tworzona przez TechnicalAnalysisInterpretationTable
        """
    
    async def create(self, technical_analysis_interpretation_id: int, harmonic_pattern_id: int) -> Optional[int]:
        """Tworzy nowe powiązanie między interpretacją a wzorcem harmonicznym."""
        try:
            # Sprawdź czy powiązanie już istnieje
            existing = await self.fetch_one(
                "SELECT id FROM technical_analysis_interpretation_harmonic_patterns WHERE technical_analysis_interpretation_id = $1 AND harmonic_pattern_id = $2",
                technical_analysis_interpretation_id, harmonic_pattern_id
            )
            
            if existing:
                logger.debug(f"Powiązanie interpretacja-wzorzec już istnieje: {technical_analysis_interpretation_id}-{harmonic_pattern_id}")
                return None
            
            relation_id = await self.fetch_val(
                "INSERT INTO technical_analysis_interpretation_harmonic_patterns (technical_analysis_interpretation_id, harmonic_pattern_id) VALUES ($1, $2) RETURNING id",
                technical_analysis_interpretation_id, harmonic_pattern_id
            )
            logger.info(f"Utworzono powiązanie interpretacja-wzorzec: {technical_analysis_interpretation_id}-{harmonic_pattern_id} (ID: {relation_id})")
            return relation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia powiązania interpretacja-wzorzec: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera powiązanie po ID."""
        return await self.fetch_one("""
        SELECT tahp.id, tahp.technical_analysis_interpretation_id, tahp.harmonic_pattern_id,
               tai.timestamp as interpretation_timestamp, tai.content as interpretation_content,
               ta.interval as harmonic_pattern_interval
        FROM technical_analysis_interpretation_harmonic_patterns tahp
        LEFT JOIN technical_analysis_interpretation tai ON tahp.technical_analysis_interpretation_id = tai.id
        LEFT JOIN technical_analysis_harmonic_patterns ta ON tahp.harmonic_pattern_id = ta.id
        WHERE tahp.id = $1
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
            
            if 'harmonic_pattern_id' in kwargs:
                update_fields.append(f"harmonic_pattern_id = ${param_count}")
                values.append(kwargs['harmonic_pattern_id'])
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE technical_analysis_interpretation_harmonic_patterns SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano powiązanie interpretacja-wzorzec z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji powiązania interpretacja-wzorzec: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa powiązanie o podanym ID."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_interpretation_harmonic_patterns WHERE id = $1", record_id)
            logger.info(f"Usunięto powiązanie interpretacja-wzorzec z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązania interpretacja-wzorzec: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT tahp.id, tahp.technical_analysis_interpretation_id, tahp.harmonic_pattern_id,
               tai.timestamp as interpretation_timestamp, tai.content as interpretation_content,
               ta.interval as harmonic_pattern_interval
        FROM technical_analysis_interpretation_harmonic_patterns tahp
        LEFT JOIN technical_analysis_interpretation tai ON tahp.technical_analysis_interpretation_id = tai.id
        LEFT JOIN technical_analysis_harmonic_patterns ta ON tahp.harmonic_pattern_id = ta.id
        ORDER BY tahp.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_interpretation_id(self, interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania dla danej interpretacji."""
        return await self.fetch_all("""
        SELECT tahp.id, tahp.technical_analysis_interpretation_id, tahp.harmonic_pattern_id,
               ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp,
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json,
               a.asset, a.quote
        FROM technical_analysis_interpretation_harmonic_patterns tahp
        LEFT JOIN technical_analysis_harmonic_patterns ta ON tahp.harmonic_pattern_id = ta.id
        LEFT JOIN assets a ON ta.asset_id = a.id
        WHERE tahp.technical_analysis_interpretation_id = $1
        """, interpretation_id)
    
    async def get_by_harmonic_pattern_id(self, harmonic_pattern_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie powiązania dla danego wzorca harmonicznego."""
        return await self.fetch_all("""
        SELECT tahp.id, tahp.technical_analysis_interpretation_id, tahp.harmonic_pattern_id,
               tai.timestamp, tai.content, tai.asset_id,
               a.asset, a.quote
        FROM technical_analysis_interpretation_harmonic_patterns tahp
        LEFT JOIN technical_analysis_interpretation tai ON tahp.technical_analysis_interpretation_id = tai.id
        LEFT JOIN assets a ON tai.asset_id = a.id
        WHERE tahp.harmonic_pattern_id = $1
        """, harmonic_pattern_id)
    
    async def delete_by_interpretation_id(self, interpretation_id: int) -> bool:
        """Usuwa wszystkie powiązania dla danej interpretacji."""
        try:
            await self.execute_query(
                "DELETE FROM technical_analysis_interpretation_harmonic_patterns WHERE technical_analysis_interpretation_id = $1",
                interpretation_id
            )
            logger.info(f"Usunięto wszystkie powiązania dla interpretacji {interpretation_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązań dla interpretacji: {e}", exc_info=True)
            return False
    
    async def delete_by_harmonic_pattern_id(self, harmonic_pattern_id: int) -> bool:
        """Usuwa wszystkie powiązania dla danego wzorca harmonicznego."""
        try:
            await self.execute_query(
                "DELETE FROM technical_analysis_interpretation_harmonic_patterns WHERE harmonic_pattern_id = $1",
                harmonic_pattern_id
            )
            logger.info(f"Usunięto wszystkie powiązania dla wzorca harmonicznego {harmonic_pattern_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania powiązań dla wzorca harmonicznego: {e}", exc_info=True)
            return False
    
    async def count_all(self) -> int:
        """Zlicza wszystkie powiązania."""
        result = await self.fetch_val("SELECT COUNT(*) FROM technical_analysis_interpretation_harmonic_patterns")
        return result or 0
    
    async def count_by_interpretation(self, interpretation_id: int) -> int:
        """Zlicza powiązania dla konkretnej interpretacji."""
        result = await self.fetch_val(
            "SELECT COUNT(*) FROM technical_analysis_interpretation_harmonic_patterns WHERE technical_analysis_interpretation_id = $1",
            interpretation_id
        )
        return result or 0
    
    async def count_by_harmonic_pattern(self, harmonic_pattern_id: int) -> int:
        """Zlicza powiązania dla konkretnego wzorca harmonicznego."""
        result = await self.fetch_val(
            "SELECT COUNT(*) FROM technical_analysis_interpretation_harmonic_patterns WHERE harmonic_pattern_id = $1",
            harmonic_pattern_id
        )
        return result or 0

