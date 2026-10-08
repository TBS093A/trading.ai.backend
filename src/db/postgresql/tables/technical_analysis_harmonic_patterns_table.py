from typing import Optional, Dict, Any, List, Sequence, Tuple
from .abstract_table import AbstractTable, CleanupRule
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

def convert_numpy_types(obj):
    """Konwertuje NumPy typy na standardowe typy Python dla serializacji JSON."""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    else:
        return obj

class TechnicalAnalysisHarmonicPatternsTable(AbstractTable):
    """Klasa do zarządzania tabelą TechnicalAnalysisHarmonicPatterns."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS technical_analysis_harmonic_patterns (
            id SERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            interval VARCHAR(10),
            x_point_timestamp BIGINT,
            a_point_timestamp BIGINT,
            b_point_timestamp BIGINT,
            c_point_timestamp BIGINT,
            d_point_timestamp BIGINT,
            ta_object_json JSONB NOT NULL,
            confluences_json JSONB,
            engine_version VARCHAR(32),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
    # Klucz formacji (migracja 4 - unikalny indeks): te same punkty na tym samym assecie i interwale
    # to jedna formacja. X (ABCD) i D (ABC) mogą być NULL - stąd COALESCE.
    POINTS_KEY = ("asset_id, interval, COALESCE(x_point_timestamp, -1), a_point_timestamp, "
                  "b_point_timestamp, c_point_timestamp, COALESCE(d_point_timestamp, -1)")

    @staticmethod
    def points_key(p: Dict[str, Any]) -> Tuple:
        nz = lambda v: -1 if v is None else int(v)
        return (int(p["asset_id"]), p["interval"], nz(p.get("x_point_timestamp")), int(p["a_point_timestamp"]),
                int(p["b_point_timestamp"]), int(p["c_point_timestamp"]), nz(p.get("d_point_timestamp")))

    def cleanup_rules(self) -> List[CleanupRule]:
        from ....harmonic_scan import params_hash

        # Tylko jawnie stara wersja silnika (NULL = zapis sprzed wersjonowania - zostaje) i tylko tam,
        # gdzie zakres przeskanowano już bieżącą wersją: gdyby formacja nadal wychodziła, upsert
        # podbiłby jej engine_version - skoro nie, silnik jej już nie znajduje.
        return [CleanupRule(
            name="harmonic_patterns.old_engine",
            table="technical_analysis_harmonic_patterns",
            description="formacje ze starej wersji silnika w zakresach przeskanowanych bieżącą wersją",
            where="""engine_version IS NOT NULL AND engine_version <> $1 AND EXISTS (
                SELECT 1 FROM technical_analysis_harmonic_scan_windows w
                WHERE w.asset_id = technical_analysis_harmonic_patterns.asset_id
                  AND w.interval = technical_analysis_harmonic_patterns.interval
                  AND w.params_hash = $1
                  AND w.start_time <= COALESCE(x_point_timestamp, a_point_timestamp)
                  AND w.end_time >= COALESCE(d_point_timestamp, c_point_timestamp))""",
            args=(params_hash(),),
        )]

    async def get_existing_by_points(self, patterns: Sequence[Dict[str, Any]]) -> Dict[Tuple, Dict[str, Any]]:
        """Istniejące wiersze dla kluczy punktów z `patterns` - jedno zapytanie na całą paczkę."""
        keys = list({self.points_key(p) for p in patterns})
        if not keys:
            return {}
        cols = list(zip(*keys))
        rows = await self.fetch_all(
            f"""SELECT t.id, t.asset_id, t.interval, t.x_point_timestamp, t.a_point_timestamp,
                       t.b_point_timestamp, t.c_point_timestamp, t.d_point_timestamp,
                       t.ta_object_json, t.engine_version
            FROM technical_analysis_harmonic_patterns t
            JOIN unnest($1::int[], $2::text[], $3::bigint[], $4::bigint[], $5::bigint[], $6::bigint[], $7::bigint[])
                 AS k(asset_id, interval, x, a, b, c, d)
              ON ({self.POINTS_KEY}) = (k.asset_id, k.interval, k.x, k.a, k.b, k.c, k.d)""",  # nosemgrep: stała
            *[list(c) for c in cols],
        )
        out = {}
        for r in rows:
            if isinstance(r.get("ta_object_json"), str):
                r["ta_object_json"] = json.loads(r["ta_object_json"])
            out[self.points_key(r)] = r
        return out

    async def upsert_many(self, patterns: Sequence[Dict[str, Any]], engine_version: str) -> int:
        """Wstawia nowe / nadpisuje istniejące formacje (klucz punktów). Pusty confluences_json nie
        kasuje zapisanych konfluencji (post-processing dopisuje je osobno)."""
        if not patterns:
            return 0
        query = f"""
        INSERT INTO technical_analysis_harmonic_patterns
            (asset_id, interval, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp,
             d_point_timestamp, ta_object_json, confluences_json, engine_version, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
        ON CONFLICT ({self.POINTS_KEY}) DO UPDATE SET
            ta_object_json = EXCLUDED.ta_object_json,
            confluences_json = COALESCE(EXCLUDED.confluences_json, technical_analysis_harmonic_patterns.confluences_json),
            engine_version = EXCLUDED.engine_version,
            updated_at = NOW()
        """  # nosemgrep: POINTS_KEY to stała, wartości idą parametrami
        args = []
        for p in patterns:
            conf = convert_numpy_types(p.get("confluences_json")) if p.get("confluences_json") else None
            args.append((
                p["asset_id"], p["interval"], p.get("x_point_timestamp"), p["a_point_timestamp"],
                p["b_point_timestamp"], p["c_point_timestamp"], p.get("d_point_timestamp"),
                json.dumps(convert_numpy_types(p["ta_object_json"])), json.dumps(conf) if conf else None,
                engine_version,
            ))
        async with self.pool.acquire() as conn:
            await conn.executemany(query, args)  # nosemgrep: query z POINTS_KEY (stała), wartości parametrami
        return len(args)
    
    async def create(self, asset_id: int, ta_object_json: Dict[str, Any], 
                    interval: str = None, x_point_timestamp: int = None, a_point_timestamp: int = None, 
                    b_point_timestamp: int = None, c_point_timestamp: int = None, 
                    d_point_timestamp: int = None, confluences_json: Dict[str, Any] = None) -> Optional[int]:
        """Tworzy nową analizę techniczną i zwraca jej ID."""
        try:
            # Konwertuj NumPy typy przed serializacją JSON
            converted_ta_object_json = convert_numpy_types(ta_object_json)
            converted_confluences_json = convert_numpy_types(confluences_json) if confluences_json else None
            
            analysis_id = await self.fetch_val(
                """INSERT INTO technical_analysis_harmonic_patterns 
                (asset_id, interval, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp, ta_object_json, confluences_json) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id""",
                asset_id, interval, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp, json.dumps(converted_ta_object_json), json.dumps(converted_confluences_json) if converted_confluences_json else None
            )
            logger.info(f"Utworzono analizę techniczną z ID: {analysis_id}")
            return analysis_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia analizy technicznej: {e}", exc_info=True)
            return None
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera analizę techniczną po ID."""
        result = await self.fetch_one("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.id = $1
        """, record_id)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return result
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje analizę techniczną o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            if 'asset_id' in kwargs:
                update_fields.append(f"asset_id = ${param_count}")
                values.append(kwargs['asset_id'])
                param_count += 1
            
            if 'interval' in kwargs:
                update_fields.append(f"interval = ${param_count}")
                values.append(kwargs['interval'])
                param_count += 1
            
            if 'x_point_timestamp' in kwargs:
                update_fields.append(f"x_point_timestamp = ${param_count}")
                values.append(kwargs['x_point_timestamp'])
                param_count += 1
            
            if 'a_point_timestamp' in kwargs:
                update_fields.append(f"a_point_timestamp = ${param_count}")
                values.append(kwargs['a_point_timestamp'])
                param_count += 1
            
            if 'b_point_timestamp' in kwargs:
                update_fields.append(f"b_point_timestamp = ${param_count}")
                values.append(kwargs['b_point_timestamp'])
                param_count += 1
            
            if 'c_point_timestamp' in kwargs:
                update_fields.append(f"c_point_timestamp = ${param_count}")
                values.append(kwargs['c_point_timestamp'])
                param_count += 1
            
            if 'd_point_timestamp' in kwargs:
                update_fields.append(f"d_point_timestamp = ${param_count}")
                values.append(kwargs['d_point_timestamp'])
                param_count += 1
            
            if 'ta_object_json' in kwargs:
                update_fields.append(f"ta_object_json = ${param_count}")
                converted_ta_object_json = convert_numpy_types(kwargs['ta_object_json'])
                values.append(json.dumps(converted_ta_object_json))
                param_count += 1
            
            if 'confluences_json' in kwargs:
                update_fields.append(f"confluences_json = ${param_count}")
                converted_confluences = convert_numpy_types(kwargs['confluences_json']) if kwargs['confluences_json'] else None
                values.append(json.dumps(converted_confluences) if converted_confluences else None)
                param_count += 1
            
            if not update_fields:
                return False
            
            values.append(record_id)
            query = f"UPDATE technical_analysis_harmonic_patterns SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano analizę techniczną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji analizy technicznej: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa analizę techniczną o podanym ID."""
        try:
            await self.execute_query("DELETE FROM technical_analysis_harmonic_patterns WHERE id = $1", record_id)
            logger.info(f"Usunięto analizę techniczną z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania analizy technicznej: {e}", exc_info=True)
            return False
    
    async def delete_by_asset_id(self, asset_id: int) -> int:
        """Usuwa wszystkie analizy techniczne dla danego assetu.
        
        Args:
            asset_id: ID assetu
            
        Returns:
            Liczba usuniętych rekordów
        """
        try:
            # Najpierw policz ile rekordów będzie usuniętych
            count = await self.fetch_val(
                "SELECT COUNT(*) FROM technical_analysis_harmonic_patterns WHERE asset_id = $1",
                asset_id
            )
            
            # Usuń wszystkie rekordy
            await self.execute_query(
                "DELETE FROM technical_analysis_harmonic_patterns WHERE asset_id = $1",
                asset_id
            )
            
            logger.info(f"Usunięto {count} analiz technicznych dla asset_id: {asset_id}")
            return count or 0
        except Exception as e:
            logger.error(f"Błąd podczas usuwania analiz technicznych dla asset_id {asset_id}: {e}", exc_info=True)
            return 0
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie analizy techniczne z limitem i offsetem."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        ORDER BY ta.id DESC LIMIT $1 OFFSET $2
        """, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne dla asset."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_by_asset_id_and_interval(self, asset_id: int, interval: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne dla asset i interwału."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 AND ta.interval = $2
        ORDER BY ta.id DESC LIMIT $3 OFFSET $4
        """, asset_id, interval, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_by_timestamp_range(self, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne z określonego zakresu czasowego (używa x_point_timestamp)."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.x_point_timestamp >= $1 AND ta.x_point_timestamp <= $2
        ORDER BY ta.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_latest_by_asset_id(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera najnowszą analizę techniczną dla asset."""
        result = await self.fetch_one("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1
        ORDER BY ta.id DESC
        LIMIT 1
        """, asset_id)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return result
    
    async def search_by_json_pattern(self, pattern: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Wyszukuje analizy techniczne po wzorcu w JSON."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.ta_object_json::text ILIKE $1
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, f"%{pattern}%", limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_by_point_timestamp(self, point_type: str, timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne według konkretnego punktu czasowego."""
        if point_type not in ['x', 'a', 'b', 'c', 'd']:
            raise ValueError("point_type musi być jednym z: 'x', 'a', 'b', 'c', 'd'")
        
        column_name = f"{point_type}_point_timestamp"
        results = await self.fetch_all(f"""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.{column_name} = $1
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, timestamp, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_by_point_timestamp_range(self, point_type: str, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne według zakresu czasowego konkretnego punktu."""
        if point_type not in ['x', 'a', 'b', 'c', 'd']:
            raise ValueError("point_type musi być jednym z: 'x', 'a', 'b', 'c', 'd'")
        
        column_name = f"{point_type}_point_timestamp"
        results = await self.fetch_all(f"""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.{column_name} >= $1 AND ta.{column_name} <= $2
        ORDER BY ta.id DESC LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results

    async def get_complete_patterns(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera kompletne wzorce harmoniczne (wszystkie punkty wypełnione)."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 
        AND ta.x_point_timestamp IS NOT NULL 
        AND ta.a_point_timestamp IS NOT NULL 
        AND ta.b_point_timestamp IS NOT NULL 
        AND ta.c_point_timestamp IS NOT NULL 
        AND ta.d_point_timestamp IS NOT NULL
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results
    
    async def get_incomplete_patterns(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera niekompletne wzorce harmoniczne (przynajmniej jeden punkt jest NULL)."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 
        AND (ta.x_point_timestamp IS NULL 
        OR ta.a_point_timestamp IS NULL 
        OR ta.b_point_timestamp IS NULL 
        OR ta.c_point_timestamp IS NULL 
        OR ta.d_point_timestamp IS NULL)
        ORDER BY ta.id DESC LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results 

    async def get_by_timestamp_range_and_asset_id(self, start_timestamp: int, end_timestamp: int, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne z określonego zakresu czasowego i asset."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.x_point_timestamp >= $1 AND ta.x_point_timestamp <= $2 AND ta.asset_id = $3
        ORDER BY ta.id DESC LIMIT $4 OFFSET $5
        """, start_timestamp, end_timestamp, asset_id, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results 
    
    async def get_by_timestamp_range_and_asset_id_and_interval(self, start_timestamp: int, end_timestamp: int, asset_id: int, interval: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera analizy techniczne z określonego zakresu czasowego, asset i interwału."""
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.x_point_timestamp >= $1 AND ta.x_point_timestamp <= $2 AND ta.asset_id = $3 AND ta.interval = $4
        ORDER BY ta.id DESC LIMIT $5 OFFSET $6
        """, start_timestamp, end_timestamp, asset_id, interval, limit, offset)
        
        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return results

    async def get_within_range(self, asset_id: int, interval: str, start_timestamp: int, end_timestamp: int,
                               limit: int = 2000) -> List[Dict[str, Any]]:
        """Formacje, których WSZYSTKIE punkty leżą w [start_timestamp, end_timestamp] (skan zakresu).

        Pierwszy punkt to X (albo A dla ABCD), ostatni D (albo C dla ABC).
        """
        results = await self.fetch_all("""
        SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp,
               ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
               a.asset, a.quote
        FROM technical_analysis_harmonic_patterns ta
        JOIN assets a ON ta.asset_id = a.id
        WHERE ta.asset_id = $1 AND ta.interval = $2
          AND COALESCE(ta.x_point_timestamp, ta.a_point_timestamp) >= $3
          AND COALESCE(ta.d_point_timestamp, ta.c_point_timestamp) <= $4
        ORDER BY COALESCE(ta.d_point_timestamp, ta.c_point_timestamp) DESC, ta.id DESC
        LIMIT $5
        """, asset_id, interval, start_timestamp, end_timestamp, limit)

        for result in results:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])

        return results

    async def check_pattern_exists(self, asset_id: int, x_point_timestamp: int, a_point_timestamp: int, 
                                 b_point_timestamp: int, c_point_timestamp: int, d_point_timestamp: int,
                                 interval: str = None) -> bool:
        """
        Sprawdza czy wzorzec o podanych timestampach już istnieje dla danego asset i interwału.
        
        Obsługuje NULL dla x_point_timestamp (ABCD/ABC) i d_point_timestamp (ABC)
        używając IS NOT DISTINCT FROM.
        """
        if interval:
            result = await self.fetch_one("""
            SELECT COUNT(*) as count
            FROM technical_analysis_harmonic_patterns 
            WHERE asset_id = $1 
            AND x_point_timestamp IS NOT DISTINCT FROM $2 
            AND a_point_timestamp = $3 
            AND b_point_timestamp = $4 
            AND c_point_timestamp = $5 
            AND d_point_timestamp IS NOT DISTINCT FROM $6
            AND interval = $7
            """, asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp, interval)
        else:
            result = await self.fetch_one("""
            SELECT COUNT(*) as count
            FROM technical_analysis_harmonic_patterns 
            WHERE asset_id = $1 
            AND x_point_timestamp IS NOT DISTINCT FROM $2 
            AND a_point_timestamp = $3 
            AND b_point_timestamp = $4 
            AND c_point_timestamp = $5 
            AND d_point_timestamp IS NOT DISTINCT FROM $6
            """, asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp)
        
        return result['count'] > 0 if result else False
    
    async def get_by_point_timestamps(self, asset_id: int, x_point_timestamp: int, a_point_timestamp: int, 
                                     b_point_timestamp: int, c_point_timestamp: int, d_point_timestamp: int,
                                     interval: str = None) -> Optional[Dict[str, Any]]:
        """
        Pobiera wzorzec o podanych timestampach dla danego asset i opcjonalnie interwału.
        
        Obsługuje NULL dla x_point_timestamp (ABCD/ABC) i d_point_timestamp (ABC)
        używając IS NOT DISTINCT FROM.
        """
        if interval:
            result = await self.fetch_one("""
            SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
                   ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
                   a.asset, a.quote
            FROM technical_analysis_harmonic_patterns ta
            JOIN assets a ON ta.asset_id = a.id
            WHERE ta.asset_id = $1 
            AND ta.x_point_timestamp IS NOT DISTINCT FROM $2 
            AND ta.a_point_timestamp = $3 
            AND ta.b_point_timestamp = $4 
            AND ta.c_point_timestamp = $5 
            AND ta.d_point_timestamp IS NOT DISTINCT FROM $6
            AND ta.interval = $7
            LIMIT 1
            """, asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp, interval)
        else:
            result = await self.fetch_one("""
            SELECT ta.id, ta.asset_id, ta.interval, ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp, 
                   ta.c_point_timestamp, ta.d_point_timestamp, ta.ta_object_json, ta.confluences_json,
                   a.asset, a.quote
            FROM technical_analysis_harmonic_patterns ta
            JOIN assets a ON ta.asset_id = a.id
            WHERE ta.asset_id = $1 
            AND ta.x_point_timestamp IS NOT DISTINCT FROM $2 
            AND ta.a_point_timestamp = $3 
            AND ta.b_point_timestamp = $4 
            AND ta.c_point_timestamp = $5 
            AND ta.d_point_timestamp IS NOT DISTINCT FROM $6
            LIMIT 1
            """, asset_id, x_point_timestamp, a_point_timestamp, b_point_timestamp, c_point_timestamp, d_point_timestamp)
        
        if result:
            result['ta_object_json'] = json.loads(result['ta_object_json'])
            if result.get('confluences_json'):
                result['confluences_json'] = json.loads(result['confluences_json'])
        
        return result
    

    async def count_all(self) -> int:
        """Zlicza wszystkie analizy techniczne wzorców harmonicznych."""
        result = await self.fetch_val("""
        SELECT COUNT(*) FROM technical_analysis_harmonic_patterns
        """)
        
        return result or 0
    
    async def count_by_asset(self, asset_id: int) -> int:
        """Zlicza analizy techniczne wzorców harmonicznych dla konkretnego assetu."""
        result = await self.fetch_val("""
        SELECT COUNT(*) FROM technical_analysis_harmonic_patterns WHERE asset_id = $1
        """, asset_id)
        
        return result or 0
    
    async def find_duplicates(self, asset_id: int = None) -> List[Dict[str, Any]]:
        """
        Znajduje duplikaty wzorców harmonicznych.
        
        Duplikat jest definiowany jako wzorzec o tych samych wartościach:
        - asset_id
        - interval
        - x_point_timestamp (może być NULL dla ABCD/ABC)
        - a_point_timestamp
        - b_point_timestamp
        - c_point_timestamp
        - d_point_timestamp (może być NULL dla ABC)
        
        Używa IS NOT DISTINCT FROM aby poprawnie obsługiwać NULL (NULL = NULL -> TRUE)
        
        Args:
            asset_id: Opcjonalnie ID assetu do sprawdzenia (None = wszystkie assety)
            
        Returns:
            Lista duplikatów z ich ID-ami (zachowuje najstarszy rekord, zwraca nowsze do usunięcia)
        """
        # IS NOT DISTINCT FROM traktuje NULL jako równe sobie (NULL IS NOT DISTINCT FROM NULL = TRUE)
        # W przeciwieństwie do = gdzie NULL = NULL daje NULL (falsy)
        base_query = """
        WITH duplicates AS (
            SELECT 
                asset_id,
                interval,
                COALESCE(x_point_timestamp, -1) as x_ts,
                a_point_timestamp,
                b_point_timestamp,
                c_point_timestamp,
                COALESCE(d_point_timestamp, -1) as d_ts,
                MIN(id) as keep_id,
                COUNT(*) as duplicate_count
            FROM technical_analysis_harmonic_patterns
            {where_clause}
            GROUP BY asset_id, interval, COALESCE(x_point_timestamp, -1), a_point_timestamp, 
                     b_point_timestamp, c_point_timestamp, COALESCE(d_point_timestamp, -1)
            HAVING COUNT(*) > 1
        )
        SELECT ta.id, ta.asset_id, ta.interval, 
               ta.x_point_timestamp, ta.a_point_timestamp, ta.b_point_timestamp,
               ta.c_point_timestamp, ta.d_point_timestamp,
               d.keep_id, d.duplicate_count
        FROM technical_analysis_harmonic_patterns ta
        JOIN duplicates d ON 
            ta.asset_id = d.asset_id AND
            ta.interval IS NOT DISTINCT FROM d.interval AND
            COALESCE(ta.x_point_timestamp, -1) = d.x_ts AND
            ta.a_point_timestamp = d.a_point_timestamp AND
            ta.b_point_timestamp = d.b_point_timestamp AND
            ta.c_point_timestamp = d.c_point_timestamp AND
            COALESCE(ta.d_point_timestamp, -1) = d.d_ts
        WHERE ta.id != d.keep_id
        ORDER BY ta.asset_id, ta.interval, ta.id
        """
        
        if asset_id is not None:
            query = base_query.format(where_clause=f"WHERE asset_id = $1")
            results = await self.fetch_all(query, asset_id)
        else:
            query = base_query.format(where_clause="")
            results = await self.fetch_all(query)
        
        return results
    
    async def remove_duplicates(self, asset_id: int = None) -> int:
        """
        Usuwa duplikaty wzorców harmonicznych, zachowując najstarsze rekordy.
        
        Args:
            asset_id: Opcjonalnie ID assetu (None = wszystkie assety)
            
        Returns:
            Liczba usuniętych duplikatów
        """
        try:
            # Znajdź duplikaty
            duplicates = await self.find_duplicates(asset_id)
            
            if not duplicates:
                logger.info(f"Brak duplikatów do usunięcia" + (f" dla asset_id={asset_id}" if asset_id else ""))
                return 0
            
            # Pobierz ID-ki do usunięcia
            ids_to_delete = [d['id'] for d in duplicates]
            
            # Usuń duplikaty
            if ids_to_delete:
                placeholders = ', '.join([f'${i+1}' for i in range(len(ids_to_delete))])
                await self.execute_query(
                    f"DELETE FROM technical_analysis_harmonic_patterns WHERE id IN ({placeholders})",
                    *ids_to_delete
                )
                
                logger.info(f"Usunięto {len(ids_to_delete)} duplikatów wzorców harmonicznych" + 
                           (f" dla asset_id={asset_id}" if asset_id else ""))
            
            return len(ids_to_delete)
            
        except Exception as e:
            logger.error(f"Błąd podczas usuwania duplikatów: {e}", exc_info=True)
            return 0
    
    async def count_duplicates(self, asset_id: int = None) -> int:
        """
        Zlicza duplikaty wzorców harmonicznych.
        
        Args:
            asset_id: Opcjonalnie ID assetu (None = wszystkie assety)
            
        Returns:
            Liczba duplikatów
        """
        duplicates = await self.find_duplicates(asset_id)
        return len(duplicates)

    async def get_pattern_counts_by_asset_id(self, asset_id: int) -> List[Dict[str, Any]]:
        """Returns bullish/bearish pattern counts per interval for an asset."""
        return await self.fetch_all("""
            SELECT
                interval,
                COUNT(*) FILTER (WHERE ta_object_json::jsonb->>'is_bullish' = 'true')  AS bullish,
                COUNT(*) FILTER (WHERE ta_object_json::jsonb->>'is_bullish' = 'false') AS bearish
            FROM technical_analysis_harmonic_patterns
            WHERE asset_id = $1
            GROUP BY interval
        """, asset_id)