import logging
import traceback
import json
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class LlmTechnicalAnalysisInterpretation:
    """
    Klasa odpowiedzialna za interpretację analiz technicznych za pomocą LLM'ów.
    Używa wzorca strategii do obsługi różnych LLM'ów.
    """
    
    TA_PROMPT = """
Twoim zadaniem jest przeprowadzić **interpretację techniczną danego aktywa** (np. spółki giełdowej lub kryptowaluty) na podstawie załączonych wykresów. Każdy wykres zawiera różne narzędzia analizy technicznej (np. formacje XABCD, MACD, RSI, OBV, zniesienia Fibonacciego, kanały trendu itp.).

---

📊 **Dane wejściowe:**
- Aktywo: {asset}/{quote}
- Zakres czasowy wykresów: {interval}
- Obrazki: [wiele wykresów – z różnych interwałów]
- Data analizy: {datetime.now()}
- Wykorzystane Patterny w liście obiektów JSON:

{json_patterns_list}

---

🎯 **Twoje cele:**
1. Zidentyfikuj formację XABCD na każdym wykresie i określ jej typ (np. Gartley, Bat, itd.)
2. Sprawdź, czy zniesienia Fibonacciego spełniają warunki danej formacji
3. Oceń znaczenie strefy PRZ (czy jesteśmy blisko niej, czy ją przebiliśmy)
4. Oceń stosunek ryzyka do zysku (SL / TP) dla każdej formacji
5. Przeanalizuj sygnały z MACD (cross, dywergencje), RSI (wykupienie/wyprzedanie) oraz OBV (potwierdzenie wolumenu)
6. Wydaj ogólną ocenę sytuacji technicznej (bycza / neutralna / niedźwiedzia)
7. Wypisz potencjalne scenariusze (jeśli wzrośnie / jeśli spadnie) oraz strefy decyzyjne
8. Oceń sygnały wskaźników technicznych (MACD, RSI, OBV):
   - Czy dają sygnał kupna, sprzedaży, czy są neutralne?
9. Zbadaj kierunek trendu (krótkoterminowy / średnioterminowy / długoterminowy).
10. Określ poziomy wsparcia i oporu – i czy są one testowane / przebijane.
11. Oceń jakość sygnałów (czy są zgodne, czy sprzeczne).
12. Wydaj ogólną ocenę techniczną:
    - 🟢 Sygnały wzrostowe
    - 🟡 Neutralne
    - 🔴 Sygnały spadkowe

---

🧾 **Wygeneruj odpowiedź w formacie JSON:**
```json
{{
  "asset": {asset},
  "quote": {quote},
  "trend_direction": {{
    "short_term": "wzrostowy",
    "mid_term": "neutralny",
    "long_term": "spadkowy"
  }},
  "identified_patterns": [
    {{
      "name": "Formacja harmoniczna Bearish Bat (1D)",
      "pattern_validity": true,
      "fib_levels": {{
        "AB_retracement": "0.618",
        "BC_retracement": "0.886",
        "CD_extension": "1.618"
      }}
    }}
  ],
  "indicators": {{
    "MACD": "sygnał kupna – przecięcie linii MACD powyżej sygnału",
    "RSI": "wartość 68 – blisko strefy wykupienia",
    "OBV": "rosnący – potwierdza popyt"
  }},
  "support_resistance": {{
    "support_levels": ["$52.30", "$50.10"],
    "resistance_levels": ["$56.80", "$59.00"],
    "price_position": "cena testuje opór $56.80"
  }},
  "prz_zone": {{
    "price_range": "188.5 – 190.3",
    "current_price_position": "tuż poniżej PRZ, możliwe odbicie"
  }},
  "risk_reward": {{
    "SL": "185.2",
    "TP1": "195.0",
    "TP2": "198.4",
    "RR_ratio": "3.1"
  }},
  "signal_quality": "Większość wskaźników wskazuje na kontynuację trendu wzrostowego, brak istotnych rozbieżności.",
  "technical_rating": "🟢 Sygnały wzrostowe",
  "suggested_focus": "Obserwuj przebicie oporu $56.80 – może nastąpić silny ruch w górę, potwierdzony przez OBV i MACD."
}}
```
"""

    CHART_INTERVALS = {
        #"1m": timedelta(minutes=1),
        #"15m": timedelta(minutes=15),
        #"30m": timedelta(minutes=30),
        #"1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
        "3d": timedelta(days=3),
        "1w": timedelta(weeks=1),
        "1M": timedelta(days=31),
        #"3M": timedelta(days=93),
        #"1Y": timedelta(days=365),
    }

    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy LlmTechnicalAnalysisInterpretation
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.llm_apis = self.api_facade.get_fabric().get_llm_apis()
        self.storage_apis = self.api_facade.get_fabric().get_storage_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
    
    def _extract_json_from_response(self, response_text: str) -> str:
        """
        Wyciąga JSON z odpowiedzi LLM'a.
        
        Args:
            response_text: Odpowiedź z LLM'a
            
        Returns:
            str: Wyciągnięty JSON lub oryginalny tekst jeśli nie znaleziono JSON
        """
        try:
            # Szukaj JSON w odpowiedzi
            start_marker = "```json"
            end_marker = "```"
            
            start_idx = response_text.find(start_marker)
            if start_idx != -1:
                start_idx += len(start_marker)
                end_idx = response_text.find(end_marker, start_idx)
                if end_idx != -1:
                    json_content = response_text[start_idx:end_idx].strip()
                    # Sprawdź czy to poprawny JSON
                    json.loads(json_content)
                    return json_content
            
            # Jeśli nie ma markerów, spróbuj znaleźć JSON w nawiasach klamrowych
            import re
            json_pattern = r'\{.*\}'
            matches = re.findall(json_pattern, response_text, re.DOTALL)
            if matches:
                for match in matches:
                    try:
                        json.loads(match)
                        return match
                    except json.JSONDecodeError:
                        continue
            
            # Jeśli nie znaleziono JSON, zwróć oryginalny tekst
            logger.warning("Nie znaleziono poprawnego JSON w odpowiedzi LLM'a")
            return response_text
            
        except Exception as e:
            logger.error(f"Błąd podczas wyciągania JSON z odpowiedzi: {e}")
            return response_text
    
    async def _get_all_assets(self) -> List[Dict[str, Any]]:
        """
        Pobiera wszystkie assety z bazy danych.
        
        Returns:
            List[Dict[str, Any]]: Lista assetów
        """
        try:
            assets_table = self.db.get_table("assets")
            assets = await assets_table.get_all(limit=1000, offset=0)
            logger.info(f"Pobrano {len(assets)} assetów z bazy danych")
            return assets
        except Exception as e:
            logger.error(f"Błąd podczas pobierania assetów: {e}", exc_info=True)
            return []
    
    async def _get_chart_images_without_interpretations(self, asset_id: int, interval: str) -> List[Dict[str, Any]]:
        """
        Pobiera obrazy wykresów bez interpretacji analizy technicznej dla danego asset i interwału.
        
        Args:
            asset_id: ID assetu
            interval: Interwał czasowy
            
        Returns:
            List[Dict[str, Any]]: Lista obrazów wykresów
        """
        try:
            chart_images_table = self.db.get_table("chart_images")
            chart_images = await chart_images_table.get_without_technical_analysis_interpretations_by_asset_and_interval(
                asset_id=asset_id, 
                interval=interval,
                limit=100,
                offset=0
            )
            logger.info(f"Pobrano {len(chart_images)} obrazów wykresów dla asset_id={asset_id}, interval={interval}")
            return chart_images
        except Exception as e:
            logger.error(f"Błąd podczas pobierania obrazów wykresów: {e}", exc_info=True)
            return []
    
    async def _download_chart_images(self, chart_images: List[Dict[str, Any]]) -> List[str]:
        """
        Pobiera obrazy wykresów ze storage.
        
        Args:
            chart_images: Lista obrazów wykresów z bazy danych
            
        Returns:
            List[str]: Lista base64 obrazów
        """
        downloaded_images = []
        
        for chart_image in chart_images:
            try:
                file_path = chart_image['image_file_path']
                storage_type = chart_image['storage']
                
                # Znajdź odpowiedni storage API
                for storage_api in self.storage_apis:
                    if storage_api.STORAGE == storage_type:
                        image_data = storage_api.download_file(file_path)
                        if image_data:
                            downloaded_images.append(image_data)
                            logger.debug(f"Pobrano obraz: {file_path}")
                        else:
                            logger.warning(f"Nie udało się pobrać obrazu: {file_path}")
                        break
                else:
                    logger.warning(f"Nie znaleziono storage API dla typu: {storage_type}")
                    
            except Exception as e:
                logger.error(f"Błąd podczas pobierania obrazu {chart_image.get('image_file_path', 'unknown')}: {e}")
                continue
        
        logger.info(f"Pobrano {len(downloaded_images)} obrazów z {len(chart_images)} dostępnych")
        return downloaded_images
    
    async def _get_harmonic_patterns_for_chart_images(self, chart_images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Pobiera wzorce harmoniczne dla wszystkich obrazów wykresów i usuwa duplikaty.
        
        Args:
            chart_images: Lista obrazów wykresów
            
        Returns:
            List[Dict[str, Any]]: Lista unikalnych wzorców harmonicznych
        """
        try:
            chart_images_harmonic_patterns_table = self.db.get_table("chart_images_harmonic_patterns")
            all_patterns = []
            seen_pattern_ids = set()
            
            for chart_image in chart_images:
                chart_image_id = chart_image['id']
                patterns = await chart_images_harmonic_patterns_table.get_by_chart_image_id(chart_image_id)
                
                for pattern in patterns:
                    pattern_id = pattern['id']
                    
                    # Sprawdź czy wzorzec już został dodany (usuń duplikaty)
                    if pattern_id not in seen_pattern_ids:
                        seen_pattern_ids.add(pattern_id)
                        
                        # Konwertuj wzorzec na format JSON
                        json_pattern = {
                            "id": pattern['id'],
                            "asset_id": pattern['asset_id'],
                            "asset": pattern['asset'],
                            "quote": pattern['quote'],
                            "x_point_timestamp": pattern['x_point_timestamp'],
                            "a_point_timestamp": pattern['a_point_timestamp'],
                            "b_point_timestamp": pattern['b_point_timestamp'],
                            "c_point_timestamp": pattern['c_point_timestamp'],
                            "d_point_timestamp": pattern['d_point_timestamp'],
                            "ta_object_json": pattern['ta_object_json']
                        }
                        all_patterns.append(json_pattern)
            
            logger.debug(f"Pobrano {len(all_patterns)} unikalnych wzorców harmonicznych z {len(chart_images)} obrazów wykresów")
            return all_patterns
        except Exception as e:
            logger.error(f"Błąd podczas pobierania wzorców harmonicznych: {e}", exc_info=True)
            return []
    
    async def _send_to_llm(self, prompt: str, images: List[str]) -> Optional[Dict[str, Any]]:
        """
        Wysyła prompt i obrazy do LLM'a.
        
        Args:
            prompt: Prompt do wysłania
            images: Lista obrazów w formacie base64
            
        Returns:
            Optional[Dict[str, Any]]: Odpowiedź z LLM'a lub None w przypadku błędu
        """
        try:
            for llm_api in self.llm_apis:
                try:
                    response = await llm_api.send_message(prompt, images)
                    logger.info(f"Otrzymano odpowiedź z LLM'a: {llm_api.__class__.__name__}")
                    return response
                except Exception as e:
                    logger.error(f"Błąd podczas wysyłania do LLM'a {llm_api.__class__.__name__}: {e}")
                    continue
            
            logger.error("Nie udało się wysłać do żadnego LLM'a")
            return None
            
        except Exception as e:
            logger.error(f"Błąd podczas wysyłania do LLM'a: {e}", exc_info=True)
            return None
    
    async def _save_interpretation(self, asset_id: int, technical_analysis_id: int, content: str) -> Optional[int]:
        """
        Zapisuje interpretację analizy technicznej do bazy danych.
        
        Args:
            asset_id: ID assetu
            technical_analysis_id: ID analizy technicznej
            content: Zawartość interpretacji w formacie JSON
            
        Returns:
            Optional[int]: ID zapisanej interpretacji lub None w przypadku błędu
        """
        try:
            technical_analysis_interpretation_table = self.db.get_table("technical_analysis_interpretation")
            timestamp = datetime.now().isoformat()
            
            interpretation_id = await technical_analysis_interpretation_table.create(
                asset_id=asset_id,
                technical_analysis_id=technical_analysis_id,
                timestamp=timestamp,
                content=content
            )
            
            if interpretation_id:
                logger.info(f"Zapisano interpretację analizy technicznej z ID: {interpretation_id}")
                
                # Utwórz powiązanie z obrazami wykresów
                await self._create_chart_image_interpretation_relations(interpretation_id, asset_id)
                
                return interpretation_id
            else:
                logger.error("Nie udało się zapisać interpretacji analizy technicznej")
                return None
                
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania interpretacji: {e}", exc_info=True)
            return None
    
    async def _create_chart_image_interpretation_relations(self, interpretation_id: int, asset_id: int) -> None:
        """
        Tworzy powiązania między interpretacją a obrazami wykresów.
        
        Args:
            interpretation_id: ID interpretacji
            asset_id: ID assetu
        """
        try:
            # Pobierz obrazy wykresów dla tego assetu
            chart_images_table = self.db.get_table("chart_images")
            chart_images = await chart_images_table.get_without_technical_analysis_interpretations_by_asset(
                asset_id=asset_id,
                limit=100,
                offset=0
            )
            
            # Utwórz powiązania
            technical_analysis_interpretation_chart_images_table = self.db.get_table("technical_analysis_interpretation_chart_images")
            
            for chart_image in chart_images:
                try:
                    await technical_analysis_interpretation_chart_images_table.create(
                        technical_analysis_interpretation_id=interpretation_id,
                        chart_image_id=chart_image['id']
                    )
                    logger.debug(f"Utworzono powiązanie interpretacja-obraz: {interpretation_id}-{chart_image['id']}")
                except Exception as e:
                    logger.error(f"Błąd podczas tworzenia powiązania: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia powiązań: {e}", exc_info=True)
    
    async def sync(self) -> None:
        """
        Główna metoda synchronizacji interpretacji analiz technicznych.
        Przetwarza wszystkie assety i interwały, generuje interpretacje za pomocą LLM'a.
        """
        try:
            logger.info("Rozpoczynam synchronizację interpretacji analiz technicznych")
            
            # 0. Pobierz wszystkie assety z bazy
            assets = await self._get_all_assets()
            if not assets:
                logger.warning("Brak assetów do przetworzenia")
                return
            
            logger.info(f"Znaleziono {len(assets)} assetów do przetworzenia")
            
            # Nested loop po assetach i interwałach
            for asset in assets:
                asset_id = asset['id']
                asset_name = asset['asset']
                quote_name = asset['quote']
                
                logger.info(f"Przetwarzam asset: {asset_name}/{quote_name} (ID: {asset_id})")
                
                for interval in self.CHART_INTERVALS.keys():
                    logger.info(f"Przetwarzam interwał: {interval} dla assetu {asset_name}/{quote_name}")
                    
                    try:
                        # 1. Pobierz obrazy wykresów bez interpretacji dla asset i interwału
                        chart_images = await self._get_chart_images_without_interpretations(asset_id, interval)
                        
                        if not chart_images:
                            logger.info(f"Brak obrazów wykresów bez interpretacji dla {asset_name}/{quote_name} - {interval}")
                            continue
                        
                        logger.info(f"Znaleziono {len(chart_images)} obrazów wykresów do przetworzenia")
                        
                        # 2. Pobierz obrazy ze storage
                        downloaded_images = await self._download_chart_images(chart_images)
                        
                        if not downloaded_images:
                            logger.warning(f"Nie udało się pobrać żadnych obrazów dla {asset_name}/{quote_name} - {interval}")
                            continue
                        
                        # 3. Pobierz wzorce harmoniczne dla wszystkich obrazów i usuń duplikaty
                        if chart_images:
                            harmonic_patterns = await self._get_harmonic_patterns_for_chart_images(chart_images)
                            
                            # Przygotuj JSON z wzorcami
                            json_patterns_list = json.dumps(harmonic_patterns, indent=2) if harmonic_patterns else "[]"
                        else:
                            json_patterns_list = "[]"
                        
                        # 4. Przygotuj prompt z danymi
                        prompt = self.TA_PROMPT.format(
                            asset=asset_name,
                            quote=quote_name,
                            interval=interval,
                            datetime=datetime.now(),
                            json_patterns_list=json_patterns_list
                        )
                        
                        # 5. Wyślij do LLM'a
                        llm_response = await self._send_to_llm(prompt, downloaded_images)
                        
                        if not llm_response:
                            logger.error(f"Nie otrzymano odpowiedzi z LLM'a dla {asset_name}/{quote_name} - {interval}")
                            continue
                        
                        # 6. Wyciągnij JSON z odpowiedzi
                        response_content = llm_response.get('message', '')
                        json_content = self._extract_json_from_response(response_content)
                        
                        # 7. Zapisz interpretację do bazy danych
                        if chart_images and harmonic_patterns:
                            # Użyj pierwszego wzorca harmonicznego jako technical_analysis_id
                            first_pattern_id = harmonic_patterns[0]['id']
                            interpretation_id = await self._save_interpretation(
                                asset_id=asset_id,
                                technical_analysis_id=first_pattern_id,
                                content=json_content
                            )
                            
                            if interpretation_id:
                                logger.info(f"Pomyślnie zapisano interpretację dla {asset_name}/{quote_name} - {interval}")
                            else:
                                logger.error(f"Nie udało się zapisać interpretacji dla {asset_name}/{quote_name} - {interval}")
                        else:
                            logger.warning(f"Brak wzorców harmonicznych dla {asset_name}/{quote_name} - {interval}")
                        
                    except Exception as e:
                        logger.error(f"Błąd podczas przetwarzania {asset_name}/{quote_name} - {interval}: {e}", exc_info=True)
                        continue
            
            logger.info("Zakończono synchronizację interpretacji analiz technicznych")
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji interpretacji analiz technicznych: {e}", exc_info=True)
            raise
