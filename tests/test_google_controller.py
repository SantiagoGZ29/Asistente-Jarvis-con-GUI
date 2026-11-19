"""Pruebas del controlador con Gmail y Google Calendar simulados."""

from __future__ import annotations

from pathlib import Path

import pytest

from google_helpers import (
    FakeCalendarService,
    FakeGoogleSession,
    FakeMailService,
    at,
    event,
    message,
)
from test_controller import Harness, voice_settings

from jarvis.core.controller import GoogleInfo
from jarvis.core.errors import (
    GoogleAuthCancelledError,
    GoogleAuthExpiredError,
    GoogleConsentDeniedError,
    GoogleRateLimitError,
)


@pytest.fixture
def google_harness(tmp_path: Path):
    created: list[Harness] = []

    def build(session: FakeGoogleSession) -> Harness:
        item = Harness(voice_settings(), tmp_path, google=session)
        created.append(item)
        item.start()
        return item

    yield build
    for item in created:
        item.stop()


def last_text(item: Harness) -> str:
    return item.rec.jarvis_texts[-1] if item.rec.jarvis_texts else ""


def last_error(item: Harness) -> str:
    return item.rec.errors[-1] if item.rec.errors else ""


# ======================================================================
# Arranque y estado
# ======================================================================
def test_arranque_no_contacta_google(google_harness) -> None:
    session = FakeGoogleSession(connected=False)
    item = google_harness(session)

    assert session.connects == 0
    assert session.mail.list_calls == 0
    assert session.calendar.windows == []

    info = item.controller.google_info()
    assert isinstance(info, GoogleInfo)
    assert info.configured is True
    assert info.connected is False


def test_estado_sin_configurar(google_harness) -> None:
    session = FakeGoogleSession(
        configured=False,
        connected=False,
        problem="Falta el archivo credentials.json.",
    )
    item = google_harness(session)

    item.send("estado de google")

    assert "Falta el archivo credentials.json" in last_text(item)


def test_estado_conectado(google_harness) -> None:
    session = FakeGoogleSession(account="Ana Pérez (ana@example.com)")
    item = google_harness(session)

    item.send("estado de Google")

    assert "Google está conectado con Ana Pérez" in last_text(item)


def test_estado_configurado_sin_conectar(google_harness) -> None:
    session = FakeGoogleSession(connected=False, account="")
    item = google_harness(session)

    item.send("estado de Google")

    assert "todavía no está conectado" in last_text(item)
    assert "CONECTAR GOOGLE" in last_text(item)


# ======================================================================
# Conexión y desconexión
# ======================================================================
def test_conectar_google(google_harness) -> None:
    session = FakeGoogleSession(connected=False, account="")
    item = google_harness(session)

    item.send("conecta Google")

    assert session.connects == 1
    assert session.connected is True
    assert "quedó conectado" in last_text(item)
    assert item.rec.google
    assert item.rec.google[-1].connected is True
    assert any("navegador" in notice for notice in item.rec.notices)


def test_conectar_ya_conectado_no_reautoriza(google_harness) -> None:
    session = FakeGoogleSession(account="Ana Pérez (ana@example.com)")
    item = google_harness(session)

    item.send("conecta Google")

    assert session.connects == 0
    assert "ya está conectado" in last_text(item)


def test_conectar_sin_configuracion(google_harness) -> None:
    session = FakeGoogleSession(
        configured=False,
        connected=False,
        problem="Google Cloud no está configurado.",
    )
    item = google_harness(session)

    item.send("conecta Google")

    assert session.connects == 0
    assert "Google Cloud no está configurado" in last_error(item)


def test_conectar_cancelado_por_el_usuario(google_harness) -> None:
    session = FakeGoogleSession(
        connected=False, connect_error=GoogleAuthCancelledError()
    )
    item = google_harness(session)

    item.send("conecta Google")

    assert session.connected is False
    assert "canceló la conexión con Google" in last_error(item)


def test_conectar_sin_permisos(google_harness) -> None:
    session = FakeGoogleSession(
        connected=False, connect_error=GoogleConsentDeniedError()
    )
    item = google_harness(session)

    item.send("conecta Google")

    assert "No se concedieron los permisos" in last_error(item)


def test_error_inesperado_al_conectar(google_harness) -> None:
    session = FakeGoogleSession(connected=False, connect_error=RuntimeError("boom"))
    item = google_harness(session)

    item.send("conecta Google")

    assert "No se pudo conectar con Google" in last_error(item)


def test_desconectar_google(google_harness) -> None:
    session = FakeGoogleSession()
    item = google_harness(session)

    item.send("desconecta Google")

    assert session.disconnects == 1
    assert session.connected is False
    assert "He desconectado Google" in last_text(item)
    assert item.rec.google[-1].connected is False


def test_desconectar_si_ya_estaba_desconectado(google_harness) -> None:
    session = FakeGoogleSession(connected=False, account="")
    item = google_harness(session)

    item.send("desconecta Google")

    assert "ya estaba desconectado" in last_text(item)


# ======================================================================
# Correo
# ======================================================================
def test_revisar_correos_y_publicar_estado(google_harness) -> None:
    mail = FakeMailService(
        messages=(
            message("a", subject="Propuesta", is_read=False),
            message("b", subject="Factura", is_read=True),
        )
    )
    item = google_harness(FakeGoogleSession(mail=mail))

    item.send("revisa mis correos")

    assert mail.list_calls == 1
    assert "Propuesta" in last_text(item)
    info = item.rec.google[-1]
    assert info.mail_count == 2
    assert info.unread == 1
    assert info.mail_query.startswith("Bandeja de entrada de Gmail")
    assert "2 correos" in info.detail or info.detail == ""


def test_contar_correos_sin_leer(google_harness) -> None:
    mail = FakeMailService(
        messages=(
            message("a", is_read=False),
            message("b", is_read=False),
            message("c", is_read=True),
        )
    )
    item = google_harness(FakeGoogleSession(mail=mail))

    item.send("¿cuántos correos sin leer tengo?")

    assert "2 sin leer" in last_text(item)


def test_leer_el_ultimo_correo(google_harness) -> None:
    mail = FakeMailService(messages=(message("a", subject="Último asunto"),))
    item = google_harness(FakeGoogleSession(mail=mail))

    item.send("lee el último correo")

    assert mail.detail_calls == ["a"]
    assert "Último asunto" in last_text(item)


def test_buscar_correo_por_remitente(google_harness) -> None:
    mail = FakeMailService(
        messages=(
            message("a", subject="Propuesta", sender_name="Ana Pérez"),
            message("b", subject="Factura", sender_name="Luis Soto"),
        )
    )
    item = google_harness(FakeGoogleSession(mail=mail))

    item.send("busca el correo de Ana")

    assert "Propuesta" in last_text(item)


def test_seguimiento_del_correo(google_harness) -> None:
    mail = FakeMailService(messages=(message("a", subject="Plan semanal"),))
    item = google_harness(FakeGoogleSession(mail=mail))

    item.send("revisa mis correos")
    item.send("¿de quién es el correo?")

    assert "Ana Pérez" in last_text(item)
    assert mail.detail_calls == ["a"]


def test_correo_sin_conexion(google_harness) -> None:
    session = FakeGoogleSession(connected=False, account="")
    item = google_harness(session)

    item.send("revisa mis correos")

    assert "Google no está conectado" in last_error(item)
    assert "CONECTAR GOOGLE" in last_error(item)
    assert item.rec.google[-1].connected is False


def test_correo_sin_configuracion(google_harness) -> None:
    session = FakeGoogleSession(
        configured=False,
        connected=False,
        problem="Falta credentials.json.",
    )
    item = google_harness(session)

    item.send("revisa mis correos")

    assert "Falta credentials.json" in last_error(item)


def test_sesion_vencida_limpia_el_contexto(google_harness) -> None:
    mail = FakeMailService(error=GoogleAuthExpiredError())
    session = FakeGoogleSession(mail=mail)
    item = google_harness(session)

    item.send("revisa mis correos")

    assert session.expired == 1
    assert "La sesión de Google venció" in last_error(item)
    assert item.rec.google[-1].connected is False
    assert session.connected is False


def test_limite_de_peticiones_muestra_error_claro(google_harness) -> None:
    mail = FakeMailService(error=GoogleRateLimitError())
    item = google_harness(FakeGoogleSession(mail=mail))

    item.send("revisa mis correos")

    assert "limitó temporalmente" in last_error(item)


def test_refrescar_correo_desde_la_interfaz(google_harness) -> None:
    mail = FakeMailService()
    item = google_harness(FakeGoogleSession(mail=mail))

    item.controller.refresh_mail()
    assert item.controller.wait_for_idle(3.0)
    assert mail.list_calls == 1


# ======================================================================
# Calendario
# ======================================================================
def test_consultar_agenda_de_hoy(google_harness) -> None:
    calendar = FakeCalendarService(
        events=(event("ev-1", subject="Revisión semanal"),),
        now_value=at(2026, 11, 18, 7, 0),
    )
    item = google_harness(FakeGoogleSession(calendar=calendar))

    item.send("¿qué tengo hoy?")

    assert calendar.windows == ["today"]
    assert "Revisión semanal" in last_text(item)
    info = item.rec.google[-1]
    assert info.calendar_count == 1
    assert "Revisión semanal" in info.next_event


def test_agenda_vacia(google_harness) -> None:
    calendar = FakeCalendarService(events=())
    item = google_harness(FakeGoogleSession(calendar=calendar))

    item.send("¿qué tengo hoy?")

    assert "No hay eventos" in last_text(item)


def test_proxima_reunion(google_harness) -> None:
    calendar = FakeCalendarService(
        events=(
            event(
                "ev-1",
                subject="Revisión",
                start=at(2026, 11, 18, 9),
                end=at(2026, 11, 18, 10),
            ),
        ),
        now_value=at(2026, 11, 18, 7, 0),
    )
    item = google_harness(FakeGoogleSession(calendar=calendar))

    item.send("¿cuál es mi próxima reunión?")

    assert calendar.windows == ["next7"]
    assert "Revisión" in last_text(item)


def test_seguimiento_de_la_agenda(google_harness) -> None:
    calendar = FakeCalendarService(
        events=(event("ev-1", subject="Revisión", location="Sala 3"),),
        now_value=at(2026, 11, 18, 7, 0),
    )
    item = google_harness(FakeGoogleSession(calendar=calendar))

    item.send("¿qué tengo hoy?")
    item.send("¿dónde es el evento?")

    assert "Sala 3" in last_text(item)


def test_refrescar_calendario_con_periodo(google_harness) -> None:
    calendar = FakeCalendarService()
    item = google_harness(FakeGoogleSession(calendar=calendar))

    item.controller.refresh_calendar("tomorrow")
    assert item.controller.wait_for_idle(3.0)
    assert calendar.windows == ["tomorrow"]


def test_calendario_sin_conexion(google_harness) -> None:
    session = FakeGoogleSession(connected=False, account="")
    item = google_harness(session)

    item.send("¿qué tengo hoy?")

    assert "Google no está conectado" in last_error(item)
