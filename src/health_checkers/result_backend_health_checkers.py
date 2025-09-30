"""
Strategy Design Pattern dla sprawdzania Celery Result Backend Health.

Implementuje różne strategie sprawdzania result backends:
- Redis  
- RPC (in-memory)
- Database (PostgreSQL, MySQL, etc.)

Autor: AI Assistant
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class AbstractResultBackendHealthChecker(ABC):
    """
    Abstrakcyjna klasa bazowa dla sprawdzania stanu Celery Result Backend.
    
    Implementuje Strategy Pattern - każdy typ result backend ma swoją strategię.
    """
    
    def __init__(self, backend_url: str):
        """
        Inicjalizacja health checker'a.
        
        Args:
            backend_url: URL result backend (np. "redis://user:pass@host:port/db")
        """
        self.backend_url = backend_url
        self.parsed_url = urlparse(backend_url) if backend_url else None
    
    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan result backend.
        
        Returns:
            Dict[str, Any]: Wynik sprawdzenia z polami:
                - healthy: bool
                - message: str
                - details: Optional[Dict[str, Any]]
                - error: Optional[str]
        """
        pass
    
    def _extract_connection_info(self) -> Dict[str, Any]:
        """Wyciąga informacje o połączeniu z URL."""
        if not self.parsed_url:
            return {"raw_url": self.backend_url}
        
        return {
            "scheme": self.parsed_url.scheme,
            "hostname": self.parsed_url.hostname,
            "port": self.parsed_url.port,
            "username": self.parsed_url.username,
            "path": self.parsed_url.path
        }


class RedisResultBackendHealthChecker(AbstractResultBackendHealthChecker):
    """Health checker dla Redis result backend."""
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan Redis result backend poprzez połączenie Redis.
        """
        try:
            # Sprawdź czy to prawidłowy URL Redis
            if not self._is_redis_url():
                return {
                    "healthy": False,
                    "message": "Nieprawidłowy URL Redis",
                    "error": f"URL nie jest rozpoznany jako Redis: {self.parsed_url.scheme if self.parsed_url else 'None'}",
                    "details": self._extract_connection_info()
                }
            
            # Próba połączenia z Redis
            connection_result = await self._test_redis_connection()
            
            if connection_result["connected"]:
                return {
                    "healthy": True,
                    "message": "Redis result backend dostępny",
                    "details": {
                        **self._extract_connection_info(),
                        "connection_test": "passed",
                        "backend_type": "Redis",
                        "redis_info": connection_result.get("info", {}),
                        "test_operations": connection_result.get("test_operations", {})
                    }
                }
            else:
                return {
                    "healthy": False,
                    "message": "Redis result backend niedostępny", 
                    "error": connection_result.get("error", "Unknown connection error"),
                    "details": self._extract_connection_info()
                }
                
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania Redis result backend: {e}")
            return {
                "healthy": False,
                "message": "Błąd sprawdzania Redis result backend",
                "error": str(e),
                "details": self._extract_connection_info()
            }
    
    def _is_redis_url(self) -> bool:
        """Sprawdza czy URL to Redis."""
        if not self.parsed_url:
            return False
        redis_schemes = ['redis', 'rediss', 'redis+socket']
        return self.parsed_url.scheme.lower() in redis_schemes
    
    async def _test_redis_connection(self) -> Dict[str, Any]:
        """
        Testuje połączenie z Redis i podstawowe operacje result backend.
        
        Returns:
            Dict z informacją o połączeniu i testach
        """
        try:
            # Import tylko gdy potrzebny
            import redis.asyncio as redis
            
            # Spróbuj nawiązać połączenie z timeoutem
            client = redis.from_url(
                self.backend_url,
                socket_connect_timeout=3,
                socket_timeout=3
            )
            
            # Test ping
            pong = await asyncio.wait_for(client.ping(), timeout=3.0)
            
            # Test podstawowych operacji result backend
            test_operations = await self._test_result_backend_operations(client)
            
            # Pobierz podstawowe info
            info = await client.info("server")
            
            await client.close()
            
            return {
                "connected": True,
                "message": "Redis connection and operations successful",
                "info": {
                    "redis_version": info.get("redis_version", "unknown"),
                    "used_memory_human": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", "unknown")
                },
                "test_operations": test_operations
            }
            
        except ImportError:
            # Fallback - sprawdzenie portu TCP
            return await self._test_tcp_connection()
        except asyncio.TimeoutError:
            return {
                "connected": False,
                "error": "Redis connection timeout (3s)"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": f"Redis connection failed: {str(e)}"
            }
    
    async def _test_result_backend_operations(self, client) -> Dict[str, Any]:
        """
        Testuje podstawowe operacje typowe dla Celery result backend.
        
        Args:
            client: Połączenie Redis
            
        Returns:
            Dict z wynikami testów operacji
        """
        operations_results = {}
        
        try:
            # Test SET/GET (podstawa result backend)
            test_key = "celery_health_test"
            test_value = "health_check_value"
            
            # SET
            await client.set(test_key, test_value, ex=10)  # 10s TTL
            operations_results["set"] = "OK"
            
            # GET
            retrieved = await client.get(test_key)
            if retrieved and retrieved.decode() == test_value:
                operations_results["get"] = "OK"
            else:
                operations_results["get"] = "FAILED"
            
            # DELETE (cleanup)
            await client.delete(test_key)
            operations_results["delete"] = "OK"
            
            # Test HSET/HGET (Celery używa hash'ów dla metadata)
            hash_key = "celery_health_test_hash"
            await client.hset(hash_key, "status", "SUCCESS")
            await client.hset(hash_key, "result", "test_result")
            await client.expire(hash_key, 10)  # 10s TTL
            
            hash_status = await client.hget(hash_key, "status")
            if hash_status and hash_status.decode() == "SUCCESS":
                operations_results["hash_operations"] = "OK"
            else:
                operations_results["hash_operations"] = "FAILED"
            
            # Cleanup hash
            await client.delete(hash_key)
            
        except Exception as e:
            operations_results["error"] = str(e)
        
        return operations_results
    
    async def _test_tcp_connection(self) -> Dict[str, Any]:
        """Fallback test TCP connection."""
        try:
            host = self.parsed_url.hostname or 'localhost'
            port = self.parsed_url.port or 6379
            
            # Test TCP połączenia
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            
            return {
                "connected": True,
                "message": "TCP connection successful (fallback test)"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": f"TCP connection failed: {str(e)}"
            }


class RPCResultBackendHealthChecker(AbstractResultBackendHealthChecker):
    """Health checker dla RPC (in-memory) result backend."""
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan RPC result backend.
        
        RPC backend jest in-memory więc głównie sprawdzamy czy URL jest prawidłowy.
        """
        try:
            # RPC backend to zwykle "rpc://"
            if not self._is_rpc_url():
                return {
                    "healthy": False,
                    "message": "Nieprawidłowy URL RPC",
                    "error": f"URL nie jest rozpoznany jako RPC: {self.backend_url}",
                    "details": {"raw_url": self.backend_url}
                }
            
            # RPC backend nie wymaga zewnętrznego połączenia - jest in-memory
            # Więc sprawdzamy głównie czy konfiguracja jest prawidłowa
            return {
                "healthy": True,
                "message": "RPC result backend skonfigurowany",
                "details": {
                    "backend_type": "RPC (in-memory)",
                    "url": self.backend_url,
                    "note": "RPC backend przechowuje wyniki w pamięci Celery worker'a",
                    "limitations": "Wyniki są tracone po restarcie worker'ów"
                }
            }
                
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania RPC result backend: {e}")
            return {
                "healthy": False,
                "message": "Błąd sprawdzania RPC result backend",
                "error": str(e),
                "details": {"raw_url": self.backend_url}
            }
    
    def _is_rpc_url(self) -> bool:
        """Sprawdza czy URL to RPC."""
        # RPC URL może być "rpc://", "rpc", lub podobne
        return (
            self.backend_url.lower().startswith('rpc://') or 
            self.backend_url.lower() == 'rpc'
        )


class DatabaseResultBackendHealthChecker(AbstractResultBackendHealthChecker):
    """Health checker dla Database result backend (PostgreSQL, MySQL, etc.)."""
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan Database result backend.
        """
        try:
            # Sprawdź czy to prawidłowy URL bazy danych
            if not self._is_database_url():
                return {
                    "healthy": False,
                    "message": "Nieprawidłowy URL bazy danych",
                    "error": f"URL nie jest rozpoznany jako baza danych: {self.parsed_url.scheme if self.parsed_url else 'None'}",
                    "details": self._extract_connection_info()
                }
            
            # Próba sprawdzenia połączenia (podstawowa implementacja)
            connection_result = await self._test_database_connection()
            
            if connection_result["connected"]:
                return {
                    "healthy": True,
                    "message": "Database result backend dostępny",
                    "details": {
                        **self._extract_connection_info(),
                        "backend_type": "Database",
                        "database_type": self.parsed_url.scheme.replace('db+', ''),
                        "connection_test": "passed"
                    }
                }
            else:
                return {
                    "healthy": False,
                    "message": "Database result backend niedostępny", 
                    "error": connection_result.get("error", "Unknown connection error"),
                    "details": self._extract_connection_info()
                }
                
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania Database result backend: {e}")
            return {
                "healthy": False,
                "message": "Błąd sprawdzania Database result backend",
                "error": str(e),
                "details": self._extract_connection_info()
            }
    
    def _is_database_url(self) -> bool:
        """Sprawdza czy URL to baza danych."""
        if not self.parsed_url:
            return False
        
        db_schemes = [
            'db+postgresql', 'db+mysql', 'db+sqlite',
            'postgresql', 'mysql', 'sqlite'
        ]
        return self.parsed_url.scheme.lower() in db_schemes
    
    async def _test_database_connection(self) -> Dict[str, Any]:
        """
        Testuje połączenie z bazą danych (podstawowa implementacja).
        
        Returns:
            Dict z informacją o połączeniu
        """
        try:
            # Podstawowy test TCP dla portu bazy danych
            host = self.parsed_url.hostname or 'localhost'
            
            # Domyślne porty dla różnych baz
            default_ports = {
                'postgresql': 5432,
                'db+postgresql': 5432,
                'mysql': 3306,
                'db+mysql': 3306
            }
            
            port = self.parsed_url.port or default_ports.get(self.parsed_url.scheme, 5432)
            
            # Test TCP połączenia
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
            
            return {
                "connected": True,
                "message": "Database TCP connection successful"
            }
            
        except Exception as e:
            return {
                "connected": False,
                "error": f"Database connection failed: {str(e)}"
            }


class ResultBackendHealthCheckerFactory:
    """
    Factory do tworzenia odpowiednich Health Checker'ów na podstawie URL result backend.
    """
    
    @staticmethod
    def create_checker(backend_url: str) -> AbstractResultBackendHealthChecker:
        """
        Tworzy odpowiedni health checker na podstawie URL result backend.
        
        Args:
            backend_url: URL result backend Celery
            
        Returns:
            AbstractResultBackendHealthChecker: Odpowiednia implementacja
            
        Raises:
            ValueError: Gdy scheme URL nie jest obsługiwany
        """
        if not backend_url:
            raise ValueError("Result backend URL nie może być pusty")
        
        # RPC backend
        if backend_url.lower().startswith('rpc') or backend_url.lower() == 'rpc':
            return RPCResultBackendHealthChecker(backend_url)
        
        parsed = urlparse(backend_url)
        scheme = parsed.scheme.lower()
        
        # Redis schemes
        if scheme in ['redis', 'rediss', 'redis+socket']:
            return RedisResultBackendHealthChecker(backend_url)
        
        # Database schemes
        elif scheme in ['db+postgresql', 'db+mysql', 'db+sqlite', 'postgresql', 'mysql', 'sqlite']:
            return DatabaseResultBackendHealthChecker(backend_url)
        
        else:
            raise ValueError(
                f"Nieobsługiwany scheme result backend: {scheme}. "
                f"Obsługiwane: rpc, redis, rediss, db+postgresql, db+mysql, db+sqlite"
            )
    
    @staticmethod
    def get_supported_schemes() -> Dict[str, str]:
        """
        Zwraca mapę obsługiwanych schemes.
        
        Returns:
            Dict[str, str]: Mapa scheme -> typ result backend
        """
        return {
            'rpc': 'RPC (in-memory)',
            'redis': 'Redis',
            'rediss': 'Redis (SSL)',
            'redis+socket': 'Redis (Unix Socket)',
            'db+postgresql': 'PostgreSQL Database',
            'db+mysql': 'MySQL Database', 
            'db+sqlite': 'SQLite Database',
            'postgresql': 'PostgreSQL Database',
            'mysql': 'MySQL Database',
            'sqlite': 'SQLite Database'
        }
