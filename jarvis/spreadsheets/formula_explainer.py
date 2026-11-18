"""Explicación de fórmulas de Excel sin ejecutarlas.

Se leen las expresiones tal como las guarda el libro (``data_only=False``) y,
por separado, los resultados cacheados que Excel haya guardado. Nunca se
recalcula ni se evalúa la fórmula.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from jarvis.spreadsheets.models import SheetModel, cell_reference, normalize_text
from jarvis.spreadsheets.sheet_profiler import format_value

_FUNCTION_RE = re.compile(
    r"(?<![A-Za-z0-9_.])([A-Za-zÁÉÍÓÚÜÑ][A-Za-z0-9_.ÁÉÍÓÚÜÑ]*)\s*\("
)
_CELL_RE = re.compile(r"\$?([A-Z]{1,3})\$?(\d{1,7})")

FUNCTION_INFO = {
    "SI": ("SI", "devuelve un valor u otro según una condición"),
    "IF": ("SI", "devuelve un valor u otro según una condición"),
    "Y": ("Y", "exige que se cumplan todas las condiciones"),
    "AND": ("Y", "exige que se cumplan todas las condiciones"),
    "O": ("O", "basta con que se cumpla una condición"),
    "OR": ("O", "basta con que se cumpla una condición"),
    "NO": ("NO", "invierte una condición verdadera/falsa"),
    "NOT": ("NO", "invierte una condición verdadera/falsa"),
    "BUSCARV": ("BUSCARV", "busca un valor en la primera columna de un rango y devuelve otro dato de esa fila"),
    "VLOOKUP": ("BUSCARV", "busca un valor en la primera columna de un rango y devuelve otro dato de esa fila"),
    "BUSCARX": ("BUSCARX", "busca un valor en un rango y devuelve el dato correspondiente de otra columna o fila"),
    "XLOOKUP": ("BUSCARX", "busca un valor en un rango y devuelve el dato correspondiente de otra columna o fila"),
    "SUMA": ("SUMA", "suma los valores indicados"),
    "SUM": ("SUMA", "suma los valores indicados"),
    "SUMAR.SI": ("SUMAR.SI", "suma solo los valores que cumplen una condición"),
    "SUMIF": ("SUMAR.SI", "suma solo los valores que cumplen una condición"),
    "SUMAR.SI.CONJUNTO": ("SUMAR.SI.CONJUNTO", "suma los valores que cumplen varias condiciones"),
    "SUMIFS": ("SUMAR.SI.CONJUNTO", "suma los valores que cumplen varias condiciones"),
    "PROMEDIO": ("PROMEDIO", "calcula la media aritmética"),
    "AVERAGE": ("PROMEDIO", "calcula la media aritmética"),
    "CONTAR": ("CONTAR", "cuenta cuántas celdas contienen números"),
    "COUNT": ("CONTAR", "cuenta cuántas celdas contienen números"),
    "CONTARA": ("CONTARA", "cuenta cuántas celdas no están vacías"),
    "COUNTA": ("CONTARA", "cuenta cuántas celdas no están vacías"),
    "CONTAR.SI": ("CONTAR.SI", "cuenta las celdas que cumplen una condición"),
    "COUNTIF": ("CONTAR.SI", "cuenta las celdas que cumplen una condición"),
    "CONTAR.SI.CONJUNTO": ("CONTAR.SI.CONJUNTO", "cuenta las celdas que cumplen varias condiciones"),
    "COUNTIFS": ("CONTAR.SI.CONJUNTO", "cuenta las celdas que cumplen varias condiciones"),
    "SI.ERROR": ("SI.ERROR", "muestra un valor alternativo si la fórmula da error"),
    "IFERROR": ("SI.ERROR", "muestra un valor alternativo si la fórmula da error"),
    "CONCATENAR": ("CONCATENAR", "une varios textos en uno solo"),
    "CONCATENATE": ("CONCATENAR", "une varios textos en uno solo"),
    "CONCAT": ("CONCAT", "une varios textos o rangos en uno solo"),
    "HOY": ("HOY", "devuelve la fecha actual"),
    "TODAY": ("HOY", "devuelve la fecha actual"),
    "AHORA": ("AHORA", "devuelve la fecha y la hora actuales"),
    "NOW": ("AHORA", "devuelve la fecha y la hora actuales"),
    "FECHA": ("FECHA", "construye una fecha a partir de año, mes y día"),
    "DATE": ("FECHA", "construye una fecha a partir de año, mes y día"),
    "AÑO": ("AÑO", "extrae el año de una fecha"),
    "YEAR": ("AÑO", "extrae el año de una fecha"),
    "MES": ("MES", "extrae el mes de una fecha"),
    "MONTH": ("MES", "extrae el mes de una fecha"),
    "DIA": ("DÍA", "extrae el día de una fecha"),
    "DAY": ("DÍA", "extrae el día de una fecha"),
    "DIAS": ("DÍAS", "calcula la diferencia en días entre dos fechas"),
    "DAYS": ("DÍAS", "calcula la diferencia en días entre dos fechas"),
    "SIFECHA": ("SIFECHA", "calcula la diferencia entre dos fechas en días, meses o años"),
    "DATEDIF": ("SIFECHA", "calcula la diferencia entre dos fechas en días, meses o años"),
    "IZQUIERDA": ("IZQUIERDA", "toma los primeros caracteres de un texto"),
    "LEFT": ("IZQUIERDA", "toma los primeros caracteres de un texto"),
    "DERECHA": ("DERECHA", "toma los últimos caracteres de un texto"),
    "RIGHT": ("DERECHA", "toma los últimos caracteres de un texto"),
    "EXTRAE": ("EXTRAE", "toma una parte concreta de un texto"),
    "MID": ("EXTRAE", "toma una parte concreta de un texto"),
    "LARGO": ("LARGO", "cuenta los caracteres de un texto"),
    "LEN": ("LARGO", "cuenta los caracteres de un texto"),
    "REDONDEAR": ("REDONDEAR", "redondea un número a los decimales indicados"),
    "ROUND": ("REDONDEAR", "redondea un número a los decimales indicados"),
    "MAX": ("MAX", "devuelve el valor mayor"),
    "MIN": ("MIN", "devuelve el valor menor"),
    "ESBLANCO": ("ESBLANCO", "comprueba si una celda está vacía"),
    "ISBLANK": ("ESBLANCO", "comprueba si una celda está vacía"),
    "ES.ERROR": ("ES.ERROR", "comprueba si un valor es un error"),
    "ISERROR": ("ES.ERROR", "comprueba si un valor es un error"),
    "INDICE": ("ÍNDICE", "devuelve un valor de una posición concreta de un rango"),
    "INDEX": ("ÍNDICE", "devuelve un valor de una posición concreta de un rango"),
    "COINCIDIR": ("COINCIDIR", "busca un valor y devuelve su posición"),
    "MATCH": ("COINCIDIR", "busca un valor y devuelve su posición"),
    "ELEGIR": ("ELEGIR", "elige un valor de una lista según un índice"),
    "CHOOSE": ("ELEGIR", "elige un valor de una lista según un índice"),
}


@dataclass(frozen=True)
class FormulaExplanation:
    sheet: str
    cell: str
    formula: str
    column: str = ""
    functions: tuple[str, ...] = ()
    cached_value: Any = None
    has_cached: bool = False
    example: str = ""
    text: str = ""
    source: str = ""
    formula_count: int = 1

    @property
    def missing_cache_note(self) -> str:
        return (
            "Puedo identificar y explicar la fórmula, pero el archivo no "
            "contiene un resultado calculado disponible para esta celda. "
            "Ábrelo y guárdalo en Excel para actualizar sus resultados."
        )


def _function_names(formula: str) -> tuple[str, ...]:
    names: list[str] = []
    for match in _FUNCTION_RE.finditer(formula or ""):
        name = match.group(1).upper()
        for prefix in ("_XLFN.", "_XLWS."):
            if name.startswith(prefix):
                name = name[len(prefix) :]
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _normalize_pattern(formula: str) -> str:
    """Patrón aproximado para agrupar fórmulas equivalentes."""
    return re.sub(r"\d+", "#", formula.upper().replace("$", ""))


def formulas_in_column(sheet: SheetModel, column_name: str) -> list[tuple[str, str]]:
    """Devuelve [(celda, fórmula)] de la columna indicada."""
    column, candidates = sheet.column(column_name)
    if column is None:
        if candidates:
            raise ValueError(
                "Hay varias columnas que coinciden: "
                + ", ".join(item.name for item in candidates)
            )
        raise ValueError(f"No encontré la columna «{column_name}».")
    prefix = column.letter.upper()
    found: list[tuple[str, str]] = []
    for reference, formula in sheet.formulas.items():
        match = re.fullmatch(r"([A-Z]{1,3})(\d+)", reference.strip().upper())
        if match and match.group(1) == prefix:
            found.append((reference, formula))
    found.sort(key=lambda item: int(re.sub(r"\D", "", item[0]) or 0))
    return found


def _row_example(sheet: SheetModel, row_number: int) -> str:
    pairs: list[str] = []
    for column in sheet.columns:
        value = sheet.value_at(row_number, column.index)
        if value in (None, ""):
            continue
        pairs.append(f"{column.name} = {format_value(value)}")
    if not pairs:
        return ""
    return "En esa fila los valores son: " + "; ".join(pairs[:8]) + "."


def explain_formula(
    sheet: SheetModel,
    *,
    column_name: str = "",
    reference: str = "",
    row_number: int | None = None,
) -> FormulaExplanation:
    """Explica una fórmula concreta o la más representativa de una columna."""
    if not sheet.formulas:
        raise ValueError(
            f"La hoja «{sheet.name}» no contiene fórmulas detectadas."
        )

    chosen_reference = ""
    formula = ""
    column_label = ""

    if reference:
        target = reference.strip().upper()
        formula = sheet.formulas.get(target, "")
        if not formula:
            raise ValueError(
                f"No encontré una fórmula en la celda {target} de la hoja "
                f"«{sheet.name}»."
            )
        chosen_reference = target
        match = re.fullmatch(r"([A-Z]{1,3})(\d+)", target)
        if match:
            for column in sheet.columns:
                if column.letter.upper() == match.group(1):
                    column_label = column.name
                    break
    elif column_name:
        try:
            found = formulas_in_column(sheet, column_name)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not found:
            raise ValueError(
                f"No encontré fórmulas en la columna «{column_name}» de la "
                f"hoja «{sheet.name}»."
            )
        # Se elige el patrón más repetido y, dentro de él, la primera fila.
        patterns: dict[str, int] = {}
        for _cell, item in found:
            pattern = _normalize_pattern(item)
            patterns[pattern] = patterns.get(pattern, 0) + 1
        best_pattern = max(patterns.items(), key=lambda item: item[1])[0]
        for cell, item in found:
            if _normalize_pattern(item) == best_pattern:
                chosen_reference, formula = cell, item
                break
        column, _ = sheet.column(column_name)
        column_label = column.name if column is not None else column_name
    else:
        # Sin pistas: fórmula más frecuente de todo el libro de la hoja.
        patterns = {}
        for cell, item in sheet.formulas.items():
            pattern = _normalize_pattern(item)
            patterns.setdefault(pattern, []).append((cell, item))
        best = max(patterns.values(), key=lambda items: len(items))
        chosen_reference, formula = sorted(
            best, key=lambda item: int(re.sub(r"\D", "", item[0]) or 0)
        )[0]
        match = re.fullmatch(r"([A-Z]{1,3})(\d+)", chosen_reference)
        if match:
            for column in sheet.columns:
                if column.letter.upper() == match.group(1):
                    column_label = column.name
                    break

    functions = _function_names(formula)
    if not functions:
        raise ValueError(
            "No reconocí funciones de Excel en esa fórmula; puede ser una "
            "operación aritmética simple."
        )

    names: list[str] = []
    descriptions: list[str] = []
    for function in functions:
        info = FUNCTION_INFO.get(function)
        if info is None:
            names.append(function)
            descriptions.append(
                f"«{function}» es una función que no tengo catalogada; "
                "la explico de forma general."
            )
            continue
        label, description = info
        names.append(label)
        descriptions.append(f"{label} {description}.")
    descriptions = list(dict.fromkeys(descriptions))

    relevant_cells = [
        match.group(0)
        for match in _CELL_RE.finditer(formula)
        if match.group(1) and match.group(2)
    ]
    example_row = row_number
    if example_row is None:
        match = re.fullmatch(r"[A-Z]{1,3}(\d+)", chosen_reference)
        if match:
            example_row = int(match.group(1))
    example = _row_example(sheet, example_row) if example_row else ""

    has_cached = chosen_reference in sheet.formula_values
    cached = sheet.formula_values.get(chosen_reference)
    if cached is None:
        has_cached = False

    formula_count = 1
    if column_label:
        try:
            formula_count = len(formulas_in_column(sheet, column_label))
        except ValueError:
            formula_count = 1

    text_parts = [
        f"La fórmula de la celda {chosen_reference} en la hoja «{sheet.name}» "
        f"es: {formula}",
    ]
    if column_label:
        text_parts.append(
            f"Está en la columna «{column_label}» y afecta a "
            f"{formula_count} celda(s) con fórmula."
        )
    text_parts.append("Qué hace: " + " ".join(descriptions))
    if relevant_cells:
        text_parts.append(
            "Toma datos de las celdas " + ", ".join(relevant_cells[:8]) + "."
        )
    if example:
        text_parts.append(example)
    if has_cached:
        text_parts.append(
            f"El último resultado guardado por Excel es "
            f"{format_value(cached)}."
        )
    else:
        text_parts.append(FormulaExplanation(
            sheet=sheet.name,
            cell=chosen_reference,
            formula=formula,
        ).missing_cache_note)
        text_parts.append(
            "No inventaré un resultado: los valores mostrados arriba son los "
            "datos de entrada, no el cálculo."
        )

    return FormulaExplanation(
        sheet=sheet.name,
        cell=chosen_reference,
        formula=formula,
        column=column_label,
        functions=tuple(names),
        cached_value=cached,
        has_cached=has_cached,
        example=example,
        text="\n".join(text_parts),
        source=f"Fuente: hoja {sheet.name}, celda {chosen_reference}",
        formula_count=formula_count,
    )


def explain_workbook_formulas(workbook) -> str:
    """Resumen local de todas las fórmulas detectadas."""
    lines: list[str] = []
    for sheet in workbook.sheets:
        if not sheet.formulas:
            continue
        functions: dict[str, int] = {}
        for formula in sheet.formulas.values():
            for name in _function_names(formula):
                info = FUNCTION_INFO.get(name)
                label = info[0] if info else name
                functions[label] = functions.get(label, 0) + 1
        summary = ", ".join(
            f"{name} ({count})"
            for name, count in sorted(functions.items(), key=lambda item: -item[1])
        )
        lines.append(
            f"Hoja «{sheet.name}»: {sheet.formula_count} fórmulas"
            + (f" — {summary}" if summary else "")
        )
    if not lines:
        return "El libro no contiene fórmulas detectadas."
    return "Fórmulas detectadas:\n" + "\n".join(lines)


def suggest_formula_column(sheet: SheetModel) -> str:
    """Columna con más fórmulas, útil para preguntas sin pista."""
    if not sheet.formulas:
        return ""
    counts: dict[str, int] = {}
    for reference in sheet.formulas:
        match = re.fullmatch(r"([A-Z]{1,3})(\d+)", reference)
        if match:
            counts[match.group(1)] = counts.get(match.group(1), 0) + 1
    if not counts:
        return ""
    best_letter = max(counts.items(), key=lambda item: item[1])[0]
    for column in sheet.columns:
        if column.letter.upper() == best_letter:
            return column.name
    return best_letter


__all__ = [
    "FUNCTION_INFO",
    "FormulaExplanation",
    "explain_formula",
    "explain_workbook_formulas",
    "formulas_in_column",
    "suggest_formula_column",
]
