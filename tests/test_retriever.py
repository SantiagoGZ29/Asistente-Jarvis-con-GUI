"""Pruebas de la búsqueda local de fragmentos relevantes."""

from __future__ import annotations

from pathlib import Path

from jarvis.documents.chunker import chunk_document
from jarvis.documents.docx_loader import load_document
from jarvis.documents.retriever import Retriever, resolve_section, tokenize


def _retriever(path: Path) -> Retriever:
    document = load_document(path)
    return Retriever(chunk_document(document, max_chars=600))


def test_selecciona_contexto_relevante(sample_docx: Path) -> None:
    retriever = _retriever(sample_docx)
    hits = retriever.search("¿Cuál es el objetivo principal?")

    assert hits
    assert "objetivo" in hits[0].chunk.text.lower()
    assert hits[0].score > 0


def test_encuentra_fechas_y_plazos(sample_docx: Path) -> None:
    retriever = _retriever(sample_docx)
    hits = retriever.search("cuándo vence el plazo de revisión")

    assert hits
    best_text = hits[0].chunk.text.lower()
    assert "plazo" in best_text or "vence" in best_text
    assert "febrero" in best_text


def test_prioriza_coincidencias_en_encabezado(sample_docx: Path) -> None:
    retriever = _retriever(sample_docx)
    hits = retriever.search("responsabilidades")

    assert hits
    assert "Responsabilidades" in hits[0].chunk.heading_path


def test_consulta_sin_relacion_no_devuelve_nada(sample_docx: Path) -> None:
    retriever = _retriever(sample_docx)
    assert retriever.search("criptografía cuántica y fusión nuclear") == []


def test_consulta_vacia_no_devuelve_nada(sample_docx: Path) -> None:
    retriever = _retriever(sample_docx)
    assert retriever.search("   ") == []
    assert retriever.search("¿y el de la?") == []


def test_resuelve_secciones_por_numero_y_titulo(sample_docx: Path) -> None:
    document = load_document(sample_docx)

    by_number = resolve_section(document, "2")
    assert by_number is not None
    assert by_number.title == "Objetivo"

    by_title = resolve_section(document, "responsabilidades")
    assert by_title is not None
    assert by_title.title == "Responsabilidades"

    assert resolve_section(document, "99") is None
    assert resolve_section(document, "sección inexistente") is None
    assert resolve_section(document, "") is None


def test_tokenizacion_ignora_acentos_y_palabras_vacias() -> None:
    tokens = tokenize("¿Cuáles son las FECHAS de entrega del informe?")
    assert "fechas" in tokens
    assert "entrega" in tokens
    assert "cuales" not in tokens
    assert "son" not in tokens
