"""Ayudas compartidas para construir libros .xlsx temporales en las pruebas."""

from __future__ import annotations

import re
import zipfile
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

TODAY = date(2026, 11, 10)


def write_book(path: Path) -> Path:
    """Libro realista con título, encabezado en la fila 3, tabla y fórmulas."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Tareas"

    sheet.merge_cells("A2:M2")
    sheet["A2"] = "LISTADO DE TAREAS · OCTUBRE 2026"

    headers = [
        "ID",
        "Tarea",
        "Área",
        "Responsable",
        "Estado",
        "Prioridad",
        "Fecha inicio",
        "Fecha límite",
        "Importe",
        "Avance",
        "Notas",
        "Cálculo",
        "Cálculo gestión",
    ]
    for column, value in enumerate(headers, start=1):
        sheet.cell(row=3, column=column, value=value)

    rows = [
        (
            1,
            "Preparar informe",
            "Gestión",
            "Ana",
            "Pendiente",
            "Alta",
            date(2026, 10, 1),
            date(2026, 11, 1),
            1000,
            0.25,
            "",
        ),
        (
            2,
            "Revisar presupuesto",
            "Gestión",
            "Luis",
            "En curso",
            "Media",
            date(2026, 10, 5),
            date(2026, 11, 12),
            2000,
            0.5,
            "",
        ),
        (
            3,
            "Actualizar web",
            "Operaciones",
            "Ana",
            "Hecha",
            "Baja",
            date(2026, 9, 1),
            date(2026, 10, 15),
            1500,
            1,
            "",
        ),
        (
            4,
            "Llamar cliente",
            "Operaciones",
            "Marta",
            "Pendiente",
            "Alta",
            date(2026, 10, 10),
            date(2026, 11, 5),
            "1.500,50",
            0.1,
            "",
        ),
        None,  # fila completamente vacía dentro de los datos
        (
            2,
            "Revisar presupuesto",
            "Gestión",
            None,
            "Pendiente",
            None,
            date(2026, 10, 6),
            date(2026, 11, 25),
            "500",
            0.2,
            "",
        ),
        (
            6,
            "Enviar factura",
            "Gestión",
            "Luis",
            "Pendiente",
            "Alta",
            "2026-10-20",
            date(2026, 10, 30),
            "750",
            0.3,
            "",
        ),
        (
            7,
            "Preparar informe",
            "Ventas",
            "Ana",
            "Pendiente",
            "Media",
            None,
            None,
            300,
            0.4,
            "",
        ),
    ]
    for offset, values in enumerate(rows, start=4):
        if values is None:
            continue
        for column, value in enumerate(values, start=1):
            sheet.cell(row=offset, column=column, value=value)

    for row in [*range(4, 8), *range(9, 12)]:
        sheet.cell(
            row=row,
            column=12,
            value=f"=SI.ERROR(REDONDEAR(I{row}*J{row};2);0)",
        )
    sheet["M4"] = '=SUMAR.SI($C$4:$C$11;"Gestión";$I$4:$I$11)'

    table = Table(displayName="TablaTareas", ref="A3:M11")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium9",
        showRowStripes=True,
    )
    sheet.add_table(table)

    summary = workbook.create_sheet("Resumen")
    summary.append(["Métrica", "Valor"])

    hidden = workbook.create_sheet("Oculta")
    hidden.append(["Secreto"])
    hidden.append(["no mezclar"])
    hidden.sheet_state = "hidden"

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def patch_cached_value(
    source: Path,
    target: Path,
    *,
    sheet_xml: str = "xl/worksheets/sheet1.xml",
    reference: str = "L4",
    value: str = "250",
) -> Path:
    """Inserta un resultado cacheado como lo haría Excel al guardar."""
    with zipfile.ZipFile(source) as origin, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as destination:
        for item in origin.infolist():
            data = origin.read(item.filename)
            if item.filename == sheet_xml:
                text = data.decode("utf-8")
                pattern = re.compile(
                    rf'(<c r="{reference}"[^>]*>)(.*?)(</c>)', re.DOTALL
                )
                match = pattern.search(text)
                assert match is not None
                body = match.group(2)
                if "<v></v>" in body:
                    body = body.replace("<v></v>", f"<v>{value}</v>")
                else:
                    body += f"<v>{value}</v>"
                text = (
                    text[: match.start()]
                    + match.group(1)
                    + body
                    + match.group(3)
                    + text[match.end() :]
                )
                data = text.encode("utf-8")
            destination.writestr(item, data)
    return target
