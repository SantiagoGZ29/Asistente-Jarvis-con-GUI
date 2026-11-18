"""Modelos de datos para libros de Excel y resultados de análisis.

El objetivo es conservar la referencia original de cada dato (hoja, celda,
rango, tabla y fila) para que las respuestas puedan justificarse sin inventar
posiciones. Los modelos son de solo lectura: el cargador nunca guarda el libro.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable


def normalize_text(text: Any) -> str:
    """Minúsculas, sin acentos y con espacios normalizados."""
    value = str(text or "")
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


def column_letter(index: int) -> str:
    """Índice 0-based a letra de columna de Excel (0 -> A, 26 -> AA)."""
    if index < 0:
        raise ValueError("El índice de columna no puede ser negativo.")
    letters: list[str] = []
    current = index + 1
    while current:
        current, remainder = divmod(current - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def cell_reference(row: int, column: int) -> str:
    """Referencia A1 para fila/columna 1-based."""
    return f"{column_letter(column - 1)}{row}"


def is_date_value(value: Any) -> bool:
    return isinstance(value, (date, datetime))


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


@dataclass(frozen=True)
class RangeRef:
    """Rango rectangular de una hoja, con nombre de tabla opcional."""

    sheet: str
    min_col: int
    min_row: int
    max_col: int
    max_row: int
    table: str = ""

    @property
    def ref(self) -> str:
        if self.max_row < self.min_row or self.max_col < self.min_col:
            return ""
        start = cell_reference(self.min_row, self.min_col)
        end = cell_reference(self.max_row, self.max_col)
        return start if start == end else f"{start}:{end}"

    @property
    def full(self) -> str:
        base = f"{self.sheet}!{self.ref}" if self.ref else self.sheet
        return f"{base} ({self.table})" if self.table else base

    def describe(self) -> str:
        suffix = f", tabla {self.table}" if self.table else ""
        return f"hoja {self.sheet}, rango {self.ref}{suffix}"


@dataclass(frozen=True)
class ColumnModel:
    """Columna de una hoja con su tipo inferido y estadísticas básicas."""

    name: str
    letter: str
    index: int
    kind: str = "empty"
    number_format: str = ""
    empty: int = 0
    total: int = 0
    unique: int = 0
    formula_count: int = 0
    samples: tuple[Any, ...] = ()

    @property
    def is_numeric(self) -> bool:
        return self.kind in {"number", "percentage"}

    @property
    def is_date(self) -> bool:
        return self.kind == "date"

    @property
    def is_percentage(self) -> bool:
        return self.kind == "percentage"

    @property
    def is_empty(self) -> bool:
        return self.kind == "empty"


@dataclass(frozen=True)
class TableModel:
    """Tabla estructurada de Excel (ListObject)."""

    name: str
    range: RangeRef
    headers: tuple[str, ...] = ()

    def describe(self) -> str:
        return f"{self.name} ({self.range.ref})"


@dataclass
class SheetModel:
    """Contenido extraído de una hoja de cálculo."""

    name: str
    index: int
    hidden: bool = False
    header_row: int | None = None
    header_confidence: float = 0.0
    header_candidates: tuple[int, ...] = ()
    headers: tuple[str, ...] = ()
    columns: tuple[ColumnModel, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    row_numbers: tuple[int, ...] = ()
    data_range: RangeRef | None = None
    tables: tuple[TableModel, ...] = ()
    merged_ranges: tuple[str, ...] = ()
    formulas: dict[str, str] = field(default_factory=dict)
    formula_values: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    purpose: str = "datos"
    dimensions: str = ""
    empty_rows: int = 0

    @property
    def records(self) -> int:
        """Filas con datos; las filas totalmente vacías no cuentan."""
        return sum(
            1
            for row in self.rows
            if any(value not in (None, "") for value in row)
        )

    @property
    def formula_count(self) -> int:
        return len(self.formulas)

    @property
    def table(self) -> TableModel | None:
        return self.tables[0] if self.tables else None

    def column(self, name: str) -> tuple[ColumnModel | None, tuple[ColumnModel, ...]]:
        """Devuelve (columna exacta, candidatas) con coincidencia difusa."""
        target = normalize_text(name)
        if not target:
            return None, ()
        exact = [
            column
            for column in self.columns
            if normalize_text(column.name) == target
        ]
        if len(exact) == 1:
            return exact[0], ()
        if len(exact) > 1:
            return None, tuple(exact)
        partial = [
            column
            for column in self.columns
            if target in normalize_text(column.name)
            or normalize_text(column.name) in target
        ]
        if len(partial) == 1:
            return partial[0], ()
        return None, tuple(partial)

    def value_at(self, row_number: int, column_index: int) -> Any:
        """Valor de una fila Excel (1-based) y columna 0-based."""
        try:
            position = self.row_numbers.index(row_number)
        except ValueError:
            return None
        if 0 <= column_index < len(self.rows[position]):
            return self.rows[position][column_index]
        return None

    def formula_for(self, reference: str) -> str | None:
        return self.formulas.get(reference.strip().upper())

    def cached_value(self, reference: str) -> Any:
        return self.formula_values.get(reference.strip().upper())

    def as_dicts(self, limit: int | None = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for position, values in enumerate(self.rows):
            if limit is not None and position >= limit:
                break
            if not any(value not in (None, "") for value in values):
                continue
            record = {"_fila": self.row_numbers[position]}
            for index, column in enumerate(self.columns):
                record[column.name] = values[index] if index < len(values) else None
            result.append(record)
        return result

    def describe(self) -> str:
        hidden = " (oculta)" if self.hidden else ""
        return (
            f"{self.name}{hidden}: {self.records} registros, "
            f"{len(self.columns)} columnas, {self.formula_count} fórmulas"
        )


@dataclass
class WorkbookModel:
    """Libro completo, con todas sus hojas y avisos de carga."""

    path: Path
    sheets: tuple[SheetModel, ...]
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    title: str = ""
    active_sheet: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def visible_sheets(self) -> tuple[SheetModel, ...]:
        return tuple(sheet for sheet in self.sheets if not sheet.hidden)

    @property
    def hidden_sheets(self) -> tuple[SheetModel, ...]:
        return tuple(sheet for sheet in self.sheets if sheet.hidden)

    @property
    def formula_count(self) -> int:
        return sum(sheet.formula_count for sheet in self.visible_sheets)

    @property
    def records(self) -> int:
        return sum(sheet.records for sheet in self.visible_sheets)

    @property
    def columns(self) -> int:
        return sum(len(sheet.columns) for sheet in self.visible_sheets)

    @property
    def tables(self) -> tuple[TableModel, ...]:
        return tuple(table for sheet in self.sheets for table in sheet.tables)

    def sheet(self, name: str) -> tuple[SheetModel | None, tuple[SheetModel, ...]]:
        target = normalize_text(name)
        if not target:
            return None, ()
        exact = [
            sheet for sheet in self.sheets if normalize_text(sheet.name) == target
        ]
        if len(exact) == 1:
            return exact[0], ()
        if len(exact) > 1:
            return None, tuple(exact)
        partial = [
            sheet
            for sheet in self.sheets
            if target in normalize_text(sheet.name)
            or normalize_text(sheet.name) in target
        ]
        if len(partial) == 1:
            return partial[0], ()
        return None, tuple(partial)

    def first_sheet(self, *, include_hidden: bool = False) -> SheetModel | None:
        if self.active_sheet:
            active, _ = self.sheet(self.active_sheet)
            if active is not None and (include_hidden or not active.hidden):
                return active
        for sheet in self.sheets:
            if include_hidden or not sheet.hidden:
                return sheet
        return None


# ----------------------------------------------------------------------
# Información para la interfaz
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class SheetInfo:
    name: str
    hidden: bool
    rows: int
    columns: int
    formulas: int
    tables: int
    purpose: str = ""


@dataclass(frozen=True)
class SpreadsheetInfo:
    """Datos que muestra la tarjeta del libro activo."""

    path: str
    name: str
    title: str
    status: str
    sheets: tuple[SheetInfo, ...] = ()
    hidden_sheets: tuple[str, ...] = ()
    rows: int = 0
    columns: int = 0
    formulas: int = 0
    tables: int = 0
    current_sheet: str = ""
    opened: bool = False
    truncated: bool = False
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_model(
        cls,
        workbook: WorkbookModel,
        *,
        status: str = "LISTO",
        opened: bool = False,
        current_sheet: str = "",
    ) -> "SpreadsheetInfo":
        return cls(
            path=str(workbook.path),
            name=workbook.name,
            title=workbook.title or workbook.path.stem,
            status=status,
            sheets=tuple(
                SheetInfo(
                    name=sheet.name,
                    hidden=sheet.hidden,
                    rows=sheet.records,
                    columns=len(sheet.columns),
                    formulas=sheet.formula_count,
                    tables=len(sheet.tables),
                    purpose=sheet.purpose,
                )
                for sheet in workbook.sheets
            ),
            hidden_sheets=tuple(sheet.name for sheet in workbook.hidden_sheets),
            rows=workbook.records,
            columns=workbook.columns,
            formulas=workbook.formula_count,
            tables=len(workbook.tables),
            current_sheet=current_sheet or workbook.active_sheet,
            opened=opened,
            truncated=workbook.truncated,
            warnings=workbook.warnings,
        )


@dataclass(frozen=True)
class Metric:
    label: str
    value: str


@dataclass(frozen=True)
class AnalysisInfo:
    """Resultado listo para el panel de análisis de la ventana."""

    title: str
    kind: str = "analysis"
    metrics: tuple[Metric, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    sources: tuple[str, ...] = ()
    alerts: tuple[str, ...] = ()
    note: str = ""
    sheet: str = ""
    options: tuple[str, ...] = ()


__all__ = [
    "AnalysisInfo",
    "ColumnModel",
    "Metric",
    "RangeRef",
    "SheetInfo",
    "SheetModel",
    "SpreadsheetInfo",
    "TableModel",
    "WorkbookModel",
    "as_date",
    "cell_reference",
    "column_letter",
    "is_date_value",
    "normalize_text",
]
