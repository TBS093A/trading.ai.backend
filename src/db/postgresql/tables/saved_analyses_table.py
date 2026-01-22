"""
Tabela zapisanych analiz użytkowników.

Zawiera zapisane widoki wykresów wraz z:
- Wybranym assetem i interwałem
- Stanem wykresu (scroll, zoom, widoczny zakres)
- Opcjami wyświetlania patternów (fibo lines, display options)
- Wybranymi patternami
- Ustawieniami indykatorów
- Globalnymi ustawieniami wyświetlania
"""

from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
import json

logger = logging.getLogger(__name__)


class SavedAnalysesTable(AbstractTable):
    """Klasa do zarządzania tabelą SavedAnalyses."""
    
    def create_table(self) -> str:
        """Tworzy tabelę saved_analyses z odpowiednią strukturą."""
        return """
        CREATE TABLE IF NOT EXISTS saved_analyses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            
            -- Asset and interval info
            asset_id INTEGER NOT NULL,
            asset_name VARCHAR(100),
            quote_name VARCHAR(50),
            exchange_id INTEGER,
            exchange_name VARCHAR(100),
            interval VARCHAR(10) NOT NULL,
            
            -- Chart view state (visible time range, scroll position)
            chart_visible_range JSONB,
            
            -- Selected pattern info
            selected_pattern_id INTEGER,
            expanded_pattern_id INTEGER,
            
            -- Pattern display options (per pattern settings)
            pattern_display_options JSONB DEFAULT '{}',
            
            -- Shared pattern data (for cross-interval line sharing)
            shared_pattern_data JSONB DEFAULT '{}',
            
            -- Global pattern display settings
            global_pattern_display JSONB DEFAULT '{}',
            
            -- Indicators visibility
            indicators JSONB DEFAULT '{}',
            
            -- Analysis display settings
            unselected_alpha REAL DEFAULT 0.15,
            auto_center_on_select BOOLEAN DEFAULT TRUE,
            
            -- Harmonic patterns snapshot (IDs of patterns at time of save)
            harmonic_pattern_ids JSONB DEFAULT '[]',
            
            -- Thumbnail or preview image (optional, base64)
            thumbnail TEXT,
            
            -- Metadata
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE INDEX IF NOT EXISTS idx_saved_analyses_user_id ON saved_analyses(user_id);
        CREATE INDEX IF NOT EXISTS idx_saved_analyses_asset_id ON saved_analyses(asset_id);
        CREATE INDEX IF NOT EXISTS idx_saved_analyses_created_at ON saved_analyses(created_at DESC);
        """
    
    async def create(
        self,
        user_id: int,
        name: str,
        asset_id: int,
        interval: str,
        description: str = None,
        asset_name: str = None,
        quote_name: str = None,
        exchange_id: int = None,
        exchange_name: str = None,
        chart_visible_range: Dict = None,
        selected_pattern_id: int = None,
        expanded_pattern_id: int = None,
        pattern_display_options: Dict = None,
        shared_pattern_data: Dict = None,
        global_pattern_display: Dict = None,
        indicators: Dict = None,
        unselected_alpha: float = 0.15,
        auto_center_on_select: bool = True,
        harmonic_pattern_ids: List[int] = None,
        thumbnail: str = None
    ) -> Optional[int]:
        """
        Tworzy nową zapisaną analizę.
        
        Args:
            user_id: ID użytkownika tworzącego analizę
            name: Nazwa zapisanej analizy
            asset_id: ID assetu
            interval: Interwał wykresu
            description: Opcjonalny opis
            asset_name: Nazwa assetu
            quote_name: Nazwa waluty kwotowanej
            exchange_id: ID giełdy
            exchange_name: Nazwa giełdy
            chart_visible_range: Widoczny zakres wykresu
            selected_pattern_id: ID wybranego patternu
            expanded_pattern_id: ID rozwiniętego patternu
            pattern_display_options: Opcje wyświetlania dla każdego patternu
            shared_pattern_data: Dane patternów dla cross-interval sharing
            global_pattern_display: Globalne ustawienia wyświetlania patternów
            indicators: Widoczność indykatorów
            unselected_alpha: Alpha dla niewybranych patternów
            auto_center_on_select: Auto-center przy wyborze
            harmonic_pattern_ids: Lista ID patternów harmonicznych
            thumbnail: Miniaturka jako base64
            
        Returns:
            Optional[int]: ID nowej analizy lub None w przypadku błędu
        """
        try:
            analysis_id = await self.fetch_val(
                """
                INSERT INTO saved_analyses (
                    user_id, name, description,
                    asset_id, asset_name, quote_name, exchange_id, exchange_name, interval,
                    chart_visible_range,
                    selected_pattern_id, expanded_pattern_id,
                    pattern_display_options, shared_pattern_data,
                    global_pattern_display, indicators,
                    unselected_alpha, auto_center_on_select,
                    harmonic_pattern_ids, thumbnail
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
                RETURNING id
                """,
                user_id, name, description,
                asset_id, asset_name, quote_name, exchange_id, exchange_name, interval,
                json.dumps(chart_visible_range) if chart_visible_range else None,
                selected_pattern_id, expanded_pattern_id,
                json.dumps(pattern_display_options or {}),
                json.dumps(shared_pattern_data or {}),
                json.dumps(global_pattern_display or {}),
                json.dumps(indicators or {}),
                unselected_alpha, auto_center_on_select,
                json.dumps(harmonic_pattern_ids or []),
                thumbnail
            )
            logger.info(f"Utworzono zapisaną analizę: {name} (ID: {analysis_id}) dla user_id: {user_id}")
            return analysis_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia zapisanej analizy: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera zapisaną analizę po ID."""
        result = await self.fetch_one(
            """
            SELECT * FROM saved_analyses WHERE id = $1
            """,
            record_id
        )
        if result:
            return self._deserialize_json_fields(result)
        return None
    
    async def get_by_user(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Pobiera zapisane analizy dla użytkownika.
        
        Args:
            user_id: ID użytkownika
            limit: Maksymalna liczba wyników
            offset: Offset dla paginacji
            
        Returns:
            List[Dict]: Lista zapisanych analiz
        """
        results = await self.fetch_all(
            """
            SELECT id, user_id, name, description,
                   asset_id, asset_name, quote_name, exchange_id, exchange_name, interval,
                   created_at, updated_at
            FROM saved_analyses 
            WHERE user_id = $1
            ORDER BY updated_at DESC
            LIMIT $2 OFFSET $3
            """,
            user_id, limit, offset
        )
        return results
    
    async def get_by_user_full(
        self,
        user_id: int,
        analysis_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Pobiera pełne dane zapisanej analizy dla użytkownika.
        
        Args:
            user_id: ID użytkownika (do weryfikacji własności)
            analysis_id: ID analizy
            
        Returns:
            Dict: Pełne dane analizy lub None jeśli nie znaleziono
        """
        result = await self.fetch_one(
            """
            SELECT * FROM saved_analyses 
            WHERE id = $1 AND user_id = $2
            """,
            analysis_id, user_id
        )
        if result:
            return self._deserialize_json_fields(result)
        return None
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje zapisaną analizę o podanym ID."""
        try:
            update_fields = []
            params = []
            param_counter = 1
            
            # Mapowanie pól do aktualizacji
            simple_fields = [
                'name', 'description', 'asset_id', 'asset_name', 
                'quote_name', 'exchange_id', 'exchange_name', 'interval',
                'selected_pattern_id', 'expanded_pattern_id',
                'unselected_alpha', 'auto_center_on_select', 'thumbnail'
            ]
            
            json_fields = [
                'chart_visible_range', 'pattern_display_options', 
                'shared_pattern_data', 'global_pattern_display',
                'indicators', 'harmonic_pattern_ids'
            ]
            
            for field in simple_fields:
                if field in kwargs:
                    update_fields.append(f"{field} = ${param_counter}")
                    params.append(kwargs[field])
                    param_counter += 1
            
            for field in json_fields:
                if field in kwargs:
                    update_fields.append(f"{field} = ${param_counter}")
                    params.append(json.dumps(kwargs[field]) if kwargs[field] is not None else None)
                    param_counter += 1
            
            if not update_fields:
                return False
            
            # Zawsze aktualizuj updated_at
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            
            params.append(record_id)
            query = f"UPDATE saved_analyses SET {', '.join(update_fields)} WHERE id = ${param_counter}"
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano zapisaną analizę z ID: {record_id}")
            return True
            
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji zapisanej analizy: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa zapisaną analizę o podanym ID."""
        try:
            await self.execute_query(
                "DELETE FROM saved_analyses WHERE id = $1",
                record_id
            )
            logger.info(f"Usunięto zapisaną analizę z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania zapisanej analizy: {e}", exc_info=True)
            return False
    
    async def delete_by_asset_id(self, asset_id: int) -> int:
        """
        Usuwa wszystkie zapisane analizy dla danego assetu.
        
        Args:
            asset_id: ID assetu
            
        Returns:
            int: Liczba usuniętych rekordów
        """
        try:
            # Policz ile rekordów będzie usuniętych
            count = await self.fetch_val(
                "SELECT COUNT(*) FROM saved_analyses WHERE asset_id = $1",
                asset_id
            )
            
            # Usuń wszystkie rekordy
            await self.execute_query(
                "DELETE FROM saved_analyses WHERE asset_id = $1",
                asset_id
            )
            
            logger.info(f"Usunięto {count} zapisanych analiz dla asset_id: {asset_id}")
            return count or 0
        except Exception as e:
            logger.error(f"Błąd podczas usuwania zapisanych analiz dla asset_id {asset_id}: {e}", exc_info=True)
            return 0
    
    async def delete_by_user(self, record_id: int, user_id: int) -> bool:
        """
        Usuwa zapisaną analizę tylko jeśli należy do użytkownika.
        
        Args:
            record_id: ID analizy do usunięcia
            user_id: ID użytkownika (do weryfikacji własności)
            
        Returns:
            bool: True jeśli usunięto, False w przeciwnym razie
        """
        try:
            result = await self.fetch_val(
                """
                DELETE FROM saved_analyses 
                WHERE id = $1 AND user_id = $2
                RETURNING id
                """,
                record_id, user_id
            )
            if result:
                logger.info(f"Usunięto zapisaną analizę z ID: {record_id} (user_id: {user_id})")
                return True
            else:
                logger.warning(f"Nie znaleziono analizy do usunięcia (ID: {record_id}, user_id: {user_id})")
                return False
        except Exception as e:
            logger.error(f"Błąd podczas usuwania zapisanej analizy: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie zapisane analizy z limitem i offsetem."""
        results = await self.fetch_all(
            """
            SELECT id, user_id, name, description,
                   asset_id, asset_name, quote_name, exchange_id, exchange_name, interval,
                   created_at, updated_at
            FROM saved_analyses 
            ORDER BY updated_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
        return results
    
    async def count_by_user(self, user_id: int) -> int:
        """Zwraca liczbę zapisanych analiz dla użytkownika."""
        result = await self.fetch_val(
            "SELECT COUNT(*) FROM saved_analyses WHERE user_id = $1",
            user_id
        )
        return result or 0
    
    def _deserialize_json_fields(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Deserializuje pola JSONB z rekordu."""
        result = dict(record)
        
        json_fields = [
            'chart_visible_range', 'pattern_display_options',
            'shared_pattern_data', 'global_pattern_display',
            'indicators', 'harmonic_pattern_ids'
        ]
        
        for field in json_fields:
            if field in result and result[field] is not None:
                if isinstance(result[field], str):
                    try:
                        result[field] = json.loads(result[field])
                    except json.JSONDecodeError:
                        logger.warning(f"Nie udało się zdekodować JSON dla pola {field}")
                        result[field] = {}
                # Jeśli już jest dict/list, zostaw jak jest (asyncpg automatycznie dekoduje JSONB)
        
        return result

