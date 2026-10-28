"""Interfaz de usuario de Mi Jarvis.

La consola está disponible siempre; la interfaz gráfica se importa de forma
diferida para que `--console` y `--check` no carguen Qt ni sus dependencias.
"""

from __future__ import annotations

from typing import Any

from jarvis.ui.console import ConsoleApp  # noqa: F401

__all__ = ["ConsoleApp", "HelpDialog", "MainWindow", "PrivacyDialog", "run_gui"]


def __getattr__(name: str) -> Any:
    if name in {"HelpDialog", "MainWindow", "PrivacyDialog", "SettingsDialog", "run_gui"}:
        from jarvis.ui import gui

        return getattr(gui, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
