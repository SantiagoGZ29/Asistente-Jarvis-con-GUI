"""Pruebas de Google Calendar: períodos, zona local, paginación y contexto."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from google_helpers import (
    FakeCalendarClient,
    FakeCalendarService,
    FakeProvider,
    allowed_consent,
    at,
    calendar_event,
    event,
    utc,
)

from jarvis.core.errors import GoogleApiError
from jarvis.integrations.google_calendar import (
    PERIOD_NEXT7,
    PERIOD_TODAY,
    PERIOD_TOMORROW,
    PERIOD_WEEK,
    CalendarEvent,
    CalendarWindow,
    GoogleCalendarAssistant,
    GoogleCalendarService,
    compute_window,
    period_label,
    weekday_period,
)

SANTIAGO = ZoneInfo("America/Santiago")
NOW = at(2026, 11, 18, 7, 0)


def service(client: FakeCalendarClient) -> GoogleCalendarService:
    return GoogleCalendarService(
        client,
        timezone_name="America/Santiago",
        clock=lambda: NOW,
    )


# ----------------------------------------------------------------------
# Períodos
# ----------------------------------------------------------------------
def test_periodo_hoy_y_manana() -> None:
    start, end = compute_window(PERIOD_TODAY, now=NOW, tz=SANTIAGO)
    assert start == at(2026, 11, 18, 0, 0)
    assert end.date() == NOW.date()
    assert end.hour == 23 and end.minute == 59

    tomorrow_start, tomorrow_end = compute_window(
        PERIOD_TOMORROW, now=NOW, tz=SANTIAGO
    )
    assert tomorrow_start == at(2026, 11, 19, 0, 0)
    assert tomorrow_end.date() == tomorrow_start.date()


def test_semana_laboral_de_lunes_a_viernes() -> None:
    start, end = compute_window(PERIOD_WEEK, now=NOW, tz=SANTIAGO)
    assert start == at(2026, 11, 16, 0, 0)
    assert start.weekday() == 0
    assert end.date() == start.date() + timedelta(days=4)
    assert end.weekday() == 4


def test_proximos_siete_dias_desde_ahora() -> None:
    start, end = compute_window(PERIOD_NEXT7, now=NOW, tz=SANTIAGO)
    assert start == NOW
    assert end == NOW + timedelta(days=7)


def test_periodo_de_dia_de_la_semana() -> None:
    monday = compute_window(weekday_period(0), now=NOW, tz=SANTIAGO)
    assert monday[0].date() == NOW.date() + timedelta(days=5)
    assert monday[0].weekday() == 0

    today = compute_window(weekday_period(2), now=NOW, tz=SANTIAGO)
    assert today[0].date() == NOW.date()

    assert period_label(PERIOD_TODAY) == "hoy"
    assert period_label(PERIOD_TOMORROW) == "mañana"
    assert period_label(PERIOD_WEEK) == "esta semana"
    assert period_label(PERIOD_NEXT7) == "los próximos siete días"
    assert period_label(weekday_period(0)) == "el lunes"
    assert weekday_period(99) == "weekday:6"


def test_hora_naive_se_interpreta_en_la_zona_local() -> None:
    naive = datetime(2026, 11, 18, 10, 0)
    start, end = compute_window(PERIOD_TODAY, now=naive, tz=SANTIAGO)
    assert start.tzinfo == SANTIAGO
    assert start.date() == naive.date()


# ----------------------------------------------------------------------
# Consulta y paginación
# ----------------------------------------------------------------------
def test_consulta_usa_primary_single_events_y_zona_local() -> None:
    client = FakeCalendarClient(pages=[{"items": []}])

    service(client).list_window(PERIOD_TODAY, now=NOW)

    call = client.calls[0]
    assert call["time_zone"] == "America/Santiago"
    assert call["time_min"] == "2026-11-18T00:00:00-03:00"
    assert call["max_results"] == 200
    assert call["page_token"] is None


def test_paginacion_con_next_page_token() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event(
                        "ev-1",
                        start={"dateTime": utc(2026, 11, 18, 12)},
                        end={"dateTime": utc(2026, 11, 18, 13)},
                    )
                ],
                "nextPageToken": "pagina-2",
            },
            {
                "items": [
                    calendar_event(
                        "ev-2",
                        summary="Almuerzo",
                        start={"dateTime": utc(2026, 11, 18, 15)},
                        end={"dateTime": utc(2026, 11, 18, 16)},
                    )
                ]
            },
        ]
    )

    window = service(client).list_window(PERIOD_TODAY, now=NOW)

    assert [item.id for item in window.events] == ["ev-1", "ev-2"]
    assert [call["page_token"] for call in client.calls] == [None, "pagina-2"]


def test_evento_cancelado_y_formato_invalido_se_omiten() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event("cancelado", status="cancelled"),
                    {"id": "sin-fechas", "summary": "Roto"},
                    calendar_event(
                        "ok",
                        start={"dateTime": utc(2026, 11, 18, 12)},
                        end={"dateTime": utc(2026, 11, 18, 13)},
                    ),
                ]
            }
        ]
    )

    window = service(client).list_window(PERIOD_TODAY, now=NOW)

    assert [item.id for item in window.events] == ["ok"]


def test_respuesta_con_items_invalidos() -> None:
    client = FakeCalendarClient(pages=[{"items": "no-es-lista"}])
    with pytest.raises(GoogleApiError):
        service(client).list_window(PERIOD_TODAY, now=NOW)


def test_eventos_fuera_de_la_ventana_y_duplicados() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event(
                        "antes",
                        start={"dateTime": utc(2026, 11, 10, 12)},
                        end={"dateTime": utc(2026, 11, 10, 13)},
                    ),
                    calendar_event(
                        "dentro",
                        start={"dateTime": utc(2026, 11, 18, 12)},
                        end={"dateTime": utc(2026, 11, 18, 13)},
                    ),
                    calendar_event(
                        "dentro",
                        start={"dateTime": utc(2026, 11, 18, 12)},
                        end={"dateTime": utc(2026, 11, 18, 13)},
                    ),
                ],
                "nextPageToken": "p2",
            },
            {
                "items": [
                    calendar_event(
                        "despues",
                        start={"dateTime": utc(2026, 11, 25, 12)},
                        end={"dateTime": utc(2026, 11, 25, 13)},
                    )
                ]
            },
        ]
    )

    window = service(client).list_window(PERIOD_TODAY, now=NOW)

    assert [item.id for item in window.events] == ["dentro"]


def test_hora_utc_se_convierte_a_santiago() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event(
                        "ev-1",
                        start={"dateTime": "2026-11-18T12:00:00Z"},
                        end={"dateTime": "2026-11-18T13:30:00Z"},
                    )
                ]
            }
        ]
    )

    window = service(client).list_window(PERIOD_TODAY, now=NOW)
    item = window.events[0]

    assert item.start.hour == 9
    assert item.start.minute == 0
    assert item.start.tzinfo == SANTIAGO
    assert "09:00–10:30" in item.range_label


def test_hora_sin_zona_usa_la_zona_indicada() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event(
                        "ev-1",
                        start={
                            "dateTime": "2026-11-18T10:00:00",
                            "timeZone": "America/Santiago",
                        },
                        end={
                            "dateTime": "2026-11-18T11:00:00",
                            "timeZone": "America/Santiago",
                        },
                    )
                ]
            }
        ]
    )

    item = service(client).list_window(PERIOD_TODAY, now=NOW).events[0]
    assert item.start == at(2026, 11, 18, 10, 0)


def test_evento_de_dia_completo_ajusta_el_fin_exclusivo() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event(
                        "todo-el-dia",
                        summary="Feriado",
                        start={"date": "2026-11-18"},
                        end={"date": "2026-11-19"},
                    )
                ]
            }
        ]
    )

    item = service(client).list_window(PERIOD_TODAY, now=NOW).events[0]

    assert item.is_all_day is True
    assert item.start == at(2026, 11, 18, 0, 0)
    assert item.end.date() == at(2026, 11, 18, 0, 0).date()
    assert item.end.hour == 23
    assert "todo el día" in item.range_label


def test_orden_por_hora_y_etiquetas() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    calendar_event(
                        "tarde",
                        summary="Tarde",
                        start={"dateTime": utc(2026, 11, 18, 18)},
                        end={"dateTime": utc(2026, 11, 18, 19)},
                    ),
                    calendar_event(
                        "manana",
                        summary="Mañana",
                        start={"dateTime": utc(2026, 11, 18, 12)},
                        end={"dateTime": utc(2026, 11, 18, 13)},
                    ),
                ]
            }
        ]
    )

    window = service(client).list_window(PERIOD_TODAY, now=NOW)

    assert [item.subject for item in window.events] == ["Mañana", "Tarde"]
    assert window.label == "hoy"
    assert window.count == 2
    assert window.events[0].show_as_label == "ocupado"
    assert window.events[0].compact(index=1).startswith("1. ")


def test_ubicacion_objeto_y_participantes() -> None:
    client = FakeCalendarClient(
        pages=[
            {
                "items": [
                    {
                        "id": "ev-1",
                        "summary": "  Reunión   clave ",
                        "start": {"dateTime": utc(2026, 11, 18, 12)},
                        "end": {"dateTime": utc(2026, 11, 18, 13)},
                        "location": {"displayName": "Sala 3"},
                        "organizer": {
                            "displayName": "Ana Pérez",
                            "email": "ana@example.com",
                        },
                        "attendees": [
                            {"displayName": "Luis", "email": "luis@example.com"},
                            {"email": "sin-nombre@example.com"},
                        ],
                        "transparency": "transparent",
                    }
                ]
            }
        ]
    )

    item = service(client).list_window(PERIOD_TODAY, now=NOW).events[0]

    assert item.subject == "Reunión clave"
    assert item.location == "Sala 3"
    assert item.organizer == "Ana Pérez <ana@example.com>"
    assert item.attendees == (
        "Luis <luis@example.com>",
        "sin-nombre@example.com",
    )
    assert item.show_as_label == "libre"
    detailed = item.detailed()
    assert "Dónde: Sala 3." in detailed
    assert "Participantes:" in detailed
    assert "Estado: libre." in detailed


# ----------------------------------------------------------------------
# Asistente
# ----------------------------------------------------------------------
def assistant(
    events: tuple[CalendarEvent, ...] | None = None,
    **kwargs: Any,
) -> GoogleCalendarAssistant:
    fake = FakeCalendarService(
        events=(event(),) if events is None else events,
        now_value=NOW,
    )
    return GoogleCalendarAssistant(fake, consent=allowed_consent(), **kwargs)


def test_agenda_lista_eventos_y_guarda_ventana() -> None:
    bot = assistant(
        (
            event("ev-1", subject="Revisión", start=at(2026, 11, 18, 9)),
            event("ev-2", subject="Almuerzo", start=at(2026, 11, 18, 12)),
        )
    )

    answer = bot.agenda(PERIOD_TODAY)

    assert answer.grounded is True
    assert "2 eventos" in answer.text
    assert "Revisión" in answer.text
    assert bot.window is not None
    assert bot.active is not None and bot.active.id == "ev-1"


def test_agenda_vacia() -> None:
    bot = assistant(())
    answer = bot.agenda(PERIOD_TODAY)
    assert "No hay eventos" in answer.text
    assert bot.active is None


def test_proximo_evento_ignora_los_pasados() -> None:
    bot = assistant(
        (
            event("viejo", subject="Ayer", start=at(2026, 11, 17, 9), end=at(2026, 11, 17, 10)),
            event("hoy", subject="Hoy", start=at(2026, 11, 18, 9), end=at(2026, 11, 18, 10)),
        )
    )

    answer = bot.next_event()

    assert "Hoy" in answer.text
    assert "próxima reunión" in answer.text


def test_proximo_evento_sin_reuniones() -> None:
    bot = assistant(())
    assert "No tienes reuniones" in bot.next_event().text


def test_seguimiento_de_ubicacion_horario_y_detalle() -> None:
    bot = assistant(
        (
            event("ev-1", subject="Revisión", location="Sala 3", start=at(2026, 11, 18, 9)),
            event("ev-2", subject="Almuerzo", location="Cafetería", start=at(2026, 11, 18, 12)),
        )
    )
    bot.agenda(PERIOD_TODAY)

    assert "Sala 3" in bot.follow_up("¿dónde es la primera?").text
    assert "Ana Pérez" in bot.follow_up("¿quién organiza?").text
    assert "Luis Soto" in bot.follow_up("¿quiénes participan?").text
    assert "09:00" in bot.follow_up("¿a qué hora empieza?").text
    assert "Evento:" in bot.follow_up("dame los detalles").text
    assert "Cafetería" in bot.follow_up("¿dónde es la de las 12?").text


def test_seguimiento_sin_agenda_consultada() -> None:
    bot = assistant()
    assert "Todavía no he consultado tu agenda" in bot.follow_up("¿dónde es?").text


def test_resumen_con_gemini_y_consentimiento() -> None:
    provider = FakeProvider(replies=["Tienes una revisión a las nueve."])
    bot = assistant(provider=provider)
    bot.agenda(PERIOD_TODAY)

    answer = bot.summarize()

    assert answer.text == "Tienes una revisión a las nueve."
    assert "AGENDA DE GOOGLE CALENDAR" in provider.prompts[0]
    assert "Revisión semanal" in provider.prompts[0]


def test_resumen_sin_proveedor_es_local() -> None:
    bot = assistant()
    bot.agenda(PERIOD_TODAY)

    answer = bot.summarize()

    assert "Resumen local" in answer.text
    assert answer.notice and "no se envió" in answer.notice


def test_pregunta_sin_proveedor_muestra_el_evento() -> None:
    bot = assistant()
    bot.agenda(PERIOD_TODAY)

    answer = bot.ask("¿hay algo urgente?")

    assert "Evento:" in answer.text
    assert answer.notice
