#!/usr/bin/env python3
import asyncio
import logging
import traceback
import os
import multiprocessing
import math
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from celery.result import AsyncResult
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Import bazy danych
from src.db.database_facade import DatabaseFacade

# Import Celery tasks
from src.celery_tasks.sync_tasks import sync_exchanges_task
from src.celery_tasks.analysis_tasks import (
    sync_technical_analysis_task,
    sync_fundamental_analysis_task
)
from src.celery_tasks.llm_tasks import (
    sync_llm_technical_interpretation_task,
    sync_llm_fundamental_interpretation_task,
    sync_llm_general_decision_task
)
from src.celery_tasks.transaction_tasks import (
    sync_transactions_wallets_task,
    sync_transactions_task
)
from src.controller_rest_celery_worker import get_celery_app

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
        
        # Inicjalizacja Celery
        self.celery_app = get_celery_app()
        logger.info("🔧 Zainicjalizowano Celery app")
        
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
        """
        Metoda zastępcza - klasy synchronizacyjne nie są już bezpośrednio używane.
        Wszystkie operacje synchronizacji są teraz wykonywane przez Celery workers.
        """
        logger.info("Klasy synchronizacyjne są zarządzane przez Celery workers")
    
    def _reset_workflow_status(self) -> None:
        """Resetuje status workflow do stanu początkowego."""
        for key in self.workflow_status:
            self.workflow_status[key] = False
        logger.info("Status workflow został zresetowany")
    
    def _get_available_celery_workers(self, queue: str = None) -> int:
        """
        Pobiera liczbę dostępnych (wolnych) workerów Celery.
        
        Args:
            queue: Nazwa kolejki (opcjonalnie - jeśli None, liczy wszystkich)
            
        Returns:
            int: Liczba dostępnych workerów
        """
        try:
            inspect = self.celery_app.control.inspect()
            
            # Pobierz statystyki workerów
            stats = inspect.stats()
            active_tasks = inspect.active()
            
            if stats is None or active_tasks is None:
                logger.warning("⚠️ Nie można pobrać statystyk workerów Celery - używam wartości domyślnej (2)")
                return 2  # Domyślna wartość
            
            # Policz dostępnych workerów
            total_workers = 0
            busy_workers = 0
            
            for worker_name in stats.keys():
                total_workers += 1
                # Sprawdź czy worker ma aktywne zadania
                if worker_name in active_tasks and len(active_tasks[worker_name]) > 0:
                    busy_workers += 1
            
            available_workers = max(1, total_workers - busy_workers)  # Minimum 1
            
            logger.info(f"👷 Celery workers: total={total_workers}, busy={busy_workers}, available={available_workers}")
            
            return available_workers
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas pobierania informacji o workerach Celery: {e}")
            return 2  # Domyślna wartość w przypadku błędu
    
    def _calculate_chunk_params(self, total_limit: int, num_workers: int, global_offset: int = 0) -> List[Tuple[int, int]]:
        """
        Oblicza parametry chunków (limit, offset) dla podziału zadań między workerów.
        
        Args:
            total_limit: Całkowita liczba elementów do przetworzenia
            num_workers: Liczba workerów
            global_offset: Globalny offset (opcjonalny)
            
        Returns:
            List[Tuple[int, int]]: Lista tupli (limit, offset) dla każdego chunka
        """
        chunk_size = math.ceil(total_limit / num_workers)
        chunks = []
        
        for i in range(num_workers):
            offset = global_offset + (i * chunk_size)
            limit = min(chunk_size, total_limit - (i * chunk_size))
            
            if limit > 0:  # Dodaj chunk tylko jeśli ma elementy do przetworzenia
                chunks.append((limit, offset))
                
        logger.info(f"🔄 Podzielono zadania na {len(chunks)} chunków (chunk_size={chunk_size}, total_limit={total_limit})")
        for i, (limit, offset) in enumerate(chunks):
            logger.info(f"   Chunk {i+1}: limit={limit}, offset={offset}")
            
        return chunks
    
    async def _wait_for_celery_tasks(self, task_results: List[AsyncResult], task_name: str = "tasks") -> bool:
        """
        Czeka na zakończenie zadań Celery i zbiera wyniki.
        
        Args:
            task_results: Lista AsyncResult z Celery
            task_name: Nazwa zadań (do logowania)
            
        Returns:
            bool: True jeśli wszystkie zadania się udały, False w przeciwnym razie
        """
        try:
            logger.info(f"⏳ Oczekiwanie na zakończenie {len(task_results)} zadań {task_name}")
            
            all_success = True
            completed_tasks = 0
            
            # Czekaj na zakończenie wszystkich zadań
            for i, task_result in enumerate(task_results):
                try:
                    # Czekaj na zakończenie zadania (blocking call, ale w async context używamy sleep)
                    while not task_result.ready():
                        await asyncio.sleep(1)  # Sprawdzaj co sekundę
                    
                    # Pobierz wynik
                    result = task_result.result
                    
                    if isinstance(result, dict):
                        success = result.get('success', False)
                        if success:
                            completed_tasks += 1
                            logger.info(f"✅ Zadanie {i+1}/{len(task_results)} {task_name} zakończone pomyślnie")
                        else:
                            all_success = False
                            error_msg = result.get('error', 'Unknown error')
                            logger.error(f"❌ Zadanie {i+1}/{len(task_results)} {task_name} nieudane: {error_msg}")
                    else:
                        logger.warning(f"⚠️ Zadanie {i+1}/{len(task_results)} {task_name} zwróciło nieoczekiwany wynik")
                        all_success = False
                        
                except Exception as e:
                    logger.error(f"❌ Błąd podczas oczekiwania na zadanie {i+1}/{len(task_results)} {task_name}: {e}")
                    all_success = False
            
            logger.info(f"📊 Zadania {task_name}: {completed_tasks}/{len(task_results)} pomyślnych")
            return all_success
            
        except Exception as e:
            logger.error(f"❌ Błąd podczas czekania na zadania {task_name}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_exchanges_sync(self) -> bool:
        """
        Uruchamia synchronizację giełd przez Celery.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI GIEŁD (CELERY) ===")
            
            # Wyślij zadanie do Celery
            task_result = sync_exchanges_task.apply_async(
                kwargs={'test_mode': self.test_mode},
                queue='sync_queue'
            )
            
            logger.info(f"📤 Wysłano zadanie synchronizacji giełd: task_id={task_result.id}")
            
            # Czekaj na zakończenie zadania
            success = await self._wait_for_celery_tasks([task_result], "exchanges_sync")
            
            if success:
                self.workflow_status['exchanges_completed'] = True
                logger.info("=== SYNCHRONIZACJA GIEŁD ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA GIEŁD NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji giełd: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_fundamental_analysis_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację analizy fundamentalnej przez Celery z podziałem na workerów.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI ANALIZY FUNDAMENTALNEJ (CELERY) ===")
            
            # Pobierz liczbę dostępnych workerów
            available_workers = self._get_available_celery_workers()
            
            # Oblicz chunki
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            # Przygotuj zadania dla Celery
            tasks = []
            
            logger.info("📰 Uruchamianie zadań analizy fundamentalnej w Celery")
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_fundamental_analysis_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode
                    },
                    queue='analysis_queue'
                )
                tasks.append(task_result)
                logger.info(f"📤 Wysłano zadanie fundamentalne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Czekaj na zakończenie wszystkich zadań
            success = await self._wait_for_celery_tasks(tasks, "fundamental_analysis")
            
            if success:
                self.workflow_status['fundamental_analysis_completed'] = True
                logger.info("=== SYNCHRONIZACJA ANALIZY FUNDAMENTALNEJ ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA ANALIZY FUNDAMENTALNEJ NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy fundamentalnej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_technical_analysis_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację analizy technicznej przez Celery z podziałem na workerów.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI ANALIZY TECHNICZNEJ (CELERY) ===")
            
            # Pobierz liczbę dostępnych workerów
            available_workers = self._get_available_celery_workers()
            
            # Oblicz chunki
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            # Przygotuj zadania dla Celery
            tasks = []
            
            logger.info("📈 Uruchamianie zadań analizy technicznej w Celery")
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_technical_analysis_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode
                    },
                    queue='analysis_queue'
                )
                tasks.append(task_result)
                logger.info(f"📤 Wysłano zadanie techniczne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Czekaj na zakończenie wszystkich zadań
            success = await self._wait_for_celery_tasks(tasks, "technical_analysis")
            
            if success:
                self.workflow_status['technical_analysis_completed'] = True
                logger.info("=== SYNCHRONIZACJA ANALIZY TECHNICZNEJ ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA ANALIZY TECHNICZNEJ NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji analizy technicznej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_llm_fundamental_interpretation_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację interpretacji LLM analizy fundamentalnej przez Celery z podziałem na workerów.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI INTERPRETACJI LLM FUNDAMENTALNEJ (CELERY) ===")
            
            # Pobierz liczbę dostępnych workerów
            available_workers = self._get_available_celery_workers()
            
            # Oblicz chunki
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            # Przygotuj zadania dla Celery
            tasks = []
            
            logger.info("🤖📊 Uruchamianie zadań interpretacji LLM fundamentalnej w Celery")
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_llm_fundamental_interpretation_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"📤 Wysłano zadanie LLM fundamentalne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Czekaj na zakończenie wszystkich zadań
            success = await self._wait_for_celery_tasks(tasks, "llm_fundamental_interpretation")
            
            if success:
                self.workflow_status['llm_fundamental_completed'] = True
                logger.info("=== SYNCHRONIZACJA INTERPRETACJI LLM FUNDAMENTALNEJ ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA INTERPRETACJI LLM FUNDAMENTALNEJ NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji interpretacji LLM fundamentalnej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_llm_technical_interpretation_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację interpretacji LLM analizy technicznej przez Celery z podziałem na workerów.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI INTERPRETACJI LLM TECHNICZNEJ (CELERY) ===")
            
            # Pobierz liczbę dostępnych workerów
            available_workers = self._get_available_celery_workers()
            
            # Oblicz chunki
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            # Przygotuj zadania dla Celery
            tasks = []
            
            logger.info("🤖📈 Uruchamianie zadań interpretacji LLM technicznej w Celery")
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_llm_technical_interpretation_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"📤 Wysłano zadanie LLM techniczne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Czekaj na zakończenie wszystkich zadań
            success = await self._wait_for_celery_tasks(tasks, "llm_technical_interpretation")
            
            if success:
                self.workflow_status['llm_technical_completed'] = True
                logger.info("=== SYNCHRONIZACJA INTERPRETACJI LLM TECHNICZNEJ ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA INTERPRETACJI LLM TECHNICZNEJ NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji interpretacji LLM technicznej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_llm_general_decision_sync(self, limit: int = 50, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację decyzji transakcyjnych LLM przez Celery z podziałem na workerów.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI DECYZJI LLM GENERALNEJ (CELERY) ===")
            
            # Pobierz liczbę dostępnych workerów
            available_workers = self._get_available_celery_workers()
            
            # Oblicz chunki
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            # Przygotuj zadania dla Celery
            tasks = []
            
            logger.info("🎯 Uruchamianie zadań decyzji LLM generalnej w Celery")
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_llm_general_decision_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode
                    },
                    queue='llm_queue'
                )
                tasks.append(task_result)
                logger.info(f"📤 Wysłano zadanie LLM generalne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Czekaj na zakończenie wszystkich zadań
            success = await self._wait_for_celery_tasks(tasks, "llm_general_decision")
            
            if success:
                self.workflow_status['llm_general_completed'] = True
                logger.info("=== SYNCHRONIZACJA DECYZJI LLM GENERALNEJ ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA DECYZJI LLM GENERALNEJ NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji decyzji LLM generalnej: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_transactions_wallets_sync(self, phase: str = "pre") -> bool:
        """
        Uruchamia synchronizację portfeli/walletów z giełd przez Celery.
        
        Args:
            phase: Faza synchronizacji ("pre" lub "post")
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            phase_label = "PRZED TRANSAKCJAMI" if phase == "pre" else "PO TRANSAKCJACH"
            logger.info(f"=== ROZPOCZĘCIE SYNCHRONIZACJI PORTFELI {phase_label} (CELERY) ===")
            
            # Wyślij zadanie do Celery
            task_result = sync_transactions_wallets_task.apply_async(
                kwargs={
                    'phase': phase,
                    'test_mode': self.test_mode
                },
                queue='transaction_queue'
            )
            
            logger.info(f"📤 Wysłano zadanie synchronizacji portfeli: task_id={task_result.id}, phase={phase}")
            
            # Czekaj na zakończenie zadania
            success = await self._wait_for_celery_tasks([task_result], f"transactions_wallets_{phase}")
            
            if success:
                # Oznacz odpowiednią fazę jako ukończoną
                if phase == "pre":
                    self.workflow_status['transactions_wallets_pre_completed'] = True
                else:
                    self.workflow_status['transactions_wallets_post_completed'] = True
                
                logger.info(f"=== SYNCHRONIZACJA PORTFELI {phase_label} ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error(f"=== SYNCHRONIZACJA PORTFELI {phase_label} NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji portfeli ({phase}): {e}")
            logger.error(traceback.format_exc())
            return False

    async def _run_transactions_sync(self, limit: int = 500, offset: int = 0) -> bool:
        """
        Uruchamia synchronizację transakcji przez Celery z podziałem na workerów.
        
        Returns:
            bool: True jeśli synchronizacja się udała, False w przeciwnym razie
        """
        try:
            logger.info("=== ROZPOCZĘCIE SYNCHRONIZACJI TRANSAKCJI (CELERY) ===")
            
            # Pobierz liczbę dostępnych workerów
            available_workers = self._get_available_celery_workers()
            
            # Oblicz chunki
            chunks = self._calculate_chunk_params(limit, available_workers, offset)
            
            # Przygotuj zadania dla Celery
            tasks = []
            
            logger.info("💰 Uruchamianie zadań synchronizacji transakcji w Celery")
            for chunk_limit, chunk_offset in chunks:
                task_result = sync_transactions_task.apply_async(
                    kwargs={
                        'limit': chunk_limit,
                        'offset': chunk_offset,
                        'test_mode': self.test_mode
                    },
                    queue='transaction_queue'
                )
                tasks.append(task_result)
                logger.info(f"📤 Wysłano zadanie transakcji: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
            
            # Czekaj na zakończenie wszystkich zadań
            success = await self._wait_for_celery_tasks(tasks, "transactions")
            
            if success:
                self.workflow_status['transactions_completed'] = True
                logger.info("=== SYNCHRONIZACJA TRANSAKCJI ZAKOŃCZONA POMYŚLNIE ===")
            else:
                logger.error("=== SYNCHRONIZACJA TRANSAKCJI NIEUDANA ===")
            
            return success
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji transakcji: {e}")
            logger.error(traceback.format_exc())
            return False
    
    async def _run_parallel_analysis(self, limit: int = 50, offset: int = 0) -> tuple[bool, bool]:
        """
        Uruchamia równolegle analizę fundamentalną i techniczną z wykorzystaniem Celery.
        Dzieli zadania między wolnych workerów na podstawie dostępności.
        
        Returns:
            tuple[bool, bool]: (sukces_fundamental, sukces_technical)
        """
        logger.info("=== ROZPOCZĘCIE RÓWNOLEGŁYCH ANALIZ (FUNDAMENTAL + TECHNICAL) Z CELERY ===")
        
        # Pobierz liczbę dostępnych workerów
        available_workers = self._get_available_celery_workers()
        
        # Podziel dostępnych workerów po połowie między analizy
        workers_per_analysis = max(1, available_workers // 2)
        
        logger.info(f"👷 Przydzielono {workers_per_analysis} workerów dla każdej analizy")
        
        # Oblicz chunki dla obu analiz
        fundamental_chunks = self._calculate_chunk_params(limit, workers_per_analysis, offset)
        technical_chunks = self._calculate_chunk_params(limit, workers_per_analysis, offset)
        
        # Przygotuj zadania dla Celery
        fundamental_tasks = []
        technical_tasks = []
        
        # Uruchom zadania fundamentalne
        logger.info("📰 Uruchamianie zadań analizy fundamentalnej w Celery")
        for chunk_limit, chunk_offset in fundamental_chunks:
            task_result = sync_fundamental_analysis_task.apply_async(
                kwargs={
                    'limit': chunk_limit,
                    'offset': chunk_offset,
                    'test_mode': self.test_mode
                },
                queue='analysis_queue'
            )
            fundamental_tasks.append(task_result)
            logger.info(f"📤 Wysłano zadanie fundamentalne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
        
        # Uruchom zadania techniczne
        logger.info("📈 Uruchamianie zadań analizy technicznej w Celery")
        for chunk_limit, chunk_offset in technical_chunks:
            task_result = sync_technical_analysis_task.apply_async(
                kwargs={
                    'limit': chunk_limit,
                    'offset': chunk_offset,
                    'test_mode': self.test_mode
                },
                queue='analysis_queue'
            )
            technical_tasks.append(task_result)
            logger.info(f"📤 Wysłano zadanie techniczne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
        
        # Oczekuj na zakończenie wszystkich zadań fundamentalnych
        logger.info("⏳ Oczekiwanie na zadania fundamentalne...")
        fundamental_success = await self._wait_for_celery_tasks(fundamental_tasks, "fundamental_analysis")
        
        # Oczekuj na zakończenie wszystkich zadań technicznych
        logger.info("⏳ Oczekiwanie na zadania techniczne...")
        technical_success = await self._wait_for_celery_tasks(technical_tasks, "technical_analysis")
        
        # Oznacz jako ukończone w zależności od sukcesu
        if fundamental_success:
            self.workflow_status['fundamental_analysis_completed'] = True
        if technical_success:
            self.workflow_status['technical_analysis_completed'] = True
        
        logger.info(f"=== RÓWNOLEGŁE ANALIZY CELERY ZAKOŃCZONE: Fundamental={fundamental_success}, Technical={technical_success} ===")
        return fundamental_success, technical_success
    
    async def _run_parallel_llm_interpretations(self, limit: int = 50, offset: int = 0) -> tuple[bool, bool]:
        """
        Uruchamia równolegle interpretacje LLM z wykorzystaniem Celery.
        Dzieli zadania między wolnych workerów na podstawie dostępności.
        
        Returns:
            tuple[bool, bool]: (sukces_llm_fundamental, sukces_llm_technical)
        """
        logger.info("=== ROZPOCZĘCIE RÓWNOLEGŁYCH INTERPRETACJI LLM Z CELERY ===")
        
        # Pobierz liczbę dostępnych workerów
        available_workers = self._get_available_celery_workers()
        
        # Podziel dostępnych workerów po połowie między interpretacje
        workers_per_interpretation = max(1, available_workers // 2)
        
        logger.info(f"👷 Przydzielono {workers_per_interpretation} workerów dla każdej interpretacji LLM")
        
        # Oblicz chunki dla obu interpretacji
        fundamental_chunks = self._calculate_chunk_params(limit, workers_per_interpretation, offset)
        technical_chunks = self._calculate_chunk_params(limit, workers_per_interpretation, offset)
        
        # Przygotuj zadania dla Celery
        fundamental_tasks = []
        technical_tasks = []
        
        # Uruchom zadania interpretacji fundamentalnej LLM
        logger.info("🤖 Uruchamianie zadań interpretacji LLM fundamentalnej w Celery")
        for chunk_limit, chunk_offset in fundamental_chunks:
            task_result = sync_llm_fundamental_interpretation_task.apply_async(
                kwargs={
                    'limit': chunk_limit,
                    'offset': chunk_offset,
                    'test_mode': self.test_mode
                },
                queue='llm_queue'
            )
            fundamental_tasks.append(task_result)
            logger.info(f"📤 Wysłano zadanie LLM fundamentalne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
        
        # Uruchom zadania interpretacji technicznej LLM
        logger.info("🤖 Uruchamianie zadań interpretacji LLM technicznej w Celery")
        for chunk_limit, chunk_offset in technical_chunks:
            task_result = sync_llm_technical_interpretation_task.apply_async(
                kwargs={
                    'limit': chunk_limit,
                    'offset': chunk_offset,
                    'test_mode': self.test_mode
                },
                queue='llm_queue'
            )
            technical_tasks.append(task_result)
            logger.info(f"📤 Wysłano zadanie LLM techniczne: task_id={task_result.id}, limit={chunk_limit}, offset={chunk_offset}")
        
        # Oczekuj na zakończenie zadań interpretacji fundamentalnej LLM
        logger.info("⏳ Oczekiwanie na zadania LLM fundamentalne...")
        llm_fundamental_success = await self._wait_for_celery_tasks(fundamental_tasks, "llm_fundamental_interpretation")
        
        # Oczekuj na zakończenie zadań interpretacji technicznej LLM
        logger.info("⏳ Oczekiwanie na zadania LLM techniczne...")
        llm_technical_success = await self._wait_for_celery_tasks(technical_tasks, "llm_technical_interpretation")
        
        # Oznacz jako ukończone w zależności od sukcesu
        if llm_fundamental_success:
            self.workflow_status['llm_fundamental_completed'] = True
        if llm_technical_success:
            self.workflow_status['llm_technical_completed'] = True
        
        logger.info(f"=== RÓWNOLEGŁE INTERPRETACJE LLM CELERY ZAKOŃCZONE: Fundamental={llm_fundamental_success}, Technical={llm_technical_success} ===")
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
