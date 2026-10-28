"""Pruebas de fragmentación y agrupación de documentos."""

from __future__ import annotations

from pathlib import Path

from jarvis.documents.chunker import (
    batch_chunks,
    chunk_document,
    chunks_for_heading,
)
from jarvis.documents.docx_loader import load_document


def test_documento_corto_genera_fragmentos_con_fuente(sample_docx: Path) -> None:
    document = load_document(sample_docx)
    chunks = chunk_document(document, max_chars=1_200)

    assert chunks
    assert all(chunk.text.strip() for chunk in chunks)
    assert all(chunk.block_ids for chunk in chunks)
    assert any("objetivo principal" in chunk.text for chunk in chunks)

    objective = next(
        chunk for chunk in chunks if "objetivo principal" in chunk.text
    )
    assert "Objetivo" in objective.heading_path
    assert "Manual de Ejemplo" in objective.heading_path
    assert "Encabezado:" in objective.prompt_text


def test_documento_extenso_se_fragmenta(long_docx: Path) -> None:
    document = load_document(long_docx)
    chunks = chunk_document(document, max_chars=400)

    assert len(chunks) > 10
    assert all(len(chunk.text) <= 400 for chunk in chunks)
    # Los identificadores de fragmento son estables y únicos.
    assert [chunk.chunk_id for chunk in chunks] == [
        f"C{index}" for index in range(1, len(chunks) + 1)
    ]
    # Cada fragmento conserva el encabezado de su sección.
    assert all(chunk.heading_path for chunk in chunks)


def test_parrafo_muy_largo_se_divide(sample_docx: Path) -> None:
    document = load_document(sample_docx)
    chunks = chunk_document(document, max_chars=60)

    assert len(chunks) > 1
    # Los fragmentos de texto nunca superan el límite; los de tabla pueden
    # incluir la cabecera repetida, necesaria para interpretar las filas.
    text_chunks = [chunk for chunk in chunks if chunk.kind == "texto"]
    assert all(len(chunk.text) <= 60 for chunk in text_chunks)
    assert any("objetivo" in chunk.text.lower() for chunk in text_chunks)


def test_las_tablas_entran_en_la_busqueda(sample_docx: Path) -> None:
    document = load_document(sample_docx)
    chunks = chunk_document(document, max_chars=1_200)

    table_chunks = [chunk for chunk in chunks if chunk.kind == "tabla"]
    assert table_chunks
    assert any("Preparar informe" in chunk.text for chunk in table_chunks)
    assert all("T1" in chunk.block_ids for chunk in table_chunks)


def test_agrupacion_respeta_el_limite(long_docx: Path) -> None:
    document = load_document(long_docx)
    chunks = chunk_document(document, max_chars=400)
    batches = batch_chunks(chunks, 1_500)

    assert len(batches) > 1
    assert sum(len(batch) for batch in batches) == len(chunks)
    for batch in batches:
        total = sum(chunk.char_count + 2 for chunk in batch)
        assert total <= 1_500


def test_fragmentos_por_encabezado(sample_docx: Path) -> None:
    document = load_document(sample_docx)
    chunks = chunk_document(document, max_chars=1_200)
    section = next(
        section for section in document.sections if section.title == "Responsabilidades"
    )
    selected = chunks_for_heading(chunks, section.path)

    assert selected
    assert all("Responsabilidades" in chunk.heading_path for chunk in selected)
    assert any("coordinador" in chunk.text for chunk in selected)
