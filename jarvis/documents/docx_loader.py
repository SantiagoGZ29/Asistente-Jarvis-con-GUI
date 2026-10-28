"""Lectura de documentos de Microsoft Word (.docx) con python-docx."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table as DocxTable
from docx.text.paragraph import Paragraph as DocxParagraph
from docx.oxml.ns import qn

from jarvis.core.errors import (
    DocumentEmptyError,
    DocumentFormatError,
    DocumentNotFoundError,
    DocumentProtectedError,
)
from jarvis.core.logging_setup import get_logger
from jarvis.documents.models import DocumentModel, Paragraph, Section, TableBlock

logger = get_logger("docx_loader")

_HEADING_STYLE_RE = re.compile(r"^(heading|titulo|t[ií]tulo)\s*(\d)$", re.IGNORECASE)
_SUPPORTED_SUFFIXES = {".docx"}


def _heading_level(paragraph: DocxParagraph) -> int | None:
    """Nivel de encabezado según el estilo o el nivel de esquema del párrafo."""
    style = paragraph.style
    if style is not None:
        name = (style.name or "").strip()
        match = _HEADING_STYLE_RE.match(name)
        if match:
            return int(match.group(2))
        # Algunos documentos usan estilos propios basados en "Heading N".
        base = style.base_style
        depth = 0
        while base is not None and depth < 5:
            match = _HEADING_STYLE_RE.match((base.name or "").strip())
            if match:
                return int(match.group(2))
            base = base.base_style
            depth += 1

    element = paragraph._p
    properties = element.pPr
    if properties is not None and properties.outlineLvl is not None:
        try:
            level = int(properties.outlineLvl.val) + 1
        except (TypeError, ValueError):
            return None
        if 1 <= level <= 9:
            return level
    return None


def _clean_cell(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _table_rows(table: DocxTable) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            text = _clean_cell(cell.text)
            # Las celdas combinadas se repiten en python-docx; se evita el duplicado.
            if cells and cells[-1] == text:
                continue
            cells.append(text)
        if any(cells):
            rows.append(tuple(cells))
    return tuple(rows)


def _section_texts(document) -> tuple[tuple[str, ...], tuple[str, ...]]:
    headers: list[str] = []
    footers: list[str] = []
    for section in document.sections:
        try:
            for paragraph in section.header.paragraphs:
                text = paragraph.text.strip()
                if text and text not in headers:
                    headers.append(text)
            for table in section.header.tables:
                for row in table.rows:
                    text = " | ".join(_clean_cell(cell.text) for cell in row.cells)
                    if text.strip(" |") and text not in headers:
                        headers.append(text)
            for paragraph in section.footer.paragraphs:
                text = paragraph.text.strip()
                if text and text not in footers:
                    footers.append(text)
        except (KeyError, ValueError):
            # Un encabezado dañado no debe impedir leer el cuerpo.
            continue
    return tuple(headers), tuple(footers)


def load_document(path: str | Path) -> DocumentModel:
    """Extrae párrafos, títulos, encabezados y tablas de un archivo .docx."""
    file_path = Path(path).expanduser()

    if not file_path.exists():
        raise DocumentNotFoundError(
            f"No se encontró el archivo '{file_path.name}'. Revisa la ruta."
        )
    if not file_path.is_file():
        raise DocumentNotFoundError(
            f"'{file_path.name}' no es un archivo. Selecciona un documento .docx."
        )
    if file_path.suffix.lower() not in _SUPPORTED_SUFFIXES:
        raise DocumentFormatError(
            f"'{file_path.name}' no es un documento .docx. "
            "Esta versión solo lee archivos de Word en formato .docx "
            "(no .doc, .pdf, .rtf ni imágenes)."
        )

    try:
        document = DocxDocument(str(file_path))
    except PermissionError as exc:
        raise DocumentProtectedError(
            f"No se pudo abrir '{file_path.name}': puede estar abierto en Word "
            "o no tener permisos de lectura."
        ) from exc
    except PackageNotFoundError as exc:
        raise DocumentFormatError(
            f"'{file_path.name}' está dañado, no es un .docx real o está protegido. "
            "Ábrelo en Word y guárdalo de nuevo como .docx."
        ) from exc
    except (KeyError, zipfile.BadZipFile, ValueError, OSError) as exc:
        raise DocumentFormatError(
            f"No se pudo interpretar '{file_path.name}'. El archivo puede estar "
            "dañado, incompleto o protegido."
        ) from exc
    except Exception as exc:  # pragma: no cover - protección adicional
        logger.exception("Error inesperado al abrir el documento")
        raise DocumentFormatError(
            f"No se pudo leer '{file_path.name}'. Comprueba que sea un .docx válido."
        ) from exc

    blocks: list[Paragraph | TableBlock] = []
    paragraph_counter = 0
    table_counter = 0
    order = 0
    heading_path: list[str] = []
    sections: list[Section] = []
    last_text = ""
    warnings: list[str] = []

    body = document.element.body
    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p"):
            paragraph = DocxParagraph(child, document)
            text = re.sub(r"[ \t]+", " ", paragraph.text or "").strip()
            if not text:
                continue
            paragraph_counter += 1
            order += 1
            level = _heading_level(paragraph)
            if level is not None:
                heading_path = heading_path[: level - 1]
                while len(heading_path) < level - 1:
                    heading_path.append("")
                heading_path.append(text)
                while heading_path and not heading_path[-1]:
                    heading_path.pop()
            blocks.append(
                Paragraph(
                    id=f"P{paragraph_counter}",
                    order=order,
                    index=paragraph_counter,
                    text=text,
                    style=(paragraph.style.name if paragraph.style is not None else ""),
                    heading_level=level,
                    heading_path=tuple(part for part in heading_path if part),
                )
            )
            if level is not None:
                sections.append(
                    Section(
                        number=len(sections) + 1,
                        title=text,
                        path=tuple(part for part in heading_path if part),
                        level=level,
                        block_id=f"P{paragraph_counter}",
                    )
                )
            last_text = text
        elif tag == qn("w:tbl"):
            table = DocxTable(child, document)
            rows = _table_rows(table)
            if not rows:
                continue
            table_counter += 1
            order += 1
            caption = ""
            if last_text.lower().startswith(("tabla", "cuadro")):
                caption = last_text
            blocks.append(
                TableBlock(
                    id=f"T{table_counter}",
                    order=order,
                    index=table_counter,
                    rows=rows,
                    heading_path=tuple(part for part in heading_path if part),
                    caption=caption,
                )
            )
            last_text = ""

    header_texts, footer_texts = _section_texts(document)

    try:
        core_title = (document.core_properties.title or "").strip()
    except Exception:  # pragma: no cover - propiedades dañadas
        core_title = ""

    if sections:
        title = sections[0].title
    elif core_title:
        title = core_title
    else:
        title = file_path.stem

    if not blocks:
        try:
            image_count = len(document.inline_shapes)
        except Exception:  # pragma: no cover - documentos dañados
            image_count = 0
        if image_count:
            raise DocumentEmptyError(
                f"'{file_path.name}' no tiene texto legible: parece contener solo "
                f"imágenes ({image_count}). Esta versión no lee texto dentro de imágenes "
                "ni documentos escaneados."
            )
        raise DocumentEmptyError(
            f"'{file_path.name}' no contiene texto legible. "
            "Puede estar vacío o incluir solo elementos gráficos."
        )

    try:
        image_count = len(document.inline_shapes)
        if image_count:
            warnings.append(
                f"El documento contiene {image_count} imagen(es). Esta versión no "
                "lee texto ni tablas que estén dentro de imágenes."
            )
    except Exception:  # pragma: no cover
        pass

    document_model = DocumentModel(
        path=file_path,
        title=title,
        blocks=tuple(blocks),
        sections=tuple(sections),
        header_texts=header_texts,
        footer_texts=footer_texts,
        warnings=tuple(warnings),
    )
    logger.info(
        "Documento leído: %s (%d párrafos, %d tablas, %d caracteres)",
        file_path.name,
        len(document_model.paragraphs),
        len(document_model.tables),
        document_model.char_count,
    )
    return document_model
