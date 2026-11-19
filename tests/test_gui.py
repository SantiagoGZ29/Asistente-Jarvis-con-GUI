"""Pruebas de humo de la interfaz gráfica (sin pantalla real)."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from jarvis.config import Settings  # noqa: E402
from jarvis.core.consent import (  # noqa: E402
    ALL_REQUESTS,
    ELEVENLABS_STT,
    ELEVENLABS_TTS,
    GEMINI_CHAT,
    GEMINI_DOCUMENT,
    GEMINI_GOOGLE,
    GEMINI_SPREADSHEET,
)
from jarvis.core.controller import ChatMessage, DocumentInfo, GoogleInfo  # noqa: E402
from jarvis.core.states import AssistantState, MicState  # noqa: E402
from jarvis.spreadsheets.models import (  # noqa: E402
    AnalysisInfo,
    Metric,
    SheetInfo,
    SpreadsheetInfo,
)
from jarvis.ui.gui import (  # noqa: E402
    MainWindow,
    PrivacyDialog,
    _apply_preferences,
    _load_consent,
    _save_consent,
)
from jarvis.ui.widgets import GooglePanel  # noqa: E402

ALL_FALSE = {key: False for key in ALL_REQUESTS}


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication(["pytest-jarvis"])
    yield app
    app.processEvents()


def pump(app: QApplication, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def make_window(
    qt_app: QApplication,
    tmp_path: Path,
    *,
    settings: Settings | None = None,
    grants: dict[str, bool] | None = None,
) -> tuple[MainWindow, QSettings]:
    store = QSettings(str(tmp_path / "gui.ini"), QSettings.Format.IniFormat)
    window = MainWindow(
        settings or Settings(env_file=None, speak_responses=False),
        ALL_FALSE if grants is None else grants,
        store=store,
        device_probe=lambda: (),
    )
    return window, store


def test_ventana_sin_claves_se_construye_y_cierra_limpio(
    qt_app: QApplication, tmp_path: Path
) -> None:
    window, _store = make_window(qt_app, tmp_path)
    window.show()
    assert window.controller is not None
    assert window.controller.wait_for_idle(3.0)
    pump(qt_app)

    assert "Mi Jarvis" in window.windowTitle()
    assert window.state_pill.text() == "PREPARADO"
    assert window._chips["gemini"].text() == "GEMINI · SIN CLAVE"
    assert window._chips["voice"].text() == "VOZ · SIN CLAVE"
    assert window.controller.mic_state is MicState.UNAVAILABLE
    assert window.document_card.name.text() == "Sin documento"
    # El saludo inicial aparece aunque no haya claves ni voz.
    assert len(window._bubbles) >= 1
    assert window.empty_hint.isHidden()

    window.close()
    assert window.controller is None
    assert window.bridge._closed is True


def test_senales_actualizan_estado_conversacion_y_tarjetas(
    qt_app: QApplication, tmp_path: Path
) -> None:
    window, _store = make_window(qt_app, tmp_path)
    window.show()

    window.bridge.stateChanged.emit(
        AssistantState.READY, AssistantState.LISTENING, "prueba"
    )
    assert window.state_pill.text() == "ESCUCHANDO"
    assert window.orb._state is AssistantState.LISTENING

    window.bridge.partial.emit("hola mun")
    assert window.partial.text() == "hola mun"
    window.bridge.partial.emit("")
    assert window.partial.text() != "hola mun"

    window.bridge.message.emit(ChatMessage("user", "hola"))
    window.bridge.message.emit(
        ChatMessage("jarvis", "respuesta breve", ("P1",))
    )
    assert len(window._bubbles) == 2
    assert window.empty_hint.isHidden()

    window.bridge.health.emit(
        {
            "gemini": "configurado",
            "voice": "configurada",
            "mic_state": "STREAMING",
            "mic_running": True,
            "microphone": "Micrófono de prueba",
            "stt": "realtime",
            "state": "LISTENING",
        }
    )
    assert window._chips["gemini"].text() == "GEMINI · LISTO"
    assert "ESCUCHANDO" in window._chips["mic"].text()
    assert window._chips["stt"].text() == "STT · REALTIME"

    window.bridge.choices.emit(("manual", "otro"))
    assert len(window.choices._buttons) == 2
    assert not window.choices.isHidden()

    window.bridge.document.emit(
        DocumentInfo(
            path="C:/Downloads/manual.docx",
            name="manual.docx",
            title="Manual",
            paragraphs=4,
            tables=1,
            sections=2,
            characters=1234,
            opened=True,
        )
    )
    assert window.document_card.name.text() == "manual.docx"
    assert "abierto en Word" in window.document_card.meta.text()

    window.bridge.micTest.emit(
        {"ok": False, "message": "No se detectó voz en la prueba."}
    )
    assert not window.notice.isHidden()
    assert "No se detectó voz" in window.notice.text()

    window.close()


def test_cierre_es_idempotente_y_no_deja_controlador(
    qt_app: QApplication, tmp_path: Path
) -> None:
    window, _store = make_window(qt_app, tmp_path)
    window.show()
    window.close()
    window.close()
    assert window.controller is None


def test_tarjeta_de_excel_y_panel_de_analisis(
    qt_app: QApplication, tmp_path: Path
) -> None:
    window, _store = make_window(qt_app, tmp_path)
    window.show()

    info = SpreadsheetInfo(
        path=str(tmp_path / "Seguimiento tareas.xlsx"),
        name="Seguimiento tareas.xlsx",
        title="Seguimiento de tareas",
        status="LISTO",
        sheets=(
            SheetInfo(
                name="Tareas",
                hidden=False,
                rows=7,
                columns=13,
                formulas=8,
                tables=1,
                purpose="tareas",
            ),
        ),
        rows=7,
        columns=13,
        formulas=8,
        tables=1,
        current_sheet="Tareas",
        opened=True,
    )
    window.bridge.spreadsheet.emit(info)
    pump(qt_app)

    assert window.spreadsheet_card.name.text() == "Seguimiento tareas.xlsx"
    assert not window.spreadsheet_card.isHidden()
    assert window.document_card.isHidden()
    assert "hoja actual: Tareas" in window.spreadsheet_card.meta.text()
    assert "8 fórmulas" in window.spreadsheet_card.meta.text()
    assert "abierto en Excel" in window.spreadsheet_card.meta.text()

    analysis = AnalysisInfo(
        title="Tareas por área",
        metrics=(Metric("Registros", "7"), Metric("Grupos", "3")),
        columns=("Área", "Registros"),
        rows=(("Gestión", "4"), ("Operaciones", "2")),
        sources=("Fuente: hoja Tareas, rango A3:M11",),
        alerts=("Hay una fila vacía.",),
        note="Cálculo realizado en Python, de solo lectura.",
        sheet="Tareas",
    )
    window.bridge.analysis.emit(analysis)
    pump(qt_app)

    assert not window.analysis.isHidden()
    assert window.analysis.heading.text() == "Tareas por área"
    assert window.analysis.table.rowCount() == 2
    assert window.analysis.table.columnCount() == 2
    assert window.analysis.table.item(0, 0).text() == "Gestión"
    assert "Fuente: hoja Tareas" in window.analysis.sources.text()
    assert "fila vacía" in window.analysis.alerts.text()

    window.bridge.spreadsheet.emit(None)
    pump(qt_app)
    assert window.spreadsheet_card.isHidden()
    assert not window.document_card.isHidden()
    assert window.analysis.isHidden()

    window.close()


def test_consentimiento_y_preferencias_se_guardan(
    qt_app: QApplication, tmp_path: Path
) -> None:
    store = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    grants = {
        ELEVENLABS_STT.key: True,
        ELEVENLABS_TTS.key: False,
        GEMINI_DOCUMENT.key: True,
        GEMINI_CHAT.key: False,
        GEMINI_SPREADSHEET.key: True,
        GEMINI_GOOGLE.key: False,
    }
    _save_consent(store, grants)
    assert _load_consent(store) == grants

    store.setValue("audio/input_device", "MME|Micrófono|1")
    store.setValue("behavior/auto_listen", False)
    store.setValue("behavior/speak_responses", False)
    settings = Settings(env_file=None)
    applied = _apply_preferences(settings, store)

    assert applied.input_device_key == "MME|Micrófono|1"
    assert applied.auto_listen is False
    assert applied.speak_responses is False

    forced = _apply_preferences(
        replace(settings, speak_responses=False), store, force_text=True
    )
    assert forced.speak_responses is False


def test_privacidad_empieza_sin_marcar_y_modo_texto_deniega_todo(
    qt_app: QApplication,
) -> None:
    dialog = PrivacyDialog(Settings(env_file=None))
    assert dialog.choices() == ALL_FALSE
    assert dialog.text_only is False
    dialog._choose_text_only()
    assert dialog.text_only is True
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert not any(dialog.choices().values())


def test_panel_google_cambia_de_estado(qt_app: QApplication) -> None:
    panel = GooglePanel()

    assert panel.status.text() == "SIN CONFIGURAR"
    assert panel.connect_button.text() == "CONECTAR GOOGLE"
    assert panel.connect_button.isEnabled() is False
    assert panel.mail_button.isEnabled() is False
    assert "Gmail" in panel.mail_state.text()

    panel.set_google(
        GoogleInfo(configured=True, connected=False, problem="Revisa el .env.")
    )
    assert panel.status.text() == "CONFIGURADO · SIN AUTORIZAR"
    assert panel.connect_button.isEnabled() is True
    assert panel.mail_button.isEnabled() is False
    assert panel.problem.isHidden() is False

    panel.set_google(
        GoogleInfo(
            configured=True,
            connected=True,
            account="ana@example.com",
            mail_count=20,
            unread=3,
            mail_query="Bandeja de entrada de Gmail: 20 correos",
            calendar_count=2,
            calendar_query="Hoy: 2 eventos",
            next_event="«Revisión» · mar 17 nov 2026, 09:00–10:00",
        )
    )
    assert panel.status.text() == "CONECTADO"
    assert "ana@example.com" in panel.account.text()
    assert "3 sin leer" in panel.mail_state.text()
    assert "Hoy: 2 eventos" in panel.calendar_state.text()
    assert "Revisión" in panel.calendar_state.text()
    assert panel.connect_button.isEnabled() is False
    assert panel.mail_button.isEnabled() is True
    assert panel.problem.isHidden() is True

    panel.set_google(GoogleInfo(configured=True, connected=False, busy=True))
    assert panel.status.text() == "CONECTANDO…"
    assert panel.connect_button.text() == "CONECTANDO…"
    assert panel.connect_button.isEnabled() is False


def test_ventana_actualiza_el_panel_google(
    qt_app: QApplication, tmp_path: Path
) -> None:
    window, _store = make_window(qt_app, tmp_path)
    window.show()
    assert window.controller.wait_for_idle(3.0)
    pump(qt_app)

    window.bridge.google.emit(
        GoogleInfo(configured=True, connected=True, account="ana@example.com")
    )
    pump(qt_app)

    assert window.google_panel.status.text() == "CONECTADO"
    assert "ana@example.com" in window.google_panel.account.text()

    window.close()
