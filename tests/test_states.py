"""Pruebas de la máquina de estados del asistente."""

from __future__ import annotations

import pytest

from jarvis.core.states import (
    BUSY_STATES,
    MIC_LABELS,
    RECOGNITION_STATES,
    STATE_HINTS,
    STATE_LABELS,
    AssistantState,
    InvalidStateTransition,
    MicState,
    StateMachine,
    allowed_transitions,
    can_transition,
    recognition_expected,
)


def test_estado_inicial_y_lectura() -> None:
    machine = StateMachine()
    assert machine.state is AssistantState.STARTING
    assert machine.history == (AssistantState.STARTING,)


def test_transicion_valida_notifica_a_los_oyentes() -> None:
    machine = StateMachine(AssistantState.LISTENING)
    seen: list[tuple[AssistantState, AssistantState, str]] = []
    machine.subscribe(lambda old, new, reason: seen.append((old, new, reason)))

    assert machine.set_state(AssistantState.USER_SPEAKING, reason="voz detectada")

    assert machine.state is AssistantState.USER_SPEAKING
    assert seen == [
        (
            AssistantState.LISTENING,
            AssistantState.USER_SPEAKING,
            "voz detectada",
        )
    ]


def test_transicion_imposible_se_rechaza_y_se_registra(caplog) -> None:
    machine = StateMachine(AssistantState.STARTING)

    assert machine.set_state(AssistantState.USER_SPEAKING) is False
    assert machine.state is AssistantState.STARTING
    assert "Transición no permitida" in caplog.text


def test_modo_estricto_lanza_excepcion() -> None:
    machine = StateMachine(AssistantState.ERROR, strict=True)

    with pytest.raises(InvalidStateTransition):
        machine.set_state(AssistantState.JARVIS_SPEAKING)


def test_transicion_forced_permite_recuperacion() -> None:
    machine = StateMachine(AssistantState.STARTING)

    assert machine.set_state(AssistantState.LISTENING, force=True) is True
    assert machine.state is AssistantState.LISTENING


def test_mismo_estado_es_idempotente_y_no_notifica() -> None:
    machine = StateMachine(AssistantState.LISTENING)
    seen: list[AssistantState] = []
    machine.subscribe(lambda old, new, reason: seen.append(new))

    assert machine.set_state(AssistantState.LISTENING) is True
    assert seen == []


def test_baja_de_oyente() -> None:
    machine = StateMachine(AssistantState.READY)
    seen: list[AssistantState] = []
    unsubscribe = machine.subscribe(lambda old, new, reason: seen.append(new))
    unsubscribe()

    machine.set_state(AssistantState.LISTENING)
    assert seen == []


def test_un_oyente_roto_no_impide_la_transicion() -> None:
    machine = StateMachine(AssistantState.READY)
    seen: list[AssistantState] = []

    def broken(old, new, reason):
        raise RuntimeError("oyente roto")

    machine.subscribe(broken)
    machine.subscribe(lambda old, new, reason: seen.append(new))

    assert machine.set_state(AssistantState.LISTENING) is True
    assert seen == [AssistantState.LISTENING]


def test_historial_limitado() -> None:
    machine = StateMachine(AssistantState.LISTENING, max_history=3)
    machine.set_state(AssistantState.PROCESSING)
    machine.set_state(AssistantState.JARVIS_SPEAKING)
    machine.set_state(AssistantState.LISTENING)

    assert len(machine.history) == 3
    assert machine.history[-1] is AssistantState.LISTENING


def test_todos_los_estados_son_alcanzables() -> None:
    pendientes = [AssistantState.STARTING]
    visitados = {AssistantState.STARTING}
    while pendientes:
        actual = pendientes.pop()
        for siguiente in allowed_transitions(actual):
            if siguiente not in visitados:
                visitados.add(siguiente)
                pendientes.append(siguiente)

    assert visitados == set(AssistantState)


def test_tabla_de_transiciones_coherente() -> None:
    for state in AssistantState:
        assert state in STATE_LABELS
        assert state in STATE_HINTS
        assert isinstance(allowed_transitions(state), frozenset)
        assert state not in allowed_transitions(state)

    for mic_state in MicState:
        assert mic_state in MIC_LABELS


def test_consultas_escritas_funcionan_con_microfono_en_pausa() -> None:
    assert can_transition(AssistantState.PAUSED, AssistantState.PROCESSING)
    assert can_transition(AssistantState.PAUSED, AssistantState.JARVIS_SPEAKING)


def test_reconocimiento_solo_en_escucha_y_habla_del_usuario() -> None:
    assert recognition_expected(AssistantState.LISTENING)
    assert recognition_expected(AssistantState.USER_SPEAKING)
    for state in (
        AssistantState.PAUSED,
        AssistantState.PROCESSING,
        AssistantState.JARVIS_SPEAKING,
        AssistantState.ERROR,
        AssistantState.STARTING,
        AssistantState.READY,
    ):
        assert not recognition_expected(state)

    assert RECOGNITION_STATES == {
        AssistantState.LISTENING,
        AssistantState.USER_SPEAKING,
    }
    assert BUSY_STATES == {
        AssistantState.STARTING,
        AssistantState.PROCESSING,
        AssistantState.JARVIS_SPEAKING,
    }
