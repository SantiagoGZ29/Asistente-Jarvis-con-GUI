"""Pruebas del análisis local y de solo lectura de libros de Excel."""

from __future__ import annotations

import re
import zipfile
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

from jarvis.core.errors import SpreadsheetError, SpreadsheetFormatError
from jarvis.spreadsheets import (
    SpreadsheetInfo,
    WorkbookLoader,
    WorkbookModel,
    describe_workbook,
    is_spreadsheet_path,
    load_workbook_model,
)
from jarvis.spreadsheets.data_quality import (
    diagnose_sheet,
    diagnose_workbook,
    format_issues,
)
from jarvis.spreadsheets.formula_explainer import (
    explain_formula,
    explain_workbook_formulas,
)
from jarvis.spreadsheets.models import ColumnModel, SheetModel
from jarvis.spreadsheets.query_engine import (
    QueryEngine,
    QueryFilter,
    QueryPlan,
    resolve_column,
    resolve_sheet,
)
from jarvis.spreadsheets.query_planner import local_plan
from jarvis.spreadsheets.spreadsheet_assistant import SpreadsheetAssistant
from jarvis.spreadsheets.workbook_loader import LoadLimits

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


@pytest.fixture
def book_path(tmp_path: Path) -> Path:
    return write_book(tmp_path / "Seguimiento tareas.xlsx")


@pytest.fixture
def book(book_path: Path) -> WorkbookModel:
    return load_workbook_model(book_path)


@pytest.fixture
def assistant(book: WorkbookModel) -> SpreadsheetAssistant:
    return SpreadsheetAssistant(workbook=book, today=TODAY)


def plan(**kwargs) -> QueryPlan:
    return QueryPlan(**kwargs)


def execute(book: WorkbookModel, **kwargs):
    return QueryEngine().execute(book, plan(**kwargs), today=TODAY)


# ======================================================================
# Carga y estructura
# ======================================================================
def test_carga_estructura_encabezado_tabla_y_hoja_oculta(book: WorkbookModel) -> None:
    sheet = book.sheet("Tareas")[0]
    assert sheet is not None
    assert sheet.header_row == 3
    assert sheet.headers[:3] == ("ID", "Tarea", "Área")
    assert sheet.records == 7
    assert sheet.data_range is not None
    assert sheet.data_range.ref == "A3:M11"
    assert [table.name for table in sheet.tables] == ["TablaTareas"]
    assert "A2:M2" in sheet.merged_ranges
    assert sheet.formula_count == 8
    assert sheet.purpose == "tareas"
    assert sheet.empty_rows == 1

    assert [item.name for item in book.sheets] == ["Tareas", "Resumen", "Oculta"]
    assert [item.name for item in book.hidden_sheets] == ["Oculta"]
    assert book.formula_count == 8
    assert book.records == 7


def test_no_mezcla_hojas_ocultas_sin_pedirlo(book: WorkbookModel) -> None:
    visible = resolve_sheet(book, "")
    assert visible.name == "Tareas"

    with pytest.raises(Exception) as info:
        resolve_sheet(book, "Oculta")
    assert "oculta" in str(info.value).lower()

    hidden = resolve_sheet(book, "Oculta", include_hidden=True)
    assert hidden.name == "Oculta"


def test_describe_el_libro_sin_ia(book: WorkbookModel) -> None:
    text = describe_workbook(book)
    assert "Seguimiento tareas.xlsx" in text
    assert "Tareas" in text
    assert "7 registros" in text
    assert "oculta" in text.lower()


def test_rechaza_xls_y_archivos_inexistentes(tmp_path: Path) -> None:
    old = tmp_path / "antiguo.xls"
    old.write_bytes(b"no es un xlsx")
    with pytest.raises(SpreadsheetFormatError) as info:
        WorkbookLoader().load(old)
    assert "guárdalo como .xlsx" in info.value.user_message

    with pytest.raises(SpreadsheetError):
        WorkbookLoader().load(tmp_path / "fantasma.xlsx")

    assert is_spreadsheet_path("libro.XLSX")
    assert is_spreadsheet_path("macro.xlsm")
    assert not is_spreadsheet_path("libro.xls")
    assert not is_spreadsheet_path("documento.docx")


def test_limites_de_carga_marcan_analisis_parcial(book_path: Path) -> None:
    limited = WorkbookLoader(
        LoadLimits(max_rows=2, max_columns=3, max_cells=20)
    ).load(book_path)

    assert limited.truncated is True
    sheet = limited.sheet("Tareas")[0]
    assert sheet is not None
    assert sheet.truncated is True
    assert len(sheet.rows) <= 2
    assert len(sheet.columns) <= 3
    assert any("límite" in warning.lower() for warning in limited.warnings)


def test_tarjeta_de_interfaz_resume_el_libro(book: WorkbookModel) -> None:
    info = SpreadsheetInfo.from_model(book, status="LISTO", opened=True)
    assert info.name == "Seguimiento tareas.xlsx"
    assert info.rows == 7
    assert info.current_sheet == "Tareas"
    assert info.tables == 1
    assert info.formulas == 8
    assert info.hidden_sheets == ("Oculta",)
    assert info.sheets[0].columns == 13


# ======================================================================
# Consultas deterministas
# ======================================================================
def test_conteos_sumas_promedios_minimos_y_maximos(book: WorkbookModel) -> None:
    total = execute(book, operation="count")
    assert total.value == 7

    pendientes = execute(
        book,
        operation="count",
        filters=(QueryFilter("Estado", "eq", "Pendiente"),),
    )
    assert pendientes.value == 5

    suma = execute(book, operation="sum", column="Importe")
    assert suma.value == pytest.approx(7550.5)
    assert "7.550,5" in suma.text

    media = execute(book, operation="mean", column="Importe")
    assert media.value == pytest.approx(7550.5 / 7)

    minimo = execute(book, operation="min", column="Importe")
    maximo = execute(book, operation="max", column="Importe")
    assert minimo.value == pytest.approx(300)
    assert maximo.value == pytest.approx(2000)


def test_porcentajes_valores_distintos_y_duplicados(book: WorkbookModel) -> None:
    porcentaje = execute(
        book,
        operation="percentage",
        filters=(QueryFilter("Estado", "eq", "Pendiente"),),
    )
    assert porcentaje.value == pytest.approx(5 / 7 * 100)
    assert "5 de 7" in porcentaje.text

    areas = execute(book, operation="count_distinct", column="Área")
    assert areas.value == 3

    duplicados = execute(book, operation="duplicates", column="ID")
    assert duplicados.matched >= 1
    assert "duplicados" in duplicados.text.lower()


def test_filtros_categoricos_fechas_y_combinados(book: WorkbookModel) -> None:
    octubre = execute(
        book,
        operation="count",
        filters=(
            QueryFilter("Fecha inicio", "between", ("2026-10-01", "2026-10-31")),
        ),
    )
    assert octubre.value == 5

    combinado = execute(
        book,
        operation="count",
        filters=(
            QueryFilter("Área", "eq", "Gestión"),
            QueryFilter("Estado", "eq", "Pendiente"),
        ),
    )
    assert combinado.value == 3

    texto = execute(
        book,
        operation="count",
        filters=(QueryFilter("Tarea", "contains", "informe"),),
    )
    assert texto.value == 2


def test_agrupaciones_por_area_y_por_mes(book: WorkbookModel) -> None:
    por_area = execute(book, operation="group_count", group_by="Área")
    counts = {group.label: group.count for group in por_area.groups}
    assert counts == {"Gestión": 4, "Operaciones": 2, "Ventas": 1}

    por_mes = execute(
        book,
        operation="group_count",
        group_by="__month__",
        column="Fecha inicio",
    )
    meses = {group.label: group.count for group in por_mes.groups}
    assert meses["10/2026"] == 5
    assert meses["09/2026"] == 1
    assert meses["(sin fecha)"] == 1

    suma_area = execute(
        book,
        operation="group_sum",
        group_by="Área",
        column="Importe",
    )
    totales = {group.label: group.total for group in suma_area.groups}
    assert totales["Gestión"] == pytest.approx(4250)
    assert totales["Operaciones"] == pytest.approx(3000.5)


def test_vencimientos_proximos_y_fechas_ausentes(book: WorkbookModel) -> None:
    vencidas = execute(book, operation="date_due", today=TODAY)
    assert vencidas.value == 3

    proximas = execute(
        book, operation="date_upcoming", days=20, today=TODAY
    )
    assert proximas.value == 2
    assert all(group.label for group in proximas.groups)

    sin_fecha = execute(
        book,
        operation="missing",
        column="Fecha límite",
    )
    assert sin_fecha.value == 1

    entre = execute(
        book,
        operation="date_between",
        date_field="Fecha límite",
        date_from=date(2026, 11, 1),
        date_to=date(2026, 11, 30),
    )
    assert entre.value == 4


def test_listado_con_fuentes_y_limite(book: WorkbookModel) -> None:
    resultado = execute(
        book,
        operation="list",
        filters=(QueryFilter("Área", "eq", "Operaciones"),),
        limit=20,
    )
    assert resultado.matched == 2
    assert resultado.columns[0] == "Fila"
    assert any("Fuente: hoja Tareas" in source for source in resultado.sources)
    assert "A6:M7" in resultado.sources[0]


def test_columnas_ambiguas_piden_aclaracion(book: WorkbookModel) -> None:
    sheet = book.sheet("Tareas")[0]
    assert sheet is not None
    # «Cálculo» coincide parcialmente con dos columnas.
    with pytest.raises(Exception) as info:
        resolve_column(sheet, "Cálculo g")
    assert "Cálculo gestión" in str(info.value)


def test_plan_local_entiende_preguntas_en_espanol(book: WorkbookModel) -> None:
    sheet_plan = local_plan(book, "¿Cuántas tareas están vencidas?", today=TODAY)
    assert sheet_plan is not None
    assert sheet_plan.operation == "date_due"

    group_plan = local_plan(book, "Agrupa las tareas por área", today=TODAY)
    assert group_plan is not None
    assert group_plan.operation == "group_count"
    assert group_plan.group_by == "Área"

    sum_plan = local_plan(book, "Agrupa y suma el importe por área", today=TODAY)
    assert sum_plan is not None
    assert sum_plan.operation == "group_sum"
    assert sum_plan.column == "Importe"


# ======================================================================
# Calidad de datos
# ======================================================================
def test_diagnostico_de_calidad_detecta_problemas(book: WorkbookModel) -> None:
    problemas = diagnose_workbook(book)
    texto = format_issues(problemas)

    assert problemas
    assert "duplicad" in texto.lower()
    assert "vacías" in texto.lower()
    assert "vacías dentro de los datos" in texto.lower()
    assert "texto" in texto.lower()
    assert "Tareas" in texto


def test_calidad_detecta_fechas_de_texto_y_encabezados_repetidos() -> None:
    sheet = SheetModel(
        name="Prueba",
        index=0,
        header_row=1,
        headers=("Nombre", "Nombre", "Revisión", "Importe"),
        columns=(
            ColumnModel("Nombre", "A", 0, "text"),
            ColumnModel("Nombre", "B", 1, "text"),
            ColumnModel("Revisión", "C", 2, "text"),
            ColumnModel("Importe", "D", 3, "number"),
        ),
        rows=(
            ("Ana", "Ana", "2026-10-01", 10),
            ("Luis", "Luis", "2026-10-02", 20),
            ("Marta", "Marta", "pendiente", 30),
            ("Eva", "Eva", "n/a", 40),
        ),
        row_numbers=(2, 3, 4, 5),
    )
    problemas = diagnose_sheet(sheet)
    texto = " ".join(problema.describe() for problema in problemas)

    assert "Encabezados repetidos" in texto
    assert "Fechas guardadas como texto" in texto


# ======================================================================
# Fórmulas
# ======================================================================
def test_explica_formula_localizada_y_sin_resultado_cacheado(
    book: WorkbookModel,
) -> None:
    sheet = book.sheet("Tareas")[0]
    assert sheet is not None

    explicacion = explain_formula(sheet, column_name="Cálculo")
    assert explicacion.cell == "L4"
    assert "SI.ERROR" in explicacion.formula
    assert "REDONDEAR" in explicacion.functions
    assert explicacion.has_cached is False
    assert "no contiene un resultado calculado" in explicacion.text
    assert "No inventaré un resultado" in explicacion.text
    assert "Fuente: hoja Tareas, celda L4" in explicacion.source


def test_explica_funcion_de_suma_condicional(book: WorkbookModel) -> None:
    sheet = book.sheet("Tareas")[0]
    assert sheet is not None

    explicacion = explain_formula(sheet, reference="M4")
    assert "SUMAR.SI" in explicacion.functions
    assert "SUMAR.SI" in explicacion.text
    assert "C4:C11" in explicacion.text or "$C$4:$C$11" in explicacion.text


def test_resumen_de_formulas_del_libro(book: WorkbookModel) -> None:
    texto = explain_workbook_formulas(book)
    assert "Tareas" in texto
    assert "8 fórmulas" in texto
    assert "SI.ERROR" in texto
    assert "SUMAR.SI" in texto


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


def test_lee_resultado_cacheado_sin_recalcular(
    book_path: Path, tmp_path: Path
) -> None:
    cached_path = patch_cached_value(
        book_path, tmp_path / "cacheado.xlsx", value="250"
    )
    cached_book = load_workbook_model(cached_path)
    sheet = cached_book.sheet("Tareas")[0]
    assert sheet is not None

    explicacion = explain_formula(sheet, column_name="Cálculo")
    assert explicacion.has_cached is True
    assert explicacion.cached_value == 250
    assert "último resultado guardado por Excel es 250" in explicacion.text


# ======================================================================
# Asistente
# ======================================================================
def test_asistente_responde_con_calculos_y_fuentes(
    assistant: SpreadsheetAssistant,
) -> None:
    answer = assistant.ask("¿Cuántas tareas están vencidas?")
    assert answer.grounded is True
    assert "3 registros vencidos" in answer.text
    assert any(source.heading == "Tareas" for source in answer.sources)

    suma = assistant.ask("Suma el importe total de Tareas")
    assert "7.550,5" in suma.text
    assert "Python" in (suma.notice or "") or suma.grounded

    grupos = assistant.ask("Agrupa las tareas por área")
    assert "Gestión" in grupos.text
    assert "Operaciones" in grupos.text


def test_asistente_mantiene_contexto_y_lo_reinicia(
    assistant: SpreadsheetAssistant, book: WorkbookModel, tmp_path: Path
) -> None:
    primera = assistant.ask("¿Cuántas tareas están vencidas?")
    assert "3" in primera.text

    seguimiento = assistant.ask("¿Y cuántas corresponden a Gestión?")
    assert "2" in seguimiento.text
    assert "Gestión" in seguimiento.text

    otra = write_book(tmp_path / "Otro libro.xlsx")
    assistant.load(load_workbook_model(otra))
    assert assistant.history == []
    assert assistant.last_plan is None


def test_asistente_pide_hoja_cuando_hay_varias_con_datos(
    tmp_path: Path,
) -> None:
    workbook = Workbook()
    enero = workbook.active
    enero.title = "Enero"
    enero.append(["ID", "Tarea"])
    enero.append([1, "Una"])
    febrero = workbook.create_sheet("Febrero")
    febrero.append(["ID", "Tarea"])
    febrero.append([2, "Otra"])
    path = tmp_path / "Dos hojas.xlsx"
    workbook.save(path)

    assistant = SpreadsheetAssistant(
        workbook=load_workbook_model(path), today=TODAY
    )
    answer = assistant.ask("¿Cuántas tareas hay?")
    assert answer.grounded is False
    assert "varias hojas con datos" in answer.text
    assert "Enero" in answer.text and "Febrero" in answer.text
    assert answer.options

    con_hoja = assistant.ask("¿Cuántas tareas hay en la hoja Enero?")
    assert con_hoja.grounded is True
    assert "1" in con_hoja.text


def test_asistente_explica_formulas_y_calidad(
    assistant: SpreadsheetAssistant,
) -> None:
    formula = assistant.ask("Explícame la fórmula de la columna Cálculo")
    assert "SI.ERROR" in formula.text
    assert any("L4" in source.ref for source in formula.sources)

    calidad = assistant.ask("Revisa la calidad de los datos")
    assert "problemas" in calidad.text.lower()
    assert "duplicad" in calidad.text.lower()


def test_asistente_resumen_y_recomendaciones(
    assistant: SpreadsheetAssistant,
) -> None:
    resumen = assistant.ask("Resume la hoja Tareas")
    assert "Tareas" in resumen.text
    assert "registros" in resumen.text

    recomendacion = assistant.ask("¿Qué debería revisar primero del libro?")
    assert recomendacion.grounded is True
    assert recomendacion.text


def test_limite_de_tiempo_avisa_antes_de_consultar_a_gemini(
    book: WorkbookModel,
) -> None:
    assistant = SpreadsheetAssistant(
        workbook=book, today=TODAY, timeout_s=0
    )

    answer = assistant.ask("dime algo bonito del libro")

    assert answer.grounded is False
    assert "tiempo máximo" in answer.text


def test_asistente_sin_libro_lo_explica() -> None:
    assistant = SpreadsheetAssistant()
    with pytest.raises(Exception) as info:
        assistant.ask("¿Cuántas tareas hay?")
    assert "libro" in str(info.value).lower()


def test_analysis_info_alimenta_el_panel(assistant: SpreadsheetAssistant) -> None:
    assistant.ask("Agrupa las tareas por área")
    info = assistant.analysis_info(sheet="Tareas")
    assert info.kind == "spreadsheet"
    assert info.title
    assert info.metrics
    assert info.columns
    assert info.rows
    assert info.sources
    assert "Python" in info.note
