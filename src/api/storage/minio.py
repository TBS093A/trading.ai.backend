import os
import logging
import base64
import io
from typing import Optional, Dict, Any
from minio import Minio
from minio.error import S3Error
from .abstract_storage import AbstractStorage
import traceback

logger = logging.getLogger(__name__)


class MinIOStorage(AbstractStorage):
    """
    Implementacja storage MinIO dziedzicząca po AbstractStorage
    """
    
    STORAGE = "MINIO"
    
    def __init__(self, access_key: str = None, secret_key: str = None, endpoint: str = None, 
                 secure: bool = True, bucket_name: str = "images", is_enabled: bool = False):
        """
        Inicjalizacja MinIO Storage
        
        Args:
            access_key (str): Klucz dostępu do MinIO
            secret_key (str): Klucz tajny do MinIO
            endpoint (str): Adres endpoint'u MinIO
            secure (bool): Czy używać secure connection (jeśli True, używaj https)
            bucket_name (str): Nazwa bucket'a w MinIO (domyślnie "images")
            is_enabled (bool): Czy storage jest włączony
        """
        super().__init__()
        
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint
        self.secure = secure
        self.bucket_name = bucket_name
        self.is_enabled = is_enabled
        
        # Jeśli storage jest wyłączony, nie inicjalizuj klienta
        if not self.is_enabled:
            logger.info("MinIOStorage jest wyłączony - pomijam inicjalizację klienta")
            self.client = None
            return
        
        # Walidacja wymaganych parametrów
        if not all([self.access_key, self.secret_key, self.endpoint]):
            logger.warning("Brak wymaganych parametrów MinIO - wyłączam storage")
            self.is_enabled = False
            self.client = None
            return
        
        # Inicjalizacja klienta MinIO
        try:
            self.client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure
            )
            
            # Sprawdź czy bucket istnieje, jeśli nie - utwórz go
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Utworzono bucket: {self.bucket_name}")
            else:
                logger.info(f"Bucket {self.bucket_name} już istnieje")
                
        except Exception as e:
            logger.error(f"Błąd podczas inicjalizacji MinIO: {str(e)}")
            self.is_enabled = False
            self.client = None
    
    def upload_file(self, file_name: str, file_base64: str) -> bool:
        """
        Upload pliku do MinIO (zapis base64)
        
        Args:
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
            file_base64 (str, optional): Base64 string do zapisania jako plik
            
        Returns:
            bool: True jeśli upload się powiódł, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas uploadu lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("MinIOStorage jest wyłączony")
            
        try:
            if file_base64 is not None:
                # Dekoduj base64 i upload do MinIO
                try:
                    file_content = base64.b64decode(file_base64)
                    
                    # Zawinięcie bajtów w BytesIO, aby utworzyć obiekt file-like
                    file_stream = io.BytesIO(file_content)
                    
                    # Upload pliku do MinIO
                    self.client.put_object(
                        bucket_name=self.bucket_name,
                        object_name=file_name,
                        data=file_stream,
                        length=len(file_content)
                    )
                    
                    logger.info(f"Pomyślnie zapisano base64 jako plik: {file_name}")
                    return True
                except Exception as e:
                    logger.error(f"Błąd podczas uploadu do MinIO: {str(e)}")
                    raise Exception(f"Błąd podczas uploadu do MinIO: {str(e)}")
            else:
                raise ValueError("Musi być podany parametr file_base64")
            
        except S3Error as e:
            logger.error(f"Błąd S3 podczas uploadu pliku {file_name}: {str(e)}")
            raise Exception(f"Błąd S3 podczas uploadu: {str(e)}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas uploadu pliku {file_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas uploadu pliku: {str(e)}")
    
    def download_file(self, file_name: str) -> Optional[str]:
        """
        Pobierz plik z MinIO i zwróć jako base64 string
        
        Args:
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
            
        Returns:
            Optional[str]: Base64 string z zawartością pliku lub None jeśli błąd
            
        Raises:
            Exception: Gdy wystąpi błąd podczas pobierania lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("MinIOStorage jest wyłączony")
        try:
            # Pobierz plik z MinIO jako bytes
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=file_name
            )
            
            # Wczytaj zawartość pliku
            file_content = response.read()
            response.close()
            response.release_conn()
            
            # Przekonwertuj na base64
            base64_content = base64.b64encode(file_content).decode('utf-8')
            
            logger.info(f"Pomyślnie wczytano plik jako base64: {file_name}")
            return base64_content
            
        except S3Error as e:
            if "NoSuchKey" in str(e):
                logger.error(f"Plik {file_name} nie istnieje w MinIO")
                return None
            else:
                logger.error(f"Błąd S3 podczas pobierania pliku {file_name}: {str(e)}")
                raise Exception(f"Błąd S3 podczas pobierania: {str(e)}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas pobierania pliku {file_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas pobierania pliku: {str(e)}")
    
    def delete_file(self, file_name: str) -> bool:
        """
        Usuń plik z MinIO
        
        Args:
            file_name (str): Nazwa pliku w MinIO do usunięcia (może zawierać ścieżkę względną w bucket)
            
        Returns:
            bool: True jeśli usunięcie się powiodło, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas usuwania lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("MinIOStorage jest wyłączony")
        try:
            # Usuń plik z MinIO
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=file_name
            )
            
            logger.info(f"Pomyślnie usunięto plik: {file_name}")
            return True
            
        except S3Error as e:
            if "NoSuchKey" in str(e):
                logger.warning(f"Plik {file_name} nie istnieje w MinIO")
                return False
            else:
                logger.error(f"Błąd S3 podczas usuwania pliku {file_name}: {str(e)}")
                raise Exception(f"Błąd S3 podczas usuwania: {str(e)}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas usuwania pliku {file_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas usuwania pliku: {str(e)}")
    
    def file_exists(self, file_name: str) -> bool:
        """
        Sprawdź czy plik istnieje w MinIO
        
        Args:
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
            
        Returns:
            bool: True jeśli plik istnieje, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas sprawdzania lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("MinIOStorage jest wyłączony")
        try:
            # Sprawdź czy obiekt istnieje
            self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=file_name
            )
            return True
        except S3Error as e:
            if "NoSuchKey" in str(e):
                return False
            else:
                logger.error(f"Błąd podczas sprawdzania istnienia pliku {file_name}: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania istnienia pliku {file_name}: {str(e)}")
            return False
    
    def get_file_url(self, file_name: str, expires: int = 3600) -> Optional[str]:
        """
        Pobierz URL do pliku w MinIO (presigned URL)
        
        Args:
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
            expires (int): Czas wygaśnięcia URL w sekundach (domyślnie 1 godzina)
            
        Returns:
            Optional[str]: URL do pliku lub None jeśli błąd
            
        Raises:
            Exception: Gdy wystąpi błąd podczas generowania URL lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("MinIOStorage jest wyłączony")
        try:
            # Generuj presigned URL
            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=file_name,
                expires=expires
            )
            return url
        except Exception as e:
            logger.error(f"Błąd podczas generowania URL dla pliku {file_name}: {str(e)}")
            return None

    async def health_check(self) -> Dict[str, Any]:
        """
        Sprawdza stan zdrowotny MinIO storage.
        
        Returns:
            Dict[str, Any]: Wynik sprawdzenia MinIO storage
        """
        try:
            # Sprawdź czy storage jest włączony
            if not self.is_enabled:
                return {
                    "healthy": False,
                    "storage_type": self.STORAGE,
                    "message": "MinIO storage jest wyłączony",
                    "details": {
                        "is_enabled": self.is_enabled,
                        "reason": "Storage disabled in configuration"
                    },
                    "error": None
                }
            
            # Sprawdź czy klient jest zainicjalizowany
            if not self.client:
                return {
                    "healthy": False,
                    "storage_type": self.STORAGE,
                    "message": "MinIO client nie jest zainicjalizowany",
                    "details": {
                        "is_enabled": self.is_enabled,
                        "client_initialized": False
                    },
                    "error": "Missing configuration parameters"
                }
            
            # Test połączenia z MinIO - sprawdź czy bucket istnieje
            bucket_exists = self.client.bucket_exists(self.bucket_name)
            
            if not bucket_exists:
                # Spróbuj utworzyć bucket
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Utworzono bucket: {self.bucket_name}")
                bucket_created = True
            else:
                bucket_created = False
            
            # Test operacji - spróbuj wykonać test upload/download/delete
            test_operations = await self._test_minio_operations()
            
            # Pobierz informacje o bucket
            bucket_info = self._get_bucket_info()
            
            return {
                "healthy": True,
                "storage_type": self.STORAGE,
                "message": "MinIO storage dostępny i funkcjonalny",
                "details": {
                    "is_enabled": self.is_enabled,
                    "client_initialized": True,
                    "endpoint": self.endpoint,
                    "bucket_name": self.bucket_name,
                    "bucket_exists": True,
                    "bucket_created": bucket_created,
                    "secure_connection": self.secure,
                    "test_operations": test_operations,
                    "bucket_info": bucket_info
                },
                "error": None
            }
            
        except S3Error as e:
            logger.error(f"Błąd S3 podczas sprawdzania MinIO: {e}")
            return {
                "healthy": False,
                "storage_type": self.STORAGE,
                "message": "Błąd S3 podczas sprawdzania MinIO",
                "details": {
                    "is_enabled": self.is_enabled,
                    "endpoint": self.endpoint,
                    "bucket_name": self.bucket_name,
                    "error_code": getattr(e, 'code', 'Unknown')
                },
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania MinIO storage: {e}")
            return {
                "healthy": False,
                "storage_type": self.STORAGE,
                "message": "Błąd sprawdzania MinIO storage",
                "details": {
                    "is_enabled": self.is_enabled,
                    "client_initialized": self.client is not None
                },
                "error": str(e)
            }

    async def _test_minio_operations(self) -> Dict[str, str]:
        """
        Testuje podstawowe operacje MinIO (upload/download/delete).
        
        Returns:
            Dict[str, str]: Wyniki testów operacji
        """
        operations_results = {}
        test_file_name = "health_check_test.txt"
        test_content = "MinIO health check test content"
        test_base64 = base64.b64encode(test_content.encode()).decode()
        
        try:
            # Test upload
            upload_result = self.upload_file(test_file_name, test_base64)
            operations_results["upload"] = "OK" if upload_result else "FAILED"
            
            if upload_result:
                # Test download
                downloaded_content = self.download_file(test_file_name)
                if downloaded_content and downloaded_content == test_base64:
                    operations_results["download"] = "OK"
                else:
                    operations_results["download"] = "FAILED"
                
                # Test delete (cleanup)
                delete_result = self.delete_file(test_file_name)
                operations_results["delete"] = "OK" if delete_result else "FAILED"
            else:
                operations_results["download"] = "SKIPPED"
                operations_results["delete"] = "SKIPPED"
                
        except Exception as e:
            operations_results["error"] = str(e)
        
        return operations_results

    def _get_bucket_info(self) -> Dict[str, Any]:
        """
        Pobiera informacje o bucket MinIO.
        
        Returns:
            Dict[str, Any]: Informacje o bucket
        """
        try:
            # Pobierz podstawowe informacje o obiektach w bucket
            objects_count = 0
            total_size = 0
            
            # Policz obiekty (ograniczamy do 100 dla performance)
            objects = self.client.list_objects(self.bucket_name, recursive=True, max_keys=100)
            for obj in objects:
                objects_count += 1
                total_size += obj.size
                
            return {
                "objects_count": objects_count if objects_count < 100 else "100+",
                "total_size_bytes": total_size,
                "total_size_human": self._format_bytes(total_size)
            }
            
        except Exception as e:
            logger.warning(f"Nie można pobrać informacji o bucket: {e}")
            return {
                "objects_count": "unknown",
                "total_size_bytes": 0,
                "error": str(e)
            }

    def _format_bytes(self, bytes_size: int) -> str:
        """Formatuje rozmiar w bytach na human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB"
