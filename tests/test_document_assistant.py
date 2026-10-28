"""Pruebas del asistente documental con un proveedor simulado."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.assistants.document_assistant import (
    NO_INFO_MARKER,
    DocumentAssistant,
)
from jarvis.core.consent import ConsentManager
from jarvis.core.errors import ConsentDeniedError
from jarvis.documents.chunker import chunk_document
from jarvis.documents.docx_loader import load_document


def _assistant(path: Path, provider, *, consent=None, **kwargs) -> DocumentAssistant:
    document = load_document(path)
    options = {
        "chunks": chunk_document(document, max_chars=400),
        "max_context_chars": 3_000,
        "max_batch_chars": 1_500,
        "chunk_size_chars": 400,
        "consent": consent,
    }
    options.update(kwargs)
    return DocumentAssistant(provider, document, **options)


def test_pregunta_devuelve_respuesta_y_fuentes(sample_docx: Path, fake_provider) -> None:
    assistant = _assistant(sample_docx, fake_provider)
    answer = assistant.ask("¿Cuál es el objetivo principal?")

    assert answer.grounded is True
    assert "organizar el trabajo" in answer.text
    assert answer.sources
    assert "Objetivo" in answer.sources[0].heading
    assert "Fuentes consultadas" in answer.render()
    assert fake_provider.call_count == 1

    prompt = fake_provider.calls[0]["prompt"]
    assert "INICIO_DOCUMENTO" in prompt
    assert "FIN_DOCUMENTO>>>" in prompt
    assert "objetivo principal" in prompt.lower()
    # Solo se envía el contexto necesario, no el documento completo.
    assert "15 de marzo" not in prompt
    assert len(prompt) < 3_000 + 1_200


def test_elimina_citas_inventadas(sample_docx: Path, make_fake_provider) -> None:
    provider = make_fake_provider(
        "El objetivo es organizar el trabajo [P4] y también [P99] y [T7]."
    )
    assistant = _assistant(sample_docx, provider)
    answer = assistant.ask("objetivo principal")

    assert "[P4]" in answer.text
    assert "[P99]" not in answer.text
    assert "[T7]" not in answer.text
    assert answer.sources[0].ref == "P4"


def test_pregunta_sin_relacion_no_llama_al_proveedor(
    sample_docx: Path, fake_provider
) -> None:
    assistant = _assistant(sample_docx, fake_provider)
    answer = assistant.ask("¿Qué dice sobre criptografía cuántica?")

    assert answer.grounded is False
    assert "No encontré" in answer.text
    assert fake_provider.call_count == 0


def test_respuesta_controlada_si_el_modelo_no_encuentra_informacion(
    sample_docx: Path, make_fake_provider
) -> None:
    provider = make_fake_provider(NO_INFO_MARKER)
    assistant = _assistant(sample_docx, provider)
    answer = assistant.ask("¿Cuál es el objetivo principal?")

    assert answer.grounded is False
    assert "no contiene información suficiente" in answer.text.lower()
    assert NO_INFO_MARKER not in answer.text
    assert answer.sources  # se muestran los fragmentos revisados


def test_resumen_general_incluye_secciones_obligatorias(
    sample_docx: Path, make_fake_provider
) -> None:
    provider = make_fake_provider("1. Objetivo principal: organizar el trabajo [P4].")
    assistant = _assistant(sample_docx, provider)
    answer = assistant.summarize()

    assert answer.grounded is True
    assert "organizar el trabajo" in answer.text
    prompt = provider.calls[0]["prompt"]
    for section in (
        "Objetivo principal",
        "Ideas y conceptos clave",
        "Responsabilidades",
        "Fechas y plazos",
        "Acciones pendientes",
        "Conclusiones relevantes",
    ):
        assert section in prompt
    assert provider.call_count == 1


def test_resumen_de_documento_extenso_usa_varios_lotes(
    long_docx: Path, make_fake_provider
) -> None:
    provider = make_fake_provider("Resumen parcial simulado [P1].")
    assistant = _assistant(long_docx, provider)
    answer = assistant.summarize()

    assert answer.grounded is True
    assert provider.call_count > 1
    assert "Resumen parcial" in provider.calls[-1]["prompt"]
    assert "síntesis final" in provider.calls[-1]["prompt"].lower()


def test_resumen_de_seccion_concreta(sample_docx: Path, make_fake_provider) -> None:
    provider = make_fake_provider("Resumen de la sección [P4].")
    assistant = _assistant(sample_docx, provider)
    answer = assistant.summarize_section("2")

    assert answer.grounded is True
    assert "Manual de Ejemplo > Objetivo" in provider.calls[0]["prompt"]
    assert "Sección: Manual de Ejemplo > Objetivo" in provider.calls[0]["prompt"]


def test_seccion_inexistente_informa_y_lista_opciones(
    sample_docx: Path, fake_provider
) -> None:
    assistant = _assistant(sample_docx, fake_provider)
    answer = assistant.summarize_section("99")

    assert answer.grounded is False
    assert "No encontré una sección" in answer.text
    assert "Objetivo" in answer.text
    assert fake_provider.call_count == 0


def test_explicacion_breve_por_defecto(sample_docx: Path, make_fake_provider) -> None:
    provider = make_fake_provider(
        "El objetivo es ordenar el trabajo del equipo. Por ejemplo, asignar tareas [P4]."
    )
    assistant = _assistant(sample_docx, provider)
    answer = assistant.explain("objetivo")

    assert answer.grounded is True
    prompt = provider.calls[0]["prompt"]
    assert "uno a tres párrafos" in prompt
    assert "lenguaje claro" in prompt
    assert provider.calls[0]["max_output_tokens"] == 700


def test_extrae_fechas_y_plazos(sample_docx: Path, make_fake_provider) -> None:
    provider = make_fake_provider(
        "- 15 de marzo de 2026: entrega final [P9].\n"
        "- 28 de febrero de 2026: plazo de revisión [P10]."
    )
    assistant = _assistant(sample_docx, provider)
    answer = assistant.extract("fechas")

    assert answer.grounded is True
    assert "15 de marzo" in answer.text
    assert answer.sources
    prompt = provider.calls[0]["prompt"]
    assert "Extrae todas las fechas" in prompt


def test_consentimiento_denegado_impide_llamar_al_proveedor(
    sample_docx: Path, fake_provider
) -> None:
    consent = ConsentManager(lambda request: False)
    assistant = _assistant(sample_docx, fake_provider, consent=consent)

    with pytest.raises(ConsentDeniedError):
        assistant.ask("¿Cuál es el objetivo principal?")
    assert fake_provider.call_count == 0


def test_consentimiento_aceptado_se_pide_una_sola_vez(
    sample_docx: Path, fake_provider
) -> None:
    calls: list[str] = []
    consent = ConsentManager(lambda request: calls.append(request.key) or True)
    assistant = _assistant(sample_docx, fake_provider, consent=consent)

    assistant.ask("objetivo principal")
    assistant.explain("objetivo")

    assert calls == ["gemini_document"]
    assert fake_provider.call_count == 2
