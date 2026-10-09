# trading.ai backend

Backend of trading.ai: harmonic pattern (XABCD) detection with confluences, causal tracking of
setup outcomes, a learned pattern strength model, variant benchmarks, e-mail alerts and a trading
engine (paper + Binance USDT-M Futures) driven by setup signals.

One Docker image, three processes selected by `SERVICE_MODE` (`docker-entrypoint.sh`):

| `SERVICE_MODE`           | Entry point                          | Role                                                              |
|--------------------------|--------------------------------------|-------------------------------------------------------------------|
| `rest-api-controller`    | `main_controller_rest_api.py`        | FastAPI REST API used by the frontend (`trading.ai.frontend`)     |
| `sync-controller`        | `main_controller_sync.py`            | APScheduler; cron jobs stored in the DB enqueue Celery tasks      |
| `rest-api-celery-worker` | `src.controller_rest_celery_worker`  | Celery worker (queues `celery`, `sync_queue`, `analysis_queue`)   |

Infrastructure: PostgreSQL, RabbitMQ (Celery broker), Redis (Celery result backend), optional MinIO
(chart images). Production runs on Kubernetes (ArgoCD), see [CI/CD](#cicd-and-supply-chain).

---

## Contents

- [Architecture](#architecture)
- [Domain: from candles to trades](#domain-from-candles-to-trades)
  - [Harmonic patterns and confluences](#harmonic-patterns-and-confluences)
  - [Setups and outcome tracking](#setups-and-outcome-tracking)
  - [Pattern strength model](#pattern-strength-model)
  - [Variant reports (benchmarks)](#variant-reports-benchmarks)
  - [E-mail alerts](#e-mail-alerts)
  - [Trading engine](#trading-engine)
- [Scheduler](#scheduler)
- [REST API](#rest-api)
- [Database](#database)
- [Configuration](#configuration)
- [Running locally](#running-locally)
- [Tests](#tests)
- [Operations](#operations)
- [CI/CD and supply chain](#cicd-and-supply-chain)

---

## Architecture

```
                    ┌───────────────────────────┐
  frontend ───────▶ │ rest-api-controller       │ FastAPI, auth (sessions + CSRF), klines cache
                    └──────────┬────────────────┘
                               │ enqueue (RabbitMQ)
  ┌──────────────────┐         ▼
  │ sync-controller  │ ──▶ Celery workers ──▶ exchanges (Binance, KuCoin, MEXC, yfinance)
  │ APScheduler +    │         │
  │ cron jobs in DB  │         ▼
  └──────────────────┘    PostgreSQL  (patterns, setups, models, reports, alerts, trading)
```

Source layout:

| Path | What |
|------|------|
| `main_controller_rest_api.py`, `src/controller_rest_domain_*.py` | REST API, one router per domain |
| `main_controller_sync.py` | scheduler, `_run_*` processes, cron sync with the DB |
| `src/celery_tasks/` | Celery tasks (`sync_tasks`, `analysis_tasks`, `maintenance_tasks`) |
| `src/sync_technical_analysis.py` | `TechnicalAnalysis` - orchestrator of the nightly sync, facade for tasks |
| `src/analysis_services/` | `KlinesSource`, `PatternStore`, `ConfluencePostProcessor`, `HarmonicScanService`, `SetupTrackingService`, `StrengthService`, `VariantReportService` |
| `src/utils/harmonic_patterns/` | confluence detectors (candles, indicators, Fibonacci, structure, volume, HTF trend) |
| `src/harmonic_scan.py` | on-demand range scans with persistent coverage windows |
| `src/harmonic_validation.py` | ratios, matching patterns, PRZ and targets for X..D points |
| `src/harmonic_setups.py` | causal setup generator + outcome simulation, win-rate stats |
| `src/pattern_strength.py` | features + L2 logistic regression strength model |
| `src/setup_variants.py` | entry / management variants simulator |
| `src/harmonic_alerts.py`, `src/templates/email/` | e-mail alerts (HTML + text) |
| `src/trading/` | risk settings, paper exchange, engine, Binance futures adapter, live flow |
| `src/db/` | PostgreSQL access (table classes, factory), migrations, janitor |
| `src/api/` | exchange clients, LLM, news, storage, Telegram |
| `src/klines_cache.py` | single-flight LRU cache for chart klines pages |

---

## Domain: from candles to trades

### Harmonic patterns and confluences

- Patterns are found with `pyharmonics` (XABCD: gartley, bat, alt bat, butterfly, deep butterfly, crab,
  deep crab, bartley, cypher, shark, deep shark; plus ABCD) on closed candles.
- **Nightly sync** scans assets and stores patterns in `technical_analysis_harmonic_patterns` (upsert on
  the point key, `engine_version` per row).
- **On demand** (`GET /harmonics/{asset_id}/{interval}`): missing parts of the requested range are scanned by
  a worker and remembered as coverage windows (`technical_analysis_harmonic_scan_windows`); the API replies
  `202 computing` with `retry_after_ms` until the range is complete.
- **Confluences** (`src/utils/harmonic_patterns/`, catalog in `pattern_strength.CONFLUENCE_CATALOG`), each
  with a direction (bullish / bearish / both) and a category - the same as the frontend sidebar:

  | Category | Types |
  |----------|-------|
  | momentum | RSI oversold/overbought/divergences, stochastic |
  | candles | engulfing, pin bar, hammer, shooting star, morning/evening star, doji |
  | fibonacci | `fib_cluster`, `higher_tf_fib` |
  | structure | support/resistance zones and trendlines (same and higher TF), pivot points, round levels |
  | volume | volume spike/dry-up/profile, MACD crossovers/divergences, OBV divergences |
  | trend | `higher_tf_uptrend` / `higher_tf_downtrend` |

- **Higher-TF trend** (`trend_confluences.py`): EMA200 on the next higher interval (1h→4h, 4h→1d, …),
  using only candles closed before D. Uptrend = close above EMA and EMA rising over 10 bars (downtrend mirrored);
  otherwise no confluence.
- Fib cluster, higher-TF S/R and trend are computed after the pattern is stored (`ConfluencePostProcessor`).

### Setups and outcome tracking

Stored patterns are not used to measure win rate: the engine only confirms D after the reversal happened,
so patterns that broke through the PRZ never exist there. Instead (`src/harmonic_setups.py`):

- a **setup** = X, A, B, C known at time *t* (C confirmed as a pivot `spacing` candles later, incremental
  zigzag, no repainting) + the D zone (PRZ) from the same definitions as manual validation;
- only candles after *t* decide the outcome:

```
waiting --(price touches PRZ)--> open --(TP1 or SL first)--> win / loss
   |                               '--(no outcome in 2*L candles)--> expired
   |--(price breaks C)--> invalidated
   '--(no entry in L candles)--> no_entry              L = candles from X to C
```

- entry at the near PRZ edge (or the open on a gap), SL/TP from the chart rules (`FibonacciTargets`, D = entry),
  whole position closed at TP1 (`r_multiple`), TP2 reached-before-SL recorded; TP and SL in one candle = SL.
- Confluences are causal: `pre_confluences_json` (level confluences known before the touch) and
  `confluences_json` at the entry candle.
- Rows live in `technical_analysis_harmonic_setups`, keyed by a **params version** (hash of `SETUP_PARAMS`).
  Changing simulation rules bumps the version and starts a new series; old series are cleaned by the janitor.
- **Replay** (backfill) runs over up to 10 000 candles per asset/interval; **live** tracking runs hourly for
  tracked assets and writes status changes to `harmonic_setup_events` (alerts, trading).
- `GET /harmonics/stats` - win rate with a 95% Wilson interval, mean R, MFE/MAE, entry and TP2 rates.

### Pattern strength model

`src/pattern_strength.py`, served by `StrengthService`:

- **Features**: each confluence type as aligned / against the pattern direction, category coverage, counts of
  aligned/opposite confluences, pattern type, interval, structure size, ratio deviation from the definition.
- **Model**: L2-regularised logistic regression (numpy IRLS) predicting TP1 before SL.
- **Two kinds**:
  - `entry` - full confluences at entry / confirmation candle;
  - `pre` - level confluences only (Fibonacci, structure, trend, volume profile), usable while a setup is waiting.
- **Validation**: out-of-time split (oldest 70% train, newest 30% test) - AUC, win rate and mean R per quintile;
  the production model is then refit on all data. `score` = percentile of the prediction (0-100), `p_win` =
  probability, `factors` = per-feature contributions with labels.
- Refit weekly (Sunday 04:00 UTC) or via `POST /harmonics/strength/fit`; history in `harmonic_strength_models`.

### Variant reports (benchmarks)

`src/setup_variants.py` + `VariantReportService`: every variant replays the same setups and differs only in
entry and management.

- **entry** `touch` (near PRZ edge, like the production series) or `confirm` (reversal candle within 3 candles
  after the touch; market entry at the next open; SL beyond the extreme since the touch, `SL_BUFFER` 0.1%);
- **management**: `breakeven_at`, `rr_cap`;
- **filters**: `min_strength`, `min_ev` (`p_win*RR - (1-p_win)`), `trend` (`with` / `not_against`).
- Honest scoring: touch variants use the `pre` model on candles before the touch, confirm variants the `entry`
  model on the closed confirmation candle. Both models are fit only on data before the report cutoff, so the
  **out** (after cutoff) numbers are the ones to trust.
- Variants: `baseline`, `be_1r`, `rr_cap_2`, `rr_cap_1_5`, `confirm`, `confirm_be`, `confirm_cap_2`,
  `pre_strength_60/70/80`, `pre_ev_positive`, `confirm_strength_60/70/80`, `confirm_ev_be`, `baseline_trend`,
  `baseline_not_against`, `pre_strength_70_trend`, `confirm_trend`, `confirm_strength_80_trend`,
  `confirm_strength_70_not_against`.
- `POST /harmonics/variants/run` fans out one Celery task per tracked asset/interval
  (`run_variant_pair`); results in `harmonic_variant_reports`.

### E-mail alerts

`src/harmonic_alerts.py`: after each hourly tracking run (+10 min) every user gets at most one e-mail with the
setup events matching their settings (statuses, assets, intervals - `PUT /harmonics/alerts/settings`).
HTML in the frontend style (`src/templates/email/setup_alerts.html`, Jinja2 with autoescape) + plain text.
SMTP from `SMTP_*` (Gmail in production); without `SMTP_HOST` events wait in the DB, nothing is marked sent.

### Trading engine

`src/trading/` - trades from setup signals, fully tracked in the DB
(`trading_accounts`, `trading_signals`, `trading_orders`, `trading_positions`, `trading_events`,
equity snapshots). Runs after each hourly tracking run per (asset, interval), on closed candles.

- **Exchanges**: `paper` (fills on real candles with the same rules as the simulator - limit touch, gap at open,
  SL before TP in one candle, maker/taker fees and slippage) and `binance_futures_testnet`
  (USDT-M Futures: signed REST, symbol filters, isolated margin, one-way mode, idempotent client order ids,
  SL as STOP_MARKET reduceOnly, reconciliation every run - the exchange wins, every mismatch is a `reconcile` event).
- **Entry modes** (per account):
  - `touch` - limit order at the near PRZ edge for fresh `waiting` setups, `pre` strength;
  - `confirm` - after the touch, wait for a reversal candle (window 3), market entry at the next open,
    `entry` strength; SL = farther of the chart rule and the touch extreme.
- **Account filters** (editable after creation): assets, intervals, patterns, direction
  (`GET /trading/filter-options` lists the allowed values).
- **Risk settings** (`RISK_FIELDS`, each with description, range and default): `risk_per_trade_pct`,
  `max_open_positions`, `max_positions_per_asset`, `daily_loss_limit_pct`, `max_drawdown_stop_pct`,
  `max_position_notional_pct`, `min_strength`, `min_ev`, `fee_pct`, `slippage_pct`, `leverage`,
  `trend_filter` (`off` / `with` / `not_against`).
- **Presets**: `conservative`, `balanced`, `confirm_strong` (confirm + strength ≥ 80), `aggressive`.
  `POST /trading/risk/preview` replays settings on variant report trades (equity, drawdown, losing streaks,
  bootstrap risk of ruin).
- Every decision is logged in `trading_events`, rejected signals keep the reason; `GET /trading/signals/{id}/trace`
  shows setup → signal → orders → position → events; `GET /trading/accounts/{id}/compare` compares the account
  with the backtest of the same setups. Kill switch per account.

---

## Scheduler

`sync-controller` keeps APScheduler in sync with the `cron_system_sync_job` table (processes in
`system_sync_job`); jobs can be enabled/disabled/moved from the cron jobs panel (`/cron-jobs` API).

| Process | Default schedule (UTC) | What |
|---------|------------------------|------|
| `run_full_sync_workflow` | daily 06:00 | exchanges/assets sync, then the harmonic pattern sync with post-processed confluences |
| `_run_harmonic_setups_tracking` | hourly at :03 | live setup tracking for pairs with a new closed candle; +10 min: alerts and trading equity snapshot |
| `_run_strength_model_fit` | Sunday 04:00 | refit `entry` and `pre` strength models |
| `_run_db_janitor` | daily 03:30 | DB cleanup (see [Operations](#operations)) |

Tracked assets (`tracked_assets`): which assets get the nightly pattern sync and which intervals get setup
tracking (`PUT /harmonics/tracked-assets/{asset_id}`; new intervals trigger a backfill).

---

## REST API

Interactive docs: `/docs` (Swagger) on the running API (port 9090). Authentication: session cookie from
`POST /auth/login` + CSRF header for state-changing requests; admin-only endpoints are marked below.

| Domain | Main endpoints |
|--------|----------------|
| Auth / users | `POST /auth/login`, `/auth/logout`, `GET /auth/verify`, user CRUD (admin) |
| Assets / exchanges | asset CRUD and search, asset-exchange relations, `GET /exchanges/klines/{asset_id}/{interval}` (cached pages) |
| Technical analysis | stored harmonic patterns (filters by asset, interval, points), chart images |
| Harmonics | `GET /harmonics/{asset_id}/{interval}` (range scan), `POST /harmonics/validate`, `GET /harmonics/stats`, `GET /harmonics/setups` (`section=active|won|lost|junk`), `POST /harmonics/setups/backfill` (admin) |
| Tracked assets | `GET/PUT/DELETE /harmonics/tracked-assets[/{asset_id}]` |
| Strength | `GET /harmonics/strength/model`, `POST /harmonics/strength/fit` (admin), `GET /harmonics/strength/history`, `GET /harmonics/strength/data` |
| Variants | `GET /harmonics/variants/reports`, `POST /harmonics/variants/run` (admin), `GET /harmonics/variants/report` |
| Alerts | `GET/PUT /harmonics/alerts/settings`, `GET /harmonics/alerts/events`, `POST /harmonics/alerts/test` |
| Trading | `GET/POST /trading/accounts`, `PATCH /trading/accounts/{id}` (risk, filters, entry mode, enabled), `POST .../kill-switch`, `GET .../equity|signals|positions|orders|events|compare`, `GET /trading/signals/{id}/trace`, `GET /trading/risk/fields`, `GET /trading/filter-options`, `POST /trading/risk/preview` |
| Cron jobs / sync | cron job CRUD and enable/disable, manual sync triggers, component health |
| Maintenance (admin) | `GET/POST /maintenance/db/janitor`, `GET /maintenance/db/migrations` |

Each `src/controller_rest_domain_*.py` starts with a docstring listing its endpoints and semantics.

---

## Database

- Table classes in `src/db/postgresql/tables/` (one class per table, created by `init_db()`), accessed through
  the factory: `db.get_factory().get_<table>_table()`.
- **Migrations**: `src/db/postgresql/migrations.py` - numbered, applied once at startup, recorded in
  `schema_migrations` (`GET /maintenance/db/migrations`). Add a new `Migration(n, name, sql)` with the next
  number; never edit an applied one.
- **Janitor** (`src/db/janitor.py`): tables declare `CleanupRule`s (expired sessions, outdated setup series and
  engine versions, …); the janitor counts and deletes in batches, compacts scan windows and reports tables
  unknown to the registry (never dropped automatically). Dry-run unless `DB_JANITOR_ENABLED=true`.

---

## Configuration

Environment variables (`src/config.py`; a `.env` file in the repo root is read when present):

| Group | Variables |
|-------|-----------|
| Database / broker | `DATABASE_URL` (or `DATABASE_USERNAME`, `DATABASE_PASSWORD`, `DATABASE_HOST`, `DATABASE_PORT`, `DATABASE_SCHEMA` - composed by the entrypoint), `CELERY_BROKER_URL` / `RABBITMQ_*`, `CELERY_RESULT_BACKEND` / `REDIS_*`, `TEST_DATABASE_URL` |
| Exchanges | `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `BINANCE_FUTURES_TESTNET_API_KEY`, `BINANCE_FUTURES_TESTNET_API_SECRET`, `BINANCE_FUTURES_API_KEY`, `BINANCE_FUTURES_API_SECRET`, `KUCOIN_API_KEY`, `KUCOIN_API_SECRET`, `KUCOIN_API_KEY_PASSPHRASE`, `MEXC_API_KEY`, `MEXC_API_SECRET` |
| API / security | `CORS_ALLOWED_ORIGINS`, `FRONTEND_URL`, `CSRF_SECRET_KEY`, `SESSION_EXPIRY_PERIOD`, `RATE_LIMIT_REQUESTS_PER_MINUTE`, `RATE_LIMIT_BURST_SIZE`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `ADMIN_CREATE_FORCE`, `ENVIRONMENT`, `ENABLE_ERROR_RESPONSES`, `ENABLE_HANDLER_LOGGING` |
| E-mail | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SSL`, `SMTP_STARTTLS` |
| Storage | `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET_NAME`, `MINIO_SECURE`, `LOCAL_STORAGE_IS_ENABLED`, `LOCAL_STORAGE_PATH` |
| News / LLM / Telegram | `CRYPTO_PANIC_API_KEY`, `GNEWS_API_KEY`, `COINDESK_API_KEY`, `OPENAI_API_KEY`, `TELETHON_*`, `TELEGRAM_SESSION_NAME` |
| Maintenance | `DB_JANITOR_ENABLED` |

`src/config.py` validates required variables at import time (`DATABASE_URL`, Telegram and exchange keys);
unit tests set dummies in `tox.ini`. In production secrets come from sealed secrets in `cloud.config` - never
commit real values.

Trading accounts on `binance_futures_testnet` use `BINANCE_FUTURES_TESTNET_API_*` (process-wide, not per user) and
take their starting balance from the exchange; both variables are required. Live
`binance_futures` is prepared in the adapter but not yet enabled in the API.

---

## Running locally

Requirements: Python 3.13, `tox`, PostgreSQL, RabbitMQ, Redis.

```bash
tox -e rest-api-controller        # REST API (uvicorn)
tox -e sync-controller            # scheduler
tox -e rest-api-celery-worker     # Celery worker
```

Or with the image:

```bash
docker build -t trading-ai-backend .
docker run --env-file .env -e SERVICE_MODE=rest-api-controller -p 9090:9090 trading-ai-backend
```

Typical first steps after start: log in as the admin from `ADMIN_*`, add tracked assets
(`PUT /harmonics/tracked-assets/{asset_id}`) - this enqueues the setup backfill - then fit the strength models
(`POST /harmonics/strength/fit`) once there are resolved setups.

---

## Tests

```bash
tox -e unit-tests                 # no DB, network or credentials; coverage XML for the CI gate
tox -e technical-analysis-tests   # integration tests needing DB / exchanges
```

`tests/unit/` covers harmonic setups and validation, confluence detectors (incl. HTF trend), strength model,
variants, alerts, scan cache, janitor, dashboards, trading engine (paper, confirm mode, filters, risk) and the
Binance futures adapter (against a fake exchange). The PRE-MERGE gate fails below `MIN_COVERAGE`.

---

## Operations

- **Backfill a new setup series** (after changing `SETUP_PARAMS`):
  `POST /harmonics/setups/backfill` `{"asset_ids": [...], "intervals": ["1h","4h","1d"], "candles": 10000}`
  (admin), then `POST /harmonics/strength/fit`, then `POST /harmonics/variants/run`.
- **Janitor**: `GET /maintenance/db/janitor` shows what would be deleted; `POST` runs it (deletes only when
  `DB_JANITOR_ENABLED=true`).
- **Alerts check**: `POST /harmonics/alerts/test` sends a test e-mail to the logged-in user.
- **Trading**: kill switch per account (`POST /trading/accounts/{id}/kill-switch`); live accounts reconcile with
  the exchange every hourly run.
- Deployed version = the image tag in `cloud.config` = the `master` merge commit.

---

## CI/CD and supply chain

Every change goes through `Jenkinsfile.build` (Jenkins, same model as the terraform pipelines in `cloud.config`):

```
PR -> PRE-MERGE gate -> merge -> POST-MERGE -> RELEASE -> production
```

- **PRE-MERGE** (every PR, required status `jenkins/pre-merge` on `master`): gitleaks, lint, unit tests, coverage threshold,
  Semgrep, Trivy (dependencies, then the built image - scanned before it is ever pushed). The gate scripts come
  from `master`, not from the PR under test. Results land in a `jenkins-bot` comment on the PR.
- **POST-MERGE** (only for a `master` commit that is the merge of a PR with a passing gate): push by digest,
  CycloneDX SBOM, cosign signature verified against [`cosign.pub`](cosign.pub).
- **RELEASE**: image tag bumped in `cloud.config` (ArgoCD), rollout + smoke test, automatic rollback by reverting
  the bump, OWASP ZAP baseline. Progress goes to a comment on the merged PR.

Verify a deployed image yourself:

```bash
cosign verify --key cosign.pub --insecure-ignore-tlog=true registry.00x097.com/trading-ai-backend@sha256:<digest>
```

(`--insecure-ignore-tlog`: signatures are not uploaded to the public Rekor log - private registry.)
