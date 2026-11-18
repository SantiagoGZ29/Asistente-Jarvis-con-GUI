"""Carga segura de libros de Excel con openpyxl.

Se hacen dos lecturas:

* ``data_only=False`` para fórmulas, tablas, celdas combinadas y formatos.
* ``data_only=True`` para los valores calculados que Excel haya guardado.

Nunca se guarda el archivo, no se ejecutan macros y no se sigue ningún enlace.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.cell import coordinate_from_string, range_boundaries
from openpyxl.utils.exceptions import InvalidFileException

from jarvis.core.errors import (
    SpreadsheetEmptyError,
    SpreadsheetFormatError,
    SpreadsheetLimitError,
    SpreadsheetProtectedError,
)
from jarvis.core.logging_setup import get_logger
from jarvis.spreadsheets.models import (
    RangeRef,
    SheetModel,
    TableModel,
    WorkbookModel,
    normalize_text,
)
from jarvis.spreadsheets.sheet_profiler import build_sheet

logger = get_logger("workbook_loader")

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm")
OPTIONAL_EXTENSIONS = (".xls", ".xlsb")


@dataclass(frozen=True)
class LoadLimits:
    max_file_mb: float = 25.0
    max_rows: int = 10_000
    max_columns: int = 60
    max_cells: int = 300_000
    header_scan_rows: int = 12
    small_file_mb: float = 12.0
    max_uncompressed_mb: float = 400.0


class WorkbookLoader:
    """Carga y perfila un libro sin modificarlo."""

    def __init__(self, limits: LoadLimits | None = None) -> None:
        self.limits = limits or LoadLimits()

    def load(self, path: Path | str) -> WorkbookModel:
        target = Path(path)
        if not target.is_file():
            raise SpreadsheetErrorNotFound(target)
        suffix = target.suffix.casefold()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise SpreadsheetFormatError(
                f"«{target.name}» no es un libro .xlsx o .xlsm. "
                "Si es .xls o .xlsb, ábrelo en Excel y guárdalo como .xlsx."
            )
        self._check_size(target)
        self._check_zip(target)

        try:
            workbook = load_workbook(
                filename=str(target),
                data_only=False,
                read_only=False,
                keep_links=False,
                keep_vba=False,
            )
        except PermissionError as exc:
            raise SpreadsheetProtectedError(
                "El libro está abierto en Excel o no tengo permiso para leerlo. "
                "Ciérralo en Excel y vuelve a intentarlo."
            ) from exc
        except InvalidFileException as exc:
            raise SpreadsheetFormatError(
                "El archivo no es un libro de Excel válido. "
                "Ábrelo en Excel, guárdalo como .xlsx y vuelve a intentarlo."
            ) from exc
        except Exception as exc:
            raise SpreadsheetFormatError(
                "No pude abrir el libro. Comprueba que no esté dañado, "
                "protegido con contraseña o abierto exclusivamente en Excel."
            ) from exc

        try:
            return self._read(workbook, target)
        finally:
            try:
                workbook.close()
            except Exception:  # pragma: no cover - cierre defensivo
                pass

    # ------------------------------------------------------------------
    # Comprobaciones previas
    # ------------------------------------------------------------------
    def _check_size(self, path: Path) -> None:
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.limits.max_file_mb:
            raise SpreadsheetLimitError(
                f"El libro ocupa {size_mb:.1f} MB y el límite es "
                f"{self.limits.max_file_mb:.0f} MB. Puedes aumentar "
                "JARVIS_SPREADSHEET_MAX_FILE_MB o analizar una copia más pequeña."
            )

    def _check_zip(self, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 12_000:
                    raise SpreadsheetLimitError(
                        "El libro contiene demasiados componentes internos "
                        "para analizarlo con seguridad."
                    )
                total = sum(entry.file_size for entry in entries)
                if total > self.limits.max_uncompressed_mb * 1024 * 1024:
                    raise SpreadsheetLimitError(
                        "El contenido descomprimido del libro supera el límite "
                        "de seguridad. Analiza una copia más pequeña."
                    )
        except zipfile.BadZipFile as exc:
            raise SpreadsheetFormatError(
                "El archivo no es un .xlsx válido o está dañado."
            ) from exc

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------
    def _read(self, workbook: Any, path: Path) -> WorkbookModel:
        values_workbook = load_workbook(
            filename=str(path),
            data_only=True,
            read_only=True,
            keep_links=False,
            keep_vba=False,
        )
        sheets: list[SheetModel] = []
        warnings: list[str] = []
        truncated_any = False
        try:
            for index, worksheet in enumerate(workbook.worksheets):
                values_sheet = values_workbook[worksheet.title]
                sheet = self._read_sheet(
                    worksheet,
                    values_sheet,
                    index=index,
                )
                sheets.append(sheet)
                if sheet.truncated:
                    truncated_any = True
                warnings.extend(sheet.warnings)
        finally:
            try:
                values_workbook.close()
            except Exception:  # pragma: no cover
                pass

        visible_with_data = [
            sheet
            for sheet in sheets
            if not sheet.hidden and sheet.rows
        ]
        if not visible_with_data:
            raise SpreadsheetEmptyError(
                "El libro no contiene datos legibles en sus hojas visibles. "
                "Comprueba que no esté vacío o que las hojas no estén ocultas."
            )

        active = getattr(workbook, "active", None)
        active_name = getattr(active, "title", "") if active is not None else ""
        title = ""
        try:
            title = (workbook.properties.title or "").strip()
        except Exception:  # pragma: no cover - propiedades corruptas
            title = ""

        return WorkbookModel(
            path=path,
            sheets=tuple(sheets),
            warnings=tuple(dict.fromkeys(warnings)),
            truncated=truncated_any,
            title=title,
            active_sheet=active_name,
        )

    def _read_sheet(self, worksheet: Any, values_sheet: Any, *, index: int) -> SheetModel:
        limits = self.limits
        hidden = getattr(worksheet, "sheet_state", "visible") != "visible"
        warnings: list[str] = []
        truncated = False

        max_row = _safe_dimension(worksheet, "max_row", limits.max_rows)
        max_col = _safe_dimension(worksheet, "max_column", limits.max_columns)
        if max_row > limits.max_rows or max_col > limits.max_columns:
            truncated = True
            warnings.append(
                f"La hoja «{worksheet.title}» supera el límite de "
                f"{limits.max_rows} filas o {limits.max_columns} columnas; "
                "se analizó solo esa parte."
            )
        max_row = min(max_row, limits.max_rows)
        max_col = min(max_col, limits.max_columns)
        if max_row * max_col > limits.max_cells:
            allowed_rows = max(1, limits.max_cells // max(1, max_col))
            if allowed_rows < max_row:
                max_row = allowed_rows
                truncated = True
                warnings.append(
                    f"La hoja «{worksheet.title}» se recortó a {max_row} filas "
                    "por el límite de celdas."
                )

        formulas, formats, formula_counts = self._read_formulas(
            worksheet, max_row=max_row, max_col=max_col
        )
        tables = self._read_tables(worksheet, max_col=max_col)
        merges: tuple[str, ...] = ()
        try:
            merges = tuple(
                str(item) for item in list(worksheet.merged_cells.ranges)[:200]
            )
        except Exception:  # pragma: no cover - hojas con metadatos raros
            merges = ()

        rows, row_numbers, values_truncated = self._read_values(
            values_sheet, max_row=max_row, max_col=max_col
        )
        if values_truncated:
            truncated = True

        # Recorta filas/columnas totalmente vacías del final.
        while rows and not any(value not in (None, "") for value in rows[-1]):
            rows.pop()
            row_numbers.pop()
        width = 0
        for row in rows:
            for position in range(len(row) - 1, -1, -1):
                if row[position] not in (None, ""):
                    width = max(width, position + 1)
                    break
        if width:
            max_col = min(max_col, width)
            rows = [tuple(row[:max_col]) for row in rows]

        formula_values: dict[str, Any] = {}
        for reference in formulas:
            row_number, column_index = _coordinate(reference)
            value = None
            if 0 < row_number <= len(rows):
                row = rows[row_number - 1]
                if 0 < column_index <= len(row):
                    value = row[column_index - 1]
            formula_values[reference] = value

        sheet = build_sheet(
            name=worksheet.title,
            index=index,
            rows=rows,
            row_numbers=row_numbers,
            hidden=hidden,
            column_formats=formats,
            formula_counts=formula_counts,
            header_scan_rows=limits.header_scan_rows,
            tables=tables,
            merged_ranges=merges,
            formulas=formulas,
            formula_values=formula_values,
            truncated=truncated,
            warnings=tuple(warnings),
        )
        if sheet.header_candidates:
            sheet.warnings = sheet.warnings + (
                f"Hay varias filas que podrían ser encabezado en «{sheet.name}» "
                f"(filas {', '.join(str(row) for row in sheet.header_candidates)}). "
                "Se usó la más probable.",
            )
        if hidden:
            sheet.warnings = sheet.warnings + (
                f"La hoja «{sheet.name}» está oculta; no se mezclará en los "
                "análisis ordinarios.",
            )
        return sheet

    def _read_values(
        self,
        worksheet: Any,
        *,
        max_row: int,
        max_col: int,
    ) -> tuple[list[tuple[Any, ...]], list[int], bool]:
        rows: list[tuple[Any, ...]] = []
        row_numbers: list[int] = []
        truncated = False
        try:
            iterator = worksheet.iter_rows(
                min_row=1,
                max_row=max_row,
                max_col=max_col,
                values_only=True,
            )
        except Exception:  # pragma: no cover - hoja corrupta
            return rows, row_numbers, True
        for position, row in enumerate(iterator, start=1):
            if position > max_row:
                truncated = True
                break
            # Se conservan las filas vacías intermedias para que la posición
            # de la lista coincida con el número real de fila de Excel. Las
            # filas vacías del final se recortan después.
            values = tuple(row)
            rows.append(values)
            row_numbers.append(position)
        return rows, row_numbers, truncated

    def _read_formulas(
        self,
        worksheet: Any,
        *,
        max_row: int,
        max_col: int,
    ) -> tuple[dict[str, str], list[str], list[int]]:
        formulas: dict[str, str] = {}
        format_counts: list[dict[str, int]] = [{} for _ in range(max_col)]
        formula_counts = [0] * max_col
        try:
            iterator = worksheet.iter_rows(
                min_row=1, max_row=max_row, max_col=max_col
            )
        except Exception:  # pragma: no cover
            return formulas, [""] * max_col, formula_counts
        for row in iterator:
            for cell in row:
                try:
                    coordinate = str(cell.coordinate).upper()
                except Exception:  # pragma: no cover
                    continue
                value = getattr(cell, "value", None)
                is_formula = getattr(cell, "data_type", "") == "f" or (
                    isinstance(value, str) and value.startswith("=")
                )
                if is_formula:
                    formulas[coordinate] = str(value)
                    column_index = getattr(cell, "column", 1) - 1
                    if 0 <= column_index < len(formula_counts):
                        formula_counts[column_index] += 1
                if value not in (None, ""):
                    column_index = getattr(cell, "column", 1) - 1
                    if 0 <= column_index < len(format_counts):
                        number_format = getattr(cell, "number_format", "") or ""
                        if number_format and number_format != "General":
                            bucket = format_counts[column_index]
                            bucket[number_format] = bucket.get(number_format, 0) + 1
        formats: list[str] = []
        for bucket in format_counts:
            if not bucket:
                formats.append("")
                continue
            formats.append(max(bucket.items(), key=lambda item: item[1])[0])
        return formulas, formats, formula_counts

    def _read_tables(self, worksheet: Any, *, max_col: int) -> tuple[TableModel, ...]:
        tables: list[TableModel] = []
        try:
            raw_tables = list(worksheet.tables.values())
        except Exception:  # pragma: no cover - modo de solo lectura
            return ()
        for raw in raw_tables[:50]:
            name = str(getattr(raw, "name", "") or "Tabla")
            ref = str(getattr(raw, "ref", "") or "")
            if not ref:
                continue
            try:
                min_col, min_row, max_col_ref, max_row = range_boundaries(ref)
            except Exception:
                continue
            headers: tuple[str, ...] = ()
            try:
                header_row = [
                    worksheet.cell(row=min_row, column=column).value
                    for column in range(min_col, min(max_col_ref, max_col) + 1)
                ]
                headers = tuple(
                    str(value).strip() for value in header_row if value is not None
                )
            except Exception:  # pragma: no cover
                headers = ()
            tables.append(
                TableModel(
                    name=name,
                    range=RangeRef(
                        sheet=worksheet.title,
                        min_col=min_col,
                        min_row=min_row,
                        max_col=min(max_col_ref, max_col),
                        max_row=max_row,
                    ),
                    headers=headers,
                )
            )
        return tuple(tables)


def _safe_dimension(worksheet: Any, attribute: str, fallback: int) -> int:
    try:
        value = int(getattr(worksheet, attribute) or 0)
    except Exception:  # pragma: no cover
        value = 0
    return value or fallback


def _coordinate(reference: str) -> tuple[int, int]:
    try:
        column_letters, row = coordinate_from_string(reference)
        from openpyxl.utils.cell import column_index_from_string

        return int(row), column_index_from_string(column_letters)
    except Exception:  # pragma: no cover
        return 0, 0


class SpreadsheetErrorNotFound(SpreadsheetFormatError):
    def __init__(self, path: Path) -> None:
        super().__init__(
            f"No se encontró el libro «{path.name}». Comprueba que siga en "
            "Descargas y vuelve a intentarlo."
        )


def load_workbook_model(
    path: Path | str,
    *,
    max_file_mb: float = 25.0,
    max_rows: int = 10_000,
    max_columns: int = 60,
    max_cells: int = 300_000,
    header_scan_rows: int = 12,
) -> WorkbookModel:
    """Atajo con límites explícitos para el controlador y las pruebas."""
    return WorkbookLoader(
        LoadLimits(
            max_file_mb=max_file_mb,
            max_rows=max_rows,
            max_columns=max_columns,
            max_cells=max_cells,
            header_scan_rows=header_scan_rows,
        )
    ).load(path)


def is_spreadsheet_path(path: Path | str) -> bool:
    return Path(path).suffix.casefold() in SUPPORTED_EXTENSIONS


def describe_workbook(workbook: WorkbookModel) -> str:
    """Resumen breve y local, sin IA, para la respuesta de apertura."""
    visible = workbook.visible_sheets
    names = ", ".join(sheet.name for sheet in visible[:8])
    extra = f" y {len(visible) - 8} más" if len(visible) > 8 else ""
    lines = [
        f"Libro cargado: «{workbook.name}».",
        f"{len(workbook.sheets)} hojas: {names}{extra}.",
    ]
    if workbook.hidden_sheets:
        hidden = ", ".join(sheet.name for sheet in workbook.hidden_sheets)
        lines.append(f"Hojas ocultas: {hidden}. No las mezclaré salvo que lo pidas.")
    active = workbook.first_sheet()
    if active is not None:
        lines.append(
            f"«{active.name}» tiene {active.records} registros y "
            f"{len(active.columns)} columnas."
        )
    if workbook.formula_count:
        lines.append(f"Detecté {workbook.formula_count} fórmulas.")
    if workbook.tables:
        lines.append(f"Detecté {len(workbook.tables)} tablas de Excel.")
    if workbook.truncated:
        lines.append("El libro supera algún límite; analicé solo una parte.")
    lines.append("Ya puedo analizarlo: pregunta por datos, hojas o fórmulas.")
    return "\n".join(lines)


__all__ = [
    "LoadLimits",
    "OPTIONAL_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "WorkbookLoader",
    "describe_workbook",
    "is_spreadsheet_path",
    "load_workbook_model",
    "normalize_text",
]
