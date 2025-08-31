from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ExchangeAccountStateBuyStrategiesTable(AbstractTable):
    """Klasa do zarządzania tabelą ExchangeAccountStateBuyStrategies."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS exchange_account_state_buy_strategies (
            id SERIAL PRIMARY KEY,
            exchange_account_state_id INTEGER NOT NULL UNIQUE,
            is_percent BOOLEAN NOT NULL DEFAULT FALSE,
            type VARCHAR(10) NOT NULL CHECK (type IN ('MARKET', 'LIMIT')),
            movement_amount DECIMAL(20,8) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (exchange_account_state_id) REFERENCES exchange_account_state(id) ON DELETE CASCADE
        );
        """
    
    async def create(self, exchange_account_state_id: int, is_percent: bool, type: str, 
                    movement_amount: float) -> Optional[int]:
        """
        Tworzy nową strategię kupna i zwraca jej ID.
        
        Args:
            exchange_account_state_id: ID stanu konta giełdowego
            is_percent: Czy movement_amount jest procentem (True) czy kwotą bezwzględną (False)
            type: Typ zlecenia ('MARKET' lub 'LIMIT')
            movement_amount: Kwota ruchu (procent lub kwota bezwzględna)
        """
        try:
            # Walidacja typu zlecenia
            if type not in ['MARKET', 'LIMIT']:
                raise ValueError(f"Nieprawidłowy typ zlecenia: {type}. Dozwolone: MARKET, LIMIT")
            
            # Walidacja movement_amount
            if movement_amount <= 0:
                raise ValueError(f"movement_amount musi być większe niż 0, podano: {movement_amount}")
            
            # Jeśli is_percent=True, sprawdź czy wartość jest sensowna (0-100%)
            if is_percent and movement_amount > 100:
                raise ValueError(f"Dla is_percent=True, movement_amount nie powinno przekraczać 100%, podano: {movement_amount}")
            
            strategy_id = await self.fetch_val("""
                INSERT INTO exchange_account_state_buy_strategies 
                (exchange_account_state_id, is_percent, type, movement_amount) 
                VALUES ($1, $2, $3, $4) RETURNING id
            """, exchange_account_state_id, is_percent, type, movement_amount)
            
            logger.info(f"Utworzono strategię kupna: {type} {movement_amount} dla account_state {exchange_account_state_id} z ID: {strategy_id}")
            return strategy_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia strategii kupna: {e}", exc_info=True)
            return None
    
    async def create_many(self, strategies: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Tworzy wiele strategii kupna jednym zapytaniem.
        
        Args:
            strategies: Lista słowników z kluczami: 'exchange_account_state_id', 'is_percent', 'type', 'movement_amount'
                         
        Returns:
            Dict[str, int]: Słownik mapujący klucz strategii na jej ID
        """
        if not strategies:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            for strategy in strategies:
                # Walidacja obowiązkowych pól
                required_fields = ['exchange_account_state_id', 'is_percent', 'type', 'movement_amount']
                for field in required_fields:
                    if field not in strategy:
                        raise ValueError(f"Brak wymaganego pola: {field}")
                
                # Walidacja typu zlecenia
                if strategy['type'] not in ['MARKET', 'LIMIT']:
                    raise ValueError(f"Nieprawidłowy typ zlecenia: {strategy['type']}")
                
                # Walidacja movement_amount
                if strategy['movement_amount'] <= 0:
                    raise ValueError(f"movement_amount musi być większe niż 0")
                
                if strategy['is_percent'] and strategy['movement_amount'] > 100:
                    raise ValueError(f"Dla is_percent=True, movement_amount nie powinno przekraczać 100%")
                
                exchange_account_state_id = strategy['exchange_account_state_id']
                is_percent = strategy['is_percent']
                type_val = strategy['type']
                movement_amount = strategy['movement_amount']
                
                values_list.append(f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2}, ${param_counter + 3})")
                params.extend([exchange_account_state_id, is_percent, type_val, movement_amount])
                param_counter += 4
            
            query = f"""
                INSERT INTO exchange_account_state_buy_strategies 
                (exchange_account_state_id, is_percent, type, movement_amount) 
                VALUES {', '.join(values_list)}
                ON CONFLICT (exchange_account_state_id) DO NOTHING
                RETURNING id, exchange_account_state_id
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_strategies = {}
            for result in results:
                key = str(result['exchange_account_state_id'])
                created_strategies[key] = result['id']
            
            logger.info(f"Utworzono {len(created_strategies)} nowych strategii kupna z {len(strategies)} prób")
            return created_strategies
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu strategii kupna: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera strategię kupna po ID wraz z informacjami o stanie konta."""
        return await self.fetch_one("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eabs.id = $1
        """, record_id)
    
    async def get_by_exchange_account_state_id(self, exchange_account_state_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera strategię kupna dla konkretnego stanu konta (relacja 1:1)."""
        return await self.fetch_one("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eabs.exchange_account_state_id = $1
        """, exchange_account_state_id)
    
    async def get_by_exchange_id(self, exchange_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie strategie kupna dla danej giełdy."""
        return await self.fetch_all("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eas.exchange_id = $1
            ORDER BY eas.type, eas.currency
            LIMIT $2 OFFSET $3
        """, exchange_id, limit, offset)
    
    async def get_by_strategy_type(self, strategy_type: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera strategie kupna według typu (MARKET/LIMIT)."""
        if strategy_type not in ['MARKET', 'LIMIT']:
            raise ValueError(f"Nieprawidłowy typ strategii: {strategy_type}")
            
        return await self.fetch_all("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eabs.type = $1
            ORDER BY e.name, eas.type, eas.currency
            LIMIT $2 OFFSET $3
        """, strategy_type, limit, offset)
    
    async def get_percent_based_strategies(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera strategie bazujące na procentach."""
        return await self.fetch_all("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eabs.is_percent = TRUE
            ORDER BY eabs.movement_amount DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_absolute_amount_strategies(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera strategie bazujące na kwotach bezwzględnych."""
        return await self.fetch_all("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            WHERE eabs.is_percent = FALSE
            ORDER BY eabs.movement_amount DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje strategię kupna o podanym ID."""
        try:
            # Sprawdź jakie pola są dostępne do aktualizacji
            allowed_fields = ['exchange_account_state_id', 'is_percent', 'type', 'movement_amount']
            update_fields = []
            params = []
            param_counter = 1
            
            for field, value in kwargs.items():
                if field in allowed_fields:
                    if field == 'type' and value not in ['MARKET', 'LIMIT']:
                        raise ValueError(f"Nieprawidłowy typ zlecenia: {value}")
                    
                    if field == 'movement_amount' and value <= 0:
                        raise ValueError(f"movement_amount musi być większe niż 0")
                    
                    # Jeśli aktualizujemy is_percent na True, sprawdź movement_amount
                    if field == 'is_percent' and value and 'movement_amount' in kwargs and kwargs['movement_amount'] > 100:
                        raise ValueError(f"Dla is_percent=True, movement_amount nie powinno przekraczać 100%")
                    
                    update_fields.append(f"{field} = ${param_counter}")
                    params.append(value)
                    param_counter += 1
            
            if not update_fields:
                logger.warning(f"Brak dozwolonych pól do aktualizacji dla strategii kupna {record_id}")
                return False
            
            # Dodaj updated_at
            update_fields.append(f"updated_at = ${param_counter}")
            params.append(datetime.now())
            param_counter += 1
            
            # Dodaj record_id jako ostatni parametr
            params.append(record_id)
            
            query = f"""
                UPDATE exchange_account_state_buy_strategies 
                SET {', '.join(update_fields)}
                WHERE id = ${param_counter}
            """
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano strategię kupna z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji strategii kupna: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa strategię kupna o podanym ID."""
        try:
            await self.execute_query("DELETE FROM exchange_account_state_buy_strategies WHERE id = $1", record_id)
            logger.info(f"Usunięto strategię kupna z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania strategii kupna: {e}", exc_info=True)
            return False
    
    async def delete_by_exchange_account_state_id(self, exchange_account_state_id: int) -> bool:
        """Usuwa strategię kupna dla konkretnego stanu konta."""
        try:
            await self.execute_query(
                "DELETE FROM exchange_account_state_buy_strategies WHERE exchange_account_state_id = $1",
                exchange_account_state_id
            )
            logger.info(f"Usunięto strategię kupna dla account_state_id: {exchange_account_state_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania strategii kupna dla account_state_id: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie strategie kupna z limitem i offsetem."""
        return await self.fetch_all("""
            SELECT eabs.id, eabs.exchange_account_state_id, eabs.is_percent, eabs.type, 
                   eabs.movement_amount, eabs.created_at, eabs.updated_at,
                   eas.exchange_id, eas.type as account_type, eas.currency, eas.amount as account_amount,
                   e.name as exchange_name, e.display_name as exchange_display_name
            FROM exchange_account_state_buy_strategies eabs
            JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
            JOIN exchanges e ON eas.exchange_id = e.id
            ORDER BY e.name, eas.type, eas.currency
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def calculate_buy_amount(self, strategy_id: int) -> Optional[float]:
        """
        Oblicza rzeczywistą kwotę do zakupu na podstawie strategii.
        
        Returns:
            float: Kwota do zakupu lub None jeśli strategia nie istnieje
        """
        try:
            result = await self.fetch_one("""
                SELECT eabs.is_percent, eabs.movement_amount,
                       eas.amount as account_amount
                FROM exchange_account_state_buy_strategies eabs
                JOIN exchange_account_state eas ON eabs.exchange_account_state_id = eas.id
                WHERE eabs.id = $1
            """, strategy_id)
            
            if not result:
                return None
            
            if result['is_percent']:
                # Oblicz procent z salda konta
                buy_amount = (result['account_amount'] * result['movement_amount']) / 100
            else:
                # Użyj kwoty bezwzględnej
                buy_amount = result['movement_amount']
            
            logger.info(f"Obliczono kwotę zakupu dla strategii {strategy_id}: {buy_amount}")
            return float(buy_amount)
            
        except Exception as e:
            logger.error(f"Błąd podczas obliczania kwoty zakupu: {e}", exc_info=True)
            return None
