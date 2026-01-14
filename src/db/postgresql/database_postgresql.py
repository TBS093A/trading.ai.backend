import asyncpg
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
from .database_postgresql_factory import DatabasePostgreSQLFactory

logger = logging.getLogger(__name__)

class DatabasePostgreSQL:
    """Klasa do obsługi połączenia z bazą danych PostgreSQL."""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.pool = None
        self.factory = None
    
    async def init_db(self):
        """Inicjalizuje pulę połączeń i tworzy wszystkie tabele, jeśli nie istnieją."""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(self.database_url)
                logger.info("Utworzono pulę połączeń z bazą danych.")
                
                # Inicjalizuj fabrykę
                self.factory = DatabasePostgreSQLFactory(self.pool)
                
                # Utwórz wszystkie tabele
                await self._create_all_tables()
                logger.info("Sprawdzono/utworzono wszystkie tabele.")
            except Exception as e:
                logger.error(f"Błąd podczas inicjalizacji puli połączeń z bazą danych: {e}", exc_info=True)
                self.pool = None
                self.factory = None
                raise
    
    async def _create_all_tables(self):
        """Tworzy wszystkie tabele używając fabryki."""
        if self.factory is None:
            raise RuntimeError("Fabryka nie została zainicjalizowana")
        
        async with self.pool.acquire() as connection:
            # Pobierz wszystkie zapytania CREATE TABLE
            create_queries = self.factory.get_create_table_queries()
            
            # Wykonaj zapytania w odpowiedniej kolejności (z uwzględnieniem zależności)
            table_order = [
                'system_sync_job',  # Musi być przed cron_system_sync_job
                'cron_system_sync_job',  # Zależy od system_sync_job
                'users',  # Musi być przed user_sessions
                'user_sessions',  # Zależy od users
                'assets',
                'exchanges',
                'asset_exchanges',
                'technical_analysis_harmonic_patterns',
            ]
            
            for table_name in table_order:
                if table_name in create_queries:
                    # Podziel zapytania na poszczególne polecenia SQL (oddzielone przez ;)
                    create_query = create_queries[table_name]
                    sql_statements = [stmt.strip() for stmt in create_query.split(';') if stmt.strip()]
                    
                    for sql_statement in sql_statements:
                        try:
                            await connection.execute(sql_statement)
                        except Exception as e:
                            logger.error(f"Błąd podczas wykonywania SQL dla tabeli {table_name}: {sql_statement[:100]}...")
                            logger.error(f"Błąd: {e}")
                            # Kontynuuj dla pozostałych poleceń
                    
                    logger.info(f"Sprawdzono/utworzono tabelę: {table_name}")
            
            # Inicjalizuj domyślne dane po utworzeniu wszystkich tabel
            await self._seed_initial_data()
    
    async def _seed_initial_data(self):
        """Inicjalizuje domyślne dane we wszystkich tabelach używając abstrakcyjnej metody seed_default_records."""
        try:
            logger.info("=== ROZPOCZĘCIE SEEDOWANIA DOMYŚLNYCH DANYCH ===")
            
            # Pobierz wszystkie tabele z factory
            all_tables = self.factory.get_all_tables()
            seed_results = []
            
            # Iteruj przez wszystkie tabele i wywołaj seed_default_records
            for table_name, table_instance in all_tables.items():
                try:
                    logger.info(f"Seedowanie tabeli: {table_name}")
                    result = await table_instance.seed_default_records()
                    seed_results.append(result)
                    
                    if result['seeded']:
                        logger.info(f"✅ {table_name}: {result['message']}")
                    else:
                        logger.info(f"ℹ️ {table_name}: {result['message']}")
                        
                except Exception as e:
                    logger.error(f"❌ Błąd podczas seedowania tabeli {table_name}: {e}")
                    seed_results.append({
                        'table_name': table_name,
                        'seeded': False,
                        'created_count': 0,
                        'total_count': 0,
                        'message': f'Error: {str(e)}'
                    })
            
            # Wyświetl tabelkę z wynikami seedowania
            self._display_seeding_results_table(seed_results)
            
            # Wyświetl zawartość tabel które zostały zaseedowane
            await self._display_seeded_tables_content(seed_results, all_tables)
            
            logger.info("=== ZAKOŃCZENIE SEEDOWANIA DOMYŚLNYCH DANYCH ===")
            
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji domyślnych danych: {e}", exc_info=True)
    
    def _display_seeding_results_table(self, results: List[Dict[str, Any]]):
        """Wyświetla tabelkę z wynikami seedowania."""
        if not results:
            return
            
        # Nagłówki tabeli
        headers = ['Table Name', 'Seeded', 'Created', 'Total', 'Message']
        
        # Oblicz szerokość kolumn
        col_widths = [len(header) for header in headers]
        for result in results:
            col_widths[0] = max(col_widths[0], len(str(result['table_name'])))
            col_widths[1] = max(col_widths[1], len('✅' if result['seeded'] else '❌'))
            col_widths[2] = max(col_widths[2], len(str(result['created_count'])))
            col_widths[3] = max(col_widths[3], len(str(result['total_count'])))
            col_widths[4] = max(col_widths[4], len(str(result['message'])))
        
        # Separator linii
        separator = '+' + '+'.join(['-' * (w + 2) for w in col_widths]) + '+'
        
        # Buduj tabelę
        table_lines = []
        table_lines.append(separator)
        
        # Nagłówek
        header_line = '|'
        for i, header in enumerate(headers):
            header_line += f' {header:<{col_widths[i]}} |'
        table_lines.append(header_line)
        table_lines.append(separator)
        
        # Wiersze danych
        for result in results:
            seeded_icon = '✅' if result['seeded'] else '❌'
            data_line = '|'
            values = [
                result['table_name'],
                seeded_icon,
                str(result['created_count']),
                str(result['total_count']),
                result['message']
            ]
            
            for i, value in enumerate(values):
                data_line += f' {value:<{col_widths[i]}} |'
            table_lines.append(data_line)
        
        table_lines.append(separator)
        
        # Wyświetl tabelę
        logger.info("📊 WYNIKI SEEDOWANIA DOMYŚLNYCH DANYCH:")
        for line in table_lines:
            logger.info(line)
    
    async def _display_seeded_tables_content(self, seed_results: List[Dict[str, Any]], all_tables: Dict[str, Any]):
        """Wyświetla zawartość tabel które zostały zaseedowane lub mają rekordy."""
        try:
            # Filtruj tabele które mają dane do wyświetlenia
            tables_to_show = [
                result for result in seed_results 
                if result['seeded'] or result['total_count'] > 0
            ]
            
            if not tables_to_show:
                logger.info("ℹ️ Brak tabel z danymi do wyświetlenia")
                return
            
            logger.info("📋 ZAWARTOŚĆ TABEL Z DOMYŚLNYMI DANYMI:")
            logger.info("")
            
            for result in tables_to_show:
                table_name_key = result['table_name']
                
                # Znajdź odpowiadającą instancję tabeli w all_tables
                table_instance = None
                for key, instance in all_tables.items():
                    if key == table_name_key:
                        table_instance = instance
                        break
                
                if not table_instance:
                    logger.warning(f"⚠️ Nie znaleziono instancji tabeli: {table_name_key}")
                    continue
                
                try:
                    # Pobierz dane z tabeli (ograniczamy do 20 rekordów dla czytelności)
                    records = await table_instance.get_all(limit=20, offset=0)
                    
                    if not records:
                        logger.info(f"📄 Tabela: {table_name_key.upper()} (pusta)")
                        continue
                    
                    # Wyświetl zawartość tabeli
                    self._display_table_records(table_name_key, records, result['total_count'])
                    logger.info("")  # Pusta linia dla separacji
                    
                except Exception as e:
                    logger.error(f"❌ Błąd podczas pobierania danych z tabeli {table_name_key}: {e}")
                    
        except Exception as e:
            logger.error(f"Błąd podczas wyświetlania zawartości tabel: {e}", exc_info=True)
    
    def _display_table_records(self, table_name: str, records: List[Dict[str, Any]], total_count: int):
        """Wyświetla rekordy tabeli w formacie ASCII."""
        if not records:
            return
        
        # Przygotuj nagłówek
        limit_info = f" (showing {len(records)} of {total_count})" if len(records) < total_count else f" ({total_count} records)"
        logger.info(f"📄 Tabela: {table_name.upper()}{limit_info}")
        
        # Pobierz wszystkie kolumny
        all_columns = set()
        for record in records:
            all_columns.update(record.keys())
        columns = sorted(list(all_columns))
        
        if not columns:
            logger.info("   (brak kolumn)")
            return
        
        # Przygotuj dane do wyświetlenia - ogranicz długość wartości
        display_records = []
        for record in records:
            display_record = {}
            for col in columns:
                value = record.get(col, '')
                # Formatuj różne typy danych
                if value is None:
                    display_value = 'NULL'
                elif isinstance(value, bool):
                    display_value = 'TRUE' if value else 'FALSE'
                elif isinstance(value, (int, float)):
                    display_value = str(value)
                else:
                    display_value = str(value)
                    # Ogranicz długość długich wartości
                    if len(display_value) > 50:
                        display_value = display_value[:47] + '...'
                
                display_record[col] = display_value
            display_records.append(display_record)
        
        # Oblicz szerokość kolumn
        col_widths = {}
        for col in columns:
            col_widths[col] = max(len(col), max(len(record[col]) for record in display_records))
            # Ogranicz maksymalną szerokość kolumny
            col_widths[col] = min(col_widths[col], 60)
        
        # Separator linii
        separator = '+' + '+'.join(['-' * (col_widths[col] + 2) for col in columns]) + '+'
        
        # Buduj tabelę
        table_lines = []
        table_lines.append(separator)
        
        # Nagłówek kolumn
        header_line = '|'
        for col in columns:
            header_line += f' {col:<{col_widths[col]}} |'
        table_lines.append(header_line)
        table_lines.append(separator)
        
        # Wiersze danych
        for record in display_records:
            data_line = '|'
            for col in columns:
                value = record[col]
                # Ogranicz wartość do szerokości kolumny
                if len(value) > col_widths[col]:
                    value = value[:col_widths[col]-3] + '...'
                data_line += f' {value:<{col_widths[col]}} |'
            table_lines.append(data_line)
        
        table_lines.append(separator)
        
        # Wyświetl tabelę z wcięciem
        for line in table_lines:
            logger.info(f"   {line}")
    
    async def get_db_pool(self):
        """Zwraca istniejącą pulę połączeń lub inicjalizuje ją."""
        if self.pool is None:
            await self.init_db()
        if self.pool is None:
            raise ConnectionError("Pula połączeń z bazą danych jest niedostępna.")
        return self.pool
    
    def get_factory(self) -> DatabasePostgreSQLFactory:
        """Zwraca fabrykę tabel."""
        if self.factory is None:
            raise RuntimeError("Fabryka nie została zainicjalizowana. Wywołaj init_db() najpierw.")
        return self.factory
    
    async def close_db(self):
        """Zamyka pulę połączeń."""
        if self.pool:
            await self.pool.close()
            self.pool = None
            self.factory = None
            logger.info("Zamknięto pulę połączeń z bazą danych.")

    async def drop_all_tables(self):
        """Usuwa wszystkie tabele z bazy danych."""
        if self.pool is None:
            await self.init_db()
        
        async with self.pool.acquire() as connection:
            # Kolejność usuwania (odwrotna do tworzenia - z uwzględnieniem zależności)
            table_order = [
                'user_sessions',  # Usuń przed users z powodu foreign key
                'cron_system_sync_job',  # Usuń przed system_sync_job z powodu foreign key
                'system_sync_job',
                'chart_images_harmonic_patterns',
                'technical_analysis_interpretation_chart_images',  # Tabela pośrednia
                'chart_images',
                'general_interpretation',
                'investment_strategies',
                'technical_analysis_interpretation_harmonic_patterns',  # Tabela pośrednia
                'technical_analysis_interpretation',
                'fundamental_analysis_interpretation_analyses',  # Tabela pośrednia
                'fundamental_analysis_interpretation_assets',  # Tabela pośrednia
                'fundamental_analysis_interpretation',
                'technical_analysis_harmonic_patterns',
                'fundamental_analysis_assets',  # Tabela pośrednia
                'fundamental_analysis',
                'asset_exchanges',
                'exchanges',
                'assets',
                'users'
            ]
            
            for table_name in table_order:
                try:
                    await connection.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                    logger.info(f"Usunięto tabelę: {table_name}")
                except Exception as e:
                    logger.warning(f"Nie udało się usunąć tabeli {table_name}: {e}")
            
            logger.info("Usunięto wszystkie tabele z bazy danych.")
    
    async def reset_database(self):
        """Usuwa wszystkie tabele i tworzy je na nowo."""
        logger.info("Rozpoczynam reset bazy danych...")
        await self.drop_all_tables()
        await self._create_all_tables()
        logger.info("Reset bazy danych zakończony.")
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Testuje połączenie z bazą danych i zwraca informacje o wszystkich tabelach.
        
        Returns:
            Dict[str, Any]: Informacje o połączeniu i listę wszystkich tabel w bazie
        """
        try:
            pool = await self.get_db_pool()
            
            async with pool.acquire() as connection:
                # Zapytanie testowe - zwróć wszystkie tabele w schemacie public
                query = """
                SELECT table_name, table_type 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
                """
                
                rows = await connection.fetch(query)
                tables = [{"name": row["table_name"], "type": row["table_type"]} for row in rows]
                
                # Dodatkowe informacje o bazie
                version_query = "SELECT version()"
                version_row = await connection.fetchrow(version_query)
                db_version = version_row["version"] if version_row else "Unknown"
                
                return {
                    "connection": "OK",
                    "database_version": db_version,
                    "tables_count": len(tables),
                    "tables": tables,
                    "test_passed": True
                }
                
        except Exception as e:
            logger.error(f"Test połączenia z bazą danych nieudany: {e}")
            return {
                "connection": "FAILED",
                "error": str(e),
                "test_passed": False
            }