"""Motor de consultas verificables sobre libros de Excel.

Todas las operaciones se ejecutan en Python con un catálogo cerrado. El plan
llega ya validado (por reglas locales o por Gemini) y aquí se comprueban de
nuevo la hoja, las columnas, los operadores y los límites antes de calcular.
Nunca se evalúa una fórmula ni se ejecuta código.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable, Sequence

from jarvis.core.errors import JarvisError
from jarvis.spreadsheets.models import (
    ColumnModel,
    RangeRef,
    SheetModel,
    WorkbookModel,
    cell_reference,
    normalize_text,
)
from jarvis.spreadsheets.sheet_profiler import (
    format_number,
    format_percent,
    format_value,
    parse_date,
    parse_number,
)

MAX_ROWS_PER_QUERY = 10_000

ALLOWED_OPERATIONS = (
    "count",
    "count_distinct",
    "sum",
    "mean",
    "min",
    "max",
    "percentage",
    "group_count",
    "group_sum",
    "list",
    "duplicates",
    "missing",
    "date_due",
    "date_upcoming",
    "date_between",
    "compare_groups",
    "describe",
    "quality",
)

ALLOWED_OPERATORS = (
    "eq",
    "not_eq",
    "contains",
    "not_contains",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "empty",
    "not_empty",
)

# Estados que no se consideran pendientes al hablar de vencimientos.
DONE_STATUSES = (
    "completada",
    "completado",
    "terminada",
    "terminado",
    "finalizada",
    "finalizado",
    "hecha",
    "hecho",
    "cerrada",
    "cerrado",
    "cancelada",
    "cancelado",
)

_DATE_WORDS = (
    "fecha",
    "vencimiento",
    "limite",
    "límite",
    "plazo",
    "entrega",
    "inicio",
    "fin",
)

_AMOUNT_WORDS = (
    "importe",
    "total",
    "monto",
    "cantidad",
    "precio",
    "coste",
    "costo",
    "gasto",
    "ingreso",
    "salario",
    "valor",
)


class QueryError(JarvisError):
    default_message = "No pude interpretar esa consulta sobre el libro."


@dataclass(frozen=True)
class QueryFilter:
    column: str
    op: str = "eq"
    value: Any = None

    def describe(self) -> str:
        if self.op == "empty":
            return f"{self.column} vacío"
        if self.op == "not_empty":
            return f"{self.column} con valor"
        if isinstance(self.value, (list, tuple)):
            value = ", ".join(str(item) for item in self.value)
        else:
            value = str(self.value)
        return f"{self.column} {self.op} {value}"


@dataclass
class QueryPlan:
    operation: str
    sheet: str = ""
    column: str = ""
    filters: tuple[QueryFilter, ...] = ()
    group_by: str = ""
    second_group_by: str = ""
    limit: int = 50
    include_hidden: bool = False
    date_field: str = ""
    today: date | None = None
    days: int = 7
    date_from: date | None = None
    date_to: date | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        parts = [self.operation]
        if self.sheet:
            parts.append(f"hoja={self.sheet}")
        if self.column:
            parts.append(f"columna={self.column}")
        if self.group_by:
            parts.append(f"agrupar={self.group_by}")
        if self.filters:
            parts.append(
                "filtros=" + "; ".join(item.describe() for item in self.filters)
            )
        return " | ".join(parts)


@dataclass(frozen=True)
class QueryGroup:
    label: str
    count: int
    total: float = 0.0
    rows: tuple[int, ...] = ()

    def amount_text(self) -> str:
        return format_number(self.total)


@dataclass
class QueryResult:
    plan: QueryPlan
    operation: str
    sheet: str
    title: str = ""
    value: float | None = None
    text: str = ""
    metrics: tuple[tuple[str, str], ...] = ()
    columns: tuple[str, ...] = ()
    table: tuple[tuple[str, ...], ...] = ()
    groups: tuple[QueryGroup, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()
    matched: int = 0
    total: int = 0
    sources: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    range_ref: str = ""
    sheet_model: SheetModel | None = None

    @property
    def numeric(self) -> bool:
        return self.value is not None


# ----------------------------------------------------------------------
# Utilidades de validación
# ----------------------------------------------------------------------
def _is_hidden(sheet: SheetModel) -> bool:
    return sheet.hidden


def resolve_sheet(
    workbook: WorkbookModel, name: str = "", *, include_hidden: bool = False
) -> SheetModel:
    visible = tuple(
        sheet
        for sheet in workbook.sheets
        if include_hidden or not sheet.hidden
    )
    if name:
        target = normalize_text(name)
        exact = [sheet for sheet in visible if normalize_text(sheet.name) == target]
        if len(exact) == 1:
            return exact[0]
        partial = [
            sheet
            for sheet in visible
            if target in normalize_text(sheet.name)
            or normalize_text(sheet.name) in target
        ]
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            options = ", ".join(sheet.name for sheet in partial)
            raise QueryError(
                f"Hay varias hojas que coinciden con «{name}»: {options}. "
                "¿Cuál quieres consultar?"
            )
        raise QueryError(
            f"No encontré la hoja «{name}». Hojas disponibles: "
            + ", ".join(sheet.name for sheet in visible)
            + "."
        )
    first = workbook.first_sheet(include_hidden=include_hidden)
    if first is None or (first.hidden and not include_hidden):
        raise QueryError(
            "No hay hojas visibles con datos. Si quieres consultar una hoja "
            "oculta, pídemelo expresamente."
        )
    return first


def resolve_column(sheet: SheetModel, name: str) -> ColumnModel:
    if not name:
        raise QueryError(
            "Necesito saber qué columna usar. Columnas disponibles: "
            + ", ".join(column.name for column in sheet.columns)
            + "."
        )
    column, candidates = sheet.column(name)
    if column is not None:
        return column
    if candidates:
        options = ", ".join(item.name for item in candidates)
        raise QueryError(
            f"Hay varias columnas que coinciden con «{name}»: {options}. "
            "¿Cuál quieres usar?"
        )
    raise QueryError(
        f"No encontré la columna «{name}» en la hoja «{sheet.name}». "
        "Columnas disponibles: "
        + ", ".join(column.name for column in sheet.columns)
        + "."
    )


def _find_column_by_words(
    sheet: SheetModel, words: Sequence[str], *, kinds: Sequence[str] = ()
) -> ColumnModel | None:
    for column in sheet.columns:
        name = normalize_text(column.name)
        if any(word in name for word in words):
            if not kinds or column.kind in kinds:
                return column
    return None


def guess_date_column(sheet: SheetModel) -> ColumnModel | None:
    due_words = (
        "vencimiento",
        "vence",
        "límite",
        "limite",
        "plazo",
        "entrega",
        "deadline",
    )
    return (
        _find_column_by_words(sheet, due_words, kinds=("date",))
        or _find_column_by_words(sheet, due_words)
        or _find_column_by_words(sheet, _DATE_WORDS, kinds=("date",))
        or _find_column_by_words(sheet, _DATE_WORDS)
    )


def guess_amount_column(sheet: SheetModel) -> ColumnModel | None:
    return _find_column_by_words(
        sheet, _AMOUNT_WORDS, kinds=("number", "percentage")
    )


def guess_group_column(sheet: SheetModel) -> ColumnModel | None:
    preferred = (
        "area",
        "área",
        "departamento",
        "estado",
        "responsable",
        "categoria",
        "categoría",
        "tipo",
        "prioridad",
    )
    for word in preferred:
        column = _find_column_by_words(sheet, (word,))
        if column is not None and column.is_empty is False:
            return column
    return None


# ----------------------------------------------------------------------
# Filtros
# ----------------------------------------------------------------------
def _comparable(value: Any) -> Any:
    if isinstance(value, (date,)):
        return value
    parsed_date = parse_date(value)
    if parsed_date is not None:
        return parsed_date
    number = parse_number(value)
    if number is not None and not isinstance(value, str):
        return number
    if isinstance(value, str):
        return normalize_text(value)
    return value


def _match_filter(value: Any, operator: str, expected: Any) -> bool:
    if operator == "empty":
        return value is None or (isinstance(value, str) and not value.strip())
    if operator == "not_empty":
        return not (value is None or (isinstance(value, str) and not value.strip()))

    text = normalize_text(value)
    expected_text = normalize_text(expected)

    if operator == "eq":
        left, right = _comparable(value), _comparable(expected)
        if isinstance(left, date) and isinstance(right, date):
            return left == right
        if isinstance(left, float) and isinstance(right, float):
            return abs(left - right) < 1e-9
        return text == expected_text
    if operator == "not_eq":
        return not _match_filter(value, "eq", expected)
    if operator == "contains":
        return expected_text in text
    if operator == "not_contains":
        return expected_text not in text
    if operator == "in":
        values = expected if isinstance(expected, (list, tuple, set)) else [expected]
        return any(_match_filter(value, "eq", item) for item in values)
    if operator == "not_in":
        values = expected if isinstance(expected, (list, tuple, set)) else [expected]
        return not any(_match_filter(value, "eq", item) for item in values)

    left, right = _comparable(value), _comparable(expected)
    if operator in {"gt", "gte", "lt", "lte"}:
        if isinstance(right, date):
            left_date = parse_date(value)
            if left_date is None:
                return False
            left = left_date
        else:
            left_number = parse_number(value)
            right_number = parse_number(expected)
            if left_number is None or right_number is None:
                return False
            left, right = left_number, right_number
    elif operator == "between":
        values = expected if isinstance(expected, (list, tuple)) else ()
        if len(values) != 2:
            return False
        return _match_filter(value, "gte", values[0]) and _match_filter(
            value, "lte", values[1]
        )

    if left is None or right is None:
        return False
    try:
        if operator == "gt":
            return left > right
        if operator == "gte":
            return left >= right
        if operator == "lt":
            return left < right
        if operator == "lte":
            return left <= right
    except TypeError:
        return False
    return False


def filter_records(
    sheet: SheetModel,
    records: Sequence[dict[str, Any]],
    filters: Sequence[QueryFilter],
) -> list[dict[str, Any]]:
    if not filters:
        return list(records)
    resolved: list[tuple[str, str, Any]] = []
    for item in filters:
        if item.op not in ALLOWED_OPERATORS:
            raise QueryError(
                f"El operador «{item.op}» no está permitido. Usa uno de: "
                + ", ".join(ALLOWED_OPERATORS)
                + "."
            )
        column = resolve_column(sheet, item.column)
        resolved.append((column.name, item.op, item.value))
    result = []
    for record in records:
        if all(
            _match_filter(record.get(name), operator, value)
            for name, operator, value in resolved
        ):
            result.append(record)
    return result


# ----------------------------------------------------------------------
# Ejecución
# ----------------------------------------------------------------------
class QueryEngine:
    """Ejecuta planes de consulta sobre un libro ya cargado."""

    def __init__(self, *, max_rows: int = MAX_ROWS_PER_QUERY) -> None:
        self.max_rows = max_rows

    def execute(
        self,
        workbook: WorkbookModel,
        plan: QueryPlan,
        *,
        today: date | None = None,
    ) -> QueryResult:
        if plan.operation not in ALLOWED_OPERATIONS:
            raise QueryError(
                f"La operación «{plan.operation}» no está permitida. "
                "Puedo contar, sumar, promediar, agrupar, filtrar, comparar "
                "fechas, detectar duplicados o describir hojas."
            )
        sheet = resolve_sheet(
            workbook, plan.sheet, include_hidden=plan.include_hidden
        )
        records = sheet.as_dicts()
        if len(records) > self.max_rows:
            records = records[: self.max_rows]

        current_day = plan.today or today or date.today()
        filtered = filter_records(sheet, records, plan.filters)
        operation = plan.operation

        if operation == "count":
            return self._count(workbook, sheet, plan, filtered, records)
        if operation == "count_distinct":
            return self._count_distinct(workbook, sheet, plan, filtered, records)
        if operation in {"sum", "mean", "min", "max"}:
            return self._aggregate(workbook, sheet, plan, filtered, records, operation)
        if operation == "percentage":
            return self._percentage(workbook, sheet, plan, filtered, records)
        if operation in {"group_count", "group_sum", "compare_groups"}:
            return self._group(
                workbook, sheet, plan, filtered, records, operation
            )
        if operation == "list":
            return self._list(workbook, sheet, plan, filtered, records)
        if operation == "duplicates":
            return self._duplicates(workbook, sheet, plan, records)
        if operation == "missing":
            return self._missing(workbook, sheet, plan, records)
        if operation == "date_due":
            return self._date_due(
                workbook, sheet, plan, filtered, records, current_day
            )
        if operation == "date_upcoming":
            return self._date_upcoming(
                workbook, sheet, plan, filtered, records, current_day
            )
        if operation == "date_between":
            return self._date_between(
                workbook, sheet, plan, filtered, records, current_day
            )
        if operation == "describe":
            return self._describe(workbook, sheet, plan, records)
        if operation == "quality":
            return self._quality(workbook, sheet, plan, records)
        raise QueryError(f"La operación «{operation}» no está implementada.")

    # ------------------------------------------------------------------
    # Operaciones
    # ------------------------------------------------------------------
    def _base(
        self, workbook: WorkbookModel, sheet: SheetModel, plan: QueryPlan
    ) -> QueryResult:
        return QueryResult(
            plan=plan,
            operation=plan.operation,
            sheet=sheet.name,
            total=sheet.records,
            sheet_model=sheet,
        )

    def _finish(
        self,
        result: QueryResult,
        records: Sequence[dict[str, Any]],
        *,
        note: str = "",
    ) -> QueryResult:
        result.sources = (self._source(result.sheet_model, records),)
        if note:
            result.notes = result.notes + (note,)
        return result

    @staticmethod
    def _source(sheet: SheetModel | None, records: Sequence[dict[str, Any]]) -> str:
        if sheet is None:
            return ""
        rows = [record.get("_fila", 0) for record in records if record.get("_fila")]
        last_col = (
            sheet.columns[-1].letter if sheet.columns else "A"
        )
        if rows:
            first = min(rows)
            last = max(rows)
            start = cell_reference(first, 1)
            end = cell_reference(last, len(sheet.columns) or 1)
            reference = f"{start}:{end}"
        elif sheet.data_range is not None:
            reference = sheet.data_range.ref
        else:
            reference = f"A1:{last_col}1"
        table = f", tabla {sheet.table.name}" if sheet.table else ""
        return f"Fuente: hoja {sheet.name}, rango {reference}{table}"

    def _count(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        result = self._base(workbook, sheet, plan)
        result.value = float(len(filtered))
        result.matched = len(filtered)
        if not plan.filters:
            result.title = "Registros"
            result.text = f"La hoja «{sheet.name}» tiene {len(filtered)} registros."
        else:
            description = " y ".join(item.describe() for item in plan.filters)
            result.title = "Registros filtrados"
            result.text = (
                f"Hay {len(filtered)} registros en la hoja «{sheet.name}» "
                f"que cumplen: {description}."
            )
        result.metrics = (
            ("Registros", str(len(filtered))),
            ("Total de la hoja", str(len(records))),
        )
        return self._finish(result, filtered if plan.filters else records)

    def _count_distinct(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        column = resolve_column(sheet, plan.column)
        values = {
            normalize_text(record.get(column.name))
            for record in filtered
            if record.get(column.name) not in (None, "")
        }
        result = self._base(workbook, sheet, plan)
        result.value = float(len(values))
        result.matched = len(filtered)
        result.title = f"Valores únicos en {column.name}"
        result.text = (
            f"Hay {len(values)} valores distintos en la columna "
            f"«{column.name}» de la hoja «{sheet.name}»."
        )
        result.metrics = (
            ("Valores distintos", str(len(values))),
            ("Registros considerados", str(len(filtered))),
        )
        return self._finish(result, filtered)

    def _numeric_values(
        self, filtered: Sequence[dict[str, Any]], column: ColumnModel
    ) -> list[float]:
        values: list[float] = []
        for record in filtered:
            number = parse_number(record.get(column.name))
            if number is None:
                parsed_date = parse_date(record.get(column.name))
                if parsed_date is None:
                    continue
                number = float(parsed_date.toordinal())
            values.append(number)
        return values

    def _aggregate(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
        operation: str,
    ) -> QueryResult:
        column = (
            resolve_column(sheet, plan.column)
            if plan.column
            else guess_amount_column(sheet)
        )
        if column is None:
            raise QueryError(
                "No sé qué columna numérica sumar o promediar. Dime el nombre "
                "de la columna. Columnas disponibles: "
                + ", ".join(item.name for item in sheet.columns)
                + "."
            )
        if column.kind in {"text", "empty"} and operation in {"sum", "mean"}:
            candidates = [item.name for item in sheet.columns if item.is_numeric]
            raise QueryError(
                f"La columna «{column.name}» contiene texto, no números. "
                + (
                    "Columnas numéricas disponibles: " + ", ".join(candidates) + "."
                    if candidates
                    else "No detecté columnas numéricas en esta hoja."
                )
            )
        values = self._numeric_values(filtered, column)
        result = self._base(workbook, sheet, plan)
        result.matched = len(filtered)
        if not values:
            result.title = f"{operation} de {column.name}"
            result.text = (
                f"No hay valores numéricos que calcular en la columna "
                f"«{column.name}» de la hoja «{sheet.name}»."
            )
            result.notes = (
                "Puede que la columna esté vacía o que los números estén "
                "guardados como texto.",
            )
            return self._finish(result, filtered)
        total = sum(values)
        if operation == "sum":
            result.value = total
            result.title = f"Suma de {column.name}"
            result.text = (
                f"La suma de «{column.name}» en la hoja «{sheet.name}» es "
                f"{format_number(total)}."
            )
        elif operation == "mean":
            result.value = total / len(values)
            result.title = f"Promedio de {column.name}"
            result.text = (
                f"El promedio de «{column.name}» en la hoja «{sheet.name}» es "
                f"{format_number(result.value)}."
            )
        elif operation == "min":
            result.value = min(values)
            result.title = f"Mínimo de {column.name}"
            result.text = (
                f"El valor mínimo de «{column.name}» es "
                f"{format_number(result.value)}."
            )
        else:
            result.value = max(values)
            result.title = f"Máximo de {column.name}"
            result.text = (
                f"El valor máximo de «{column.name}» es "
                f"{format_number(result.value)}."
            )
        result.metrics = (
            ("Resultado", format_number(result.value)),
            ("Valores usados", str(len(values))),
        )
        result.columns = ("Fila", column.name)
        result.table = tuple(
            (str(record.get("_fila", "")), format_value(record.get(column.name)))
            for record in filtered
            if parse_number(record.get(column.name)) is not None
        )[:20]
        return self._finish(result, filtered)

    def _percentage(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        result = self._base(workbook, sheet, plan)
        result.matched = len(filtered)
        percentage = (len(filtered) / len(records) * 100) if records else 0.0
        result.value = percentage
        description = " y ".join(item.describe() for item in plan.filters)
        result.title = "Porcentaje"
        result.text = (
            f"Representan el {format_number(percentage)} % del total de la "
            f"hoja «{sheet.name}»: {len(filtered)} de {len(records)} registros"
            + (f", filtrando por {description}." if description else ".")
        )
        result.metrics = (
            ("Porcentaje", f"{format_number(percentage)} %"),
            ("Coincidencias", str(len(filtered))),
            ("Total", str(len(records))),
        )
        return self._finish(result, filtered)

    def _group(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
        operation: str,
    ) -> QueryResult:
        month_mode = normalize_text(plan.group_by) in {
            "__month__",
            "mes",
            "month",
            "por mes",
        }
        group_column: ColumnModel | None = None
        if not month_mode:
            group_column = (
                resolve_column(sheet, plan.group_by)
                if plan.group_by
                else guess_group_column(sheet)
            )
        if month_mode:
            group_column = (
                resolve_column(sheet, plan.column)
                if plan.column
                else guess_date_column(sheet)
            )
            if group_column is None:
                raise QueryError(
                    "No detecté una columna de fechas para agrupar por mes."
                )
        if group_column is None:
            raise QueryError(
                "No sé por qué columna agrupar. Dime una columna, por ejemplo "
                "área, estado, responsable o mes. Columnas disponibles: "
                + ", ".join(item.name for item in sheet.columns)
                + "."
            )
        value_column: ColumnModel | None = None
        if operation in {"group_sum", "compare_groups"} and plan.column:
            value_column = resolve_column(sheet, plan.column)
        elif plan.column and operation == "compare_groups":
            value_column = resolve_column(sheet, plan.column)

        buckets: dict[str, list[dict[str, Any]]] = {}
        for record in filtered:
            if month_mode:
                parsed = parse_date(record.get(group_column.name))
                if parsed is None:
                    key = "(sin fecha)"
                else:
                    key = f"{parsed.month:02d}/{parsed.year}"
            else:
                key = format_value(record.get(group_column.name)) or "(vacío)"
            buckets.setdefault(key, []).append(record)

        groups: list[QueryGroup] = []
        for label, items in buckets.items():
            total = 0.0
            if value_column is not None:
                total = sum(
                    parse_number(item.get(value_column.name)) or 0.0
                    for item in items
                )
            groups.append(
                QueryGroup(
                    label=label,
                    count=len(items),
                    total=total,
                    rows=tuple(item.get("_fila", 0) for item in items),
                )
            )
        if month_mode:
            groups.sort(key=lambda item: item.label)
        else:
            groups.sort(
                key=lambda item: (-(item.total if value_column else item.count), item.label)
            )

        result = self._base(workbook, sheet, plan)
        result.matched = len(filtered)
        result.groups = tuple(groups)
        result.title = f"Agrupado por {'mes' if month_mode else group_column.name}"
        measure = (
            f"suma de «{value_column.name}»"
            if value_column is not None
            else "número de registros"
        )
        lines = [
            f"En la hoja «{sheet.name}», agrupado por "
            f"{'mes' if month_mode else '«' + group_column.name + '»'} "
            f"({measure}):"
        ]
        for group in groups[:15]:
            amount = (
                f": {format_number(group.total)}"
                if value_column is not None
                else ""
            )
            lines.append(f"  - {group.label}: {group.count} registros{amount}")
        if len(groups) > 15:
            lines.append(f"  - y {len(groups) - 15} grupos más")
        result.text = "\n".join(lines)
        result.columns = (
            ("Mes" if month_mode else group_column.name,
             value_column.name if value_column else "Registros")
        )
        result.table = tuple(
            (
                group.label,
                format_number(group.total) if value_column else str(group.count),
            )
            for group in groups[:50]
        )
        result.metrics = (
            ("Grupos", str(len(groups))),
            ("Registros", str(len(filtered))),
        )
        return self._finish(result, filtered)

    def _list(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        result = self._base(workbook, sheet, plan)
        result.matched = len(filtered)
        show = plan.extra.get("show") if plan.extra else None
        columns: list[ColumnModel] = []
        if isinstance(show, (list, tuple)) and show:
            columns = [resolve_column(sheet, str(name)) for name in show]
        else:
            columns = list(sheet.columns[:6])
        limit = max(1, min(plan.limit or 20, 100))
        result.title = "Registros encontrados"
        result.text = (
            f"Mostrando {min(limit, len(filtered))} de {len(filtered)} registros "
            f"de la hoja «{sheet.name}»"
            + (
                " con los filtros indicados."
                if plan.filters
                else "."
            )
        )
        result.columns = ("Fila",) + tuple(column.name for column in columns)
        result.table = tuple(
            (str(record.get("_fila", "")),)
            + tuple(format_value(record.get(column.name)) for column in columns)
            for record in filtered[:limit]
        )
        result.rows = tuple(filtered[:limit])
        result.metrics = (("Registros mostrados", str(len(result.table))),)
        return self._finish(result, filtered[:limit])

    def _duplicates(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        result = self._base(workbook, sheet, plan)
        keys: list[str] = []
        column: ColumnModel | None = None
        if plan.column:
            column = resolve_column(sheet, plan.column)
        for record in records:
            if column is not None:
                key = normalize_text(record.get(column.name))
            else:
                key = "|".join(
                    normalize_text(record.get(item.name))
                    for item in sheet.columns
                )
            if key and key.strip("|"):
                keys.append(key)
        counts: dict[str, int] = {}
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
        duplicates = [(key, count) for key, count in counts.items() if count > 1]
        duplicates.sort(key=lambda item: (-item[1], item[0]))
        result.value = float(len(duplicates))
        result.matched = len(records)
        result.title = "Registros duplicados"
        if duplicates:
            label = column.name if column is not None else "fila completa"
            result.text = (
                f"Encontré {len(duplicates)} valores duplicados en la hoja "
                f"«{sheet.name}» según {label}. "
                f"El más repetido aparece {duplicates[0][1]} veces."
            )
            result.table = tuple(
                (key, str(count)) for key, count in duplicates[:25]
            )
            result.columns = (label, "Repeticiones")
            result.metrics = (
                ("Valores duplicados", str(len(duplicates))),
                ("Registros revisados", str(len(records))),
            )
        else:
            result.text = (
                f"No encontré duplicados en la hoja «{sheet.name}»"
                + (f" según «{column.name}»." if column else ".")
            )
            result.metrics = (("Duplicados", "0"),)
        return self._finish(result, records)

    def _missing(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        result = self._base(workbook, sheet, plan)
        result.matched = len(records)
        targets: list[ColumnModel] = []
        if plan.column:
            targets = [resolve_column(sheet, plan.column)]
        else:
            targets = list(sheet.columns)
        rows: list[tuple[str, str]] = []
        total_missing = 0
        for column in targets:
            missing = sum(
                1
                for record in records
                if record.get(column.name) in (None, "")
                or (
                    isinstance(record.get(column.name), str)
                    and not str(record.get(column.name)).strip()
                )
            )
            total_missing += missing
            if missing:
                rows.append((column.name, str(missing)))
        result.value = float(total_missing)
        result.title = "Valores vacíos"
        if rows:
            result.text = (
                f"Hay valores vacíos en {len(rows)} columnas de la hoja "
                f"«{sheet.name}»: "
                + ", ".join(f"{name} ({count})" for name, count in rows[:8])
                + "."
            )
        else:
            result.text = (
                f"No encontré valores vacíos en las columnas revisadas de "
                f"«{sheet.name}»."
            )
        result.columns = ("Columna", "Vacíos")
        result.table = tuple(rows[:25])
        result.metrics = (("Celdas vacías", str(total_missing)),)
        return self._finish(result, records)

    def _status_excluded(self, record: dict[str, Any], sheet: SheetModel) -> bool:
        status_column = _find_column_by_words(
            sheet, ("estado", "situacion", "situación", "status")
        )
        if status_column is None:
            return False
        return normalize_text(record.get(status_column.name)) in DONE_STATUSES

    def _date_due(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
        today: date,
    ) -> QueryResult:
        column = (
            resolve_column(sheet, plan.date_field)
            if plan.date_field
            else guess_date_column(sheet)
        )
        if column is None:
            raise QueryError(
                "No detecté una columna de fechas para calcular vencimientos. "
                "Dime su nombre. Columnas disponibles: "
                + ", ".join(item.name for item in sheet.columns)
                + "."
            )
        overdue: list[tuple[dict[str, Any], date]] = []
        for record in filtered:
            parsed = parse_date(record.get(column.name))
            if parsed is None or parsed >= today:
                continue
            if self._status_excluded(record, sheet):
                continue
            overdue.append((record, parsed))
        result = self._base(workbook, sheet, plan)
        result.matched = len(overdue)
        result.value = float(len(overdue))
        result.title = "Registros vencidos"
        result.text = (
            f"Hay {len(overdue)} registros vencidos en la hoja "
            f"«{sheet.name}» según «{column.name}» "
            f"(fecha de hoy: {today.strftime('%d/%m/%Y')})."
        )
        if overdue:
            group_column = (
                resolve_column(sheet, plan.group_by)
                if plan.group_by
                else guess_group_column(sheet)
            )
            if group_column is not None:
                buckets: dict[str, int] = {}
                for record, _parsed in overdue:
                    key = format_value(record.get(group_column.name)) or "(vacío)"
                    buckets[key] = buckets.get(key, 0) + 1
                result.groups = tuple(
                    QueryGroup(label=label, count=count)
                    for label, count in sorted(
                        buckets.items(), key=lambda item: (-item[1], item[0])
                    )
                )
                result.text += " Por " + group_column.name + ": " + ", ".join(
                    f"{group.label} ({group.count})" for group in result.groups[:8]
                ) + "."
            rows = sorted(overdue, key=lambda item: item[1])[:10]
            result.columns = ("Fila", "Fecha", "Estado")
            status_column = _find_column_by_words(
                sheet, ("estado", "situacion", "situación", "status")
            )
            result.table = tuple(
                (
                    str(record.get("_fila", "")),
                    parsed.strftime("%d/%m/%Y"),
                    format_value(record.get(status_column.name))
                    if status_column
                    else "",
                )
                for record, parsed in rows
            )
        result.metrics = (
            ("Vencidos", str(len(overdue))),
            ("Registros revisados", str(len(filtered))),
        )
        return self._finish(result, [item[0] for item in overdue])

    def _date_upcoming(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
        today: date,
    ) -> QueryResult:
        column = (
            resolve_column(sheet, plan.date_field)
            if plan.date_field
            else guess_date_column(sheet)
        )
        if column is None:
            raise QueryError(
                "No detecté una columna de fechas para calcular próximos "
                "vencimientos. Dime su nombre."
            )
        days = max(1, min(plan.days or 7, 365))
        limit_day = today + timedelta(days=days)
        upcoming: list[tuple[dict[str, Any], date]] = []
        for record in filtered:
            parsed = parse_date(record.get(column.name))
            if parsed is None or not (today <= parsed <= limit_day):
                continue
            if self._status_excluded(record, sheet):
                continue
            upcoming.append((record, parsed))
        upcoming.sort(key=lambda item: item[1])
        result = self._base(workbook, sheet, plan)
        result.matched = len(upcoming)
        result.value = float(len(upcoming))
        result.title = "Próximos vencimientos"
        result.text = (
            f"Hay {len(upcoming)} registros que vencen entre hoy y el "
            f"{limit_day.strftime('%d/%m/%Y')} en la hoja «{sheet.name}»."
        )
        result.columns = ("Fila", "Fecha", "Registro")
        result.table = tuple(
            (
                str(record.get("_fila", "")),
                parsed.strftime("%d/%m/%Y"),
                format_value(
                    record.get(
                        sheet.columns[0].name if sheet.columns else "Fila"
                    )
                ),
            )
            for record, parsed in upcoming[:20]
        )
        result.metrics = (
            ("Próximos", str(len(upcoming))),
            ("Ventana", f"{days} días"),
        )
        return self._finish(result, [item[0] for item in upcoming])

    def _date_between(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        filtered: Sequence[dict[str, Any]],
        records: Sequence[dict[str, Any]],
        today: date,
    ) -> QueryResult:
        column = (
            resolve_column(sheet, plan.date_field)
            if plan.date_field
            else guess_date_column(sheet)
        )
        if column is None:
            raise QueryError(
                "No detecté una columna de fechas para delimitar el período."
            )
        start = plan.date_from or today.replace(day=1)
        end = plan.date_to or today
        matches: list[tuple[dict[str, Any], date]] = []
        for record in filtered:
            parsed = parse_date(record.get(column.name))
            if parsed is not None and start <= parsed <= end:
                matches.append((record, parsed))
        matches.sort(key=lambda item: item[1])
        result = self._base(workbook, sheet, plan)
        result.matched = len(matches)
        result.value = float(len(matches))
        result.title = "Registros en el período"
        result.text = (
            f"Hay {len(matches)} registros de la hoja «{sheet.name}» con "
            f"«{column.name}» entre {start.strftime('%d/%m/%Y')} y "
            f"{end.strftime('%d/%m/%Y')}."
        )
        result.columns = ("Fila", "Fecha")
        result.table = tuple(
            (str(record.get("_fila", "")), parsed.strftime("%d/%m/%Y"))
            for record, parsed in matches[:20]
        )
        result.metrics = (
            ("Registros", str(len(matches))),
            ("Desde", start.strftime("%d/%m/%Y")),
            ("Hasta", end.strftime("%d/%m/%Y")),
        )
        return self._finish(result, [item[0] for item in matches])

    def _describe(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        result = self._base(workbook, sheet, plan)
        result.matched = len(records)
        kinds: dict[str, int] = {}
        for column in sheet.columns:
            kinds[column.kind] = kinds.get(column.kind, 0) + 1
        result.title = f"Resumen de {sheet.name}"
        result.text = (
            f"La hoja «{sheet.name}» tiene {len(records)} registros y "
            f"{len(sheet.columns)} columnas. "
            f"Parece contener {sheet.purpose}. "
            "Columnas: "
            + ", ".join(column.name for column in sheet.columns[:12])
            + ("." if len(sheet.columns) <= 12 else ", etc.")
        )
        if sheet.formula_count:
            result.text += f" Detecté {sheet.formula_count} fórmulas."
        result.metrics = (
            ("Registros", str(len(records))),
            ("Columnas", str(len(sheet.columns))),
            ("Fórmulas", str(sheet.formula_count)),
            ("Tablas", str(len(sheet.tables))),
        )
        result.columns = ("Columna", "Tipo", "Vacíos")
        result.table = tuple(
            (column.name, _kind_label(column.kind), str(column.empty))
            for column in sheet.columns[:30]
        )
        return self._finish(result, records)

    def _quality(
        self,
        workbook: WorkbookModel,
        sheet: SheetModel,
        plan: QueryPlan,
        records: Sequence[dict[str, Any]],
    ) -> QueryResult:
        from jarvis.spreadsheets.data_quality import diagnose_sheet

        issues = diagnose_sheet(sheet)
        result = self._base(workbook, sheet, plan)
        result.matched = len(records)
        result.title = f"Calidad de datos de {sheet.name}"
        if not issues:
            result.text = f"No encontré problemas evidentes en la hoja «{sheet.name}»."
            result.metrics = (("Problemas", "0"),)
        else:
            result.text = (
                f"Encontré {len(issues)} posibles problemas en la hoja "
                f"«{sheet.name}»."
            )
            result.columns = ("Problema", "Columna", "Casos")
            result.table = tuple(
                (issue.problem, issue.column or "—", str(issue.count))
                for issue in issues[:20]
            )
            result.metrics = (
                ("Problemas", str(len(issues))),
                ("Casos", str(sum(issue.count for issue in issues))),
            )
            result.notes = tuple(
                f"{issue.problem}: {issue.recommendation}" for issue in issues[:5]
            )
        return self._finish(result, records)


def _kind_label(kind: str) -> str:
    return {
        "number": "número",
        "percentage": "porcentaje",
        "date": "fecha",
        "text": "texto",
        "bool": "sí/no",
        "mixed": "mixto",
        "empty": "vacía",
    }.get(kind, kind)


__all__ = [
    "ALLOWED_OPERATIONS",
    "ALLOWED_OPERATORS",
    "DONE_STATUSES",
    "QueryEngine",
    "QueryError",
    "QueryFilter",
    "QueryGroup",
    "QueryPlan",
    "QueryResult",
    "filter_records",
    "guess_amount_column",
    "guess_date_column",
    "guess_group_column",
    "resolve_column",
    "resolve_sheet",
]
