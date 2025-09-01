#!/usr/bin/env python3
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor
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
    6. Transactions (po LlmGeneralAnalysisTransactionDecision)
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja kontrolera synchronizacji.
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.scheduler = AsyncIOScheduler()
        self.thread_executor = ThreadPoolExecutor(max_workers=4)
        
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
            'transactions_completed': False
        }
    
    def _init_sync_classes(self) -> None:
        """Inicjalizuje instancje wszystkich klas synchronizacyjnych."""
        try:
            self.exchanges = Exchanges(test_mode=self.test_mode)
            self.fundamental_analysis = FundamentalAnalysis(test_mode=self.test_mode)
            self.technical_analysis = TechnicalAnalysis(test_mode=self.test_mode)
            self.llm_fundamental = LlmFundamentalAnalysisInterpretation(test_mode=self.test_mode)
            self.llm_technical = LlmTechnicalAnalysisInterpretation(test_mode=self.test_mode)
            self.llm_general = LlmGeneralAnalysisTransactionDecision(test_mode=self.test_mode)
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
        Uruchamia równolegle analizę fundamentalną i techniczną.
        
        Returns:
            tuple[bool, bool]: (sukces_fundamental, sukces_technical)
        """
        logger.info("=== ROZPOCZĘCIE RÓWNOLEGŁYCH ANALIZ (FUNDAMENTAL + TECHNICAL) ===")
        
        # Uruchom równolegle obie analizy używając asyncio.gather
        results = await asyncio.gather(
            self._run_fundamental_analysis_sync(limit=limit, offset=offset),
            self._run_technical_analysis_sync(limit=limit, offset=offset),
            return_exceptions=True
        )
        
        fundamental_success = results[0] if not isinstance(results[0], Exception) else False
        technical_success = results[1] if not isinstance(results[1], Exception) else False
        
        if isinstance(results[0], Exception):
            logger.error(f"Wyjątek w analizie fundamentalnej: {results[0]}")
        if isinstance(results[1], Exception):
            logger.error(f"Wyjątek w analizie technicznej: {results[1]}")
        
        logger.info(f"=== RÓWNOLEGŁE ANALIZY ZAKOŃCZONE: Fundamental={fundamental_success}, Technical={technical_success} ===")
        return fundamental_success, technical_success
    
    async def _run_parallel_llm_interpretations(self, limit: int = 50, offset: int = 0) -> tuple[bool, bool]:
        """
        Uruchamia równolegle interpretacje LLM (po ukończeniu odpowiadających im analiz).
        
        Returns:
            tuple[bool, bool]: (sukces_llm_fundamental, sukces_llm_technical)
        """
        logger.info("=== ROZPOCZĘCIE RÓWNOLEGŁYCH INTERPRETACJI LLM ===")
        
        # Sprawdź warunki wstępne
        fundamental_ready = self.workflow_status['fundamental_analysis_completed']
        technical_ready = self.workflow_status['technical_analysis_completed']
        
        tasks = []
        if fundamental_ready:
            tasks.append(self._run_llm_fundamental_interpretation_sync(limit=limit, offset=offset))
        if technical_ready:
            tasks.append(self._run_llm_technical_interpretation_sync(limit=limit, offset=offset))
        
        if not tasks:
            logger.warning("Brak gotowych analiz do interpretacji LLM")
            return False, False
        
        # Uruchom dostępne interpretacje równolegle
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        llm_fundamental_success = False
        llm_technical_success = False
        
        # Mapuj wyniki na podstawie tego które zadania zostały uruchomione
        result_index = 0
        if fundamental_ready:
            llm_fundamental_success = results[result_index] if not isinstance(results[result_index], Exception) else False
            if isinstance(results[result_index], Exception):
                logger.error(f"Wyjątek w interpretacji LLM fundamentalnej: {results[result_index]}")
            result_index += 1
        
        if technical_ready:
            llm_technical_success = results[result_index] if not isinstance(results[result_index], Exception) else False
            if isinstance(results[result_index], Exception):
                logger.error(f"Wyjątek w interpretacji LLM technicznej: {results[result_index]}")
        
        logger.info(f"=== RÓWNOLEGŁE INTERPRETACJE LLM ZAKOŃCZONE: Fundamental={llm_fundamental_success}, Technical={llm_technical_success} ===")
        return llm_fundamental_success, llm_technical_success
    
    async def run_full_sync_workflow(self) -> None:
        """
        Uruchamia pełny workflow synchronizacji w określonej kolejności.
        
        Kolejność wykonania:
        1. Exchanges
        2. FundamentalAnalysis + TechnicalAnalysis (równolegle)
        3. LlmFundamentalAnalysisInterpretation + LlmTechnicalAnalysisInterpretation (równolegle)
        4. LlmGeneralAnalysisTransactionDecision
        5. Transactions
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
                
                # KROK 5: Transakcje (tylko jeśli decyzja generalna się udała)
                if llm_general_success:
                    logger.info("💰 KROK 5: Synchronizacja transakcji")
                    transactions_success = await self._run_transactions_sync()
                    
                    if transactions_success:
                        logger.info("✅ PEŁNY WORKFLOW ZAKOŃCZONY POMYŚLNIE")
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
            logger.info(f"💰 Transactions: {'✅' if self.workflow_status['transactions_completed'] else '❌'}")
            
        except Exception as e:
            logger.error(f"❌ Krytyczny błąd w workflow synchronizacji: {e}")
            logger.error(traceback.format_exc())
    
    def setup_cron_jobs(self) -> None:
        """Konfiguruje cronjobs dla automatycznego uruchamiania workflow."""
        try:
            # Cron job dla sobót o 6:00 rano
            self.scheduler.add_job(
                func=self.run_full_sync_workflow,
                trigger=CronTrigger(day_of_week='sat', hour=6, minute=0),
                id='weekly_sync_saturday',
                name='Tygodniowa synchronizacja - sobota 6:00',
                replace_existing=True
            )
            
            logger.info("✅ Skonfigurowano cron job: soboty o 6:00")
            
        except Exception as e:
            logger.error(f"Błąd podczas konfiguracji cron jobs: {e}")
            raise
    
    async def start(self) -> None:
        """
        Startuje kontroler synchronizacji.
        Uruchamia workflow od razu po starcie, a następnie konfiguruje cronjobs.
        """
        try:
            logger.info("🚀 URUCHAMIANIE SYNC CONTROLLER")
            
            # Konfiguruj cron jobs
            self.setup_cron_jobs()
            
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
