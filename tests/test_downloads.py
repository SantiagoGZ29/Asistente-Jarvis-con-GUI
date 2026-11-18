"""Pruebas de búsqueda y apertura de documentos de Descargas."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.errors import DocumentError
from jarvis.documents.downloads import (
    AMBIGUOUS,
    MATCH,
    NO_FOLDER,
    NOT_FOUND,
    DownloadsLibrary,
    normalize_name,
    score_name,
    windows_downloads_folder,
)


def write_docx(path: Path, content: bytes = b"PK\x03\x04") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def downloads(tmp_path: Path) -> Path:
    root = tmp_path / "Descargas"
    root.mkdir()
    return root


def library(root: Path, **kwargs) -> DownloadsLibrary:
    return DownloadsLibrary(root=root, **kwargs)


def test_encuentra_sin_extension_ni_tildes(downloads: Path) -> None:
    objetivo = write_docx(downloads / "Planificación del Proyecto.docx")

    result = library(downloads).search("planificacion del proyecto")

    assert result.decision == MATCH
    assert result.selected is not None
    assert result.selected.path == objetivo


def test_ignora_mayusculas_y_guiones_bajos(downloads: Path) -> None:
    objetivo = write_docx(downloads / "INFORME_SEMANAL_MARZO.DOCX")

    result = library(downloads).search("informe semanal marzo")

    assert result.decision == MATCH
    assert result.selected.path == objetivo


def test_nombre_dictado_con_extension(downloads: Path) -> None:
    objetivo = write_docx(downloads / "Manual de mi Jarvis.docx")

    result = library(downloads).search("manual de mi jarvis.docx")

    assert result.decision == MATCH
    assert result.selected.path == objetivo


def test_ambiguedad_pide_aclaracion(downloads: Path) -> None:
    write_docx(downloads / "Informe enero.docx")
    write_docx(downloads / "Informe febrero.docx")

    result = library(downloads).search("informe")

    assert result.decision == AMBIGUOUS
    assert result.selected is None
    assert len(result.candidates) == 2
    assert "¿Cuál quieres?" in result.describe()


def test_no_elige_entre_proyectos_parecidos(downloads: Path) -> None:
    write_docx(downloads / "Proyecto alfa.docx")
    write_docx(downloads / "Proyecto beta.docx")

    result = library(downloads).search("proyecto")

    assert result.decision == AMBIGUOUS
    assert result.selected is None


def test_coincidencia_clara_con_competencia_lejana(downloads: Path) -> None:
    objetivo = write_docx(downloads / "Informe semanal marzo.docx")
    write_docx(downloads / "Presupuesto 2026.docx")

    result = library(downloads).search("informe semanal")

    assert result.decision == MATCH
    assert result.selected.path == objetivo
    assert result.best.score >= 0.86


def test_sin_resultados(downloads: Path) -> None:
    write_docx(downloads / "Otra cosa.docx")

    result = library(downloads).search("presupuesto anual")

    assert result.decision == NOT_FOUND
    assert result.matches == ()
    assert "No encontré" in result.describe()


def test_consulta_vacia_pide_nombre(downloads: Path) -> None:
    result = library(downloads).search("   ")

    assert result.decision == NOT_FOUND
    assert "Dime el nombre" in (result.warning or "")


def test_respeta_la_profundidad_maxima(downloads: Path) -> None:
    write_docx(downloads / "nivel1" / "nivel2" / "informe profundo.docx")

    poco = library(downloads, max_depth=1).search("informe profundo")
    suficiente = library(downloads, max_depth=2).search("informe profundo")

    assert poco.decision == NOT_FOUND
    assert suficiente.decision == MATCH


def test_limite_de_archivos_avisa(downloads: Path) -> None:
    write_docx(downloads / "uno.docx")
    write_docx(downloads / "dos.docx")
    write_docx(downloads / "tres.docx")

    result = library(downloads, max_files=1).search("uno")

    assert result.truncated is True
    assert "límite" in (result.warning or "")


def test_ignora_no_docx_temporales_y_ocultos(downloads: Path) -> None:
    write_docx(downloads / "notas.txt")
    write_docx(downloads / "~$informe.docx")
    write_docx(downloads / ".informe.docx")
    objetivo = write_docx(downloads / "informe bueno.docx")

    result = library(downloads).search("informe")

    assert result.selected is not None
    assert result.selected.path == objetivo


def test_no_sale_de_subcarpetas_ocultas(downloads: Path) -> None:
    write_docx(downloads / ".oculta" / "informe secreto.docx")
    write_docx(downloads / "informe publico.docx")

    result = library(downloads).search("informe")

    assert result.selected is not None
    assert result.selected.path.name == "informe publico.docx"


def test_carpeta_inexistente_se_informa(tmp_path: Path) -> None:
    result = library(tmp_path / "no-existe").search("informe")

    assert result.decision == NO_FOLDER
    assert "no existe" in result.describe()


def test_usa_la_carpeta_conocida_inyectada(tmp_path: Path) -> None:
    root = tmp_path / "Descargas"
    root.mkdir()
    write_docx(root / "manual.docx")

    library_ = DownloadsLibrary(known_folder=lambda: root)
    result = library_.search("manual")

    assert library_.root == root
    assert result.decision == MATCH


def test_encuentra_un_libro_excel_sin_extension_ni_tildes(
    downloads: Path,
) -> None:
    objetivo = write_docx(downloads / "sub" / "Planificación_Tareas.xlsx")
    library_ = DownloadsLibrary(
        root=downloads, extensions=(".docx", ".xlsx", ".xlsm")
    )

    result = library_.search("planificacion tareas")

    assert result.decision == MATCH
    assert result.selected is not None
    assert result.selected.path == objetivo
    assert result.selected.kind == "spreadsheet"


def test_ambiguedad_entre_word_y_excel_muestra_ambos(downloads: Path) -> None:
    write_docx(downloads / "Seguimiento marzo.docx")
    write_docx(downloads / "Seguimiento marzo.xlsx")
    library_ = DownloadsLibrary(
        root=downloads, extensions=(".docx", ".xlsx", ".xlsm")
    )

    result = library_.search("seguimiento marzo")

    assert result.decision == AMBIGUOUS
    assert len(result.candidates) == 2
    assert {match.kind for match in result.candidates} == {
        "document",
        "spreadsheet",
    }


def test_abre_excel_y_rechaza_xls_antiguo(downloads: Path) -> None:
    abiertos: list[Path] = []
    library_ = DownloadsLibrary(
        root=downloads,
        extensions=(".docx", ".xlsx", ".xlsm"),
        opener=abiertos.append,
    )
    libro = write_docx(downloads / "datos.xlsx")
    antiguo = write_docx(downloads / "datos.xls")

    assert library_.open_document(libro) == libro
    assert abiertos == [libro]

    with pytest.raises(DocumentError) as info:
        library_.open_document(antiguo)
    assert ".xlsx/.xlsm" in info.value.user_message


def test_abre_con_aplicacion_inyectada(downloads: Path) -> None:
    objetivo = write_docx(downloads / "manual.docx")
    abiertos: list[Path] = []

    library_ = DownloadsLibrary(root=downloads, opener=abiertos.append)
    devuelto = library_.open_document(objetivo)

    assert devuelto == objetivo
    assert abiertos == [objetivo]


def test_no_abre_archivos_fuera_de_descargas(tmp_path: Path) -> None:
    root = tmp_path / "Descargas"
    root.mkdir()
    fuera = write_docx(tmp_path / "secreto.docx")
    library_ = DownloadsLibrary(root=root, opener=lambda path: None)

    with pytest.raises(DocumentError) as info:
        library_.open_document(fuera)

    assert "solo abre archivos .docx" in info.value.user_message


def test_no_abre_otros_formatos(downloads: Path) -> None:
    archivo = write_docx(downloads / "notas.txt")
    library_ = DownloadsLibrary(root=downloads, opener=lambda path: None)

    with pytest.raises(DocumentError):
        library_.open_document(archivo)


def test_no_abre_rutas_inexistentes(downloads: Path) -> None:
    library_ = DownloadsLibrary(root=downloads, opener=lambda path: None)

    with pytest.raises(DocumentError):
        library_.open_document(downloads / "fantasma.docx")


def test_fallo_del_sistema_al_abrir_se_explica(downloads: Path) -> None:
    objetivo = write_docx(downloads / "manual.docx")

    def falla(path: Path) -> None:
        raise OSError("no hay asociación")

    library_ = DownloadsLibrary(root=downloads, opener=falla)

    with pytest.raises(DocumentError) as info:
        library_.open_document(objetivo)

    assert "no pudo abrirlo" in info.value.user_message


def test_normalizacion_y_puntuacion() -> None:
    assert normalize_name("Planificación_Proyecto.DOCX") == "planificacion proyecto"
    assert score_name("manual", "Manual de mi Jarvis.docx") >= 0.9
    assert score_name("manual de mi jarvis", "Manual de mi Jarvis.docx") == 1.0
    assert score_name("presupuesto", "Informe anual.docx") < 0.5
    assert score_name("", "manual.docx") == 0.0


def test_la_carpeta_real_de_windows_existe_si_esta_disponible() -> None:
    folder = windows_downloads_folder()
    if folder is not None:
        assert folder.is_dir()
