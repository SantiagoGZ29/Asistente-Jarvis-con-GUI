"""Pruebas de OAuth 2.0 de Google, cache cifrada y errores, sin red."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import pytest

from jarvis.core.errors import (
    GoogleAccessBlockedError,
    GoogleApiError,
    GoogleAuthCancelledError,
    GoogleAuthExpiredError,
    GoogleConsentDeniedError,
    GoogleNetworkError,
    GoogleNotConfiguredError,
    GoogleNotConnectedError,
)
from jarvis.integrations import GOOGLE_SCOPES
from jarvis.integrations.google_auth import (
    EncryptedTokenStore,
    GoogleAuth,
    default_cache_path,
)


def write_client_secrets(tmp_path: Path, *, kind: str = "installed") -> Path:
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps(
            {
                kind: {
                    "client_id": "cliente-de-prueba.apps.googleusercontent.com",
                    "client_secret": "secreto-de-prueba",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def id_token(name: str = "Ana Pérez", email: str = "ana@example.com") -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"name": name, "email": email}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"cabecera.{payload}.firma"


class FakeCredentials:
    def __init__(
        self,
        *,
        valid: bool = True,
        refresh_token: str | None = "refresh-de-prueba",
        scopes: tuple[str, ...] = GOOGLE_SCOPES,
        id_token_value: str = "",
        refresh_error: BaseException | None = None,
    ) -> None:
        self.valid = valid
        self.refresh_token = refresh_token
        self.scopes = tuple(scopes)
        self.id_token = id_token_value
        self.refresh_error = refresh_error
        self.refreshed = 0
        self.requests: list[Any] = []

    def to_json(self) -> str:
        return json.dumps(
            {
                "token": "access-de-prueba",
                "refresh_token": self.refresh_token,
                "client_id": "cliente-de-prueba.apps.googleusercontent.com",
                "client_secret": "secreto-de-prueba",
                "scopes": list(self.scopes),
                "universe_domain": "googleapis.com",
            }
        )

    def refresh(self, request: Any) -> None:
        self.requests.append(request)
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refreshed += 1
        self.valid = True


class FakeFlow:
    def __init__(
        self,
        credentials: Any = None,
        *,
        error: BaseException | None = None,
    ) -> None:
        self.credentials = credentials
        self.error = error
        self.kwargs: dict[str, Any] = {}

    def run_local_server(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.credentials


def make_auth(
    tmp_path: Path,
    *,
    flow: FakeFlow | None = None,
    credentials: FakeCredentials | None = None,
    cache_name: str = "cache.bin",
) -> GoogleAuth:
    return GoogleAuth(
        write_client_secrets(tmp_path),
        cache_path=tmp_path / cache_name,
        flow_factory=(lambda path, scopes: flow) if flow is not None else None,
        credentials_factory=(
            (lambda info, scopes: credentials) if credentials is not None else None
        ),
        request_factory=lambda: "peticion-de-prueba",
    )


def test_sin_archivo_de_credenciales_no_se_puede_conectar(tmp_path: Path) -> None:
    auth = GoogleAuth(tmp_path / "no-existe.json", cache_path=tmp_path / "c.json")
    assert auth.configured is False
    assert "credentials.json" in auth.config_problem
    with pytest.raises(GoogleNotConfiguredError):
        auth.connect()


def test_archivo_inexistente_y_tipo_web(tmp_path: Path) -> None:
    missing = GoogleAuth(tmp_path / "falta.json")
    assert "No se encontró" in missing.config_problem

    web = write_client_secrets(tmp_path, kind="web")
    auth = GoogleAuth(web, cache_path=tmp_path / "c.bin")
    assert auth.configured is False
    assert "escritorio" in auth.config_problem

    broken = tmp_path / "roto.json"
    broken.write_text("{no es json", encoding="utf-8")
    auth = GoogleAuth(broken, cache_path=tmp_path / "c.bin")
    assert auth.configured is False
    assert "no se pudo leer" in auth.config_problem.lower()


def test_conexion_abre_navegador_sin_codigo_y_guarda_cache(tmp_path: Path) -> None:
    credentials = FakeCredentials(id_token_value=id_token())
    flow = FakeFlow(credentials)
    auth = make_auth(tmp_path, flow=flow)

    account = auth.connect()

    assert account == "Ana Pérez (ana@example.com)"
    assert auth.connected is True
    assert flow.kwargs["port"] == 0
    assert flow.kwargs["open_browser"] is True
    assert flow.kwargs["authorization_prompt_message"] == ""
    assert flow.kwargs["timeout_seconds"] == 300
    assert (tmp_path / "cache.bin").exists()


def test_sesion_guardada_se_reutiliza_sin_volver_a_abrir_navegador(
    tmp_path: Path,
) -> None:
    credentials = FakeCredentials(id_token_value=id_token())
    auth = make_auth(tmp_path, flow=FakeFlow(credentials))
    auth.connect()

    def fail_flow(path: Path, scopes: tuple[str, ...]) -> Any:
        raise AssertionError("No se debe abrir el navegador con cache válida")

    cached = FakeCredentials()
    restored = GoogleAuth(
        write_client_secrets(tmp_path),
        cache_path=tmp_path / "cache.bin",
        flow_factory=fail_flow,
        credentials_factory=lambda info, scopes: cached,
        request_factory=lambda: "peticion",
    )

    assert restored.connect() == "Ana Pérez (ana@example.com)"
    assert restored.connected is True
    assert restored.get_credentials() is cached


def test_cache_corrupta_se_ignora_y_se_pide_autorizacion(tmp_path: Path) -> None:
    auth = make_auth(tmp_path, flow=FakeFlow(FakeCredentials(id_token_value=id_token())))
    auth.connect()
    (tmp_path / "cache.bin").write_bytes(b"basura que no descifra")
    auth.mark_signed_out()
    auth._config_problem = ""  # el archivo de credenciales sigue siendo válido
    auth._credentials = None

    flow = FakeFlow(FakeCredentials(id_token_value=id_token()))
    auth._flow_factory = lambda path, scopes: flow
    assert auth.connect() == "Ana Pérez (ana@example.com)"
    assert auth.connected is True


def test_token_vencido_se_renueva_en_silencio(tmp_path: Path) -> None:
    cached = FakeCredentials()
    auth = make_auth(tmp_path, flow=FakeFlow(cached), credentials=cached)
    auth.connect()
    cached.valid = False

    result = auth.get_credentials()

    assert result is cached
    assert cached.refreshed == 1
    assert cached.requests == ["peticion-de-prueba"]


def test_sin_refresh_token_la_sesion_vencio(tmp_path: Path) -> None:
    cached = FakeCredentials(refresh_token=None)
    auth = make_auth(tmp_path, flow=FakeFlow(cached), credentials=cached)
    auth.connect()
    cached.valid = False

    with pytest.raises(GoogleAuthExpiredError):
        auth.get_credentials()
    assert auth.connected is False


def test_refresco_con_error_de_red_se_traduce(tmp_path: Path) -> None:
    cached = FakeCredentials(
        refresh_error=ConnectionResetError("connection reset")
    )
    auth = make_auth(tmp_path, flow=FakeFlow(cached), credentials=cached)
    auth.connect()
    cached.valid = False

    with pytest.raises(GoogleNetworkError):
        auth.get_credentials()
    assert auth.connected is False


def test_refresco_rechazado_se_traduce_a_sesion_vencida(tmp_path: Path) -> None:
    cached = FakeCredentials(
        refresh_error=RuntimeError("invalid_grant: token revoked")
    )
    auth = make_auth(tmp_path, flow=FakeFlow(cached), credentials=cached)
    auth.connect()
    cached.valid = False

    with pytest.raises(GoogleAuthExpiredError):
        auth.get_credentials()


def test_get_credentials_sin_conexion(tmp_path: Path) -> None:
    auth = make_auth(tmp_path, flow=FakeFlow(FakeCredentials()))
    with pytest.raises(GoogleNotConnectedError):
        auth.get_credentials()


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (RuntimeError("access_denied"), GoogleConsentDeniedError),
        (RuntimeError("org_internal"), GoogleAccessBlockedError),
        (RuntimeError("TimeoutError: timed out"), GoogleAuthCancelledError),
        (RuntimeError("invalid_grant: expired"), GoogleAuthExpiredError),
        (ConnectionResetError("connection reset"), GoogleNetworkError),
        (RuntimeError("algo raro"), GoogleApiError),
    ),
)
def test_errores_del_flujo_se_traducen(
    tmp_path: Path, error: BaseException, expected: type[BaseException]
) -> None:
    auth = make_auth(tmp_path, flow=FakeFlow(error=error))
    with pytest.raises(expected):
        auth.connect()


def test_cancelacion_solicitada_tras_autorizar(tmp_path: Path) -> None:
    import threading

    event = threading.Event()
    event.set()
    auth = make_auth(
        tmp_path,
        flow=FakeFlow(FakeCredentials(id_token_value=id_token())),
    )
    with pytest.raises(GoogleAuthCancelledError):
        auth.connect(cancel_event=event)


def test_disconnect_borra_la_cache(tmp_path: Path) -> None:
    auth = make_auth(
        tmp_path, flow=FakeFlow(FakeCredentials(id_token_value=id_token()))
    )
    auth.connect()
    cache = tmp_path / "cache.bin"
    assert cache.exists()

    auth.disconnect()

    assert not cache.exists()
    assert auth.connected is False
    assert auth.account == ""


@pytest.mark.skipif(os.name != "nt", reason="DPAPI solo existe en Windows")
def test_cache_dpapi_ida_y_vuelta(tmp_path: Path) -> None:
    store = EncryptedTokenStore(tmp_path / "token.bin")
    assert store.save("contenido secreto") is True
    assert store.encrypted is True
    raw = (tmp_path / "token.bin").read_bytes()
    assert b"contenido secreto" not in raw
    assert store.load() == "contenido secreto"
    assert store.load() != raw.decode("latin-1")

    store.clear()
    assert not (tmp_path / "token.bin").exists()
    assert store.load() is None


def test_ruta_de_cache_por_defecto_usa_perfil_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_cache_path() == tmp_path / "MiJarvis" / "google_token_cache.bin"
