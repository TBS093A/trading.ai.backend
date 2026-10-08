"""
Alerty mailowe o zmianach setupów XABCD (zdarzenia z harmonic_setup_events).

Każdy użytkownik dostaje co najwyżej jeden mail na przebieg - zestawienie zdarzeń pasujących do
jego ustawień (harmonic_setup_alert_settings: statusy, assety, interwały). SMTP z konfiguracji
(SMTP_*); bez SMTP_HOST zdarzenia czekają w bazie (nic nie jest oznaczane jako wysłane).
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "waiting": "nowy setup - czeka na wejście w PRZ",
    "open": "pozycja otwarta",
    "win": "zamknięta na TP1",
    "loss": "zamknięta na SL",
    "expired": "zamknięta po czasie",
    "no_entry": "bez wejścia (minął czas)",
    "invalidated": "unieważniony (C przebite)",
}


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int = 587
    username: Optional[str] = None
    password: Optional[str] = None
    sender: str = "trading.ai <noreply@localhost>"
    starttls: bool = True
    ssl: bool = False
    timeout: int = 20

    @classmethod
    def from_config(cls, config) -> Optional["SmtpSettings"]:
        if not getattr(config, "smtp_host", None):
            return None
        return cls(
            host=config.smtp_host, port=int(config.smtp_port or 587), username=config.smtp_username or None,
            password=config.smtp_password or None, sender=config.smtp_from or f"trading.ai <{config.smtp_username}>",
            starttls=config.smtp_starttls, ssl=config.smtp_ssl,
        )


def matches(event: Dict[str, Any], subscriber: Dict[str, Any]) -> bool:
    if event["to_status"] not in (subscriber.get("statuses") or []):
        return False
    if subscriber.get("asset_ids") is not None and event["asset_id"] not in subscriber["asset_ids"]:
        return False
    if subscriber.get("intervals") is not None and event["interval"] not in subscriber["intervals"]:
        return False
    return True


def recipients(events: Sequence[Dict[str, Any]],
               subscribers: Iterable[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    out = []
    for sub in subscribers:
        mine = [e for e in events if matches(e, sub)]
        if mine:
            out.append((sub, mine))
    return out


def _fmt_time(ms: Optional[int]) -> str:
    if ms is None:
        return "-"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _fmt_price(p: Optional[float]) -> str:
    if p is None:
        return "-"
    return f"{p:.8g}"


def describe(event: Dict[str, Any]) -> str:
    p = event.get("payload") or {}
    direction = "LONG" if event["is_bullish"] else "SHORT"
    head = (f"{p.get('symbol', event['asset_id'])} [{event['interval']}] {event['pattern_type']} {direction}: "
            f"{STATUS_LABELS.get(event['to_status'], event['to_status'])}")
    if event.get("from_status"):
        head += f" (wcześniej: {event['from_status']})"
    lines = [head, f"  czas: {_fmt_time(event['event_time'])}"]
    prz = p.get("prz") or [None, None]
    lines.append(f"  PRZ: {_fmt_price(prz[0])} - {_fmt_price(prz[1])}")
    if p.get("entry_price") is not None:
        lines.append(f"  wejście: {_fmt_price(p['entry_price'])}  SL: {_fmt_price(p.get('sl'))}  "
                     f"TP1: {_fmt_price(p.get('tp1'))}  TP2: {_fmt_price(p.get('tp2'))}")
    if p.get("r_multiple") is not None:
        lines.append(f"  wynik: {p['r_multiple']:+.2f} R")
    return "\n".join(lines)


def render(subscriber: Dict[str, Any], events: Sequence[Dict[str, Any]]) -> Tuple[str, str]:
    counts: Dict[str, int] = {}
    for e in events:
        counts[e["to_status"]] = counts.get(e["to_status"], 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    if len(events) == 1:
        e = events[0]
        subject = (f"[trading.ai] {(e.get('payload') or {}).get('symbol', e['asset_id'])} {e['interval']} "
                   f"{e['pattern_type']} - {e['to_status']}")
    else:
        subject = f"[trading.ai] {len(events)} zmian setupów ({summary})"
    body = "\n\n".join(describe(e) for e in events)
    body += ("\n\n--\nUstawienia alertów: zakładka Skuteczność formacji -> Alerty. "
             "Setup = X..C + PRZ znane w chwili zdarzenia; SL/TP wg reguł z wykresu.")
    return subject, body


def send_email(settings: SmtpSettings, to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    context = ssl.create_default_context()
    if settings.ssl:
        server = smtplib.SMTP_SSL(settings.host, settings.port, timeout=settings.timeout, context=context)
    else:
        server = smtplib.SMTP(settings.host, settings.port, timeout=settings.timeout)
    with server:
        if settings.starttls and not settings.ssl:
            server.starttls(context=context)
        if settings.username:
            server.login(settings.username, settings.password or "")
        server.send_message(msg)


async def notify_pending(db, settings: Optional[SmtpSettings], send=send_email,
                         limit: int = 1000) -> Dict[str, Any]:
    """Wysyła zestawienia oczekujących zdarzeń i oznacza je jako obsłużone.

    Zdarzenia oznaczamy po próbie wysyłki wszystkim odbiorcom - nieudany mail do jednej osoby jest
    logowany, ale nie powoduje ponownej wysyłki pozostałym.
    """
    import asyncio

    if settings is None:
        logger.warning("Alerty setupów: brak SMTP_HOST - zdarzenia czekają na konfigurację poczty")
        return {"sent": 0, "events": 0, "smtp": False}
    factory = db.get_factory()
    events_table = factory.get_harmonic_setup_events_table()
    events = await events_table.pending(limit)
    if not events:
        return {"sent": 0, "events": 0, "smtp": True}
    subscribers = await factory.get_harmonic_setup_alert_settings_table().get_email_subscribers()
    sent, failed = 0, []
    for sub, mine in recipients(events, subscribers):
        subject, body = render(sub, mine)
        try:
            await asyncio.to_thread(send, settings, sub["email"], subject, body)
            sent += 1
        except Exception as e:
            logger.error(f"Alert do użytkownika {sub['user_id']} nie wysłany: {e}")
            failed.append(sub["user_id"])
    await events_table.mark_notified([e["id"] for e in events])
    logger.info(f"Alerty setupów: {len(events)} zdarzeń, {sent} maili, nieudane: {failed or 'brak'}")
    return {"sent": sent, "events": len(events), "failed_users": failed, "smtp": True}
