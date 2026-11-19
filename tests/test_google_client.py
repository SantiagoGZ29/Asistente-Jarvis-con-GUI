"""Pruebas del cliente de solo lectura de Gmail y Calendar, sin red."""

from __future__ import annotations

from typing import Any

import pytest

from google_helpers import FakeHttpError

from jarvis.core.errors import (
    GoogleApiError,
    GoogleAuthExpiredError,
    GoogleForbiddenError,
    GoogleNetworkError,
    GoogleRateLimitError,
)
from jarvis.integrations.google_client import ReadOnlyGoogleApi


class Script:
    """Entrega resultados preparados a cada ejecución simulada."""

    def __init__(self, outcomes: list[Any] | None = None) -> None:
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, Any]] = []

    def request(self, **params: Any) -> "Executable":
        self.calls.append(dict(params))
        return Executable(self)

    def next_outcome(self) -> Any:
        return self.outcomes.pop(0) if self.outcomes else {}

    # Las fachadas de Gmail y Calendar usan estos nombres reales.
    def list(self, **params: Any) -> "Executable":
        return self.request(**params)

    def get(self, **params: Any) -> "Executable":
        return self.request(**params)


class Executable:
    def __init__(self, script: Script) -> None:
        self.script = script

    def execute(self, **_kwargs: Any) -> Any:
        outcome = self.script.next_outcome()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class GmailFacade:
    def __init__(self, profile: Any = None, messages: Script | None = None) -> None:
        self.profile = profile if profile is not None else {"emailAddress": "ana@example.com"}
        self._messages = messages or Script()
        self._profile_calls: list[dict[str, Any]] = []

    def users(self) -> "GmailFacade":
        return self

    def getProfile(self, **params: Any) -> Executable:
        self._profile_calls.append(dict(params))
        if isinstance(self.profile, Script):
            return self.profile.request(**params)
        return Executable(Script([self.profile]))

    def messages(self) -> Script:
        return self._messages


def gmail_facade(
    *, profile: Any = None, messages: Script | None = None
) -> Any:
    return GmailFacade(profile=profile, messages=messages)


class CalendarFacade:
    def __init__(self, events: Script | None = None) -> None:
        self._events = events or Script()

    def events(self) -> Script:
        return self._events


def make_api(
    *,
    gmail: Any | None = None,
    calendar: Any | None = None,
    sleeps: list[float] | None = None,
    retries: int = 2,
) -> ReadOnlyGoogleApi:
    return ReadOnlyGoogleApi(
        object(),
        gmail_factory=lambda credentials: gmail or gmail_facade(),
        calendar_factory=lambda credentials: calendar or CalendarFacade(),
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
        max_retries=retries,
    )


def test_lista_de_gmail_pide_solo_la_bandeja_y_campos_minimos() -> None:
    messages = Script(
        [
            {
                "messages": [{"id": "m-1", "threadId": "t-1"}],
                "nextPageToken": "pagina-2",
            }
        ]
    )
    api = make_api(gmail=gmail_facade(messages=messages))

    payload = api.gmail_list_messages(max_results=500, page_token="inicio")

    assert payload["nextPageToken"] == "pagina-2"
    call = messages.calls[0]
    assert call["userId"] == "me"
    assert call["labelIds"] == ["INBOX"]
    assert call["maxResults"] == 100
    assert call["pageToken"] == "inicio"
    assert call["fields"] == "messages(id,threadId),nextPageToken"


def test_detalle_de_gmail_usa_metadata_por_defecto() -> None:
    messages = Script([{"id": "m-1", "payload": {}}])
    api = make_api(gmail=gmail_facade(messages=messages))

    api.gmail_get_message("m-1")

    call = messages.calls[0]
    assert call["userId"] == "me"
    assert call["id"] == "m-1"
    assert call["format"] == "metadata"
    assert call["metadataHeaders"] == ["From", "Subject", "Date"]
    assert "fields" not in call


def test_detalle_de_gmail_con_cuerpo_completo_y_campos() -> None:
    messages = Script([{"id": "m-1"}])
    api = make_api(gmail=gmail_facade(messages=messages))

    api.gmail_get_message(
        "m-1",
        format="full",
        metadata_headers=("From", "To"),
        fields="id,payload",
    )

    call = messages.calls[0]
    assert call["format"] == "full"
    assert call["metadataHeaders"] == ["From", "To"]
    assert call["fields"] == "id,payload"


def test_perfil_de_gmail() -> None:
    gmail = gmail_facade(profile={"emailAddress": "ana@example.com"})
    api = make_api(gmail=gmail)

    assert api.gmail_profile()["emailAddress"] == "ana@example.com"
    assert gmail._profile_calls == [{"userId": "me"}]


def test_calendario_usa_primary_y_single_events() -> None:
    events = Script(
        [{"items": [{"id": "ev-1"}], "nextPageToken": "siguiente"}]
    )
    api = make_api(calendar=CalendarFacade(events))

    payload = api.calendar_list_events(
        time_min="2026-11-17T00:00:00-03:00",
        time_max="2026-11-18T00:00:00-03:00",
        time_zone="America/Santiago",
        max_results=9_000,
        page_token="token-1",
    )

    assert payload["nextPageToken"] == "siguiente"
    call = events.calls[0]
    assert call["calendarId"] == "primary"
    assert call["singleEvents"] is True
    assert call["orderBy"] == "startTime"
    assert call["timeZone"] == "America/Santiago"
    assert call["maxResults"] == 2500
    assert call["pageToken"] == "token-1"
    assert "items(id,summary,start,end" in call["fields"]


def test_reintenta_429_respetando_retry_after() -> None:
    messages = Script(
        [
            FakeHttpError(429, headers={"Retry-After": "7"}),
            {"messages": [{"id": "m-1"}]},
        ]
    )
    sleeps: list[float] = []
    api = make_api(gmail=gmail_facade(messages=messages), sleeps=sleeps)

    result = api.gmail_list_messages(max_results=1)

    assert result["messages"] == [{"id": "m-1"}]
    assert sleeps == [7.0]
    # Una sola solicitud; el reintento reutiliza la misma petición HTTP.
    assert len(messages.calls) == 1
    assert len(api.calls) == 2


def test_429_agotado_devuelve_error_claro() -> None:
    messages = Script([FakeHttpError(429)])
    api = make_api(gmail=gmail_facade(messages=messages), retries=0)

    with pytest.raises(GoogleRateLimitError):
        api.gmail_list_messages(max_results=1)


@pytest.mark.parametrize(
    ("status", "expected"),
    (
        (401, GoogleAuthExpiredError),
        (403, GoogleForbiddenError),
        (404, GoogleApiError),
    ),
)
def test_errores_http_con_mensaje(status: int, expected: type[BaseException]) -> None:
    messages = Script([FakeHttpError(status)])
    api = make_api(gmail=gmail_facade(messages=messages), retries=0)

    with pytest.raises(expected):
        api.gmail_list_messages(max_results=1)


def test_error_500_se_reintenta_y_luego_falla() -> None:
    messages = Script([FakeHttpError(503), FakeHttpError(503)])
    sleeps: list[float] = []
    api = make_api(
        gmail=gmail_facade(messages=messages), sleeps=sleeps, retries=1
    )

    with pytest.raises(GoogleApiError):
        api.gmail_list_messages(max_results=1)
    assert len(messages.calls) == 1
    assert len(api.calls) == 2
    assert sleeps


def test_error_de_red_se_traduce() -> None:
    messages = Script([ConnectionResetError("connection reset by peer")])
    api = make_api(gmail=gmail_facade(messages=messages), retries=0)

    with pytest.raises(GoogleNetworkError):
        api.gmail_list_messages(max_results=1)


def test_respuesta_con_formato_inesperado() -> None:
    messages = Script([["esto", "no", "es", "un", "mapa"]])
    api = make_api(gmail=gmail_facade(messages=messages), retries=0)

    with pytest.raises(GoogleApiError):
        api.gmail_list_messages(max_results=1)


def test_no_hay_metodos_de_escritura_ni_llamadas_no_get() -> None:
    api = make_api()
    for name in ("send", "modify", "delete", "insert", "patch", "update"):
        assert not hasattr(api, name)
    api.gmail_profile()
    api.gmail_list_messages(max_results=1)
    assert api.calls
    assert {method for method, _operation in api.calls} == {"GET"}
