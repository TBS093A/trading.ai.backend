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
        'cron_system_sync_job': CronSystemSyncJobTable
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
    
    

    
    def get_fundamental_analysis_table(self) -> FundamentalAnalysisTable:
        """Zwraca tabelę FundamentalAnalysis."""
        return self.get_table('fundamental_analysis')
    
    def get_fundamental_analysis_interpretation_table(self) -> FundamentalAnalysisInterpretationTable:
        """Zwraca tabelę FundamentalAnalysisInterpretation."""
        return self.get_table('fundamental_analysis_interpretation')
    
    def get_technical_analysis_harmonic_patterns_table(self) -> TechnicalAnalysisHarmonicPatternsTable:
        """Zwraca tabelę TechnicalAnalysisHarmonicPatterns."""
        return self.get_table('technical_analysis_harmonic_patterns')
    
    def get_technical_analysis_interpretation_table(self) -> TechnicalAnalysisInterpretationTable:
        """Zwraca tabelę TechnicalAnalysisInterpretation."""
        return self.get_table('technical_analysis_interpretation')
    
    def get_technical_analysis_interpretation_harmonic_patterns_table(self) -> TechnicalAnalysisInterpretationHarmonicPatternsTable:
        """Zwraca tabelę TechnicalAnalysisInterpretationHarmonicPatterns."""
        return self.get_table('technical_analysis_interpretation_harmonic_patterns')
    
    def get_technical_analysis_interpretation_chart_images_table(self) -> TechnicalAnalysisInterpretationChartImagesTable:
        """Zwraca tabelę TechnicalAnalysisInterpretationChartImages."""
        return self.get_table('technical_analysis_interpretation_chart_images')
    
    def get_general_interpretation_table(self) -> GeneralInterpretationTable:
        """Zwraca tabelę GeneralInterpretation."""
        return self.get_table('general_interpretation')
    
    def get_investment_strategies_table(self) -> InvestmentStrategiesTable:
        """Zwraca tabelę InvestmentStrategies."""
        return self.get_table('investment_strategies')
    

    def get_chart_images_table(self) -> ChartImagesTable:
        """Zwraca tabelę ChartImages."""
        return self.get_table('chart_images')
    
    def get_chart_images_harmonic_patterns_table(self) -> ChartImagesHarmonicPatternsTable:
        """Zwraca tabelę ChartImagesHarmonicPatterns."""
        return self.get_table('chart_images_harmonic_patterns')
    
    def get_exchange_transactions_table(self) -> ExchangeTransactionsTable:
        """Zwraca tabelę ExchangeTransactions."""
        return self.get_table('exchange_transactions')
    
    def get_exchange_account_state_table(self) -> ExchangeAccountStateTable:
        """Zwraca tabelę ExchangeAccountState."""
        return self.get_table('exchange_account_state')
    
    def get_exchange_account_state_buy_strategies_table(self) -> ExchangeAccountStateBuyStrategiesTable:
        """Zwraca tabelę ExchangeAccountStateBuyStrategies."""
        return self.get_table('exchange_account_state_buy_strategies')
    
    def get_exchange_account_state_sell_strategies_table(self) -> ExchangeAccountStateSellStrategiesTable:
        """Zwraca tabelę ExchangeAccountStateSellStrategies."""
        return self.get_table('exchange_account_state_sell_strategies')
    
    def get_system_sync_job_table(self) -> SystemSyncJobTable:
        """Zwraca tabelę SystemSyncJob."""
        return self.get_table('system_sync_job')
    
    def get_cron_system_sync_job_table(self) -> CronSystemSyncJobTable:
        """Zwraca tabelę CronSystemSyncJob."""
        return self.get_table('cron_system_sync_job')
    
    def get_all_tables(self) -> Dict[str, AbstractTable]:
        """Zwraca wszystkie tabele."""
        return {name: self.get_table(name) for name in self._table_classes.keys()}
    
    def get_create_table_queries(self) -> Dict[str, str]:
        """Zwraca wszystkie zapytania CREATE TABLE."""
        return {name: self.get_table(name).create_table() for name in self._table_classes.keys()} 