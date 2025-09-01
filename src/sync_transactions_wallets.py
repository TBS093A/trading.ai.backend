import logging
import traceback
from typing import List, Dict, Any, Optional
from .api import ApiFacade
from .db.database_facade import DatabaseFacade

logger = logging.getLogger(__name__)


class TransactionsWallets:
    """
    Klasa odpowiedzialna za synchronizację portfeli/walletów z giełd z bazą danych.
    Pobiera aktualne stany kont z API exchanges i aktualizuje bazę danych.
    """
    
    def __init__(self, test_mode: bool = False):
        """
        Inicjalizacja klasy TransactionsWallets
        
        Args:
            test_mode: Czy uruchamiać w trybie testowym
        """
        self.test_mode = test_mode
        self.api_facade = ApiFacade()
        self.exchanges = self.api_facade.get_fabric().get_exchanges_apis()
        
        # Inicjalizacja bazy danych
        if not self.test_mode:
            self.db = DatabaseFacade().get_database_postgresql()
        else:
            self.db = DatabaseFacade().get_test_database_postgresql()

    async def _get_exchange_id_by_name(self, exchange_name: str) -> Optional[int]:
        """
        Pobiera ID giełdy z bazy danych na podstawie nazwy.
        
        Args:
            exchange_name: Nazwa giełdy (np. "BINANCE", "MEXC")
            
        Returns:
            Optional[int]: ID giełdy lub None jeśli nie znaleziono
        """
        try:
            exchanges_table = self.db.get_factory().get_exchanges_table()
            exchange_record = await exchanges_table.get_by_name(exchange_name)
            
            if exchange_record:
                return exchange_record['id']
            else:
                logger.warning(f"Nie znaleziono giełdy o nazwie: {exchange_name}")
                return None
                
        except Exception as e:
            logger.error(f"Błąd podczas pobierania ID giełdy {exchange_name}: {e}", exc_info=True)
            return None

    async def _update_or_create_wallet_record(self, exchange_id: int, wallet_info: Dict[str, Any]) -> bool:
        """
        Aktualizuje lub tworzy rekord portfela w bazie danych.
        
        Args:
            exchange_id: ID giełdy w bazie danych
            wallet_info: Informacje o portfelu z API
            
        Returns:
            bool: True jeśli operacja się powiodła
        """
        try:
            exchange_account_state_table = self.db.get_factory().get_exchange_account_state_table()
            
            # Sprawdź czy rekord już istnieje
            existing_record = await exchange_account_state_table.get_specific_account(
                exchange_id=exchange_id,
                account_type=wallet_info['type'],
                currency=wallet_info['currency']
            )
            
            if existing_record:
                # Aktualizuj istniejący rekord
                success = await exchange_account_state_table.update_specific_account_amount(
                    exchange_id=exchange_id,
                    account_type=wallet_info['type'],
                    currency=wallet_info['currency'],
                    new_amount=wallet_info['amount']
                )
                
                if success:
                    logger.info(f"Zaktualizowano wallet: {wallet_info['type']} {wallet_info['currency']} "
                              f"na giełdzie {exchange_id}, nowe saldo: {wallet_info['amount']}")
                    return True
                else:
                    logger.error(f"Błąd podczas aktualizacji wallet: {wallet_info}")
                    return False
            else:
                # Utwórz nowy rekord
                record_id = await exchange_account_state_table.create(
                    exchange_id=exchange_id,
                    type=wallet_info['type'],
                    currency=wallet_info['currency'],
                    amount=wallet_info['amount'],
                    is_enabled=wallet_info['is_enabled']
                )
                
                if record_id:
                    logger.info(f"Utworzono nowy wallet: {wallet_info['type']} {wallet_info['currency']} "
                              f"na giełdzie {exchange_id}, saldo: {wallet_info['amount']}, ID: {record_id}")
                    return True
                else:
                    logger.error(f"Błąd podczas tworzenia wallet: {wallet_info}")
                    return False
                    
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji/tworzenia rekordu wallet: {e}", exc_info=True)
            return False

    async def sync(self) -> Dict[str, Any]:
        """
        Synchronizuje portfele ze wszystkich giełd z bazą danych.
        
        Returns:
            Dict[str, Any]: Raport z synchronizacji
        """
        logger.info("Rozpoczynam synchronizację portfeli z giełd")
        
        sync_report = {
            'total_exchanges': len(self.exchanges),
            'successful_exchanges': 0,
            'failed_exchanges': 0,
            'total_wallets_processed': 0,
            'successful_wallets': 0,
            'failed_wallets': 0,
            'exchanges_details': {}
        }
        
        try:
            # Iteruj po wszystkich exchange API
            for exchange in self.exchanges:
                exchange_name = getattr(exchange, 'EXCHANGE_NAME', exchange.__class__.__name__)
                logger.info(f"Synchronizuję portfele z giełdy: {exchange_name}")
                
                exchange_details = {
                    'wallets_processed': 0,
                    'successful_wallets': 0,
                    'failed_wallets': 0,
                    'errors': []
                }
                
                try:
                    # Pobierz ID giełdy z bazy danych
                    exchange_id = await self._get_exchange_id_by_name(exchange_name)
                    
                    if exchange_id is None:
                        error_msg = f"Nie można znaleźć ID giełdy dla: {exchange_name}"
                        logger.error(error_msg)
                        exchange_details['errors'].append(error_msg)
                        sync_report['failed_exchanges'] += 1
                        sync_report['exchanges_details'][exchange_name] = exchange_details
                        continue
                    
                    # Pobierz informacje o portfelach z API giełdy
                    try:
                        wallets_info = exchange._get_wallet_information()
                        logger.info(f"Pobrano {len(wallets_info)} portfeli z {exchange_name}")
                        
                    except Exception as e:
                        error_msg = f"Błąd podczas pobierania portfeli z API {exchange_name}: {e}"
                        logger.error(error_msg, exc_info=True)
                        exchange_details['errors'].append(error_msg)
                        sync_report['failed_exchanges'] += 1
                        sync_report['exchanges_details'][exchange_name] = exchange_details
                        continue
                    
                    # Przetwórz każdy portfel
                    for wallet_info in wallets_info:
                        exchange_details['wallets_processed'] += 1
                        sync_report['total_wallets_processed'] += 1
                        
                        try:
                            # Walidacja danych portfela
                            required_fields = ['type', 'currency', 'amount', 'is_enabled']
                            for field in required_fields:
                                if field not in wallet_info:
                                    raise ValueError(f"Brak wymaganego pola w danych portfela: {field}")
                            
                            # Aktualizuj lub utwórz rekord w bazie
                            success = await self._update_or_create_wallet_record(exchange_id, wallet_info)
                            
                            if success:
                                exchange_details['successful_wallets'] += 1
                                sync_report['successful_wallets'] += 1
                            else:
                                exchange_details['failed_wallets'] += 1
                                sync_report['failed_wallets'] += 1
                                
                        except Exception as e:
                            error_msg = f"Błąd podczas przetwarzania portfela {wallet_info}: {e}"
                            logger.error(error_msg, exc_info=True)
                            exchange_details['errors'].append(error_msg)
                            exchange_details['failed_wallets'] += 1
                            sync_report['failed_wallets'] += 1
                    
                    # Oznacz giełdę jako pomyślnie przetworzoną jeśli nie było błędów
                    if len(exchange_details['errors']) == 0:
                        sync_report['successful_exchanges'] += 1
                        logger.info(f"Pomyślnie zsynchronizowano portfele z giełdy {exchange_name}: "
                                  f"{exchange_details['successful_wallets']}/{exchange_details['wallets_processed']}")
                    else:
                        sync_report['failed_exchanges'] += 1
                        
                except Exception as e:
                    error_msg = f"Nieprzewidziany błąd podczas synchronizacji giełdy {exchange_name}: {e}"
                    logger.error(error_msg, exc_info=True)
                    exchange_details['errors'].append(error_msg)
                    sync_report['failed_exchanges'] += 1
                
                sync_report['exchanges_details'][exchange_name] = exchange_details
            
            # Podsumowanie synchronizacji
            logger.info(f"Zakończono synchronizację portfeli. Podsumowanie:")
            logger.info(f"  - Giełdy: {sync_report['successful_exchanges']}/{sync_report['total_exchanges']} pomyślnych")
            logger.info(f"  - Portfele: {sync_report['successful_wallets']}/{sync_report['total_wallets_processed']} pomyślnych")
            
            if sync_report['failed_exchanges'] > 0 or sync_report['failed_wallets'] > 0:
                logger.warning(f"  - Błędy: {sync_report['failed_exchanges']} giełd, {sync_report['failed_wallets']} portfeli")
            
            return sync_report
            
        except Exception as e:
            logger.error(f"Krytyczny błąd podczas synchronizacji portfeli: {e}", exc_info=True)
            return sync_report
