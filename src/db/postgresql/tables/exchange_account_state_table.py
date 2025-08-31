from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ExchangeAccountStateTable(AbstractTable):
    """Klasa do zarządzania tabelą ExchangeAccountState."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS exchange_account_state (
            id SERIAL PRIMARY KEY,
            exchange_id INTEGER NOT NULL,
            type VARCHAR(10) NOT NULL CHECK (type IN ('SPOT', 'FUTURES')),
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            currency VARCHAR(10) NOT NULL,
            amount DECIMAL(20,8) NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(exchange_id, type, currency),
            FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE
        );
        """
    
    async def create(self, exchange_id: int, type: str, currency: str, amount: float = 0.0, 
                    is_enabled: bool = True) -> Optional[int]:
        """
        Tworzy nowy stan konta i zwraca jego ID.
        
        Args:
            exchange_id: ID giełdy
            type: Typ konta ('SPOT', 'FUTURES')
            currency: Waluta (np. 'BTC', 'ETH', 'USDT')
            amount: Ilość waluty na koncie
            is_enabled: Czy konto jest aktywne
        """
        try:
            # Walidacja typu konta
            if type not in ['SPOT', 'FUTURES']:
                raise ValueError(f"Nieprawidłowy typ konta: {type}. Dozwolone: SPOT, MARGIN, FUTURES")
            
            account_state_id = await self.fetch_val("""
                INSERT INTO exchange_account_state 
                (exchange_id, type, currency, amount, is_enabled) 
                VALUES ($1, $2, $3, $4, $5) RETURNING id
            """, exchange_id, type, currency, amount, is_enabled)
            
            logger.info(f"Utworzono stan konta: {type} {currency} na giełdzie {exchange_id} z ID: {account_state_id}")
            return account_state_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia stanu konta: {e}", exc_info=True)
            return None
    
    async def create_many(self, account_states: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Tworzy wiele stanów kont jednym zapytaniem.
        
        Args:
            account_states: Lista słowników z kluczami: 'exchange_id', 'type', 'currency', 
                           opcjonalnie 'amount', 'is_enabled'
                         
        Returns:
            Dict[str, int]: Słownik mapujący klucz stanu konta na jego ID
        """
        if not account_states:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            for account_state in account_states:
                # Walidacja obowiązkowych pól
                required_fields = ['exchange_id', 'type', 'currency']
                for field in required_fields:
                    if field not in account_state:
                        raise ValueError(f"Brak wymaganego pola: {field}")
                
                # Walidacja typu konta
                if account_state['type'] not in ['SPOT', 'FUTURES']:
                    raise ValueError(f"Nieprawidłowy typ konta: {account_state['type']}")
                
                exchange_id = account_state['exchange_id']
                type_val = account_state['type']
                currency = account_state['currency']
                amount = account_state.get('amount', 0.0)
                is_enabled = account_state.get('is_enabled', True)
                
                values_list.append(f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2}, ${param_counter + 3}, ${param_counter + 4})")
                params.extend([exchange_id, type_val, currency, amount, is_enabled])
                param_counter += 5
            
            query = f"""
                INSERT INTO exchange_account_state 
                (exchange_id, type, currency, amount, is_enabled) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (exchange_id, type, currency) DO NOTHING
                RETURNING id, exchange_id, type, currency
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_states = {}
            for result in results:
                # Utwórz unikalny klucz dla stanu konta
                key = f"{result['exchange_id']}:{result['type']}:{result['currency']}"
                created_states[key] = result['id']
            
            logger.info(f"Utworzono {len(created_states)} nowych stanów kont z {len(account_states)} prób")
            return created_states
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu stanów kont: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera stan konta po ID wraz z informacjami o powiązanej giełdzie."""
        return await self.fetch_one("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.id = $1
        """, record_id)
    
    async def get_by_exchange_id(self, exchange_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie stany kont dla danej giełdy."""
        return await self.fetch_all("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.exchange_id = $1
            ORDER BY eas.type, eas.currency
            LIMIT $2 OFFSET $3
        """, exchange_id, limit, offset)
    
    async def get_by_exchange_and_type(self, exchange_id: int, account_type: str, 
                                      limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera stany kont dla danej giełdy i typu konta."""
        if account_type not in ['SPOT', 'FUTURES']:
            raise ValueError(f"Nieprawidłowy typ konta: {account_type}")
            
        return await self.fetch_all("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.exchange_id = $1 AND eas.type = $2
            ORDER BY eas.currency
            LIMIT $3 OFFSET $4
        """, exchange_id, account_type, limit, offset)
    
    async def get_by_currency(self, currency: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie stany kont dla danej waluty."""
        return await self.fetch_all("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.currency = $1
            ORDER BY e.name, eas.type
            LIMIT $2 OFFSET $3
        """, currency, limit, offset)
    
    async def get_enabled_accounts(self, exchange_id: Optional[int] = None, 
                                  limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie aktywne konta (is_enabled = True)."""
        if exchange_id is not None:
            return await self.fetch_all("""
                SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                       eas.amount, eas.created_at, eas.updated_at,
                       e.name as exchange_name, e.display_name as exchange_display_name
                FROM exchange_account_state eas
                JOIN exchanges e ON eas.exchange_id = e.id
                WHERE eas.is_enabled = TRUE AND eas.exchange_id = $1
                ORDER BY e.name, eas.type, eas.currency
                LIMIT $2 OFFSET $3
            """, exchange_id, limit, offset)
        else:
            return await self.fetch_all("""
                SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                       eas.amount, eas.created_at, eas.updated_at,
                       e.name as exchange_name, e.display_name as exchange_display_name
                FROM exchange_account_state eas
                JOIN exchanges e ON eas.exchange_id = e.id
                WHERE eas.is_enabled = TRUE
                ORDER BY e.name, eas.type, eas.currency
                LIMIT $1 OFFSET $2
            """, limit, offset)
    
    async def get_accounts_with_balance(self, min_amount: float = 0.0, 
                                       limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera konta które mają saldo większe niż podana wartość."""
        return await self.fetch_all("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.amount > $1
            ORDER BY eas.amount DESC
            LIMIT $2 OFFSET $3
        """, min_amount, limit, offset)
    
    async def get_specific_account(self, exchange_id: int, account_type: str, currency: str) -> Optional[Dict[str, Any]]:
        """Pobiera konkretny stan konta po exchange_id, typie i walucie."""
        if account_type not in ['SPOT', 'FUTURES']:
            raise ValueError(f"Nieprawidłowy typ konta: {account_type}")
            
        return await self.fetch_one("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.exchange_id = $1 AND eas.type = $2 AND eas.currency = $3
        """, exchange_id, account_type, currency)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje stan konta o podanym ID."""
        try:
            # Sprawdź jakie pola są dostępne do aktualizacji
            allowed_fields = ['exchange_id', 'type', 'is_enabled', 'currency', 'amount']
            update_fields = []
            params = []
            param_counter = 1
            
            for field, value in kwargs.items():
                if field in allowed_fields:
                    if field == 'type' and value not in ['SPOT', 'FUTURES']:
                        raise ValueError(f"Nieprawidłowy typ konta: {value}")
                    
                    update_fields.append(f"{field} = ${param_counter}")
                    params.append(value)
                    param_counter += 1
            
            if not update_fields:
                logger.warning(f"Brak dozwolonych pól do aktualizacji dla stanu konta {record_id}")
                return False
            
            # Dodaj updated_at
            update_fields.append(f"updated_at = ${param_counter}")
            params.append(datetime.now())
            param_counter += 1
            
            # Dodaj record_id jako ostatni parametr
            params.append(record_id)
            
            query = f"""
                UPDATE exchange_account_state 
                SET {', '.join(update_fields)}
                WHERE id = ${param_counter}
            """
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano stan konta z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji stanu konta: {e}", exc_info=True)
            return False
    
    async def update_amount(self, record_id: int, new_amount: float) -> bool:
        """Aktualizuje tylko saldo na koncie."""
        return await self.update(record_id, amount=new_amount)
    
    async def update_specific_account_amount(self, exchange_id: int, account_type: str, 
                                           currency: str, new_amount: float) -> bool:
        """Aktualizuje saldo konkretnego konta po exchange_id, typie i walucie."""
        try:
            if account_type not in ['SPOT', 'FUTURES']:
                raise ValueError(f"Nieprawidłowy typ konta: {account_type}")
            
            await self.execute_query("""
                UPDATE exchange_account_state 
                SET amount = $1, updated_at = $2
                WHERE exchange_id = $3 AND type = $4 AND currency = $5
            """, new_amount, datetime.now(), exchange_id, account_type, currency)
            
            logger.info(f"Zaktualizowano saldo konta: {account_type} {currency} na giełdzie {exchange_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji salda konta: {e}", exc_info=True)
            return False
    
    async def toggle_account_status(self, record_id: int) -> bool:
        """Zmienia status konta na przeciwny (enabled <-> disabled)."""
        try:
            await self.execute_query("""
                UPDATE exchange_account_state 
                SET is_enabled = NOT is_enabled, updated_at = $1
                WHERE id = $2
            """, datetime.now(), record_id)
            
            logger.info(f"Zmieniono status konta z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas zmiany statusu konta: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa stan konta o podanym ID."""
        try:
            await self.execute_query("DELETE FROM exchange_account_state WHERE id = $1", record_id)
            logger.info(f"Usunięto stan konta z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania stanu konta: {e}", exc_info=True)
            return False
    
    async def delete_by_exchange_and_currency(self, exchange_id: int, account_type: str, currency: str) -> bool:
        """Usuwa konkretny stan konta po exchange_id, typie i walucie."""
        try:
            if account_type not in ['SPOT', 'FUTURES']:
                raise ValueError(f"Nieprawidłowy typ konta: {account_type}")
                
            await self.execute_query(
                "DELETE FROM exchange_account_state WHERE exchange_id = $1 AND type = $2 AND currency = $3",
                exchange_id, account_type, currency
            )
            logger.info(f"Usunięto stan konta: {account_type} {currency} na giełdzie {exchange_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania stanu konta: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie stany kont z limitem i offsetem."""
        return await self.fetch_all("""
            SELECT eas.id, eas.exchange_id, eas.type, eas.is_enabled, eas.currency, 
                   eas.amount, eas.created_at, eas.updated_at,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            ORDER BY e.name, eas.type, eas.currency
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_portfolio_summary_by_exchange(self, exchange_id: int) -> List[Dict[str, Any]]:
        """Pobiera podsumowanie portfela dla danej giełdy (wszystkie waluty i typy kont)."""
        return await self.fetch_all("""
            SELECT 
                e.name as exchange_name,
                eas.type as account_type,
                eas.currency,
                SUM(eas.amount) as total_amount,
                COUNT(*) as accounts_count,
                COUNT(CASE WHEN eas.is_enabled THEN 1 END) as enabled_accounts,
                MAX(eas.updated_at) as last_updated
            FROM exchange_account_state eas
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.exchange_id = $1
            GROUP BY e.name, eas.type, eas.currency
            HAVING SUM(eas.amount) > 0
            ORDER BY eas.type, eas.currency
        """, exchange_id)
    
    async def get_total_balance_by_currency(self, currency: str) -> Optional[Dict[str, Any]]:
        """Pobiera łączne saldo dla danej waluty na wszystkich giełdach i kontach."""
        return await self.fetch_one("""
            SELECT 
                eas.currency,
                SUM(eas.amount) as total_amount,
                COUNT(*) as accounts_count,
                COUNT(DISTINCT eas.exchange_id) as exchanges_count,
                COUNT(CASE WHEN eas.is_enabled THEN 1 END) as enabled_accounts
            FROM exchange_account_state eas
            WHERE eas.currency = $1
            GROUP BY eas.currency
        """, currency)
