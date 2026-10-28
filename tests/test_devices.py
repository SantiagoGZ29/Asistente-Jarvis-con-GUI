"""Pruebas de enumeración y selección de micrófonos."""

from __future__ import annotations

import pytest

from jarvis.audio.devices import (
    WINDOWS_PRIVACY_HINT,
    InputDevice,
    default_input_index,
    explain_audio_error,
    list_input_devices,
    resolve_device,
    startup_device,
)


class _Default:
    def __init__(self, device) -> None:
        self.device = device


class FakeSoundDevice:
    def __init__(self, *, device=2, raise_on_query: bool = False) -> None:
        self.default = _Default(device)
        self.raise_on_query = raise_on_query

    def query_hostapis(self):
        if self.raise_on_query:
            raise RuntimeError("PortAudio no disponible")
        return [{"name": "MME"}, {"name": "Windows WASAPI"}]

    def query_devices(self):
        if self.raise_on_query:
            raise RuntimeError("PortAudio no disponible")
        return [
            {
                "name": "Altavoces",
                "max_input_channels": 0,
                "max_output_channels": 2,
                "hostapi": 0,
                "default_samplerate": 48_000.0,
            },
            {
                "name": "Micrófono interno",
                "max_input_channels": 2,
                "hostapi": 1,
                "default_samplerate": 48_000.0,
            },
            {
                "name": "Auriculares",
                "max_input_channels": 1,
                "hostapi": 1,
                "default_samplerate": 16_000.0,
            },
        ]


def test_enumera_solo_entradas_con_su_host_api() -> None:
    devices = list_input_devices(FakeSoundDevice())

    assert [device.name for device in devices] == ["Micrófono interno", "Auriculares"]
    assert devices[0].hostapi == "Windows WASAPI"
    assert devices[0].channels == 2
    assert devices[0].default_samplerate == 48_000
    assert devices[1].is_default is True
    assert devices[1].label.endswith("· predeterminado")


def test_enumera_host_api_desconocida_sin_fallar() -> None:
    class Backend(FakeSoundDevice):
        def query_devices(self):
            return [
                {
                    "name": "Micrófono raro",
                    "max_input_channels": 1,
                    "hostapi": 99,
                    "default_samplerate": 0,
                }
            ]

    devices = list_input_devices(Backend())

    assert devices[0].hostapi == "Host API"
    assert devices[0].default_samplerate == 16_000


def test_sin_dispositivos_o_error_devuelve_vacio() -> None:
    assert list_input_devices(FakeSoundDevice(raise_on_query=True)) == ()

    class Empty(FakeSoundDevice):
        def query_devices(self):
            return []

    assert list_input_devices(Empty()) == ()


@pytest.mark.parametrize(
    ("device", "expected"),
    [([2, 5], 2), ((1, 0), 1), (3, 3), (None, None), (-1, None), ("x", None)],
)
def test_indice_predeterminado(device, expected) -> None:
    assert default_input_index(FakeSoundDevice(device=device)) == expected


def test_indice_predeterminado_formato_sounddevice() -> None:
    class Pair:
        """Imita sounddevice._InputOutputPair."""

        def __init__(self, value):
            self._value = value

        def __getitem__(self, index):
            if index in (0, "input"):
                return self._value
            raise KeyError(index)

    assert default_input_index(FakeSoundDevice(device=Pair(4))) == 4


def test_resuelve_por_clave_identidad_y_nombre() -> None:
    devices = list_input_devices(FakeSoundDevice())
    auriculares = devices[1]

    assert resolve_device(devices, auriculares.key) == auriculares
    # El índice cambia entre reinicios: se reencuentra por host + nombre.
    otra_sesion = InputDevice(
        index=7,
        name=auriculares.name,
        hostapi=auriculares.hostapi,
        channels=1,
        default_samplerate=16_000,
    )
    assert resolve_device((otra_sesion,), auriculares.key) == otra_sesion
    assert resolve_device(devices, "Windows WASAPI|MICRÓFONO INTERNO") == devices[0]
    assert resolve_device(devices, "no existe") is None
    assert resolve_device(devices, "") is None


def test_arranque_usa_el_guardado_si_existe() -> None:
    devices = list_input_devices(FakeSoundDevice())

    device, warning = startup_device("Windows WASAPI|Micrófono interno", devices=devices)

    assert device is devices[0]
    assert warning is None


def test_arranque_avisa_si_el_guardado_desaparecio() -> None:
    devices = list_input_devices(FakeSoundDevice())

    device, warning = startup_device("WASAPI|Micrófono vendido", devices=devices)

    assert device is devices[1]  # el predeterminado
    assert warning is not None
    assert "ya no está disponible" in warning


def test_arranque_sin_dispositivos_avisa_y_no_bloquea() -> None:
    device, warning = startup_device(None, devices=())

    assert device is None
    assert warning is not None
    assert "por teclado" in warning


def test_arranque_sin_preferencia_usa_el_predeterminado() -> None:
    devices = list_input_devices(FakeSoundDevice())

    device, warning = startup_device(None, devices=devices)

    assert device is devices[1]
    assert warning is None


def test_errores_de_audio_traducidos() -> None:
    denied = explain_audio_error(PermissionError("Access is denied"))
    assert "Windows no permite" in denied
    assert WINDOWS_PRIVACY_HINT in denied

    rate = explain_audio_error(RuntimeError("PortAudioError: Invalid sample rate -9997"))
    assert "frecuencia" in rate

    busy = explain_audio_error(RuntimeError("Device unavailable [-9985]"))
    assert "en uso" in busy

    missing = explain_audio_error(RuntimeError("Invalid device [-9996]"))
    assert "ya no existe" in missing

    generic = explain_audio_error(RuntimeError("algo raro"))
    assert "teclado" in generic
