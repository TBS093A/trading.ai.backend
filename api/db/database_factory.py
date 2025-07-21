from typing import Dict, Type
from .abstract_table import AbstractTable
from .assets_table import AssetsTable
from .users_table import UsersTable
from .user_secrets_table import UserSecretsTable
from .transactions_table import TransactionsTable
from .fundamental_analysis_table import FundamentalAnalysisTable
from .fundamental_analysis_interpretation_table import FundamentalAnalysisInterpretationTable
from .technical_analysis_table import TechnicalAnalysisTable
from .technical_analysis_interpretation_table import TechnicalAnalysisInterpretationTable
from .general_interpretation_table import GeneralInterpretationTable
from .telegram_signal_channels_table import TelegramSignalChannelsTable
from .telegram_signals_table import TelegramSignalsTable
from .telegram_signal_interpretation_table import TelegramSignalInterpretationTable
import asyncpg
import logging

logger = logging.getLogger(__name__)

class DatabaseFactory:
    """Fabryka do tworzenia obiektów tabel."""
    
    _table_classes: Dict[str, Type[AbstractTable]] = {
        'assets': AssetsTable,
        'users': UsersTable,
        'user_secrets': UserSecretsTable,
        'transactions': TransactionsTable,
        'fundamental_analysis': FundamentalAnalysisTable,
        'fundamental_analysis_interpretation': FundamentalAnalysisInterpretationTable,
        'technical_analysis': TechnicalAnalysisTable,
        'technical_analysis_interpretation': TechnicalAnalysisInterpretationTable,
        'general_interpretation': GeneralInterpretationTable,
        'telegram_signal_channels': TelegramSignalChannelsTable,
        'telegram_signals': TelegramSignalsTable,
        'telegram_signal_interpretation': TelegramSignalInterpretationTable
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
    
    def get_users_table(self) -> UsersTable:
        """Zwraca tabelę Users."""
        return self.get_table('users')
    
    def get_user_secrets_table(self) -> UserSecretsTable:
        """Zwraca tabelę UserSecrets."""
        return self.get_table('user_secrets')
    
    def get_transactions_table(self) -> TransactionsTable:
        """Zwraca tabelę Transactions."""
        return self.get_table('transactions')
    
    def get_fundamental_analysis_table(self) -> FundamentalAnalysisTable:
        """Zwraca tabelę FundamentalAnalysis."""
        return self.get_table('fundamental_analysis')
    
    def get_fundamental_analysis_interpretation_table(self) -> FundamentalAnalysisInterpretationTable:
        """Zwraca tabelę FundamentalAnalysisInterpretation."""
        return self.get_table('fundamental_analysis_interpretation')
    
    def get_technical_analysis_table(self) -> TechnicalAnalysisTable:
        """Zwraca tabelę TechnicalAnalysis."""
        return self.get_table('technical_analysis')
    
    def get_technical_analysis_interpretation_table(self) -> TechnicalAnalysisInterpretationTable:
        """Zwraca tabelę TechnicalAnalysisInterpretation."""
        return self.get_table('technical_analysis_interpretation')
    
    def get_general_interpretation_table(self) -> GeneralInterpretationTable:
        """Zwraca tabelę GeneralInterpretation."""
        return self.get_table('general_interpretation')
    
    def get_telegram_signal_channels_table(self) -> TelegramSignalChannelsTable:
        """Zwraca tabelę TelegramSignalChannels."""
        return self.get_table('telegram_signal_channels')
    
    def get_telegram_signals_table(self) -> TelegramSignalsTable:
        """Zwraca tabelę TelegramSignals."""
        return self.get_table('telegram_signals')
    
    def get_telegram_signal_interpretation_table(self) -> TelegramSignalInterpretationTable:
        """Zwraca tabelę TelegramSignalInterpretation."""
        return self.get_table('telegram_signal_interpretation')
    
    def get_all_tables(self) -> Dict[str, AbstractTable]:
        """Zwraca wszystkie tabele."""
        return {name: self.get_table(name) for name in self._table_classes.keys()}
    
    def get_create_table_queries(self) -> Dict[str, str]:
        """Zwraca wszystkie zapytania CREATE TABLE."""
        return {name: self.get_table(name).create_table() for name in self._table_classes.keys()} 