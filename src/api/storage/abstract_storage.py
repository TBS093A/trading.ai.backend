from typing import Optional

class AbstractStorage:

    STORAGE = "ABSTRACT"

    def __init__(self):
        pass

    def upload_file(self, file_path: str, file_name: str) -> bool:
        """
        Upload pliku do storage
        
        Args:
            file_path (str): Ścieżka do pliku lokalnego
            file_name (str): Nazwa pliku w storage
            
        Returns:
            bool: True jeśli upload się powiódł, False w przeciwnym razie
        """
        pass

    def download_file(self, file_name: str, local_path: Optional[str] = None) -> Optional[str]:
        """
        Pobierz plik z storage
        
        Args:
            file_name (str): Nazwa pliku w storage
            local_path (str, optional): Ścieżka lokalna gdzie zapisać plik
            
        Returns:
            Optional[str]: Ścieżka do pobranego pliku lub None jeśli błąd
        """
        pass
    
    def delete_file(self, file_name: str) -> bool:
        """
        Usuń plik z storage
        
        Args:
            file_name (str): Nazwa pliku w storage do usunięcia
            
        Returns:
            bool: True jeśli usunięcie się powiodło, False w przeciwnym razie
        """
        pass