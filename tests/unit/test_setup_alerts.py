"""
Unit testy śledzonych assetów i alertów setupów: zdarzenia zmian statusów, harmonogram godzinny,
dobór odbiorców i treść maili, wysyłka (atrapa SMTP) oraz endpointy /harmonics/tracked-assets
i /harmonics/alerts - bez bazy, sieci i serwera poczty.
"""

import asyncio
import unittest
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from main_controller_sync import harmonic_scan_due
from src import controller_rest_domain_harmonics as harmonics_api
from src import harmonic_alerts as ha
from src import harmonic_setups as hs
from src.auth import AuthUser, require_admin, require_auth

H = 3_600_000


def row(status, created=100 * H, entry=None, exit_=None, x=1):
    return {"asset_id": 1, "interval": "1h", "params_version": "v", "pattern_type": "gartley",
            "is_bullish": True, "x_time": x, "a_time": 2, "b_time": 3, "c_time": 4,
            "points_json": {}, "prz_min": 1.0, "prz_max": 2.0, "created_time": created,
            "status": status, "entry_time": entry, "entry_price": 1.5 if entry else None,
            "sl": 1.0 if entry else None, "tp1": 2.5 if entry else None, "tp2": 3.0 if entry else None,
            "exit_time": exit_, "r_multiple": 2.0 if status == "win" else None, "targets_source": "app"}


def key(r):
    return (r["pattern_type"], r["x_time"], r["a_time"], r["b_time"], r["c_time"])


class TestStatusEvents(unittest.TestCase):
    def test_known_setup_changing_status_is_always_an_event(self):
        r = row("win", entry=50 * H, exit_=60 * H)
        events = hs.status_events([r], {key(r): "open"}, "BTC/USDT", new_since=99 * H)
        self.assertEqual([(e["from_status"], e["to_status"], e["event_time"]) for e in events],
                         [("open", "win", 60 * H)])
        self.assertEqual(events[0]["payload"]["symbol"], "BTC/USDT")

    def test_unchanged_status_is_not_an_event(self):
        r = row("waiting")
        self.assertEqual(hs.status_events([r], {key(r): "waiting"}, "B", new_since=0), [])

    def test_new_setups_only_when_recent(self):
        fresh, old = row("waiting", created=100 * H), row("open", created=10 * H, entry=20 * H, x=9)
        events = hs.status_events([fresh, old], {}, "B", new_since=97 * H)
        self.assertEqual([(e["from_status"], e["to_status"]) for e in events], [(None, "waiting")])


class TestHourlySchedule(unittest.TestCase):
    targets = [{"asset_id": 1, "interval": i} for i in ("1h", "4h", "1d", "7x")]

    def due(self, hour):
        now = 20_000 * 24 * H + hour * H + 3 * 60_000  # hh:03 UTC
        return [t["interval"] for t in harmonic_scan_due(self.targets, now)]

    def test_hourly_every_hour_4h_and_daily_on_their_closes(self):
        self.assertEqual(self.due(0), ["1h", "4h", "1d"])
        self.assertEqual(self.due(4), ["1h", "4h"])
        self.assertEqual(self.due(5), ["1h"])


def event(eid, status="win", asset=1, interval="1h"):
    return {"id": eid, "asset_id": asset, "interval": interval, "pattern_type": "bat", "is_bullish": False,
            "from_status": "open", "to_status": status, "event_time": 100 * H,
            "payload": {"symbol": "ETH/USDT", "prz": [10, 11], "entry_price": 10.5, "sl": 12, "tp1": 9,
                        "tp2": 8, "r_multiple": 1.0}}


SUB_ALL = {"user_id": 1, "email": "a@x.io", "statuses": ["win", "loss"], "asset_ids": None, "intervals": None}
SUB_4H = {"user_id": 2, "email": "b@x.io", "statuses": ["win"], "asset_ids": [1], "intervals": ["4h"]}


class TestRecipientsAndRendering(unittest.TestCase):
    def test_filters_by_status_asset_and_interval(self):
        out = ha.recipients([event(1), event(2, "open"), event(3, interval="4h")], [SUB_ALL, SUB_4H])
        self.assertEqual([(s["user_id"], [e["id"] for e in es]) for s, es in out], [(1, [1, 3]), (2, [3])])

    def test_render(self):
        subject, body = ha.render(SUB_ALL, [event(1)])
        self.assertIn("ETH/USDT 1h bat - win", subject)
        self.assertIn("SHORT", body)
        self.assertIn("+1.00 R", body)
        subject, _ = ha.render(SUB_ALL, [event(1), event(2, "loss")])
        self.assertIn("2 zmian", subject)


def alerts_db(events, subscribers):
    events_table = mock.MagicMock()
    events_table.pending = mock.AsyncMock(return_value=events)
    events_table.mark_notified = mock.AsyncMock()
    factory = mock.MagicMock()
    factory.get_harmonic_setup_events_table.return_value = events_table
    factory.get_harmonic_setup_alert_settings_table.return_value.get_email_subscribers = mock.AsyncMock(
        return_value=subscribers)
    return mock.MagicMock(get_factory=mock.MagicMock(return_value=factory)), events_table


SMTP = ha.SmtpSettings(host="smtp.test")


class TestNotifyPending(unittest.TestCase):
    def test_without_smtp_events_wait(self):
        db, table = alerts_db([event(1)], [SUB_ALL])
        self.assertEqual(asyncio.run(ha.notify_pending(db, None))["smtp"], False)
        table.pending.assert_not_awaited()
        table.mark_notified.assert_not_awaited()

    def test_one_mail_per_user_and_events_marked(self):
        db, table = alerts_db([event(1), event(2, "loss")], [SUB_ALL, SUB_4H])
        send = mock.MagicMock()
        res = asyncio.run(ha.notify_pending(db, SMTP, send=send))
        self.assertEqual(res["sent"], 1)
        self.assertEqual(send.call_args.args[1], "a@x.io")
        table.mark_notified.assert_awaited_once_with([1, 2])

    def test_a_failed_mail_does_not_resend_to_others(self):
        db, table = alerts_db([event(1)], [SUB_ALL, {**SUB_4H, "intervals": None}])
        send = mock.MagicMock(side_effect=[OSError("refused"), None])
        res = asyncio.run(ha.notify_pending(db, SMTP, send=send))
        self.assertEqual((res["sent"], res["failed_users"]), (1, [1]))
        table.mark_notified.assert_awaited_once_with([1])

    def test_send_email_uses_starttls_and_login(self):
        with mock.patch("smtplib.SMTP") as smtp:
            ha.send_email(ha.SmtpSettings(host="h", username="u", password="p", sender="s@x"), "t@x", "S", "B")
        server = smtp.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("u", "p")
        self.assertEqual(server.send_message.call_args.args[0]["To"], "t@x")

    def test_settings_from_config(self):
        cfg = mock.MagicMock(smtp_host=None)
        self.assertIsNone(ha.SmtpSettings.from_config(cfg))
        cfg = mock.MagicMock(smtp_host="h", smtp_port=465, smtp_username="u", smtp_password="p",
                             smtp_from=None, smtp_starttls=False, smtp_ssl=True)
        s = ha.SmtpSettings.from_config(cfg)
        self.assertEqual((s.port, s.ssl, s.sender), (465, True, "trading.ai <u>"))


class TestEndpoints(unittest.TestCase):
    def setUp(self):
        self.tracked = mock.MagicMock()
        self.tracked.get_by_id = mock.AsyncMock(return_value={"asset_id": 1, "setup_intervals": ["1h"]})
        self.tracked.upsert = mock.AsyncMock(side_effect=lambda a, p, i: {"asset_id": a, "setup_intervals": i})
        self.tracked.delete = mock.AsyncMock(return_value=False)
        self.tracked.list_with_assets = mock.AsyncMock(return_value=[])
        self.alerts = mock.MagicMock()
        self.alerts.get_for_user = mock.AsyncMock(return_value={"user_id": 7, "email": None})
        self.alerts.save_for_user = mock.AsyncMock(return_value={"user_id": 7, "email": "a@x.io"})
        factory = mock.MagicMock()
        factory.get_tracked_assets_table.return_value = self.tracked
        factory.get_harmonic_setup_alert_settings_table.return_value = self.alerts
        factory.get_assets_table.return_value.get_by_id = mock.AsyncMock(return_value={"id": 1})
        factory.get_harmonic_setup_events_table.return_value.recent = mock.AsyncMock(return_value=[])
        db = mock.MagicMock(get_factory=mock.MagicMock(return_value=factory))
        self.enqueue = mock.MagicMock(side_effect=lambda a, i, c: f"t-{i}")
        for p in [mock.patch.object(harmonics_api, "get_db", mock.AsyncMock(return_value=db)),
                  mock.patch.object(harmonics_api, "_enqueue_setups", self.enqueue)]:
            p.start()
            self.addCleanup(p.stop)
        app = FastAPI()
        app.include_router(harmonics_api.router, prefix=harmonics_api.PREFIX)
        user = AuthUser({"user_id": 7, "username": "u", "role": "user"})
        app.dependency_overrides[require_auth] = lambda: user
        app.dependency_overrides[require_admin] = lambda: user
        self.client = TestClient(app)

    def test_put_tracked_backfills_only_new_intervals(self):
        r = self.client.put("/harmonics/tracked-assets/1", json={"setup_intervals": ["1h", "4h"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([t["interval"] for t in r.json()["backfill_tasks"]], ["4h"])
        self.enqueue.assert_called_once_with(1, "4h", 5000)

    def test_put_tracked_rejects_unknown_interval(self):
        self.assertEqual(self.client.put("/harmonics/tracked-assets/1", json={"setup_intervals": ["9x"]}).status_code, 422)

    def test_delete_untracked_is_404(self):
        self.assertEqual(self.client.delete("/harmonics/tracked-assets/1").status_code, 404)

    def test_alert_settings_are_per_user_and_validated(self):
        r = self.client.get("/harmonics/alerts/settings")
        self.assertEqual(r.status_code, 200)
        self.alerts.get_for_user.assert_awaited_with(7)
        self.assertIn("available_statuses", r.json())
        self.assertEqual(self.client.put("/harmonics/alerts/settings",
                                         json={"email_enabled": True}).status_code, 422)
        self.assertEqual(self.client.put("/harmonics/alerts/settings",
                                         json={"email": "not-an-email"}).status_code, 422)
        self.assertEqual(self.client.put("/harmonics/alerts/settings",
                                         json={"email": "a@x.io", "statuses": ["moon"]}).status_code, 422)
        r = self.client.put("/harmonics/alerts/settings",
                            json={"email": " a@x.io ", "email_enabled": True, "statuses": ["win", "win"]})
        self.assertEqual(r.status_code, 200)
        args = self.alerts.save_for_user.await_args.args
        self.assertEqual(args[:4], (7, "a@x.io", True, ["win"]))

    def test_test_mail_requires_smtp(self):
        with mock.patch.object(harmonics_api.config, "smtp_host", None):
            self.assertEqual(self.client.post("/harmonics/alerts/test").status_code, 503)

    def test_routes_are_not_shadowed_by_the_range_route(self):
        self.assertEqual(self.client.get("/harmonics/alerts/events").status_code, 200)
        self.assertEqual(self.client.get("/harmonics/tracked-assets").status_code, 200)


if __name__ == "__main__":
    unittest.main()
