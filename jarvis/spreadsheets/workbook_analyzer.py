"""Perfil general del libro: propósito de cada hoja e indicadores posibles.

Es análisis determinista basado en encabezados, tipos y muestras. No inventa
relaciones: solo propone las que se apoyan en columnas con el mismo nombre.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jarvis.spreadsheets.models import (
    ColumnModel,
    SheetModel,
    WorkbookModel,
    normalize_text,
)
from jarvis.spreadsheets.sheet_profiler import (
    format_number,
    format_value,
    parse_date,
    parse_number,
)

_PURPOSE_TEXT = {
    "tareas": "registros de tareas o actividades, con estados, responsables y fechas",
    "finanzas": "información económica: ingresos, gastos, importes o presupuesto",
    "inventario": "productos, cantidades, precios o existencias",
    "contactos": "personas o entidades de contacto",
    "datos": "datos tabulares de propósito general",
}


@dataclass(frozen=True)
class SheetProfile:
    name: str
    purpose: str
    description: str
    records: int
    columns: tuple[str, ...]
    key_columns: tuple[str, ...]
    numeric_columns: tuple[str, ...]
    date_columns: tuple[str, ...]
    category_columns: tuple[str, ...]
    formula_count: int
    tables: tuple[str, ...]
    indicators: tuple[str, ...]
    hidden: bool = False


@dataclass(frozen=True)
class WorkbookProfile:
    name: str
    title: str
    sheets: tuple[SheetProfile, ...]
    relationships: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def visible(self) -> tuple[SheetProfile, ...]:
        return tuple(sheet for sheet in self.sheets if not sheet.hidden)

    def sheet(self, name: str) -> SheetProfile | None:
        target = normalize_text(name)
        for sheet in self.sheets:
            if normalize_text(sheet.name) == target:
                return sheet
        for sheet in self.sheets:
            if target and target in normalize_text(sheet.name):
                return sheet
        return None

    def summary_text(self) -> str:
        visible = self.visible
        lines = [
            f"El libro «{self.name}» tiene {len(visible)} hojas visibles"
            + (f" y {len(self.sheets) - len(visible)} ocultas" if len(self.sheets) > len(visible) else "")
            + "."
        ]
        for sheet in visible:
            lines.append(f"  - {sheet.description}")
        if self.relationships:
            lines.append("Relaciones posibles: " + "; ".join(self.relationships[:4]) + ".")
        return "\n".join(lines)


def _is_category(column: ColumnModel) -> bool:
    return column.kind in {"text", "bool"} and 0 < column.unique <= 30


def _key_columns(sheet: SheetModel) -> tuple[str, ...]:
    keys: list[str] = []
    for column in sheet.columns:
        name = normalize_text(column.name)
        if name in {"id", "codigo", "código", "nombre", "descripcion", "descripción"}:
            keys.append(column.name)
    if not keys and sheet.columns:
        keys.append(sheet.columns[0].name)
    return tuple(keys[:3])


def _indicators(sheet: SheetModel) -> tuple[str, ...]:
    indicators: list[str] = []
    numeric = [column for column in sheet.columns if column.is_numeric]
    dates = [column for column in sheet.columns if column.is_date]
    categories = [column for column in sheet.columns if _is_category(column)]
    for column in numeric[:3]:
        indicators.append(f"suma y promedio de «{column.name}»")
    for column in dates[:2]:
        indicators.append(f"vencimientos y agrupación por mes según «{column.name}»")
    for column in categories[:3]:
        indicators.append(f"conteo agrupado por «{column.name}»")
    if sheet.formula_count:
        indicators.append(f"explicación de {sheet.formula_count} fórmulas")
    return tuple(indicators[:8])


def profile_sheet(sheet: SheetModel) -> SheetProfile:
    purpose = sheet.purpose
    description = (
        f"«{sheet.name}»"
        + (" (oculta)" if sheet.hidden else "")
        + f": {sheet.records} registros, {len(sheet.columns)} columnas; "
        + _PURPOSE_TEXT.get(purpose, _PURPOSE_TEXT["datos"])
        + "."
    )
    return SheetProfile(
        name=sheet.name,
        purpose=purpose,
        description=description,
        records=sheet.records,
        columns=tuple(column.name for column in sheet.columns),
        key_columns=_key_columns(sheet),
        numeric_columns=tuple(
            column.name for column in sheet.columns if column.is_numeric
        ),
        date_columns=tuple(
            column.name for column in sheet.columns if column.is_date
        ),
        category_columns=tuple(
            column.name for column in sheet.columns if _is_category(column)
        ),
        formula_count=sheet.formula_count,
        tables=tuple(table.name for table in sheet.tables),
        indicators=_indicators(sheet),
        hidden=sheet.hidden,
    )


def profile_workbook(workbook: WorkbookModel) -> WorkbookProfile:
    profiles = tuple(profile_sheet(sheet) for sheet in workbook.sheets)
    relationships: list[str] = []
    for index, first in enumerate(profiles):
        first_columns = {normalize_text(column) for column in first.columns}
        for second in profiles[index + 1 :]:
            shared = first_columns & {
                normalize_text(column) for column in second.columns
            }
            interesting = {
                column
                for column in shared
                if column and column not in {"id", "fila", "fecha", "total", "importe"}
            }
            if interesting:
                relationships.append(
                    f"«{first.name}» y «{second.name}» comparten "
                    + ", ".join(sorted(interesting)[:3])
                )
    return WorkbookProfile(
        name=workbook.name,
        title=workbook.title,
        sheets=profiles,
        relationships=tuple(relationships[:6]),
        warnings=workbook.warnings,
    )


def summarize_sheet(sheet: SheetModel) -> str:
    """Resumen local de una hoja, con datos calculados y sin IA."""
    lines = [
        f"La hoja «{sheet.name}» contiene {sheet.records} registros y "
        f"{len(sheet.columns)} columnas."
    ]
    if sheet.header_row:
        lines.append(f"Los encabezados están en la fila {sheet.header_row}.")
    numeric = [column for column in sheet.columns if column.is_numeric]
    for column in numeric[:3]:
        values = [
            parse_number(value)
            for value in (
                sheet.rows[index][column.index]
                if column.index < len(sheet.rows[index])
                else None
                for index in range(len(sheet.rows))
            )
        ]
        numbers = [value for value in values if value is not None]
        if numbers:
            lines.append(
                f"«{column.name}»: suma {format_number(sum(numbers))}, "
                f"promedio {format_number(sum(numbers) / len(numbers))}, "
                f"mínimo {format_number(min(numbers))} y "
                f"máximo {format_number(max(numbers))}."
            )
    dates = [column for column in sheet.columns if column.is_date]
    for column in dates[:2]:
        parsed = [
            parse_date(
                sheet.rows[index][column.index]
                if column.index < len(sheet.rows[index])
                else None
            )
            for index in range(len(sheet.rows))
        ]
        real = [value for value in parsed if value is not None]
        if real:
            lines.append(
                f"«{column.name}» va del {min(real).strftime('%d/%m/%Y')} al "
                f"{max(real).strftime('%d/%m/%Y')}."
            )
    categories = [column for column in sheet.columns if _is_category(column)]
    for column in categories[:3]:
        counts: dict[str, int] = {}
        for index in range(len(sheet.rows)):
            value = (
                sheet.rows[index][column.index]
                if column.index < len(sheet.rows[index])
                else None
            )
            label = format_value(value) or "(vacío)"
            counts[label] = counts.get(label, 0) + 1
        top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        lines.append(
            f"«{column.name}»: "
            + ", ".join(f"{label} ({count})" for label, count in top)
            + "."
        )
    if sheet.formula_count:
        lines.append(f"Detecté {sheet.formula_count} fórmulas en esta hoja.")
    if sheet.tables:
        lines.append(
            "Tablas de Excel: "
            + ", ".join(table.describe() for table in sheet.tables)
            + "."
        )
    if sheet.merged_ranges:
        lines.append(
            f"Hay {len(sheet.merged_ranges)} rangos combinados; pueden afectar "
            "a encabezados o totales."
        )
    if sheet.truncated:
        lines.append(
            "La hoja supera los límites configurados: este resumen es parcial."
        )
    return "\n".join(lines)


def format_profile(profile: WorkbookProfile) -> str:
    return profile.summary_text()


__all__ = [
    "SheetProfile",
    "WorkbookProfile",
    "format_profile",
    "profile_sheet",
    "profile_workbook",
    "summarize_sheet",
]
