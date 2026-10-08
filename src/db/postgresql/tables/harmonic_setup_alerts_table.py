from typing import Any, Dict, List, Optional, Sequence
import json
import logging

from .abstract_table import AbstractTable, CleanupRule

logger = logging.getLogger(__name__)

ALERT_STATUSES = ("waiting", "open", "win", "loss", "expired", "no_entry", "invalidated")
DEFAULT_ALERT_STATUSES = ("waiting", "open", "win", "loss", "expired")


class HarmonicSetupAlertSettingsTable(AbstractTable):
    """Ustawienia alertów mailowych użytkownika o zmianach setupów XABCD.

    asset_ids / intervals = NULL oznacza "wszystkie śledzone" (tracked_assets).
    Adres e-mail jest w users.email (migracja 3).
    """

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS harmonic_setup_alert_settings (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            email_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            statuses TEXT[] NOT NULL DEFAULT ARRAY['waiting', 'open', 'win', 'loss', 'expired'],
            asset_ids INTEGER[],
            intervals TEXT[],
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """

    async def get_for_user(self, user_id: int) -> Dict[str, Any]:
        row = await self.fetch_one(
            """SELECT s.user_id, s.email_enabled, s.statuses, s.asset_ids, s.intervals, s.updated_at, u.email
            FROM users u LEFT JOIN harmonic_setup_alert_settings s ON s.user_id = u.id
            WHERE u.id = $1""",
            user_id,
        )
        if row is None:
            return {}
        if row.get("user_id") is None:  # jeszcze nic nie zapisał - wartości domyślne
            row.update(user_id=user_id, email_enabled=False, statuses=list(DEFAULT_ALERT_STATUSES),
                       asset_ids=None, intervals=None, updated_at=None)
        return row

    async def save_for_user(self, user_id: int, email: Optional[str], email_enabled: bool,
                            statuses: Sequence[str], asset_ids: Optional[Sequence[int]],
                            intervals: Optional[Sequence[str]]) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE users SET email = $2, updated_at = CURRENT_TIMESTAMP WHERE id = $1",
                                   user_id, email)
                await conn.execute(
                    """INSERT INTO harmonic_setup_alert_settings
                        (user_id, email_enabled, statuses, asset_ids, intervals)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (user_id) DO UPDATE SET email_enabled = EXCLUDED.email_enabled,
                        statuses = EXCLUDED.statuses, asset_ids = EXCLUDED.asset_ids,
                        intervals = EXCLUDED.intervals, updated_at = NOW()""",
                    user_id, email_enabled, list(statuses),
                    list(asset_ids) if asset_ids is not None else None,
                    list(intervals) if intervals is not None else None,
                )
        return await self.get_for_user(user_id)

    async def get_email_subscribers(self) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            """SELECT s.user_id, u.username, u.email, s.statuses, s.asset_ids, s.intervals
            FROM harmonic_setup_alert_settings s JOIN users u ON u.id = s.user_id
            WHERE s.email_enabled AND u.is_active AND COALESCE(u.email, '') <> ''"""
        )

    async def create(self, **kwargs) -> Optional[int]:
        await self.save_for_user(**kwargs)
        return kwargs.get("user_id")

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_for_user(record_id) or None

    async def update(self, record_id: int, **kwargs) -> bool:
        await self.save_for_user(record_id, **kwargs)
        return True

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM harmonic_setup_alert_settings WHERE user_id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.fetch_all(
            "SELECT * FROM harmonic_setup_alert_settings ORDER BY user_id LIMIT $1 OFFSET $2", limit, offset
        )


class HarmonicSetupEventsTable(AbstractTable):
    """Zmiany statusów setupów wykryte przez śledzenie na żywo - kanał alertów (outbox) i historia.

    notified_at = NULL -> jeszcze nie wysłane mailem. Bez klucza obcego do setupu: zdarzenie ma
    zostać, nawet gdy janitor usunie starą serię setupów.
    """

    RETENTION_DAYS = 90

    def create_table(self) -> str:
        return """
        CREATE TABLE IF NOT EXISTS harmonic_setup_events (
            id BIGSERIAL PRIMARY KEY,
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            interval VARCHAR(10) NOT NULL,
            params_version VARCHAR(32) NOT NULL,
            pattern_type VARCHAR(40) NOT NULL,
            is_bullish BOOLEAN NOT NULL,
            x_time BIGINT NOT NULL,
            c_time BIGINT NOT NULL,
            from_status VARCHAR(16),
            to_status VARCHAR(16) NOT NULL,
            event_time BIGINT NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notified_at TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_harmonic_setup_events_pending
            ON harmonic_setup_events (created_at) WHERE notified_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_harmonic_setup_events_asset
            ON harmonic_setup_events (asset_id, interval, created_at DESC);
        """

    def cleanup_rules(self) -> List[CleanupRule]:
        return [CleanupRule(
            name="harmonic_setup_events.old",
            table="harmonic_setup_events",
            description=f"zdarzenia setupów starsze niż {self.RETENTION_DAYS} dni",
            where="created_at < NOW() - make_interval(days => $1)",
            args=(self.RETENTION_DAYS,),
        )]

    async def add_many(self, events: Sequence[Dict[str, Any]]) -> int:
        if not events:
            return 0
        async with self.pool.acquire() as conn:
            await conn.executemany(
                """INSERT INTO harmonic_setup_events (asset_id, interval, params_version, pattern_type, is_bullish,
                    x_time, c_time, from_status, to_status, event_time, payload)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                [(e["asset_id"], e["interval"], e["params_version"], e["pattern_type"], e["is_bullish"],
                  e["x_time"], e["c_time"], e.get("from_status"), e["to_status"], e["event_time"],
                  json.dumps(e["payload"])) for e in events],
            )
        return len(events)

    async def pending(self, limit: int = 1000) -> List[Dict[str, Any]]:
        rows = await self.fetch_all(
            """SELECT e.*, a.asset, a.quote FROM harmonic_setup_events e JOIN assets a ON a.id = e.asset_id
            WHERE e.notified_at IS NULL ORDER BY e.id LIMIT $1""",
            limit,
        )
        return [_decode(r) for r in rows]

    async def mark_notified(self, ids: Sequence[int]) -> None:
        if ids:
            await self.execute_query(
                "UPDATE harmonic_setup_events SET notified_at = NOW() WHERE id = ANY($1::bigint[])", list(ids)
            )

    async def recent(self, asset_ids: Optional[Sequence[int]] = None, interval: Optional[str] = None,
                     limit: int = 100) -> List[Dict[str, Any]]:
        args: List[Any] = [limit]
        where = []
        if asset_ids:
            args.append(list(asset_ids))
            where.append(f"e.asset_id = ANY(${len(args)}::int[])")
        if interval:
            args.append(interval)
            where.append(f"e.interval = ${len(args)}")
        rows = await self.fetch_all(
            f"""SELECT e.*, a.asset, a.quote FROM harmonic_setup_events e JOIN assets a ON a.id = e.asset_id
            {"WHERE " + " AND ".join(where) if where else ""}
            ORDER BY e.id DESC LIMIT $1""",  # nosemgrep: warunki stałe, wartości parametrami
            *args,
        )
        return [_decode(r) for r in rows]

    async def create(self, **kwargs) -> Optional[int]:
        await self.add_many([kwargs])
        return None

    async def get_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        row = await self.fetch_one("SELECT * FROM harmonic_setup_events WHERE id = $1", record_id)
        return _decode(row) if row else None

    async def update(self, record_id: int, **kwargs) -> bool:
        return False

    async def delete(self, record_id: int) -> bool:
        await self.execute_query("DELETE FROM harmonic_setup_events WHERE id = $1", record_id)
        return True

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return await self.recent(limit=limit)


def _decode(row: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(row.get("payload"), str):
        row["payload"] = json.loads(row["payload"])
    return row
