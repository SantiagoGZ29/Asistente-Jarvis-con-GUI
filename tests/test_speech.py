"""Pruebas de la salida de voz: streaming, niveles, parada y errores."""

from __future__ import annotations

import threading
import time

import pytest

from jarvis.core.errors import JarvisError
from jarvis.voice.speech import SpeechCallbacks, SpeechOutput


def pcm(amplitude: int, samples: int) -> bytes:
    return int(amplitude).to_bytes(2, "little", signed=True) * samples


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class FakeOutputStream:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.written = bytearray()
        self.started = False
        self.stopped = False
        self.aborted = False
        self.closed = False
        self.block_writes = False
        self.write_started = threading.Event()
        self._aborted = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        self.started = True

    def write(self, data: bytes) -> None:
        if self._aborted.is_set():
            raise RuntimeError("flujo abortado")
        self.write_started.set()
        if self.block_writes:
            self._aborted.wait(2.0)
            if self._aborted.is_set():
                raise RuntimeError("flujo abortado")
        with self._lock:
            self.written.extend(data)

    def abort(self) -> None:
        self.aborted = True
        self._aborted.set()

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, *, block_writes: bool = False) -> None:
        self.block_writes = block_writes
        self.stream: FakeOutputStream | None = None
        self.requests: list[dict] = []

    def RawOutputStream(self, **kwargs):
        self.requests.append(kwargs)
        self.stream = FakeOutputStream(**kwargs)
        self.stream.block_writes = self.block_writes
        return self.stream


def make_output(chunks, backend=None, **kwargs) -> tuple[SpeechOutput, dict]:
    events = {
        "started": 0,
        "levels": [],
        "done": 0,
        "errors": [],
    }

    def factory(text: str):
        for chunk in chunks:
            yield chunk

    callbacks = SpeechCallbacks(
        on_started=lambda: events.__setitem__("started", events["started"] + 1),
        on_level=lambda value: events["levels"].append(value),
        on_done=lambda: events.__setitem__("done", events["done"] + 1),
        on_error=events["errors"].append,
    )
    output = SpeechOutput(
        factory,
        backend=backend or FakeBackend(),
        callbacks=callbacks,
        **kwargs,
    )
    return output, events


def test_reproduce_pcm_y_reporta_niveles_reales() -> None:
    backend = FakeBackend()
    output, events = make_output([pcm(2400, 1600)], backend=backend)

    assert output.speak("  Hola, soy Jarvis.  ") is True

    assert output.wait_until_done(3.0)
    stream = backend.stream
    assert stream is not None
    assert stream.kwargs["samplerate"] == 16_000
    assert stream.kwargs["channels"] == 1
    assert stream.kwargs["dtype"] == "int16"
    assert stream.started is True
    assert bytes(stream.written) == pcm(2400, 1600)
    assert events["started"] == 1
    assert events["done"] == 1
    assert events["errors"] == []
    assert max(events["levels"]) > 0.3
    assert events["levels"][-1] == 0.0
    assert output.is_speaking is False


def test_fragmentos_sucesivos_se_escriben_en_orden() -> None:
    backend = FakeBackend()
    first = pcm(1200, 320)
    second = pcm(2400, 320)
    output, _ = make_output([b"", first, second], backend=backend)

    output.speak("texto")
    assert output.wait_until_done(3.0)

    assert backend.stream is not None
    assert bytes(backend.stream.written) == first + second


def test_texto_vacio_no_abre_audio() -> None:
    backend = FakeBackend()
    output, events = make_output([pcm(1000, 320)], backend=backend)

    assert output.speak("   ") is False
    assert backend.requests == []
    assert events["done"] == 0


def test_no_solapa_dos_respuestas() -> None:
    backend = FakeBackend(block_writes=True)
    output, _ = make_output([pcm(2000, 3200)], backend=backend)
    output.speak("primera")
    assert backend.stream is not None
    assert wait_until(lambda: backend.stream.write_started.is_set())

    assert output.speak("segunda") is False

    output.stop()
    assert output.wait_until_done(2.0)


def test_parada_interrumpe_y_limpia_el_nivel() -> None:
    backend = FakeBackend(block_writes=True)
    output, events = make_output([pcm(2400, 16000)], backend=backend)
    output.speak("una respuesta larga")
    assert backend.stream is not None
    assert wait_until(lambda: backend.stream.write_started.is_set())

    started = time.monotonic()
    output.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert backend.stream.aborted is True
    assert backend.stream.closed is True
    assert output.wait_until_done(2.0)
    assert output.is_speaking is False
    assert events["errors"] == []
    assert events["levels"][-1] == 0.0
    assert events["done"] == 1


def test_error_de_sintesis_se_muestra_al_usuario() -> None:
    backend = FakeBackend()

    def factory(text: str):
        raise JarvisError("No hay clave de ElevenLabs configurada.")
        yield b""  # pragma: no cover - generador nunca llega aquí

    events = {"errors": [], "done": 0}
    output = SpeechOutput(
        factory,
        backend=backend,
        callbacks=SpeechCallbacks(
            on_done=lambda: events.__setitem__("done", events["done"] + 1),
            on_error=events["errors"].append,
        ),
    )

    assert output.speak("hola") is True
    assert output.wait_until_done(2.0)

    assert events["errors"] == ["No hay clave de ElevenLabs configurada."]
    assert events["done"] == 1
    assert backend.stream is None


def test_error_de_salida_de_audio_se_explica() -> None:
    class BrokenBackend:
        def RawOutputStream(self, **kwargs):
            raise RuntimeError("No output device")

    output, events = make_output([pcm(1000, 320)], backend=BrokenBackend())

    output.speak("hola")
    assert output.wait_until_done(2.0)

    assert events["errors"]
    assert "salida de audio" in events["errors"][0]
    assert events["done"] == 1


def test_respuesta_sin_audio_no_se_queda_en_silencio() -> None:
    output, events = make_output([b"", b""])

    output.speak("hola")
    assert output.wait_until_done(2.0)

    assert events["errors"]
    assert "no devolvió audio" in events["errors"][0]
    assert events["done"] == 1


def test_shutdown_cierra_el_hilo() -> None:
    output, _ = make_output([pcm(2000, 1600)])

    output.speak("hola")
    output.shutdown()

    assert output.is_speaking is False
    assert output.thread_alive is False
    assert output.wait_until_done(1.0)


def test_frecuencia_invalida() -> None:
    with pytest.raises(ValueError):
        SpeechOutput(lambda text: [], sample_rate=0)
