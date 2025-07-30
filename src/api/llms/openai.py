import os
import logging
import traceback
import base64
from typing import Optional, Dict, Any, List, Union
from openai import AsyncOpenAI

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class OpenAIError(Exception):
    """Bazowa klasa wyjątków dla modułu OpenAI."""
    pass

class APIKeyMissingError(OpenAIError):
    """Wyjątek rzucany gdy brak klucza API OpenAI."""
    pass

class AnalysisError(OpenAIError):
    """Wyjątek rzucany przy błędach analizy."""
    pass

class QuotaExceededError(OpenAIError):
    """Wyjątek rzucany gdy przekroczono limit zapytań API."""
    pass

class ImageProcessingError(OpenAIError):
    """Wyjątek rzucany przy błędach przetwarzania obrazka."""
    pass

class OpenaiAPI:
    def __init__(self, api_key: str, prompt: str = "{message}"):
        """
        Inicjalizacja klienta OpenAI.

        Args:
            api_key: Klucz API OpenAI
            prompt: prompt do analizy - wymagane zmienne formatowane:
                {message} - wiadomość do analizy
        """
        if not api_key:
            logger.error("Brak klucza API OpenAI. Ustaw zmienną środowiskową OPENAI_API_KEY.")
            raise APIKeyMissingError("Brak klucza API OpenAI. Ustaw zmienną środowiskową OPENAI_API_KEY.")
        
        try:
            self.__client = AsyncOpenAI(api_key=api_key)
            self.prompt = prompt
        except Exception as e:
            logger.error(f"Błąd inicjalizacji klienta OpenAI: {e}", exc_info=True)
            raise APIKeyMissingError(f"Błąd inicjalizacji klienta OpenAI: {e}")

    async def check_api_status(self) -> Dict[str, Any]:
        """
        Sprawdza status API OpenAI.
        
        Returns:
            Słownik z informacjami o statusie API
            
        Raises:
            APIKeyMissingError: Gdy brak klucza API OpenAI
            QuotaExceededError: Gdy przekroczono limit zapytań API
        """
        try:
            logger.info("Sprawdzanie statusu API OpenAI")
            
            response = await self.__client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "This is a test message to check API status."},
                    {"role": "user", "content": "Hello"}
                ],
                max_tokens=5
            )
            
            if response and response.choices and len(response.choices) > 0:
                status_info = {
                    "available": True,
                    "model": "gpt-4o-mini",
                    "usage": vars(response.usage) if hasattr(response, "usage") else {},
                    "organization_id": getattr(response, "organization_id", None)
                }
                logger.info(f"API OpenAI jest dostępne, użycie tokenów: {status_info['usage']}")
                return status_info
            else:
                status_info = {"available": False, "error": "Nieprawidłowa odpowiedź API"}
                logger.warning("API OpenAI zwróciło nieprawidłową odpowiedź podczas testu")
                return status_info
        
        except Exception as e:
            error_message = str(e)
            status_info = {"available": False, "error": error_message}
            
            if "429" in error_message or "quota" in error_message.lower() or "insufficient_quota" in error_message:
                logger.error(f"Przekroczono limit zapytań API OpenAI: {e}")
                raise QuotaExceededError(f"Przekroczono limit zapytań API OpenAI: {error_message}")
            
            logger.error(f"Błąd podczas sprawdzania statusu API OpenAI: {e}", exc_info=True)
            return status_info

    def __prepare_image_content(self, image_data: Union[str, bytes]) -> Dict[str, str]:
        """
        Przygotowuje dane obrazka do wysłania do API OpenAI.
        
        Args:
            image_data: Dane obrazka jako string (base64) lub bytes
            
        Returns:
            Słownik z danymi obrazka w formacie wymaganym przez API
            
        Raises:
            ImageProcessingError: Gdy wystąpi błąd podczas przetwarzania obrazka
        """
        try:
            if isinstance(image_data, str):
                # Jeśli to już base64 string
                if image_data.startswith('data:image'):
                    return {"type": "image_url", "image_url": {"url": image_data}}
                # Jeśli to ścieżka do pliku
                with open(image_data, 'rb') as image_file:
                    image_data = image_file.read()
            
            # Konwersja bytes na base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            return {
                "type": "input_image",
                "image_url": f"data:image/jpeg;base64,{base64_image}"
            }
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania obrazka: {e}", exc_info=True)
            raise ImageProcessingError(f"Nie udało się przetworzyć obrazka: {str(e)}")

    async def send_message(self, message: str, image: Optional[Union[str, bytes]] = None) -> Dict[str, str]:
        """
        Wysyła wiadomość i opcjonalnie obrazek do API OpenAI.
        
        Args:
            message: Wiadomość do analizy
            image: Opcjonalne dane obrazka (ścieżka do pliku, base64 string lub bytes)
            
        Returns:
            Słownik zawierający odpowiedź z API
            
        Raises:
            APIKeyMissingError: Gdy brak klucza API OpenAI
            QuotaExceededError: Gdy przekroczono limit zapytań API
            AnalysisError: Przy innych błędach API OpenAI
            ImageProcessingError: Gdy wystąpi błąd podczas przetwarzania obrazka
        """
        try:
            prompt = self.prompt.format(message=message)
            
            # Dodaj obrazek jeśli jest dostępny
            if image:
                try:
                    # Przygotuj zawartość wiadomości z obrazkiem
                    content = [
                        {"type": "text", "text": prompt},
                        self.__prepare_image_content(image)
                    ]
                    
                    logger.info("Wysyłanie zapytania z obrazkiem do OpenAI API")
                    response = await self.__client.chat.completions.create(
                        model="gpt-4-vision-preview",  # Model z obsługą wizji
                        messages=[
                            {
                                "role": "system",
                                "content": "Jesteś ekspertem w analizie technicznej rynków kryptowalut."
                            },
                            {
                                "role": "user",
                                "content": content
                            }
                        ],
                        temperature=0.2,
                        max_tokens=4096,
                    )
                except ImageProcessingError as e:
                    logger.error(f"Nie udało się przetworzyć obrazka: {e}, traceback: {traceback.format_exc()}")
                    raise ImageProcessingError(f"Nie udało się przetworzyć obrazka: {e}, traceback: {traceback.format_exc()}")
            # Przetwarzanie bez obrazka
            else:
                logger.info("Wysyłanie zapytania do OpenAI API")
                response = await self.__client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "Jesteś ekspertem w analizie technicznej rynków kryptowalut."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=4096,
                )

            result = {
                "message": response.choices[0].message.content.strip()
            }
            
            logger.info("Pomyślnie wygenerowano analizę techniczną za pomocą OpenAI")
            return result

        except Exception as e:
            error_message = str(e)
            logger.error(f"Błąd API OpenAI podczas analizy: {e}, traceback: {traceback.format_exc()}", exc_info=True)
            
            if "429" in error_message or "quota" in error_message.lower() or "insufficient_quota" in error_message:
                raise QuotaExceededError(f"Przekroczono limit zapytań API OpenAI: {error_message}")
            
            raise AnalysisError(f"Błąd API OpenAI: {str(e)}, traceback: {traceback.format_exc()}")
