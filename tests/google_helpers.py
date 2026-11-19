"""Dobles de prueba para Gmail y Google Calendar, sin red ni credenciales."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from jarvis.core.consent import ConsentManager
from jarvis.integrations.google_calendar import (
    CalendarEvent,
    CalendarWindow,
)
from jarvis.integrations.google_mail import MailDetail, MailMessage

SANTIAGO = ZoneInfo("America/Santiago")


def at(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SANTIAGO)


def message(
    message_id: str = "gmail-1",
    *,
    subject: str = "Informe mensual",
    sender_name: str = "Ana Pérez",
    sender_address: str = "ana@example.com",
    received: datetime | None = None,
    is_read: bool = False,
    importance: str = "normal",
    attachments: bool = False,
    preview: str = "Resumen del informe",
) -> MailMessage:
    return MailMessage(
        id=message_id,
        subject=subject,
        sender_name=sender_name,
        sender_address=sender_address,
        received=received or at(2026, 11, 17, 8, 30),
        is_read=is_read,
        importance=importance,
        has_attachments=attachments,
        preview=preview,
    )


def detail(
    item: MailMessage | None = None,
    *,
    body: str = "Hola equipo:\n\nAdjunto el informe.",
) -> MailDetail:
    return MailDetail(
        message=item or message(),
        body_text=body,
        to=("Jarvis <jarvis@example.com>",),
        cc=(),
    )


def event(
    event_id: str = "ev-1",
    *,
    subject: str = "Revisión semanal",
    start: datetime | None = None,
    end: datetime | None = None,
    location: str = "Sala 3",
    organizer: str = "Ana Pérez <ana@example.com>",
    attendees: tuple[str, ...] = ("Ana Pérez", "Luis Soto"),
    all_day: bool = False,
    show_as: str = "busy",
) -> CalendarEvent:
    begin = start or at(2026, 11, 17, 9, 0)
    finish = end or at(2026, 11, 17, 10, 0)
    return CalendarEvent(
        id=event_id,
        subject=subject,
        start=begin,
        end=finish,
        location=location,
        organizer=organizer,
        attendees=attendees,
        is_all_day=all_day,
        show_as=show_as,
    )


@dataclass
class FakeMailService:
    messages: tuple[MailMessage, ...] = (message(),)
    bodies: dict[str, str] = field(
        default_factory=lambda: {"gmail-1": "Hola equipo:\n\nAdjunto el informe."}
    )
    list_calls: int = 0
    detail_calls: list[str] = field(default_factory=list)
    error: Exception | None = None

    def list_recent(self, limit: int | None = None) -> tuple[MailMessage, ...]:
        self.list_calls += 1
        if self.error is not None:
            raise self.error
        if limit is None:
            return self.messages
        return self.messages[:limit]

    def get_message(self, message_id: str) -> MailDetail:
        self.detail_calls.append(message_id)
        if self.error is not None:
            raise self.error
        found = next(
            (item for item in self.messages if item.id == message_id),
            message(message_id),
        )
        return detail(found, body=self.bodies.get(message_id, ""))


@dataclass
class FakeCalendarService:
    events: tuple[CalendarEvent, ...] = (event(),)
    now_value: datetime = field(default_factory=lambda: at(2026, 11, 17, 7, 0))
    windows: list[str] = field(default_factory=list)
    error: Exception | None = None

    def now(self) -> datetime:
        return self.now_value

    def list_window(
        self, period: str, *, now: datetime | None = None
    ) -> CalendarWindow:
        self.windows.append(period)
        if self.error is not None:
            raise self.error
        start = now or self.now_value
        return CalendarWindow(
            period=period,
            start=start,
            end=start,
            events=self.events,
            fetched_at=start,
        )


@dataclass
class FakeProvider:
    replies: list[str] = field(default_factory=lambda: ["Resumen generado."])
    prompts: list[str] = field(default_factory=list)

    def complete(self, *, prompt: str, **_kwargs: Any) -> str:
        self.prompts.append(prompt)
        if self.replies:
            return self.replies.pop(0)
        return ""


class FakeGoogleSession:
    """Sesión de Google con servicios en memoria."""

    def __init__(
        self,
        *,
        configured: bool = True,
        connected: bool = True,
        problem: str = "",
        account: str = "Ana Pérez (ana@example.com)",
        mail: FakeMailService | None = None,
        calendar: FakeCalendarService | None = None,
        connect_error: Exception | None = None,
    ) -> None:
        self._configured = configured
        self._connected = connected
        self.problem = problem
        self.account = account if connected else ""
        self.mail = mail or FakeMailService()
        self.calendar = calendar or FakeCalendarService()
        self.connect_error = connect_error
        self.cancelled = False
        self.disconnects = 0
        self.connects = 0
        self.expired = 0

    @property
    def configured(self) -> bool:
        return self._configured

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, *, cancel_event=None) -> str:
        self.connects += 1
        if self.connect_error is not None:
            raise self.connect_error
        self._connected = True
        if not self.account:
            self.account = "Ana Pérez (ana@example.com)"
        return self.account

    def disconnect(self) -> None:
        self.disconnects += 1
        self._connected = False
        self.account = ""

    def cancel(self) -> None:
        self.cancelled = True

    def mark_expired(self) -> None:
        self.expired += 1
        self._connected = False
        self.account = ""

    def mail_service(self) -> FakeMailService:
        return self.mail

    def calendar_service(self) -> FakeCalendarService:
        return self.calendar

    def status(self) -> dict[str, Any]:
        return {
            "configured": self._configured,
            "connected": self._connected,
            "account": self.account,
            "problem": self.problem,
            "detail": "",
            "timezone": "America/Santiago",
        }


def allowed_consent() -> ConsentManager:
    return ConsentManager(lambda request: True, enabled=False)


class FakeHttpResponse:
    """Respuesta mínima con ``status`` y cabeceras al estilo httplib2."""

    def __init__(
        self,
        status: int = 200,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.status = status
        self.headers = {str(k).lower(): v for k, v in (headers or {}).items()}

    def get(self, name: str) -> Any:
        return self.headers.get(str(name).lower())


class FakeHttpError(Exception):
    def __init__(
        self,
        status: int,
        *,
        headers: Mapping[str, str] | None = None,
        message: str = "",
    ) -> None:
        super().__init__(message or f"HTTP {status}")
        self.resp = FakeHttpResponse(status, headers=headers)


class FakeExecutable:
    def __init__(self, result: Any = None, error: BaseException | None = None) -> None:
        self.result = {} if result is None else result
        self.error = error
        self.calls = 0

    def execute(self, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeGmailClient:
    """Cliente de la API de Gmail simulado; solo lectura."""

    def __init__(
        self,
        list_payloads: list[dict[str, Any]] | None = None,
        metadata: dict[str, dict[str, Any]] | None = None,
        full: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.list_payloads = list(list_payloads or [{"messages": []}])
        self.metadata = dict(metadata or {})
        self.full = dict(full or {})
        self.list_calls: list[dict[str, Any]] = []
        self.metadata_calls: list[dict[str, Any]] = []
        self.full_calls: list[dict[str, Any]] = []

    def gmail_list_messages(
        self, *, max_results: int, page_token: str | None = None
    ) -> dict[str, Any]:
        self.list_calls.append(
            {"max_results": max_results, "page_token": page_token}
        )
        index = len(self.list_calls) - 1
        if index < len(self.list_payloads):
            return self.list_payloads[index]
        return {"messages": []}

    def gmail_get_message(
        self,
        message_id: str,
        *,
        format: str = "metadata",
        metadata_headers: tuple[str, ...] = (),
        fields: str = "",
    ) -> dict[str, Any]:
        record = {
            "id": message_id,
            "format": format,
            "metadata_headers": tuple(metadata_headers),
            "fields": fields,
        }
        if format == "full":
            self.full_calls.append(record)
            return self.full.get(message_id, {})
        self.metadata_calls.append(record)
        return self.metadata.get(message_id, {})


class FakeCalendarClient:
    """Cliente de la API de Calendar simulado; solo lectura."""

    def __init__(self, pages: list[dict[str, Any]] | None = None) -> None:
        self.pages = list(pages or [{"items": []}])
        self.calls: list[dict[str, Any]] = []

    def calendar_list_events(
        self,
        *,
        time_min: str,
        time_max: str,
        time_zone: str,
        max_results: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "time_min": time_min,
                "time_max": time_max,
                "time_zone": time_zone,
                "max_results": max_results,
                "page_token": page_token,
            }
        )
        index = len(self.calls) - 1
        if index < len(self.pages):
            return self.pages[index]
        return {"items": []}


def gmail_message(
    message_id: str,
    *,
    subject: str,
    name: str,
    address: str,
    internal_date: int,
    labels: tuple[str, ...] = ("INBOX",),
    snippet: str = "",
    parts: list[dict[str, Any]] | None = None,
    headers: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, Any]:
    raw_headers = headers or (
        ("From", f"{name} <{address}>"),
        ("Subject", subject),
        ("Date", "Tue, 17 Nov 2026 12:00:00 +0000"),
    )
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "labelIds": list(labels),
        "snippet": snippet or f"Vista previa de {subject}",
        "internalDate": str(internal_date),
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": key, "value": value} for key, value in raw_headers
            ],
            "parts": parts or [],
        },
    }


def calendar_event(
    event_id: str = "ev-1",
    *,
    summary: str = "Revisión semanal",
    start: Any = None,
    end: Any = None,
    location: str = "Sala 3",
    organizer: str = "Ana Pérez",
    attendees: tuple[str, ...] = (),
    status: str = "confirmed",
    transparency: str = "opaque",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "summary": summary,
        "status": status,
        "transparency": transparency,
        "location": location,
        "organizer": {"displayName": organizer, "email": "ana@example.com"},
        "attendees": [
            {"displayName": person, "email": ""} for person in attendees
        ],
        "start": start
        or {"dateTime": "2026-11-17T12:00:00Z", "timeZone": "UTC"},
        "end": end
        or {"dateTime": "2026-11-17T13:00:00Z", "timeZone": "UTC"},
    }


def utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> str:
    return (
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )
