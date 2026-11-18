"""Perfilado de hojas: encabezados, tipos, fechas y categorías.

No se apoya en que los encabezados estén en la primera fila. Puntúa las
primeras filas y devuelve la mejor candidata junto con las alternativas, para
que el asistente pueda preguntar cuando la estructura sea ambigua.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from jarvis.spreadsheets.models import (
    ColumnModel,
    SheetModel,
    column_letter,
    normalize_text,
)

_SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_DATE_PATTERNS = (
    re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$"),
    re.compile(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$"),
    re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$"),
    re.compile(
        r"^(\d{1,2})\s+de\s+([a-záéíóú]+)\s+de\s+(\d{4})$",
        re.IGNORECASE,
    ),
)

_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:[.,]\d+)*|\.\d+|,\d+)$")
_HEADER_HINTS = (
    "id",
    "nombre",
    "descripcion",
    "fecha",
    "estado",
    "prioridad",
    "responsable",
    "area",
    "departamento",
    "total",
    "importe",
    "cantidad",
    "precio",
    "categoria",
    "tipo",
    "codigo",
    "correo",
    "telefono",
    "porcentaje",
    "avance",
    "observaciones",
)


@dataclass(frozen=True)
class HeaderDetection:
    header_row: int | None
    headers: tuple[str, ...]
    confidence: float = 0.0
    candidates: tuple[int, ...] = ()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value).strip()


def parse_number(value: Any) -> float | None:
    """Convierte números de Excel y texto numérico español a float."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace("€", "").replace("$", "").replace(" ", "")
    percent = text.endswith("%")
    if percent:
        text = text[:-1]
    if not _NUMBER_RE.match(text):
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+", text):
            text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
    else:
        if re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+", text):
            text = text.replace(".", "")
    try:
        number = float(text)
    except ValueError:
        return None
    if percent:
        number /= 100.0
    return -number if negative else number


def parse_date(value: Any) -> date | None:
    """Convierte fechas nativas y texto con formatos habituales."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = " ".join(value.strip().split())
    if not text:
        return None
    # Descarta la hora si acompaña a una fecha.
    text = re.split(r"\s+\d{1,2}:\d{2}", text)[0]
    for pattern in _DATE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groups()
        try:
            if pattern is _DATE_PATTERNS[1]:
                year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
            elif pattern is _DATE_PATTERNS[3]:
                day, month_name, year = (
                    int(groups[0]),
                    groups[1].lower(),
                    int(groups[2]),
                )
                month = _SPANISH_MONTHS.get(normalize_text(month_name), 0)
                if not month:
                    continue
            else:
                day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
            if year < 100:
                year += 2000 if year < 70 else 1900
            return date(year, month, day)
        except ValueError:
            continue
    return None


def is_date_like(value: Any) -> bool:
    return parse_date(value) is not None


def is_number_like(value: Any) -> bool:
    return parse_number(value) is not None


def looks_like_header(values: Sequence[Any]) -> bool:
    """Heurística rápida para una fila concreta."""
    texts = [value for value in values if value not in (None, "")]
    if not texts:
        return False
    string_count = sum(
        1
        for value in texts
        if isinstance(value, str)
        and not is_number_like(value)
        and not is_date_like(value)
    )
    return string_count / len(texts) >= 0.55


def _row_values(rows: Sequence[Sequence[Any]], position: int) -> list[Any]:
    return list(rows[position]) if position < len(rows) else []


def detect_header(
    rows: Sequence[Sequence[Any]],
    *,
    scan_rows: int = 12,
) -> HeaderDetection:
    """Detecta la fila de encabezados en las primeras filas."""
    if not rows:
        return HeaderDetection(None, ())

    limit = min(len(rows), max(1, scan_rows))
    max_width = max((_last_non_empty(row) for row in rows[:limit]), default=0)
    if max_width == 0:
        return HeaderDetection(None, ())

    first_data_row = None
    for position, row in enumerate(rows):
        if any(value not in (None, "") for value in row):
            first_data_row = position
            break
    if first_data_row is None:
        return HeaderDetection(None, ())

    scored: list[tuple[float, int, tuple[str, ...]]] = []
    for position in range(limit):
        row = _row_values(rows, position)
        if not any(value not in (None, "") for value in row):
            continue
        if position >= len(rows) - 1 and len(rows) > 1:
            # Un encabezado necesita al menos una fila de datos debajo.
            continue
        width = max(max_width, _last_non_empty(row))
        cells = [row[index] if index < len(row) else None for index in range(width)]
        filled = [value for value in cells if value not in (None, "")]
        if not filled:
            continue
        fill_ratio = len(filled) / max(1, width)
        stringish = sum(
            1
            for value in filled
            if isinstance(value, str)
            and not is_number_like(value)
            and not is_date_like(value)
        )
        string_ratio = stringish / len(filled)
        numeric_or_date = sum(
            1
            for value in filled
            if is_number_like(value) or is_date_like(value)
        )
        numeric_ratio = numeric_or_date / len(filled)
        labels = [_cell_text(value) for value in filled]
        unique_ratio = len(set(normalize_text(label) for label in labels)) / max(
            1, len(labels)
        )
        hint_bonus = (
            sum(
                1
                for label in labels
                if any(hint in normalize_text(label) for hint in _HEADER_HINTS)
            )
            / max(1, len(labels))
        )
        data_below = 0
        examined = 0
        for later in range(position + 1, min(len(rows), position + 21)):
            examined += 1
            if any(value not in (None, "") for value in rows[later]):
                data_below += 1
        data_ratio = data_below / examined if examined else 0.0
        score = (
            0.34 * string_ratio
            + 0.20 * fill_ratio
            + 0.18 * data_ratio
            + 0.12 * unique_ratio
            + 0.08 * hint_bonus
            - 0.22 * numeric_ratio
        )
        scored.append((round(score, 4), position, tuple(labels)))

    if not scored:
        return HeaderDetection(None, ())

    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score, best_position, best_labels = scored[0]
    candidates: list[int] = []
    for score, position, _labels in scored[1:]:
        if score >= max(0.50, best_score - 0.07) and position != best_position:
            candidates.append(position + 1)
    if best_score < 0.34:
        # Sin encabezado claro: los datos empiezan en la primera fila útil.
        return HeaderDetection(None, ())
    return HeaderDetection(
        header_row=best_position + 1,
        headers=best_labels,
        confidence=best_score,
        candidates=tuple(candidates[:3]),
    )


def _last_non_empty(row: Sequence[Any]) -> int:
    """Último índice (1-based) con contenido; 0 si la fila está vacía."""
    for index in range(len(row) - 1, -1, -1):
        value = row[index]
        if value is not None and str(value).strip() != "":
            return index + 1
    return 0


def infer_kind(values: Sequence[Any], number_format: str = "") -> str:
    """Infiere el tipo dominante de una columna a partir de una muestra."""
    present = [value for value in values if value not in (None, "")]
    if not present:
        return "empty"
    total = len(present)
    dates = sum(1 for value in present if parse_date(value) is not None)
    numbers = sum(
        1
        for value in present
        if parse_number(value) is not None and not isinstance(value, bool)
    )
    booleans = sum(1 for value in present if isinstance(value, bool))
    if dates / total >= 0.75 and numbers / total < 0.5:
        return "date"
    if numbers / total >= 0.8:
        if "%" in (number_format or ""):
            return "percentage"
        return "number"
    if booleans / total >= 0.8:
        return "bool"
    strings = sum(1 for value in present if isinstance(value, str))
    if strings / total >= 0.8:
        return "text"
    return "mixed"


def sheet_purpose(headers: Iterable[str]) -> str:
    """Propósito aproximado de la hoja según sus encabezados."""
    text = " ".join(normalize_text(header) for header in headers)
    if any(
        word in text
        for word in (
            "tarea",
            "estado",
            "prioridad",
            "responsable",
            "vencimiento",
            "pendiente",
        )
    ):
        return "tareas"
    if any(
        word in text
        for word in ("ingreso", "gasto", "importe", "factura", "presupuesto", "total")
    ):
        return "finanzas"
    if any(
        word in text
        for word in ("producto", "precio", "stock", "inventario", "cantidad")
    ):
        return "inventario"
    if any(
        word in text
        for word in ("nombre", "correo", "email", "telefono", "contacto")
    ):
        return "contactos"
    return "datos"


def build_columns(
    headers: Sequence[str],
    rows: Sequence[Sequence[Any]],
    *,
    number_formats: Sequence[str] | None = None,
    formula_counts: Sequence[int] | None = None,
    sample_limit: int = 300,
) -> tuple[ColumnModel, ...]:
    """Construye columnas con tipo, vacíos, únicos y muestras."""
    width = max(
        [len(headers)]
        + [len(row) for row in rows]
        + [0],
    )
    columns: list[ColumnModel] = []
    used_names: set[str] = set()
    for index in range(width):
        raw_name = headers[index] if index < len(headers) else ""
        name = _cell_text(raw_name) or f"Columna {column_letter(index)}"
        base = name
        suffix = 2
        while normalize_text(name) in used_names:
            name = f"{base} ({suffix})"
            suffix += 1
        used_names.add(normalize_text(name))
        values = [
            row[index] if index < len(row) else None
            for row in rows[:sample_limit]
        ]
        present = [value for value in values if value not in (None, "")]
        number_format = (
            number_formats[index]
            if number_formats is not None and index < len(number_formats)
            else ""
        )
        kind = infer_kind(present, number_format)
        columns.append(
            ColumnModel(
                name=name,
                letter=column_letter(index),
                index=index,
                kind=kind,
                number_format=number_format or "",
                empty=len(values) - len(present),
                total=len(values),
                unique=len({_unique_key(value) for value in present}),
                formula_count=(
                    formula_counts[index]
                    if formula_counts is not None and index < len(formula_counts)
                    else 0
                ),
                samples=tuple(present[:5]),
            )
        )
    return tuple(columns)


def _unique_key(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        parsed = parse_date(value)
        return parsed.isoformat() if parsed else str(value)
    if isinstance(value, str):
        return normalize_text(value)
    return repr(value)


def build_sheet(
    *,
    name: str,
    index: int,
    rows: Sequence[Sequence[Any]],
    row_numbers: Sequence[int],
    hidden: bool = False,
    column_formats: Sequence[str] | None = None,
    formula_counts: Sequence[int] | None = None,
    header_scan_rows: int = 12,
    tables: tuple = (),
    merged_ranges: tuple[str, ...] = (),
    formulas: dict[str, str] | None = None,
    formula_values: dict[str, Any] | None = None,
    truncated: bool = False,
    warnings: tuple[str, ...] = (),
) -> SheetModel:
    """Construye una hoja completa a partir de filas ya extraídas."""
    detection = detect_header(rows, scan_rows=header_scan_rows)
    header_position = (
        detection.header_row - 1 if detection.header_row is not None else None
    )
    headers = list(detection.headers)
    data_start = (header_position + 1) if header_position is not None else 0

    # Descarta filas completamente vacías y conserva su número original.
    data_rows: list[Sequence[Any]] = []
    data_numbers: list[int] = []
    empty_rows = 0
    last_data_position = None
    for position in range(len(rows) - 1, data_start - 1, -1):
        if any(value not in (None, "") for value in rows[position]):
            last_data_position = position
            break
    for position in range(data_start, len(rows)):
        row = rows[position]
        if not any(value not in (None, "") for value in row):
            if last_data_position is not None and position < last_data_position:
                empty_rows += 1
            continue
        data_rows.append(row)
        data_numbers.append(
            row_numbers[position] if position < len(row_numbers) else position + 1
        )

    if header_position is not None and header_position < len(rows):
        header_row = rows[header_position]
        width = max(
            [len(header_row)]
            + [len(row) for row in data_rows]
            + [len(headers)]
            + [0]
        )
        headers = [
            _cell_text(header_row[column]) if column < len(header_row) else ""
            for column in range(width)
        ]

    # Recorta columnas totalmente vacías al final.
    width = max([len(headers)] + [len(row) for row in data_rows] + [0])
    while width > 0:
        has_header = bool(_cell_text(headers[width - 1])) if width <= len(headers) else False
        has_data = any(
            width <= len(row) and row[width - 1] not in (None, "")
            for row in data_rows
        )
        if has_header or has_data:
            break
        width -= 1
    headers = headers[:width]
    trimmed_rows = tuple(tuple(row[:width]) for row in data_rows)

    formats: list[str] = list(column_formats or ())
    while len(formats) < width:
        formats.append("")
    columns = build_columns(
        headers,
        trimmed_rows,
        number_formats=formats[:width],
        formula_counts=formula_counts,
    )

    min_row = min(data_numbers) if data_numbers else None
    max_row = max(data_numbers) if data_numbers else None
    data_range = None
    if min_row is not None and max_row is not None and width:
        data_range = _make_range(
            name,
            min_row=max(1, (detection.header_row or min_row)),
            max_row=max_row,
            min_col=1,
            max_col=width,
        )

    return SheetModel(
        name=name,
        index=index,
        hidden=hidden,
        header_row=detection.header_row,
        header_confidence=detection.confidence,
        header_candidates=detection.candidates,
        headers=tuple(headers),
        columns=columns,
        rows=trimmed_rows,
        row_numbers=tuple(data_numbers),
        data_range=data_range,
        tables=tables,
        merged_ranges=merged_ranges,
        formulas=formulas or {},
        formula_values=formula_values or {},
        warnings=warnings,
        truncated=truncated,
        purpose=sheet_purpose(headers),
        dimensions=(
            f"A1:{column_letter(max(0, width - 1))}{max_row}"
            if width and max_row
            else ""
        ),
        empty_rows=empty_rows,
    )


def _make_range(sheet: str, *, min_row: int, max_row: int, min_col: int, max_col: int):
    from jarvis.spreadsheets.models import RangeRef

    return RangeRef(
        sheet=sheet,
        min_col=min_col,
        min_row=min_row,
        max_col=max_col,
        max_row=max_row,
    )


def format_number(value: float, *, maximum_decimals: int = 2) -> str:
    """Número con separadores españoles y sin decimales innecesarios."""
    if value == int(value):
        return f"{int(value):,}".replace(",", ".")
    text = f"{value:,.{maximum_decimals}f}".rstrip("0").rstrip(".")
    integer, _, decimals = text.partition(".")
    return integer.replace(",", ".") + (f",{decimals}" if decimals else "")


def format_value(value: Any, *, percentage: bool = False) -> str:
    """Representación legible en español de un valor de celda."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    if isinstance(value, datetime):
        if value.hour == 0 and value.minute == 0 and value.second == 0:
            return value.strftime("%d/%m/%Y")
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (int, float)):
        text = format_number(float(value))
        return f"{text} %" if percentage else text
    return str(value).strip()


def format_percent(value: float) -> str:
    return f"{format_number(value * 100)} %"


__all__ = [
    "HeaderDetection",
    "build_columns",
    "build_sheet",
    "detect_header",
    "format_number",
    "format_percent",
    "format_value",
    "infer_kind",
    "is_date_like",
    "is_number_like",
    "looks_like_header",
    "parse_date",
    "parse_number",
    "sheet_purpose",
]
