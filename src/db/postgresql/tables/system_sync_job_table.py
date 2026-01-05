from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging

logger = logging.getLogger(__name__)

class SystemSyncJobTable(AbstractTable):
    """Klasa do zarządzania tabelą SystemSyncJob."""
    
    def create_table(self) -> str:
        return """
        CREATE SEQUENCE IF NOT EXISTS system_sync_job_id_seq;
        CREATE TABLE IF NOT EXISTS system_sync_job (
            id INTEGER PRIMARY KEY DEFAULT nextval('system_sync_job_id_seq'),
            process VARCHAR(100) NOT NULL UNIQUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        ALTER SEQUENCE system_sync_job_id_seq OWNED BY system_sync_job.id;
        """
    
    async def create(self, process: str) -> Optional[int]:
        """Tworzy nowy system sync job i zwraca jego ID."""
        try:
            job_id = await self.fetch_val(
                "INSERT INTO system_sync_job (process) VALUES ($1) RETURNING id",
                process
            )
            logger.info(f"Utworzono system sync job: {process} z ID: {job_id}")
            return job_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia system sync job: {e}", exc_info=True)
            return None
    
    async def create_many(self, processes: List[str]) -> Dict[str, int]:
        """
        Tworzy wiele system sync jobs jednym zapytaniem i zwraca ich ID.
        
        Args:
            processes: Lista nazw procesów
            
        Returns:
            Dict[str, int]: Słownik mapujący proces na jego ID
        """
        if not processes:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            for process in processes:
                values_list.append(f"(${param_counter})")
                params.append(process)
                param_counter += 1
            
            query = f"""
                INSERT INTO system_sync_job (process) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (process) DO NOTHING
                RETURNING id, process
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_jobs = {}
            for result in results:
                created_jobs[result['process']] = result['id']
            
            logger.info(f"Utworzono {len(created_jobs)} nowych system sync jobs z {len(processes)} prób")
            return created_jobs
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu system sync jobs: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera system sync job po ID."""
        return await self.fetch_one(
            "SELECT id, process, created_at FROM system_sync_job WHERE id = $1",
            record_id
        )
    
    async def get_by_process(self, process: str) -> Optional[Dict[str, Any]]:
        """Pobiera system sync job po nazwie procesu."""
        return await self.fetch_one(
            "SELECT id, process, created_at FROM system_sync_job WHERE process = $1",
            process
        )
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje system sync job o podanym ID."""
        try:
            if 'process' in kwargs:
                await self.execute_query(
                    "UPDATE system_sync_job SET process = $1 WHERE id = $2",
                    kwargs['process'], record_id
                )
                logger.info(f"Zaktualizowano system sync job z ID: {record_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji system sync job: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa system sync job o podanym ID."""
        try:
            await self.execute_query("DELETE FROM system_sync_job WHERE id = $1", record_id)
            logger.info(f"Usunięto system sync job z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania system sync job: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie system sync jobs z limitem i offsetem."""
        return await self.fetch_all(
            "SELECT id, process, created_at FROM system_sync_job ORDER BY id LIMIT $1 OFFSET $2",
            limit, offset
        )
    
    async def search_by_process(self, process: str) -> List[Dict[str, Any]]:
        """Wyszukuje system sync jobs po nazwie procesu."""
        return await self.fetch_all(
            "SELECT id, process, created_at FROM system_sync_job WHERE process ILIKE $1 ORDER BY process",
            f"%{process}%"
        )
    
    async def _seed_default_processes(self) -> Dict[str, int]:
        """Dodaje domyślne procesy do tabeli system_sync_job."""
        try:
            default_processes = [
                "_run_exchanges_sync",
                "_run_technical_analysis_sync",
                "run_full_sync_workflow"
            ]
            
            created_jobs = await self.create_many(default_processes)
            logger.info(f"Zainicjalizowano domyślne procesy synchronizacji: {len(created_jobs)} utworzonych")
            
            # Jeśli nie wszystkie zostały utworzone (już istniały), pobierz wszystkie
            if len(created_jobs) < len(default_processes):
                all_jobs = {}
                for process in default_processes:
                    job = await self.get_by_process(process)
                    if job:
                        all_jobs[process] = job['id']
                
                logger.info(f"Wszystkie domyślne procesy obecne w bazie: {len(all_jobs)}")
                return all_jobs
            
            return created_jobs
            
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji domyślnych procesów: {e}", exc_info=True)
            return {}
    
    async def count_all(self) -> int:
        """Zlicza wszystkie system sync jobs."""
        result = await self.fetch_val("SELECT COUNT(*) FROM system_sync_job")
        return result or 0
    
    async def seed_default_records(self) -> Dict[str, Any]:
        """
        Inicjalizuje domyślne procesy synchronizacji.
        
        Returns:
            Dict[str, Any]: Informacje o seedowaniu
        """
        try:
            # Sprawdź ile rekordów było przed seedowaniem
            initial_count = await self.count_all()
            
            # Wykonaj seedowanie
            created_jobs = await self._seed_default_processes()
            
            # Sprawdź ile rekordów jest po seedowaniu
            final_count = await self.count_all()
            created_count = len(created_jobs) if created_jobs else 0
            
            # Określ message w zależności od wyniku
            if created_count > 0:
                message = f'Created {created_count} new default sync processes'
                seeded = True
            elif final_count > 0:
                message = f'All default sync processes already exist (total: {final_count})'
                seeded = False
            else:
                message = 'No sync processes found after seeding attempt'
                seeded = False
            
            return {
                'table_name': 'system_sync_job',
                'seeded': seeded,
                'created_count': created_count,
                'total_count': final_count,
                'message': message
            }
            
        except Exception as e:
            logger.error(f"Błąd podczas seedowania system_sync_job: {e}", exc_info=True)
            return {
                'table_name': 'system_sync_job',
                'seeded': False,
                'created_count': 0,
                'total_count': await self.count_all(),
                'message': f'Error during seeding: {str(e)}'
            }
