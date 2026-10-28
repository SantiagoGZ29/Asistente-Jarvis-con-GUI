"""Piezas visuales dibujadas con QPainter para Mi Jarvis."""

from __future__ import annotations

import math
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.states import AssistantState
from jarvis.ui import theme

_STATE_COLORS: dict[AssistantState, QColor] = {
    AssistantState.STARTING: QColor(theme.BLUE),
    AssistantState.READY: QColor(56, 189, 248),
    AssistantState.LISTENING: QColor(theme.CYAN),
    AssistantState.USER_SPEAKING: QColor(103, 232, 249),
    AssistantState.PROCESSING: QColor(theme.VIOLET),
    AssistantState.JARVIS_SPEAKING: QColor(129, 140, 248),
    AssistantState.PAUSED: QColor(100, 116, 139),
    AssistantState.ERROR: QColor(theme.RED),
}


def _lerp_color(current: QColor, target: QColor, factor: float = 0.14) -> QColor:
    return QColor(
        int(current.red() + (target.red() - current.red()) * factor),
        int(current.green() + (target.green() - current.green()) * factor),
        int(current.blue() + (target.blue() - current.blue()) * factor),
        int(current.alpha() + (target.alpha() - current.alpha()) * factor),
    )


class OrbWidget(QWidget):
    """Orbe central animado; su pulso sigue el nivel real del audio."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._state = AssistantState.STARTING
        self._color = QColor(theme.BLUE)
        self._target = QColor(theme.BLUE)
        self._user = 0.0
        self._jarvis = 0.0
        self._amplitude = 0.0
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def sizeHint(self) -> QSize:
        return QSize(360, 360)

    def set_state(self, state: AssistantState) -> None:
        self._state = state
        self._target = _STATE_COLORS.get(state, QColor(theme.BLUE))

    def set_levels(self, user: float, jarvis: float) -> None:
        self._user = max(0.0, min(1.0, float(user)))
        self._jarvis = max(0.0, min(1.0, float(jarvis)))

    def set_user_level(self, level: float) -> None:
        self.set_levels(level, self._jarvis)

    def set_jarvis_level(self, level: float) -> None:
        self.set_levels(self._user, level)

    def showEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802 - API de Qt
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._phase += 0.045
        self._color = _lerp_color(self._color, self._target)
        target = max(self._user, self._jarvis)
        if self._state in (AssistantState.PROCESSING, AssistantState.STARTING):
            target = max(target, 0.22)
        self._amplitude += (target - self._amplitude) * 0.18
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API de Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        height = self.height()
        center = QPointF(width / 2.0, height / 2.0)
        base = max(30.0, min(width, height) * 0.235)
        radius = base * (1.0 + self._amplitude * 0.16)
        color = self._color

        # Halo exterior.
        glow = QRadialGradient(center, radius * 2.05)
        halo = QColor(color)
        halo.setAlpha(78 + int(self._amplitude * 70))
        glow.setColorAt(0.0, halo)
        halo2 = QColor(color)
        halo2.setAlpha(22)
        glow.setColorAt(0.55, halo2)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 2.05, radius * 2.05)

        # Anillos orbitales.
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for index, factor in enumerate((1.18, 1.38, 1.62)):
            ring = QColor(color)
            ring.setAlpha(30 + index * 14)
            painter.setPen(QPen(ring, 1.2))
            wobble = math.sin(self._phase * 0.8 + index) * radius * 0.02
            painter.drawEllipse(center, radius * factor + wobble, radius * factor + wobble)

        # Espectro circular: responde al nivel real de audio.
        painter.setPen(Qt.PenStyle.NoPen)
        bars = 84
        for index in range(bars):
            angle = self._phase * 0.35 + index * (2.0 * math.pi / bars)
            pattern = 0.45 + 0.55 * abs(math.sin(index * 1.71 + self._phase * 2.2))
            length = 3.0 + self._amplitude * base * 0.30 * pattern
            if index % 3 == 0:
                length += self._amplitude * base * 0.08
            start = radius * 1.06
            inner = QPointF(
                center.x() + math.cos(angle) * start,
                center.y() + math.sin(angle) * start,
            )
            outer = QPointF(
                center.x() + math.cos(angle) * (start + length),
                center.y() + math.sin(angle) * (start + length),
            )
            mark = QColor(color)
            mark.setAlpha(70 + int(120 * pattern * (0.25 + self._amplitude)))
            painter.setPen(QPen(mark, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(inner, outer)

        # Partículas orbitando.
        painter.setPen(Qt.PenStyle.NoPen)
        for index in range(14):
            angle = self._phase * 0.7 + index * (2.0 * math.pi / 14)
            distance = radius * (1.22 + 0.18 * math.sin(self._phase * 1.3 + index * 1.7))
            point = QPointF(
                center.x() + math.cos(angle) * distance,
                center.y() + math.sin(angle) * distance,
            )
            dot = QColor(color)
            dot.setAlpha(60 + int(120 * (0.5 + 0.5 * math.sin(self._phase * 2.0 + index))))
            painter.setBrush(dot)
            size = 1.6 + 1.8 * (0.5 + 0.5 * math.sin(index * 2.1))
            painter.drawEllipse(point, size, size)

        # Arco giratorio mientras procesa.
        if self._state in (AssistantState.PROCESSING, AssistantState.STARTING):
            arc_color = QColor(theme.VIOLET)
            arc_color.setAlpha(190)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(arc_color, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            rect = QRectF(
                center.x() - radius * 1.30,
                center.y() - radius * 1.30,
                radius * 2.60,
                radius * 2.60,
            )
            start_angle = int((self._phase * 90.0) % 5_760)
            painter.drawArc(rect, start_angle, 70 * 16)

        # Núcleo.
        core = QRadialGradient(
            QPointF(center.x() - radius * 0.30, center.y() - radius * 0.36),
            radius * 1.35,
        )
        core.setColorAt(0.0, QColor(255, 255, 255, 235))
        inner = QColor(color)
        inner.setAlpha(235)
        core.setColorAt(0.42, inner)
        deep = QColor(color).darker(230)
        deep.setAlpha(220)
        core.setColorAt(0.85, deep)
        core.setColorAt(1.0, QColor(2, 6, 16, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(core)
        painter.drawEllipse(center, radius, radius)

        # Borde luminoso.
        edge = QColor(color)
        edge.setAlpha(180)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(edge, 1.4))
        painter.drawEllipse(center, radius, radius)

        # Arco interior tenue.
        inner_arc = QColor(255, 255, 255, 70)
        painter.setPen(QPen(inner_arc, 1.0))
        painter.drawArc(
            QRectF(
                center.x() - radius * 0.74,
                center.y() - radius * 0.74,
                radius * 1.48,
                radius * 1.48,
            ),
            int(-self._phase * 50) % 5_760,
            130 * 16,
        )


class LevelBars(QWidget):
    """Barras de nivel suavizadas a partir del audio real."""

    def __init__(self, accent: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._level = 0.0
        self._display = 0.0
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def sizeHint(self) -> QSize:
        return QSize(260, 62)

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, float(level)))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._display += (self._level - self._display) * 0.32
        if self._level < 0.01:
            self._display *= 0.86
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = max(1, self.width())
        height = max(1, self.height())
        count = max(12, min(44, width // 9))
        gap = 3.0
        bar_width = max(2.0, (width - gap * (count - 1)) / count)
        center_y = height / 2.0
        amplitude = self._display
        for index in range(count):
            pattern = (
                0.30
                + 0.70
                * abs(math.sin(index * 1.43 + 0.8))
                * (0.55 + 0.45 * abs(math.sin(index * 0.37 + 1.7)))
            )
            active = 2.0 + amplitude * pattern * (height - 10.0)
            idle = 2.0 + 1.5 * abs(math.sin(index * 0.6))
            bar_height = max(idle, active)
            alpha = 55 + int(150 * min(1.0, amplitude * 1.6))
            color = QColor(self._accent)
            color.setAlpha(alpha)
            x = index * (bar_width + gap)
            rect = QRectF(x, center_y - bar_height / 2.0, bar_width, bar_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, bar_width / 2.0, bar_width / 2.0)
        painter.end()


class VoicePanel(QFrame):
    """Panel «TU VOZ» o «JARVIS» con barras y transcripción."""

    def __init__(
        self,
        title: str,
        accent: QColor,
        hint: str,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("PanelSoft")
        self._title = QLabel(title)
        self._title.setObjectName("SectionTitle")
        self.bars = LevelBars(accent)
        self.caption = QLabel(hint)
        self.caption.setObjectName("Hint")
        self.caption.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        layout.addWidget(self._title)
        layout.addWidget(self.bars)
        layout.addWidget(self.caption)

    def set_level(self, level: float) -> None:
        self.bars.set_level(level)

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)


class DocumentCard(QFrame):
    """Tarjeta del documento activo."""

    pickRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        title = QLabel("DOCUMENTO ACTIVO")
        title.setObjectName("SectionTitle")
        self.name = QLabel("Sin documento")
        self.name.setObjectName("DocName")
        self.name.setWordWrap(True)
        self.meta = QLabel(
            "Abre un .docx de Descargas por voz o elígelo manualmente."
        )
        self.meta.setObjectName("DocMeta")
        self.meta.setWordWrap(True)
        self.button = QPushButton("Elegir .docx")
        self.button.setObjectName("Ghost")
        self.button.clicked.connect(self.pickRequested.emit)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        layout.addWidget(title)
        layout.addWidget(self.name)
        layout.addWidget(self.meta)
        layout.addSpacing(4)
        layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignLeft)

    def set_document(self, info) -> None:
        if info is None:
            self.name.setText("Sin documento")
            self.meta.setText(
                "Abre un .docx de Descargas por voz o elígelo manualmente."
            )
            return
        self.name.setText(info.name)
        opened = "abierto en Word" if info.opened else "cargado para consulta"
        characters = f"{info.characters:,}".replace(",", ".")
        self.meta.setText(
            f"{info.title}\n"
            f"{info.paragraphs} párrafos · {info.tables} tablas · "
            f"{info.sections} encabezados · {characters} caracteres\n"
            f"{opened}"
        )


class ConversationBubble(QFrame):
    """Mensaje de la conversación con hora y fuentes."""

    def __init__(self, message, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        role = getattr(message, "role", "jarvis")
        text = getattr(message, "text", str(message))
        timestamp = getattr(message, "time_label", "")
        sources: Iterable[str] = getattr(message, "sources", ())
        grounded = bool(getattr(message, "grounded", True))

        is_user = role == "user"
        is_system = role == "system"
        self.setObjectName("PanelSoft")
        accent = theme.CYAN if is_user else (theme.AMBER if is_system else theme.VIOLET)
        self.setStyleSheet(
            f"QFrame#PanelSoft {{ background-color: {theme.PANEL_ALT}; "
            f"border: 1px solid {theme.BORDER_SOFT}; "
            f"border-left: 2px solid {accent}; border-radius: 12px; }}"
        )

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        who = QLabel(
            "TÚ" if is_user else ("SISTEMA" if is_system else "JARVIS")
        )
        who.setStyleSheet(
            f"color: {accent}; font-size: 9px; font-weight: 700; "
            "letter-spacing: 2px;"
        )
        when = QLabel(timestamp)
        when.setStyleSheet(f"color: {theme.DIM}; font-size: 9px;")
        header.addWidget(who)
        header.addStretch(1)
        header.addWidget(when)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        body.setStyleSheet(f"color: {theme.TEXT}; font-size: 12px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 11)
        layout.setSpacing(5)
        layout.addLayout(header)
        layout.addWidget(body)

        if sources:
            source_text = "Fuentes: " + " · ".join(sources)
            source_label = QLabel(source_text)
            source_label.setWordWrap(True)
            source_label.setStyleSheet(
                f"color: {theme.DIM}; font-size: 10px;"
            )
            layout.addWidget(source_label)
        if not grounded and not is_system:
            warn = QLabel("Respuesta no basada en el documento")
            warn.setStyleSheet(f"color: {theme.AMBER}; font-size: 10px;")
            layout.addWidget(warn)


class ChoicesPanel(QFrame):
    """Lista de documentos candidatos; nunca elige sin confirmación."""

    chosen = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PanelSoft")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)
        self._title = QLabel("¿QUÉ DOCUMENTO ABRO?")
        self._title.setObjectName("SectionTitle")
        self._layout.addWidget(self._title)
        self._buttons: list[QPushButton] = []
        self.hide()

    def set_choices(self, names: Iterable[str]) -> None:
        for button in self._buttons:
            button.deleteLater()
        self._buttons = []
        names = list(names)
        if not names:
            self.hide()
            return
        for index, name in enumerate(names):
            button = QPushButton(f"{index + 1}.  {name}")
            button.setObjectName("Choice")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, choice=index: self.chosen.emit(choice)
            )
            self._layout.addWidget(button)
            self._buttons.append(button)
        self.show()
