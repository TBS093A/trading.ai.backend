import os
import logging
import base64
from typing import Optional
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
            Exception: Gdy wystąpi błąd podczas uploadu
        """
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
            Exception: Gdy wystąpi błąd podczas pobierania
        """
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
            Exception: Gdy wystąpi błąd podczas usuwania
        """
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
        """
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
            Exception: Zawsze rzuca wyjątek o braku obsługi URL-i
        """
        raise Exception("LocalStorage nie obsługuje URL-i - ta funkcjonalność nie jest dostępna dla lokalnego storage") 