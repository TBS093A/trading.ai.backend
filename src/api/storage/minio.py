import os
import logging
import base64
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
    
    def upload_file(self, file_name: str, file_base64: str) -> bool:
        """
        Upload pliku do MinIO (zapis base64)
        
        Args:
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
            file_base64 (str, optional): Base64 string do zapisania jako plik
            
        Returns:
            bool: True jeśli upload się powiódł, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas uploadu
        """
        try:
            if file_base64 is not None:
                # Dekoduj base64 i upload do MinIO
                try:
                    file_content = base64.b64decode(file_base64)
                    
                    # Upload pliku do MinIO
                    self.client.put_object(
                        bucket_name=self.bucket_name,
                        object_name=file_name,
                        data=file_content,
                        length=len(file_content)
                    )
                    
                    logger.info(f"Pomyślnie zapisano base64 jako plik: {file_name}")
                    return True
                except Exception as e:
                    logger.error(f"Błąd podczas dekodowania base64: {str(e)}")
                    raise Exception(f"Błąd podczas dekodowania base64: {str(e)}")
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
            Exception: Gdy wystąpi błąd podczas pobierania
        """
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
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
            
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
            file_name (str): Nazwa pliku w MinIO (może zawierać ścieżkę względną w bucket)
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
