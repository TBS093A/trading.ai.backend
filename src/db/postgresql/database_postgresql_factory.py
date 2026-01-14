from typing import Dict, Type
from .tables import *
import asyncpg
import logging

logger = logging.getLogger(__name__)

class DatabasePostgreSQLFactory:
    """Fabryka do tworzenia obiektów tabel."""
    
    _table_classes: Dict[str, Type[AbstractTable]] = {
        'assets': AssetsTable,
        'exchanges': ExchangesTable,
        'asset_exchanges': AssetExchangesTable,
        'technical_analysis_harmonic_patterns': TechnicalAnalysisHarmonicPatternsTable,
        'system_sync_job': SystemSyncJobTable,
        'cron_system_sync_job': CronSystemSyncJobTable,
        'users': UsersTable,
        'user_sessions': UserSessionsTable
    }
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
        self._instances: Dict[str, AbstractTable] = {}
    
    def get_table(self, table_name: str) -> AbstractTable:
        """Zwraca instancję tabeli o podanej nazwie."""
        if table_name not in self._instances:
            if table_name not in self._table_classes:
                raise ValueError(f"Nieznana tabela: {table_name}")
            
            table_class = self._table_classes[table_name]
            self._instances[table_name] = table_class(self.pool)
            logger.info(f"Utworzono instancję tabeli: {table_name}")
        
        return self._instances[table_name]
    
    def get_assets_table(self) -> AssetsTable:
        """Zwraca tabelę Assets."""
        return self.get_table('assets')
    
    def get_exchanges_table(self) -> ExchangesTable:
        """Zwraca tabelę Exchanges."""
        return self.get_table('exchanges')
    
    def get_asset_exchanges_table(self) -> AssetExchangesTable:
        """Zwraca tabelę AssetExchanges."""
        return self.get_table('asset_exchanges')
    
    def get_technical_analysis_harmonic_patterns_table(self) -> TechnicalAnalysisHarmonicPatternsTable:
        """Zwraca tabelę TechnicalAnalysisHarmonicPatterns."""
        return self.get_table('technical_analysis_harmonic_patterns')
    
    def get_system_sync_job_table(self) -> SystemSyncJobTable:
        """Zwraca tabelę SystemSyncJob."""
        return self.get_table('system_sync_job')
    
    def get_cron_system_sync_job_table(self) -> CronSystemSyncJobTable:
        """Zwraca tabelę CronSystemSyncJob."""
        return self.get_table('cron_system_sync_job')
    
    def get_users_table(self) -> UsersTable:
        """Zwraca tabelę Users."""
        return self.get_table('users')
    
    def get_user_sessions_table(self) -> UserSessionsTable:
        """Zwraca tabelę UserSessions."""
        return self.get_table('user_sessions')
    
    def get_all_tables(self) -> Dict[str, AbstractTable]:
        """Zwraca wszystkie tabele."""
        return {name: self.get_table(name) for name in self._table_classes.keys()}
    
    def get_create_table_queries(self) -> Dict[str, str]:
        """Zwraca wszystkie zapytania CREATE TABLE."""
        return {name: self.get_table(name).create_table() for name in self._table_classes.keys()} 