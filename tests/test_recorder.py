"""Pruebas de la captura explícita de audio y la limpieza de temporales."""

from __future__ import annotations

import time
import wave
from pathlib import Path

import pytest

from jarvis.audio.recorder import AudioRecorder
from jarvis.core.errors import AudioError


class FakeStream:
    def __init__(self, callback) -> None:
        self.callback = callback
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
        self.callback(payload, len(payload) // 2, None, None)


class FakeBackend:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.stream: FakeStream | None = None
        self.kwargs: dict | None = None

    def InputStream(self, **kwargs):
        if self.fail:
            raise RuntimeError("sin micrófono")
        self.kwargs = kwargs
        self.stream = FakeStream(kwargs["callback"])
        return self.stream

    def query_devices(self):
        if self.fail:
            raise RuntimeError("sin dispositivos")
        return [{"name": "micrófono simulado"}]


def test_grabacion_genera_wav_y_se_elimina(tmp_path: Path) -> None:
    backend = FakeBackend()
    recorder = AudioRecorder(backend=backend, temp_dir=tmp_path, max_seconds=5)

    recorder.start()
    assert recorder.is_recording
    backend.stream.feed(b"\x00\x01" * 800)
    path = recorder.stop()

    assert path.exists()
    assert path.parent == tmp_path
    assert path.name.startswith("jarvis_voz_")
    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 16_000
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() == 800

    assert AudioRecorder.delete_file(path) is True
    assert not path.exists()


def test_backend_recibe_configuracion_correcta() -> None:
    backend = FakeBackend()
    recorder = AudioRecorder(backend=backend, sample_rate=16_000, max_seconds=10)
    recorder.start()
    backend.stream.feed(b"\x00\x00" * 10)
    recorder.stop()

    assert backend.kwargs["samplerate"] == 16_000
    assert backend.kwargs["channels"] == 1
    assert backend.kwargs["dtype"] == "int16"


def test_detener_sin_grabar_falla() -> None:
    recorder = AudioRecorder(backend=FakeBackend())
    with pytest.raises(AudioError):
        recorder.stop()


def test_grabacion_sin_audio_falla() -> None:
    backend = FakeBackend()
    recorder = AudioRecorder(backend=backend, max_seconds=5)
    recorder.start()
    with pytest.raises(AudioError):
        recorder.stop()


def test_cancelar_no_genera_archivo(tmp_path: Path) -> None:
    backend = FakeBackend()
    recorder = AudioRecorder(backend=backend, temp_dir=tmp_path, max_seconds=5)
    recorder.start()
    backend.stream.feed(b"\x00\x00" * 100)
    recorder.cancel()

    assert not recorder.is_recording
    assert backend.stream.stopped
    assert list(tmp_path.glob("jarvis_voz_*.wav")) == []
    with pytest.raises(AudioError):
        recorder.stop()


def test_microfono_no_disponible() -> None:
    backend = FakeBackend(fail=True)
    recorder = AudioRecorder(backend=backend)
    assert recorder.is_available() is False
    with pytest.raises(AudioError):
        recorder.start()


def test_limite_de_tiempo_detiene_la_grabacion(tmp_path: Path) -> None:
    backend = FakeBackend()
    recorder = AudioRecorder(backend=backend, temp_dir=tmp_path, max_seconds=0.05)
    recorder.start()
    backend.stream.feed(b"\x00\x00" * 50)
    time.sleep(0.4)

    # El temporizador ya detuvo la grabación; stop devuelve el archivo generado.
    path = recorder.stop()
    assert path.exists()
    assert not recorder.is_recording
    AudioRecorder.delete_file(path)


def test_eliminar_archivo_inexistente_no_falla(tmp_path: Path) -> None:
    assert AudioRecorder.delete_file(tmp_path / "no-existe.wav") is True
    assert AudioRecorder.delete_file(None) is False
