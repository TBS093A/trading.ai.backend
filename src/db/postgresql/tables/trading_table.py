from typing import Any, Dict, List, Optional, Sequence
import json
import logging

from .abstract_table import AbstractTable

logger = logging.getLogger(__name__)

SIGNAL_OPEN_STATUSES = ("armed", "entered")
JSON_FIELDS = ("risk_json", "filters_json", "data_json")


def _decode(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if row:
        for c in JSON_FIELDS:
            if isinstance(row.get(c), str):
                row[c] = json.loads(row[c])
    return row


class TradingTable(AbstractTable):
    """Trading z sygnałów setupów (src/trading): konta, sygnały, zlecenia, pozycje, kapitał, dziennik.

    Łańcuch: technical_analysis_harmonic_setups -> trading_signals (konto + setup) -> trading_orders
    (wejście / SL / TP / zamknięcie, buy|sell, long|short) -> trading_positions (wynik w walucie i R).
    trading_events zapisuje każdą decyzję (także odrzucenia) z powodem.
    """

    EXTRA_TABLES = ("trading_signals", "trading_orders", "trading_positions", "trading_equity", "trading_events")

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS trading_accounts (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            exchange VARCHAR(40) NOT NULL DEFAULT 'paper',
            base_currency VARCHAR(10) NOT NULL DEFAULT 'USDT',
            starting_equity DOUBLE PRECISION NOT NULL,
            cash DOUBLE PRECISION NOT NULL,
            peak_equity DOUBLE PRECISION NOT NULL,
            entry_mode VARCHAR(20) NOT NULL DEFAULT 'touch',
            risk_json JSONB NOT NULL,
            filters_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            kill_switch BOOLEAN NOT NULL DEFAULT FALSE,
            kill_reason TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS trading_signals (
            id BIGSERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
            setup_id INTEGER REFERENCES technical_analysis_harmonic_setups(id) ON DELETE SET NULL,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            symbol VARCHAR(40) NOT NULL,
            interval VARCHAR(10) NOT NULL,
            pattern_type VARCHAR(40) NOT NULL,
            direction VARCHAR(5) NOT NULL CHECK (direction IN ('long', 'short')),
            entry_price DOUBLE PRECISION NOT NULL,
            sl DOUBLE PRECISION NOT NULL,
            tp DOUBLE PRECISION NOT NULL,
            strength INTEGER,
            p_win DOUBLE PRECISION,
            ev DOUBLE PRECISION,
            status VARCHAR(12) NOT NULL,
            reason TEXT,
            setup_created_time BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (account_id, setup_id)
        );
        CREATE INDEX IF NOT EXISTS idx_trading_signals_open ON trading_signals (account_id, status);
        CREATE TABLE IF NOT EXISTS trading_positions (
            id BIGSERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
            signal_id BIGINT NOT NULL REFERENCES trading_signals(id) ON DELETE CASCADE,
            asset_id INTEGER NOT NULL,
            symbol VARCHAR(40) NOT NULL,
            direction VARCHAR(5) NOT NULL,
            qty DOUBLE PRECISION NOT NULL,
            entry_price DOUBLE PRECISION NOT NULL,
            sl DOUBLE PRECISION NOT NULL,
            tp DOUBLE PRECISION NOT NULL,
            risk_amount DOUBLE PRECISION NOT NULL,
            opened_time BIGINT NOT NULL,
            closed_time BIGINT,
            exit_price DOUBLE PRECISION,
            exit_reason VARCHAR(12),
            mark_price DOUBLE PRECISION,
            mark_time BIGINT,
            fees DOUBLE PRECISION NOT NULL DEFAULT 0,
            pnl DOUBLE PRECISION,
            r_multiple DOUBLE PRECISION,
            status VARCHAR(8) NOT NULL DEFAULT 'open'
        );
        CREATE INDEX IF NOT EXISTS idx_trading_positions_open ON trading_positions (account_id, status);
        CREATE TABLE IF NOT EXISTS trading_orders (
            id BIGSERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
            signal_id BIGINT REFERENCES trading_signals(id) ON DELETE CASCADE,
            position_id BIGINT REFERENCES trading_positions(id) ON DELETE SET NULL,
            client_order_id VARCHAR(64) NOT NULL UNIQUE,
            exchange_order_id VARCHAR(64),
            symbol VARCHAR(40) NOT NULL,
            side VARCHAR(4) NOT NULL CHECK (side IN ('buy', 'sell')),
            position_side VARCHAR(5) NOT NULL CHECK (position_side IN ('long', 'short')),
            order_type VARCHAR(20) NOT NULL,
            purpose VARCHAR(12) NOT NULL,
            price DOUBLE PRECISION,
            qty DOUBLE PRECISION NOT NULL,
            filled_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
            avg_fill_price DOUBLE PRECISION,
            fee DOUBLE PRECISION NOT NULL DEFAULT 0,
            status VARCHAR(10) NOT NULL,
            placed_time BIGINT NOT NULL,
            filled_time BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_trading_orders_signal ON trading_orders (signal_id);
        CREATE TABLE IF NOT EXISTS trading_equity (
            id BIGSERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
            market_time BIGINT NOT NULL,
            equity DOUBLE PRECISION NOT NULL,
            cash DOUBLE PRECISION NOT NULL,
            open_positions INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_trading_equity_account ON trading_equity (account_id, market_time);
        CREATE TABLE IF NOT EXISTS trading_events (
            id BIGSERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
            signal_id BIGINT REFERENCES trading_signals(id) ON DELETE CASCADE,
            order_id BIGINT REFERENCES trading_orders(id) ON DELETE SET NULL,
            position_id BIGINT REFERENCES trading_positions(id) ON DELETE SET NULL,
            kind VARCHAR(30) NOT NULL,
            message TEXT NOT NULL,
            data_json JSONB,
            market_time BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_trading_events_account ON trading_events (account_id, id DESC);
        """

    # ─────────── konta ───────────

    async def create_account(self, name: str, exchange: str, starting_equity: float, entry_mode: str,
                             risk: Dict[str, Any], filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return _decode(await self.fetch_one(
            """INSERT INTO trading_accounts (name, exchange, starting_equity, cash, peak_equity, entry_mode,
                risk_json, filters_json) VALUES ($1, $2, $3, $3, $3, $4, $5, $6) RETURNING *""",
            name, exchange, starting_equity, entry_mode, json.dumps(risk), json.dumps(filters),
        ))

    async def update_account(self, account_id: int, **fields) -> Optional[Dict[str, Any]]:
        allowed = {"name", "entry_mode", "risk_json", "filters_json", "enabled", "kill_switch", "kill_reason",
                   "cash", "peak_equity"}
        sets, args = [], [account_id]
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(f"pole konta nieobsługiwane: {k}")
            args.append(json.dumps(v) if k in JSON_FIELDS else v)
            sets.append(f"{k} = ${len(args)}")
        if not sets:
            return await self.get_account(account_id)
        return _decode(await self.fetch_one(
            f"UPDATE trading_accounts SET {', '.join(sets)}, updated_at = NOW() WHERE id = $1 RETURNING *",  # nosemgrep: kolumny z allowlisty
            *args,
        ))

    async def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        return _decode(await self.fetch_one("SELECT * FROM trading_accounts WHERE id = $1", account_id))

    async def list_accounts(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            "SELECT * FROM trading_accounts WHERE ($1::boolean IS FALSE OR enabled) ORDER BY id", enabled_only
        )
        return [_decode(r) for r in rows]

    # ─────────── sygnały ───────────

    async def create_signal(self, **s) -> Optional[Dict[str, Any]]:
        cols = ("account_id", "setup_id", "asset_id", "symbol", "interval", "pattern_type", "direction",
                "entry_price", "sl", "tp", "strength", "p_win", "ev", "status", "reason", "setup_created_time")
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        return await self.fetch_one(
            f"""INSERT INTO trading_signals ({', '.join(cols)}) VALUES ({placeholders})
            ON CONFLICT (account_id, setup_id) DO NOTHING RETURNING *""",  # nosemgrep: kolumny stałe
            *[s.get(c) for c in cols],
        )

    async def set_signal_status(self, signal_id: int, status: str, reason: Optional[str] = None) -> None:
        await self.execute_query(
            "UPDATE trading_signals SET status = $2, reason = COALESCE($3, reason), updated_at = NOW() WHERE id = $1",
            signal_id, status, reason,
        )

    async def signaled_setup_ids(self, account_id: int, setup_ids: Sequence[int]) -> set:
        if not setup_ids:
            return set()
        rows = await self.fetch_all(
            "SELECT setup_id FROM trading_signals WHERE account_id = $1 AND setup_id = ANY($2::int[])",
            account_id, list(setup_ids),
        )
        return {r["setup_id"] for r in rows}

    async def open_signals(self, account_id: int, asset_id: Optional[int] = None,
                           interval: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT s.*, st.status AS setup_status FROM trading_signals s
            LEFT JOIN technical_analysis_harmonic_setups st ON st.id = s.setup_id
            WHERE s.account_id = $1 AND s.status = ANY($2::text[])
              AND ($3::int IS NULL OR s.asset_id = $3) AND ($4::text IS NULL OR s.interval = $4)
            ORDER BY s.id""",
            account_id, list(SIGNAL_OPEN_STATUSES), asset_id, interval,
        )

    async def list_signals(self, account_id: int, status: Optional[str] = None, limit: int = 100,
                           offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT * FROM trading_signals WHERE account_id = $1 AND ($2::text IS NULL OR status = $2)
            ORDER BY id DESC LIMIT $3 OFFSET $4""",
            account_id, status, limit, offset,
        )

    async def get_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT * FROM trading_signals WHERE id = $1", signal_id)

    # ─────────── zlecenia ───────────

    async def create_order(self, **o) -> Optional[Dict[str, Any]]:
        cols = ("account_id", "signal_id", "position_id", "client_order_id", "exchange_order_id", "symbol", "side",
                "position_side", "order_type", "purpose", "price", "qty", "status", "placed_time")
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        return await self.fetch_one(
            f"""INSERT INTO trading_orders ({', '.join(cols)}) VALUES ({placeholders})
            ON CONFLICT (client_order_id) DO NOTHING RETURNING *""",  # nosemgrep: kolumny stałe
            *[o.get(c) for c in cols],
        )

    async def fill_order(self, order_id: int, price: float, qty: float, fee: float, filled_time: int,
                         position_id: Optional[int] = None) -> None:
        await self.execute_query(
            """UPDATE trading_orders SET status = 'filled', filled_qty = $3, avg_fill_price = $2, fee = $4,
                filled_time = $5, position_id = COALESCE($6, position_id), updated_at = NOW() WHERE id = $1""",
            order_id, price, qty, fee, filled_time, position_id,
        )

    async def set_order_status(self, order_id: int, status: str) -> None:
        await self.execute_query(
            "UPDATE trading_orders SET status = $2, updated_at = NOW() WHERE id = $1", order_id, status
        )

    async def update_order(self, order_id: int, **fields) -> None:
        """Stan z giełdy (src/trading/live.py): id zlecenia na giełdzie, status, wypełnienie."""
        allowed = {"exchange_order_id", "status", "filled_qty", "avg_fill_price", "fee", "filled_time", "qty", "price"}
        sets, args = [], [order_id]
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(f"pole zlecenia nieobsługiwane: {k}")
            args.append(v)
            sets.append(f"{k} = ${len(args)}")
        if sets:
            await self.execute_query(
                f"UPDATE trading_orders SET {', '.join(sets)}, updated_at = NOW() WHERE id = $1",  # nosemgrep: kolumny z allowlisty
                *args,
            )

    async def orders_for_signal(self, signal_id: int) -> List[Dict[str, Any]]:
        return await self.fetch_all("SELECT * FROM trading_orders WHERE signal_id = $1 ORDER BY id", signal_id)

    async def list_orders(self, account_id: int, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT * FROM trading_orders WHERE account_id = $1 ORDER BY id DESC LIMIT $2 OFFSET $3",
            account_id, limit, offset,
        )

    # ─────────── pozycje ───────────

    async def open_position(self, **p) -> Optional[Dict[str, Any]]:
        cols = ("account_id", "signal_id", "asset_id", "symbol", "direction", "qty", "entry_price", "sl", "tp",
                "risk_amount", "opened_time", "fees")
        placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
        return await self.fetch_one(
            f"INSERT INTO trading_positions ({', '.join(cols)}) VALUES ({placeholders}) RETURNING *",  # nosemgrep: stałe
            *[p.get(c) for c in cols],
        )

    async def close_position(self, position_id: int, exit_price: float, exit_reason: str, closed_time: int,
                             fees: float, pnl: float, r_multiple: float) -> None:
        await self.execute_query(
            """UPDATE trading_positions SET status = 'closed', exit_price = $2, exit_reason = $3, closed_time = $4,
                fees = $5, pnl = $6, r_multiple = $7 WHERE id = $1""",
            position_id, exit_price, exit_reason, closed_time, fees, pnl, r_multiple,
        )

    async def update_position(self, position_id: int, **fields) -> None:
        """Korekta z rekoncyliacji z giełdą (ilość / cena wejścia - giełda wygrywa)."""
        allowed = {"qty", "entry_price", "risk_amount"}
        sets, args = [], [position_id]
        for k, v in fields.items():
            if k not in allowed:
                raise ValueError(f"pole pozycji nieobsługiwane: {k}")
            args.append(v)
            sets.append(f"{k} = ${len(args)}")
        if sets:
            await self.execute_query(
                f"UPDATE trading_positions SET {', '.join(sets)} WHERE id = $1",  # nosemgrep: kolumny z allowlisty
                *args,
            )

    async def mark_position(self, position_id: int, price: float, market_time: int) -> None:
        await self.execute_query(
            "UPDATE trading_positions SET mark_price = $2, mark_time = $3 WHERE id = $1", position_id, price, market_time
        )

    async def positions(self, account_id: int, status: Optional[str] = None, limit: int = 200,
                        offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT * FROM trading_positions WHERE account_id = $1 AND ($2::text IS NULL OR status = $2)
            ORDER BY id DESC LIMIT $3 OFFSET $4""",
            account_id, status, limit, offset,
        )

    async def position_for_signal(self, signal_id: int) -> Optional[Dict[str, Any]]:
        return await self.fetch_one("SELECT * FROM trading_positions WHERE signal_id = $1", signal_id)

    async def realized_pnl_since(self, account_id: int, since_ms: int) -> float:
        value = await self.fetch_val(
            "SELECT COALESCE(SUM(pnl), 0) FROM trading_positions WHERE account_id = $1 AND status = 'closed' "
            "AND closed_time >= $2", account_id, since_ms,
        )
        return float(value or 0.0)

    async def stats(self, account_id: int) -> Dict[str, Any]:
        row = await self.fetch_one(
            """SELECT COUNT(*) FILTER (WHERE status = 'closed') AS closed,
                      COUNT(*) FILTER (WHERE status = 'open') AS open,
                      COUNT(*) FILTER (WHERE status = 'closed' AND pnl > 0) AS wins,
                      COALESCE(SUM(pnl) FILTER (WHERE status = 'closed'), 0) AS realized_pnl,
                      COALESCE(SUM(fees), 0) AS fees,
                      AVG(r_multiple) FILTER (WHERE status = 'closed') AS avg_r
            FROM trading_positions WHERE account_id = $1""",
            account_id,
        ) or {}
        return {"closed": int(row.get("closed") or 0), "open": int(row.get("open") or 0),
                "wins": int(row.get("wins") or 0), "realized_pnl": float(row.get("realized_pnl") or 0.0),
                "fees": float(row.get("fees") or 0.0),
                "avg_r": float(row["avg_r"]) if row.get("avg_r") is not None else None}

    async def closed_vs_backtest(self, account_id: int) -> List[Dict[str, Any]]:
        """Zamknięte pozycje z wynikiem tego samego setupu w symulacji (seria produkcyjna)."""
        return await self.fetch_all(
            """SELECT p.r_multiple AS account_r, st.r_multiple AS backtest_r, st.status AS backtest_status
            FROM trading_positions p JOIN trading_signals s ON s.id = p.signal_id
            LEFT JOIN technical_analysis_harmonic_setups st ON st.id = s.setup_id
            WHERE p.account_id = $1 AND p.status = 'closed'""",
            account_id,
        )

    # ─────────── kapitał i dziennik ───────────

    async def snapshot_equity(self, account_id: int, market_time: int, equity: float, cash: float,
                              open_positions: int) -> None:
        await self.execute_query(
            "INSERT INTO trading_equity (account_id, market_time, equity, cash, open_positions) VALUES ($1, $2, $3, $4, $5)",
            account_id, market_time, equity, cash, open_positions,
        )

    async def equity_series(self, account_id: int, limit: int = 2000) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT market_time, equity, cash, open_positions FROM (
                 SELECT * FROM trading_equity WHERE account_id = $1 ORDER BY market_time DESC LIMIT $2) recent
            ORDER BY market_time""",
            account_id, limit,
        )

    async def log_event(self, account_id: int, kind: str, message: str, signal_id: Optional[int] = None,
                        order_id: Optional[int] = None, position_id: Optional[int] = None,
                        data: Optional[Dict[str, Any]] = None, market_time: Optional[int] = None) -> None:
        await self.execute_query(
            """INSERT INTO trading_events (account_id, signal_id, order_id, position_id, kind, message, data_json,
                market_time) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            account_id, signal_id, order_id, position_id, kind, message, json.dumps(data) if data else None,
            market_time,
        )

    async def events(self, account_id: int, signal_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            """SELECT * FROM trading_events WHERE account_id = $1 AND ($2::bigint IS NULL OR signal_id = $2)
            ORDER BY id DESC LIMIT $3""",
            account_id, signal_id, limit,
        )
        return [_decode(r) for r in rows]

    # ─────────── AbstractTable ───────────

    async def create(self, **kwargs) -> Optional[int]:
        row = await self.create_account(**kwargs)
        return row["id"] if row else None

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_account(record_id)

    async def update(self, record_id: int, **kwargs) -> bool:
        return await self.update_account(record_id, **kwargs) is not None

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM trading_accounts WHERE id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return (await self.list_accounts())[offset:offset + limit]
