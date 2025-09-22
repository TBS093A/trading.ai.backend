#!/usr/bin/env python3
import asyncio
import logging
import traceback
import os
import multiprocessing
import math
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Import klas synchronizacyjnych
from src.sync_exchanges import Exchanges
from src.sync_fundamental_analysis import FundamentalAnalysis
from src.sync_technical_analysis import TechnicalAnalysis
from src.sync_llm_fundamental_analysis_interpretation import LlmFundamentalAnalysisInterpretation
from src.sync_llm_technical_analysis_interpretation import LlmTechnicalAnalysisInterpretation
from src.sync_llm_general_analysis_transaction_decision import LlmGeneralAnalysisTransactionDecision
from src.sync_transactions import Transactions
from src.sync_transactions_wallets import TransactionsWallets
from src.db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class SyncController:
    """
    Kontroler synchronizacji odpowiedzialny za zarządzanie cronjonami
    i orkiestrację procesu synchronizacji wszystkich komponentów systemu.
    
    Workflow synchronizacji:
    1. Exchanges (sync_exchanges.py) -> uruchamiany zaraz po starcie i w soboty
    2. FundamentalAnalysis + TechnicalAnalysis (równolegle, po Exchanges)
    3. LlmFundamentalAnalysisInterpretation (po FundamentalAnalysis)
    4. LlmTechnicalAnalysisInterpretation (po TechnicalAnalysis)
    5. LlmGeneralAnalysisTransactionDecision (po obu interpretacjach LLM)
    6. TransactionsWallets (przed transakcjami, po LlmGeneralAnalysisTransactionDecision)
    7. Transactions (po TransactionsWallets)
    8. TransactionsWallets (po transakcjach, aktualizacja portfeli)
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja kontrolera synchronizacji.
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.scheduler = AsyncIOScheduler()
        
        # Pobierz informacje o zasobach CPU
        self.cpu_count = multiprocessing.cpu_count()
        self.max_workers = max(2, self.cpu_count)  # minimum 2 wątki
        self.thread_executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        logger.info(f"💻 Zainicjalizowano ThreadPool z {self.max_workers} wątkami (dostępne CPU: {self.cpu_count})")
        
        # Inicjalizacja bazy danych
        self._init_database()
        
        # Inicjalizacja klas synchronizacyjnych
        self._init_sync_classes()
        
        # Status workflow - używany do kontroli kolejności wykonania
        self.workflow_status = {
            'exchanges_completed': False,
            'fundamental_analysis_completed': False,
            'technical_analysis_completed': False,
            'llm_fundamental_completed': False,
            'llm_technical_completed': False,
            'llm_general_completed': False,
            'transactions_wallets_pre_completed': False,
            'transactions_completed': False,
            'transactions_wallets_post_completed': False
        }
    
    def _init_database(self) -> None:
        """Inicjalizuje połączenie z bazą danych."""
        try:
            # Inicjalizacja bazy danych
            if not self.test_mode:
                self.db = DatabaseFacade().get_database_postgresql()
            else:
                self.db = DatabaseFacade().get_test_database_postgresql()
                
            logger.info("Zainicjalizowano połączenie z bazą danych")
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji bazy danych: {e}")
            raise
    
    def _init_sync_classes(self) -> None:
        """Inicjalizuje instancje wszystkich klas synchronizacyjnych."""
        try:
            self.exchanges = Exchanges(test_mode=self.test_mode)
            self.fundamental_analysis = FundamentalAnalysis(test_mode=self.test_mode)
            self.technical_analysis = TechnicalAnalysis(test_mode=self.test_mode)
            self.llm_fundamental = LlmFundamentalAnalysisInterpretation(test_mode=self.test_mode)
            self.llm_technical = LlmTechnicalAnalysisInterpretation(test_mode=self.test_mode)
            self.llm_general = LlmGeneralAnalysisTransactionDecision(test_mode=self.test_mode)
            self.transactions_wallets = TransactionsWallets(test_mode=self.test_mode)
            self.transactions = Transactions(test_mode=self.test_mode)
            
            logger.info("Zainicjalizowano wszystkie klasy synchronizacyjne")
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji klas synchronizacyjnych: {e}")
            raise
    
    def _reset_workflow_status(self) -> None:
        """Resetuje status workflow do stanu początkowego."""
        for key in self.workflow_status:
            self.workflow_status[key] = False
        logger.info("Status workflow został zresetowany")
    
    def _calculate_chunk_params(self, total_limit: int, num_workers: int) -> List[Tuple[int, int]]:
        """
        Oblicza parametry chunków (limit, offset) dla podziału zadań między wątki.
        
        Args:
            total_limit: Całkowita liczba elementów do przetworzenia
            num_workers: Liczba wątków roboczych
            
        Returns:
            List[Tuple[int, int]]: Lista tupli (limit, offset) dla każdego chunka
        """
        chunk_size = math.ceil(total_limit / num_workers)
        chunks = []
        
        for i in range(num_workers):
            offset = i * chunk_size
            limit = min(chunk_size, total_limit - offset)
            
            if limit > 0:  # Dodaj chunk tylko jeśli ma elementy do przetworzenia
                chunks.append((limit, offset))
                
        logger.info(f"🔄 Podzielono zadania na {len(chunks)} chunków (chunk_size={chunk_size}, total_limit={total_limit})")
        for i, (limit, offset) in enumerate(chunks):
            logger.info(f"   Chunk {i+1}: limit={limit}, offset={offset}")
            
        return chunks
    
    def _run_sync_method_in_thread_sync(self, sync_method, limit: int, offset: int) -> bool:
        """
        Synchroniczna metoda do uruchamiania metod sync w wątku przez ThreadPoolExecutor.
        
        Args:
            sync_method: Metoda synchronizacyjna do uruchomienia
            limit: Limit dla metody sync
            offset: Offset dla metody sync
            
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            # Utwórz nową pętlę asyncio dla wątku
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Uruchom metodę async w nowej pętli
                result = loop.run_until_complete(sync_method(limit=limit, offset=offset))
                return True
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Błąd w wątku dla metody {sync_method.__name__}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_exchanges_sync(self) -> bool:
        """
        Uruchamia synchronizację giełd.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI GIEŁD ===")
            await self.exchanges.sync_assets()
            self.workflow_status['exchanges_completed'] = True
            logger.info("=== SYNCHRONIZACJA GIEŁD ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji giełd: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_fundamental_analysis_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację analizy fundamentalnej.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI ANALIZY FUNDAMENTALNEJ ===")
            await self.fundamental_analysis.sync_news(limit=limit, offset=offset)
            self.workflow_status['fundamental_analysis_completed'] = True
            logger.info("=== SYNCHRONIZACJA ANALIZY FUNDAMENTALNEJ ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy fundamentalnej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_technical_analysis_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację analizy technicznej.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI ANALIZY TECHNICZNEJ ===")
            await self.technical_analysis.sync_technical_analysis(limit=limit, offset=offset)
            self.workflow_status['technical_analysis_completed'] = True
            logger.info("=== SYNCHRONIZACJA ANALIZY TECHNICZNEJ ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy technicznej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_llm_fundamental_interpretation_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację interpretacji LLM analizy fundamentalnej.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI INTERPRETACJI LLM FUNDAMENTALNEJ ===")
            await self.llm_fundamental.sync_crypto_fundamental_analysis_interpretations(limit=limit, offset=offset)
            self.workflow_status['llm_fundamental_completed'] = True
            logger.info("=== SYNCHRONIZACJA INTERPRETACJI LLM FUNDAMENTALNEJ ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji interpretacji LLM fundamentalnej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_llm_technical_interpretation_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację interpretacji LLM analizy technicznej.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI INTERPRETACJI LLM TECHNICZNEJ ===")
            await self.llm_technical.sync(limit=limit, offset=offset)
            self.workflow_status['llm_technical_completed'] = True
            logger.info("=== SYNCHRONIZACJA INTERPRETACJI LLM TECHNICZNEJ ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji interpretacji LLM technicznej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_llm_general_decision_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację decyzji transakcyjnych LLM.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI DECYZJI LLM GENERALNEJ ===")
            await self.llm_general.sync(limit=limit, offset=offset)
            self.workflow_status['llm_general_completed'] = True
            logger.info("=== SYNCHRONIZACJA DECYZJI LLM GENERALNEJ ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji decyzji LLM generalnej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_transactions_wallets_sync(self, phase: str = "pre") -> bool:
        """
        Uruchamia synchronizację portfeli/walletów z giełd.
        
        Args:
            phase: Faza synchronizacji ("pre" lub "post")
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            phase_label = "PRZED TRANSAKCJAMI" if phase == "pre" else "PO TRANSAKCJACH"
            logger.info(f"=== ROZPOCZĘCIE SYNCHRONIZACJI PORTFELI {phase_label} ===")
            
            sync_report = await self.transactions_wallets.sync()
            
            # Oznacz odpowiednią fazę jako ukończoną
            if phase == "pre":
                self.workflow_status['transactions_wallets_pre_completed'] = True
            else:
                self.workflow_status['transactions_wallets_post_completed'] = True
            
            logger.info(f"=== SYNCHRONIZACJA PORTFELI {phase_label} ZAKOŃCZONA POMYŚLNIE ===")
            logger.info(f"Portfele zsynchronizowane: {sync_report['successful_wallets']}/{sync_report['total_wallets_processed']}")
            
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji portfeli ({phase}): {e}")
            logger.error(traceback.format_exc())
            return False

    async def _run_transactions_sync(self, limit: int = 500, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację transakcji.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI TRANSAKCJI ===")
            await self.transactions.sync(limit=limit, offset=offset)
            self.workflow_status['transactions_completed'] = True
            logger.info("=== SYNCHRONIZACJA TRANSAKCJI ZAKOŃCZONA POMYŚLNIE ===")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji transakcji: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_parallel_analysis(self, limit: int = 50, offset: int = 0) -> tuple[bool, bool]:
        """
        Uruchamia równolegle analizę fundamentalną i techniczną z wykorzystaniem ThreadPool.
        Dzieli zadania między wątki na podstawie dostępnych zasobów CPU.
        
        Returns:
            tuple[bool, bool]: (sukces_fundamental, sukces_technical)
        """
        logger.info("=== ROZPOCZĘCIE RÓWNOLEGŁYCH ANALIZ (FUNDAMENTAL + TECHNICAL) Z THREADPOOL ===")
        
        # Podziel dostępne wątki po połowie między analizy
        workers_per_analysis = max(1, self.max_workers // 2)
        
        logger.info(f"🧵 Przydzielono {workers_per_analysis} wątków dla każdej analizy")
        
        # Oblicz chunki dla obu analiz
        fundamental_chunks = self._calculate_chunk_params(limit, workers_per_analysis)
        technical_chunks = self._calculate_chunk_params(limit, workers_per_analysis)
        
        # Przygotuj zadania dla ThreadPool
        fundamental_futures = []
        technical_futures = []
        
        # Uruchom zadania fundamentalne
        logger.info("📰 Uruchamianie zadań analizy fundamentalnej w ThreadPool")
        for chunk_limit, chunk_offset in fundamental_chunks:
            future = self.thread_executor.submit(
                self._run_sync_method_in_thread_sync,
                self.fundamental_analysis.sync_news,
                chunk_limit,
                chunk_offset + offset  # Dodaj globalny offset
            )
            fundamental_futures.append(future)
        
        # Uruchom zadania techniczne
        logger.info("📈 Uruchamianie zadań analizy technicznej w ThreadPool")
        for chunk_limit, chunk_offset in technical_chunks:
            future = self.thread_executor.submit(
                self._run_sync_method_in_thread_sync,
                self.technical_analysis.sync_technical_analysis,
                chunk_limit,
                chunk_offset + offset  # Dodaj globalny offset
            )
            technical_futures.append(future)
        
        # Oczekuj na zakończenie wszystkich zadań fundamentalnych
        fundamental_success = True
        for future in as_completed(fundamental_futures):
            try:
                result = future.result()
                if not result:
                    fundamental_success = False
            except Exception as e:
                logger.error(f"Wyjątek w zadaniu analizy fundamentalnej: {e}")
                fundamental_success = False
        
        # Oczekuj na zakończenie wszystkich zadań technicznych
        technical_success = True
        for future in as_completed(technical_futures):
            try:
                result = future.result()
                if not result:
                    technical_success = False
            except Exception as e:
                logger.error(f"Wyjątek w zadaniu analizy technicznej: {e}")
                technical_success = False
        
        # Oznacz jako ukończone w zależności od sukcesu
        if fundamental_success:
            self.workflow_status['fundamental_analysis_completed'] = True
        if technical_success:
            self.workflow_status['technical_analysis_completed'] = True
        
        logger.info(f"=== RÓWNOLEGŁE ANALIZY THREADPOOL ZAKOŃCZONE: Fundamental={fundamental_success}, Technical={technical_success} ===")
        return fundamental_success, technical_success
    
    async def _run_parallel_llm_interpretations(self, limit: int = 50, offset: int = 0) -> tuple[bool, bool]:
        """
        Uruchamia równolegle interpretacje LLM z wykorzystaniem ThreadPool.
        Dzieli zadania między wątki na podstawie dostępnych zasobów CPU.
        
        Returns:
            tuple[bool, bool]: (sukces_llm_fundamental, sukces_llm_technical)
        """
        logger.info("=== ROZPOCZĘCIE RÓWNOLEGŁYCH INTERPRETACJI LLM Z THREADPOOL ===")
        
        # Podziel dostępne wątki po połowie między interpretacje
        workers_per_interpretation = max(1, self.max_workers // 2)
        
        logger.info(f"🧵 Przydzielono {workers_per_interpretation} wątków dla każdej interpretacji LLM")
        
        # Oblicz chunki dla obu interpretacji
        fundamental_chunks = self._calculate_chunk_params(limit, workers_per_interpretation)
        technical_chunks = self._calculate_chunk_params(limit, workers_per_interpretation)
        
        # Przygotuj zadania dla ThreadPool
        fundamental_futures = []
        technical_futures = []
        
        # Uruchom zadania interpretacji fundamentalnej LLM
        logger.info("🤖 Uruchamianie zadań interpretacji LLM fundamentalnej w ThreadPool")
        
        for chunk_limit, chunk_offset in fundamental_chunks:
            future = self.thread_executor.submit(
                self._run_sync_method_in_thread_sync,
                self.llm_fundamental.sync_crypto_fundamental_analysis_interpretations,
                chunk_limit,
                chunk_offset + offset  # Dodaj globalny offset
            )
            fundamental_futures.append(future)
        
        # Uruchom zadania interpretacji technicznej LLM
        logger.info("🤖 Uruchamianie zadań interpretacji LLM technicznej w ThreadPool")
        
        for chunk_limit, chunk_offset in technical_chunks:
            future = self.thread_executor.submit(
                self._run_sync_method_in_thread_sync,
                self.llm_technical.sync,
                chunk_limit,
                chunk_offset + offset  # Dodaj globalny offset
            )
            technical_futures.append(future)
        
        # Oczekuj na zakończenie zadań interpretacji fundamentalnej LLM
        llm_fundamental_success = True
        for future in as_completed(fundamental_futures):
            try:
                result = future.result()
                if not result:
                    llm_fundamental_success = False
            except Exception as e:
                logger.error(f"Wyjątek w zadaniu interpretacji LLM fundamentalnej: {e}")
                llm_fundamental_success = False
        
        # Oczekuj na zakończenie zadań interpretacji technicznej LLM
        llm_technical_success = True
        for future in as_completed(technical_futures):
            try:
                result = future.result()
                if not result:
                    llm_technical_success = False
            except Exception as e:
                logger.error(f"Wyjątek w zadaniu interpretacji LLM technicznej: {e}")
                llm_technical_success = False
        
        # Oznacz jako ukończone w zależności od sukcesu
        if llm_fundamental_success:
            self.workflow_status['llm_fundamental_completed'] = True
        if llm_technical_success:
            self.workflow_status['llm_technical_completed'] = True
        
        logger.info(f"=== RÓWNOLEGŁE INTERPRETACJE LLM THREADPOOL ZAKOŃCZONE: Fundamental={llm_fundamental_success}, Technical={llm_technical_success} ===")
        return llm_fundamental_success, llm_technical_success
    
    async def run_full_sync_workflow(self) -> None:
        """
        Uruchamia pełny workflow synchronizacji w określonej kolejności.
        
        Kolejność wykonania:
        1. Exchanges
        2. FundamentalAnalysis + TechnicalAnalysis (równolegle)
        3. LlmFundamentalAnalysisInterpretation + LlmTechnicalAnalysisInterpretation (równolegle)
        4. LlmGeneralAnalysisTransactionDecision
        5. TransactionsWallets (przed transakcjami)
        6. Transactions
        7. TransactionsWallets (po transakcjach)
        """
        try:
            logger.info("🚀 ROZPOCZĘCIE PEŁNEGO WORKFLOW SYNCHRONIZACJI 🚀")
            start_time = datetime.now()
            
            # Reset statusu workflow
            self._reset_workflow_status()
            
            # KROK 1: Exchanges (wymagany dla dalszych kroków)
            logger.info("📊 KROK 1: Synchronizacja giełd")
            exchanges_success = await self._run_exchanges_sync()
            
            if not exchanges_success:
                logger.error("❌ Synchronizacja giełd nieudana - zatrzymuję workflow")
                return
            
            # KROK 2: Równoległe analizy (Fundamental + Technical)
            logger.info("📈 KROK 2: Równoległe analizy (Fundamental + Technical)")
            fundamental_success, technical_success = await self._run_parallel_analysis()
            
            # KROK 3: Równoległe interpretacje LLM (tylko dla udanych analiz)
            logger.info("🤖 KROK 3: Równoległe interpretacje LLM")
            llm_fundamental_success, llm_technical_success = await self._run_parallel_llm_interpretations()
            
            # KROK 4: Decyzja generalna LLM (tylko jeśli przynajmniej jedna interpretacja się udała)
            if llm_fundamental_success or llm_technical_success:
                logger.info("🎯 KROK 4: Decyzja generalna LLM")
                llm_general_success = await self._run_llm_general_decision_sync()
                
                # KROK 5: Synchronizacja portfeli PRZED transakcjami (tylko jeśli decyzja generalna się udała)
                if llm_general_success:
                    logger.info("💼 KROK 5: Synchronizacja portfeli przed transakcjami")
                    wallets_pre_success = await self._run_transactions_wallets_sync(phase="pre")
                    
                    # KROK 6: Transakcje (kontynuuj niezależnie od wyniku synchronizacji portfeli)
                    logger.info("💰 KROK 6: Synchronizacja transakcji")
                    transactions_success = await self._run_transactions_sync()
                    
                    # KROK 7: Synchronizacja portfeli PO transakcjach
                    logger.info("💼 KROK 7: Synchronizacja portfeli po transakcjach")
                    wallets_post_success = await self._run_transactions_wallets_sync(phase="post")
                    
                    if transactions_success:
                        logger.info("✅ PEŁNY WORKFLOW ZAKOŃCZONY POMYŚLNIE")
                        if not wallets_pre_success or not wallets_post_success:
                            logger.warning("⚠️ Workflow zakończony z błędami w synchronizacji portfeli")
                    else:
                        logger.warning("⚠️ Workflow zakończony z błędami w transakcjach")
                else:
                    logger.warning("⚠️ Workflow zatrzymany - decyzja generalna LLM nieudana")
            else:
                logger.warning("⚠️ Workflow zatrzymany - brak udanych interpretacji LLM")
            
            # Podsumowanie
            end_time = datetime.now()
            duration = end_time - start_time
            
            logger.info("📋 PODSUMOWANIE WORKFLOW:")
            logger.info(f"⏱️ Czas wykonania: {duration}")
            logger.info(f"📊 Exchanges: {'✅' if exchanges_success else '❌'}")
            logger.info(f"📰 Fundamental Analysis: {'✅' if fundamental_success else '❌'}")
            logger.info(f"📈 Technical Analysis: {'✅' if technical_success else '❌'}")
            logger.info(f"🤖 LLM Fundamental: {'✅' if llm_fundamental_success else '❌'}")
            logger.info(f"🤖 LLM Technical: {'✅' if llm_technical_success else '❌'}")
            logger.info(f"🎯 LLM General: {'✅' if self.workflow_status['llm_general_completed'] else '❌'}")
            logger.info(f"💼 Wallets Pre: {'✅' if self.workflow_status['transactions_wallets_pre_completed'] else '❌'}")
            logger.info(f"💰 Transactions: {'✅' if self.workflow_status['transactions_completed'] else '❌'}")
            logger.info(f"💼 Wallets Post: {'✅' if self.workflow_status['transactions_wallets_post_completed'] else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ Krytyczny błąd w workflow synchronizacji: {e}")
            logger.error(traceback.format_exc())
    
    async def setup_cron_jobs(self) -> None:
        """Konfiguruje cronjobs dla automatycznego uruchamiania workflow na podstawie bazy danych."""
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # Pobierz wszystkie włączone cron jobs z bazy danych
            cron_table = self.db.get_factory().get_cron_system_sync_job_table()
            enabled_jobs = await cron_table.get_all_enabled()
            
            logger.info(f"🔍 Znaleziono {len(enabled_jobs)} włączonych cron jobs w bazie danych")
            
            for job_config in enabled_jobs:
                try:
                    # Pobierz nazwę procesu i znajdź odpowiadającą mu metodę
                    process_name = job_config['process']
                    method = getattr(self, process_name, None)
                    
                    if method is None:
                        logger.warning(f"⚠️ Nie znaleziono metody {process_name} w SyncController")
                        continue
                    
                    # Przygotuj parametry dla CronTrigger
                    cron_params = {}
                    if job_config['year'] is not None:
                        cron_params['year'] = job_config['year']
                    if job_config['month'] is not None:
                        cron_params['month'] = job_config['month']
                    if job_config['day'] is not None:
                        cron_params['day'] = job_config['day']
                    if job_config['week'] is not None:
                        cron_params['week'] = job_config['week']
                    if job_config['day_of_week'] is not None:
                        cron_params['day_of_week'] = job_config['day_of_week']
                    if job_config['hour'] is not None:
                        cron_params['hour'] = job_config['hour']
                    if job_config['minute'] is not None:
                        cron_params['minute'] = job_config['minute']
                    if job_config['second'] is not None:
                        cron_params['second'] = job_config['second']
                    if job_config['start_date'] is not None:
                        cron_params['start_date'] = job_config['start_date']
                    if job_config['end_date'] is not None:
                        cron_params['end_date'] = job_config['end_date']
                    if job_config['timezone'] is not None:
                        cron_params['timezone'] = job_config['timezone']
                    if job_config['jitter'] is not None and job_config['jitter'] > 0:
                        cron_params['jitter'] = job_config['jitter']
                    
                    # Utwórz CronTrigger z parametrami
                    trigger = CronTrigger(**cron_params)
                    
                    # Dodaj job do schedulera
                    self.scheduler.add_job(
                        func=method,
                        trigger=trigger,
                        id=f"cron_job_{job_config['id']}",
                        name=job_config['name'],
                        replace_existing=True
                    )
                    
                    logger.info(f"✅ Skonfigurowano cron job: {job_config['name']} (ID: {job_config['id']})")
                    
                except Exception as e:
                    logger.error(f"❌ Błąd podczas konfiguracji cron job {job_config.get('name', 'Unknown')}: {e}")
            
            if len(enabled_jobs) == 0:
                logger.warning("⚠️ Brak włączonych cron jobs w bazie danych")
            else:
                logger.info(f"✅ Skonfigurowano {len(enabled_jobs)} cron jobs z bazy danych")
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas konfiguracji cron jobs: {e}")
            raise
    
    async def start(self) -> None:
        """
        Startuje kontroler synchronizacji.
        Uruchamia workflow od razu po starcie, a następnie konfiguruje cronjobs.
        """
        try:
            logger.info("🚀 URUCHAMIANIE SYNC CONTROLLER")
            
            # Konfiguruj cron jobs
            await self.setup_cron_jobs()
            
            # Uruchom scheduler
            self.scheduler.start()
            logger.info("📅 Scheduler uruchomiony")
            
            # Uruchom workflow od razu po starcie
            logger.info("⚡ Uruchamianie workflow po starcie aplikacji")
            await self.run_full_sync_workflow()
            
            # Utrzymuj aplikację przy życiu
            logger.info("🔄 Kontroler działa - oczekiwanie na zaplanowane zadania...")
            
            try:
                # Pętla nieskończona - aplikacja będzie działać do przerwania
                while True:
                    await asyncio.sleep(60)  # Sprawdzaj co minutę czy aplikacja ma działać
                    
            except KeyboardInterrupt:
                logger.info("🛑 Otrzymano sygnał przerwania")
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas uruchamiania kontrolera: {e}")
            logger.error(traceback.format_exc())
            raise
        finally:
            await self.stop()
    
    async def stop(self) -> None:
        """Zatrzymuje kontroler synchronizacji."""
        try:
            logger.info("🛑 ZATRZYMYWANIE SYNC CONTROLLER")
            
            # Zatrzymaj scheduler
            if self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("📅 Scheduler zatrzymany")
            
            # Zatrzymaj thread executor
            self.thread_executor.shutdown(wait=True)
            logger.info("🧵 Thread executor zatrzymany")
            
            logger.info("✅ Sync Controller zatrzymany pomyślnie")
            
        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania kontrolera: {e}")


async def main():
    """Główna funkcja aplikacji."""
    # Konfiguracja logowania
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('sync_controller.log')
        ]
    )
    
    logger.info("🎉 URUCHAMIANIE APLIKACJI SYNC CONTROLLER")
    
    # Utwórz i uruchom kontroler
    controller = SyncController(test_mode=False)
    await controller.start()


if __name__ == "__main__":
    """Punkt startowy aplikacji synchronizującej."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Aplikacja przerwana przez użytkownika")
    except Exception as e:
        print(f"❌ Krytyczny błąd aplikacji: {e}")
        logging.error(f"Krytyczny błąd aplikacji: {e}")
        logging.error(traceback.format_exc())
    finally:
        print("👋 Aplikacja zakończona")
