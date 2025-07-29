from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class AssetsTable(AbstractTable):
    """Klasa do zarządzania tabelą Assets."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,
            asset TEXT NOT NULL,
            quote TEXT NOT NULL,
            UNIQUE(asset, quote)
        );
        """
    
    async def create(self, asset: str, quote: str) -> Optional[int]:
        """Tworzy nowy asset i zwraca jego ID."""
        try:
            asset_id = await self.fetch_val(
                "INSERT INTO assets (asset, quote) VALUES ($1, $2) RETURNING id",
                asset, quote
            )
            logger.info(f"Utworzono asset: {asset}/{quote} z ID: {asset_id}")
            return asset_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia asset: {e}", exc_info=True)
            return None
    
    async def check_many(self, assets: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Sprawdza które assety już istnieją w bazie danych.
        
        Args:
            assets: Lista słowników z kluczami 'asset' i 'quote'
            
        Returns:
            Dict[str, int]: Słownik mapujący asset na jego ID (tylko dla istniejących)
        """
        if not assets:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            asset_quotes = [(item['asset'], item['quote']) for item in assets]
            
            # Buduj zapytanie z wieloma warunkami OR
            conditions = []
            params = []
            param_counter = 1
            
            for asset, quote in asset_quotes:
                conditions.append(f"(asset = ${param_counter} AND quote = ${param_counter + 1})")
                params.extend([asset, quote])
                param_counter += 2
            
            query = f"""
                SELECT id, asset, quote 
                FROM assets 
                WHERE {' OR '.join(conditions)}
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            existing_assets = {}
            for result in results:
                asset_key = f"{result['asset']}/{result['quote']}"
                existing_assets[asset_key] = result['id']
            
            logger.info(f"Sprawdzono {len(assets)} assetów, znaleziono {len(existing_assets)} istniejących")
            return existing_assets
            
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania wielu assetów: {e}", exc_info=True)
            return {}
    
    async def create_many(self, assets: List[Dict[str, str]]) -> Dict[str, int]:
        """
        Tworzy wiele assetów jednym zapytaniem i zwraca ich ID.
        
        Args:
            assets: Lista słowników z kluczami 'asset' i 'quote'
            
        Returns:
            Dict[str, int]: Słownik mapujący asset na jego ID
        """
        if not assets:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            asset_quotes = [(item['asset'], item['quote']) for item in assets]
            
            # Buduj zapytanie INSERT z wieloma wartościami
            values_list = []
            params = []
            param_counter = 1
            
            for asset, quote in asset_quotes:
                values_list.append(f"(${param_counter}, ${param_counter + 1})")
                params.extend([asset, quote])
                param_counter += 2
            
            query = f"""
                INSERT INTO assets (asset, quote) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (asset, quote) DO NOTHING
                RETURNING id, asset, quote
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_assets = {}
            for result in results:
                asset_key = f"{result['asset']}/{result['quote']}"
                created_assets[asset_key] = result['id']
            
            logger.info(f"Utworzono {len(created_assets)} nowych assetów z {len(assets)} prób")
            return created_assets
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu assetów: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera asset po ID."""
        return await self.fetch_one(
            "SELECT id, asset, quote FROM assets WHERE id = $1",
            record_id
        )
    
    async def get_by_asset(self, asset: str) -> Optional[Dict[str, Any]]:
        """Pobiera pierwszy asset po nazwie asset (bez względu na quote)."""
        return await self.fetch_one(
            "SELECT id, asset, quote FROM assets WHERE asset = $1 ORDER BY id LIMIT 1",
            asset
        )
    
    async def get_by_asset_quote(self, asset: str, quote: str) -> Optional[Dict[str, Any]]:
        """Pobiera asset po asset i quote."""
        return await self.fetch_one(
            "SELECT id, asset, quote FROM assets WHERE asset = $1 AND quote = $2",
            asset, quote
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje asset o podanym ID."""
        try:
            if 'asset' in kwargs and 'quote' in kwargs:
                await self.execute_query(
                    "UPDATE assets SET asset = $1, quote = $2 WHERE id = $3",
                    kwargs['asset'], kwargs['quote'], record_id
                )
                logger.info(f"Zaktualizowano asset z ID: {record_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji asset: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa asset o podanym ID."""
        try:
            await self.execute_query("DELETE FROM assets WHERE id = $1", record_id)
            logger.info(f"Usunięto asset z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania asset: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie assety z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, asset, quote FROM assets ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def search_by_asset(self, asset: str) -> List[Dict[str, Any]]:
        """Wyszukuje assety po nazwie asset."""
        return await self.fetch_all(
            "SELECT id, asset, quote FROM assets WHERE asset ILIKE $1 ORDER BY asset",
            f"%{asset}%"
        )
    
    async def search_by_quote(self, quote: str) -> List[Dict[str, Any]]:
        """Wyszukuje assety po nazwie quote."""
        return await self.fetch_all(
            "SELECT id, asset, quote FROM assets WHERE quote ILIKE $1 ORDER BY quote",
            f"%{quote}%"
        ) 