"""Puente entre el controlador (hilos) y Qt (hilo de interfaz).

Los callbacks del controlador se emiten como señales de Qt. Cuando el emisor
vive en otro hilo, Qt entrega la señal en cola al hilo de la ventana, de modo
que ningún widget se toca desde el hilo de audio o de red.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from jarvis.core.consent import ALL_REQUESTS, ConsentRequest
from jarvis.core.controller import ControllerCallbacks


class ControllerBridge(QObject):
    """Señales tipadas y puerta de consentimiento segura entre hilos."""

    stateChanged = Signal(object, object, str)
    micChanged = Signal(object, str)
    userLevel = Signal(float)
    jarvisLevel = Signal(float)
    partial = Signal(str)
    message = Signal(object)
    notice = Signal(str)
    error = Signal(str)
    health = Signal(object)
    document = Signal(object)
    spreadsheet = Signal(object)
    analysis = Signal(object)
    analysisChoices = Signal(object)
    choices = Signal(object)
    pickRequested = Signal()
    exitRequested = Signal()
    micTest = Signal(object)
    consentRequested = Signal(str)

    _CONSENT_TIMEOUT = 120.0

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[threading.Event, list[bool]]] = {}
        self._closed = False

    # ------------------------------------------------------------------
    # Callbacks del controlador
    # ------------------------------------------------------------------
    def callbacks(self) -> ControllerCallbacks:
        return ControllerCallbacks(
            on_state=self.stateChanged.emit,
            on_mic=self.micChanged.emit,
            on_user_level=self.userLevel.emit,
            on_jarvis_level=self.jarvisLevel.emit,
            on_partial=self.partial.emit,
            on_message=self.message.emit,
            on_notice=self.notice.emit,
            on_error=self.error.emit,
            on_health=self.health.emit,
            on_document=self.document.emit,
            on_spreadsheet=self.spreadsheet.emit,
            on_analysis=self.analysis.emit,
            on_analysis_choices=self.analysisChoices.emit,
            on_choices=self.choices.emit,
            on_pick_document=self.pickRequested.emit,
            on_exit=self.exitRequested.emit,
            on_mic_test=self.micTest.emit,
        )

    # ------------------------------------------------------------------
    # Consentimiento
    # ------------------------------------------------------------------
    def ask(self, request: ConsentRequest) -> bool:
        """Se ejecuta en el hilo del controlador y espera la respuesta de Qt."""
        if self._closed:
            return False
        event = threading.Event()
        box = [False]
        with self._lock:
            self._pending[request.key] = (event, box)
        self.consentRequested.emit(request.key)
        if not event.wait(self._CONSENT_TIMEOUT):
            self._finish(request.key, False)
            return False
        return box[0]

    def resolve(self, key: str, accepted: bool) -> bool:
        """La interfaz acepta o rechaza una petición pendiente."""
        with self._lock:
            entry = self._pending.get(key)
        if entry is None:
            return False
        event, box = entry
        box[0] = bool(accepted)
        event.set()
        return True

    def _finish(self, key: str, accepted: bool) -> None:
        with self._lock:
            entry = self._pending.pop(key, None)
        if entry is None:
            return
        event, box = entry
        box[0] = bool(accepted)
        event.set()

    def cancel_all(self) -> None:
        """Al cerrar la ventana no dejamos ningún hilo esperando permiso."""
        with self._lock:
            self._closed = True
            keys = list(self._pending)
        for key in keys:
            self._finish(key, False)


__all__ = ["ALL_REQUESTS", "ControllerBridge"]
