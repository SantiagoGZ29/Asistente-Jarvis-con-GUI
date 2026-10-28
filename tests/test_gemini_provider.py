"""Pruebas del proveedor de Gemini con un cliente simulado."""

from __future__ import annotations

import httpx
import pytest

from jarvis.core.errors import (
    ProviderAuthError,
    ProviderModelError,
    ProviderNetworkError,
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from jarvis.providers.gemini_provider import GeminiProvider


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.candidates: list = []


class FakeModels:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict | None = None

    def generate_content(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.models = FakeModels(response=response, error=error)


class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"error {status_code}")


def _provider(client: FakeClient) -> GeminiProvider:
    return GeminiProvider(api_key="clave-simulada", model="modelo-prueba", client=client)


def test_sin_clave_falla_con_mensaje_claro() -> None:
    with pytest.raises(ProviderNotConfiguredError) as error:
        GeminiProvider(api_key="", model="gemini-3.8-flash")
    assert "GEMINI_API_KEY" in error.value.user_message


def test_sin_modelo_falla_con_mensaje_claro() -> None:
    with pytest.raises(ProviderNotConfiguredError):
        GeminiProvider(api_key="clave", model="")


def test_genera_texto_y_envia_configuracion() -> None:
    client = FakeClient(response=FakeResponse("Respuesta de prueba"))
    provider = _provider(client)

    result = provider.complete(
        prompt="Pregunta",
        system_instruction="Instrucciones",
        temperature=0.1,
        max_output_tokens=500,
    )

    assert result == "Respuesta de prueba"
    kwargs = client.models.kwargs
    assert kwargs["model"] == "modelo-prueba"
    assert kwargs["contents"] == "Pregunta"
    assert kwargs["config"].system_instruction == "Instrucciones"
    assert kwargs["config"].temperature == 0.1
    assert kwargs["config"].max_output_tokens == 500


def test_respuesta_vacia_controlada() -> None:
    provider = _provider(FakeClient(response=FakeResponse("")))
    with pytest.raises(ProviderResponseError):
        provider.complete(prompt="x", system_instruction="y")


def test_limite_de_uso_se_traduce_en_mensaje_comprensible() -> None:
    provider = _provider(FakeClient(error=FakeStatusError(429)))
    with pytest.raises(ProviderRateLimitError) as error:
        provider.complete(prompt="x", system_instruction="y")

    message = error.value.user_message.lower()
    assert "cuota" in message or "límite" in message
    assert "espera" in message


def test_error_de_red_se_traduce_en_mensaje_comprensible() -> None:
    provider = _provider(FakeClient(error=httpx.ConnectError("sin conexión")))
    with pytest.raises(ProviderNetworkError) as error:
        provider.complete(prompt="x", system_instruction="y")
    assert "conexión" in error.value.user_message.lower()


def test_clave_rechazada() -> None:
    provider = _provider(FakeClient(error=FakeStatusError(401)))
    with pytest.raises(ProviderAuthError):
        provider.complete(prompt="x", system_instruction="y")


def test_modelo_no_disponible() -> None:
    provider = _provider(FakeClient(error=FakeStatusError(404)))
    with pytest.raises(ProviderModelError):
        provider.complete(prompt="x", system_instruction="y")


def test_no_crea_cliente_real_si_se_inyecta_uno() -> None:
    client = FakeClient(response=FakeResponse("ok"))
    provider = _provider(client)
    assert provider._ensure_client() is client
    assert provider.model_name == "modelo-prueba"


class FlakyModels:
    """Falla con 503 las dos primeras veces y luego responde."""

    def __init__(self, failures: int = 2) -> None:
        self.failures = failures
        self.calls = 0

    def generate_content(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise FakeStatusError(503)
        return FakeResponse("Recuperado tras reintentos")


class FlakyClient:
    def __init__(self, failures: int = 2) -> None:
        self.models = FlakyModels(failures)


def test_reintenta_errores_transitorios_503(monkeypatch) -> None:
    import jarvis.providers.gemini_provider as gemini_module

    esperas: list[float] = []
    monkeypatch.setattr(gemini_module.time, "sleep", esperas.append)

    client = FlakyClient(failures=2)
    provider = _provider(client)
    result = provider.complete(prompt="x", system_instruction="y")

    assert result == "Recuperado tras reintentos"
    assert client.models.calls == 3
    assert esperas == [2.0, 5.0]


def test_no_reintenta_errores_no_transitorios(monkeypatch) -> None:
    import jarvis.providers.gemini_provider as gemini_module

    esperas: list[float] = []
    monkeypatch.setattr(gemini_module.time, "sleep", esperas.append)

    provider = _provider(FakeClient(error=FakeStatusError(429)))
    with pytest.raises(ProviderRateLimitError):
        provider.complete(prompt="x", system_instruction="y")
    assert esperas == []
