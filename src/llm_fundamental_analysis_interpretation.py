import logging
import traceback
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class LlmFundamentalAnalysisInterpretation:
    """
    Klasa odpowiedzialna za interpretację analiz fundamentalnych za pomocą LLM'ów.
    Używa wzorca strategii do obsługi różnych LLM'ów.
    """
    
    CRYPTO_PROMPT = """
    Masz dostęp do aktualnych wiadomości oraz poprzedniej analizy fundamentalnej dotyczącej danego aktywa (np. spółki giełdowej, kryptowaluty, ETF-u lub sektora). Twoim zadaniem jest wyciągnąć możliwie najwięcej informacji pomocnych w podejmowaniu decyzji inwestycyjnych.
    
    🔸 **Kontekst**:
    - Aktywo: {asset}/{quote}
    - Data analizy: {analysis_date}
    
    🔸 **Źródła wejściowe**:
    1. **Aktualne newsy**:
    
    {all_news} 
    
    2. **Poprzednia analiza fundamentalna**:
    
    {last_fundamental_analysis} 
    
    ---
    
    🎯 **Twoje zadania**:
    1. Przeanalizuj główne tematy, które pojawiają się w aktualnych newsach - jakie mają znaczenie fundamentalne?
    2. Czy zaszły jakieś istotne zmiany od poprzedniej analizy?
    3. Oceń aktualną sytuację fundamentalną aktywa - czy poprawiła się, pogorszyła, czy pozostała stabilna?
    4. Zidentyfikuj czynniki ryzyka oraz czynniki potencjalnego wzrostu.
    5. Wydaj krótką **ocenę (rating)** w skali:
       - 🟢 Pozytywna sytuacja fundamentalna
       - 🟡 Neutralna
       - 🔴 Negatywna
    
    ---
    
    📦 **Zwróć wynik w formacie JSON**:
    ```json
    {{
      "asset": "{asset}",
      "quote": "{quote}",
      "summary": "Krótka interpretacja aktualnych wiadomości i zmian.",
      "main_signals": [
        "🟢 Silny wzrost przychodów Q2 2025",
        "🟡 Kontrowersje wokół zarządu – niepotwierdzone informacje",
        "🔴 Dochodzenie SEC w toku (wpływ nieznany)"
      ],
      "changes_since_last_analysis": "Opis zmian, np. 'zwiększona zmienność, lepsze wyniki kwartalne, ryzyko regulacyjne'",
      "risks": [
        "Możliwe nowe regulacje w sektorze",
        "Uzależnienie od jednego klienta"
      ],
      "opportunities": [
        "Nowy kontrakt z firmą X",
        "Silny popyt w Azji"
      ],
      "fundamental_rating": "🟡 Neutralna",
      "suggested_focus": "Obserwuj rozwój sytuacji wokół postępowania SEC. Możliwa korekta w krótkim terminie, ale fundamenty długoterminowe stabilne."
    }}
    ```
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy LlmFundamentalAnalysisInterpretation
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.llm_apis = self.api_facade.get_fabric().get_llm_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
    
    def _format_news_for_prompt(self, news_list: List[Dict[str, Any]]) -> str:
        """
        Formatuje listę newsów do formatu wymaganego przez prompt.
        
        Args:
            news_list: Lista newsów z bazy danych
            
        Returns:
            str: Sformatowane newsy jako string
        """
        if not news_list:
            return "Brak aktualnych wiadomości."
        
        formatted_news = []
        for i, news in enumerate(news_list, 1):
            # Konwertuj timestamp na czytelną datę
            timestamp_date = datetime.fromtimestamp(news['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            
            # Przygotuj content jako string
            content_str = json.dumps(news['content'], indent=2, ensure_ascii=False)
            
            formatted_news.append(
                f"""
                ## news {news['id']} - published at {timestamp_date}

                    {content_str}
                """
            )
        
        return "\n".join(formatted_news)
    
    def _format_last_analysis_for_prompt(self, last_analysis: Optional[Dict[str, Any]]) -> str:
        """
        Formatuje ostatnią analizę fundamentalną do formatu wymaganego przez prompt.
        
        Args:
            last_analysis: Ostatnia analiza fundamentalna lub None
            
        Returns:
            str: Sformatowana analiza jako string
        """
        if not last_analysis:
            return "brak ostatniej analizy fundamentalnej w bazie"
        
        # Konwertuj timestamp na czytelną datę
        timestamp_date = datetime.fromtimestamp(last_analysis['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        
        # Przygotuj content jako string
        content_str = json.dumps(last_analysis['content'], indent=2, ensure_ascii=False)
        
        return f"""
        ## Ostatnia analiza fundamentalna - {timestamp_date}
        Serwis: {last_analysis.get('service', 'Nieznany')}
        Link: {last_analysis.get('link', 'Brak')}
        
        {content_str}
        """
    
    async def _process_asset_interpretation(self, asset: Dict[str, Any], news_list: List[Dict[str, Any]], last_analysis: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Przetwarza interpretację LLM dla pojedynczego assetu.
        
        Args:
            asset: Informacje o assecie
            news_list: Lista newsów dla assetu
            last_analysis: Ostatnia analiza fundamentalna dla assetu
            
        Returns:
            Dict[str, Any]: Wynik interpretacji lub None w przypadku błędu
        """
        try:
            # Formatuj dane dla prompta
            all_news = self._format_news_for_prompt(news_list)
            last_fundamental_analysis = self._format_last_analysis_for_prompt(last_analysis)
            
            # Przygotuj prompt z danymi
            analysis_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            prompt = self.CRYPTO_PROMPT.format(
                asset=asset['asset'],
                quote=asset['quote'],
                analysis_date=analysis_date,
                all_news=all_news,
                last_fundamental_analysis=last_fundamental_analysis
            )
            
            # Przetwórz przez wszystkie dostępne LLM'y
            for llm_api in self.llm_apis:
                try:
                    logger.info(f"Przetwarzam interpretację LLM dla assetu {asset['asset']} przez {llm_api.__class__.__name__}")
                    
                    # Wyślij zapytanie do LLM'a
                    response = await llm_api.send_message(prompt)
                    
                    if response and "message" in response:
                        try:
                            # Próbuj sparsować odpowiedź jako JSON
                            interpretation_result = json.loads(response["message"])
                            
                            # Dodaj dodatkowe informacje
                            interpretation_result['asset'] = asset['asset']
                            interpretation_result['quote'] = asset['quote']
                            interpretation_result['timestamp'] = int(datetime.now().timestamp())
                            
                            logger.info(f"Pomyślnie wygenerowano interpretację dla assetu {asset['asset']}")
                            return interpretation_result
                            
                        except json.JSONDecodeError as e:
                            logger.error(f"Nie udało się sparsować odpowiedzi JSON dla assetu {asset['asset']}: {e}")
                            continue
                    else:
                        logger.warning(f"Nieprawidłowa odpowiedź z LLM'a dla assetu {asset['asset']}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Błąd podczas przetwarzania przez {llm_api.__class__.__name__} dla assetu {asset['asset']}: {e}")
                    continue
            
            logger.error(f"Nie udało się wygenerować interpretacji LLM dla assetu {asset['asset']} przez żaden z dostępnych LLM'ów")
            return None
            
        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania interpretacji LLM dla assetu {asset['asset']}: {e}", exc_info=True)
            return None
    
    async def sync_crypto_fundamental_analysis_interpretations(self, limit: int = 50, offset: int = 0) -> None:
        """
        Synchronizuje interpretacje analiz fundamentalnych za pomocą LLM'ów.
        
        Args:
            limit: Maksymalna liczba assetów do przetworzenia (domyślnie 50)
            offset: Offset dla pobierania assetów (domyślnie 0)
            
        Returns:
            None
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # KROK 1: Pobierz assety z bazy danych
            logger.info("=== KROK 1: Pobieranie assetów z bazy danych ===")
            assets = await self.db.get_factory().get_assets_table().get_all(
                limit=limit, 
                offset=offset
            )
            logger.info(f"Pobrano {len(assets)} assetów z bazy danych")
            
            if not assets:
                logger.warning("Brak assetów w bazie danych - nie można przetworzyć interpretacji LLM")
                return None
            
            # KROK 2: Przetwórz każdy asset
            logger.info("=== KROK 2: Przetwarzanie interpretacji LLM dla assetów ===")
            
            fundamental_analysis_table = self.db.get_factory().get_fundamental_analysis_table()
            interpretation_table = self.db.get_factory().get_fundamental_analysis_interpretation_table()
            
            processed_count = 0
            error_count = 0
            
            for asset in assets:
                try:
                    logger.info(f"Przetwarzam asset: {asset['asset']}/{asset['quote']}")
                    
                    # Pobierz newsy bez interpretacji dla tego assetu
                    news_without_interpretation = await fundamental_analysis_table.get_analyses_without_interpretation_by_asset_id(
                        asset_id=asset['id'],
                        limit=100  # Pobierz wszystkie dostępne newsy bez interpretacji
                    )
                    
                    if not news_without_interpretation:
                        logger.info(f"Brak newsów bez interpretacji LLM dla assetu {asset['asset']} - pomijam")
                        continue
                    
                    logger.info(f"Znaleziono {len(news_without_interpretation)} newsów bez interpretacji LLM dla assetu {asset['asset']}")
                    
                    # Pobierz ostatnią analizę fundamentalną dla tego assetu
                    last_analysis = await fundamental_analysis_table.get_latest_by_asset_id(asset['id'])
                    
                    # Przetwórz interpretację
                    interpretation_result = await self._process_asset_interpretation(
                        asset=asset,
                        news_list=news_without_interpretation,
                        last_analysis=last_analysis
                    )
                    
                    if interpretation_result:
                        # Zapisz interpretację w bazie danych
                        interpretation_id = await interpretation_table.create(
                            asset_ids=[asset['id']],
                            fundamental_analysis_ids=[news['id'] for news in news_without_interpretation],
                            timestamp=interpretation_result['timestamp'],
                            content=interpretation_result
                        )
                        
                        if interpretation_id:
                            processed_count += 1
                            logger.info(f"Zapisano interpretację LLM {interpretation_id} dla assetu {asset['asset']}")
                        else:
                            error_count += 1
                            logger.error(f"Nie udało się zapisać interpretacji LLM dla assetu {asset['asset']}")
                    else:
                        error_count += 1
                        logger.error(f"Nie udało się wygenerować interpretacji LLM dla assetu {asset['asset']}")
                
                except Exception as e:
                    error_count += 1
                    logger.error(f"Błąd podczas przetwarzania assetu {asset['asset']}: {e}", exc_info=True)
                    continue
            
            logger.info(f"=== Synchronizacja interpretacji LLM zakończona ===")
            logger.info(f"Przetworzono: {processed_count} assetów")
            logger.info(f"Błędy: {error_count} assetów")
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji interpretacji LLM: {e}", exc_info=True)
            return None
