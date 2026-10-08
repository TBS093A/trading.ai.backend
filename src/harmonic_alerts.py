"""
Alerty mailowe o zmianach setupów XABCD (zdarzenia z harmonic_setup_events).

Każdy użytkownik dostaje co najwyżej jeden mail na przebieg - zestawienie zdarzeń pasujących do
jego ustawień (harmonic_setup_alert_settings: statusy, assety, interwały). SMTP z konfiguracji
(SMTP_*); bez SMTP_HOST zdarzenia czekają w bazie (nic nie jest oznaczane jako wysłane).

Mail ma dwie wersje: HTML w stylu frontu (szablon src/templates/email/setup_alerts.html, Jinja2 z
autoescape) i zwykły tekst (describe) dla klientów bez HTML.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

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
    strength = _strength_view(p.get("strength"))
    if strength:
        lines.append(f"  siła ({strength['kind']}): {strength['score']}/100"
                     + (f", szansa TP1 {strength['p_win']}" if strength["p_win"] else ""))
    return "\n".join(lines)


# Motyw frontu (trading.ai.frontend src/styles: --bg-*, --text-*, --accent-*).
THEME = {
    "bg": "#060810", "card": "#0f1419", "border": "#21262d",
    "text": "#e6edf3", "secondary": "#8b949e", "muted": "#484f58",
    "accent": "#00f0ff", "accent_dim": "#00a0aa",
    "green": "#00ff88", "red": "#ff3366", "yellow": "#ffcc00", "orange": "#ff9933",
    "purple": "#9945ff", "magenta": "#ff00aa",
}
FONTS = {
    "sans": "'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif",
    "mono": "'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
}
STATUS_STYLE = {   # status -> (krótka etykieta, kolor)
    "waiting": ("WAITING", THEME["yellow"]),
    "open": ("OPEN", THEME["accent"]),
    "win": ("WIN", THEME["green"]),
    "loss": ("LOSS", THEME["red"]),
    "expired": ("EXPIRED", THEME["orange"]),
    "no_entry": ("NO ENTRY", THEME["secondary"]),
    "invalidated": ("INVALIDATED", THEME["purple"]),
}
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "email"


@lru_cache(maxsize=1)
def _templates() -> Environment:
    # Szablon maila z repo, autoescape włączony - nie renderujemy szablonów od użytkownika.
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)),  # nosemgrep
                       autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)  # nosemgrep


def app_url_from_config(config) -> Optional[str]:
    """Adres frontu do przycisku w mailu: FRONTEND_URL, inaczej pierwszy origin z CORS."""
    url = (getattr(config, "frontend_url", "") or "").strip()
    if not url:
        origins = (getattr(config, "cors_allowed_origins_str", "") or "").split(",")
        url = next((o.strip() for o in origins if o.strip().startswith("https://")), "")
    return url.rstrip("/") or None


def _local_time(ms: Optional[int]) -> str:
    if ms is None:
        return "-"
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ms / 1000, tz=ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:   # obraz bez bazy stref czasowych - zostaje UTC
        return ""


def _plural_changes(n: int) -> str:
    if n == 1:
        return "1 zmiana setupu"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} zmiany setupów"
    return f"{n} zmian setupów"


def chart_link(app_url: Optional[str], e: Dict[str, Any]) -> Optional[str]:
    """Link do wykresu z tym setupem (front czyta parametry z URL - view, asset_id, interval, t, setup)."""
    if not app_url:
        return None
    from urllib.parse import urlencode

    query = {"view": "chart", "asset_id": e["asset_id"], "interval": e["interval"], "t": e["event_time"],
             "pattern": e["pattern_type"], "x": e.get("x_time"), "c": e.get("c_time")}
    return f"{app_url}/?{urlencode({k: v for k, v in query.items() if v is not None})}"


def _strength_view(strength: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not strength or strength.get("score") is None:
        return None
    score = int(strength["score"])
    return {"score": score, "kind": "wstępna" if strength.get("kind") == "pre" else "pełna",
            "bg": f"rgba(0,255,136,{0.06 + 0.34 * score / 100:.2f})",
            "p_win": f"{round(100 * strength['p_win'])}%" if strength.get("p_win") is not None else None,
            "factors": [f["label"] for f in (strength.get("factors") or [])[:3]]}


def _event_view(e: Dict[str, Any], app_url: Optional[str] = None) -> Dict[str, Any]:
    p = e.get("payload") or {}
    label, color = STATUS_STYLE.get(e["to_status"], (e["to_status"].upper(), THEME["secondary"]))
    bull = bool(e["is_bullish"])
    prz = p.get("prz") or [None, None]
    levels = [{"label": "PRZ", "value": f"{_fmt_price(prz[0])} – {_fmt_price(prz[1])}", "color": THEME["text"]}]
    if p.get("entry_price") is not None:
        levels += [
            {"label": "Wejście", "value": _fmt_price(p["entry_price"]), "color": THEME["accent"]},
            {"label": "SL", "value": _fmt_price(p.get("sl")), "color": THEME["red"]},
            {"label": "TP1", "value": _fmt_price(p.get("tp1")), "color": THEME["green"]},
            {"label": "TP2", "value": _fmt_price(p.get("tp2")), "color": THEME["green"]},
        ]
    r = p.get("r_multiple")
    return {
        "symbol": p.get("symbol", str(e["asset_id"])), "interval": e["interval"], "pattern": e["pattern_type"],
        "direction": "LONG" if bull else "SHORT",
        "direction_color": THEME["green"] if bull else THEME["red"],
        "direction_bg": "rgba(0,255,136,0.12)" if bull else "rgba(255,51,102,0.12)",
        "status_label": label, "status_color": color,
        "from_label": STATUS_STYLE.get(e.get("from_status"), (None,))[0] if e.get("from_status") else None,
        "description": STATUS_LABELS.get(e["to_status"], e["to_status"]),
        "r": f"{r:+.2f} R" if r is not None else None,
        "r_color": THEME["green"] if (r or 0) > 0 else THEME["red"],
        "levels": levels,
        "time_utc": _fmt_time(e["event_time"]), "time_local": _local_time(e["event_time"]),
        "strength": _strength_view(p.get("strength")),
        "chart_url": chart_link(app_url, e),
    }


def _subject(events: Sequence[Dict[str, Any]], counts: Dict[str, int]) -> str:
    if len(events) == 1:
        e = events[0]
        return (f"[trading.ai] {(e.get('payload') or {}).get('symbol', e['asset_id'])} {e['interval']} "
                f"{e['pattern_type']} - {e['to_status']}")
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    return f"[trading.ai] {_plural_changes(len(events))} ({summary})"


def render(subscriber: Dict[str, Any], events: Sequence[Dict[str, Any]],
           app_url: Optional[str] = None) -> Tuple[str, str, str]:
    """(temat, tekst, HTML) zestawienia zdarzeń dla jednego odbiorcy."""
    counts: Dict[str, int] = {}
    for e in events:
        counts[e["to_status"]] = counts.get(e["to_status"], 0) + 1
    subject = _subject(events, counts)
    body = "\n\n".join(describe(e) + (f"\n  wykres: {chart_link(app_url, e)}" if app_url else "") for e in events)
    body += ("\n\n--\nUstawienia alertów: zakładka Skuteczność formacji -> Alerty. "
             "Setup = X..C + PRZ znane w chwili zdarzenia; SL/TP wg reguł z wykresu.")
    if app_url:
        body += f"\n{app_url}"

    views = [_event_view(e, app_url) for e in events]
    if len(views) == 1:
        v = views[0]
        headline = f"{v['symbol']} {v['interval']} {v['pattern']}: {v['description']}"
    else:
        headline = _plural_changes(len(views))
    summary = [{"label": STATUS_STYLE.get(k, (k.upper(),))[0], "count": n,
                "color": STATUS_STYLE.get(k, (None, THEME["secondary"]))[1]}
               for k, n in sorted(counts.items(), key=lambda kv: list(STATUS_STYLE).index(kv[0])
                                  if kv[0] in STATUS_STYLE else 99)]
    html = _templates().get_template("setup_alerts.html").render(
        subject=subject, headline=headline, preheader=" · ".join(f"{s['label']} {s['count']}" for s in summary),
        summary=summary, events=views, app_url=app_url, settings_url=None, c=THEME, f=FONTS,
    )
    return subject, body, html


def sample_event() -> Dict[str, Any]:
    """Przykładowe zdarzenie do maila testowego (POST /harmonics/alerts/test)."""
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "id": 0, "asset_id": 0, "interval": "1h", "pattern_type": "gartley", "is_bullish": True,
        "from_status": "open", "to_status": "win", "event_time": now,
        "x_time": now - 40 * 3_600_000, "c_time": now - 10 * 3_600_000,
        "payload": {"symbol": "BTC/USDT (przykład)", "prz": [61850.0, 62120.5], "entry_price": 62120.5,
                    "sl": 61240.0, "tp1": 63550.0, "tp2": 64480.0, "r_multiple": 1.62,
                    "strength": {"score": 82, "p_win": 0.46, "kind": "entry",
                                 "factors": [{"label": "bullish engulfing (zgodna z kierunkiem)", "impact": 0.4}]}},
    }


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

    def send(self, to: str, subject: str, body: str, html: Optional[str] = None) -> None:
        msg = EmailMessage()
        msg["From"] = self.settings.sender
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        self.server.send_message(msg)

    def __exit__(self, *exc) -> None:
        try:
            self.server.quit()
        except Exception:
            self.server.close()


def send_email(settings: SmtpSettings, to: str, subject: str, body: str, html: Optional[str] = None) -> None:
    with SmtpSession(settings) as session:
        session.send(to, subject, body, html)


# Błędy, po których nie ma sensu wysyłać dalej w tym przebiegu - serwer / sieć / logowanie.
# Odmowa dla jednego adresu (SMTPRecipientsRefused, SMTPDataError) dotyczy tylko tego maila.
CONNECTION_ERRORS = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                     smtplib.SMTPAuthenticationError, smtplib.SMTPHeloError, OSError)
# Zdarzenie, które czekało dłużej (np. poczta nie działała), zamykamy bez maila - alert o wejściu
# w pozycję sprzed doby to już nie alert.
MAX_EVENT_AGE_S = 24 * 3600


async def notify_pending(db, settings: Optional[SmtpSettings], session_factory=SmtpSession,
                         limit: int = 1000, now: Optional[datetime] = None,
                         app_url: Optional[str] = None) -> Dict[str, Any]:
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
                    subject, body, html = render(sub, mine, app_url)
                    try:
                        session.send(sub["email"], subject, body, html)
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
