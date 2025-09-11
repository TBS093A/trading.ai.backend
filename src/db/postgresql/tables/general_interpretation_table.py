from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class GeneralInterpretationTable(AbstractTable):
    """Klasa do zarządzania tabelą GeneralInterpretation."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS general_interpretation (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            technical_analysis_interpretation_id INTEGER REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE,
            fundamental_analysis_interpretation_id INTEGER REFERENCES fundamental_analysis_interpretation(id) ON DELETE CASCADE,
            investment_strategy_id INTEGER REFERENCES investment_strategies(id) ON DELETE CASCADE,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    
    async def create(self, asset_id: int, timestamp: str, content: str, 
                    technical_analysis_interpretation_id: int = None, 
                    fundamental_analysis_interpretation_id: int = None,
                    investment_strategy_id: int = None) -> Optional[int]:
        """Tworzy nową ogólną interpretację i zwraca jej ID."""
        try:
            interpretation_id = await self.fetch_val(
                """INSERT INTO general_interpretation 
                (asset_id, timestamp, content, technical_analysis_interpretation_id, fundamental_analysis_interpretation_id, investment_strategy_id) 
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                asset_id, timestamp, content, technical_analysis_interpretation_id, fundamental_analysis_interpretation_id, investment_strategy_id
            )
            logger.info(f"Utworzono ogólną interpretację z ID: {interpretation_id}")
            return interpretation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia ogólnej interpretacji: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera ogólną interpretację po ID."""
        return await self.fetch_one("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.id = $1
        """, record_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje ogólną interpretację o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'technical_analysis_interpretation_id' in kwargs:
                update_fields.append(f"technical_analysis_interpretation_id = ${param_count}")
                values.append(kwargs['technical_analysis_interpretation_id'])
                param_count += 1
            
            if 'fundamental_analysis_interpretation_id' in kwargs:
                update_fields.append(f"fundamental_analysis_interpretation_id = ${param_count}")
                values.append(kwargs['fundamental_analysis_interpretation_id'])
                param_count += 1
            
            if 'investment_strategy_id' in kwargs:
                update_fields.append(f"investment_strategy_id = ${param_count}")
                values.append(kwargs['investment_strategy_id'])
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
            query = f"UPDATE general_interpretation SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano ogólną interpretację z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji ogólnej interpretacji: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa ogólną interpretację o podanym ID."""
        try:
            await self.execute_query("DELETE FROM general_interpretation WHERE id = $1", record_id)
            logger.info(f"Usunięto ogólną interpretację z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania ogólnej interpretacji: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie ogólne interpretacje z limitem i offsetem."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        ORDER BY gi.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera ogólne interpretacje dla asset."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.asset_id = $1
        ORDER BY gi.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_technical_analysis_interpretation_id(self, technical_analysis_interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera ogólne interpretacje dla konkretnej interpretacji analizy technicznej."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.technical_analysis_interpretation_id = $1
        ORDER BY gi.id DESC
        """, technical_analysis_interpretation_id)
    
    async def get_by_fundamental_analysis_interpretation_id(self, fundamental_analysis_interpretation_id: int) -> List[Dict[str, Any]]:
        """Pobiera ogólne interpretacje dla konkretnej interpretacji analizy fundamentalnej."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.fundamental_analysis_interpretation_id = $1
        ORDER BY gi.id DESC
        """, fundamental_analysis_interpretation_id)
    
    async def get_by_timestamp_range(self, start_timestamp: str, end_timestamp: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera ogólne interpretacje z określonego zakresu czasowego."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.timestamp >= $1 AND gi.timestamp <= $2
        ORDER BY gi.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def search_by_content(self, content: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje ogólne interpretacje po zawartości."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.content ILIKE $1
        ORDER BY gi.id DESC LIMIT $2 OFFSET $3
        """, f"%{content}%", limit, offset)
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą ogólną interpretację dla asset."""
        return await self.fetch_one("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.asset_id = $1
        ORDER BY gi.id DESC
        LIMIT 1
        """, asset_id)
    
    async def get_complete_interpretation(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera kompletną interpretację z wszystkimi powiązanymi danymi."""
        return await self.fetch_one("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               tai.content as technical_interpretation_content,
               fai.content as fundamental_interpretation_content,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN technical_analysis_interpretation tai ON gi.technical_analysis_interpretation_id = tai.id
        LEFT JOIN fundamental_analysis_interpretation fai ON gi.fundamental_analysis_interpretation_id = fai.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.asset_id = $1
        ORDER BY gi.id DESC
        LIMIT 1
        """, asset_id)
    
    async def get_by_investment_strategy_id(self, investment_strategy_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera ogólne interpretacje dla konkretnej strategii inwestycyjnej."""
        return await self.fetch_all("""
        SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
               gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
               a.asset, a.quote,
               istr.name as investment_strategy_name, istr.description as investment_strategy_description
        FROM general_interpretation gi
        JOIN assets a ON gi.asset_id = a.id
        LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
        WHERE gi.investment_strategy_id = $1
        ORDER BY gi.id DESC LIMIT $2 OFFSET $3
        """, investment_strategy_id, limit, offset)
    
    async def count_by_investment_strategy_id(self, investment_strategy_id: int) -> int:
        """Zwraca liczbę interpretacji dla danej strategii inwestycyjnej."""
        result = await self.fetch_val("SELECT COUNT(*) FROM general_interpretation WHERE investment_strategy_id = $1", investment_strategy_id)
        return result or 0
    
    async def get_all_general_interpretations_without_transactions(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera wszystkie ogólne interpretacje które nie mają powiązanych transakcji w ExchangeTransactionsTable.
        
        Args:
            limit: Maksymalna liczba wyników
            offset: Przesunięcie dla paginacji
            
        Returns:
            List[Dict[str, Any]]: Lista interpretacji bez powiązanych transakcji
        """
        try:
            results = await self.fetch_all("""
                SELECT gi.id, gi.asset_id, gi.technical_analysis_interpretation_id, 
                       gi.fundamental_analysis_interpretation_id, gi.investment_strategy_id, gi.timestamp, gi.content, gi.created_at,
                       a.asset, a.quote,
                       istr.name as investment_strategy_name, istr.description as investment_strategy_description
                FROM general_interpretation gi
                JOIN assets a ON gi.asset_id = a.id
                LEFT JOIN investment_strategies istr ON gi.investment_strategy_id = istr.id
                LEFT JOIN exchange_transactions et ON gi.id = et.general_interpretation_id
                WHERE et.general_interpretation_id IS NULL
                ORDER BY gi.id DESC
                LIMIT $1 OFFSET $2
            """, limit, offset)
            
            logger.info(f"Znaleziono {len(results)} interpretacji bez powiązanych transakcji")
            return results
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania interpretacji bez transakcji: {e}", exc_info=True)
            return []
    
    async def count_all(self) -> int:
        """Zlicza wszystkie interpretacje generalne."""
        result = await self.fetch_val("""
        SELECT COUNT(*) FROM general_interpretation
        """)
        
        return result or 0
    
    async def count_by_asset(self, asset_id: int) -> int:
        """Zlicza interpretacje generalne dla konkretnego assetu."""
        result = await self.fetch_val("""
        SELECT COUNT(*) FROM general_interpretation WHERE asset_id = $1
        """, asset_id)
        
        return result or 0 