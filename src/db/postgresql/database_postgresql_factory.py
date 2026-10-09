import re
from typing import Dict, List, Type
from .tables import *
import asyncpg
import logging

logger = logging.getLogger(__name__)

_REFERENCES = re.compile(r"REFERENCES\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)


def creation_order(create_queries: Dict[str, str]) -> List[str]:
    """Kolejność tworzenia tabel: najpierw te, do których inne mają klucze obce (REFERENCES).

    Zależności czytane z SQL tabel, więc nowa tabela nie wymaga dopisywania jej do żadnej listy.
    Przy remisie zostaje kolejność z rejestru - wynik jest deterministyczny.
    """
    deps = {
        name: {ref.lower() for ref in _REFERENCES.findall(sql) if ref.lower() != name and ref.lower() in create_queries}
        for name, sql in create_queries.items()
    }
    order: List[str] = []
    remaining = list(create_queries)
    while remaining:
        ready = [n for n in remaining if deps[n] <= set(order)]
        if not ready:
            raise ValueError(f"cykl kluczy obcych między tabelami: {remaining}")
        order.extend(ready)
        remaining = [n for n in remaining if n not in ready]
    return order


class DatabasePostgreSQLFactory:
    """Fabryka do tworzenia obiektów tabel."""
    
    _table_classes: Dict[str, Type[AbstractTable]] = {
        'assets': AssetsTable,
        'exchanges': ExchangesTable,
        'asset_exchanges': AssetExchangesTable,
        'asset_kinds': AssetKindsTable,
        'countries': CountriesTable,
        'asset_kind_map': AssetKindMapTable,
        'asset_country_map': AssetCountryMapTable,
        'technical_analysis_harmonic_patterns': TechnicalAnalysisHarmonicPatternsTable,
        'technical_analysis_harmonic_scan_windows': TechnicalAnalysisHarmonicScanWindowsTable,
        'technical_analysis_harmonic_setups': TechnicalAnalysisHarmonicSetupsTable,
        'system_sync_job': SystemSyncJobTable,
        'cron_system_sync_job': CronSystemSyncJobTable,
        'users': UsersTable,
        'user_sessions': UserSessionsTable,
        'saved_analyses': SavedAnalysesTable,
        'tracked_assets': TrackedAssetsTable,
        'harmonic_setup_alert_settings': HarmonicSetupAlertSettingsTable,
        'harmonic_setup_events': HarmonicSetupEventsTable,
        'harmonic_strength_models': HarmonicStrengthModelsTable,
        'harmonic_variant_reports': HarmonicVariantReportsTable,
        'trading_accounts': TradingTable,
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

    def get_technical_analysis_harmonic_scan_windows_table(self) -> TechnicalAnalysisHarmonicScanWindowsTable:
        """Zwraca tabelę okien skanów formacji harmonicznych (trwały cache skanów)."""
        return self.get_table('technical_analysis_harmonic_scan_windows')

    def get_technical_analysis_harmonic_setups_table(self) -> TechnicalAnalysisHarmonicSetupsTable:
        """Zwraca tabelę setupów formacji harmonicznych i ich wyników."""
        return self.get_table('technical_analysis_harmonic_setups')
    
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
    
    def get_saved_analyses_table(self) -> SavedAnalysesTable:
        """Zwraca tabelę SavedAnalyses."""
        return self.get_table('saved_analyses')

    def get_asset_kinds_table(self) -> AssetKindsTable:
        """Zwraca tabelę AssetKinds."""
        return self.get_table('asset_kinds')

    def get_countries_table(self) -> CountriesTable:
        """Zwraca tabelę Countries."""
        return self.get_table('countries')

    def get_asset_kind_map_table(self) -> AssetKindMapTable:
        """Zwraca tabelę AssetKindMap."""
        return self.get_table('asset_kind_map')

    def get_asset_country_map_table(self) -> AssetCountryMapTable:
        """Zwraca tabelę AssetCountryMap."""
        return self.get_table('asset_country_map')
    
    def get_tracked_assets_table(self) -> TrackedAssetsTable:
        """Assety liczone przez aplikację (nocny sync formacji, śledzenie setupów)."""
        return self.get_table('tracked_assets')

    def get_harmonic_setup_alert_settings_table(self) -> HarmonicSetupAlertSettingsTable:
        return self.get_table('harmonic_setup_alert_settings')

    def get_harmonic_setup_events_table(self) -> HarmonicSetupEventsTable:
        return self.get_table('harmonic_setup_events')

    def get_harmonic_strength_models_table(self) -> HarmonicStrengthModelsTable:
        return self.get_table('harmonic_strength_models')

    def get_harmonic_variant_reports_table(self) -> HarmonicVariantReportsTable:
        return self.get_table('harmonic_variant_reports')

    def get_trading_table(self) -> TradingTable:
        """Trading z sygnałów setupów (src/trading): konta, sygnały, zlecenia, pozycje, dziennik."""
        return self.get_table('trading_accounts')

    def get_all_tables(self) -> Dict[str, AbstractTable]:
        """Zwraca wszystkie tabele."""
        return {name: self.get_table(name) for name in self._table_classes.keys()}
    
    def get_create_table_queries(self) -> Dict[str, str]:
        """Zwraca wszystkie zapytania CREATE TABLE."""
        return {name: self.get_table(name).create_table() for name in self._table_classes.keys()}

    def get_creation_order(self) -> List[str]:
        return creation_order(self.get_create_table_queries())

    def get_drop_order(self) -> List[str]:
        """Odwrotność kolejności tworzenia (CASCADE i tak zdejmie zależności)."""
        return list(reversed(self.get_creation_order()))

    @classmethod
    def registered_table_names(cls) -> List[str]:
        names = list(cls._table_classes)
        for table_class in cls._table_classes.values():
            names.extend(getattr(table_class, "EXTRA_TABLES", ()))
        return names
