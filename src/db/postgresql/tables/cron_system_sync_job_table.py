from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class CronSystemSyncJobTable(AbstractTable):
    """Klasa do zarządzania tabelą CronSystemSyncJob."""
    
    def create_table(self) -> str:
        return """
        CREATE SEQUENCE IF NOT EXISTS cron_system_sync_job_id_seq;
        CREATE TABLE IF NOT EXISTS cron_system_sync_job (
            id INTEGER PRIMARY KEY DEFAULT nextval('cron_system_sync_job_id_seq'),
            name VARCHAR(255) NOT NULL,
            system_sync_job_id INTEGER NOT NULL REFERENCES system_sync_job(id) ON DELETE CASCADE,
            year INTEGER,
            month INTEGER CHECK (month >= 1 AND month <= 12),
            day INTEGER CHECK (day >= 1 AND day <= 31),
            week INTEGER,
            day_of_week VARCHAR(10),  -- może być liczbą 0-6 lub nazwą mon-sun
            hour INTEGER CHECK (hour >= 0 AND hour <= 23),
            minute INTEGER CHECK (minute >= 0 AND minute <= 59),
            second INTEGER CHECK (second >= 0 AND second <= 59),
            start_date TIMESTAMP WITH TIME ZONE,
            end_date TIMESTAMP WITH TIME ZONE,
            timezone VARCHAR(50) DEFAULT 'UTC',
            jitter INTEGER DEFAULT 0,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        ALTER SEQUENCE cron_system_sync_job_id_seq OWNED BY cron_system_sync_job.id;
        """
    
    async def create(self, name: str, system_sync_job_id: int, year: Optional[int] = None, 
                    month: Optional[int] = None, day: Optional[int] = None, week: Optional[int] = None,
                    day_of_week: Optional[str] = None, hour: Optional[int] = None, 
                    minute: Optional[int] = None, second: Optional[int] = None,
                    start_date: Optional[str] = None, end_date: Optional[str] = None,
                    timezone: str = 'UTC', jitter: int = 0, enabled: bool = True) -> Optional[int]:
        """Tworzy nowy cron system sync job i zwraca jego ID."""
        try:
            cron_job_id = await self.fetch_val("""
                INSERT INTO cron_system_sync_job 
                (name, system_sync_job_id, year, month, day, week, day_of_week, hour, minute, second, 
                 start_date, end_date, timezone, jitter, enabled) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15) 
                RETURNING id
            """, name, system_sync_job_id, year, month, day, week, day_of_week, hour, minute, second, 
                start_date, end_date, timezone, jitter, enabled)
            
            logger.info(f"Utworzono cron system sync job: {name} z ID: {cron_job_id}")
            return cron_job_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia cron system sync job: {e}", exc_info=True)
            return None
    
    async def create_many(self, cron_jobs: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Tworzy wiele cron system sync jobs jednym zapytaniem i zwraca ich ID.
        
        Args:
            cron_jobs: Lista słowników z parametrami cron jobów
            
        Returns:
            Dict[str, int]: Słownik mapujący nazwę na ID
        """
        if not cron_jobs:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            for job in cron_jobs:
                name = job.get('name')
                system_sync_job_id = job.get('system_sync_job_id')
                year = job.get('year')
                month = job.get('month')
                day = job.get('day')
                week = job.get('week')
                day_of_week = job.get('day_of_week')
                hour = job.get('hour')
                minute = job.get('minute')
                second = job.get('second')
                start_date = job.get('start_date')
                end_date = job.get('end_date')
                timezone = job.get('timezone', 'UTC')
                jitter = job.get('jitter', 0)
                enabled = job.get('enabled', True)
                
                values_list.append(f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2}, ${param_counter + 3}, ${param_counter + 4}, ${param_counter + 5}, ${param_counter + 6}, ${param_counter + 7}, ${param_counter + 8}, ${param_counter + 9}, ${param_counter + 10}, ${param_counter + 11}, ${param_counter + 12}, ${param_counter + 13}, ${param_counter + 14})")
                params.extend([name, system_sync_job_id, year, month, day, week, day_of_week, hour, minute, second, start_date, end_date, timezone, jitter, enabled])
                param_counter += 15
            
            query = f"""
                INSERT INTO cron_system_sync_job 
                (name, system_sync_job_id, year, month, day, week, day_of_week, hour, minute, second, 
                 start_date, end_date, timezone, jitter, enabled) 
                VALUES {', '.join(values_list)}
                RETURNING id, name
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_jobs = {}
            for result in results:
                created_jobs[result['name']] = result['id']
            
            logger.info(f"Utworzono {len(created_jobs)} nowych cron system sync jobs z {len(cron_jobs)} prób")
            return created_jobs
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu cron system sync jobs: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera cron system sync job po ID wraz z informacjami o powiązanym procesie."""
        return await self.fetch_one("""
            SELECT csj.id, csj.name, csj.system_sync_job_id, csj.year, csj.month, csj.day, csj.week, 
                   csj.day_of_week, csj.hour, csj.minute, csj.second, csj.start_date, csj.end_date, 
                   csj.timezone, csj.jitter, csj.enabled, csj.created_at, csj.updated_at,
                   ssj.process
            FROM cron_system_sync_job csj
            JOIN system_sync_job ssj ON csj.system_sync_job_id = ssj.id
            WHERE csj.id = $1
        """, record_id)
    
    async def get_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Pobiera cron system sync job po nazwie."""
        return await self.fetch_one("""
            SELECT csj.id, csj.name, csj.system_sync_job_id, csj.year, csj.month, csj.day, csj.week, 
                   csj.day_of_week, csj.hour, csj.minute, csj.second, csj.start_date, csj.end_date, 
                   csj.timezone, csj.jitter, csj.enabled, csj.created_at, csj.updated_at,
                   ssj.process
            FROM cron_system_sync_job csj
            JOIN system_sync_job ssj ON csj.system_sync_job_id = ssj.id
            WHERE csj.name = $1
        """, name)
    
    async def get_all_enabled(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie włączone cron system sync jobs."""
        return await self.fetch_all("""
            SELECT csj.id, csj.name, csj.system_sync_job_id, csj.year, csj.month, csj.day, csj.week, 
                   csj.day_of_week, csj.hour, csj.minute, csj.second, csj.start_date, csj.end_date, 
                   csj.timezone, csj.jitter, csj.enabled, csj.created_at, csj.updated_at,
                   ssj.process
            FROM cron_system_sync_job csj
            JOIN system_sync_job ssj ON csj.system_sync_job_id = ssj.id
            WHERE csj.enabled = TRUE
            ORDER BY csj.id
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje cron system sync job o podanym ID."""
        try:
            update_fields = []
            values = []
            param_count = 1
            
            allowed_fields = [
                'name', 'system_sync_job_id', 'year', 'month', 'day', 'week', 'day_of_week',
                'hour', 'minute', 'second', 'start_date', 'end_date', 'timezone', 'jitter', 'enabled'
            ]
            
            for field in allowed_fields:
                if field in kwargs:
                    update_fields.append(f"{field} = ${param_count}")
                    values.append(kwargs[field])
                    param_count += 1
            
            if not update_fields:
                return False
            
            # Dodaj updated_at
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            values.append(record_id)
            query = f"UPDATE cron_system_sync_job SET {', '.join(update_fields)} WHERE id = ${param_count}"
            
            await self.execute_query(query, *values)
            logger.info(f"Zaktualizowano cron system sync job z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji cron system sync job: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa cron system sync job o podanym ID."""
        try:
            await self.execute_query("DELETE FROM cron_system_sync_job WHERE id = $1", record_id)
            logger.info(f"Usunięto cron system sync job z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania cron system sync job: {e}", exc_info=True)
            return False
    
    async def enable_job(self, record_id: int) -> bool:
        """Włącza cron system sync job."""
        return await self.update(record_id, enabled=True)
    
    async def disable_job(self, record_id: int) -> bool:
        """Wyłącza cron system sync job."""
        return await self.update(record_id, enabled=False)
    
    async def get_by_process(self, process: str) -> List[Dict[str, Any]]:
        """Pobiera wszystkie cron jobs dla danego procesu."""
        return await self.fetch_all("""
            SELECT csj.id, csj.name, csj.system_sync_job_id, csj.year, csj.month, csj.day, csj.week, 
                   csj.day_of_week, csj.hour, csj.minute, csj.second, csj.start_date, csj.end_date, 
                   csj.timezone, csj.jitter, csj.enabled, csj.created_at, csj.updated_at,
                   ssj.process
            FROM cron_system_sync_job csj
            JOIN system_sync_job ssj ON csj.system_sync_job_id = ssj.id
            WHERE ssj.process = $1
            ORDER BY csj.id
        """, process)
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie cron system sync jobs z limitem i offsetem."""
        return await self.fetch_all("""
            SELECT csj.id, csj.name, csj.system_sync_job_id, csj.year, csj.month, csj.day, csj.week, 
                   csj.day_of_week, csj.hour, csj.minute, csj.second, csj.start_date, csj.end_date, 
                   csj.timezone, csj.jitter, csj.enabled, csj.created_at, csj.updated_at,
                   ssj.process
            FROM cron_system_sync_job csj
            JOIN system_sync_job ssj ON csj.system_sync_job_id = ssj.id
            ORDER BY csj.id
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def _seed_default_cron_job(self, system_sync_jobs: Dict[str, int]) -> bool:
        """Dodaje domyślny cron job dla run_full_sync_workflow o 6:00 codziennie."""
        try:
            # Sprawdź czy już istnieje domyślny job
            existing_job = await self.get_by_name("Daily Synchronization - run_full_sync_workflow")
            if existing_job:
                logger.info("Domyślny cron job już istnieje")
                return False
            
            # Pobierz ID procesu run_full_sync_workflow
            process_id = system_sync_jobs.get("run_full_sync_workflow")
            if not process_id:
                logger.error("Nie znaleziono procesu run_full_sync_workflow w system_sync_jobs")
                return False
            
            # Utwórz domyślny cron job - codziennie o 6:00:00
            default_job = {
                'name': 'Daily Synchronization - run_full_sync_workflow',
                'system_sync_job_id': process_id,
                'hour': 6,
                'minute': 0,
                'second': 0,
                'timezone': 'UTC',
                'enabled': True
            }
            
            job_id = await self.create(**default_job)
            if job_id:
                logger.info(f"Utworzono domyślny cron job dla daily synchronization z ID: {job_id}")
                return True
            else:
                logger.error("Nie udało się utworzyć domyślnego cron job")
                return False
                
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia domyślnego cron job: {e}", exc_info=True)
            return False
    
    async def count_all(self) -> int:
        """Zlicza wszystkie cron system sync jobs."""
        result = await self.fetch_val("SELECT COUNT(*) FROM cron_system_sync_job")
        return result or 0
    
    async def count_enabled(self) -> int:
        """Zlicza włączone cron system sync jobs."""
        result = await self.fetch_val("SELECT COUNT(*) FROM cron_system_sync_job WHERE enabled = TRUE")
        return result or 0
    
    async def seed_default_records(self) -> Dict[str, Any]:
        """
        Inicjalizuje domyślny cron job dla daily synchronization.
        
        Returns:
            Dict[str, Any]: Informacje o seedowaniu
        """
        try:
            # Sprawdź ile rekordów było przed seedowaniem
            initial_count = await self.count_all()
            
            # Pobierz system_sync_jobs (potrzebne do seedowania cron job)
            # W praktyce powinny już istnieć z poprzedniego seedowania SystemSyncJobTable
            from .system_sync_job_table import SystemSyncJobTable
            system_sync_job_table = SystemSyncJobTable(self.pool)
            
            # Pobierz ID procesu run_full_sync_workflow
            workflow_job = await system_sync_job_table.get_by_process('run_full_sync_workflow')
            
            if not workflow_job:
                return {
                    'table_name': 'cron_system_sync_job',
                    'seeded': False,
                    'created_count': 0,
                    'total_count': initial_count,
                    'message': 'Cannot seed: run_full_sync_workflow process not found'
                }
            
            # Wykonaj seedowanie
            system_sync_jobs = {'run_full_sync_workflow': workflow_job['id']}
            created = await self._seed_default_cron_job(system_sync_jobs)
            
            # Sprawdź ile rekordów jest po seedowaniu
            final_count = await self.count_all()
            created_count = final_count - initial_count
            
            # Określ message w zależności od wyniku
            if created:
                message = f'Created {created_count} new default cron job(s)'
                seeded = True
            elif final_count > 0:
                message = f'Default cron job already exists (total: {final_count})'
                seeded = False
            else:
                message = 'No cron jobs found after seeding attempt'
                seeded = False
            
            return {
                'table_name': 'cron_system_sync_job',
                'seeded': seeded,
                'created_count': created_count,
                'total_count': final_count,
                'message': message
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas seedowania cron_system_sync_job: {e}", exc_info=True)
            return {
                'table_name': 'cron_system_sync_job',
                'seeded': False,
                'created_count': 0,
                'total_count': await self.count_all(),
                'message': f'Error during seeding: {str(e)}'
            }
