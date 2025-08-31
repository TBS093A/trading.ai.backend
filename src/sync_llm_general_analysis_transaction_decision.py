import logging
import traceback
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class LlmGeneralAnalysisTransactionDecision:
    """
    Klasa odpowiedzialna za podejmowanie decyzji transakcyjnych na podstawie analiz fundamentalnych,
    technicznych i strategii inwestycyjnych za pomocą LLM'ów.
    """
    
    DECISION_PROMPT = """
Masz dostęp do:
- aktualnych analiz fundamentalnych,
- aktualnych analiz technicznych,
- ostatniej analizy generalnej,
- sugestii strategicznych.

Twoim zadaniem jest przeprowadzenie **pełnej analizy inwestycyjnej**, łączącej perspektywę fundamentalną i techniczną, oraz podjęcie decyzji transakcyjnej zgodnej z wytyczonymi strategiami.

---

🔸 **Kontekst**:
- Aktywo: {asset}/{quote}
- Data analizy: {datetime}

🔸 **Źródła wejściowe**:

2. **analizy fundamentalne**:
{fundamental_analysis}

3. **analizy techniczne**:
{technical_analysis}

4. **Dodatkowe sugestie strategiczne**:
{strategy}

---

🎯 **Twoje zadania**:
1. **Analiza fundamentalna**:
   - Wyciągnij kluczowe informacje z newsów i poprzedniej analizy.
   - Określ czy sytuacja fundamentalna poprawiła się, pogorszyła czy pozostała stabilna.
   - Wskaż najważniejsze ryzyka i potencjalne szanse.

2. **Analiza techniczna**:
   - Oceń wykresy, wskaźniki i patterny (np. RSI, MACD, MA, formacje świecowe, wsparcia/opory, wolumen).
   - Określ czy momentum jest wzrostowe, spadkowe czy neutralne.
   - Wskaż potencjalne scenariusze krótkoterminowe.

3. **Integracja obu podejść**:
   - Zestaw wyniki analizy fundamentalnej i technicznej.
   - Uwzględnij strategię (np. DCA, swing trading, scalping, long-term hold).
   - Podejmij decyzję transakcyjną (kup / sprzedaj / trzymaj).

4. **Wydaj ostateczną rekomendację**:
   - Uwzględnij sygnały, ryzyka i strategię.
   - Wydaj rating sytuacji rynkowej w skali:
     - 🟢 Bycza (pro wzrost)
     - 🟡 Neutralna (brak silnych sygnałów)
     - 🔴 Niedźwiedzia (pro spadek)

---

📦 **Zwróć wynik w formacie JSON**:

```json
{{
  "asset": "{asset}",
  "quote": "{quote}",
  "fundamental_summary": "Podsumowanie sytuacji fundamentalnej.",
  "technical_summary": "Podsumowanie sytuacji technicznej.",
  "main_signals": [
    "🟢 RSI powyżej 60 – momentum wzrostowe",
    "🔴 Dochodzenie SEC – ryzyko regulacyjne",
    "🟡 Stabilny wolumen handlowy – brak wybicia"
  ],
  "risks": [
    "Ryzyko regulacyjne w USA",
    "Możliwa korekta techniczna po wybiciu"
  ],
  "opportunities": [
    "Nowe partnerstwo strategiczne",
    "Potwierdzony trend wzrostowy na MA200"
  ],
  "fundamental_rating": "🟡 Neutralna",
  "technical_rating": "🟢 Wzrostowa",
  "combined_market_outlook": "🟢 Bycza",
  "strategy_applied": "{strategy}",
  "transaction_decision": {{
    "action": "BUY", 
    "confidence": "High",
    "time_horizon": "Swing / Mid-term (2–6 tygodni)",
    "justification": "Fundamenty neutralne, technicznie silne sygnały wzrostowe, strategia {strategy} wspiera akumulację."
  }},
  "suggested_focus": "Monitoruj wolumen oraz rozwój sytuacji regulacyjnej. Stop-loss sugerowany w rejonie ostatniego wsparcia."
}}
```
"""

    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy LlmGeneralAnalysisTransactionDecision
        
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
    
    def _format_fundamental_analysis_for_prompt(self, fundamental_analyses: List[Dict[str, Any]]) -> str:
        """
        Formatuje analizy fundamentalne do formatu wymaganego przez prompt.
        
        Args:
            fundamental_analyses: Lista analiz fundamentalnych
            
        Returns:
            str: Sformatowane analizy jako string
        """
        if not fundamental_analyses:
            return "Brak analiz fundamentalnych."
        
        formatted_analyses = []
        for i, analysis in enumerate(fundamental_analyses):
            # Konwertuj timestamp na czytelną datę
            timestamp_date = datetime.fromtimestamp(analysis['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
            created_at = analysis.get('created_at', 'N/A')
            
            # Przygotuj content jako string
            content_str = json.dumps(analysis['content'], indent=2, ensure_ascii=False)
            
            formatted_analyses.append(
                f"## {i} - timestamp: {timestamp_date} - created at: {created_at}\n{content_str}"
            )
        
        return "\n".join(formatted_analyses)
    
    def _format_technical_analysis_for_prompt(self, technical_analyses: List[Dict[str, Any]]) -> str:
        """
        Formatuje analizy techniczne do formatu wymaganego przez prompt.
        
        Args:
            technical_analyses: Lista analiz technicznych
            
        Returns:
            str: Sformatowane analizy jako string
        """
        if not technical_analyses:
            return "Brak analiz technicznych."
        
        formatted_analyses = []
        for i, analysis in enumerate(technical_analyses):
            # Konwertuj timestamp na czytelną datę
            timestamp_date = analysis['timestamp']
            created_at = analysis.get('created_at', 'N/A')
            
            # Pobierz interwały wzorców harmonicznych
            intervals = "brak interwałów"
            if 'intervals' in analysis and analysis['intervals']:
                intervals = ", ".join(analysis['intervals'])
            
            # Przygotuj content jako string
            content_str = analysis.get('content', 'Brak treści')
            
            formatted_analyses.append(
                f"## {i} - intervals: {intervals} - timestamp: {timestamp_date} - created at: {created_at}\n{content_str}"
            )
        
        return "\n".join(formatted_analyses)
    
    def _format_strategies_for_prompt(self, strategies: List[Dict[str, Any]]) -> str:
        """
        Formatuje strategie inwestycyjne do formatu wymaganego przez prompt.
        
        Args:
            strategies: Lista strategii inwestycyjnych
            
        Returns:
            str: Sformatowane strategie jako string
        """
        if not strategies:
            return "Brak strategii inwestycyjnych."
        
        formatted_strategies = []
        for i, strategy in enumerate(strategies):
            name = strategy.get('name', 'Nieznana nazwa')
            description = strategy.get('description', 'Brak opisu')
            
            formatted_strategies.append(
                f"## {i} - {name}\n{description}"
            )
        
        return "\n".join(formatted_strategies)
    
    def _extract_json_from_response(self, response_text: str) -> str:
        """
        Wyciąga JSON z odpowiedzi LLM, która może być otoczona backticks.
        
        Args:
            response_text: Odpowiedź z LLM
            
        Returns:
            str: Wyciągnięty JSON jako string
        """
        # Usuń białe znaki z początku i końca
        response_text = response_text.strip()
        
        # Sprawdź czy odpowiedź zaczyna się od ```json
        if response_text.startswith('```json'):
            # Znajdź koniec bloku kodu
            end_marker = '```'
            start_pos = response_text.find('```json') + 7  # 7 to długość '```json'
            end_pos = response_text.rfind(end_marker)
            
            if end_pos > start_pos:
                return response_text[start_pos:end_pos].strip()
        
        # Sprawdź czy odpowiedź zaczyna się od ```
        elif response_text.startswith('```'):
            # Znajdź koniec bloku kodu
            end_marker = '```'
            start_pos = response_text.find('```') + 3  # 3 to długość '```'
            end_pos = response_text.rfind(end_marker)
            
            if end_pos > start_pos:
                return response_text[start_pos:end_pos].strip()
        
        # Jeśli nie ma backticks, zwróć całą odpowiedź
        return response_text

    async def sync(self, limit: int = 10, offset: int = 0) -> None:
        """
        Synchronizuje decyzje transakcyjne za pomocą LLM'ów.
        
        Args:
            limit: Maksymalna liczba assetów do przetworzenia (domyślnie 10)
            offset: Offset dla pobierania assetów (domyślnie 0)
            
        Returns:
            None
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            # KROK 0: Pobierz wszystkie assety dostępne w bazie
            logger.info("=== KROK 0: Pobieranie assetów z bazy danych ===")
            assets = await self.db.get_factory().get_assets_table().get_all(
                limit=limit, 
                offset=offset
            )
            logger.info(f"Pobrano {len(assets)} assetów z bazy danych")
            
            if not assets:
                logger.warning("Brak assetów w bazie danych - nie można przetworzyć decyzji transakcyjnych")
                return None
            
            # Pobierz potrzebne tabele
            fundamental_analysis_interpretation_table = self.db.get_factory().get_fundamental_analysis_interpretation_table()
            technical_analysis_interpretation_table = self.db.get_factory().get_technical_analysis_interpretation_table()
            investment_strategies_table = self.db.get_factory().get_investment_strategies_table()
            general_interpretation_table = self.db.get_factory().get_general_interpretation_table()
            
            # KROK 1: Przetwórz każdy asset
            logger.info("=== KROK 1: Przetwarzanie decyzji transakcyjnych dla assetów ===")
            
            processed_count = 0
            error_count = 0
            
            for asset in assets:
                try:
                    asset_id = asset['id']
                    asset_name = asset['asset']
                    quote_name = asset['quote']
                    
                    logger.info(f"Przetwarzam asset: {asset_name}/{quote_name}")
                    
                    # 1.1 Pobierz analizy fundamentalne bez relacji z interpretacją generalną
                    fundamental_analyses_without_general = await fundamental_analysis_interpretation_table.get_interpretations_without_general_interpretation_by_asset_id(asset_id)
                    
                    if not fundamental_analyses_without_general:
                        logger.info(f"Brak analiz fundamentalnych bez interpretacji generalnej dla assetu {asset_name} - pomijam")
                        continue
                    
                    logger.info(f"Znaleziono {len(fundamental_analyses_without_general)} analiz fundamentalnych bez interpretacji generalnej dla assetu {asset_name}")
                    
                    # 1.2 Pobierz analizy techniczne bez relacji z interpretacją generalną
                    technical_analyses_without_general = await technical_analysis_interpretation_table.get_interpretations_without_general_interpretation_by_asset_id(asset_id)
                    
                    # Wzbogać analizy techniczne o informacje o interwałach
                    for technical_analysis in technical_analyses_without_general:
                        intervals = await technical_analysis_interpretation_table.get_all_intervals_of_used_harmonic_patterns(technical_analysis['id'])
                        technical_analysis['intervals'] = intervals
                    
                    logger.info(f"Znaleziono {len(technical_analyses_without_general)} analiz technicznych bez interpretacji generalnej dla assetu {asset_name}")
                    
                    # 1.3 Pobierz wszystkie włączone strategie inwestycyjne
                    enabled_strategies = await investment_strategies_table.get_all_enabled_strategies(limit=100, offset=0)
                    
                    logger.info(f"Znaleziono {len(enabled_strategies)} włączonych strategii inwestycyjnych")
                    
                    # Sformatuj dane dla promptu
                    fundamental_analysis_str = self._format_fundamental_analysis_for_prompt(fundamental_analyses_without_general)
                    technical_analysis_str = self._format_technical_analysis_for_prompt(technical_analyses_without_general)
                    strategies_str = self._format_strategies_for_prompt(enabled_strategies)
                    
                    # 1.4 Uzupełnij DECISION_PROMPT
                    current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    prompt = self.DECISION_PROMPT.format(
                        asset=asset_name,
                        quote=quote_name,
                        datetime=current_datetime,
                        fundamental_analysis=fundamental_analysis_str,
                        technical_analysis=technical_analysis_str,
                        strategy=strategies_str
                    )
                    
                    # 1.5 Przetwórz przez wszystkie dostępne LLM'y
                    for llm_api in self.llm_apis:
                        try:
                            logger.info(f"Przetwarzam decyzję transakcyjną dla assetu {asset_name} przez {llm_api.__class__.__name__}")
                            
                            # Wyślij zapytanie do LLM'a
                            response = await llm_api.send_message(prompt)
                            
                            if response and "message" in response:
                                try:
                                    logger.info(f"Odpowiedź z LLM'a dla assetu {asset_name}: {response['message']}")
                                    # Próbuj sparsować odpowiedź jako JSON
                                    decision_result = json.loads(self._extract_json_from_response(response["message"]))
                                    
                                    # Dodaj dodatkowe informacje
                                    decision_result['asset'] = asset_name
                                    decision_result['quote'] = quote_name
                                    decision_result['timestamp'] = current_datetime
                                    
                                    # Zapisz interpretację w bazie danych
                                    interpretation_id = await general_interpretation_table.create(
                                        asset_id=asset_id,
                                        timestamp=current_datetime,
                                        content=json.dumps(decision_result),
                                        technical_analysis_interpretation_id=technical_analyses_without_general[0]['id'] if technical_analyses_without_general else None,
                                        fundamental_analysis_interpretation_id=fundamental_analyses_without_general[0]['id'] if fundamental_analyses_without_general else None,
                                        investment_strategy_id=enabled_strategies[0]['id'] if enabled_strategies else None
                                    )
                                    
                                    if interpretation_id:
                                        processed_count += 1
                                        logger.info(f"Zapisano decyzję transakcyjną {interpretation_id} dla assetu {asset_name}")
                                    else:
                                        error_count += 1
                                        logger.error(f"Nie udało się zapisać decyzji transakcyjnej dla assetu {asset_name}")
                                        break
                                    
                                except json.JSONDecodeError as e:
                                    logger.error(f"Nie udało się sparsować odpowiedzi JSON dla assetu {asset_name}: {e}, traceback: {traceback.format_exc()}")
                                    break
                            else:
                                logger.warning(f"Nieprawidłowa odpowiedź z LLM'a dla assetu {asset_name}")
                                break
                            
                            # Jeśli dotarliśmy tutaj, oznacza to że przetworzenie się udało
                            break
                            
                        except Exception as e:
                            logger.error(f"Błąd podczas przetwarzania przez {llm_api.__class__.__name__} dla assetu {asset_name}: {e}, traceback: {traceback.format_exc()}")
                            continue
                    else:
                        # Jeśli dotarliśmy tutaj, oznacza to że żaden LLM nie przetworzył assetu
                        error_count += 1
                        logger.error(f"Nie udało się wygenerować decyzji transakcyjnej dla assetu {asset_name} przez żaden z dostępnych LLM'ów")
                
                except Exception as e:
                    error_count += 1
                    logger.error(f"Błąd podczas przetwarzania assetu {asset['asset']}: {e}", exc_info=True)
                    continue
            
            logger.info(f"=== Synchronizacja decyzji transakcyjnych zakończona ===")
            logger.info(f"Przetworzono: {processed_count} assetów")
            logger.info(f"Błędy: {error_count} assetów")
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji decyzji transakcyjnych: {e}", exc_info=True)
            return None