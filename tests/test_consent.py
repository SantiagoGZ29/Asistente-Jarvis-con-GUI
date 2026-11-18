"""Pruebas del consentimiento por sesión."""

from __future__ import annotations

from jarvis.core.consent import (
    ELEVENLABS_STT,
    GEMINI_DOCUMENT,
    GEMINI_SPREADSHEET,
    ALL_REQUESTS,
    ConsentManager,
)


def test_pide_consentimiento_una_sola_vez_por_sesion() -> None:
    calls: list[str] = []

    def ask(request) -> bool:
        calls.append(request.key)
        return True

    manager = ConsentManager(ask)

    assert manager.request(GEMINI_DOCUMENT) is True
    assert manager.request(GEMINI_DOCUMENT) is True
    assert calls == ["gemini_document"]
    assert manager.granted == frozenset({"gemini_document"})


def test_cada_proveedor_tiene_su_propio_consentimiento() -> None:
    calls: list[str] = []
    manager = ConsentManager(lambda request: calls.append(request.key) or True)

    manager.request(GEMINI_DOCUMENT)
    manager.request(ELEVENLABS_STT)
    manager.request(GEMINI_DOCUMENT)

    assert calls == ["gemini_document", "elevenlabs_stt"]


def test_rechazo_se_recuerda_y_no_reintenta() -> None:
    calls: list[str] = []
    manager = ConsentManager(lambda request: calls.append(request.key) or False)

    assert manager.request(GEMINI_DOCUMENT) is False
    assert manager.request(GEMINI_DOCUMENT) is False
    assert calls == ["gemini_document"]


def test_excel_tiene_un_consentimiento_separado_y_explicito() -> None:
    calls: list[str] = []
    manager = ConsentManager(lambda request: calls.append(request.key) or True)

    manager.request(GEMINI_DOCUMENT)
    manager.request(GEMINI_SPREADSHEET)

    assert calls == ["gemini_document", "gemini_spreadsheet"]
    assert "gemini_spreadsheet" in ALL_REQUESTS
    assert "resultados ya calculados" in GEMINI_SPREADSHEET.description
    assert "Nunca" in GEMINI_SPREADSHEET.description


def test_sin_consentimiento_explicito_todo_se_permite() -> None:
    manager = ConsentManager(lambda request: False, enabled=False)
    assert manager.request(GEMINI_DOCUMENT) is True


def test_error_de_entrada_equivale_a_rechazo() -> None:
    def broken(request):
        raise EOFError

    manager = ConsentManager(broken)
    assert manager.request(ELEVENLABS_STT) is False
