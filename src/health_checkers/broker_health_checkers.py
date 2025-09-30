"""
Strategy Design Pattern dla sprawdzania Celery Broker Health.

Implementuje różne strategie sprawdzania brokerów:
- RabbitMQ (AMQP)
- Redis

Autor: AI Assistant
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class AbstractBrokerHealthChecker(ABC):
    """
    Abstrakcyjna klasa bazowa dla sprawdzania stanu Celery Broker.
    
    Implementuje Strategy Pattern - każdy typ brokera ma swoją strategię.
    """
    
    def __init__(self, broker_url: str):
        """
        Inicjalizacja health checker'a.
        
        Args:
            broker_url: URL brokera (np. "pyamqp://user:pass@host:port//")
        """
        self.broker_url = broker_url
        self.parsed_url = urlparse(broker_url)
    
    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan brokera.
        
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
        return {
            "scheme": self.parsed_url.scheme,
            "hostname": self.parsed_url.hostname,
            "port": self.parsed_url.port,
            "username": self.parsed_url.username,
            "path": self.parsed_url.path
        }


class RabbitMQBrokerHealthChecker(AbstractBrokerHealthChecker):
    """Health checker dla RabbitMQ broker (AMQP)."""
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan RabbitMQ brokera poprzez próbę nawiązania połączenia AMQP.
        """
        try:
            # Sprawdź czy to prawidłowy URL RabbitMQ
            if not self._is_rabbitmq_url():
                return {
                    "healthy": False,
                    "message": "Nieprawidłowy URL RabbitMQ",
                    "error": f"URL nie jest rozpoznany jako RabbitMQ: {self.parsed_url.scheme}",
                    "details": self._extract_connection_info()
                }
            
            # Próba połączenia z RabbitMQ
            connection_result = await self._test_rabbitmq_connection()
            
            if connection_result["connected"]:
                return {
                    "healthy": True,
                    "message": "RabbitMQ dostępny",
                    "details": {
                        **self._extract_connection_info(),
                        "connection_test": "passed",
                        "broker_type": "RabbitMQ"
                    }
                }
            else:
                return {
                    "healthy": False,
                    "message": "RabbitMQ niedostępny",
                    "error": connection_result.get("error", "Unknown connection error"),
                    "details": self._extract_connection_info()
                }
                
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania RabbitMQ: {e}")
            return {
                "healthy": False,
                "message": "Błąd sprawdzania RabbitMQ",
                "error": str(e),
                "details": self._extract_connection_info()
            }
    
    def _is_rabbitmq_url(self) -> bool:
        """Sprawdza czy URL to RabbitMQ."""
        rabbitmq_schemes = ['amqp', 'amqps', 'pyamqp', 'librabbitmq']
        return self.parsed_url.scheme.lower() in rabbitmq_schemes
    
    async def _test_rabbitmq_connection(self) -> Dict[str, Any]:
        """
        Testuje połączenie z RabbitMQ.
        
        Returns:
            Dict z informacją o połączeniu
        """
        try:
            # Import tylko gdy potrzebny
            import aio_pika
            
            # Konwertuj URL na format aio_pika
            connection_url = self._convert_to_aio_pika_url()
            
            # Spróbuj nawiązać połączenie z timeoutem
            connection = await asyncio.wait_for(
                aio_pika.connect_robust(connection_url),
                timeout=5.0
            )
            
            # Test podstawowych operacji
            channel = await connection.channel()
            await channel.close()
            await connection.close()
            
            return {
                "connected": True,
                "message": "Connection successful"
            }
            
        except ImportError:
            # Fallback - sprawdzenie portu TCP
            return await self._test_tcp_connection()
        except asyncio.TimeoutError:
            return {
                "connected": False,
                "error": "Connection timeout (5s)"
            }
        except Exception as e:
            return {
                "connected": False,
                "error": f"Connection failed: {str(e)}"
            }
    
    def _convert_to_aio_pika_url(self) -> str:
        """Konwertuje pyamqp URL na aio_pika URL."""
        # pyamqp://user:pass@host:port// -> amqp://user:pass@host:port/
        if self.parsed_url.scheme == 'pyamqp':
            url = self.broker_url.replace('pyamqp://', 'amqp://')
            # Usuń podwójny slash na końcu jeśli istnieje
            if url.endswith('//'):
                url = url[:-1]
            return url
        return self.broker_url
    
    async def _test_tcp_connection(self) -> Dict[str, Any]:
        """Fallback test TCP connection."""
        try:
            host = self.parsed_url.hostname or 'localhost'
            port = self.parsed_url.port or 5672
            
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


class RedisBrokerHealthChecker(AbstractBrokerHealthChecker):
    """Health checker dla Redis broker."""
    
    async def check_health(self) -> Dict[str, Any]:
        """
        Sprawdza stan Redis brokera poprzez połączenie Redis.
        """
        try:
            # Sprawdź czy to prawidłowy URL Redis
            if not self._is_redis_url():
                return {
                    "healthy": False,
                    "message": "Nieprawidłowy URL Redis",
                    "error": f"URL nie jest rozpoznany jako Redis: {self.parsed_url.scheme}",
                    "details": self._extract_connection_info()
                }
            
            # Próba połączenia z Redis
            connection_result = await self._test_redis_connection()
            
            if connection_result["connected"]:
                return {
                    "healthy": True,
                    "message": "Redis dostępny",
                    "details": {
                        **self._extract_connection_info(),
                        "connection_test": "passed",
                        "broker_type": "Redis",
                        "redis_info": connection_result.get("info", {})
                    }
                }
            else:
                return {
                    "healthy": False,
                    "message": "Redis niedostępny", 
                    "error": connection_result.get("error", "Unknown connection error"),
                    "details": self._extract_connection_info()
                }
                
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania Redis: {e}")
            return {
                "healthy": False,
                "message": "Błąd sprawdzania Redis",
                "error": str(e),
                "details": self._extract_connection_info()
            }
    
    def _is_redis_url(self) -> bool:
        """Sprawdza czy URL to Redis."""
        redis_schemes = ['redis', 'rediss', 'redis+socket']
        return self.parsed_url.scheme.lower() in redis_schemes
    
    async def _test_redis_connection(self) -> Dict[str, Any]:
        """
        Testuje połączenie z Redis.
        
        Returns:
            Dict z informacją o połączeniu
        """
        try:
            # Import tylko gdy potrzebny
            import redis.asyncio as redis
            
            # Spróbuj nawiązać połączenie z timeoutem
            client = redis.from_url(
                self.broker_url,
                socket_connect_timeout=3,
                socket_timeout=3
            )
            
            # Test ping
            pong = await asyncio.wait_for(client.ping(), timeout=3.0)
            
            # Pobierz podstawowe info
            info = await client.info("server")
            
            await client.close()
            
            return {
                "connected": True,
                "message": "Redis ping successful",
                "info": {
                    "redis_version": info.get("redis_version", "unknown"),
                    "used_memory_human": info.get("used_memory_human", "unknown")
                }
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


class BrokerHealthCheckerFactory:
    """
    Factory do tworzenia odpowiednich Health Checker'ów na podstawie URL brokera.
    """
    
    @staticmethod
    def create_checker(broker_url: str) -> AbstractBrokerHealthChecker:
        """
        Tworzy odpowiedni health checker na podstawie URL brokera.
        
        Args:
            broker_url: URL brokera Celery
            
        Returns:
            AbstractBrokerHealthChecker: Odpowiednia implementacja
            
        Raises:
            ValueError: Gdy scheme URL nie jest obsługiwany
        """
        if not broker_url:
            raise ValueError("Broker URL nie może być pusty")
        
        parsed = urlparse(broker_url)
        scheme = parsed.scheme.lower()
        
        # RabbitMQ schemes
        if scheme in ['amqp', 'amqps', 'pyamqp', 'librabbitmq']:
            return RabbitMQBrokerHealthChecker(broker_url)
        
        # Redis schemes
        elif scheme in ['redis', 'rediss', 'redis+socket']:
            return RedisBrokerHealthChecker(broker_url)
        
        else:
            raise ValueError(
                f"Nieobsługiwany scheme brokera: {scheme}. "
                f"Obsługiwane: amqp, amqps, pyamqp, librabbitmq, redis, rediss"
            )
    
    @staticmethod
    def get_supported_schemes() -> Dict[str, str]:
        """
        Zwraca mapę obsługiwanych schemes.
        
        Returns:
            Dict[str, str]: Mapa scheme -> typ brokera
        """
        return {
            'amqp': 'RabbitMQ',
            'amqps': 'RabbitMQ (SSL)',
            'pyamqp': 'RabbitMQ (pyamqp)',
            'librabbitmq': 'RabbitMQ (librabbitmq)',
            'redis': 'Redis',
            'rediss': 'Redis (SSL)',
            'redis+socket': 'Redis (Unix Socket)'
        }
