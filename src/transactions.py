import logging
import traceback
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class Transactions:
    """
    Klasa odpowiedzialna za wykonywanie transakcji na podstawie analiz generalnych.
    Używa wzorca strategii do obsługi różnych giełd i strategii transakcyjnych.
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy Transactions
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges: List = self.api_facade.get_fabric().get_exchanges_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()
    
    def _parse_transaction_decision(self, general_interpretation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parsuje decyzję transakcyjną z interpretacji generalnej.
        
        Args:
            general_interpretation: Interpretacja generalna
            
        Returns:
            Dict z decyzją transakcyjną lub None jeśli nie można sparsować
        """
        try:
            # Próbuj sparsować content jako JSON
            if isinstance(general_interpretation.get('content'), str):
                content = json.loads(general_interpretation['content'])
            else:
                content = general_interpretation.get('content', {})
            
            # Sprawdź czy jest transaction_decision
            transaction_decision = content.get('transaction_decision')
            if not transaction_decision:
                logger.warning(f"Brak transaction_decision w interpretacji {general_interpretation['id']}")
                return None
            
            # Waliduj że są wymagane pola
            required_fields = ['action']
            for field in required_fields:
                if field not in transaction_decision:
                    logger.warning(f"Brak wymaganego pola '{field}' w transaction_decision interpretacji {general_interpretation['id']}")
                    return None
            
            return transaction_decision
            
        except Exception as e:
            logger.error(f"Błąd podczas parsowania transaction_decision z interpretacji {general_interpretation['id']}: {e}")
            return None
    
    def _calculate_transaction_amount(self, strategy: Dict[str, Any], account_state: Dict[str, Any]) -> float:
        """
        Oblicza kwotę przeznaczoną na transakcję na podstawie strategii i stanu konta.
        
        Args:
            strategy: Strategia kupna/sprzedaży
            account_state: Stan konta
            
        Returns:
            Kwota do wykorzystania w transakcji
        """
        try:
            movement_amount = strategy['movement_amount']
            account_amount = account_state['amount']
            is_percent = strategy['is_percent']
            
            if is_percent:
                # Oblicz kwotę na podstawie procentu
                calculated_amount = (account_amount * movement_amount) / 100
            else:
                # Użyj kwoty bezwzględnej
                calculated_amount = movement_amount
            
            # Jeśli obliczona kwota przekracza stan konta, użyj całego stanu konta
            if calculated_amount > account_amount:
                logger.info(f"Obliczona kwota ({calculated_amount}) przekracza stan konta ({account_amount}). Używam całego stanu konta.")
                return float(account_amount)
            
            return float(calculated_amount)
            
        except Exception as e:
            logger.error(f"Błąd podczas obliczania kwoty transakcji: {e}")
            return 0.0
    
    def _find_exchange_by_name(self, exchange_name: str) -> Optional[Any]:
        """
        Znajduje obiekt giełdy po nazwie.
        
        Args:
            exchange_name: Nazwa giełdy
            
        Returns:
            Obiekt giełdy lub None jeśli nie znaleziono
        """
        for exchange in self.exchanges:
            if hasattr(exchange, 'EXCHANGE_NAME') and exchange.EXCHANGE_NAME == exchange_name:
                return exchange
        return None
    
    async def _execute_transaction(self, exchange, transaction_side: str, strategy: Dict[str, Any], 
                                 asset: Dict[str, Any], transaction_amount: float) -> Optional[Dict[str, Any]]:
        """
        Wykonuje transakcję na giełdzie.
        
        Args:
            exchange: Obiekt giełdy
            transaction_side: BUY lub SELL
            strategy: Strategia transakcyjna
            asset: Informacje o assecie
            transaction_amount: Kwota do wykorzystania
            
        Returns:
            Wynik transakcji lub None w przypadku błędu
        """
        try:
            asset_name = asset['asset']
            quote_name = asset['quote']
            strategy_type = strategy['type']  # MARKET lub LIMIT
            
            logger.info(f"Wykonuję transakcję {transaction_side} {strategy_type} dla {asset_name}/{quote_name} z kwotą {transaction_amount}")
            
            if strategy_type == 'MARKET':
                # Użyj market order
                if transaction_side == 'BUY':
                    # Dla kupna market - używamy currency_size (quote)
                    result = exchange.market_buy(
                        coin=asset_name,
                        currency_size=transaction_amount,
                        used_currency=quote_name
                    )
                else:
                    # Dla sprzedaży market - używamy coin_size (asset)
                    result = exchange.market_sell(
                        coin=asset_name,
                        coin_size=transaction_amount,
                        used_currency=quote_name
                    )
            else:
                # Użyj limit order (domyślne metody buy/sell)
                if transaction_side == 'BUY':
                    result = exchange.buy(
                        coin=asset_name,
                        currency_size_to_buy=transaction_amount,
                        used_currency=quote_name
                    )
                else:
                    # Dla sprzedaży limit - używamy procent z dostępnych assetów
                    # Trzeba przekalkulować na procent
                    result = exchange.sell(
                        coin=asset_name,
                        coin_percent_size_to_sell=100.0,  # Używamy pełną kwotę którą obliczyliśmy
                        used_currency=quote_name
                    )
            
            logger.info(f"Transakcja wykonana pomyślnie: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Błąd podczas wykonywania transakcji: {e}")
            return None
    
    async def _save_transaction_to_database(self, exchange_id: int, asset_id: int, general_interpretation_id: int,
                                          transaction_side: str, quote_amount: float, asset_amount: float) -> Optional[int]:
        """
        Zapisuje transakcję w bazie danych.
        
        Args:
            exchange_id: ID giełdy
            asset_id: ID assetu
            general_interpretation_id: ID interpretacji generalnej
            transaction_side: BUY lub SELL
            quote_amount: Kwota quote
            asset_amount: Kwota asset
            
        Returns:
            ID zapisanej transakcji lub None w przypadku błędu
        """
        try:
            exchange_transactions_table = self.db.get_factory().get_exchange_transactions_table()
            
            transaction_id = await exchange_transactions_table.create(
                exchange_id=exchange_id,
                asset_id=asset_id,
                general_interpretation_id=general_interpretation_id,
                type=transaction_side,
                quote_amount=quote_amount,
                asset_amount=asset_amount
            )
            
            if transaction_id:
                logger.info(f"Zapisano transakcję w bazie danych z ID: {transaction_id}")
                return transaction_id
            else:
                logger.error("Nie udało się zapisać transakcji w bazie danych")
                return None
                
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania transakcji w bazie danych: {e}")
            return None

    async def sync(self, limit: int = 50, offset: int = 0) -> None:
        """
        Synchronizuje i wykonuje transakcje na podstawie analiz generalnych.
        
        Args:
            limit: Maksymalna liczba interpretacji do przetworzenia
            offset: Offset dla pobierania interpretacji
            
        Returns:
            None
        """
        try:
            # Inicjalizuj bazę danych jeśli nie została zainicjalizowana
            if not hasattr(self.db, 'factory') or self.db.factory is None:
                await self.db.init_db()
            
            logger.info("=== Rozpoczęcie synchronizacji transakcji ===")
            
            # KROK 0: Pobierz wszystkie analizy generalne które nie mają relacji z żadną transakcją
            logger.info("=== KROK 0: Pobieranie analiz generalnych bez transakcji ===")
            general_interpretation_table = self.db.get_factory().get_general_interpretation_table()
            general_interpretations = await general_interpretation_table.get_all_general_interpretations_without_transactions(
                limit=limit, offset=offset
            )
            
            if not general_interpretations:
                logger.info("Brak analiz generalnych bez transakcji do przetworzenia")
                return
            
            logger.info(f"Znaleziono {len(general_interpretations)} analiz generalnych bez transakcji")
            
            # Pobierz potrzebne tabele
            asset_exchanges_table = self.db.get_factory().get_asset_exchanges_table()
            exchange_account_state_table = self.db.get_factory().get_exchange_account_state_table()
            buy_strategies_table = self.db.get_factory().get_exchange_account_state_buy_strategies_table()
            sell_strategies_table = self.db.get_factory().get_exchange_account_state_sell_strategies_table()
            
            processed_count = 0
            error_count = 0
            
            # KROK 1: Loop po generalnych interpretacjach
            logger.info("=== KROK 1: Przetwarzanie analiz generalnych ===")
            for general_interpretation in general_interpretations:
                try:
                    asset_id = general_interpretation['asset_id']
                    asset_name = general_interpretation['asset']
                    quote_name = general_interpretation['quote']
                    
                    logger.info(f"Przetwarzam interpretację {general_interpretation['id']} dla assetu {asset_name}/{quote_name}")
                    
                    # Parsuj decyzję transakcyjną
                    transaction_decision = self._parse_transaction_decision(general_interpretation)
                    if not transaction_decision:
                        logger.warning(f"Nie można sparsować transaction_decision dla interpretacji {general_interpretation['id']}")
                        error_count += 1
                        continue
                    
                    transaction_action = transaction_decision['action']
                    
                    # KROK 1.0: Jeśli akcja to HODL, zatrzymaj iterację i przejdź do następnej
                    if transaction_action == 'HODL':
                        logger.info(f"Akcja HODL dla interpretacji {general_interpretation['id']} - pomijam")
                        continue
                    
                    # Waliduj akcję
                    if transaction_action not in ['BUY', 'SELL']:
                        logger.warning(f"Nieznana akcja transakcyjna: {transaction_action} dla interpretacji {general_interpretation['id']}")
                        error_count += 1
                        continue
                    
                    # KROK 1.1: Loop po giełdach
                    logger.info(f"=== KROK 1.1: Przetwarzanie giełd dla interpretacji {general_interpretation['id']} ===")
                    for exchange in self.exchanges:
                        try:
                            exchange_name = getattr(exchange, 'EXCHANGE_NAME', exchange.__class__.__name__)
                            logger.info(f"Przetwarzam giełdę: {exchange_name}")
                            
                            # KROK 1.1.1: Sprawdź czy asset jest powiązany z tą giełdą
                            asset_exchanges = await asset_exchanges_table.get_by_asset_id(asset_id)
                            
                            # Znajdź exchange dla tego assetu
                            matching_exchange = None
                            exchange_id = None
                            for asset_exchange in asset_exchanges:
                                if asset_exchange['exchange_name'] == exchange_name:
                                    matching_exchange = asset_exchange
                                    exchange_id = asset_exchange['exchange_id']
                                    break
                            
                            if not matching_exchange:
                                logger.debug(f"Asset {asset_name} nie jest powiązany z giełdą {exchange_name}")
                                continue
                            
                            logger.info(f"Asset {asset_name} jest powiązany z giełdą {exchange_name} (ID: {exchange_id})")
                            
                            # KROK 1.1.2: Pobierz włączone stany kont dla assetu na tej giełdzie
                            # Szukamy kont z walutą quote (dla kupna) lub base (dla sprzedaży)
                            if transaction_action == 'BUY':
                                # Dla kupna potrzebujemy kont z walutą quote (np. USDT)
                                target_currency = quote_name
                            else:
                                # Dla sprzedaży potrzebujemy kont z walutą asset (np. BTC)
                                target_currency = asset_name
                            
                            enabled_accounts = await exchange_account_state_table.get_enabled_accounts(exchange_id=exchange_id)
                            
                            # Filtruj konta po walucie
                            target_accounts = [acc for acc in enabled_accounts if acc['currency'] == target_currency]
                            
                            if not target_accounts:
                                logger.info(f"Brak włączonych kont z walutą {target_currency} na giełdzie {exchange_name}")
                                continue
                            
                            logger.info(f"Znaleziono {len(target_accounts)} włączonych kont z walutą {target_currency}")
                            
                            # KROK 1.1.2.1: Loop po stanach kont
                            for account_state in target_accounts:
                                try:
                                    account_state_id = account_state['id']
                                    account_amount = account_state['amount']
                                    
                                    logger.info(f"Przetwarzam konto {account_state_id} z kwotą {account_amount} {target_currency}")
                                    
                                    # Sprawdź czy konto ma jakieś środki
                                    if account_amount <= 0:
                                        logger.info(f"Konto {account_state_id} nie ma środków")
                                        continue
                                    
                                    # KROK 1.1.2.1.1: Pobierz strategię operacyjną
                                    strategy = None
                                    if transaction_action == 'BUY':
                                        strategy = await buy_strategies_table.get_by_exchange_account_state_id(account_state_id)
                                    else:
                                        strategy = await sell_strategies_table.get_by_exchange_account_state_id(account_state_id)
                                    
                                    if not strategy:
                                        logger.info(f"Brak strategii {transaction_action} dla konta {account_state_id}")
                                        continue
                                    
                                    logger.info(f"Znaleziono strategię {transaction_action}: {strategy['type']} {strategy['movement_amount']}")
                                    
                                    # Oblicz kwotę przeznaczoną na transakcję
                                    transaction_amount = self._calculate_transaction_amount(strategy, account_state)
                                    
                                    if transaction_amount <= 0:
                                        logger.warning(f"Obliczona kwota transakcji jest <= 0: {transaction_amount}")
                                        continue
                                    
                                    logger.info(f"Obliczona kwota transakcji: {transaction_amount} {target_currency}")
                                    
                                    # KROK 1.1.2.1.2: Wykonaj transakcję na giełdzie
                                    asset_dict = {'asset': asset_name, 'quote': quote_name}
                                    transaction_result = await self._execute_transaction(
                                        exchange, transaction_action, strategy, asset_dict, transaction_amount
                                    )
                                    
                                    if not transaction_result:
                                        logger.error(f"Nie udało się wykonać transakcji na giełdzie {exchange_name}")
                                        error_count += 1
                                        continue
                                    
                                    # KROK 1.1.2.1.3: Zapisz transakcję w bazie danych
                                    # Dla prostoty używamy obliczonej kwoty jako quote_amount i asset_amount
                                    # W rzeczywistej implementacji należy wyciągnąć te wartości z transaction_result
                                    if transaction_action == 'BUY':
                                        quote_amount = transaction_amount
                                        # Dla kupna asset_amount można oszacować lub wyciągnąć z transaction_result
                                        asset_amount = transaction_result.get('bought_asset_size', 0.0)
                                    else:
                                        asset_amount = transaction_amount
                                        # Dla sprzedaży quote_amount można oszacować lub wyciągnąć z transaction_result
                                        quote_amount = transaction_result.get('sold_asset_price', 0.0)
                                    
                                    transaction_id = await self._save_transaction_to_database(
                                        exchange_id=exchange_id,
                                        asset_id=asset_id,
                                        general_interpretation_id=general_interpretation['id'],
                                        transaction_side=transaction_action,
                                        quote_amount=quote_amount,
                                        asset_amount=asset_amount
                                    )
                                    
                                    if transaction_id:
                                        processed_count += 1
                                        logger.info(f"Pomyślnie przetworzono transakcję {transaction_id} dla interpretacji {general_interpretation['id']}")
                                    else:
                                        error_count += 1
                                        logger.error(f"Nie udało się zapisać transakcji dla interpretacji {general_interpretation['id']}")
                                
                                except Exception as e:
                                    error_count += 1
                                    logger.error(f"Błąd podczas przetwarzania konta {account_state.get('id', 'unknown')}: {e}")
                                    continue
                        
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Błąd podczas przetwarzania giełdy {exchange.__class__.__name__}: {e}")
                            continue
                
                except Exception as e:
                    error_count += 1
                    logger.error(f"Błąd podczas przetwarzania interpretacji {general_interpretation.get('id', 'unknown')}: {e}")
                    continue
            
            logger.info(f"=== Synchronizacja transakcji zakończona ===")
            logger.info(f"Przetworzono: {processed_count} transakcji")
            logger.info(f"Błędy: {error_count} transakcji")
            
        except Exception as e:
            logger.error(f"Błąd podczas synchronizacji transakcji: {e}", exc_info=True)
            return None
