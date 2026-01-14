# Trading AI Backend

Backend REST API dla systemu analizy kryptowalut z funkcjami synchronizacji danych z giełd, analizy technicznej (wzorce harmoniczne) i zarządzania użytkownikami.

## Tech Stack

- **Framework**: FastAPI (Python 3.11)
- **Baza danych**: PostgreSQL (asyncpg)
- **Task Queue**: Celery + Redis/RabbitMQ
- **Storage**: MinIO / Local Storage
- **Autentykacja**: Bearer Token (bcrypt)

## Struktura projektu

```
trading.ai.backend/
├── main_controller_rest_api.py    # Główny entry point REST API (port 9090)
├── main_controller_sync.py        # Kontroler synchronizacji (standalone)
├── tox.ini                        # Konfiguracja środowisk i zależności
├── src/
│   ├── config.py                  # Konfiguracja z env vars (singleton: config)
│   ├── auth.py                    # Autentykacja FastAPI (require_auth, require_admin)
│   │
│   ├── controller_rest_domain_*.py  # Kontrolery REST (auto-ładowane)
│   │   ├── controller_rest_domain_user.py         # /user/* - auth, profile, CRUD
│   │   ├── controller_rest_domain_assets.py       # /assets/* - assety crypto
│   │   ├── controller_rest_domain_exchanges.py    # /exchanges/* - giełdy
│   │   ├── controller_rest_domain_sync_system.py  # /sync/* - synchronizacja
│   │   ├── controller_rest_domain_technical_analysis.py  # /analysis/technical/*
│   │   └── controller_rest_domain_cron_jobs.py    # /system/cron/* - zadania cron
│   │
│   ├── celery_tasks/              # Zadania Celery
│   │   ├── sync_tasks.py          # sync_exchanges_task, sync_all_task
│   │   └── analysis_tasks.py      # sync_technical_analysis_task
│   │
│   ├── db/
│   │   ├── database_facade.py     # DatabaseFacade - entry point do DB
│   │   └── postgresql/
│   │       ├── database_postgresql.py         # DatabasePostgreSQL - pool, init
│   │       ├── database_postgresql_factory.py # Factory do tabel
│   │       └── tables/
│   │           ├── abstract_table.py          # Bazowa klasa tabel
│   │           ├── users_table.py             # Użytkownicy (bcrypt)
│   │           ├── user_sessions_table.py     # Sesje/tokeny
│   │           ├── assets_table.py            # Assety (BTC, ETH, etc.)
│   │           ├── exchanges_table.py         # Giełdy (Binance, MEXC)
│   │           ├── asset_exchanges_table.py   # Relacja asset-exchange
│   │           ├── technical_analysis_harmonic_patterns_table.py
│   │           ├── system_sync_job_table.py   # Typy procesów sync
│   │           └── cron_system_sync_job_table.py  # Zadania cron
│   │
│   ├── api/
│   │   ├── api_facade.py          # ApiFacade - entry point
│   │   ├── api_fabric.py          # ApiFabric - factory do API
│   │   ├── exchanges/             # Binance, MEXC, KuCoin API
│   │   ├── llms/                  # OpenAI API
│   │   ├── news_services/         # CryptoPanic, GNews, CoinDesk
│   │   └── storage/               # MinIO, Local storage
│   │
│   ├── technical_analysis/
│   │   ├── technical_analysis_facade.py
│   │   ├── technical_analysis_factory.py
│   │   ├── indicators/            # RSI, MACD, OBV
│   │   └── technical_analysis_objects/
│   │       ├── tao_harmonic_patterns.py       # Wzorce harmoniczne (Gartley, Bat, etc.)
│   │       ├── tao_fibonacci.py               # Poziomy Fibonacci
│   │       └── ...
│   │
│   ├── sync_exchanges.py          # Logika synchronizacji giełd
│   └── sync_technical_analysis.py # Logika synchronizacji analiz
```

## Kluczowe wzorce

### Kontrolery REST

Pliki `controller_rest_domain_*.py` są **automatycznie ładowane** przez `main_controller_rest_api.py`.
Każdy kontroler musi eksportować:
- `router` - instancja `APIRouter`
- `PREFIX` - prefix URL (np. `/assets`)
- `TAGS` - tagi OpenAPI

```python
from fastapi import APIRouter, Depends
from .auth import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])
PREFIX = "/assets"
TAGS = ["Assets"]
```

### Dostęp do bazy danych

```python
from .db.database_facade import DatabaseFacade

db_facade = DatabaseFacade()
db = db_facade.get_database_postgresql()
await db.init_db()

# Dostęp do tabel przez factory
users_table = db.get_factory().get_users_table()
assets_table = db.get_factory().get_assets_table()
```

### Autentykacja

```python
from .auth import require_auth, require_admin, AuthUser

# Wymaga zalogowanego użytkownika
@router.get("/data")
async def get_data(current_user: AuthUser = Depends(require_auth)):
    pass

# Wymaga admina
@router.post("/admin-action")
async def admin_action(current_user: AuthUser = Depends(require_admin)):
    pass
```

### Konfiguracja

Wszystkie zmienne środowiskowe przez `src/config.py`:
```python
from .config import config

# Dostęp do konfiguracji
db_url = config.database_url
session_expiry = config.session_expiry_period
```

## Zmienne środowiskowe

### Wymagane
| Zmienna | Opis |
|---------|------|
| `DATABASE_URL` | PostgreSQL connection string |
| `TELETHON_BOT_TOKEN` | Token bota Telegram |
| `TELETHON_API_ID` | Telegram API ID |
| `TELETHON_API_HASH` | Telegram API Hash |
| `KUCOIN_API_KEY/SECRET/PASSPHRASE` | KuCoin API |
| `MEXC_API_KEY/SECRET` | MEXC API |
| `OPENAI_API_KEY` | OpenAI API |

### Autentykacja
| Zmienna | Opis | Domyślna |
|---------|------|----------|
| `ADMIN_USERNAME` | Nazwa admina systemowego | `admin` |
| `ADMIN_PASSWORD` | Hasło admina (bcrypt) | - |
| `ADMIN_CREATE_FORCE` | Wymuś odtworzenie admina | `false` |
| `SESSION_EXPIRY_PERIOD` | Czas wygaśnięcia sesji | `24h` |

### Celery
| Zmienna | Opis |
|---------|------|
| `CELERY_BROKER_URL` | URL brokera (redis/amqp) |
| `CELERY_RESULT_BACKEND` | URL backendu wyników |

### Storage
| Zmienna | Opis |
|---------|------|
| `MINIO_ENDPOINT` | Endpoint MinIO |
| `MINIO_ACCESS_KEY/SECRET_KEY` | Klucze MinIO |
| `LOCAL_STORAGE_IS_ENABLED` | Użyj local storage |
| `LOCAL_STORAGE_PATH` | Ścieżka local storage |

## Uruchamianie

```bash
# REST API (port 9090)
tox -e rest-api-controller

# Celery Worker
tox -e rest-api-celery-worker

# Sync Controller (standalone)
tox -e sync-controller
```

## Endpointy API

### Publiczne (bez auth)
- `POST /user/auth/login` - logowanie

### Wymagają zalogowania
- `GET /user/auth/verify` - weryfikacja sesji
- `POST /user/auth/logout` - wylogowanie
- `GET /user/me` - profil
- `/assets/*`, `/exchanges/*`, `/analysis/technical/*`, `/system/cron/*`

### Wymagają admina
- `GET /health` - health check główny
- `/sync/*` - synchronizacja (POST, DELETE)
- `/user/list`, `/user/create`, `/user/{id}` - zarządzanie użytkownikami

## Tabele bazy danych

| Tabela | Opis |
|--------|------|
| `users` | Użytkownicy (id=0 to admin systemowy) |
| `user_sessions` | Tokeny sesji |
| `assets` | Pary tradingowe (BTC/USDT) |
| `exchanges` | Giełdy (Binance, MEXC) |
| `asset_exchanges` | Relacja N:M asset-exchange |
| `technical_analysis_harmonic_patterns` | Wzorce harmoniczne |
| `system_sync_job` | Definicje procesów sync |
| `cron_system_sync_job` | Zadania cron |

## Konwencje kodu

- **Język komentarzy/logów**: Polski
- **Nazwy zmiennych/funkcji**: snake_case (Python standard)
- **Klasy**: PascalCase
- **Tabele DB**: Klasy `*Table` dziedziczące z `AbstractTable`
- **Async**: Wszystkie operacje DB są async (asyncpg)

