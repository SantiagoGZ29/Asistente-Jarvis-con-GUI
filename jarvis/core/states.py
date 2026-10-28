"""Estados explícitos del asistente y transiciones permitidas.

La interfaz y el controlador comparten estos estados. Cada transición se
valida contra una tabla: una transición imposible se registra y se rechaza
en lugar de dejar la interfaz en un estado contradictorio (por ejemplo,
mostrar «ESCUCHANDO» mientras el micrófono está detenido).

El estado del micrófono es independiente: un flujo puede estar abierto
mientras la aplicación está en ``PAUSED`` (el audio se descarta).
"""

from __future__ import annotations

import threading
from enum import Enum
from typing import Callable

from jarvis.core.errors import JarvisError
from jarvis.core.logging_setup import get_logger

logger = get_logger("states")


class AssistantState(str, Enum):
    """Estados de la aplicación."""

    STARTING = "STARTING"
    READY = "READY"
    LISTENING = "LISTENING"
    USER_SPEAKING = "USER_SPEAKING"
    PROCESSING = "PROCESSING"
    JARVIS_SPEAKING = "JARVIS_SPEAKING"
    PAUSED = "PAUSED"
    ERROR = "ERROR"


class MicState(str, Enum):
    """Estado real del micrófono, sin promesas optimistas."""

    UNAVAILABLE = "UNAVAILABLE"  # no hay dispositivo de entrada
    DETECTED = "DETECTED"  # aparece en la lista, sin flujo abierto
    STREAMING = "STREAMING"  # flujo de captura abierto y entregando datos
    SPEECH = "SPEECH"  # flujo abierto y voz detectada ahora mismo
    MUTED = "MUTED"  # el usuario pausó la escucha
    ERROR = "ERROR"  # el dispositivo o el permiso fallaron


STATE_LABELS: dict[AssistantState, str] = {
    AssistantState.STARTING: "INICIANDO",
    AssistantState.READY: "PREPARADO",
    AssistantState.LISTENING: "ESCUCHANDO",
    AssistantState.USER_SPEAKING: "TE ESCUCHO",
    AssistantState.PROCESSING: "PROCESANDO",
    AssistantState.JARVIS_SPEAKING: "HABLANDO",
    AssistantState.PAUSED: "EN PAUSA",
    AssistantState.ERROR: "ERROR",
}

STATE_HINTS: dict[AssistantState, str] = {
    AssistantState.STARTING: "Comprobando configuración y micrófono…",
    AssistantState.READY: "Listo para empezar",
    AssistantState.LISTENING: "Micrófono activo; puedes hablar cuando quieras",
    AssistantState.USER_SPEAKING: "Te estoy escuchando",
    AssistantState.PROCESSING: "Analizando tu petición…",
    AssistantState.JARVIS_SPEAKING: "Respondiendo en voz alta",
    AssistantState.PAUSED: "Micrófono en pausa; no se procesan órdenes nuevas",
    AssistantState.ERROR: "Revisa el aviso y vuelve a intentarlo",
}

MIC_LABELS: dict[MicState, str] = {
    MicState.UNAVAILABLE: "SIN DISPOSITIVO",
    MicState.DETECTED: "DETECTADO",
    MicState.STREAMING: "CAPTURANDO",
    MicState.SPEECH: "VOZ DETECTADA",
    MicState.MUTED: "EN PAUSA",
    MicState.ERROR: "ERROR",
}

# Estados en los que la captura destinada al reconocimiento debe estar activa.
RECOGNITION_STATES = frozenset(
    {AssistantState.LISTENING, AssistantState.USER_SPEAKING}
)

# Estados transitorios: la interfaz muestra actividad, no reposo.
BUSY_STATES = frozenset(
    {
        AssistantState.STARTING,
        AssistantState.PROCESSING,
        AssistantState.JARVIS_SPEAKING,
    }
)

_ALLOWED: dict[AssistantState, frozenset[AssistantState]] = {
    AssistantState.STARTING: frozenset(
        {
            AssistantState.READY,
            AssistantState.LISTENING,
            AssistantState.PAUSED,
            AssistantState.ERROR,
        }
    ),
    AssistantState.READY: frozenset(
        {
            AssistantState.LISTENING,
            AssistantState.PROCESSING,
            AssistantState.JARVIS_SPEAKING,
            AssistantState.PAUSED,
            AssistantState.ERROR,
        }
    ),
    AssistantState.LISTENING: frozenset(
        {
            AssistantState.USER_SPEAKING,
            AssistantState.PROCESSING,  # consulta escrita
            AssistantState.JARVIS_SPEAKING,  # saludo o aviso hablado
            AssistantState.READY,  # el micrófono dejó de estar disponible
            AssistantState.PAUSED,
            AssistantState.ERROR,
        }
    ),
    AssistantState.USER_SPEAKING: frozenset(
        {
            AssistantState.PROCESSING,
            AssistantState.LISTENING,  # frase descartada o demasiado corta
            AssistantState.READY,  # el micrófono falló a mitad de frase
            AssistantState.PAUSED,
            AssistantState.ERROR,
        }
    ),
    AssistantState.PROCESSING: frozenset(
        {
            AssistantState.JARVIS_SPEAKING,
            AssistantState.LISTENING,  # respuesta solo en pantalla
            AssistantState.READY,  # sin micrófono disponible
            AssistantState.PAUSED,
            AssistantState.ERROR,
        }
    ),
    AssistantState.JARVIS_SPEAKING: frozenset(
        {
            AssistantState.LISTENING,
            AssistantState.PROCESSING,  # consulta escrita durante la voz
            AssistantState.READY,  # no hay micrófono al terminar la voz
            AssistantState.PAUSED,
            AssistantState.ERROR,
        }
    ),
    AssistantState.PAUSED: frozenset(
        {
            AssistantState.LISTENING,
            AssistantState.READY,
            AssistantState.PROCESSING,  # modo texto con micrófono en pausa
            AssistantState.JARVIS_SPEAKING,
            AssistantState.ERROR,
        }
    ),
    AssistantState.ERROR: frozenset(
        {
            AssistantState.READY,
            AssistantState.LISTENING,
            AssistantState.PAUSED,
        }
    ),
}


class InvalidStateTransition(JarvisError):
    """Se intentó una transición que la máquina de estados no permite."""

    default_message = "El asistente intentó pasar a un estado no válido."


def allowed_transitions(state: AssistantState) -> frozenset[AssistantState]:
    return _ALLOWED[state]


def can_transition(
    current: AssistantState, new_state: AssistantState
) -> bool:
    return new_state is current or new_state in _ALLOWED[current]


def recognition_expected(state: AssistantState) -> bool:
    """True si en este estado el reconocimiento debería estar escuchando."""
    return state in RECOGNITION_STATES


StateListener = Callable[[AssistantState, AssistantState, str], None]


class StateMachine:
    """Máquina de estados segura para varios hilos.

    ``set_state`` devuelve ``True`` si la transición se aplicó. Las
    transiciones imposibles se registran como aviso y se ignoran, salvo que
    se construya con ``strict=True`` (útil en pruebas y desarrollo).
    """

    def __init__(
        self,
        initial: AssistantState = AssistantState.STARTING,
        *,
        strict: bool = False,
        max_history: int = 50,
    ) -> None:
        self._state = initial
        self._strict = strict
        self._max_history = max(1, max_history)
        self._history: list[AssistantState] = [initial]
        self._lock = threading.RLock()
        self._listeners: list[StateListener] = []

    @property
    def state(self) -> AssistantState:
        with self._lock:
            return self._state

    @property
    def history(self) -> tuple[AssistantState, ...]:
        with self._lock:
            return tuple(self._history)

    def subscribe(self, listener: StateListener) -> Callable[[], None]:
        """Registra un oyente y devuelve la función para darse de baja."""
        with self._lock:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            with self._lock:
                if listener in self._listeners:
                    self._listeners.remove(listener)

        return unsubscribe

    def set_state(
        self,
        new_state: AssistantState,
        *,
        reason: str = "",
        force: bool = False,
    ) -> bool:
        with self._lock:
            current = self._state
            if new_state is current:
                return True
            if not force and not can_transition(current, new_state):
                message = (
                    f"Transición no permitida: {current.value} -> {new_state.value}"
                    f"{f' ({reason})' if reason else ''}"
                )
                if self._strict:
                    raise InvalidStateTransition(message)
                logger.warning("%s", message)
                return False
            self._state = new_state
            self._history.append(new_state)
            if len(self._history) > self._max_history:
                del self._history[: len(self._history) - self._max_history]
            listeners = tuple(self._listeners)

        for listener in listeners:
            try:
                listener(current, new_state, reason)
            except Exception:  # pragma: no cover - un oyente roto no debe tumbar la app
                logger.exception("Fallo en un oyente de estado")
        return True
