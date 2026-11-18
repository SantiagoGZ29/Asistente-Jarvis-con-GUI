"""Diagnóstico de calidad de datos de una hoja, sin modificar nada.

Los avisos son heurísticos y honestos: describen lo observado, no corrigen el
libro ni afirman que un dato sea incorrecto sin contexto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jarvis.spreadsheets.models import ColumnModel, SheetModel, normalize_text
from jarvis.spreadsheets.sheet_profiler import (
    format_value,
    is_date_like,
    is_number_like,
    parse_date,
    parse_number,
)

KEY_WORDS = (
    "id",
    "codigo",
    "código",
    "nombre",
    "descripcion",
    "descripción",
    "fecha",
    "estado",
    "responsable",
    "importe",
    "total",
    "correo",
    "email",
)


@dataclass(frozen=True)
class QualityIssue:
    problem: str
    sheet: str
    column: str = ""
    count: int = 0
    impact: str = ""
    recommendation: str = ""
    reference: str = ""

    def describe(self) -> str:
        where = f" en «{self.sheet}»"
        if self.column:
            where += f", columna «{self.column}»"
        text = f"{self.problem}{where}: {self.count} caso(s)."
        if self.impact:
            text += f" Impacto: {self.impact}."
        if self.recommendation:
            text += f" Recomendación: {self.recommendation}."
        return text


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _column_values(sheet: SheetModel, column: ColumnModel) -> list[Any]:
    return [
        row[column.index] if column.index < len(row) else None
        for row in sheet.rows
        if any(value not in (None, "") for value in row)
    ]


def diagnose_sheet(sheet: SheetModel) -> tuple[QualityIssue, ...]:
    issues: list[QualityIssue] = []
    issues.extend(_empty_key_cells(sheet))
    issues.extend(_duplicate_records(sheet))
    issues.extend(_text_numbers(sheet))
    issues.extend(_text_dates(sheet))
    issues.extend(_repeated_headers(sheet))
    issues.extend(_unnamed_columns(sheet))
    issues.extend(_empty_rows(sheet))
    issues.extend(_mixed_columns(sheet))
    return tuple(issues)


def _empty_key_cells(sheet: SheetModel) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for column in sheet.columns:
        name = normalize_text(column.name)
        if not any(word in name for word in KEY_WORDS):
            continue
        values = _column_values(sheet, column)
        empty = sum(1 for value in values if _is_blank(value))
        if empty:
            issues.append(
                QualityIssue(
                    problem="Celdas vacías en una columna importante",
                    sheet=sheet.name,
                    column=column.name,
                    count=empty,
                    impact="los filtros y conteos pueden excluir esos registros",
                    recommendation="revisa si faltan datos o si la fila está incompleta",
                    reference=f"{column.letter}",
                )
            )
    return issues


def _duplicate_records(sheet: SheetModel) -> list[QualityIssue]:
    key_columns = [
        column
        for column in sheet.columns
        if normalize_text(column.name) in {"id", "codigo", "código", "nombre", "correo", "email"}
    ]
    if not key_columns:
        key_columns = list(sheet.columns[:1])
    issues: list[QualityIssue] = []
    for column in key_columns:
        values = [
            normalize_text(value)
            for value in _column_values(sheet, column)
            if not _is_blank(value)
        ]
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        repeated = sum(1 for count in counts.values() if count > 1)
        if repeated:
            issues.append(
                QualityIssue(
                    problem="Registros duplicados",
                    sheet=sheet.name,
                    column=column.name,
                    count=repeated,
                    impact="pueden inflar conteos, sumas o promedios",
                    recommendation="confirma si son duplicados reales o registros distintos",
                    reference=f"{column.letter}",
                )
            )
    return issues


def _text_numbers(sheet: SheetModel) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for column in sheet.columns:
        if column.kind == "empty":
            continue
        values = _column_values(sheet, column)
        numeric_text = 0
        for value in values:
            if isinstance(value, str) and is_number_like(value):
                numeric_text += 1
        if numeric_text >= max(2, len([v for v in values if not _is_blank(v)]) // 2):
            issues.append(
                QualityIssue(
                    problem="Números guardados como texto",
                    sheet=sheet.name,
                    column=column.name,
                    count=numeric_text,
                    impact="las sumas y promedios pueden ignorarlos",
                    recommendation="convierte esos valores a número en Excel",
                    reference=f"{column.letter}",
                )
            )
    return issues


def _text_dates(sheet: SheetModel) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for column in sheet.columns:
        if column.kind == "empty":
            continue
        values = _column_values(sheet, column)
        date_text = sum(
            1
            for value in values
            if isinstance(value, str) and is_date_like(value)
        )
        present = len([value for value in values if not _is_blank(value)])
        if date_text >= 2 and date_text >= present // 2:
            issues.append(
                QualityIssue(
                    problem="Fechas guardadas como texto",
                    sheet=sheet.name,
                    column=column.name,
                    count=date_text,
                    impact="no se pueden comparar ni agrupar por período con fiabilidad",
                    recommendation="aplica un formato de fecha real en Excel",
                    reference=f"{column.letter}",
                )
            )
    return issues


def _repeated_headers(sheet: SheetModel) -> list[QualityIssue]:
    counts: dict[str, int] = {}
    for header in sheet.headers:
        key = normalize_text(header)
        if key:
            counts[key] = counts.get(key, 0) + 1
    repeated = [key for key, count in counts.items() if count > 1]
    if not repeated:
        return []
    return [
        QualityIssue(
            problem="Encabezados repetidos",
            sheet=sheet.name,
            column=", ".join(repeated),
            count=len(repeated),
            impact="puede haber columnas duplicadas o mal nombradas",
            recommendation="renombra cada columna con un nombre único",
        )
    ]


def _unnamed_columns(sheet: SheetModel) -> list[QualityIssue]:
    unnamed = [
        column
        for column in sheet.columns
        if normalize_text(column.name).startswith("columna ")
    ]
    if not unnamed:
        return []
    return [
        QualityIssue(
            problem="Columnas sin nombre",
            sheet=sheet.name,
            column=", ".join(column.letter for column in unnamed),
            count=len(unnamed),
            impact="es difícil saber qué representan esos datos",
            recommendation="añade un encabezado claro en la fila de títulos",
        )
    ]


def _empty_rows(sheet: SheetModel) -> list[QualityIssue]:
    if not sheet.empty_rows:
        return []
    return [
        QualityIssue(
            problem="Filas completamente vacías dentro de los datos",
            sheet=sheet.name,
            count=sheet.empty_rows,
            impact="pueden cortar rangos o confundir agrupaciones",
            recommendation="elimina o rellena esas filas si forman parte de la tabla",
        )
    ]


def _mixed_columns(sheet: SheetModel) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for column in sheet.columns:
        if column.kind != "mixed":
            continue
        values = [value for value in _column_values(sheet, column) if not _is_blank(value)]
        kinds: dict[str, int] = {}
        for value in values:
            if parse_date(value) is not None:
                kinds["fecha"] = kinds.get("fecha", 0) + 1
            elif parse_number(value) is not None:
                kinds["número"] = kinds.get("número", 0) + 1
            elif isinstance(value, str):
                kinds["texto"] = kinds.get("texto", 0) + 1
        if len(kinds) > 1:
            detail = ", ".join(f"{kind}: {count}" for kind, count in kinds.items())
            issues.append(
                QualityIssue(
                    problem="Tipos de datos mezclados",
                    sheet=sheet.name,
                    column=column.name,
                    count=len(values),
                    impact=f"la columna mezcla {detail}",
                    recommendation="unifica el tipo de dato de la columna",
                    reference=f"{column.letter}",
                )
            )
    return issues


def diagnose_workbook(workbook) -> tuple[QualityIssue, ...]:
    issues: list[QualityIssue] = []
    for sheet in workbook.sheets:
        if sheet.hidden or not sheet.records:
            continue
        issues.extend(diagnose_sheet(sheet))
    return tuple(issues)


def format_issues(issues: tuple[QualityIssue, ...] | list[QualityIssue]) -> str:
    if not issues:
        return "No encontré problemas evidentes de calidad de datos en las hojas visibles."
    lines = [f"Encontré {len(issues)} posibles problemas de calidad:"]
    for issue in issues[:12]:
        lines.append("  - " + issue.describe())
    if len(issues) > 12:
        lines.append(f"  - y {len(issues) - 12} problemas más.")
    return "\n".join(lines)


__all__ = [
    "QualityIssue",
    "diagnose_sheet",
    "diagnose_workbook",
    "format_issues",
    "format_value",
]
