# Struktura bazy danych - Wzorzec Strategia

## Przegląd

Ta implementacja używa wzorca strategia do zarządzania tabelami w bazie danych PostgreSQL. Każda tabela ma swoją własną klasę implementującą abstrakcyjną klasę `AbstractTable`.

## Struktura katalogów

```
telegram.pump.bot/api/db/
├── __init__.py                           # Eksport wszystkich klas
├── abstract_table.py                     # Abstrakcyjna klasa bazowa
├── database_factory.py                   # Fabryka do tworzenia obiektów tabel
├── assets_table.py                       # Tabela Assets
├── users_table.py                        # Tabela Users
├── user_secrets_table.py                 # Tabela UserSecrets
├── transactions_table.py                 # Tabela Transactions
├── fundamental_analysis_table.py         # Tabela FundamentalAnalysis
├── fundamental_analysis_interpretation_table.py  # Tabela FundamentalAnalysisInterpretation
├── technical_analysis_table.py           # Tabela TechnicalAnalysis
├── technical_analysis_interpretation_table.py    # Tabela TechnicalAnalysisInterpretation
├── general_interpretation_table.py       # Tabela GeneralInterpretation
├── telegram_signal_channels_table.py     # Tabela TelegramSignalChannels
├── telegram_signals_table.py             # Tabela TelegramSignals
├── telegram_signal_interpretation_table.py       # Tabela TelegramSignalInterpretation
└── README.md                            # Ta dokumentacja
```

## Klasy główne

### AbstractTable
Abstrakcyjna klasa bazowa definiująca interfejs dla wszystkich tabel:
- `create_table()` - zwraca string SQL do utworzenia tabeli
- `create()` - tworzy nowy rekord
- `get_by_id()` - pobiera rekord po ID
- `update()` - aktualizuje rekord
- `delete()` - usuwa rekord
- `get_all()` - pobiera wszystkie rekordy

### DatabaseFactory
Fabryka do tworzenia i zarządzania obiektami tabel:
- `get_table(table_name)` - zwraca instancję tabeli
- `get_assets_table()` - zwraca tabelę Assets
- `get_users_table()` - zwraca tabelę Users
- itd.

### PostgreSQL
Główna klasa zarządzająca bazą danych:
- `init_db()` - inicjalizuje pulę połączeń i tworzy tabele
- `get_factory()` - zwraca fabrykę tabel
- Metody pomocnicze do szybkiego dostępu do tabel

## Tabele i relacje

### Assets
- **id** (SERIAL PRIMARY KEY)
- **asset** (TEXT NOT NULL)
- **quote** (TEXT NOT NULL)
- **UNIQUE(asset, quote)**

### Users
- **id** (SERIAL PRIMARY KEY)
- **username** (TEXT UNIQUE NOT NULL)
- **password** (TEXT NOT NULL) - bcrypt
- **email** (TEXT UNIQUE NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### UserSecrets
- **id** (SERIAL PRIMARY KEY)
- **user_id** (INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE)
- **key** (TEXT NOT NULL)
- **value** (TEXT NOT NULL) - base64
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)
- **UNIQUE(user_id, key)**

### Transactions
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **user_id** (INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **exchange** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### FundamentalAnalysis
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **content** (TEXT NOT NULL)
- **link** (TEXT)
- **service** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### FundamentalAnalysisInterpretation
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **fundamental_analysis_id** (INTEGER NOT NULL REFERENCES fundamental_analysis(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **content** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### TechnicalAnalysis
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **x_point_timestamp** (TEXT NOT NULL)
- **ta_object_json** (JSONB NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### TechnicalAnalysisInterpretation
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **technical_analysis_id** (INTEGER NOT NULL REFERENCES technical_analysis(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **content** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### GeneralInterpretation
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **technical_analysis_interpretation_id** (INTEGER REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE)
- **fundamental_analysis_interpretation_id** (INTEGER REFERENCES fundamental_analysis_interpretation(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **content** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### TelegramSignalChannels
- **id** (SERIAL PRIMARY KEY)
- **telegram_id** (TEXT UNIQUE NOT NULL)
- **name** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### TelegramSignals
- **id** (SERIAL PRIMARY KEY)
- **telegram_signal_channel_id** (INTEGER NOT NULL REFERENCES telegram_signal_channels(id) ON DELETE CASCADE)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **content** (TEXT NOT NULL)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

### TelegramSignalInterpretation
- **id** (SERIAL PRIMARY KEY)
- **asset_id** (INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE)
- **telegram_signal_id** (INTEGER NOT NULL REFERENCES telegram_signals(id) ON DELETE CASCADE)
- **technical_analysis_interpretation_id** (INTEGER REFERENCES technical_analysis_interpretation(id) ON DELETE CASCADE)
- **timestamp** (TEXT NOT NULL)
- **content** (TEXT NOT NULL)
- **is_scam** (BOOLEAN DEFAULT FALSE)
- **created_at** (TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP)

## Przykład użycia

```python
from telegram.pump.bot.api.postgresql import PostgreSQL

# Inicjalizacja
db = PostgreSQL("postgresql://user:pass@localhost/dbname")
await db.init_db()

# Tworzenie asset
asset_id = await db.create_asset_and_get_id("BTC", "USDT")

# Tworzenie użytkownika
user_id = await db.create_user_and_get_id("john", "hashed_password", "john@example.com")

# Zapisanie secret
await db.save_user_secret(user_id, "api_key", "base64_encoded_value")

# Pobranie secret
secret = await db.get_user_secret(user_id, "api_key")

# Tworzenie transakcji
transaction_id = await db.create_transaction(asset_id, user_id, "2024-01-01T12:00:00Z", "binance")

# Tworzenie analizy fundamentalnej
analysis_id = await db.create_fundamental_analysis(asset_id, "2024-01-01T12:00:00Z", "News content", "https://example.com", "reuters")

# Tworzenie analizy technicznej
ta_data = {"pattern": "harmonic", "points": [...]}
ta_id = await db.create_technical_analysis(asset_id, "2024-01-01T12:00:00Z", ta_data)

# Tworzenie kanału sygnałów Telegram
channel_id = await db.get_telegram_signal_channels_table().create("@signals_channel", "Crypto Signals")

# Tworzenie sygnału Telegram
signal_id = await db.get_telegram_signals_table().create(channel_id, asset_id, "2024-01-01T12:00:00Z", "BTC/USDT BUY signal")

# Tworzenie interpretacji sygnału Telegram
interpretation_id = await db.get_telegram_signal_interpretation_table().create(
    asset_id, signal_id, "2024-01-01T12:00:00Z", "Analysis of the signal", 
    technical_analysis_interpretation_id=None, is_scam=False
)

# Bezpośredni dostęp do tabel
assets_table = db.get_assets_table()
all_assets = await assets_table.get_all()

users_table = db.get_users_table()
user = await users_table.get_by_username("john")
```

## Zalety wzorca strategia

1. **Modularność** - każda tabela ma swoją własną klasę
2. **Rozszerzalność** - łatwo dodać nowe tabele
3. **Izolacja** - zmiany w jednej tabeli nie wpływają na inne
4. **Testowanie** - każdą tabelę można testować niezależnie
5. **Typowanie** - silne typowanie dla każdej tabeli
6. **Reużywalność** - wspólne metody w AbstractTable

## Metody specjalne

Każda klasa tabeli ma dodatkowe metody specyficzne dla swojej domeny:

### AssetsTable
- `get_by_asset_quote(asset, quote)`
- `search_by_asset(asset)`
- `search_by_quote(quote)`

### UsersTable
- `get_by_username(username)`
- `get_by_email(email)`
- `search_by_username(username)`
- `search_by_email(email)`

### UserSecretsTable
- `get_by_user_and_key(user_id, key)`
- `get_value_by_user_and_key(user_id, key)`
- `update_or_create(user_id, key, value)`
- `delete_by_user_and_key(user_id, key)`
- `get_by_user_id(user_id)`
- `get_keys_by_user_id(user_id)`

### TransactionsTable
- `get_by_user_id(user_id)`
- `get_by_asset_id(asset_id)`
- `get_by_exchange(exchange)`
- `get_by_timestamp_range(start, end)`

### FundamentalAnalysisTable
- `get_by_asset_id(asset_id)`
- `get_by_service(service)`
- `get_by_timestamp_range(start, end)`
- `search_by_content(content)`

### TechnicalAnalysisTable
- `get_by_asset_id(asset_id)`
- `get_by_timestamp_range(start, end)`
- `get_latest_by_asset_id(asset_id)`
- `search_by_json_pattern(pattern)`

### GeneralInterpretationTable
- `get_by_asset_id(asset_id)`
- `get_by_technical_analysis_interpretation_id(id)`
- `get_by_fundamental_analysis_interpretation_id(id)`
- `get_by_timestamp_range(start, end)`
- `get_latest_by_asset_id(asset_id)`
- `get_complete_interpretation(asset_id)`

### TelegramSignalChannelsTable
- `get_by_telegram_id(telegram_id)`
- `search_by_name(name)`
- `search_by_telegram_id(telegram_id)`
- `get_channels_with_signal_count(limit, offset)`

### TelegramSignalsTable
- `get_by_channel_id(channel_id)`
- `get_by_asset_id(asset_id)`
- `get_by_timestamp_range(start, end)`
- `search_by_content(content)`
- `get_latest_by_asset_id(asset_id)`
- `get_signals_by_asset_and_channel(asset_id, channel_id)`

### TelegramSignalInterpretationTable
- `get_by_asset_id(asset_id)`
- `get_by_telegram_signal_id(telegram_signal_id)`
- `get_by_technical_analysis_interpretation_id(id)`
- `get_by_timestamp_range(start, end)`
- `search_by_content(content)`
- `get_by_scam_status(is_scam)`
- `get_latest_by_asset_id(asset_id)`
- `get_complete_interpretation(asset_id)` 