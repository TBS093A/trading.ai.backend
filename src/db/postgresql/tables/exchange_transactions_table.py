from typing import Optional, Dict, Any, List
from .abstract_table import AbstractTable
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ExchangeTransactionsTable(AbstractTable):
    """Klasa do zarządzania tabelą ExchangeTransactions."""
    
    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS exchange_transactions (
            id SERIAL PRIMARY KEY,
            exchange_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            general_interpretation_id INTEGER,
            type VARCHAR(4) NOT NULL CHECK (type IN ('BUY', 'SELL')),
            quote_amount DECIMAL(20,8) NOT NULL,
            asset_amount DECIMAL(20,8) NOT NULL,
            created_at BIGINT NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()) * 1000,
            FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            FOREIGN KEY (general_interpretation_id) REFERENCES general_interpretation(id) ON DELETE SET NULL
        );
        """
    
    async def create(self, exchange_id: int, asset_id: int, type: str, quote_amount: float, 
                    asset_amount: float, general_interpretation_id: Optional[int] = None, 
                    created_at: Optional[int] = None) -> Optional[int]:
        """
        Tworzy nową transakcję i zwraca jej ID.
        
        Args:
            exchange_id: ID giełdy
            asset_id: ID asseta
            type: Typ transakcji ('BUY' lub 'SELL')
            quote_amount: Ilość waluty bazowej (quote)
            asset_amount: Ilość asseta
            general_interpretation_id: Opcjonalne ID interpretacji generalnej
            created_at: Opcjonalny timestamp (domyślnie bieżący czas w ms)
        """
        try:
            # Walidacja typu transakcji
            if type not in ['BUY', 'SELL']:
                raise ValueError(f"Nieprawidłowy typ transakcji: {type}. Dozwolone: BUY, SELL")
            
            # Jeśli created_at nie został podany, użyj aktualnego czasu w milisekundach
            if created_at is None:
                created_at = int(datetime.now().timestamp() * 1000)
            
            if general_interpretation_id is not None:
                transaction_id = await self.fetch_val("""
                    INSERT INTO exchange_transactions 
                    (exchange_id, asset_id, general_interpretation_id, type, quote_amount, asset_amount, created_at) 
                    VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id
                """, exchange_id, asset_id, general_interpretation_id, type, quote_amount, asset_amount, created_at)
            else:
                transaction_id = await self.fetch_val("""
                    INSERT INTO exchange_transactions 
                    (exchange_id, asset_id, type, quote_amount, asset_amount, created_at) 
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING id
                """, exchange_id, asset_id, type, quote_amount, asset_amount, created_at)
            
            logger.info(f"Utworzono transakcję: {type} {asset_amount} na giełdzie {exchange_id} z ID: {transaction_id}")
            return transaction_id
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia transakcji: {e}", exc_info=True)
            return None
    
    async def create_many(self, transactions: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Tworzy wiele transakcji jednym zapytaniem.
        
        Args:
            transactions: Lista słowników z kluczami: 'exchange_id', 'asset_id', 'type', 
                         'quote_amount', 'asset_amount', opcjonalnie 'general_interpretation_id', 'created_at'
                         
        Returns:
            Dict[str, int]: Słownik mapujący klucz transakcji na jej ID
        """
        if not transactions:
            return {}
        
        try:
            # Przygotuj parametry dla zapytania
            values_list = []
            params = []
            param_counter = 1
            
            current_timestamp = int(datetime.now().timestamp() * 1000)
            
            for transaction in transactions:
                # Walidacja obowiązkowych pól
                required_fields = ['exchange_id', 'asset_id', 'type', 'quote_amount', 'asset_amount']
                for field in required_fields:
                    if field not in transaction:
                        raise ValueError(f"Brak wymaganego pola: {field}")
                
                # Walidacja typu transakcji
                if transaction['type'] not in ['BUY', 'SELL']:
                    raise ValueError(f"Nieprawidłowy typ transakcji: {transaction['type']}")
                
                exchange_id = transaction['exchange_id']
                asset_id = transaction['asset_id']
                general_interpretation_id = transaction.get('general_interpretation_id')
                type_val = transaction['type']
                quote_amount = transaction['quote_amount']
                asset_amount = transaction['asset_amount']
                created_at = transaction.get('created_at', current_timestamp)
                
                values_list.append(f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2}, ${param_counter + 3}, ${param_counter + 4}, ${param_counter + 5}, ${param_counter + 6})")
                params.extend([exchange_id, asset_id, general_interpretation_id, type_val, quote_amount, asset_amount, created_at])
                param_counter += 7
            
            query = f"""
                INSERT INTO exchange_transactions 
                (exchange_id, asset_id, general_interpretation_id, type, quote_amount, asset_amount, created_at) 
                VALUES {', '.join(values_list)}
                RETURNING id, exchange_id, asset_id, type, quote_amount, asset_amount
            """
            
            results = await self.fetch_all(query, *params)
            
            # Mapuj wyniki na słownik
            created_transactions = {}
            for i, result in enumerate(results):
                # Utwórz unikalny klucz dla transakcji
                key = f"{result['exchange_id']}:{result['asset_id']}:{result['type']}:{i}"
                created_transactions[key] = result['id']
            
            logger.info(f"Utworzono {len(created_transactions)} nowych transakcji z {len(transactions)} prób")
            return created_transactions
            
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia wielu transakcji: {e}", exc_info=True)
            return {}
    
    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Pobiera transakcję po ID wraz z informacjami o powiązanych rekordach."""
        return await self.fetch_one("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            WHERE et.id = $1
        """, record_id)
    
    async def get_by_asset_id(self, asset_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie transakcje dla danego asseta."""
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            WHERE et.asset_id = $1
            ORDER BY et.created_at DESC
            LIMIT $2 OFFSET $3
        """, asset_id, limit, offset)
    
    async def get_by_exchange_id(self, exchange_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie transakcje dla danej giełdy."""
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            WHERE et.exchange_id = $1
            ORDER BY et.created_at DESC
            LIMIT $2 OFFSET $3
        """, exchange_id, limit, offset)
    
    async def get_by_interpretation_id(self, interpretation_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie transakcje dla danej interpretacji."""
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            WHERE et.general_interpretation_id = $1
            ORDER BY et.created_at DESC
            LIMIT $2 OFFSET $3
        """, interpretation_id, limit, offset)
    
    async def get_by_type(self, transaction_type: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie transakcje danego typu (BUY/SELL)."""
        if transaction_type not in ['BUY', 'SELL']:
            raise ValueError(f"Nieprawidłowy typ transakcji: {transaction_type}")
            
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            WHERE et.type = $1
            ORDER BY et.created_at DESC
            LIMIT $2 OFFSET $3
        """, transaction_type, limit, offset)
    
    async def get_by_date_range(self, start_timestamp: int, end_timestamp: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera transakcje z określonego zakresu czasowego."""
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            WHERE et.created_at >= $1 AND et.created_at <= $2
            ORDER BY et.created_at DESC
            LIMIT $3 OFFSET $4
        """, start_timestamp, end_timestamp, limit, offset)
    
    async def get_transactions_without_interpretation(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera transakcje które nie mają przypisanej interpretacji."""
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            WHERE et.general_interpretation_id IS NULL
            ORDER BY et.created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def update(self, record_id: int, **kwargs) -> bool:
        """Aktualizuje transakcję o podanym ID."""
        try:
            # Sprawdź jakie pola są dostępne do aktualizacji
            allowed_fields = ['exchange_id', 'asset_id', 'general_interpretation_id', 'type', 'quote_amount', 'asset_amount']
            update_fields = []
            params = []
            param_counter = 1
            
            for field, value in kwargs.items():
                if field in allowed_fields:
                    if field == 'type' and value not in ['BUY', 'SELL']:
                        raise ValueError(f"Nieprawidłowy typ transakcji: {value}")
                    
                    update_fields.append(f"{field} = ${param_counter}")
                    params.append(value)
                    param_counter += 1
            
            if not update_fields:
                logger.warning(f"Brak dozwolonych pól do aktualizacji dla transakcji {record_id}")
                return False
            
            # Dodaj record_id jako ostatni parametr
            params.append(record_id)
            
            query = f"""
                UPDATE exchange_transactions 
                SET {', '.join(update_fields)}
                WHERE id = ${param_counter}
            """
            
            await self.execute_query(query, *params)
            logger.info(f"Zaktualizowano transakcję z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas aktualizacji transakcji: {e}", exc_info=True)
            return False
    
    async def delete(self, record_id: int) -> bool:
        """Usuwa transakcję o podanym ID."""
        try:
            await self.execute_query("DELETE FROM exchange_transactions WHERE id = $1", record_id)
            logger.info(f"Usunięto transakcję z ID: {record_id}")
            return True
        except Exception as e:
            logger.error(f"Błąd podczas usuwania transakcji: {e}", exc_info=True)
            return False
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Pobiera wszystkie transakcje z limitem i offsetem."""
        return await self.fetch_all("""
            SELECT et.id, et.exchange_id, et.asset_id, et.general_interpretation_id,
                   et.type, et.quote_amount, et.asset_amount, et.created_at,
                   e.name as exchange_name, e.display_name as exchange_display_name,
                   a.asset, a.quote,
                   gi.title as interpretation_title
            FROM exchange_transactions et
            JOIN exchanges e ON et.exchange_id = e.id
            JOIN assets a ON et.asset_id = a.id
            LEFT JOIN general_interpretation gi ON et.general_interpretation_id = gi.id
            ORDER BY et.created_at DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
    
    async def get_portfolio_summary_by_asset(self, asset_id: int) -> Optional[Dict[str, Any]]:
        """
        Pobiera podsumowanie portfela dla danego asseta (łączne kupno/sprzedaż).
        
        Returns:
            Dict zawierający: total_bought, total_sold, net_position, avg_buy_price, avg_sell_price
        """
        return await self.fetch_one("""
            SELECT 
                a.id as asset_id,
                a.asset,
                a.quote,
                COALESCE(SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END), 0) as total_bought,
                COALESCE(SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END), 0) as total_sold,
                COALESCE(SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END), 0) - 
                COALESCE(SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END), 0) as net_position,
                CASE 
                    WHEN SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END) > 0 THEN
                        SUM(CASE WHEN et.type = 'BUY' THEN et.quote_amount END) / 
                        SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END)
                    ELSE NULL
                END as avg_buy_price,
                CASE 
                    WHEN SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END) > 0 THEN
                        SUM(CASE WHEN et.type = 'SELL' THEN et.quote_amount END) / 
                        SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END)
                    ELSE NULL
                END as avg_sell_price
            FROM assets a
            LEFT JOIN exchange_transactions et ON a.id = et.asset_id
            WHERE a.id = $1
            GROUP BY a.id, a.asset, a.quote
        """, asset_id)
    
    async def get_portfolio_summary_by_exchange(self, exchange_id: int) -> List[Dict[str, Any]]:
        """Pobiera podsumowanie portfela dla danej giełdy (wszystkie assety)."""
        return await self.fetch_all("""
            SELECT 
                a.id as asset_id,
                a.asset,
                a.quote,
                e.name as exchange_name,
                COALESCE(SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END), 0) as total_bought,
                COALESCE(SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END), 0) as total_sold,
                COALESCE(SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END), 0) - 
                COALESCE(SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END), 0) as net_position,
                CASE 
                    WHEN SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END) > 0 THEN
                        SUM(CASE WHEN et.type = 'BUY' THEN et.quote_amount END) / 
                        SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END)
                    ELSE NULL
                END as avg_buy_price,
                CASE 
                    WHEN SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END) > 0 THEN
                        SUM(CASE WHEN et.type = 'SELL' THEN et.quote_amount END) / 
                        SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END)
                    ELSE NULL
                END as avg_sell_price
            FROM assets a
            JOIN exchange_transactions et ON a.id = et.asset_id
            JOIN exchanges e ON et.exchange_id = e.id
            WHERE et.exchange_id = $1
            GROUP BY a.id, a.asset, a.quote, e.name
            HAVING COALESCE(SUM(CASE WHEN et.type = 'BUY' THEN et.asset_amount END), 0) - 
                   COALESCE(SUM(CASE WHEN et.type = 'SELL' THEN et.asset_amount END), 0) != 0
            ORDER BY a.asset
        """, exchange_id)
