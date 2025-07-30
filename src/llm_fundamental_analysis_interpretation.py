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
    
    def _sort_news_by_timestamp(self, news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Sortuje newsy według timestamp (od najstarszych do najnowszych).
        
        Args:
            news_list: Lista newsów do posortowania
            
        Returns:
            List[Dict[str, Any]]: Posortowana lista newsów
        """
        return sorted(news_list, key=lambda x: x['timestamp'])

    def _get_latest_timestamp_from_news(self, news_list: List[Dict[str, Any]]) -> int:
        """
        Pobiera najnowszy timestamp z listy newsów.
        
        Args:
            news_list: Lista newsów
            
        Returns:
            int: Najnowszy timestamp
        """
        if not news_list:
            return int(datetime.now().timestamp())
        
        return max(news['timestamp'] for news in news_list)

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
                    
                    # Sortuj newsy według timestamp
                    sorted_news = self._sort_news_by_timestamp(news_without_interpretation)
                    
                    # Pobierz ostatnią interpretację z bazy danych dla tego assetu
                    last_interpretation = await interpretation_table.get_latest_by_asset_id(asset['id'])
                    
                    # Przetwórz przez wszystkie dostępne LLM'y
                    for llm_api in self.llm_apis:
                        try:
                            logger.info(f"Przetwarzam interpretację LLM dla assetu {asset['asset']} przez {llm_api.__class__.__name__}")
                            
                            # Pobierz limit tokenów dla modelu
                            tokens_limit = llm_api.MODELS.get("prompt", {}).get("limit", 30000)
                            
                            # Przygotuj podstawowy prompt bez newsów
                            base_prompt = self.CRYPTO_PROMPT.format(
                                asset=asset['asset'],
                                quote=asset['quote'],
                                analysis_date="{analysis_date}",
                                all_news="{all_news}",
                                last_fundamental_analysis="{last_fundamental_analysis}"
                            )
                            
                            # Oblicz tokeny dla podstawowego promptu
                            base_tokens = llm_api.calculate_tokens_from_prompt(base_prompt)
                            available_tokens = tokens_limit - base_tokens
                            
                            if available_tokens <= 0:
                                logger.warning(f"Podstawowy prompt przekracza limit tokenów ({base_tokens} > {tokens_limit}) dla assetu {asset['asset']}")
                                continue
                            
                            # Przetwarzaj newsy w pętli, dodając kolejne do promptu
                            current_news_batch = []
                            current_last_analysis = last_interpretation
                            iteration_count = 0
                            
                            for news in sorted_news:
                                # Sprawdź czy można dodać ten news do aktualnej partii
                                test_news_batch = current_news_batch + [news]
                                test_news_content = self._format_news_for_prompt(test_news_batch)
                                test_last_analysis = self._format_last_analysis_for_prompt(current_last_analysis)
                                
                                # Użyj najnowszego timestamp z tej partii newsów
                                analysis_timestamp = self._get_latest_timestamp_from_news(test_news_batch)
                                analysis_date = datetime.fromtimestamp(analysis_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                                
                                # Przygotuj testowy prompt
                                test_prompt = self.CRYPTO_PROMPT.format(
                                    asset=asset['asset'],
                                    quote=asset['quote'],
                                    analysis_date=analysis_date,
                                    all_news=test_news_content,
                                    last_fundamental_analysis=test_last_analysis
                                )
                                
                                # Sprawdź liczbę tokenów
                                test_token_count = llm_api.calculate_tokens_from_prompt(test_prompt)
                                
                                if test_token_count <= tokens_limit:
                                    # Można dodać ten news do aktualnej partii
                                    current_news_batch = test_news_batch
                                else:
                                    # Nie można dodać - przetwórz aktualną partię
                                    if current_news_batch:
                                        iteration_count += 1
                                        logger.info(f"Iteracja {iteration_count} dla assetu {asset['asset']}: {len(current_news_batch)} newsów, ~{llm_api.calculate_tokens_from_prompt(self._format_news_for_prompt(current_news_batch))} tokenów")
                                        
                                        # Formatuj dane dla prompta
                                        all_news = self._format_news_for_prompt(current_news_batch)
                                        last_fundamental_analysis = self._format_last_analysis_for_prompt(current_last_analysis)
                                        
                                        # Użyj najnowszego timestamp z tej partii newsów
                                        analysis_timestamp = self._get_latest_timestamp_from_news(current_news_batch)
                                        analysis_date = datetime.fromtimestamp(analysis_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                                        
                                        # Przygotuj prompt z danymi
                                        prompt = self.CRYPTO_PROMPT.format(
                                            asset=asset['asset'],
                                            quote=asset['quote'],
                                            analysis_date=analysis_date,
                                            all_news=all_news,
                                            last_fundamental_analysis=last_fundamental_analysis
                                        )
                                        
                                        # Sprawdź liczbę tokenów
                                        token_count = llm_api.calculate_tokens_from_prompt(prompt)
                                        logger.info(f"Iteracja {iteration_count}: {token_count} tokenów (limit: {tokens_limit})")
                                        
                                        # Wyślij zapytanie do LLM'a
                                        response = await llm_api.send_message(prompt)
                                        
                                        if response and "message" in response:
                                            try:
                                                logger.info(f"Odpowiedź z LLM'a dla iteracji {iteration_count}: {response['message']}")
                                                # Próbuj sparsować odpowiedź jako JSON
                                                interpretation_result = json.loads(response["message"])
                                                
                                                # Dodaj dodatkowe informacje
                                                interpretation_result['asset'] = asset['asset']
                                                interpretation_result['quote'] = asset['quote']
                                                interpretation_result['timestamp'] = analysis_timestamp
                                                interpretation_result['iteration_number'] = iteration_count
                                                
                                                # Zapisz interpretację w bazie danych
                                                interpretation_id = await interpretation_table.create(
                                                    asset_ids=[asset['id']],
                                                    fundamental_analysis_ids=[news['id'] for news in current_news_batch],
                                                    timestamp=interpretation_result['timestamp'],
                                                    content=interpretation_result
                                                )
                                                
                                                if interpretation_id:
                                                    processed_count += 1
                                                    logger.info(f"Zapisano interpretację LLM {interpretation_id} dla iteracji {iteration_count} assetu {asset['asset']}")
                                                    
                                                    # Aktualizuj last_analysis dla następnej iteracji
                                                    current_last_analysis = await interpretation_table.get_latest_by_asset_id(asset['id'])
                                                else:
                                                    error_count += 1
                                                    logger.error(f"Nie udało się zapisać interpretacji LLM dla iteracji {iteration_count} assetu {asset['asset']}")
                                                    break
                                                
                                            except json.JSONDecodeError as e:
                                                logger.error(f"Nie udało się sparsować odpowiedzi JSON dla iteracji {iteration_count} assetu {asset['asset']}: {e}, traceback: {traceback.format_exc()}")
                                                break
                                        else:
                                            logger.warning(f"Nieprawidłowa odpowiedź z LLM'a dla iteracji {iteration_count} assetu {asset['asset']}, traceback: {traceback.format_exc()}")
                                            break
                                    
                                    # Rozpocznij nową partię z tym newsem
                                    current_news_batch = [news]
                            
                            # Przetwórz ostatnią partię jeśli pozostała
                            if current_news_batch:
                                iteration_count += 1
                                logger.info(f"Ostatnia iteracja {iteration_count} dla assetu {asset['asset']}: {len(current_news_batch)} newsów")
                                
                                # Formatuj dane dla prompta
                                all_news = self._format_news_for_prompt(current_news_batch)
                                last_fundamental_analysis = self._format_last_analysis_for_prompt(current_last_analysis)
                                
                                # Użyj najnowszego timestamp z tej partii newsów
                                analysis_timestamp = self._get_latest_timestamp_from_news(current_news_batch)
                                analysis_date = datetime.fromtimestamp(analysis_timestamp).strftime('%Y-%m-%d %H:%M:%S')
                                
                                # Przygotuj prompt z danymi
                                prompt = self.CRYPTO_PROMPT.format(
                                    asset=asset['asset'],
                                    quote=asset['quote'],
                                    analysis_date=analysis_date,
                                    all_news=all_news,
                                    last_fundamental_analysis=last_fundamental_analysis
                                )
                                
                                # Sprawdź liczbę tokenów
                                token_count = llm_api.calculate_tokens_from_prompt(prompt)
                                logger.info(f"Ostatnia iteracja {iteration_count}: {token_count} tokenów (limit: {tokens_limit})")
                                
                                # Wyślij zapytanie do LLM'a
                                response = await llm_api.send_message(prompt)
                                
                                if response and "message" in response:
                                    try:
                                        logger.info(f"Odpowiedź z LLM'a dla ostatniej iteracji {iteration_count}: {response['message']}")
                                        # Próbuj sparsować odpowiedź jako JSON
                                        interpretation_result = json.loads(response["message"])
                                        
                                        # Dodaj dodatkowe informacje
                                        interpretation_result['asset'] = asset['asset']
                                        interpretation_result['quote'] = asset['quote']
                                        interpretation_result['timestamp'] = analysis_timestamp
                                        interpretation_result['iteration_number'] = iteration_count
                                        
                                        # Zapisz interpretację w bazie danych
                                        interpretation_id = await interpretation_table.create(
                                            asset_ids=[asset['id']],
                                            fundamental_analysis_ids=[news['id'] for news in current_news_batch],
                                            timestamp=interpretation_result['timestamp'],
                                            content=interpretation_result
                                        )
                                        
                                        if interpretation_id:
                                            processed_count += 1
                                            logger.info(f"Zapisano ostatnią interpretację LLM {interpretation_id} dla iteracji {iteration_count} assetu {asset['asset']}")
                                        else:
                                            error_count += 1
                                            logger.error(f"Nie udało się zapisać ostatniej interpretacji LLM dla iteracji {iteration_count} assetu {asset['asset']}")
                                        
                                    except json.JSONDecodeError as e:
                                        logger.error(f"Nie udało się sparsować odpowiedzi JSON dla ostatniej iteracji {iteration_count} assetu {asset['asset']}: {e}, traceback: {traceback.format_exc()}")
                                    else:
                                        logger.warning(f"Nieprawidłowa odpowiedź z LLM'a dla ostatniej iteracji {iteration_count} assetu {asset['asset']}, traceback: {traceback.format_exc()}")
                            
                            # Jeśli dotarliśmy tutaj, oznacza to że przetworzenie się udało
                            break
                            
                        except Exception as e:
                            logger.error(f"Błąd podczas przetwarzania przez {llm_api.__class__.__name__} dla assetu {asset['asset']}: {e}, traceback: {traceback.format_exc()}")
                            continue
                    else:
                        # Jeśli dotarliśmy tutaj, oznacza to że żaden LLM nie przetworzył assetu
                        error_count += 1
                        logger.error(f"Nie udało się wygenerować interpretacji LLM dla assetu {asset['asset']} przez żaden z dostępnych LLM'ów")
                
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
