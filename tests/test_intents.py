"""Pruebas del intérprete de órdenes en español."""

from __future__ import annotations

import pytest

from jarvis.core import intents


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Jarvis, hazme un resumen breve de este documento", intents.SUMMARY),
        ("resume el documento completo", intents.SUMMARY),
        ("¿De qué trata este manual?", intents.SUMMARY),
        ("dame un resumen general", intents.SUMMARY),
        ("extrae las fechas y plazos", intents.EXTRACT_DATES),
        ("lista las acciones pendientes", intents.EXTRACT_ACTIONS),
        ("enumera las responsabilidades", intents.EXTRACT_RESPONSIBILITIES),
        ("muéstrame las conclusiones", intents.EXTRACT_CONCLUSIONS),
        ("cambiar documento", intents.SELECT_DOCUMENT),
        ("Jarvis, lee el manual que tengo abierto", intents.SELECT_DOCUMENT),
        ("modo voz", intents.MODE_VOICE),
        ("quiero hablar por el micrófono", intents.MODE_VOICE),
        ("modo texto", intents.MODE_TEXT),
        ("desactivar la voz", intents.MODE_TEXT),
        ("ayuda", intents.HELP),
        ("¿Qué puedes hacer?", intents.HELP),
        ("salir", intents.EXIT),
        ("adios", intents.EXIT),
    ],
)
def test_reconoce_acciones_naturales(text: str, expected: str) -> None:
    assert intents.parse(text).name == expected


def test_explicacion_de_un_apartado_concreto() -> None:
    intent = intents.parse("¿Me puedes explicar brevemente el segundo apartado?")

    assert intent.name == intents.EXPLAIN
    assert intent.section == "2"
    assert intent.detail is False


def test_explicacion_con_detalle() -> None:
    intent = intents.parse("Explícame el objetivo con más detalle")
    assert intent.name == intents.EXPLAIN
    assert intent.detail is True
    assert "objetivo" in (intent.topic or "")


def test_resumen_de_una_seccion() -> None:
    intent = intents.parse("Resume la sección 3")
    assert intent.name == intents.SUMMARY_SECTION
    assert intent.section == "3"

    by_name = intents.parse("hazme un resumen del apartado de responsabilidades")
    assert by_name.name == intents.SUMMARY_SECTION
    assert by_name.section == "responsabilidades"


def test_preguntas_generales_se_tratan_como_pregunta() -> None:
    for text in (
        "¿Qué debo hacer primero según este manual?",
        "¿Cuáles son las tareas y responsabilidades que menciona?",
        "¿En qué sección aparece la información sobre plazos?",
        "Explícame este apartado como si fuera una persona que recién está aprendiendo el tema",
    ):
        intent = intents.parse(text)
        assert intent.name in {intents.QUESTION, intents.EXPLAIN}, text


def test_ordinales_y_acentos() -> None:
    assert intents.parse("resume el tercer apartado").section == "3"
    assert intents.parse("resume la sección número 4").section == "4"
    assert intents.parse("explícame el capítulo 2").section == "2"


def test_texto_vacio_es_pregunta_vacia() -> None:
    intent = intents.parse("   ")
    assert intent.name == intents.QUESTION


def test_quita_la_palabra_de_activacion() -> None:
    intent = intents.parse("Jarvis, salir")
    assert intent.name == intents.EXIT


@pytest.mark.parametrize(
    "text",
    ["Hola, Jarvis", "hola jarvis", "Buenas tardes", "¿Qué tal, Jarvis?", "hey"],
)
def test_reconoce_saludos(text: str) -> None:
    assert intents.parse(text).name == intents.GREETING


@pytest.mark.parametrize(
    ("text", "query"),
    [
        ("Jarvis, abre el manual de mi Jarvis", "manual de mi jarvis"),
        (
            "Abre el documento de Descargas llamado informe semanal",
            "informe semanal",
        ),
        (
            "Busca el archivo planificación del proyecto en Descargas y ábrelo",
            "planificacion del proyecto",
        ),
        ("Abre el documento que se llama proyecto final", "proyecto final"),
        ("abre el documento", None),
        ("busca el informe anual en la carpeta de descargas", "informe anual"),
    ],
)
def test_ordenes_de_apertura_de_documentos(text: str, query: str | None) -> None:
    intent = intents.parse(text)

    assert intent.name == intents.OPEN_DOCUMENT
    assert intent.document_query == query


@pytest.mark.parametrize(
    ("text", "query", "kind"),
    [
        ("Abre el Excel de tareas de Descargas", "tareas", "spreadsheet"),
        ("abre el libro seguimiento mensual", "seguimiento mensual", "spreadsheet"),
        ("busca la planilla de gastos.xlsx", "gastos", "spreadsheet"),
        ("abre el archivo informe.xlsx de descargas", "informe", "spreadsheet"),
        ("abre el documento informe de Descargas", "informe", "document"),
        ("abre el word del proyecto", "proyecto", "document"),
        ("abre el archivo de descargas", None, ""),
    ],
)
def test_reconoce_aperturas_de_excel_y_word(
    text: str, query: str | None, kind: str
) -> None:
    intent = intents.parse(text)

    assert intent.name == intents.OPEN_DOCUMENT
    assert intent.document_query == query
    assert intent.file_kind == kind


def test_lee_el_manual_sigue_pidiendo_selector() -> None:
    intent = intents.parse("Jarvis, lee el manual que tengo abierto")
    assert intent.name == intents.SELECT_DOCUMENT


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("detente", intents.STOP_SPEECH),
        ("deja de hablar", intents.STOP_SPEECH),
        ("detén la voz", intents.STOP_SPEECH),
        ("pausa el micrófono", intents.PAUSE_MIC),
        ("no escuches un momento", intents.PAUSE_MIC),
        ("vuelve a escuchar", intents.RESUME_MIC),
        ("reanuda la escucha", intents.RESUME_MIC),
        ("cancela eso", intents.CANCEL),
        ("olvídalo", intents.CANCEL),
    ],
)
def test_comandos_de_la_interfaz(text: str, expected: str) -> None:
    assert intents.parse(text).name == expected


def test_una_pregunta_larga_no_se_confunde_con_un_comando() -> None:
    for text in (
        "¿El documento explica cómo detener la voz del asistente paso a paso?",
        "¿Qué dice el manual sobre la pausa del proyecto y sus plazos?",
    ):
        assert intents.parse(text).name not in {
            intents.STOP_SPEECH,
            intents.PAUSE_MIC,
            intents.RESUME_MIC,
            intents.CANCEL,
        }


def test_apertura_con_resumen_posterior_limpia_la_consulta() -> None:
    intent = intents.parse("abre el manual de descargas y resúmelo")

    assert intent.name == intents.OPEN_DOCUMENT
    assert intent.document_query == "manual"
