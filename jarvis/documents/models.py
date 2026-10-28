"""Modelos de datos del documento de Word."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Paragraph:
    """Párrafo con su posición y el encabezado bajo el que aparece."""

    id: str
    order: int
    index: int
    text: str
    style: str = ""
    heading_level: int | None = None
    heading_path: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        return "parrafo"


@dataclass(frozen=True)
class TableBlock:
    """Tabla completa, con filas y columnas tal como aparecen en el .docx."""

    id: str
    order: int
    index: int
    rows: tuple[tuple[str, ...], ...]
    heading_path: tuple[str, ...] = ()
    caption: str = ""

    @property
    def kind(self) -> str:
        return "tabla"

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    def as_text(self, include_row_numbers: bool = True) -> str:
        if not self.rows:
            return ""
        lines: list[str] = []
        if self.caption:
            lines.append(f"Título de la tabla: {self.caption}")
        header = self.rows[0]
        if header:
            lines.append("Encabezados: " + " | ".join(header))
        start = 1 if len(self.rows) > 1 else 0
        for position, row in enumerate(self.rows[start:], start=start):
            cells = " | ".join(cell for cell in row if cell)
            if not cells:
                continue
            if include_row_numbers:
                lines.append(f"Fila {position + 1}: {cells}")
            else:
                lines.append(cells)
        return "\n".join(lines)

    def rows_as_text(self, start: int, end: int) -> str:
        """Texto de un rango de filas, repitiendo la cabecera si existe."""
        lines: list[str] = []
        if self.caption:
            lines.append(f"Título de la tabla: {self.caption}")
        if self.rows:
            lines.append("Encabezados: " + " | ".join(self.rows[0]))
        for position in range(max(1, start), min(end, len(self.rows))):
            cells = " | ".join(cell for cell in self.rows[position] if cell)
            if cells:
                lines.append(f"Fila {position + 1}: {cells}")
        return "\n".join(lines)


@dataclass(frozen=True)
class Section:
    """Encabezado del documento y su posición dentro de la estructura."""

    number: int
    title: str
    path: tuple[str, ...]
    level: int
    block_id: str

    @property
    def label(self) -> str:
        return " > ".join(self.path) if self.path else self.title


@dataclass(frozen=True)
class DocumentModel:
    """Contenido extraído de un archivo .docx."""

    path: Path
    title: str
    blocks: tuple[Paragraph | TableBlock, ...]
    sections: tuple[Section, ...] = field(default_factory=tuple)
    header_texts: tuple[str, ...] = field(default_factory=tuple)
    footer_texts: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def paragraphs(self) -> tuple[Paragraph, ...]:
        return tuple(block for block in self.blocks if isinstance(block, Paragraph))

    @property
    def tables(self) -> tuple[TableBlock, ...]:
        return tuple(block for block in self.blocks if isinstance(block, TableBlock))

    @property
    def char_count(self) -> int:
        return sum(len(block.text) if isinstance(block, Paragraph) else len(block.as_text()) for block in self.blocks)

    @property
    def block_map(self) -> dict[str, Paragraph | TableBlock]:
        return {block.id: block for block in self.blocks}

    def block_label(self, block_id: str) -> str:
        block = self.block_map.get(block_id)
        if block is None:
            return block_id
        heading = " > ".join(block.heading_path) if block.heading_path else "Sin encabezado"
        kind = "párrafo" if isinstance(block, Paragraph) else "tabla"
        return f"{heading} ({kind} {block.id})"

    def plain_text(self) -> str:
        parts: list[str] = []
        for block in self.blocks:
            if isinstance(block, Paragraph):
                parts.append(block.text)
            else:
                table_text = block.as_text(include_row_numbers=False)
                if table_text:
                    parts.append(table_text)
        return "\n".join(parts)
