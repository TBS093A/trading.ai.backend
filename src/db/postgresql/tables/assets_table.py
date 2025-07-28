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