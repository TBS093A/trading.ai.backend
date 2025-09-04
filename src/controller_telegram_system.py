"""
Kontroler systemowy dla Telegram - obsługa synchronizacji i zarządzania systemem.

Ta klasa implementuje:
- Komendy synchronizacji (sync_all, sync_exchanges, itp.)
- Monitoring stanu systemu
- Health check komponentów
- Zarządzanie maintenance mode
- Czyszczenie cache

Autor: AI Assistant
"""

import asyncio
import logging
import traceback
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from telethon import Button

from .controller_base_telegram import BaseTelegramControllerDomain, UserPermissionLevel, RD
from ..main_controller_sync import SyncController

logger = logging.getLogger(__name__)


class SystemTelegramControllerDomain(BaseTelegramControllerDomain):
    """
    Kontroler systemowy dla zarządzania synchronizacją i monitoringu systemu.
    
    Zapewnia funkcjonalności:
    - Synchronizacja wszystkich komponentów
    - Health check systemu
    - Monitoring wydajności
    - Zarządzanie maintenance mode
    """
    
    DOMAIN = "system"
    
    def __init__(self, **kwargs):
        """
        Inicjalizacja kontrolera systemowego.
        
        Args:
            **kwargs: Parametry przekazywane do klasy bazowej
        """
        super().__init__(**kwargs)
        
        # Inicjalizacja SyncController
        self.sync_controller = SyncController(test_mode=self.test_mode)
        
        # Status maintenance mode
        self.maintenance_mode = False
        self.maintenance_message = "System jest w trybie konserwacji."
        
        # Cache dla health check
        self.health_cache = {}
        self.health_cache_ttl = 60  # 60 sekund
        
        # Status długotrwałych operacji
        self.running_operations = {}
    
    async def get_domain_specific_stats(self) -> Dict[str, Any]:
        """Zwraca statystyki specyficzne dla domeny systemowej."""
        return {
            "sync_operations": len(self.running_operations),
            "maintenance_mode": self.maintenance_mode,
            "health_checks_performed": len(self.health_cache),
            "last_full_sync": self.sync_controller.workflow_status.get('last_run', 'Never')
        }
    
    def _check_maintenance_mode(self, user_id: int) -> bool:
        """
        Sprawdza czy system jest w trybie maintenance i czy użytkownik może go ominąć.
        
        Args:
            user_id: ID użytkownika
            
        Returns:
            bool: True jeśli użytkownik może kontynuować
        """
        if not self.maintenance_mode:
            return True
        
        # Admini mogą ominąć maintenance mode
        return self.is_admin(user_id)
    
    async def _check_user_permissions_for_sync(self, user_id: int) -> bool:
        """
        Sprawdza uprawnienia użytkownika do synchronizacji.
        
        Args:
            user_id: ID użytkownika
            
        Returns:
            bool: True jeśli użytkownik ma uprawnienia
        """
        return await self.validate_permissions(user_id, UserPermissionLevel.ADMIN)
    
    # ===================
    # STATUS & HEALTH
    # ===================
    
    @RD.cmd("status", aliases=["ping", "health"])
    async def status_command(self, event):
        """
        Komenda sprawdzania statusu bota i systemu.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        await self.log_action(user.id, "status_check")
        
        # Sprawdź maintenance mode
        if not self._check_maintenance_mode(user.id):
            await event.respond(f"⚠️ **System w trybie konserwacji**\n\n{self.maintenance_message}")
            return
        
        try:
            # Basic system info
            uptime = datetime.now() - self.stats.get('start_time', datetime.now())
            
            status_text = "🟢 **System Status: ONLINE**\n\n"
            status_text += f"👤 **Użytkownik:** {user.first_name}\n"
            status_text += f"🆔 **User ID:** `{user.id}`\n"
            status_text += f"📊 **Domena:** `{self.DOMAIN}`\n"
            status_text += f"⏰ **Uptime:** {str(uptime).split('.')[0]}\n"
            status_text += f"🔄 **Aktywne operacje:** {len(self.running_operations)}\n"
            
            # Permissions info
            user_level = await self.get_user_permission_level(user.id)
            status_text += f"🔑 **Uprawnienia:** `{user_level}`\n"
            
            # Maintenance mode info
            maintenance_emoji = "🔧" if self.maintenance_mode else "✅"
            maintenance_status = "Włączony" if self.maintenance_mode else "Wyłączony"
            status_text += f"{maintenance_emoji} **Maintenance:** {maintenance_status}\n"
            
            # Database status
            if self.db:
                try:
                    await self.init_database()
                    status_text += "💾 **Baza danych:** ✅ Połączono\n"
                except:
                    status_text += "💾 **Baza danych:** ❌ Błąd połączenia\n"
            else:
                status_text += "💾 **Baza danych:** ⚠️ Nie zainicjalizowana\n"
            
            # Sync Controller status
            sync_status = "🟢 Gotowy" if self.sync_controller else "🔴 Niedostępny"
            status_text += f"🔄 **Sync Controller:** {sync_status}\n"
            
            # Admin-only info
            if await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
                status_text += f"\n👑 **Status Admin:**\n"
                status_text += f"📈 **Akcje wykonane:** {self.stats['actions_count']}\n"
                status_text += f"❌ **Błędy:** {self.stats['errors_count']}\n"
                status_text += f"👥 **Unikalnych użytkowników:** {len(self.stats['users_interacted'])}\n"
            
            buttons = [
                [Button.inline("🔄 Odśwież", b"sys:status_refresh")],
                [Button.inline("🏠 Menu główne", b"nav:home")]
            ]
            
            await event.respond(status_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "status_check")
            await event.respond(error_msg)
    
    @RD.cb(b"sys:status_refresh")
    async def status_refresh_callback(self, event):
        """Odświeża status systemu."""
        await self.status_command(event)
    
    # ===================
    # SYNC COMMANDS
    # ===================
    
    @RD.cmd("sync_all")
    async def sync_all_command(self, event):
        """
        Pełna synchronizacja systemu - uruchamia cały workflow.
        """
        user = await self.get_user_info(event)
        if not user:
            return
        
        # Sprawdź uprawnienia
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**\n\nTylko administratorzy mogą uruchamiać synchronizację.")
            return
        
        # Sprawdź maintenance mode
        if not self._check_maintenance_mode(user.id):
            await event.respond("⚠️ **System w trybie konserwacji**\n\nSynchronizacja niedostępna.")
            return
        
        await self.log_action(user.id, "sync_all_start")
        
        operation_id = f"sync_all_{user.id}_{int(datetime.now().timestamp())}"
        
        if operation_id in self.running_operations:
            await event.respond("⚠️ **Synchronizacja już trwa**\n\nPoczekaj na zakończenie bieżącej operacji.")
            return
        
        # Rozpocznij synchronizację w tle
        self.running_operations[operation_id] = {
            "type": "sync_all",
            "user_id": user.id,
            "start_time": datetime.now(),
            "status": "running"
        }
        
        # Wyślij wiadomość o rozpoczęciu
        loading_msg = await event.respond(
            self.create_loading_message("pełną synchronizację systemu"),
            buttons=[[Button.inline("📊 Status", f"sys:sync_status:{operation_id}".encode())]]
        )
        
        try:
            # Uruchom pełny workflow w tle
            await self.sync_controller.run_full_sync_workflow()
            
            # Zaktualizuj status
            self.running_operations[operation_id]["status"] = "completed"
            self.running_operations[operation_id]["end_time"] = datetime.now()
            
            duration = self.running_operations[operation_id]["end_time"] - self.running_operations[operation_id]["start_time"]
            
            success_msg = self.create_success_message(
                "Pełna synchronizacja",
                f"⏱️ Czas wykonania: {str(duration).split('.')[0]}\n"
                f"📊 Sprawdź logi dla szczegółów."
            )
            
            buttons = [
                [Button.inline("📊 Workflow Status", b"sys:workflow_status")],
                [Button.inline("🏠 Menu", b"nav:home")]
            ]
            
            await loading_msg.edit(success_msg, buttons=buttons)
            await self.log_action(user.id, "sync_all_completed", {"duration": str(duration)})
            
        except Exception as e:
            self.running_operations[operation_id]["status"] = "error"
            self.running_operations[operation_id]["error"] = str(e)
            self.running_operations[operation_id]["end_time"] = datetime.now()
            
            error_msg = self.create_error_message("pełnej synchronizacji", str(e))
            await loading_msg.edit(error_msg)
            await self.log_action(user.id, "sync_all_error", {"error": str(e)})
            
        finally:
            # Wyczyść operację po 5 minutach
            await asyncio.sleep(300)
            self.running_operations.pop(operation_id, None)
    
    @RD.cmd("sync_exchanges")
    async def sync_exchanges_command(self, event):
        """Synchronizacja assetów z giełd."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**\n\nTylko administratorzy mogą uruchamiać synchronizację.")
            return
        
        await self.log_action(user.id, "sync_exchanges_start")
        
        loading_msg = await event.respond(self.create_loading_message("synchronizację giełd"))
        
        try:
            success = await self.sync_controller._run_exchanges_sync()
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja giełd", 
                    "✅ Assety i giełdy zostały zsynchronizowane."
                )
            else:
                msg = self.create_error_message(
                    "synchronizacji giełd",
                    "Sprawdź logi dla szczegółów."
                )
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_exchanges_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_exchanges")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_technical_analysis")
    async def sync_technical_analysis_command(self, event):
        """Synchronizacja analiz technicznych."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_technical_analysis_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"synchronizację analiz technicznych (limit: {limit}, offset: {offset})")
        )
        
        try:
            success = await self.sync_controller._run_technical_analysis_sync(limit=limit, offset=offset)
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja analiz technicznych",
                    f"📊 Processed: {limit} records starting from {offset}"
                )
            else:
                msg = self.create_error_message("synchronizacji analiz technicznych")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_technical_analysis_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_technical_analysis")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_fundamental_analysis")
    async def sync_fundamental_analysis_command(self, event):
        """Synchronizacja analiz fundamentalnych."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_fundamental_analysis_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"synchronizację analiz fundamentalnych (limit: {limit}, offset: {offset})")
        )
        
        try:
            success = await self.sync_controller._run_fundamental_analysis_sync(limit=limit, offset=offset)
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja analiz fundamentalnych",
                    f"📊 Processed: {limit} records starting from {offset}"
                )
            else:
                msg = self.create_error_message("synchronizacji analiz fundamentalnych")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_fundamental_analysis_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_fundamental_analysis")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_analysis")
    async def sync_analysis_command(self, event):
        """Synchronizacja analiz (techniczna + fundamentalna równolegle)."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_analysis_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"równoległą synchronizację analiz (limit: {limit}, offset: {offset})")
        )
        
        try:
            fundamental_success, technical_success = await self.sync_controller._run_parallel_analysis(limit=limit, offset=offset)
            
            results_text = "📊 **Wyniki synchronizacji:**\n\n"
            results_text += f"📰 Fundamental: {'✅ Sukces' if fundamental_success else '❌ Błąd'}\n"
            results_text += f"📈 Technical: {'✅ Sukces' if technical_success else '❌ Błąd'}\n"
            results_text += f"📊 Processed: {limit} records starting from {offset}"
            
            if fundamental_success or technical_success:
                msg = self.create_success_message("Synchronizacja analiz", results_text)
            else:
                msg = self.create_error_message("synchronizacji analiz", results_text)
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_analysis_completed", {
                "fundamental_success": fundamental_success,
                "technical_success": technical_success
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_analysis")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_llm_technical_analysis_interpretation")
    async def sync_llm_technical_interpretation_command(self, event):
        """Synchronizacja interpretacji LLM analiz technicznych."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_llm_technical_interpretation_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"synchronizację interpretacji LLM technicznych (limit: {limit}, offset: {offset})")
        )
        
        try:
            success = await self.sync_controller._run_llm_technical_interpretation_sync(limit=limit, offset=offset)
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja interpretacji LLM technicznych",
                    f"🤖 Processed: {limit} records starting from {offset}"
                )
            else:
                msg = self.create_error_message("synchronizacji interpretacji LLM technicznych")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_llm_technical_interpretation_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_llm_technical_interpretation")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_llm_fundamental_analysis_interpretation")
    async def sync_llm_fundamental_interpretation_command(self, event):
        """Synchronizacja interpretacji LLM analiz fundamentalnych."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_llm_fundamental_interpretation_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"synchronizację interpretacji LLM fundamentalnych (limit: {limit}, offset: {offset})")
        )
        
        try:
            success = await self.sync_controller._run_llm_fundamental_interpretation_sync(limit=limit, offset=offset)
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja interpretacji LLM fundamentalnych",
                    f"🤖 Processed: {limit} records starting from {offset}"
                )
            else:
                msg = self.create_error_message("synchronizacji interpretacji LLM fundamentalnych")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_llm_fundamental_interpretation_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_llm_fundamental_interpretation")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_llm_analysis_interpretation")
    async def sync_llm_analysis_interpretation_command(self, event):
        """Synchronizacja interpretacji LLM (fundamentalnych + technicznych równolegle)."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_llm_analysis_interpretation_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"równoległą synchronizację interpretacji LLM (limit: {limit}, offset: {offset})")
        )
        
        try:
            fundamental_success, technical_success = await self.sync_controller._run_parallel_llm_interpretations(limit=limit, offset=offset)
            
            results_text = "🤖 **Wyniki synchronizacji LLM:**\n\n"
            results_text += f"📰 Fundamental: {'✅ Sukces' if fundamental_success else '❌ Błąd'}\n"
            results_text += f"📈 Technical: {'✅ Sukces' if technical_success else '❌ Błąd'}\n"
            results_text += f"📊 Processed: {limit} records starting from {offset}"
            
            if fundamental_success or technical_success:
                msg = self.create_success_message("Synchronizacja interpretacji LLM", results_text)
            else:
                msg = self.create_error_message("synchronizacji interpretacji LLM", results_text)
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_llm_analysis_interpretation_completed", {
                "fundamental_success": fundamental_success,
                "technical_success": technical_success
            })
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_llm_analysis_interpretation")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_general_llm_analysis_interpretation")
    async def sync_general_llm_interpretation_command(self, event):
        """Synchronizacja generalnych interpretacji LLM analiz."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        # Parse argumentów
        text_parts = event.raw_text.split()
        limit = 50
        offset = 0
        
        if len(text_parts) >= 2:
            try:
                limit = int(text_parts[1])
            except ValueError:
                pass
        
        if len(text_parts) >= 3:
            try:
                offset = int(text_parts[2])
            except ValueError:
                pass
        
        await self.log_action(user.id, "sync_general_llm_interpretation_start", {"limit": limit, "offset": offset})
        
        loading_msg = await event.respond(
            self.create_loading_message(f"synchronizację generalnych interpretacji LLM (limit: {limit}, offset: {offset})")
        )
        
        try:
            success = await self.sync_controller._run_llm_general_decision_sync(limit=limit, offset=offset)
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja generalnych interpretacji LLM",
                    f"🎯 Processed: {limit} records starting from {offset}"
                )
            else:
                msg = self.create_error_message("synchronizacji generalnych interpretacji LLM")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_general_llm_interpretation_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_general_llm_interpretation")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_transactions_wallets")
    async def sync_transactions_wallets_command(self, event):
        """Synchronizacja portfeli pod transakcje."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        await self.log_action(user.id, "sync_transactions_wallets_start")
        
        loading_msg = await event.respond(self.create_loading_message("synchronizację portfeli"))
        
        try:
            success = await self.sync_controller._run_transactions_wallets_sync()
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja portfeli",
                    "💼 Portfele zostały zsynchronizowane."
                )
            else:
                msg = self.create_error_message("synchronizacji portfeli")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_transactions_wallets_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_transactions_wallets")
            await loading_msg.edit(error_msg)
    
    @RD.cmd("sync_transactions")
    async def sync_transactions_command(self, event):
        """Synchronizacja transakcji."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        await self.log_action(user.id, "sync_transactions_start")
        
        loading_msg = await event.respond(self.create_loading_message("synchronizację transakcji"))
        
        try:
            success = await self.sync_controller._run_transactions_sync()
            
            if success:
                msg = self.create_success_message(
                    "Synchronizacja transakcji",
                    "💰 Transakcje zostały zsynchronizowane."
                )
            else:
                msg = self.create_error_message("synchronizacji transakcji")
            
            await loading_msg.edit(msg)
            await self.log_action(user.id, "sync_transactions_completed", {"success": success})
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "sync_transactions")
            await loading_msg.edit(error_msg)
    
    # ===================
    # HEALTH & MONITORING
    # ===================
    
    @RD.cmd("health")
    async def health_command(self, event):
        """Health check wszystkich komponentów systemu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self._check_user_permissions_for_sync(user.id):
            await event.respond("🔒 **Brak uprawnień**")
            return
        
        await self.log_action(user.id, "health_check")
        
        loading_msg = await event.respond(self.create_loading_message("health check komponentów"))
        
        try:
            health_results = await self._perform_health_check()
            
            health_text = "🏥 **Health Check Komponentów**\n\n"
            
            overall_healthy = True
            for component, status in health_results.items():
                emoji = "✅" if status["healthy"] else "❌"
                health_text += f"{emoji} **{component}:** {status['message']}\n"
                
                if not status["healthy"]:
                    overall_healthy = False
                    if "error" in status:
                        health_text += f"   ⚠️ {status['error']}\n"
            
            # Overall status
            overall_emoji = "🟢" if overall_healthy else "🔴"
            overall_status = "HEALTHY" if overall_healthy else "ISSUES DETECTED"
            health_text = f"{overall_emoji} **System Status: {overall_status}**\n\n" + health_text
            
            buttons = [
                [Button.inline("🔄 Odśwież", b"sys:health_refresh")],
                [Button.inline("📊 Szczegóły", b"sys:health_details")]
            ]
            
            await loading_msg.edit(health_text, buttons=buttons)
            
        except Exception as e:
            error_msg = await self.handle_database_error(e, user.id, "health_check")
            await loading_msg.edit(error_msg)
    
    async def _perform_health_check(self) -> Dict[str, Dict[str, Any]]:
        """
        Wykonuje health check wszystkich komponentów.
        
        Returns:
            Dict[str, Dict[str, Any]]: Wyniki health check
        """
        # Sprawdź cache
        cache_key = "health_check"
        if (cache_key in self.health_cache and 
            datetime.now() - self.health_cache[cache_key]["timestamp"] < timedelta(seconds=self.health_cache_ttl)):
            return self.health_cache[cache_key]["data"]
        
        results = {}
        
        # Database check
        try:
            if self.db:
                await self.init_database()
                pool = await self.db.get_db_pool()
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                
                results["Database"] = {
                    "healthy": True,
                    "message": "Połączenie OK",
                    "details": {"pool_size": pool.get_size()}
                }
            else:
                results["Database"] = {
                    "healthy": False,
                    "message": "Nie zainicjalizowana",
                    "error": "Database object is None"
                }
        except Exception as e:
            results["Database"] = {
                "healthy": False,
                "message": "Błąd połączenia",
                "error": str(e)
            }
        
        # Sync Controller check
        try:
            if self.sync_controller:
                results["Sync Controller"] = {
                    "healthy": True,
                    "message": "Dostępny",
                    "details": {
                        "active_operations": len(self.running_operations),
                        "workflow_status": self.sync_controller.workflow_status
                    }
                }
            else:
                results["Sync Controller"] = {
                    "healthy": False,
                    "message": "Niedostępny",
                    "error": "SyncController object is None"
                }
        except Exception as e:
            results["Sync Controller"] = {
                "healthy": False,
                "message": "Błąd",
                "error": str(e)
            }
        
        # Cache results
        self.health_cache[cache_key] = {
            "timestamp": datetime.now(),
            "data": results
        }
        
        return results
    
    @RD.cb(b"sys:health_refresh")
    async def health_refresh_callback(self, event):
        """Odświeża health check."""
        # Wyczyść cache
        self.health_cache.clear()
        await self.health_command(event)
    
    # ===================
    # MAINTENANCE & ADMIN
    # ===================
    
    @RD.cb(b"sys:maintenance")
    async def maintenance_toggle_callback(self, event):
        """Toggle maintenance mode."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień!", alert=True)
            return
        
        self.maintenance_mode = not self.maintenance_mode
        status = "włączony" if self.maintenance_mode else "wyłączony"
        
        msg = f"🔧 **Maintenance mode {status}**\n\n"
        if self.maintenance_mode:
            msg += "⚠️ System jest teraz w trybie konserwacji.\nTylko administratorzy mają dostęp do funkcji."
        else:
            msg += "✅ System wrócił do normalnej pracy.\nWszyscy użytkownicy mają dostęp do funkcji."
        
        await event.edit(msg)
        await self.log_action(user.id, "maintenance_mode_toggle", {"enabled": self.maintenance_mode})
    
    @RD.cb(b"sys:cache_clear")
    async def cache_clear_callback(self, event):
        """Czyści cache systemu."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.answer("🔒 Brak uprawnień!", alert=True)
            return
        
        # Wyczyść cache
        cleared_items = len(self.health_cache) + len(self.user_permissions_cache)
        self.health_cache.clear()
        self.user_permissions_cache.clear()
        
        msg = f"🗑️ **Cache wyczyszczony**\n\n"
        msg += f"✅ Usunięto {cleared_items} elementów z cache."
        
        await event.edit(msg)
        await self.log_action(user.id, "cache_clear", {"items_cleared": cleared_items})
    
    @RD.cmd("logs")
    async def logs_command(self, event):
        """Wyświetlanie logów (tylko dla adminów)."""
        user = await self.get_user_info(event)
        if not user:
            return
        
        if not await self.validate_permissions(user.id, UserPermissionLevel.ADMIN):
            await event.respond("🔒 **Brak uprawnień**\n\nTylko administratorzy mają dostęp do logów.")
            return
        
        # Parse poziomu logów
        text_parts = event.raw_text.split()
        log_level = "INFO"
        
        if len(text_parts) >= 2:
            log_level = text_parts[1].upper()
        
        await event.respond(
            "📋 **System logów**\n\n"
            f"🔍 Poziom: {log_level}\n\n"
            "⚠️ Funkcja logów będzie rozszerzona w przyszłej wersji.\n"
            "Na razie sprawdź pliki logów na serwerze:\n"
            "- `sync_controller.log`\n"
            "- Logi aplikacji w stdout/stderr"
        )
        
        await self.log_action(user.id, "logs_access", {"level": log_level})
