from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AssetsTable(AbstractTable):
    """Klasa do zarządzania tabelą Assets."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS assets (
            id SERIAL PRIMARY KEY,
            asset TEXT NOT NULL,
            quote TEXT NOT NULL,
            full_name TEXT,
            UNIQUE(asset, quote)
        );
        """
    
    async def create(self, asset: str, quote: str, full_name: Optional[str] = None) -> Optional[int]:
        """Tworzy nowy asset i zwraca jego ID."""
        try:
            asset_id = await self.fetch_val(
                "INSERT INTO assets (asset, quote, full_name) VALUES ($1, $2, $3) RETURNING id",
                asset, quote, full_name
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
            assets: Lista słowników z kluczami 'asset', 'quote' i opcjonalnym 'full_name'
            
        Returns:
            Dict[str, int]: Słownik mapujący asset na jego ID
        """
        if not assets:
            return {}
        
        try:
            values_list = []
            params = []
            param_counter = 1
            
            for item in assets:
                values_list.append(
                    f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2})"
                )
                params.extend([
                    item['asset'],
                    item['quote'],
                    item.get('full_name'),
                ])
                param_counter += 3
            
            query = f"""
                INSERT INTO assets (asset, quote, full_name) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (asset, quote) DO UPDATE SET
                    full_name = COALESCE(EXCLUDED.full_name, assets.full_name)
                RETURNING id, asset, quote
            """
            
            results = await self.fetch_all(query, *params)
            
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
            "SELECT id, asset, quote, full_name FROM assets WHERE id = $1",
            record_id
        )
    
    async def get_by_asset(self, asset: str) -> Optional[Dict[str, Any]]:
        """Pobiera pierwszy asset po nazwie asset (bez względu na quote)."""
        return await self.fetch_one(
            "SELECT id, asset, quote, full_name FROM assets WHERE asset = $1 ORDER BY id LIMIT 1",
            asset
        )
    
    async def get_by_asset_quote(self, asset: str, quote: str) -> Optional[Dict[str, Any]]:
        """Pobiera asset po asset i quote."""
        return await self.fetch_one(
            "SELECT id, asset, quote, full_name FROM assets WHERE asset = $1 AND quote = $2",
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
            "SELECT id, asset, quote, full_name FROM assets ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def search_by_asset(self, asset: str) -> List[Dict[str, Any]]:
        """Wyszukuje assety po nazwie asset lub full_name."""
        return await self.fetch_all(
            "SELECT id, asset, quote, full_name FROM assets "
            "WHERE asset ILIKE $1 OR full_name ILIKE $1 ORDER BY asset",
            f"%{asset}%"
        )
    
    async def search_by_quote(self, quote: str) -> List[Dict[str, Any]]:
        """Wyszukuje assety po nazwie quote."""
        return await self.fetch_all(
            "SELECT id, asset, quote, full_name FROM assets WHERE quote ILIKE $1 ORDER BY quote",
            f"%{quote}%"
        )
    
    async def get_assets_with_old_harmonic_patterns(self, time_delta: timedelta, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera assety które mają analizy techniczne harmoniczne starsze niż podany interwał czasowy,
        ale NIE mają młodszych niż podany interwał.
        
        Args:
            time_delta: Interwał czasowy (np. timedelta(days=365))
            limit: Maksymalna liczba wyników
            offset: Przesunięcie dla paginacji
            
        Returns:
            List[Dict[str, Any]]: Lista assetów z analizami starszymi niż podany interwał, ale bez młodszych
        """
        try:
            # Oblicz timestamp dla granicy czasowej
            current_time = datetime.now()
            cutoff_timestamp = int((current_time - time_delta).timestamp() * 1000)  # Konwersja na milisekundy
            
            results = await self.fetch_all("""
                SELECT DISTINCT a.id, a.asset, a.quote
                FROM assets a
                JOIN technical_analysis_harmonic_patterns ta ON a.id = ta.asset_id
                WHERE ta.x_point_timestamp < $1
                AND a.id NOT IN (
                    SELECT DISTINCT asset_id 
                    FROM technical_analysis_harmonic_patterns 
                    WHERE x_point_timestamp >= $1
                )
                ORDER BY a.asset, a.quote
                LIMIT $2 OFFSET $3
            """, cutoff_timestamp, limit, offset)
            
            logger.info(f"Znaleziono {len(results)} assetów z analizami starszymi niż {time_delta} (bez młodszych)")
            return results
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania assetów ze starymi analizami: {e}", exc_info=True)
            return []
    
    async def get_assets_with_recent_harmonic_patterns(self, time_delta: timedelta, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera assety które mają analizy techniczne harmoniczne młodsze niż podany interwał czasowy.
        
        Args:
            time_delta: Interwał czasowy (np. timedelta(days=365))
            limit: Maksymalna liczba wyników
            offset: Przesunięcie dla paginacji
            
        Returns:
            List[Dict[str, Any]]: Lista assetów z analizami młodszymi niż podany interwał
        """
        try:
            # Oblicz timestamp dla granicy czasowej
            current_time = datetime.now()
            cutoff_timestamp = int((current_time - time_delta).timestamp() * 1000)  # Konwersja na milisekundy
            
            results = await self.fetch_all("""
                SELECT DISTINCT a.id, a.asset, a.quote
                FROM assets a
                JOIN technical_analysis_harmonic_patterns ta ON a.id = ta.asset_id
                WHERE ta.x_point_timestamp >= $1
                ORDER BY a.asset, a.quote
                LIMIT $2 OFFSET $3
            """, cutoff_timestamp, limit, offset)
            
            logger.info(f"Znaleziono {len(results)} assetów z analizami młodszymi niż {time_delta}")
            return results
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania assetów z nowymi analizami: {e}", exc_info=True)
            return []
    
    async def get_assets_without_harmonic_patterns(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera wszystkie assety które nie mają żadnych analiz technicznych harmonic patterns.
        
        Args:
            limit: Maksymalna liczba wyników
            offset: Przesunięcie dla paginacji
            
        Returns:
            List[Dict[str, Any]]: Lista assetów bez analiz technicznych harmonic patterns
        """
        try:
            results = await self.fetch_all("""
                SELECT a.id, a.asset, a.quote
                FROM assets a
                LEFT JOIN technical_analysis_harmonic_patterns ta ON a.id = ta.asset_id
                WHERE ta.asset_id IS NULL
                ORDER BY a.asset, a.quote
                LIMIT $1 OFFSET $2
            """, limit, offset)
            
            logger.info(f"Znaleziono {len(results)} assetów bez analiz technicznych harmonic patterns")
            return results
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania assetów bez analiz: {e}", exc_info=True)
            return []
    
    async def get_assets_with_unprocessed_chart_images_by_interval(self, interval: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Pobiera assety które mają chart images nieprzypisane do żadnej analizy technicznej dla konkretnego interwału.
        
        Args:
            interval: Interwał czasowy (np. '4h', '1d')
            limit: Maksymalna liczba wyników
            offset: Przesunięcie dla paginacji
            
        Returns:
            List[Dict[str, Any]]: Lista assetów z chart images bez interpretacji dla danego interwału
        """
        try:
            results = await self.fetch_all("""
                SELECT DISTINCT a.id, a.asset, a.quote
                FROM assets a
                JOIN technical_analysis_harmonic_patterns tahp ON a.id = tahp.asset_id
                JOIN chart_images_harmonic_patterns cihp ON tahp.id = cihp.harmonic_pattern_id
                JOIN chart_images ci ON cihp.chart_image_id = ci.id
                LEFT JOIN technical_analysis_interpretation_chart_images taici ON ci.id = taici.chart_image_id
                WHERE taici.chart_image_id IS NULL 
                      AND ci.interval = $1
                ORDER BY a.asset, a.quote
                LIMIT $2 OFFSET $3
            """, interval, limit, offset)
            
            logger.info(f"Znaleziono {len(results)} assetów z unprocessed chart images dla interval={interval}")
            return results
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania assetów z unprocessed chart images dla interval={interval}: {e}", exc_info=True)
            return []
    
    async def count_all(self) -> int:
        """Zlicza wszystkie assety."""
        result = await self.fetch_val("SELECT COUNT(*) FROM assets")
        return result or 0
    
    async def get_assets_with_harmonic_patterns(
        self, 
        exchange_id: Optional[int] = None, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Pobiera assety które mają analizy techniczne harmonic patterns.
        Zwraca również informacje o ostatnim patternie (timestamp z punktu D) i liczbę patternów.
        
        Args:
            exchange_id: Opcjonalne filtrowanie po ID giełdy
            limit: Maksymalna liczba wyników
            offset: Przesunięcie dla paginacji
            
        Returns:
            List[Dict[str, Any]]: Lista assetów z patternami, zawierająca:
                - id, asset, quote
                - latest_pattern_timestamp (z punktu D)
                - patterns_count
        """
        try:
            if exchange_id is not None:
                # Z filtrem po giełdzie
                results = await self.fetch_all("""
                    SELECT 
                        a.id,
                        a.asset,
                        a.quote,
                        MAX(hp.d_point_timestamp) as latest_pattern_timestamp,
                        COUNT(hp.id) as patterns_count
                    FROM assets a
                    INNER JOIN technical_analysis_harmonic_patterns hp ON a.id = hp.asset_id
                    INNER JOIN asset_exchanges ae ON a.id = ae.asset_id
                    WHERE ae.exchange_id = $1
                    GROUP BY a.id, a.asset, a.quote
                    ORDER BY MAX(hp.d_point_timestamp) DESC
                    LIMIT $2 OFFSET $3
                """, exchange_id, limit, offset)
            else:
                # Bez filtra po giełdzie
                results = await self.fetch_all("""
                    SELECT 
                        a.id,
                        a.asset,
                        a.quote,
                        MAX(hp.d_point_timestamp) as latest_pattern_timestamp,
                        COUNT(hp.id) as patterns_count
                    FROM assets a
                    INNER JOIN technical_analysis_harmonic_patterns hp ON a.id = hp.asset_id
                    GROUP BY a.id, a.asset, a.quote
                    ORDER BY MAX(hp.d_point_timestamp) DESC
                    LIMIT $1 OFFSET $2
                """, limit, offset)
            
            logger.info(f"Znaleziono {len(results)} assetów z harmonic patterns" + 
                       (f" dla exchange_id={exchange_id}" if exchange_id else ""))
            return results
            
        except Exception as e:
            logger.error(f"Błąd podczas pobierania assetów z harmonic patterns: {e}", exc_info=True)
            return []