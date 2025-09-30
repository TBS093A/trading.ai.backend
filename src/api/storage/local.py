import os
import logging
import base64
from typing import Optional, Dict, Any
from .abstract_storage import AbstractStorage
import traceback

logger = logging.getLogger(__name__)


class LocalStorage(AbstractStorage):
    """
    Implementacja storage lokalnego dziedzicząca po AbstractStorage
    """
    
    STORAGE = "LOCAL"
    
    def __init__(self, is_enabled: bool = False, storage_path: str = "./local_storage"):
        """
        Inicjalizacja Local Storage
        
        Args:
            storage_path (str): Ścieżka do katalogu gdzie będą przechowywane pliki
        """
        super().__init__()

        self.is_enabled = is_enabled
        self.storage_path = storage_path
        
        # Utwórz katalog storage jeśli nie istnieje
        try:
            if not os.path.exists(self.storage_path):
                os.makedirs(self.storage_path, exist_ok=True)
                logger.info(f"Utworzono katalog storage: {self.storage_path}")
            else:
                logger.info(f"Katalog storage już istnieje: {self.storage_path}")
                
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia katalogu storage: {str(e)}")
            raise Exception(f"Nie można utworzyć katalogu storage: {str(e)}")
    
    def upload_file(self, file_name: str, file_base64: str) -> bool:
        """
        Upload pliku do lokalnego storage (zapis base64)
        
        Args:
            file_name (str): Nazwa pliku w storage (może zawierać ścieżkę względną)
            file_base64 (str, optional): Base64 string do zapisania jako plik
            
        Returns:
            bool: True jeśli upload się powiódł, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas uploadu lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("LocalStorage jest wyłączony")
            
        try:
            # Utwórz pełną ścieżkę docelową: storage_path + file_name (który może zawierać ścieżkę)
            destination_path = os.path.join(self.storage_path, file_name)
            
            # Utwórz katalog docelowy jeśli nie istnieje
            destination_dir = os.path.dirname(destination_path)
            if destination_dir and not os.path.exists(destination_dir):
                os.makedirs(destination_dir, exist_ok=True)
                logger.info(f"Utworzono katalog: {destination_dir}")
            
            if file_base64 is not None:
                # Zapisz base64 jako plik
                try:
                    file_content = base64.b64decode(file_base64)
                    with open(destination_path, 'wb') as dest_file:
                        dest_file.write(file_content)
                    logger.info(f"Pomyślnie zapisano base64 jako plik: {destination_path}")
                    return True
                except Exception as e:
                    logger.error(f"Błąd podczas dekodowania base64: {str(e)}")
                    raise Exception(f"Błąd podczas dekodowania base64: {str(e)}")
            else:
                raise ValueError("Musi być podany parametr file_base64")
            
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas zapisywania pliku: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas zapisywania pliku: {str(e)}")
    
    def download_file(self, file_name: str) -> Optional[str]:
        """
        Pobierz plik z lokalnego storage i zwróć jako base64 string
        
        Args:
            file_name (str): Nazwa pliku w storage (może zawierać ścieżkę względną)
            
        Returns:
            Optional[str]: Base64 string z zawartością pliku lub None jeśli błąd
            
        Raises:
            Exception: Gdy wystąpi błąd podczas pobierania lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("LocalStorage jest wyłączony")
            
        try:
            # Utwórz pełną ścieżkę: storage_path + file_name (który może zawierać ścieżkę)
            file_path = os.path.join(self.storage_path, file_name)
            
            # Sprawdź czy plik istnieje
            if not os.path.exists(file_path):
                logger.error(f"Plik {file_name} nie istnieje w storage")
                return None
            
            # Wczytaj plik i przekonwertuj na base64
            with open(file_path, 'rb') as file:
                file_content = file.read()
                base64_content = base64.b64encode(file_content).decode('utf-8')
            
            logger.info(f"Pomyślnie wczytano plik jako base64: {file_name}")
            return base64_content
            
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas wczytywania pliku {file_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas wczytywania pliku: {str(e)}")
    
    def delete_file(self, file_name: str) -> bool:
        """
        Usuń plik z lokalnego storage
        
        Args:
            file_name (str): Nazwa pliku w storage do usunięcia (może zawierać ścieżkę względną)
            
        Returns:
            bool: True jeśli usunięcie się powiodło, False w przeciwnym razie
            
        Raises:
            Exception: Gdy wystąpi błąd podczas usuwania lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("LocalStorage jest wyłączony")
            
        try:
            # Utwórz pełną ścieżkę: storage_path + file_name (który może zawierać ścieżkę)
            file_path = os.path.join(self.storage_path, file_name)
            
            # Sprawdź czy plik istnieje
            if not os.path.exists(file_path):
                logger.warning(f"Plik {file_name} nie istnieje w storage")
                return False
            
            # Usuń plik
            os.remove(file_path)
            
            logger.info(f"Pomyślnie usunięto plik: {file_name}")
            return True
            
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas usuwania pliku {file_name}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise Exception(f"Błąd podczas usuwania pliku: {str(e)}")
    
    def file_exists(self, file_name: str) -> bool:
        """
        Sprawdź czy plik istnieje w lokalnym storage
        
        Args:
            file_name (str): Nazwa pliku w storage (może zawierać ścieżkę względną)
            
        Returns:
            bool: True jeśli plik istnieje, False w przeciwnym razie
            
        Raises:
            Exception: Gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("LocalStorage jest wyłączony")
            
        try:
            # Utwórz pełną ścieżkę: storage_path + file_name (który może zawierać ścieżkę)
            file_path = os.path.join(self.storage_path, file_name)
            return os.path.exists(file_path)
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas sprawdzania istnienia pliku {file_name}: {str(e)}")
            return False
    
    def get_file_url(self, file_name: str, expires: int = 3600) -> Optional[str]:
        """
        Zwróć None - LocalStorage nie obsługuje URL-i
        
        Args:
            file_name (str): Nazwa pliku w storage (może zawierać ścieżkę względną)
            expires (int): Ignorowane w tej implementacji
            
        Returns:
            None: Zawsze zwraca None
            
        Raises:
            Exception: Zawsze rzuca wyjątek o braku obsługi URL-i lub gdy storage jest wyłączony
        """
        if not self.is_enabled:
            raise Exception("LocalStorage jest wyłączony")
            
        raise Exception("LocalStorage nie obsługuje URL-i - ta funkcjonalność nie jest dostępna dla lokalnego storage")

    async def health_check(self) -> Dict[str, Any]:
        """
        Sprawdza stan zdrowotny Local storage.
        
        Returns:
            Dict[str, Any]: Wynik sprawdzenia Local storage
        """
        try:
            # Sprawdź czy storage jest włączony
            if not self.is_enabled:
                return {
                    "healthy": False,
                    "storage_type": self.STORAGE,
                    "message": "Local storage jest wyłączony",
                    "details": {
                        "is_enabled": self.is_enabled,
                        "storage_path": self.storage_path,
                        "reason": "Storage disabled in configuration"
                    },
                    "error": None
                }
            
            # Sprawdź czy katalog storage istnieje i jest dostępny
            storage_info = self._get_storage_directory_info()
            
            if not storage_info["exists"]:
                return {
                    "healthy": False,
                    "storage_type": self.STORAGE,
                    "message": "Katalog storage nie istnieje",
                    "details": {
                        "is_enabled": self.is_enabled,
                        "storage_path": self.storage_path,
                        "directory_exists": False
                    },
                    "error": "Storage directory does not exist"
                }
            
            # Test operacji - spróbuj wykonać test upload/download/delete
            test_operations = await self._test_local_operations()
            
            return {
                "healthy": True,
                "storage_type": self.STORAGE,
                "message": "Local storage dostępny i funkcjonalny",
                "details": {
                    "is_enabled": self.is_enabled,
                    "storage_path": os.path.abspath(self.storage_path),
                    "directory_exists": True,
                    "test_operations": test_operations,
                    "storage_info": storage_info
                },
                "error": None
            }
            
        except PermissionError as e:
            logger.error(f"Błąd uprawnień podczas sprawdzania Local storage: {e}")
            return {
                "healthy": False,
                "storage_type": self.STORAGE,
                "message": "Błąd uprawnień do katalogu storage",
                "details": {
                    "is_enabled": self.is_enabled,
                    "storage_path": self.storage_path,
                    "directory_exists": os.path.exists(self.storage_path)
                },
                "error": f"Permission denied: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Błąd podczas sprawdzania Local storage: {e}")
            return {
                "healthy": False,
                "storage_type": self.STORAGE,
                "message": "Błąd sprawdzania Local storage",
                "details": {
                    "is_enabled": self.is_enabled,
                    "storage_path": self.storage_path,
                    "directory_exists": os.path.exists(self.storage_path) if hasattr(os, 'path') else False
                },
                "error": str(e)
            }

    async def _test_local_operations(self) -> Dict[str, str]:
        """
        Testuje podstawowe operacje Local storage (upload/download/delete).
        
        Returns:
            Dict[str, str]: Wyniki testów operacji
        """
        operations_results = {}
        test_file_name = "health_check_test.txt"
        test_content = "Local storage health check test content"
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

    def _get_storage_directory_info(self) -> Dict[str, Any]:
        """
        Pobiera informacje o katalogu storage.
        
        Returns:
            Dict[str, Any]: Informacje o katalogu storage
        """
        try:
            if not os.path.exists(self.storage_path):
                return {
                    "exists": False,
                    "is_directory": False,
                    "readable": False,
                    "writable": False,
                    "files_count": 0,
                    "total_size_bytes": 0
                }
            
            # Sprawdź czy to katalog
            is_directory = os.path.isdir(self.storage_path)
            
            # Sprawdź uprawnienia
            readable = os.access(self.storage_path, os.R_OK)
            writable = os.access(self.storage_path, os.W_OK)
            
            # Policz pliki i rozmiar (jeśli to katalog i mamy uprawnienia)
            files_count = 0
            total_size = 0
            
            if is_directory and readable:
                try:
                    for root, dirs, files in os.walk(self.storage_path):
                        for file in files:
                            files_count += 1
                            file_path = os.path.join(root, file)
                            try:
                                total_size += os.path.getsize(file_path)
                            except (OSError, IOError):
                                pass  # Skip files we can't access
                except (OSError, IOError):
                    pass  # Skip if we can't walk the directory
            
            return {
                "exists": True,
                "is_directory": is_directory,
                "readable": readable,
                "writable": writable,
                "files_count": files_count,
                "total_size_bytes": total_size,
                "total_size_human": self._format_bytes(total_size),
                "absolute_path": os.path.abspath(self.storage_path)
            }
            
        except Exception as e:
            logger.warning(f"Nie można pobrać informacji o katalogu storage: {e}")
            return {
                "exists": False,
                "error": str(e)
            }

    def _format_bytes(self, bytes_size: int) -> str:
        """Formatuje rozmiar w bytach na human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.1f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.1f} PB" 