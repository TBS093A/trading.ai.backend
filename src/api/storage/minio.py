import os
import logging
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
    
    def __init__(self, access_key: str, secret_key: str, endpoint: str, secure: bool, bucket_name: str = "images"):
        """
        Inicjalizacja MinIO Storage
        
        Args:
            bucket_name (str): Nazwa bucket'a w MinIO (domyślnie "images")
        """
        super().__init__()
        
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint
        self.secure = secure
        self.bucket_name = bucket_name
        
        # Walidacja wymaganych parametrów
        if not all([self.access_key, self.secret_key, self.endpoint]):
            raise ValueError("Brak wymaganych parametrów MinIO: access_key, secret_key, endpoint")
        
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
            raise Exception(f"Nie można połączyć się z MinIO: {str(e)}")
    
    def upload_file(self, file_path: str, file_name: str) -> bool:
        """
        Upload pliku do MinIO
        
        Args:
            file_path (str): Ścieżka do pliku lokalnego
            file_name (str): Nazwa pliku w MinIO
            
        Returns:
            bool: True jeśli upload się powiódł, False w przeciwnym razie
            
        Raises:
            FileNotFoundError: Gdy plik lokalny nie istnieje
            Exception: Gdy wystąpi błąd podczas uploadu
        """
        try:
            # Sprawdź czy plik lokalny istnieje
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Plik lokalny nie istnieje: {file_path}")
            
            # Upload pliku do MinIO
            self.client.fput_object(
                bucket_name=self.bucket_name,
                object_name=file_name,
                file_path=file_path
            )
            
            logger.info(f"Pomyślnie uploadowano plik: {file_path} -> {file_name}")
            return True
            
        except FileNotFoundError:
            logger.error(f"Plik lokalny nie istnieje: {file_path}")
            raise
        except S3Error as e:
            logger.error(f"Błąd S3 podczas uploadu pliku {file_path}: {str(e)}")
            raise Exception(f"Błąd S3 podczas uploadu: {str(e)}")
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas uploadu pliku {file_path}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas uploadu pliku: {str(e)}")
    
    def download_file(self, file_name: str, local_path: Optional[str] = None) -> Optional[str]:
        """
        Pobierz plik z MinIO
        
        Args:
            file_name (str): Nazwa pliku w MinIO
            local_path (str, optional): Ścieżka lokalna gdzie zapisać plik.
                                      Jeśli None, użyje file_name jako nazwy pliku lokalnego
            
        Returns:
            Optional[str]: Ścieżka do pobranego pliku lub None jeśli błąd
            
        Raises:
            Exception: Gdy wystąpi błąd podczas pobierania
        """
        try:
            # Jeśli nie podano local_path, użyj file_name jako nazwy pliku lokalnego
            if local_path is None:
                local_path = file_name
            
            # Pobierz plik z MinIO
            self.client.fget_object(
                bucket_name=self.bucket_name,
                object_name=file_name,
                file_path=local_path
            )
            
            logger.info(f"Pomyślnie pobrano plik: {file_name} -> {local_path}")
            return local_path
            
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
            file_name (str): Nazwa pliku w MinIO do usunięcia
            
        Returns:
            bool: True jeśli usunięcie się powiodło, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas usuwania
        """
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
            file_name (str): Nazwa pliku w MinIO
            
        Returns:
            bool: True jeśli plik istnieje, False w przeciwnym razie
        """
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
            file_name (str): Nazwa pliku w MinIO
            expires (int): Czas wygaśnięcia URL w sekundach (domyślnie 1 godzina)
            
        Returns:
            Optional[str]: URL do pliku lub None jeśli błąd
        """
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
