"""Sesión de Google: une autenticación, API de solo lectura y servicios.

El controlador habla solo con esta clase. La sesión se crea al arrancar, pero
no contacta con Google ni lee el buzón hasta que el usuario pulsa
«CONECTAR GOOGLE» o pide una consulta.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from jarvis.config import Settings
from jarvis.core.errors import (
    GoogleNotConfiguredError,
    GoogleNotConnectedError,
)
from jarvis.core.logging_setup import get_logger
from jarvis.integrations import DEFAULT_GOOGLE_TIMEZONE
from jarvis.integrations.google_auth import GoogleAuth
from jarvis.integrations.google_calendar import GoogleCalendarService
from jarvis.integrations.google_client import ReadOnlyGoogleApi
from jarvis.integrations.google_mail import GmailService

logger = get_logger("google.session")


class GoogleSession:
    """Estado de conexión y fábricas de servicios de solo lectura."""

    def __init__(
        self,
        settings: Settings,
        *,
        auth_factory: Callable[..., Any] | None = None,
        client_factory: Callable[..., Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._auth_factory = auth_factory
        self._client_factory = client_factory
        self._sleep = sleep
        self._auth: Any | None = None
        self._client: Any | None = None
        self._account = ""
        self._problem = ""
        self._timezone = self._valid_timezone()
        self._prepare()

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    def _valid_timezone(self) -> str:
        name = (self.settings.google_timezone or DEFAULT_GOOGLE_TIMEZONE).strip()
        try:
            ZoneInfo(name)
            return name
        except Exception:
            logger.warning("GOOGLE_TIMEZONE no es válido; se usará America/Santiago")
            return DEFAULT_GOOGLE_TIMEZONE

    def _prepare(self) -> None:
        client_file = (self.settings.google_oauth_client_file or "").strip()
        if not client_file:
            self._problem = (
                "Falta GOOGLE_OAUTH_CLIENT_FILE. Descarga credentials.json de "
                "tu aplicación de escritorio de Google Cloud y escríbelo en el "
                "archivo .env."
            )
            return
        path = self.settings.google_client_path
        try:
            if self._auth_factory is not None:
                self._auth = self._auth_factory(path)
            else:
                self._auth = GoogleAuth(path)
        except Exception as exc:  # pragma: no cover - configuración defensiva
            logger.warning(
                "No se pudo preparar la autenticación de Google: %s",
                type(exc).__name__,
            )
            self._problem = (
                "No se pudo preparar la autenticación de Google. Revisa el "
                "archivo credentials.json y GOOGLE_OAUTH_CLIENT_FILE."
            )
            return
        if not getattr(self._auth, "configured", True):
            self._problem = str(
                getattr(self._auth, "config_problem", "")
                or "La configuración de Google Cloud no es válida."
            )

    @property
    def configured(self) -> bool:
        return not self._problem and self._auth is not None

    @property
    def problem(self) -> str:
        return self._problem

    @property
    def connected(self) -> bool:
        return bool(
            self.configured
            and self._auth is not None
            and getattr(self._auth, "connected", False)
            and self._client is not None
        )

    @property
    def account(self) -> str:
        return self._account

    @property
    def timezone_name(self) -> str:
        return self._timezone

    @property
    def cache_location(self) -> str:
        if self._auth is None:
            return "no disponible"
        return str(getattr(self._auth, "cache_location", "memoria"))

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------
    def connect(
        self,
        *,
        cancel_event: threading.Event | None = None,
    ) -> str:
        if not self.configured or self._auth is None:
            raise GoogleNotConfiguredError(
                self._problem or "La configuración de Google Cloud no es válida."
            )
        account = self._auth.connect(cancel_event=cancel_event)
        client = self._build_client()
        # Verifica ambos permisos sin descargar contenido.
        profile = client.gmail_profile()
        email = str(profile.get("emailAddress") or "").strip() if profile else ""
        if email:
            setter = getattr(self._auth, "set_account", None)
            if callable(setter):
                setter(email)
            account = email
        zone = ZoneInfo(self._timezone)
        now = datetime.now(zone)
        client.calendar_list_events(
            time_min=now.isoformat(timespec="seconds"),
            time_max=(now + timedelta(days=1)).isoformat(timespec="seconds"),
            time_zone=self._timezone,
            max_results=1,
        )
        self._client = client
        self._account = account
        logger.info("Google verificado: Gmail y Calendar accesibles")
        return account

    def _build_client(self) -> Any:
        assert self._auth is not None
        credentials = self._auth.get_credentials()
        if self._client_factory is not None:
            return self._client_factory(credentials)
        return ReadOnlyGoogleApi(
            credentials,
            sleep=self._sleep,
        )

    def disconnect(self) -> None:
        if self._auth is not None:
            try:
                self._auth.disconnect()
            except Exception:  # pragma: no cover - cierre defensivo
                logger.warning("No se pudo cerrar la sesión de Google")
        self._client = None
        self._account = ""

    def mark_expired(self) -> None:
        """La sesión dejó de ser válida; se pedirá autorización de nuevo."""
        self._client = None
        self._account = ""
        if self._auth is not None:
            try:
                self._auth.mark_signed_out()
            except Exception:  # pragma: no cover
                pass

    def cancel(self) -> None:
        if self._auth is not None:
            try:
                self._auth.cancel()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------------
    # Servicios
    # ------------------------------------------------------------------
    def mail_service(self) -> GmailService:
        client = self._require_client()
        return GmailService(
            client,
            timezone_name=self._timezone,
            limit=20,
            max_body_chars=max(2_000, int(self.settings.max_context_chars)),
        )

    def calendar_service(self) -> GoogleCalendarService:
        client = self._require_client()
        return GoogleCalendarService(
            client,
            timezone_name=self._timezone,
        )

    def _require_client(self) -> Any:
        if not self.connected or self._client is None:
            raise GoogleNotConnectedError()
        return self._client

    # ------------------------------------------------------------------
    # Estado para la interfaz
    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        detail = ""
        if self._problem:
            detail = self._problem
        elif self.connected:
            detail = f"Sesión guardada en {self.cache_location}"
        return {
            "configured": self.configured,
            "connected": self.connected,
            "account": self._account,
            "problem": self._problem,
            "detail": detail,
            "timezone": self._timezone,
        }


__all__ = ["GoogleSession"]
