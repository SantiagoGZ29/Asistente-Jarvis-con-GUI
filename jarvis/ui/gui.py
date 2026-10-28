"""Ventana principal de Mi Jarvis (PySide6).

La interfaz es deliberadamente delgada: dibuja lo que el controlador publica y
reenvía las órdenes del usuario. Ningún proveedor, micrófono o documento se
toca desde el hilo de Qt; el puente convierte los callbacks en señales.
"""

from __future__ import annotations

import sys
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from jarvis import __app_name__
from jarvis.audio.devices import InputDevice, list_input_devices
from jarvis.config import Settings
from jarvis.core.consent import (
    ALL_REQUESTS,
    ELEVENLABS_STT,
    ELEVENLABS_TTS,
    GEMINI_CHAT,
    GEMINI_DOCUMENT,
    ConsentManager,
    ConsentRequest,
)
from jarvis.core.controller import ChatMessage, Controller, DocumentInfo
from jarvis.core.logging_setup import get_logger
from jarvis.core.states import (
    STATE_HINTS,
    STATE_LABELS,
    AssistantState,
    MicState,
)
from jarvis.documents.downloads import windows_downloads_folder
from jarvis.ui import theme
from jarvis.ui.bridge import ControllerBridge
from jarvis.ui.widgets import (
    ChoicesPanel,
    ConversationBubble,
    DocumentCard,
    OrbWidget,
    VoicePanel,
)

logger = get_logger("gui")

_ORG = "MiJarvis"
_APP = "MiJarvis"

_CONSENT_ROWS: tuple[tuple[ConsentRequest, str], ...] = (
    (ELEVENLABS_STT, "Micrófono: transcribir mi voz con ElevenLabs"),
    (ELEVENLABS_TTS, "Voz: leer las respuestas con ElevenLabs"),
    (GEMINI_DOCUMENT, "Documentos: analizar fragmentos con Google Gemini"),
    (GEMINI_CHAT, "Conversación: enviar mis mensajes a Google Gemini"),
)

_STATE_COLORS: dict[AssistantState, str] = {
    AssistantState.STARTING: theme.BLUE,
    AssistantState.READY: "#38BDF8",
    AssistantState.LISTENING: theme.CYAN,
    AssistantState.USER_SPEAKING: "#67E8F9",
    AssistantState.PROCESSING: theme.VIOLET,
    AssistantState.JARVIS_SPEAKING: "#818CF8",
    AssistantState.PAUSED: "#94A3B8",
    AssistantState.ERROR: theme.RED,
}

_PLACEHOLDER = "Habla o escribe una orden…"


# ----------------------------------------------------------------------
# Preferencias persistentes
# ----------------------------------------------------------------------
def _default_store() -> QSettings:
    return QSettings(_ORG, _APP)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def _load_consent(store: QSettings) -> dict[str, bool]:
    return {
        key: _as_bool(store.value(f"consent/{key}"), False)
        for key in ALL_REQUESTS
    }


def _save_consent(store: QSettings, grants: dict[str, bool]) -> None:
    for key in ALL_REQUESTS:
        store.setValue(f"consent/{key}", bool(grants.get(key, False)))
    store.sync()


def _apply_preferences(
    settings: Settings, store: QSettings, *, force_text: bool = False
) -> Settings:
    """Aplica las preferencias guardadas por la interfaz sobre ``.env``."""
    device = store.value("audio/input_device", settings.input_device_key)
    auto_listen = _as_bool(
        store.value("behavior/auto_listen"), settings.auto_listen
    )
    speak = settings.speak_responses
    if not force_text:
        speak = _as_bool(
            store.value("behavior/speak_responses"), settings.speak_responses
        )
    return replace(
        settings,
        input_device_key=str(device or ""),
        auto_listen=auto_listen,
        speak_responses=speak,
    )


def _pill_style(color: str) -> str:
    value = QColor(color)
    return (
        "QLabel#StatePill {"
        f" background-color: rgba({value.red()}, {value.green()}, {value.blue()}, 38);"
        f" border: 1px solid rgba({value.red()}, {value.green()}, {value.blue()}, 165);"
        f" color: {color};"
        " }"
    )


def _chip_color(widget: QLabel, color: str) -> None:
    widget.setStyleSheet(f"color: {color};")


def _shorten(text: str, limit: int = 34) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


# ----------------------------------------------------------------------
# Diálogos
# ----------------------------------------------------------------------
class ConsentRow(QWidget):
    """Una casilla de permiso con su explicación completa."""

    def __init__(
        self,
        request: ConsentRequest,
        label: str,
        *,
        checked: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.request = request
        self.checkbox = QCheckBox(label)
        self.checkbox.setChecked(bool(checked))
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        detail = QLabel(request.description)
        detail.setObjectName("Hint")
        detail.setWordWrap(True)
        detail.setContentsMargins(26, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 6)
        layout.setSpacing(4)
        layout.addWidget(self.checkbox)
        layout.addWidget(detail)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, value: bool) -> None:
        self.checkbox.setChecked(bool(value))


def _dialog_scroll(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


class PrivacyDialog(QDialog):
    """Consentimiento explícito de primer arranque; todo empieza sin marcar."""

    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Privacidad y primeros pasos")
        self.setModal(True)
        self.setMinimumSize(620, 560)
        self.resize(660, 620)
        self._rows: list[ConsentRow] = []
        self.text_only = False

        title = QLabel("ANTES DE EMPEZAR")
        title.setObjectName("AppTitle")
        lead = QLabel(
            "Jarvis puede escuchar tu voz y hablar, pero solo si lo autorizas. "
            "Estas casillas empiezan desmarcadas: elige exactamente qué "
            "permites. Puedes cambiarlo después en Ajustes."
        )
        lead.setWordWrap(True)
        lead.setObjectName("Hint")

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(2, 2, 10, 2)
        body.setSpacing(8)
        for request, label in _CONSENT_ROWS:
            row = ConsentRow(request, label)
            self._rows.append(row)
            body.addWidget(row)
        body.addStretch(1)

        privacy = QLabel(
            "Las claves se leen del archivo .env y nunca se muestran ni se "
            "registran. Jarvis no activa facturación ni planes de pago."
        )
        privacy.setObjectName("Hint")
        privacy.setWordWrap(True)

        text_only = QPushButton("Solo modo texto")
        text_only.setObjectName("Ghost")
        text_only.clicked.connect(self._choose_text_only)
        start = QPushButton("Empezar")
        start.setObjectName("Primary")
        start.setDefault(True)
        start.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(text_only)
        buttons.addStretch(1)
        buttons.addWidget(start)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(lead)
        layout.addWidget(_dialog_scroll(content), 1)
        layout.addWidget(privacy)
        layout.addLayout(buttons)

    def _choose_text_only(self) -> None:
        self.text_only = True
        for row in self._rows:
            row.set_checked(False)
        self.accept()

    def choices(self) -> dict[str, bool]:
        return {row.request.key: row.is_checked() for row in self._rows}


class SettingsDialog(QDialog):
    """Permisos y preferencias que se pueden cambiar sin editar el .env."""

    def __init__(
        self,
        current: dict[str, bool],
        *,
        auto_listen: bool,
        speak_responses: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajustes de Jarvis")
        self.setModal(True)
        self.setMinimumSize(620, 560)
        self.resize(660, 620)
        self._rows: list[ConsentRow] = []

        title = QLabel("PRIVACIDAD Y COMPORTAMIENTO")
        title.setObjectName("AppTitle")

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(2, 2, 10, 2)
        body.setSpacing(10)

        consent_title = QLabel("PERMISOS")
        consent_title.setObjectName("SectionTitle")
        body.addWidget(consent_title)
        for request, label in _CONSENT_ROWS:
            row = ConsentRow(
                request, label, checked=bool(current.get(request.key, False))
            )
            self._rows.append(row)
            body.addWidget(row)

        behavior = QLabel("COMPORTAMIENTO")
        behavior.setObjectName("SectionTitle")
        self.auto_listen = QCheckBox("Activar la escucha al iniciar")
        self.auto_listen.setChecked(bool(auto_listen))
        self.speak_responses = QCheckBox("Leer las respuestas en voz alta")
        self.speak_responses.setChecked(bool(speak_responses))
        note = QLabel(
            "El cambio de voz se aplica al reiniciar Jarvis. El micrófono y los "
            "permisos se aplican al guardar."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        body.addSpacing(6)
        body.addWidget(behavior)
        body.addWidget(self.auto_listen)
        body.addWidget(self.speak_responses)
        body.addWidget(note)
        body.addStretch(1)

        cancel = QPushButton("Cancelar")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Guardar")
        save.setObjectName("Primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(_dialog_scroll(content), 1)
        layout.addLayout(buttons)

    def consent(self) -> dict[str, bool]:
        return {row.request.key: row.is_checked() for row in self._rows}


class HelpDialog(QDialog):
    """Ayuda breve y atajos, sin menús ocultos."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ayuda de Jarvis")
        self.setModal(True)
        self.setMinimumSize(600, 520)
        self.resize(660, 580)

        title = QLabel("QUÉ PUEDES PEDIRME")
        title.setObjectName("AppTitle")
        text = QLabel(
            "Habla o escribe con naturalidad. Ejemplos:\n\n"
            "  •  «Abre el documento informe de Descargas»\n"
            "  •  «Resume el documento»\n"
            "  •  «¿Qué fechas y plazos aparecen?»\n"
            "  •  «Extrae las acciones pendientes»\n"
            "  •  «Pausa» / «Reanuda» / «Detente» / «Cancela»\n\n"
            "Si hay varios documentos parecidos, Jarvis te preguntará cuál "
            "abrir; nunca elige uno por su cuenta. Solo abre archivos .docx "
            "que estén realmente en Descargas.\n\n"
            "ATAJOS\n\n"
            "  Ctrl+M   Pausar o reanudar la escucha\n"
            "  Ctrl+.   Detener la voz de Jarvis\n"
            "  Ctrl+T   Probar el micrófono\n"
            "  Ctrl+O   Elegir un .docx manualmente\n"
            "  Ctrl+,   Abrir Ajustes\n"
            "  F1       Esta ayuda\n\n"
            "PRIVACIDAD\n\n"
            "El audio se envía a ElevenLabs solo cuando el micrófono está "
            "activo. Los documentos y la conversación se envían a Gemini solo "
            "si lo autorizas. Puedes retirar los permisos en Ajustes; el modo "
            "texto y la apertura local de documentos siguen funcionando."
        )
        text.setWordWrap(True)
        text.setObjectName("Hint")
        text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(2, 2, 10, 2)
        body.addWidget(text)
        body.addStretch(1)

        close = QPushButton("Cerrar")
        close.setObjectName("Primary")
        close.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(_dialog_scroll(content), 1)
        layout.addLayout(buttons)


# ----------------------------------------------------------------------
# Ventana principal
# ----------------------------------------------------------------------
class MainWindow(QMainWindow):
    """Ventana del asistente; todo el estado visible viene del controlador."""

    devicesReady = Signal(object, str)

    def __init__(
        self,
        settings: Settings,
        grants: dict[str, bool] | None = None,
        *,
        document: str | Path | None = None,
        store: QSettings | None = None,
        device_probe: Callable[[], tuple[InputDevice, ...]] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._grants = dict(grants or {})
        self._store = store or _default_store()
        self._device_probe = device_probe or list_input_devices
        self._bridge = ControllerBridge(self)
        self._controller: Controller | None = None
        self._consent: ConsentManager | None = None
        self._state = AssistantState.STARTING
        self._mic_state = MicState.UNAVAILABLE
        self._mic_running = False
        self._devices: tuple[InputDevice, ...] = ()
        self._probing = False
        self._closing = False
        self._bubbles: list[ConversationBubble] = []
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self._clear_notice)

        self.setWindowTitle(f"{__app_name__} · Asistente personal")
        self.setMinimumSize(900, 640)
        self.resize(1240, 820)
        self.setStyleSheet(theme.STYLESHEET)

        self._build_ui()
        self._wire()
        self._restore_geometry()
        self._start_controller(document)

    # ------------------------------------------------------------------
    # API para pruebas
    # ------------------------------------------------------------------
    @property
    def controller(self) -> Controller | None:
        return self._controller

    @property
    def bridge(self) -> ControllerBridge:
        return self._bridge

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([520, 680])
        root.addWidget(splitter, 1)

        self.notice = QLabel("")
        self.notice.setObjectName("Notice")
        self.notice.setWordWrap(True)
        self.notice.hide()
        root.addWidget(self.notice)

        root.addWidget(self._build_controls())
        self.setCentralWidget(central)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("HeaderBar")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(18, 13, 18, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("MI JARVIS")
        title.setObjectName("AppTitle")
        subtitle = QLabel("ASISTENTE PERSONAL · VOZ, DOCUMENTOS Y DESCARGAS")
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box)
        top.addStretch(1)

        self.state_pill = QLabel(STATE_LABELS[AssistantState.STARTING])
        self.state_pill.setObjectName("StatePill")
        self.state_pill.setStyleSheet(
            _pill_style(_STATE_COLORS[AssistantState.STARTING])
        )
        top.addWidget(self.state_pill, 0, Qt.AlignmentFlag.AlignVCenter)

        help_button = QPushButton("Ayuda")
        help_button.setObjectName("Ghost")
        help_button.setToolTip("Ayuda y atajos (F1)")
        help_button.clicked.connect(self._open_help)
        settings_button = QPushButton("Ajustes")
        settings_button.setObjectName("Ghost")
        settings_button.setToolTip("Privacidad y preferencias (Ctrl+,)")
        settings_button.clicked.connect(self._open_settings)
        top.addWidget(help_button)
        top.addWidget(settings_button)
        layout.addLayout(top)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self._chips: dict[str, QLabel] = {}
        for key, text in (
            ("gemini", "GEMINI · —"),
            ("voice", "VOZ · —"),
            ("mic", "MIC · —"),
            ("stt", "STT · —"),
        ):
            chip = QLabel(text)
            chip.setObjectName("Chip")
            chip.setSizePolicy(
                QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
            )
            self._chips[key] = chip
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)
        return header

    def _build_left(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.orb = OrbWidget()
        self.orb.setMinimumHeight(220)
        layout.addWidget(self.orb, 3)

        partial_card = QFrame()
        partial_card.setObjectName("Panel")
        card_layout = QVBoxLayout(partial_card)
        card_layout.setContentsMargins(16, 12, 16, 14)
        card_layout.setSpacing(4)
        caption = QLabel("TU VOZ · TRANSCRIPCIÓN EN VIVO")
        caption.setObjectName("SectionTitle")
        self.partial = QLabel(_PLACEHOLDER)
        self.partial.setObjectName("Partial")
        self.partial.setWordWrap(True)
        self.partial.setMinimumHeight(42)
        self.partial.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.partial.setStyleSheet(f"color: {theme.DIM};")
        card_layout.addWidget(caption)
        card_layout.addWidget(self.partial)
        layout.addWidget(partial_card)

        voices = QHBoxLayout()
        voices.setSpacing(12)
        self.user_panel = VoicePanel(
            "TU VOZ", theme.USER_COLOR, "Micrófono sin iniciar"
        )
        self.jarvis_panel = VoicePanel(
            "JARVIS", theme.JARVIS_COLOR, "Sin reproducción"
        )
        voices.addWidget(self.user_panel, 1)
        voices.addWidget(self.jarvis_panel, 1)
        layout.addLayout(voices)
        panel.setMinimumWidth(330)
        return panel

    def _build_right(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        conversation = QFrame()
        conversation.setObjectName("Panel")
        conv_layout = QVBoxLayout(conversation)
        conv_layout.setContentsMargins(16, 12, 16, 12)
        conv_layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("CONVERSACIÓN")
        title.setObjectName("SectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        clear = QPushButton("Limpiar vista")
        clear.setObjectName("Ghost")
        clear.setToolTip("Oculta los mensajes de la ventana; no borra el documento")
        clear.clicked.connect(self._clear_conversation)
        header.addWidget(clear)
        conv_layout.addLayout(header)

        self.conversation = QScrollArea()
        self.conversation.setWidgetResizable(True)
        self.conversation.setFrameShape(QFrame.Shape.NoFrame)
        self.conversation.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        container = QWidget()
        self.conv_layout = QVBoxLayout(container)
        self.conv_layout.setContentsMargins(2, 2, 8, 2)
        self.conv_layout.setSpacing(8)
        self.empty_hint = QLabel(
            "Aún no hay mensajes. Habla o escribe para empezar. "
            "Puedes pedirme que abra un documento de Descargas."
        )
        self.empty_hint.setObjectName("Hint")
        self.empty_hint.setWordWrap(True)
        self.conv_layout.addWidget(self.empty_hint)
        self.conv_layout.addStretch(1)
        self.conversation.setWidget(container)
        conv_layout.addWidget(self.conversation, 1)
        layout.addWidget(conversation, 1)

        self.choices = ChoicesPanel()
        self.choices.chosen.connect(self._choose_document)
        layout.addWidget(self.choices)

        self.document_card = DocumentCard()
        self.document_card.pickRequested.connect(self._pick_document)
        layout.addWidget(self.document_card)
        panel.setMinimumWidth(340)
        return panel

    def _build_controls(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("Panel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.mic_button = QPushButton("Activar micrófono")
        self.mic_button.setObjectName("Primary")
        self.mic_button.setToolTip("Pausar o reanudar la escucha (Ctrl+M)")
        self.mic_button.clicked.connect(self._toggle_mic)

        self.stop_button = QPushButton("Detener voz")
        self.stop_button.setObjectName("Danger")
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip("Detener la reproducción (Ctrl+.)")
        self.stop_button.clicked.connect(self._stop_speech)

        self.test_button = QPushButton("Probar micrófono")
        self.test_button.setToolTip("Grabar dos segundos y medir el nivel real")
        self.test_button.clicked.connect(self._test_microphone)

        row.addWidget(self.mic_button)
        row.addWidget(self.stop_button)
        row.addWidget(self.test_button)
        row.addStretch(1)

        device_label = QLabel("MICRÓFONO")
        device_label.setObjectName("SectionTitle")
        row.addWidget(device_label)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(210)
        self.device_combo.setMaximumWidth(340)
        self.device_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.device_combo.addItem("Detectando micrófonos…", "")
        self.device_combo.currentIndexChanged.connect(self._device_changed)
        row.addWidget(self.device_combo)
        refresh = QPushButton("↻")
        refresh.setObjectName("Ghost")
        refresh.setToolTip("Volver a buscar micrófonos")
        refresh.clicked.connect(self._refresh_devices)
        row.addWidget(refresh)
        layout.addLayout(row)

        send_row = QHBoxLayout()
        send_row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "Escribe una orden o pregunta y pulsa Enter…"
        )
        self.input.returnPressed.connect(self._send_text)
        self.send_button = QPushButton("Enviar")
        self.send_button.setObjectName("Primary")
        self.send_button.clicked.connect(self._send_text)
        send_row.addWidget(self.input, 1)
        send_row.addWidget(self.send_button)
        layout.addLayout(send_row)

        self.status = QLabel(STATE_HINTS[AssistantState.STARTING])
        self.status.setObjectName("Hint")
        layout.addWidget(self.status)
        return frame

    # ------------------------------------------------------------------
    # Conexiones
    # ------------------------------------------------------------------
    def _wire(self) -> None:
        bridge = self._bridge
        bridge.stateChanged.connect(self._on_state)
        bridge.micChanged.connect(self._on_mic)
        bridge.userLevel.connect(self._on_user_level)
        bridge.jarvisLevel.connect(self._on_jarvis_level)
        bridge.partial.connect(self._on_partial)
        bridge.message.connect(self._on_message)
        bridge.notice.connect(self._on_notice)
        bridge.error.connect(self._on_error)
        bridge.health.connect(self._on_health)
        bridge.document.connect(self._on_document)
        bridge.choices.connect(self._on_choices)
        bridge.pickRequested.connect(self._pick_document)
        bridge.exitRequested.connect(self._request_close)
        bridge.micTest.connect(self._on_mic_test)
        bridge.consentRequested.connect(self._on_consent_requested)
        self.devicesReady.connect(self._on_devices_ready)

        self._shortcuts: list[QShortcut] = []
        for sequence, slot in (
            ("Ctrl+M", self._toggle_mic),
            ("Ctrl+.", self._stop_speech),
            ("Ctrl+T", self._test_microphone),
            ("Ctrl+O", self._pick_document),
            ("Ctrl+,", self._open_settings),
            ("F1", self._open_help),
            ("Escape", self._stop_speech),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

    # ------------------------------------------------------------------
    # Arranque y cierre
    # ------------------------------------------------------------------
    def _start_controller(self, document: str | Path | None) -> None:
        self._consent = ConsentManager(self._bridge.ask)
        for key, granted in self._grants.items():
            if granted:
                self._consent.grant(key)
            else:
                self._consent.deny(key)
        self._controller = Controller(
            self._settings,
            callbacks=self._bridge.callbacks(),
            consent=self._consent,
        )
        self._controller.start()
        if document:
            self._controller.load_document(document)
        self._refresh_devices()

    def _restore_geometry(self) -> None:
        geometry = self._store.value("window/geometry")
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except Exception:  # pragma: no cover - geometría corrupta
                pass

    def _save_geometry(self) -> None:
        try:
            self._store.setValue("window/geometry", self.saveGeometry())
            self._store.sync()
        except Exception:  # pragma: no cover - almacenamiento de solo lectura
            pass

    def _request_close(self) -> None:
        QTimer.singleShot(0, self.close)

    def closeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        if self._closing:
            event.accept()
            return
        self._closing = True
        self._save_geometry()
        self._notice_timer.stop()
        self._bridge.cancel_all()
        controller, self._controller = self._controller, None
        if controller is not None:
            try:
                controller.shutdown()
            except Exception:  # pragma: no cover - cierre defensivo
                logger.exception("Fallo al cerrar el controlador")
        self._consent = None
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Señales del controlador
    # ------------------------------------------------------------------
    def _on_state(self, old, new, reason: str) -> None:
        self._state = new
        self.state_pill.setText(STATE_LABELS.get(new, str(new)))
        self.state_pill.setStyleSheet(
            _pill_style(_STATE_COLORS.get(new, theme.BLUE))
        )
        self.orb.set_state(new)
        self.status.setText(STATE_HINTS.get(new, ""))
        self.stop_button.setEnabled(new is AssistantState.JARVIS_SPEAKING)
        if new is AssistantState.JARVIS_SPEAKING:
            self.jarvis_panel.set_caption("Reproduciendo la respuesta")
        elif new in (AssistantState.LISTENING, AssistantState.READY):
            self.jarvis_panel.set_caption("Sin reproducción")
        if new in (
            AssistantState.LISTENING,
            AssistantState.READY,
            AssistantState.PAUSED,
        ):
            self._set_placeholder()

    def _on_mic(self, state, detail: str) -> None:
        self._mic_state = state
        detail = detail or ""
        self.user_panel.set_caption(detail or "Micrófono sin iniciar")
        if state is MicState.SPEECH:
            self.mic_button.setText("Pausar escucha")
        elif state in (MicState.MUTED,):
            self.mic_button.setText("Reanudar escucha")
        elif state in (MicState.UNAVAILABLE, MicState.ERROR, MicState.DETECTED):
            self.mic_button.setText("Activar micrófono")
        else:
            self.mic_button.setText("Pausar escucha")

    def _on_user_level(self, level: float) -> None:
        self.user_panel.set_level(level)
        self.orb.set_user_level(level)

    def _on_jarvis_level(self, level: float) -> None:
        self.jarvis_panel.set_level(level)
        self.orb.set_jarvis_level(level)

    def _on_partial(self, text: str) -> None:
        if text:
            self.partial.setText(text)
            self.partial.setStyleSheet(f"color: {theme.TEXT};")
        else:
            self._set_placeholder()

    def _set_placeholder(self) -> None:
        self.partial.setText(_PLACEHOLDER)
        self.partial.setStyleSheet(f"color: {theme.DIM};")

    def _on_message(self, message: ChatMessage) -> None:
        self.empty_hint.hide()
        bubble = ConversationBubble(message)
        self.conv_layout.insertWidget(self.conv_layout.count() - 1, bubble)
        self._bubbles.append(bubble)
        while len(self._bubbles) > 250:
            old = self._bubbles.pop(0)
            old.setParent(None)
            old.deleteLater()
        if getattr(message, "role", "") == "user":
            self._set_placeholder()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.conversation.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear_conversation(self) -> None:
        for bubble in self._bubbles:
            bubble.setParent(None)
            bubble.deleteLater()
        self._bubbles = []
        self.empty_hint.show()

    def _on_notice(self, message: str) -> None:
        self._show_notice(message, error=False)

    def _on_error(self, message: str) -> None:
        self._show_notice(message, error=True)

    def _show_notice(self, message: str, *, error: bool) -> None:
        clean = " ".join((message or "").split())
        if not clean:
            return
        self.notice.setText(clean)
        self.notice.setObjectName("NoticeError" if error else "Notice")
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.notice.show()
        self._notice_timer.start(9000 if error else 6500)

    def _clear_notice(self) -> None:
        self.notice.hide()
        self.notice.setText("")

    def _on_health(self, report: dict[str, Any]) -> None:
        gemini = report.get("gemini") == "configurado"
        voice = report.get("voice") == "configurada"
        mic_state = report.get("mic_state", "")
        mic_running = bool(report.get("mic_running"))
        device = report.get("microphone") or "sin dispositivo"
        stt = str(report.get("stt") or "off")
        self._mic_running = mic_running
        detail = report.get("mic_detail") or device
        self.user_panel.set_caption(str(detail))

        self._chips["gemini"].setText(
            "GEMINI · " + ("LISTO" if gemini else "SIN CLAVE")
        )
        _chip_color(
            self._chips["gemini"], theme.GREEN if gemini else theme.AMBER
        )
        self._chips["gemini"].setToolTip(
            "Gemini está configurado en .env"
            if gemini
            else "Añade GEMINI_API_KEY al archivo .env"
        )

        self._chips["voice"].setText(
            "VOZ · " + ("LISTA" if voice else "SIN CLAVE")
        )
        _chip_color(self._chips["voice"], theme.GREEN if voice else theme.AMBER)
        self._chips["voice"].setToolTip(
            "ElevenLabs puede leer las respuestas"
            if voice
            else "Añade ELEVENLABS_API_KEY y ELEVENLABS_VOICE_ID al .env"
        )

        if mic_running and mic_state == MicState.SPEECH.value:
            mic_text, mic_color = "MIC · VOZ", theme.CYAN
        elif mic_running:
            mic_text, mic_color = "MIC · ESCUCHANDO", theme.GREEN
        elif mic_state == MicState.MUTED.value:
            mic_text, mic_color = "MIC · PAUSA", theme.AMBER
        elif mic_state == MicState.DETECTED.value:
            mic_text, mic_color = "MIC · DETECTADO", theme.AMBER
        elif mic_state == MicState.ERROR.value:
            mic_text, mic_color = "MIC · ERROR", theme.RED
        else:
            mic_text, mic_color = "MIC · SIN DISPOSITIVO", theme.RED
        label = _shorten(device, 26)
        self._chips["mic"].setText(f"{mic_text} · {label}" if label else mic_text)
        _chip_color(self._chips["mic"], mic_color)
        self._chips["mic"].setToolTip(device)

        stt_text = {
            "realtime": "REALTIME",
            "batch": "BATCH",
            "off": "OFF",
        }.get(stt, stt.upper())
        self._chips["stt"].setText(f"STT · {stt_text}")
        _chip_color(
            self._chips["stt"],
            theme.GREEN if stt in {"realtime", "batch"} else theme.DIM,
        )

    def _on_document(self, info: DocumentInfo | None) -> None:
        self.document_card.set_document(info)

    def _on_choices(self, names: Iterable[str]) -> None:
        self.choices.set_choices(tuple(names or ()))

    def _on_mic_test(self, result: dict[str, Any]) -> None:
        message = str(result.get("message") or "")
        self._show_notice(message, error=not bool(result.get("ok")))
        self.test_button.setEnabled(True)
        self.test_button.setText("Probar micrófono")

    def _on_consent_requested(self, key: str) -> None:
        request = ALL_REQUESTS.get(key)
        if request is None:
            self._bridge.resolve(key, False)
            return
        answer = QMessageBox.question(
            self,
            f"Permiso: {request.provider}",
            f"{request.description}\n\n¿Permites esta acción?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        accepted = answer == QMessageBox.StandardButton.Yes
        self._bridge.resolve(key, accepted)
        if self._consent is not None:
            if accepted:
                self._consent.grant(request)
            else:
                self._consent.deny(request)
        self._store.setValue(f"consent/{key}", accepted)
        self._store.sync()

    # ------------------------------------------------------------------
    # Acciones del usuario
    # ------------------------------------------------------------------
    def _toggle_mic(self) -> None:
        controller = self._controller
        if controller is None:
            return
        if self._mic_state in (
            MicState.MUTED,
            MicState.UNAVAILABLE,
            MicState.ERROR,
            MicState.DETECTED,
        ):
            controller.resume_mic()
        else:
            controller.pause_mic()

    def _stop_speech(self) -> None:
        if self._controller is not None:
            self._controller.stop_speech()

    def _test_microphone(self) -> None:
        if self._controller is None:
            return
        self.test_button.setEnabled(False)
        self.test_button.setText("Probando 2 s…")
        self._show_notice(
            "Prueba de micrófono: habla ahora durante dos segundos.", error=False
        )
        self._controller.test_microphone(2.0)

    def _send_text(self) -> None:
        text = self.input.text().strip()
        if not text or self._controller is None:
            return
        self.input.clear()
        self._controller.send_text(text)

    def _pick_document(self) -> None:
        if self._controller is None:
            return
        start = self._downloads_start()
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "Elegir documento de Word",
            str(start),
            "Documentos de Word (*.docx)",
        )
        if path:
            self._controller.load_document(path)

    @staticmethod
    def _downloads_start() -> Path:
        try:
            folder = windows_downloads_folder()
        except Exception:  # pragma: no cover - API de Windows no disponible
            folder = None
        return folder or Path.home()

    def _choose_document(self, index: int) -> None:
        if self._controller is not None:
            self._controller.choose_candidate(index)

    def _device_changed(self, index: int) -> None:
        key = self.device_combo.itemData(index) or ""
        self._settings = replace(self._settings, input_device_key=str(key))
        self._store.setValue("audio/input_device", str(key))
        self._store.sync()
        if self._controller is not None:
            self._controller.select_device(str(key))

    def _refresh_devices(self) -> None:
        if self._probing:
            return
        self._probing = True
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItem("Detectando micrófonos…", "")
        self.device_combo.blockSignals(False)

        def probe() -> None:
            error = ""
            try:
                devices = tuple(self._device_probe())
            except Exception:  # pragma: no cover - backend roto
                devices = ()
                error = "No se pudieron enumerar los micrófonos."
            self._probing = False
            if not self._closing:
                self.devicesReady.emit(devices, error)

        threading.Thread(target=probe, name="jarvis-devices", daemon=True).start()

    def _on_devices_ready(
        self, devices: tuple[InputDevice, ...], error: str
    ) -> None:
        if self._closing:
            return
        self._devices = tuple(devices or ())
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        if self._devices:
            self.device_combo.addItem("Predeterminado del sistema", "")
            for device in self._devices:
                suffix = " · predeterminado" if device.is_default else ""
                self.device_combo.addItem(
                    f"{device.short_label} — {device.hostapi}{suffix}", device.key
                )
            saved = self._settings.input_device_key
            index = self.device_combo.findData(saved) if saved else 0
            self.device_combo.setCurrentIndex(index if index >= 0 else 0)
            self.device_combo.setEnabled(True)
        else:
            self.device_combo.addItem(
                error or "Sin micrófonos detectados", ""
            )
            self.device_combo.setEnabled(False)
        self.device_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Ajustes y ayuda
    # ------------------------------------------------------------------
    def _open_settings(self) -> None:
        current = {
            key: bool(self._consent and self._consent.is_granted(key))
            for key in ALL_REQUESTS
        }
        dialog = SettingsDialog(
            current,
            auto_listen=self._settings.auto_listen,
            speak_responses=self._settings.speak_responses,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_settings(dialog)

    def _apply_settings(self, dialog: SettingsDialog) -> None:
        grants = dialog.consent()
        previous = {
            key: bool(self._consent and self._consent.is_granted(key))
            for key in ALL_REQUESTS
        }
        for key, granted in grants.items():
            if self._consent is None:
                continue
            if granted:
                self._consent.grant(key)
            else:
                self._consent.deny(key)
        self._grants = grants
        _save_consent(self._store, grants)

        stt_key = ELEVENLABS_STT.key
        stt_changed = grants.get(stt_key, False) != previous.get(stt_key, False)
        controller = self._controller
        if controller is not None and stt_changed:
            if grants.get(stt_key):
                controller.restart_microphone()
            else:
                controller.stop_microphone()

        auto_listen = dialog.auto_listen.isChecked()
        if auto_listen != self._settings.auto_listen:
            self._settings = replace(self._settings, auto_listen=auto_listen)
            self._store.setValue("behavior/auto_listen", auto_listen)
            self._store.sync()
            if controller is not None:
                if auto_listen and grants.get(stt_key, False):
                    controller.resume_mic()
                elif not auto_listen:
                    controller.pause_mic()

        speak = dialog.speak_responses.isChecked()
        if speak != self._settings.speak_responses:
            self._settings = replace(self._settings, speak_responses=speak)
            self._store.setValue("behavior/speak_responses", speak)
            self._store.sync()
            self._show_notice(
                "La lectura en voz alta se aplicará al reiniciar Jarvis.",
                error=False,
            )

    def _open_help(self) -> None:
        HelpDialog(self).exec()


# ----------------------------------------------------------------------
# Entrada
# ----------------------------------------------------------------------
def run_gui(
    settings: Settings,
    document: str | Path | None = None,
    *,
    force_text: bool = False,
    store: QSettings | None = None,
) -> int:
    """Abre la ventana principal. Devuelve el código de salida de Qt."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName(__app_name__)
        app.setOrganizationName(_ORG)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)

    store = store or _default_store()
    accepted = _as_bool(store.value("privacy/accepted"), False)
    grants = _load_consent(store)
    if not accepted:
        dialog = PrivacyDialog(settings)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return 0
        grants = dialog.choices()
        store.setValue("privacy/accepted", True)
        store.setValue(
            "behavior/auto_listen",
            False if dialog.text_only else settings.auto_listen,
        )
        if not force_text:
            store.setValue(
                "behavior/speak_responses",
                False if dialog.text_only else settings.speak_responses,
            )
        store.sync()
        _save_consent(store, grants)

    settings = _apply_preferences(settings, store, force_text=force_text)
    window = MainWindow(settings, grants, document=document, store=store)
    window.show()
    return int(app.exec())


__all__ = [
    "HelpDialog",
    "MainWindow",
    "PrivacyDialog",
    "SettingsDialog",
    "run_gui",
]
