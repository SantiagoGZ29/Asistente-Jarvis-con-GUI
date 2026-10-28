"""Pruebas de la captura continua, sus fallos y su cierre ordenado."""

from __future__ import annotations

import time

import pytest

from jarvis.audio.capture import AudioCapture
from jarvis.audio.devices import InputDevice
from jarvis.audio.vad import VoiceActivityDetector
from jarvis.core.errors import AudioError

RATE = 16_000
FRAME = 320


def pcm(amplitude: int, samples: int = FRAME) -> bytes:
    return int(amplitude).to_bytes(2, "little", signed=True) * samples


def frames(amplitude: int, count: int, samples: int = FRAME) -> bytes:
    return pcm(amplitude, samples * count)


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class FakeRawStream:
    def __init__(self, kwargs: dict) -> None:
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def feed(self, payload: bytes) -> None:
        self.kwargs["callback"](payload, len(payload) // 2, None, 0)


class FakeBackend:
    def __init__(self, *, fail_rates=(), fail_all: bool = False) -> None:
        self.fail_rates = set(fail_rates)
        self.fail_all = fail_all
        self.requests: list[dict] = []
        self.stream: FakeRawStream | None = None

    def RawInputStream(self, **kwargs):
        self.requests.append(kwargs)
        if self.fail_all:
            raise RuntimeError("Invalid device [PaErrorCode -9996]")
        if int(kwargs["samplerate"]) in self.fail_rates:
            raise RuntimeError(
                "Error opening RawInputStream: Invalid sample rate [PaErrorCode -9997]"
            )
        self.stream = FakeRawStream(kwargs)
        return self.stream


def device(native: int = 44_100) -> InputDevice:
    return InputDevice(
        index=1,
        name="Micrófono de prueba",
        hostapi="MME",
        channels=1,
        default_samplerate=native,
    )


def make_capture(backend: FakeBackend, native: int = 44_100) -> AudioCapture:
    return AudioCapture(
        device(native),
        backend=backend,
        vad=VoiceActivityDetector(
            silence_ms=400,
            preroll_ms=100,
            min_speech_ms=200,
        ),
    )


def test_abre_a_16k_mono_y_entrega_niveles() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    niveles: list[float] = []
    eventos: list[str] = []
    capture.on_level = lambda level, speaking: niveles.append(level)
    capture.on_streaming = lambda: eventos.append("streaming")
    capture.on_speech_start = lambda: eventos.append("start")

    capture.start()
    assert capture.is_running
    assert backend.stream is not None
    kwargs = backend.stream.kwargs
    assert kwargs["device"] == 1
    assert kwargs["samplerate"] == 16_000
    assert kwargs["channels"] == 1
    assert kwargs["dtype"] == "int16"
    assert kwargs["blocksize"] == FRAME

    backend.stream.feed(frames(3000, 20))

    assert wait_until(lambda: "start" in eventos)
    assert wait_until(lambda: capture.frames_received >= 20 * FRAME)
    assert max(niveles) > 0.3
    capture.stop()
    assert capture.is_running is False
    assert capture.is_streaming is False


def test_reintenta_a_la_frecuencia_nativa_si_16k_falla() -> None:
    backend = FakeBackend(fail_rates={16_000})
    capture = make_capture(backend, native=48_000)

    capture.start()

    assert [request["samplerate"] for request in backend.requests] == [16_000, 48_000]
    assert capture.actual_sample_rate == 48_000
    assert backend.stream is not None
    assert backend.stream.kwargs["blocksize"] == 960

    backend.stream.feed(frames(3000, 60, samples=960))
    assert wait_until(lambda: capture.frames_received > 0)
    # El remuestreo 48k -> 16k reduce las muestras a un tercio.
    assert wait_until(lambda: 10_000 < capture.frames_received < 20_000)
    capture.stop()


def test_fallo_total_lanza_error_con_instrucciones() -> None:
    backend = FakeBackend(fail_all=True)
    capture = make_capture(backend)

    with pytest.raises(AudioError) as info:
        capture.start()

    assert "ya no existe" in info.value.user_message
    assert capture.is_running is False
    assert capture.last_error is not None
    assert capture._thread is None


def test_error_de_permiso_menciona_privacidad() -> None:
    class Denied(FakeBackend):
        def RawInputStream(self, **kwargs):
            raise RuntimeError("Access is denied")

    capture = make_capture(Denied())

    with pytest.raises(AudioError) as info:
        capture.start()

    assert "Privacidad" in info.value.user_message


def test_stop_cierra_el_flujo_y_el_hilo() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    capture.start()
    stream = backend.stream
    assert stream is not None

    capture.stop()

    assert stream.stopped is True
    assert stream.closed is True
    assert capture._thread is None
    assert capture.is_running is False

    # Idempotente: cerrar dos veces no falla.
    capture.stop()


def test_fin_de_frase_entrega_segmento() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    segmentos: list[tuple[bytes, float]] = []
    descartes: list[float] = []
    capture.on_speech_end = lambda data, duration: segmentos.append((data, duration))
    capture.on_discard = lambda duration: descartes.append(duration)

    capture.start()
    assert backend.stream is not None
    backend.stream.feed(frames(2500, 30))
    backend.stream.feed(frames(5, 30))

    assert wait_until(lambda: bool(segmentos), timeout=4.0)
    data, duration = segmentos[0]
    assert data
    assert duration >= 0.5
    assert descartes == []
    capture.stop()


def test_frase_corta_se_descarta_sin_enviar_audio() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    segmentos: list[bytes] = []
    descartes: list[float] = []
    capture.on_speech_end = lambda data, duration: segmentos.append(data)
    capture.on_discard = lambda duration: descartes.append(duration)

    capture.start()
    assert backend.stream is not None
    backend.stream.feed(frames(2500, 4))
    backend.stream.feed(frames(5, 30))

    assert wait_until(lambda: bool(descartes), timeout=4.0)
    assert segmentos == []
    assert descartes[0] > 0
    capture.stop()


def test_suspender_ignora_el_audio_y_reactiva_despues() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    eventos: list[str] = []
    niveles: list[float] = []
    capture.on_speech_start = lambda: eventos.append("start")
    capture.on_level = lambda level, speaking: niveles.append(level)

    capture.start()
    capture.suspend()
    assert backend.stream is not None
    backend.stream.feed(frames(3000, 30))
    time.sleep(0.25)

    assert "start" not in eventos
    assert all(level == 0.0 for level in niveles[-5:])

    capture.resume()
    backend.stream.feed(frames(3000, 20))
    assert wait_until(lambda: "start" in eventos)
    capture.stop()


def test_sin_audio_reporta_estancamiento() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    errores: list[str] = []
    capture.on_error = errores.append

    capture.start()
    capture._last_chunk_at = time.monotonic() - 10

    assert wait_until(lambda: bool(errores), timeout=2.0)
    assert "dejó de enviar audio" in errores[0]
    capture.stop()


def test_los_callbacks_rotos_no_detienen_la_captura() -> None:
    backend = FakeBackend()
    capture = make_capture(backend)
    capture.on_level = lambda level, speaking: (_ for _ in ()).throw(RuntimeError("x"))
    recibidos: list[float] = []
    capture.on_speech_start = lambda: recibidos.append(1.0)

    capture.start()
    assert backend.stream is not None
    backend.stream.feed(frames(3000, 20))

    assert wait_until(lambda: bool(recibidos))
    assert capture.is_running
    capture.stop()


def test_no_se_puede_mezclar_frecuencias_de_vad() -> None:
    with pytest.raises(ValueError):
        AudioCapture(device(), sample_rate=16_000, vad=VoiceActivityDetector(sample_rate=8_000))
