"""Paleta y hoja de estilos de la interfaz de Mi Jarvis."""

from __future__ import annotations

from PySide6.QtGui import QColor

BG = "#05070F"
BG_SOFT = "#070C18"
PANEL = "#0A1120"
PANEL_ALT = "#0D1729"
BORDER = "#1B2A44"
BORDER_SOFT = "#13203A"
TEXT = "#E6EDF8"
MUTED = "#7C90AE"
DIM = "#4E617E"
CYAN = "#22D3EE"
BLUE = "#3B82F6"
VIOLET = "#8B5CF6"
GREEN = "#34D399"
AMBER = "#FBBF24"
RED = "#F87171"

USER_COLOR = QColor(CYAN)
JARVIS_COLOR = QColor(VIOLET)


STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Segoe UI Variable", "Inter", sans-serif;
}}
QMainWindow, QDialog {{
    background-color: {BG};
    color: {TEXT};
}}
QWidget {{
    color: {TEXT};
}}
QFrame#Panel {{
    background-color: {PANEL};
    border: 1px solid {BORDER_SOFT};
    border-radius: 18px;
}}
QFrame#PanelSoft {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 14px;
}}
QFrame#HeaderBar {{
    background-color: {BG_SOFT};
    border: 1px solid {BORDER_SOFT};
    border-radius: 18px;
}}
QLabel#AppTitle {{
    color: {TEXT};
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 4px;
}}
QLabel#AppSubtitle {{
    color: {DIM};
    font-size: 10px;
    letter-spacing: 2px;
}}
QLabel#SectionTitle {{
    color: {MUTED};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}}
QLabel#Hint {{
    color: {DIM};
    font-size: 11px;
}}
QLabel#Partial {{
    color: {TEXT};
    font-size: 15px;
}}
QLabel#Chip {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 11px;
    color: {MUTED};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    padding: 4px 10px;
}}
QLabel#StatePill {{
    border-radius: 13px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    padding: 6px 14px;
}}
QLabel#DocName {{
    color: {TEXT};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#DocMeta {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#Notice {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {MUTED};
    font-size: 12px;
    padding: 8px 12px;
}}
QLabel#NoticeError {{
    background-color: rgba(248, 113, 113, 28);
    border: 1px solid rgba(248, 113, 113, 90);
    border-radius: 10px;
    color: #FCA5A5;
    font-size: 12px;
    padding: 8px 12px;
}}
QPushButton {{
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 11px;
    color: {TEXT};
    font-size: 12px;
    font-weight: 600;
    padding: 8px 16px;
}}
QPushButton:hover {{
    background-color: #12203A;
    border-color: {BLUE};
}}
QPushButton:pressed {{
    background-color: #0B1526;
}}
QPushButton:disabled {{
    color: {DIM};
    border-color: {BORDER_SOFT};
    background-color: #0A101C;
}}
QPushButton#Primary {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0891B2, stop:0.55 #2563EB, stop:1 #7C3AED);
    border: 1px solid #38BDF8;
    color: #F8FAFC;
}}
QPushButton#Primary:hover {{
    border-color: #A5F3FC;
}}
QPushButton#Danger {{
    background-color: rgba(248, 113, 113, 24);
    border: 1px solid rgba(248, 113, 113, 110);
    color: #FCA5A5;
}}
QPushButton#Danger:hover {{
    background-color: rgba(248, 113, 113, 45);
}}
QPushButton#Ghost {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {MUTED};
    font-weight: 500;
    padding: 6px 10px;
}}
QPushButton#Ghost:hover {{
    color: {TEXT};
    border-color: {BORDER};
}}
QPushButton#Choice {{
    text-align: left;
    background-color: {PANEL_ALT};
    border: 1px solid {BORDER};
    padding: 7px 12px;
}}
QLineEdit {{
    background-color: {BG_SOFT};
    border: 1px solid {BORDER};
    border-radius: 12px;
    color: {TEXT};
    font-size: 13px;
    padding: 10px 14px;
    selection-background-color: {BLUE};
}}
QLineEdit:focus {{
    border-color: {CYAN};
}}
QComboBox {{
    background-color: {BG_SOFT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {TEXT};
    font-size: 11px;
    padding: 7px 12px;
    min-height: 18px;
}}
QComboBox:hover {{
    border-color: {BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    color: {TEXT};
    selection-background-color: {BLUE};
    outline: 0;
}}
QScrollArea {{
    background-color: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 9px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #2A4066;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QCheckBox {{
    color: {TEXT};
    font-size: 12px;
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background-color: {BG_SOFT};
}}
QCheckBox::indicator:checked {{
    background-color: {CYAN};
    border-color: {CYAN};
}}
QToolTip {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    color: {TEXT};
    padding: 6px;
}}
QMessageBox, QFileDialog {{
    background-color: {BG};
    color: {TEXT};
}}
QSplitter::handle {{
    background-color: transparent;
    width: 10px;
}}
"""
