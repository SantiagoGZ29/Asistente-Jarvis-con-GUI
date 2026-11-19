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
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
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
            "Abre un .docx o un libro .xlsx/.xlsm de Descargas por voz o "
            "elígelo manualmente."
        )
        self.meta.setObjectName("DocMeta")
        self.meta.setWordWrap(True)
        self.button = QPushButton("Elegir Word o Excel")
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
                "Abre un .docx o un libro .xlsx/.xlsm de Descargas por voz o "
                "elígelo manualmente."
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


class SpreadsheetCard(QFrame):
    """Tarjeta del libro de Excel activo."""

    pickRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        title = QLabel("LIBRO ACTIVO")
        title.setObjectName("SectionTitle")
        self.name = QLabel("Sin libro de Excel")
        self.name.setObjectName("DocName")
        self.name.setWordWrap(True)
        self.meta = QLabel(
            "Abre un .xlsx o .xlsm de Descargas por voz o elígelo manualmente."
        )
        self.meta.setObjectName("DocMeta")
        self.meta.setWordWrap(True)
        self.button = QPushButton("Elegir .xlsx / .xlsm")
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
        self.hide()

    def set_spreadsheet(self, info) -> None:
        if info is None:
            self.name.setText("Sin libro de Excel")
            self.meta.setText(
                "Abre un .xlsx o .xlsm de Descargas por voz o elígelo "
                "manualmente."
            )
            return
        self.name.setText(info.name)
        opened = "abierto en Excel" if info.opened else "cargado para consulta"
        sheets = ", ".join(
            f"{sheet.name} (oculta)" if sheet.hidden else sheet.name
            for sheet in info.sheets[:8]
        )
        if len(info.sheets) > 8:
            sheets += f" y {len(info.sheets) - 8} más"
        numbers = f"{info.rows:,}".replace(",", ".")
        lines = [
            info.title,
            f"{len(info.sheets)} hojas · hoja actual: "
            f"{info.current_sheet or '—'}",
            f"{sheets}" if sheets else "Sin hojas con datos legibles",
            f"{numbers} registros · {info.columns} columnas · "
            f"{info.formulas} fórmulas · {info.tables} tablas",
            f"{opened} · análisis {info.status.lower()}",
        ]
        if info.truncated:
            lines.append("Análisis parcial: el libro supera los límites.")
        if info.warnings:
            lines.append(info.warnings[0])
        self.meta.setText("\n".join(lines))


class AnalysisPanel(QFrame):
    """Resultado estructurado del último análisis, con su tabla y avisos."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PanelSoft")
        self._title = QLabel("RESULTADO DEL ANÁLISIS")
        self._title.setObjectName("SectionTitle")
        self.heading = QLabel("")
        self.heading.setObjectName("DocName")
        self.heading.setWordWrap(True)

        self._metrics = QHBoxLayout()
        self._metrics.setContentsMargins(0, 0, 0, 0)
        self._metrics.setSpacing(12)

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(80)

        self.sources = QLabel("")
        self.sources.setObjectName("Hint")
        self.sources.setWordWrap(True)
        self.alerts = QLabel("")
        self.alerts.setWordWrap(True)
        self.alerts.setStyleSheet(f"color: {theme.AMBER}; font-size: 10px;")
        self.note = QLabel("")
        self.note.setObjectName("Hint")
        self.note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(6)
        layout.addWidget(self._title)
        layout.addWidget(self.heading)
        layout.addLayout(self._metrics)
        layout.addWidget(self.table)
        layout.addWidget(self.alerts)
        layout.addWidget(self.sources)
        layout.addWidget(self.note)
        self.hide()

    def clear(self) -> None:
        while self._metrics.count():
            item = self._metrics.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.heading.setText("")
        self.sources.setText("")
        self.alerts.setText("")
        self.note.setText("")
        self.hide()

    def set_analysis(self, info) -> None:
        if info is None:
            self.clear()
            return
        self.heading.setText(info.title or "Análisis")
        while self._metrics.count():
            item = self._metrics.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for metric in info.metrics:
            label = QLabel(f"{metric.label}: {metric.value}")
            label.setObjectName("DocMeta")
            self._metrics.addWidget(label)
        self._metrics.addStretch(1)

        columns = list(info.columns or ())
        rows = [list(row) for row in (info.rows or ())]
        if rows and not columns:
            columns = [f"Columna {index + 1}" for index in range(
                max(len(row) for row in rows)
            )]
        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setRowCount(len(rows) if columns else 0)
        if columns:
            self.table.setHorizontalHeaderLabels(columns)
            for row_index, row in enumerate(rows):
                for column_index in range(len(columns)):
                    value = row[column_index] if column_index < len(row) else ""
                    item = QTableWidgetItem(str(value))
                    item.setToolTip(str(value))
                    self.table.setItem(row_index, column_index, item)
            header = self.table.horizontalHeader()
            if len(columns) <= 6:
                header.setSectionResizeMode(
                    QHeaderView.ResizeMode.ResizeToContents
                )
            else:
                header.setSectionResizeMode(
                    QHeaderView.ResizeMode.Interactive
                )
            self.table.setVisible(True)
            visible_rows = min(max(len(rows), 1), 7)
            self.table.setFixedHeight(min(240, 34 + 25 * visible_rows))
        else:
            self.table.setVisible(False)

        self.sources.setText(
            "Fuente: " + " · ".join(info.sources) if info.sources else ""
        )
        self.sources.setVisible(bool(info.sources))
        self.alerts.setText(
            "Avisos: " + " · ".join(info.alerts) if info.alerts else ""
        )
        self.alerts.setVisible(bool(info.alerts))
        self.note.setText(info.note or "")
        self.note.setVisible(bool(info.note))
        self.show()


class GooglePanel(QFrame):
    """Sección GOOGLE CONNECT: Gmail y Calendar de solo lectura."""

    connectRequested = Signal()
    disconnectRequested = Signal()
    mailRequested = Signal()
    calendarRequested = Signal()
    openMailRequested = Signal()
    openCalendarRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Panel")
        self._configured = False
        self._connected = False

        title = QLabel("GOOGLE CONNECT")
        title.setObjectName("SectionTitle")
        self.status = QLabel("SIN CONFIGURAR")
        self.status.setObjectName("Chip")
        self.status.setStyleSheet(f"color: {theme.DIM};")
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.status)

        self.account = QLabel(
            "Correo y calendario de solo lectura con las API de Google."
        )
        self.account.setObjectName("DocMeta")
        self.account.setWordWrap(True)
        self.problem = QLabel("")
        self.problem.setObjectName("Hint")
        self.problem.setWordWrap(True)
        self.problem.setVisible(False)

        # Tarjeta de correo
        self.mail_card = QFrame()
        self.mail_card.setObjectName("PanelSoft")
        mail_layout = QVBoxLayout(self.mail_card)
        mail_layout.setContentsMargins(12, 9, 12, 10)
        mail_layout.setSpacing(4)
        mail_title = QLabel("CORREO · SOLO LECTURA")
        mail_title.setObjectName("SectionTitle")
        self.mail_state = QLabel("Conecta Google para consultar la bandeja de Gmail.")
        self.mail_state.setObjectName("DocMeta")
        self.mail_state.setWordWrap(True)
        mail_buttons = QHBoxLayout()
        mail_buttons.setSpacing(6)
        self.mail_button = QPushButton("Consultar correos")
        self.mail_button.setObjectName("Primary")
        self.mail_button.clicked.connect(self.mailRequested.emit)
        self.open_mail_button = QPushButton("Abrir Gmail")
        self.open_mail_button.setObjectName("Ghost")
        self.open_mail_button.clicked.connect(self.openMailRequested.emit)
        mail_buttons.addWidget(self.mail_button)
        mail_buttons.addWidget(self.open_mail_button)
        mail_buttons.addStretch(1)
        mail_layout.addWidget(mail_title)
        mail_layout.addWidget(self.mail_state)
        mail_layout.addLayout(mail_buttons)

        # Tarjeta de calendario
        self.calendar_card = QFrame()
        self.calendar_card.setObjectName("PanelSoft")
        cal_layout = QVBoxLayout(self.calendar_card)
        cal_layout.setContentsMargins(12, 9, 12, 10)
        cal_layout.setSpacing(4)
        cal_title = QLabel("CALENDARIO · SOLO LECTURA")
        cal_title.setObjectName("SectionTitle")
        self.calendar_state = QLabel(
            "Conecta Google para consultar tu calendario."
        )
        self.calendar_state.setObjectName("DocMeta")
        self.calendar_state.setWordWrap(True)
        cal_buttons = QHBoxLayout()
        cal_buttons.setSpacing(6)
        self.calendar_button = QPushButton("Consultar agenda")
        self.calendar_button.setObjectName("Primary")
        self.calendar_button.clicked.connect(self.calendarRequested.emit)
        self.open_calendar_button = QPushButton("Abrir Google Calendar")
        self.open_calendar_button.setObjectName("Ghost")
        self.open_calendar_button.clicked.connect(
            self.openCalendarRequested.emit
        )
        cal_buttons.addWidget(self.calendar_button)
        cal_buttons.addWidget(self.open_calendar_button)
        cal_buttons.addStretch(1)
        cal_layout.addWidget(cal_title)
        cal_layout.addWidget(self.calendar_state)
        cal_layout.addLayout(cal_buttons)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.connect_button = QPushButton("CONECTAR GOOGLE")
        self.connect_button.setObjectName("Primary")
        self.connect_button.clicked.connect(self.connectRequested.emit)
        self.disconnect_button = QPushButton("Desconectar")
        self.disconnect_button.setObjectName("Ghost")
        self.disconnect_button.clicked.connect(self.disconnectRequested.emit)
        actions.addWidget(self.connect_button)
        actions.addWidget(self.disconnect_button)
        actions.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        layout.addLayout(header)
        layout.addWidget(self.account)
        layout.addWidget(self.problem)
        layout.addWidget(self.mail_card)
        layout.addWidget(self.calendar_card)
        layout.addLayout(actions)
        self.set_google(None)

    # ------------------------------------------------------------------
    def set_google(self, info) -> None:
        if info is None:
            self._configured = False
            self._connected = False
            self.status.setText("SIN CONFIGURAR")
            self.status.setStyleSheet(f"color: {theme.DIM};")
            self.account.setText(
                "Correo y calendario de solo lectura con las API de Google."
            )
            self.problem.setVisible(False)
            self.mail_state.setText(
                "Conecta Google para consultar la bandeja de Gmail."
            )
            self.calendar_state.setText(
                "Conecta Google para consultar tu calendario."
            )
            self._set_buttons(connect=False, disconnect=False, query=False)
            return

        self._configured = bool(info.configured)
        self._connected = bool(info.connected)
        busy = bool(info.busy)

        if busy:
            label, color = "CONECTANDO…", theme.AMBER
        elif self._connected:
            label, color = "CONECTADO", theme.GREEN
        elif self._configured:
            label, color = "CONFIGURADO · SIN AUTORIZAR", theme.AMBER
        else:
            label, color = "SIN CONFIGURAR", theme.DIM
        self.status.setText(label)
        self.status.setStyleSheet(f"color: {color};")

        if self._connected:
            self.account.setText(
                "Cuenta: "
                + (info.account or "Google")
                + " · solo lectura"
            )
        elif self._configured:
            self.account.setText(
                "Configurado. Pulsa CONECTAR GOOGLE para autorizar tu cuenta."
            )
        else:
            self.account.setText(
                "Coloca credentials.json y define GOOGLE_OAUTH_CLIENT_FILE en el "
                "archivo .env. Consulta el README para crear la aplicación de "
                "escritorio en Google Cloud."
            )

        problem = (info.problem or "").strip()
        self.problem.setText(problem)
        self.problem.setVisible(bool(problem))

        if not self._connected:
            self.mail_state.setText(
                "Conecta Google para consultar la bandeja de Gmail."
            )
            self.calendar_state.setText(
                "Conecta Google para consultar tu calendario."
            )
        else:
            mail_line = "Sin consultas todavía."
            if info.mail_query:
                extra = (
                    f" · {info.unread} sin leer" if info.unread else ""
                )
                mail_line = (
                    f"{info.mail_query}{extra}\n"
                    f"Últimos {info.mail_count} correos consultados."
                )
            elif info.mail_count:
                mail_line = f"{info.mail_count} correos consultados."
            self.mail_state.setText(mail_line)

            calendar_line = "Sin consultas todavía."
            if info.calendar_query:
                calendar_line = f"Última consulta: {info.calendar_query}."
            if info.next_event:
                calendar_line += f"\nPróximo: {info.next_event}"
            self.calendar_state.setText(calendar_line)

        self._set_buttons(
            connect=self._configured and not self._connected and not busy,
            disconnect=self._connected or busy,
            query=self._connected,
            busy=busy,
        )

    def _set_buttons(
        self, *, connect: bool, disconnect: bool, query: bool, busy: bool = False
    ) -> None:
        self.connect_button.setEnabled(bool(connect))
        self.disconnect_button.setEnabled(bool(disconnect))
        self.mail_button.setEnabled(bool(query))
        self.calendar_button.setEnabled(bool(query))
        self.connect_button.setText(
            "CONECTANDO…" if busy else "CONECTAR GOOGLE"
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
        self._title = QLabel("¿QUÉ ABRO?")
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
