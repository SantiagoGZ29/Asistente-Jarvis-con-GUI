"""Pruebas de lectura de documentos .docx."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from jarvis.core.errors import (
    DocumentEmptyError,
    DocumentFormatError,
    DocumentNotFoundError,
    DocumentProtectedError,
)
from jarvis.documents.docx_loader import load_document


def test_lee_parrafos_y_tablas(sample_docx: Path) -> None:
    document = load_document(sample_docx)

    assert document.path == sample_docx
    assert "objetivo principal" in document.plain_text().lower()
    assert len(document.paragraphs) >= 8
    assert len(document.tables) == 1

    table = document.tables[0]
    assert table.id == "T1"
    assert table.row_count == 3
    assert table.column_count == 3
    assert table.rows[0] == ("Tarea", "Responsable", "Fecha")
    assert table.rows[1][1] == "Ana"
    assert "Preparar informe" in table.as_text()


def test_identificadores_internos_unicos(sample_docx: Path) -> None:
    document = load_document(sample_docx)
    ids = [block.id for block in document.blocks]
    assert ids == list(dict.fromkeys(ids))
    assert all(block_id.startswith(("P", "T")) for block_id in ids)
    assert document.block_map["T1"].row_count == 3


def test_identifica_encabezados_y_su_ubicacion(sample_docx: Path) -> None:
    document = load_document(sample_docx)

    assert [section.title for section in document.sections] == [
        "Manual de Ejemplo",
        "Objetivo",
        "Responsabilidades",
        "Fechas y plazos",
        "Tabla de tareas",
        "Conclusiones",
    ]

    objective = next(
        paragraph
        for paragraph in document.paragraphs
        if "objetivo principal" in paragraph.text
    )
    assert objective.heading_path == ("Manual de Ejemplo", "Objetivo")

    responsibilities = next(
        paragraph
        for paragraph in document.paragraphs
        if "coordinador debe revisar" in paragraph.text
    )
    assert responsibilities.heading_path[-1] == "Responsabilidades"

    table = document.tables[0]
    assert table.heading_path[-1] == "Tabla de tareas"


def test_documento_vacio_falla_con_mensaje_claro(tmp_path: Path) -> None:
    path = tmp_path / "vacio.docx"
    Document().save(str(path))

    with pytest.raises(DocumentEmptyError) as error:
        load_document(path)
    assert "no contiene texto" in error.value.user_message.lower()


def test_archivo_corrupto_falla_con_mensaje_claro(tmp_path: Path) -> None:
    path = tmp_path / "roto.docx"
    path.write_bytes(b"esto no es un archivo de Word")

    with pytest.raises(DocumentFormatError) as error:
        load_document(path)
    assert "dañado" in error.value.user_message.lower() or "válido" in error.value.user_message.lower()


def test_extension_no_soportada(tmp_path: Path) -> None:
    path = tmp_path / "documento.txt"
    path.write_text("texto plano", encoding="utf-8")

    with pytest.raises(DocumentFormatError) as error:
        load_document(path)
    assert ".docx" in error.value.user_message


def test_archivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(DocumentNotFoundError):
        load_document(tmp_path / "no-existe.docx")


def test_documento_protegido_o_bloqueado(
    sample_docx: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jarvis.documents.docx_loader as loader

    def raise_permission(*args, **kwargs):
        raise PermissionError("archivo en uso")

    monkeypatch.setattr(loader, "DocxDocument", raise_permission)

    with pytest.raises(DocumentProtectedError) as error:
        load_document(sample_docx)
    assert "protegido" in error.value.user_message.lower() or "word" in error.value.user_message.lower()
