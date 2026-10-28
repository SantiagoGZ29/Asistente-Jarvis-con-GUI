"""Pruebas que garantizan que no se hacen llamadas reales a proveedores."""

from __future__ import annotations

import socket

import pytest

from jarvis.providers.gemini_provider import GeminiProvider


def test_la_red_esta_bloqueada_en_las_pruebas() -> None:
    with pytest.raises(AssertionError):
        socket.create_connection(("example.com", 80))


def test_crear_el_proveedor_no_abre_conexiones() -> None:
    # La construcción no debe conectarse: el cliente del SDK se crea de forma diferida.
    provider = GeminiProvider(api_key="clave-simulada", model="modelo-simulado")
    assert provider.model_name == "modelo-simulado"
    assert provider._client is None
