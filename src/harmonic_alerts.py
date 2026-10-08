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


class SmtpSession:
    """Jedno połączenie SMTP (STARTTLS / SSL + login) na cały przebieg notifiera.

    Błąd połączenia albo logowania wychodzi już z __enter__ - wtedy nic nie zostało wysłane.
    """

    def __init__(self, settings: SmtpSettings):
        self.settings = settings
        self.server = None

    def __enter__(self) -> "SmtpSession":
        st = self.settings
        context = ssl.create_default_context()
        if st.ssl:
            self.server = smtplib.SMTP_SSL(st.host, st.port, timeout=st.timeout, context=context)
        else:
            self.server = smtplib.SMTP(st.host, st.port, timeout=st.timeout)
        try:
            if st.starttls and not st.ssl:
                self.server.starttls(context=context)
            if st.username:
                self.server.login(st.username, st.password or "")
        except Exception:
            self.server.close()
            raise
        return self

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.settings.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        self.server.send_message(msg)

    def __exit__(self, *exc) -> None:
        try:
            self.server.quit()
        except Exception:
            self.server.close()


def send_email(settings: SmtpSettings, to: str, subject: str, body: str) -> None:
    with SmtpSession(settings) as session:
        session.send(to, subject, body)


# Błędy, po których nie ma sensu wysyłać dalej w tym przebiegu - serwer / sieć / logowanie.
# Odmowa dla jednego adresu (SMTPRecipientsRefused, SMTPDataError) dotyczy tylko tego maila.
CONNECTION_ERRORS = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                     smtplib.SMTPAuthenticationError, smtplib.SMTPHeloError, OSError)
# Zdarzenie, które czekało dłużej (np. poczta nie działała), zamykamy bez maila - alert o wejściu
# w pozycję sprzed doby to już nie alert.
MAX_EVENT_AGE_S = 24 * 3600


async def notify_pending(db, settings: Optional[SmtpSettings], session_factory=SmtpSession,
                         limit: int = 1000, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Wysyła zestawienia oczekujących zdarzeń; oznacza jako obsłużone tylko to, co doszło.

    - brak SMTP albo błąd połączenia / logowania -> nic nie jest oznaczane, następny przebieg ponawia;
    - błąd połączenia w trakcie -> oznaczone są zdarzenia, które dostali już wszyscy ich odbiorcy
      (pozostali dostaną je w następnym przebiegu, część osób może dostać je drugi raz);
    - odmowa dla jednego adresu -> logujemy i traktujemy jak obsłużone (ponowienie nic nie da);
    - zdarzenia starsze niż MAX_EVENT_AGE_S są zamykane bez maila.
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

    now = now or datetime.now(timezone.utc)
    stale = [e for e in events if e.get("created_at") and (now - e["created_at"]).total_seconds() > MAX_EVENT_AGE_S]
    stale_ids = {e["id"] for e in stale}
    fresh = [e for e in events if e["id"] not in stale_ids]

    subscribers = await factory.get_harmonic_setup_alert_settings_table().get_email_subscribers()
    plan = recipients(fresh, subscribers)
    owed: Dict[int, int] = {e["id"]: 0 for e in fresh}       # ilu odbiorcom zdarzenie jest winne
    for _, mine in plan:
        for e in mine:
            owed[e["id"]] += 1

    def deliver() -> Tuple[int, List[int], Optional[str]]:
        sent, refused, aborted = 0, [], None
        if not plan:
            return sent, refused, aborted
        try:
            with session_factory(settings) as session:
                for sub, mine in plan:
                    subject, body = render(sub, mine)
                    try:
                        session.send(sub["email"], subject, body)
                        sent += 1
                    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPDataError,
                            smtplib.SMTPSenderRefused) as e:
                        logger.error(f"Alert do użytkownika {sub['user_id']} odrzucony: {e}")
                        refused.append(sub["user_id"])
                    except CONNECTION_ERRORS as e:
                        aborted = f"{type(e).__name__}: {e}"
                        break
                    for e in mine:
                        owed[e["id"]] -= 1
        except CONNECTION_ERRORS as e:
            aborted = f"{type(e).__name__}: {e}"
        return sent, refused, aborted

    sent, refused, aborted = await asyncio.to_thread(deliver)
    done = sorted(stale_ids | {eid for eid, left in owed.items() if left == 0})
    await events_table.mark_notified(done)
    result = {"sent": sent, "events": len(events), "marked": len(done), "stale": len(stale_ids),
              "refused_users": refused, "smtp": True}
    if aborted:
        result["aborted"] = aborted
        logger.error(f"Alerty setupów: przerwane ({aborted}) - {len(events) - len(done)} zdarzeń czeka na ponowienie")
    logger.info(f"Alerty setupów: {result}")
    return result
