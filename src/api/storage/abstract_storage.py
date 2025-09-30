from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

class AbstractStorage(ABC):

    STORAGE = "ABSTRACT"

    def __init__(self):
        pass

    def upload_file(self, file_name: str, file_base64: str) -> str:
        """
        Upload pliku do storage
        
        Args:
            file_name (str): Nazwa pliku w storage (może zawierać ścieżkę względną)
            file_base64 (str): Base64 string do zapisania jako plik
            
        Returns:
            bool: True jeśli upload się powiódł, False w przeciwnym razie
        """
        pass

    def download_file(self, file_name: str) -> Optional[str]:
        """
        Pobierz plik z storage
        
        Args:
            file_name (str): Nazwa pliku w storage (może zawierać ścieżkę względną)
            
        Returns:
            Optional[str]: Base64 string z zawartością pliku lub None jeśli błąd
        """
        pass
    
    def delete_file(self, file_name: str) -> bool:
        """
        Usuń plik z storage
        
        Args:
            file_name (str): Nazwa pliku w storage do usunięcia (może zawierać ścieżkę względną)
            
        Returns:
            bool: True jeśli usunięcie się powiodło, False w przeciwnym razie
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Sprawdza stan zdrowotny storage'u.
        
        Returns:
            Dict[str, Any]: Wynik sprawdzenia z polami:
                - healthy: bool - czy storage jest zdrowy
                - storage_type: str - typ storage (MINIO, LOCAL)
                - message: str - wiadomość opisująca stan
                - details: Optional[Dict[str, Any]] - dodatkowe szczegóły
                - error: Optional[str] - błąd jeśli wystąpił
        """
        pass