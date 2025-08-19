import os
import logging
import traceback
import base64
import tiktoken
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

    MODELS = {
        "prompt": {
            "model": "gpt-4o",
            "temperature": 0.2,
            "limit": 30000,
            "max_tokens": 4096
        },
        "vision": {
            "model": "gpt-4o-mini",
            "temperature": 0.2,
            "limit": 100000,
            "max_tokens": 4096
        }
    }

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

    def calculate_tokens_from_prompt(self, prompt: str, model: str = "gpt-4o") -> int:
        """
        Oblicza liczbę tokenów w promptcie dla określonego modelu.
        
        Args:
            prompt: Tekst do analizy
            model: Model OpenAI do obliczania tokenów (domyślnie gpt-4o)
            
        Returns:
            int: Liczba tokenów w promptcie
        """
        try:
            encoding = tiktoken.encoding_for_model(model)
            token_count = len(encoding.encode(prompt))
            logger.debug(f"Obliczono {token_count} tokenów dla promptu (model: {model})")
            return token_count
        except Exception as e:
            logger.warning(f"Błąd podczas obliczania tokenów: {e}")
            # Fallback - przybliżone obliczenie (1 token ≈ 4 znaki)
            return len(prompt) // 4

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
                model=self.MODELS["vision"]["model"],
                messages=[
                    {"role": "system", "content": "This is a test message to check API status."},
                    {"role": "user", "content": "Hello"}
                ],
                max_tokens=5
            )
            
            if response and response.choices and len(response.choices) > 0:
                status_info = {
                    "available": True,
                    "model": self.MODELS["vision"]["model"],
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
                # Jeśli to już pełny URL z base64
                if image_data.startswith('data:image'):
                    return {"type": "image_url", "image_url": {"url": image_data}}
                
                # Sprawdź czy to czysty base64 string (z storage API)
                try:
                    # Spróbuj zdekodować jako base64 - jeśli się uda, to jest to base64
                    base64.b64decode(image_data, validate=True)
                    return {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    }
                except Exception:
                    # Jeśli dekodowanie base64 się nie udało, to prawdopodobnie ścieżka do pliku
                    if os.path.exists(image_data):
                        with open(image_data, 'rb') as image_file:
                            image_bytes = image_file.read()
                        base64_image = base64.b64encode(image_bytes).decode('utf-8')
                        return {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    else:
                        raise ImageProcessingError(f"Nie można przetworzyć danych obrazka: nie jest to base64 ani ścieżka do pliku")
            
            # Jeśli to bytes, konwertuj na base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            return {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
            }
        except ImageProcessingError:
            # Przepuść ImageProcessingError bez modyfikacji
            raise
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania obrazka: {e}", exc_info=True)
            raise ImageProcessingError(f"Nie udało się przetworzyć obrazka: {str(e)}")

    def __prepare_images_content(self, images: List[Union[str, bytes]]) -> List[Dict[str, Any]]:
        """
        Przygotowuje listę obrazków do wysłania do API OpenAI.
        
        Args:
            images: Lista danych obrazków (ścieżki do plików, base64 stringi lub bytes)
            
        Returns:
            Lista słowników z danymi obrazków w formacie wymaganym przez API
            
        Raises:
            ImageProcessingError: Gdy wystąpi błąd podczas przetwarzania obrazków
        """
        try:
            prepared_images = []
            for i, image_data in enumerate(images):
                try:
                    prepared_image = self.__prepare_image_content(image_data)
                    prepared_images.append(prepared_image)
                    logger.debug(f"Przygotowano obrazek {i+1}/{len(images)}")
                except ImageProcessingError as e:
                    logger.error(f"Błąd podczas przetwarzania obrazka {i+1}: {e}")
                    raise ImageProcessingError(f"Błąd podczas przetwarzania obrazka {i+1}: {e}")
            
            logger.info(f"Pomyślnie przygotowano {len(prepared_images)} obrazków")
            return prepared_images
            
        except Exception as e:
            logger.error(f"Błąd podczas przygotowywania obrazków: {e}", exc_info=True)
            raise ImageProcessingError(f"Nie udało się przygotować obrazków: {str(e)}")

    async def send_message(self, message: str, images: Optional[List[Union[str, bytes]]] = None) -> Dict[str, str]:
        """
        Wysyła wiadomość i opcjonalnie listę obrazków do API OpenAI.
        
        Args:
            message: Wiadomość do analizy
            images: Opcjonalna lista danych obrazków (ścieżki do plików, base64 stringi lub bytes)
            
        Returns:
            Słownik zawierający odpowiedź z API
            
        Raises:
            APIKeyMissingError: Gdy brak klucza API OpenAI
            QuotaExceededError: Gdy przekroczono limit zapytań API
            AnalysisError: Przy innych błędach API OpenAI
            ImageProcessingError: Gdy wystąpi błąd podczas przetwarzania obrazków
        """
        try:
            prompt = self.prompt.format(message=message)
            
            # Oblicz liczbę tokenów przed wysłaniem zapytania
            token_count = self.calculate_tokens_from_prompt(prompt, self.MODELS["prompt"]["model"])
            logger.info(f"Prompt zawiera {token_count} tokenów")
            
            # Dodaj obrazki jeśli są dostępne
            if images and len(images) > 0:
                try:
                    # Przygotuj zawartość wiadomości z obrazkami
                    content = [{"type": "text", "text": prompt}]
                    prepared_images = self.__prepare_images_content(images)
                    content.extend(prepared_images)
                    
                    # Dla obrazków używamy modelu vision, więc obliczamy tokeny dla gpt-4-vision
                    vision_token_count = self.calculate_tokens_from_prompt(prompt, self.MODELS["vision"]["model"])
                    logger.info(f"Prompt z {len(images)} obrazkami zawiera {vision_token_count} tokenów (model: {self.MODELS['vision']['model']})")
                    
                    logger.info(f"Wysyłanie zapytania z {len(images)} obrazkami do OpenAI API")
                    response = await self.__client.chat.completions.create(
                        model=self.MODELS["vision"]["model"],  # Model z obsługą wizji
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
                        temperature=self.MODELS["vision"]["temperature"],
                        max_tokens=self.MODELS["vision"]["max_tokens"],
                    )
                except ImageProcessingError as e:
                    logger.error(f"Nie udało się przetworzyć obrazków: {e}, traceback: {traceback.format_exc()}")
                    raise ImageProcessingError(f"Nie udało się przetworzyć obrazków: {e}, traceback: {traceback.format_exc()}")
            # Przetwarzanie bez obrazków
            else:
                logger.info("Wysyłanie zapytania do OpenAI API")
                response = await self.__client.chat.completions.create(
                    model=self.MODELS["prompt"]["model"],
                    messages=[
                        {"role": "system", "content": "Jesteś ekspertem w analizie technicznej rynków kryptowalut."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=self.MODELS["prompt"]["temperature"],
                    max_tokens=self.MODELS["prompt"]["max_tokens"],
                )

            result = {
                "message": response.choices[0].message.content.strip(),
                "input_tokens": token_count,
                "output_tokens": response.usage.completion_tokens if hasattr(response, 'usage') else None,
                "total_tokens": response.usage.total_tokens if hasattr(response, 'usage') else None,
                "images_processed": len(images) if images else 0
            }
            
            logger.info(f"Pomyślnie wygenerowano analizę techniczną za pomocą OpenAI. Tokeny: wejściowe={token_count}, wyjściowe={result['output_tokens']}, łącznie={result['total_tokens']}, obrazków przetworzonych={result['images_processed']}")
            return result

        except Exception as e:
            error_message = str(e)
            logger.error(f"Błąd API OpenAI podczas analizy: {e}, traceback: {traceback.format_exc()}", exc_info=True)
            
            if "429" in error_message or "quota" in error_message.lower() or "insufficient_quota" in error_message:
                raise QuotaExceededError(f"Przekroczono limit zapytań API OpenAI: {error_message}")
            
            raise AnalysisError(f"Błąd API OpenAI: {str(e)}, traceback: {traceback.format_exc()}")
