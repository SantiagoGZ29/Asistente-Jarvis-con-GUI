"""Cliente de solo lectura para Gmail y Google Calendar.

Solo existen tres operaciones de Gmail (perfil, lista y detalle) y una de
Calendar (lista de eventos). No hay forma pública de enviar, modificar,
etiquetar, archivar ni borrar nada: las clases de servicio de Google quedan
encerradas y Jamás se exponen sus métodos de escritura.

Los errores 429 respetan ``Retry-After`` y los reintentos son acotados.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Mapping, Protocol

from jarvis.core.errors import (
    GoogleApiError,
    GoogleAuthExpiredError,
    GoogleError,
    GoogleForbiddenError,
    GoogleNetworkError,
    GoogleRateLimitError,
)
from jarvis.core.logging_setup import get_logger

logger = get_logger("google.api")

_MAX_RETRY_AFTER = 30.0
_NETWORK_HINTS = (
    "connection",
    "connect",
    "network",
    "timeout",
    "timed out",
    "ssl",
    "socket",
    "proxy",
    "temporarily",
    "unavailable",
    "remotedisconnected",
)


class Executable(Protocol):
    def execute(self, **kwargs: Any) -> Any:  # pragma: no cover - interfaz
        ...


def _http_status(exc: BaseException) -> int | None:
    for candidate in (
        getattr(getattr(exc, "resp", None), "status", None),
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
    ):
        if candidate is None:
            continue
        try:
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def _retry_after(exc: BaseException, default: float = 2.0) -> float:
    resp = getattr(exc, "resp", None)
    raw = ""
    try:
        if resp is not None and hasattr(resp, "get"):
            raw = str(resp.get("retry-after") or "")
        elif resp is not None:
            raw = str(getattr(resp, "headers", {}).get("retry-after") or "")
    except Exception:
        return default
    if not raw:
        return default
    try:
        seconds = float(raw)
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return default
    return max(0.0, min(_MAX_RETRY_AFTER, seconds))


class ReadOnlyGoogleApi:
    """Acceso GET a Gmail y Google Calendar con servicios oficiales."""

    def __init__(
        self,
        credentials: Any,
        *,
        gmail_factory: Callable[[Any], Any] | None = None,
        calendar_factory: Callable[[Any], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 2,
    ) -> None:
        self._gmail = (
            gmail_factory(credentials) if gmail_factory else self._build("gmail", "v1", credentials)
        )
        self._calendar = (
            calendar_factory(credentials)
            if calendar_factory
            else self._build("calendar", "v3", credentials)
        )
        self._sleep = sleep
        self._max_retries = max(0, int(max_retries))
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _build(name: str, version: str, credentials: Any) -> Any:
        from googleapiclient.discovery import build

        # static_discovery evita descargar y cachear el documento de descubrimiento.
        return build(
            name,
            version,
            credentials=credentials,
            cache_discovery=False,
            static_discovery=True,
        )

    # ------------------------------------------------------------------
    # Gmail
    # ------------------------------------------------------------------
    def gmail_profile(self) -> dict[str, Any]:
        request = self._gmail.users().getProfile(userId="me")
        return self._execute(request, "GET gmail.users.getProfile")

    def gmail_list_messages(
        self, *, max_results: int, page_token: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "userId": "me",
            "labelIds": ["INBOX"],
            "maxResults": max(1, min(100, int(max_results))),
            "fields": "messages(id,threadId),nextPageToken",
        }
        if page_token:
            params["pageToken"] = page_token
        request = self._gmail.users().messages().list(**params)
        return self._execute(request, "GET gmail.users.messages.list")

    def gmail_get_message(
        self,
        message_id: str,
        *,
        format: str = "metadata",
        metadata_headers: tuple[str, ...] = ("From", "Subject", "Date"),
        fields: str = "",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "userId": "me",
            "id": message_id,
            "format": format,
        }
        if metadata_headers:
            params["metadataHeaders"] = list(metadata_headers)
        if fields:
            params["fields"] = fields
        request = self._gmail.users().messages().get(**params)
        return self._execute(request, "GET gmail.users.messages.get")

    # ------------------------------------------------------------------
    # Google Calendar
    # ------------------------------------------------------------------
    def calendar_list_events(
        self,
        *,
        time_min: str,
        time_max: str,
        time_zone: str,
        max_results: int,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "calendarId": "primary",
            "timeMin": time_min,
            "timeMax": time_max,
            "timeZone": time_zone,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": max(1, min(2500, int(max_results))),
            "fields": (
                "items(id,summary,start,end,location,organizer,attendees,"
                "status,transparency),nextPageToken"
            ),
        }
        if page_token:
            params["pageToken"] = page_token
        request = self._calendar.events().list(**params)
        return self._execute(request, "GET calendar.events.list")

    # ------------------------------------------------------------------
    # Ejecución y errores
    # ------------------------------------------------------------------
    def _execute(self, request: Executable, operation: str) -> dict[str, Any]:
        last_network: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self.calls.append(("GET", operation))
            try:
                payload = request.execute(num_retries=0)
            except Exception as exc:
                status = _http_status(exc)
                if status == 401:
                    raise GoogleAuthExpiredError() from exc
                if status == 403:
                    raise GoogleForbiddenError() from exc
                if status == 429:
                    wait = _retry_after(exc)
                    if attempt < self._max_retries:
                        logger.info("Google 429: reintento en %.1f s", wait)
                        self._sleep(wait)
                        continue
                    raise GoogleRateLimitError() from exc
                if status is not None and status >= 500:
                    if attempt < self._max_retries:
                        self._sleep(min(2.0 ** attempt, 4.0))
                        continue
                    raise GoogleApiError(
                        "Google informó de un problema interno. Inténtalo de "
                        "nuevo en unos minutos."
                    ) from exc
                if status == 404:
                    raise GoogleApiError(
                        "El recurso solicitado ya no existe en Google. Vuelve a "
                        "consultar la lista."
                    ) from exc
                if status is not None and status >= 400:
                    raise GoogleApiError(
                        "Google rechazó la consulta (código "
                        f"{status}). Comprueba los permisos de solo lectura."
                    ) from exc
                if _looks_like_network(exc):
                    last_network = exc
                    if attempt < self._max_retries:
                        self._sleep(min(2.0 ** attempt, 4.0))
                        continue
                    logger.warning(
                        "Fallo de red con Google (%s)", type(exc).__name__
                    )
                    raise GoogleNetworkError() from exc
                raise GoogleApiError(
                    "Google devolvió una respuesta que Jarvis no pudo procesar."
                ) from exc

            if not isinstance(payload, Mapping):
                raise GoogleApiError(
                    "Google devolvió una respuesta con un formato inesperado."
                )
            return dict(payload)

        raise GoogleNetworkError() from last_network


def _looks_like_network(exc: BaseException) -> bool:
    module = type(exc).__module__ or ""
    text = f"{type(exc).__name__} {exc}".lower()
    return module.startswith(
        ("httplib2", "requests", "urllib3", "google.auth.transport", "socket")
    ) or any(hint in text for hint in _NETWORK_HINTS)


__all__ = ["ReadOnlyGoogleApi"]
