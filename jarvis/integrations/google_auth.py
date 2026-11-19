"""Autenticación OAuth 2.0 de Google para Gmail y Google Calendar.

Se usa una aplicación de escritorio (cliente público) con el flujo oficial de
``google-auth-oauthlib``: se abre el navegador predeterminado, el usuario
autoriza y Google redirige a un servidor local efímero. El flujo incluye PKCE.

Los tokens se guardan cifrados con DPAPI de Windows en el perfil del usuario.
Si DPAPI no está disponible, la sesión vive solo en memoria: nunca se escriben
tokens en texto plano. Este módulo no importa Qt.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from jarvis.core.errors import (
    GoogleAccessBlockedError,
    GoogleApiError,
    GoogleAuthCancelledError,
    GoogleAuthExpiredError,
    GoogleConsentDeniedError,
    GoogleError,
    GoogleNetworkError,
    GoogleNotConfiguredError,
    GoogleNotConnectedError,
)
from jarvis.core.logging_setup import get_logger
from jarvis.integrations import (
    DEFAULT_GOOGLE_OAUTH_CLIENT_FILE,
    GOOGLE_SCOPES,
)

logger = get_logger("google.auth")

_CACHE_VERSION = 1
_ENTROPY = b"MiJarvis-Google-OAuth-v1"
_MAX_PROMPT_SECONDS = 300
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
)


def default_cache_path() -> Path:
    """Ruta del token cache cifrado dentro del perfil del usuario."""
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".mijarvis"
    return root / "MiJarvis" / "google_token_cache.bin"


# ----------------------------------------------------------------------
# DPAPI (Windows)
# ----------------------------------------------------------------------
class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.c_uint32),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(data, len(data))
    value = _DataBlob(
        len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
    )
    return value, buffer


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    """Cifra o descifra datos con DPAPI, ligados al usuario de Windows."""
    if os.name != "nt":
        raise OSError("DPAPI no está disponible fuera de Windows")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    blob_in, buffer_in = _blob(data)
    entropy, buffer_entropy = _blob(_ENTROPY)
    blob_out = _DataBlob()
    function = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    description = ctypes.c_wchar_p("MiJarvis Google OAuth") if protect else None
    if protect:
        ok = function(
            ctypes.byref(blob_in),
            description,
            ctypes.byref(entropy),
            None,
            None,
            0x1,  # CRYPTPROTECT_UI_FORBIDDEN
            ctypes.byref(blob_out),
        )
    else:
        ok = function(
            ctypes.byref(blob_in),
            None,
            ctypes.byref(entropy),
            None,
            None,
            0x1,
            ctypes.byref(blob_out),
        )
    # Las referencias a los buffers deben seguir vivas hasta aquí.
    _ = (buffer_in, buffer_entropy)
    if not ok:
        raise OSError("DPAPI no pudo procesar los datos")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(blob_out.pbData, ctypes.c_void_p))


class EncryptedTokenStore:
    """Guarda el token de Google cifrado; si no puede, no persiste nada."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.encrypted = False
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        return os.name == "nt"

    def load(self) -> str | None:
        if not self.available or not self.path.exists():
            return None
        try:
            raw = self.path.read_bytes()
            text = _dpapi(raw, protect=False).decode("utf-8")
            self.encrypted = True
            return text
        except Exception as exc:  # archivo corrupto o DPAPI no disponible
            logger.info(
                "No se pudo leer el token de Google (%s)", type(exc).__name__
            )
            return None

    def save(self, text: str) -> bool:
        if not self.available:
            self.encrypted = False
            return False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            raw = _dpapi(text.encode("utf-8"), protect=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_bytes(raw)
            temporary.replace(self.path)
            self.encrypted = True
            return True
        except Exception as exc:  # cifrado no disponible o sin permisos
            logger.info(
                "El token de Google quedará solo en memoria (%s)",
                type(exc).__name__,
            )
            self.encrypted = False
            return False

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:  # pragma: no cover - permisos del perfil
            logger.warning(
                "No se pudo borrar el token de Google (%s)", type(exc).__name__
            )
        self.encrypted = False


# ----------------------------------------------------------------------
# Cuenta
# ----------------------------------------------------------------------
def _decode_id_token(token: str) -> tuple[str, str]:
    """Lee nombre y correo del id_token sin usarlo para autorizar."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(
            base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        )
    except Exception:
        return "", ""
    if not isinstance(data, Mapping):
        return "", ""
    name = " ".join(str(data.get("name") or "").split())
    email = " ".join(
        str(data.get("email") or data.get("preferred_username") or "").split()
    )
    return name, email


def _display_account(name: str, email: str) -> str:
    name = " ".join((name or "").split())
    email = " ".join((email or "").split())
    if name and email and name.lower() != email.lower():
        return f"{name} ({email})"
    return name or email or "Cuenta de Google"


class GoogleAuth:
    """Sesión OAuth de una cuenta personal de Google, con cache seguro."""

    def __init__(
        self,
        client_file: Path | str = DEFAULT_GOOGLE_OAUTH_CLIENT_FILE,
        *,
        cache_path: Path | str | None = None,
        scopes: tuple[str, ...] = GOOGLE_SCOPES,
        flow_factory: Callable[[Path, tuple[str, ...]], Any] | None = None,
        credentials_factory: Callable[[Mapping[str, Any], tuple[str, ...]], Any] | None = None,
        request_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.client_file = Path(client_file)
        self.cache_path = Path(cache_path) if cache_path else default_cache_path()
        self.scopes = tuple(scopes)
        self._flow_factory = flow_factory
        self._credentials_factory = credentials_factory
        self._request_factory = request_factory
        self._store = EncryptedTokenStore(self.cache_path)
        self._credentials: Any | None = None
        self._account = ""
        self._lock = threading.RLock()
        self._config_problem = self._validate_config()

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def _validate_config(self) -> str:
        if not str(self.client_file):
            return (
                "Falta GOOGLE_OAUTH_CLIENT_FILE. Descarga el archivo "
                "credentials.json de tu aplicación de Google Cloud y escribe "
                "su ruta en el archivo .env."
            )
        if not self.client_file.exists():
            return (
                f"No se encontró el archivo de credenciales de Google "
                f"({self.client_file}). Descarga credentials.json desde Google "
                "Cloud y colócalo en la ruta indicada por "
                "GOOGLE_OAUTH_CLIENT_FILE."
            )
        try:
            data = json.loads(self.client_file.read_text(encoding="utf-8"))
        except Exception:
            return (
                "El archivo de credenciales de Google no se pudo leer. "
                "Vuelve a descargarlo desde Google Cloud como JSON."
            )
        installed = data.get("installed") if isinstance(data, Mapping) else None
        if not isinstance(installed, Mapping):
            return (
                "El archivo de credenciales no corresponde a una aplicación de "
                "escritorio. En Google Cloud crea un cliente OAuth de tipo "
                "«Aplicación de escritorio» y descarga su JSON."
            )
        if not installed.get("client_id") or not installed.get("client_secret"):
            return (
                "El archivo credentials.json está incompleto: faltan client_id "
                "o client_secret de la aplicación de escritorio."
            )
        return ""

    @property
    def configured(self) -> bool:
        return not self._config_problem

    @property
    def config_problem(self) -> str:
        return self._config_problem

    @property
    def connected(self) -> bool:
        return self._credentials is not None

    @property
    def account(self) -> str:
        return self._account

    @property
    def cache_is_encrypted(self) -> bool:
        return self._store.encrypted

    @property
    def cache_location(self) -> str:
        return str(self.cache_path) if self._store.encrypted else "memoria"

    # ------------------------------------------------------------------
    # Flujo OAuth
    # ------------------------------------------------------------------
    def _build_flow(self) -> Any:
        if self._flow_factory is not None:
            return self._flow_factory(self.client_file, self.scopes)
        from google_auth_oauthlib.flow import InstalledAppFlow

        return InstalledAppFlow.from_client_secrets_file(
            str(self.client_file), scopes=list(self.scopes)
        )

    def _build_credentials(self, info: Mapping[str, Any]) -> Any:
        if self._credentials_factory is not None:
            return self._credentials_factory(info, self.scopes)
        from google.oauth2.credentials import Credentials

        return Credentials.from_authorized_user_info(dict(info), list(self.scopes))

    def _refresh_request(self) -> Any:
        if self._request_factory is not None:
            return self._request_factory()
        from google.auth.transport.requests import Request

        return Request()

    def _restore(self) -> Any | None:
        text = self._store.load()
        if not text:
            return None
        try:
            wrapper = json.loads(text)
            if not isinstance(wrapper, Mapping):
                return None
            info = wrapper.get("credentials")
            if not isinstance(info, Mapping):
                info = wrapper
            account = str(wrapper.get("account") or "")
            credentials = self._build_credentials(info)
            granted = set(getattr(credentials, "scopes", None) or info.get("scopes") or ())
            if not set(self.scopes).issubset(granted):
                return None
            if not getattr(credentials, "valid", False):
                credentials.refresh(self._refresh_request())
            if not getattr(credentials, "valid", False):
                return None
        except Exception as exc:
            logger.info(
                "La sesión guardada de Google no se pudo reutilizar (%s)",
                type(exc).__name__,
            )
            return None
        self._account = _display_account(
            "", account or str(info.get("account") or "")
        )
        return credentials

    def _save(self, credentials: Any) -> None:
        try:
            info = json.loads(credentials.to_json())
            wrapper = {
                "version": _CACHE_VERSION,
                "account": self._account,
                "credentials": info,
            }
            self._store.save(json.dumps(wrapper, ensure_ascii=False))
        except Exception as exc:  # el flujo sigue en memoria
            logger.info(
                "No se pudo guardar la sesión de Google (%s)",
                type(exc).__name__,
            )

    def connect(self, *, cancel_event: threading.Event | None = None) -> str:
        """Autoriza la cuenta y devuelve su nombre visible.

        Primero intenta reutilizar la sesión cifrada. Si no hay tokens válidos,
        abre el navegador predeterminado con el flujo OAuth de escritorio.
        """
        if not self.configured:
            raise GoogleNotConfiguredError(self._config_problem)

        with self._lock:
            cached = self._restore()
        if cached is not None:
            with self._lock:
                self._credentials = cached
            logger.info("Google reutilizó una sesión autorizada")
            return self._account or "Cuenta de Google"

        flow = self._build_flow()
        try:
            credentials = flow.run_local_server(
                port=0,
                open_browser=True,
                authorization_prompt_message="",
                success_message=(
                    "Autorización completada. Puedes cerrar esta pestaña y "
                    "volver a Jarvis."
                ),
                timeout_seconds=_MAX_PROMPT_SECONDS,
            )
        except Exception as exc:
            raise self._error_from_exception(exc) from exc

        if cancel_event is not None and cancel_event.is_set():
            raise GoogleAuthCancelledError()
        if credentials is None:
            raise GoogleApiError(
                "Google no devolvió credenciales. Vuelve a intentar la conexión."
            )

        name, email = _decode_id_token(str(getattr(credentials, "id_token", "") or ""))
        account = _display_account(name, email)
        with self._lock:
            self._credentials = credentials
            self._account = account
        self._save(credentials)
        logger.info("Google conectado con una cuenta autorizada")
        return account

    # ------------------------------------------------------------------
    # Tokens
    # ------------------------------------------------------------------
    def get_credentials(self) -> Any:
        """Devuelve credenciales válidas, renovándolas en silencio."""
        with self._lock:
            credentials = self._credentials
        if credentials is None:
            raise GoogleNotConnectedError()
        if getattr(credentials, "valid", False):
            return credentials
        if not getattr(credentials, "refresh_token", None):
            with self._lock:
                self._credentials = None
            raise GoogleAuthExpiredError()
        try:
            credentials.refresh(self._refresh_request())
        except Exception as exc:
            with self._lock:
                self._credentials = None
            error = self._error_from_exception(exc)
            if isinstance(error, GoogleNetworkError):
                raise error from exc
            raise GoogleAuthExpiredError() from exc
        if not getattr(credentials, "valid", False):
            with self._lock:
                self._credentials = None
            raise GoogleAuthExpiredError()
        self._save(credentials)
        return credentials

    def set_account(self, account: str) -> None:
        """Completa el correo visible cuando lo confirma la API de Gmail."""
        clean = " ".join((account or "").split())
        if not clean:
            return
        with self._lock:
            self._account = _display_account("", clean)
            if self._credentials is not None:
                self._save(self._credentials)

    def cancel(self) -> None:
        """El flujo local no se puede interrumpir de forma segura; se ignora."""
        return None

    def mark_signed_out(self) -> None:
        """Olvida la cuenta en memoria; la cache se conserva para reintentar."""
        with self._lock:
            self._credentials = None

    def disconnect(self) -> None:
        """Elimina la cache de Jarvis. No cierra la sesión del navegador."""
        with self._lock:
            self._credentials = None
            self._account = ""
        self._store.clear()
        logger.info("Token de Google eliminado a petición del usuario")

    # ------------------------------------------------------------------
    # Errores OAuth
    # ------------------------------------------------------------------
    @staticmethod
    def _error_from_exception(exc: BaseException) -> GoogleError:
        if isinstance(exc, GoogleError):
            return exc
        text = f"{type(exc).__name__} {exc}".lower()

        if "access_denied" in text or "user denied" in text or "consent" in text:
            return GoogleConsentDeniedError()
        if (
            "org_internal" in text
            or "admin" in text
            or "not verified" in text
            or "access blocked" in text
            or "disallowed_useragent" in text
        ):
            return GoogleAccessBlockedError()
        if "timeout" in text or "timed out" in text or "wsgi" in text:
            return GoogleAuthCancelledError(
                "La autorización de Google no se completó a tiempo. Vuelve a "
                "pulsar «CONECTAR GOOGLE» para abrir el navegador de nuevo."
            )
        if (
            "invalid_grant" in text
            or "expired" in text
            or "revoked" in text
            or "invalid_client" in text
        ):
            return GoogleAuthExpiredError()
        if any(hint in text for hint in _NETWORK_HINTS):
            return GoogleNetworkError()
        return GoogleApiError(
            "Google no completó la autorización. Comprueba la configuración de "
            "la aplicación y vuelve a intentarlo."
        )


__all__ = [
    "EncryptedTokenStore",
    "GoogleAuth",
    "default_cache_path",
]
