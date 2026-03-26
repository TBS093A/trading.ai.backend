from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class AssetExchangesTable(AbstractTable):
    """Klasa do zarządzania tabelą AssetExchanges (relacja wiele-do-wielu)."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS asset_exchanges (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL,
            exchange_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(asset_id, exchange_id),
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE
        );
        """
    
    async def create(self, asset_id: int, exchange_id: int) -> Optional[int]:
        """Tworzy nową relację asset-exchange i zwraca jej ID."""
        try:
            relation_id = await self.fetch_val(
                "INSERT INTO asset_exchanges (asset_id, exchange_id) VALUES ($1, $2) RETURNING id",
                asset_id, exchange_id
            )
            logger.info(f"Utworzono relację asset-exchange: {asset_id}-{exchange_id} z ID: {relation_id}")
            return relation_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia relacji asset-exchange: {e}", exc_info=True)
            return None
    
    async def create_many(self, asset_exchange_pairs: List[Dict[str, int]]) -> Dict[str, int]:
        """
        Tworzy wiele relacji asset-exchange jednym zapytaniem.
        
        Args:
            asset_exchange_pairs: Lista słowników z kluczami 'asset_id' i 'exchange_id'
            
        Returns:
            Dict[str, int]: Słownik mapujący klucz "asset_id:exchange_id" na ID relacji
        """
        if not asset_exchange_pairs:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            for pair in asset_exchange_pairs:
                asset_id = pair['asset_id']
                exchange_id = pair['exchange_id']
                
                values_list.append(f"(${param_counter}, ${param_counter + 1})")
                params.extend([asset_id, exchange_id])
                param_counter += 2
            
            query = f"""
                INSERT INTO asset_exchanges (asset_id, exchange_id) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (asset_id, exchange_id) DO NOTHING
                RETURNING id, asset_id, exchange_id
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_relations = {}
            for result in results:
                key = f"{result['asset_id']}:{result['exchange_id']}"
                created_relations[key] = result['id']
            
            logger.info(f"Utworzono {len(created_relations)} nowych relacji asset-exchange z {len(asset_exchange_pairs)} prób")
            return created_relations
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu relacji asset-exchange: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera relację asset-exchange po ID."""
        return await self.fetch_one("""
            SELECT ae.id, ae.asset_id, ae.exchange_id, ae.created_at,
                   a.asset, a.quote, e.name as exchange_name
            FROM asset_exchanges ae
            JOIN assets a ON ae.asset_id = a.id
            JOIN exchanges e ON ae.exchange_id = e.id
            WHERE ae.id = $1
        """, record_id)
    
    async def get_by_asset_id(self, asset_id: int) -> List[Dict[str, Any]]:
        """Pobiera wszystkie exchanges dla danego asset."""
        return await self.fetch_all("""
            SELECT ae.id, ae.asset_id, ae.exchange_id, ae.created_at,
                   a.asset, a.quote, e.name as exchange_name, e.display_name
            FROM asset_exchanges ae
            JOIN assets a ON ae.asset_id = a.id
            JOIN exchanges e ON ae.exchange_id = e.id
            WHERE ae.asset_id = $1
            ORDER BY e.name
        """, asset_id)
    
    async def get_by_exchange_id(self, exchange_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie assety dla danego exchange z kind i country."""
        return await self.fetch_all("""
            SELECT ae.id, ae.asset_id, ae.exchange_id, ae.created_at,
                   a.asset, a.quote, a.full_name,
                   (SELECT ak.name FROM asset_kind_map akm JOIN asset_kinds ak ON akm.kind_id = ak.id WHERE akm.asset_id = a.id LIMIT 1) as kind,
                   (SELECT c.code FROM asset_country_map acm JOIN countries c ON acm.country_id = c.id WHERE acm.asset_id = a.id LIMIT 1) as country,
                   e.name as exchange_name
            FROM asset_exchanges ae
            JOIN assets a ON ae.asset_id = a.id
            JOIN exchanges e ON ae.exchange_id = e.id
            WHERE ae.exchange_id = $1
            ORDER BY a.asset, a.quote LIMIT $2 OFFSET $3
        """, exchange_id, limit, offset)
    
    async def get_by_asset_and_exchange(self, asset_id: int, exchange_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera konkretną relację asset-exchange."""
        return await self.fetch_one("""
            SELECT ae.id, ae.asset_id, ae.exchange_id, ae.created_at,
                   a.asset, a.quote, e.name as exchange_name
            FROM asset_exchanges ae
            JOIN assets a ON ae.asset_id = a.id
            JOIN exchanges e ON ae.exchange_id = e.id
            WHERE ae.asset_id = $1 AND ae.exchange_id = $2
        """, asset_id, exchange_id)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje relację asset-exchange o podanym ID."""
        try:
            # Sprawdź jakie pola są dostępne do aktualizacji
            allowed_fields = ['asset_id', 'exchange_id']
            update_fields = []
            params = []
            param_counter = 1
            
            for field, value in kwargs.items():
                if field in allowed_fields:
                    update_fields.append(f"{field} = ${param_counter}")
                    params.append(value)
                    param_counter += 1
            
            if not update_fields:
                logger.warning(f"Brak dozwolonych pól do aktualizacji dla relacji asset-exchange {record_id}")
                return False
            
            # Dodaj record_id jako ostatni parametr
            params.append(record_id)
            
            query = f"""
                UPDATE asset_exchanges 
                SET {', '.join(update_fields)}
                WHERE id = ${param_counter}
            """
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano relację asset-exchange z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji relacji asset-exchange: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa relację asset-exchange o podanym ID."""
        try:
            await self.execute_query("DELETE FROM asset_exchanges WHERE id = $1", record_id)
            logger.info(f"Usunięto relację asset-exchange z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania relacji asset-exchange: {e}", exc_info=True)
            return False
    
    async def delete_by_asset_and_exchange(self, asset_id: int, exchange_id: int) -> bool:
        """Usuwa konkretną relację asset-exchange."""
        try:
            await self.execute_query(
                "DELETE FROM asset_exchanges WHERE asset_id = $1 AND exchange_id = $2",
                asset_id, exchange_id
            )
            logger.info(f"Usunięto relację asset-exchange: {asset_id}-{exchange_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania relacji asset-exchange: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie relacje asset-exchange z limitem i offsetem."""
        return await self.fetch_all("""
            SELECT ae.id, ae.asset_id, ae.exchange_id, ae.created_at,
                   a.asset, a.quote, e.name as exchange_name
            FROM asset_exchanges ae
            JOIN assets a ON ae.asset_id = a.id
            JOIN exchanges e ON ae.exchange_id = e.id
            ORDER BY a.asset, e.name
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_assets_with_exchanges(self) -> List[Dict[str, Any]]:
        """Pobiera wszystkie assety z ich exchanges."""
        return await self.fetch_all("""
            SELECT a.id, a.asset, a.quote,
                   array_agg(e.name) as exchanges,
                   array_agg(e.display_name) as exchange_display_names
            FROM assets a
            LEFT JOIN asset_exchanges ae ON a.id = ae.asset_id
            LEFT JOIN exchanges e ON ae.exchange_id = e.id
            GROUP BY a.id, a.asset, a.quote
            ORDER BY a.asset, a.quote
        """)
    
    async def get_exchanges_with_assets(self) -> List[Dict[str, Any]]:
        """Pobiera wszystkie exchanges z ich assetami."""
        return await self.fetch_all("""
            SELECT e.id, e.name, e.display_name, e.is_active,
                   array_agg(a.asset) as assets,
                   array_agg(a.quote) as quotes
            FROM exchanges e
            LEFT JOIN asset_exchanges ae ON e.id = ae.exchange_id
            LEFT JOIN assets a ON ae.asset_id = a.id
            GROUP BY e.id, e.name, e.display_name, e.is_active
            ORDER BY e.name
        """) 