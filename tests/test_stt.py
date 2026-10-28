"""Pruebas del reconocimiento de voz: realtime, lotes e híbrido."""

from __future__ import annotations

import asyncio
import base64
import threading
import time
import wave
from pathlib import Path

import pytest
from elevenlabs.realtime.connection import RealtimeEvents

from jarvis.core.errors import JarvisError
from jarvis.voice.stt import (
    BatchTranscriber,
    HybridTranscriber,
    RealtimeTranscriber,
    SttCallbacks,
)


def pcm(amplitude: int, samples: int = 320) -> bytes:
    return int(amplitude).to_bytes(2, "little", signed=True) * samples


def wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def callbacks():
    data = {"partials": [], "finals": [], "errors": [], "notices": []}
    cb = SttCallbacks(
        on_partial=lambda text, utterance: data["partials"].append((text, utterance)),
        on_final=lambda text, utterance: data["finals"].append((text, utterance)),
        on_error=data["errors"].append,
        on_notice=data["notices"].append,
    )
    return cb, data


# ----------------------------------------------------------------------
# Scribe Realtime v2 (conexión simulada, sin red)
# ----------------------------------------------------------------------
class FakeConnection:
    def __init__(self) -> None:
        self.handlers = {}
        self.sent: list[dict] = []
        self.commits = 0
        self.closed = 0

    def on(self, event, callback) -> None:
        self.handlers[event] = callback

    async def send(self, data) -> None:
        self.sent.append(data)

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        self.closed += 1

    def emit(self, event, data) -> None:
        self.handlers[event](data)


def connect_to(connection: FakeConnection, calls: list | None = None):
    async def connect(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return connection

    return connect


def make_realtime(connection: FakeConnection, cb, **kwargs) -> RealtimeTranscriber:
    return RealtimeTranscriber(
        api_key="clave-de-prueba",
        model_id="scribe_v2_realtime",
        language="es",
        callbacks=cb,
        connect=connect_to(connection),
        ready_timeout=1.0,
        **kwargs,
    )


def test_realtime_envia_audio_en_base64_y_confirma_frase() -> None:
    connection = FakeConnection()
    cb, data = callbacks()
    stt = make_realtime(connection, cb)

    stt.start()
    assert stt.healthy is True

    stt.push_audio(b"\x01\x02\x03\x04")
    assert wait_until(lambda: bool(connection.sent))
    assert base64.b64decode(connection.sent[0]["audio_base_64"]) == b"\x01\x02\x03\x04"

    utterance = stt.commit(b"\x01\x02\x03\x04")
    assert utterance == 1
    assert connection.commits == 1

    connection.emit(
        RealtimeEvents.COMMITTED_TRANSCRIPT, {"transcript": "  hola   mundo "}
    )
    connection.emit(RealtimeEvents.PARTIAL_TRANSCRIPT, {"transcript": "hola"})

    assert wait_until(lambda: bool(data["finals"]))
    assert data["finals"] == [("hola mundo", 1)]
    assert data["partials"] == [("hola", 1)]

    stt.stop()
    assert stt.healthy is False
    assert connection.closed == 1
    assert stt._thread is None


def test_realtime_sin_conexion_no_envia_audio() -> None:
    connection = FakeConnection()
    cb, _ = callbacks()
    stt = make_realtime(connection, cb)

    stt.push_audio(b"\x01\x02")
    time.sleep(0.05)

    assert connection.sent == []


def test_realtime_error_avisa_del_respaldo() -> None:
    connection = FakeConnection()
    cb, data = callbacks()
    stt = make_realtime(connection, cb)
    stt.start()

    connection.emit(RealtimeEvents.ERROR, {"error": "cuota agotada"})

    assert wait_until(lambda: bool(data["errors"]))
    assert "modo por lotes" in data["errors"][0]
    assert stt.healthy is False
    stt.stop()


def test_realtime_fallo_de_conexion_se_traduce() -> None:
    async def connect(**kwargs):
        raise RuntimeError("sin conexión")

    stt = RealtimeTranscriber(
        api_key="clave",
        model_id="modelo",
        language="es",
        callbacks=callbacks()[0],
        connect=connect,
        ready_timeout=1.0,
    )

    with pytest.raises(JarvisError) as info:
        stt.start()

    assert info.value.user_message


def test_realtime_sin_respuesta_no_bloquea_indefinidamente() -> None:
    async def connect(**kwargs):
        await asyncio.sleep(10)

    stt = RealtimeTranscriber(
        api_key="clave",
        model_id="modelo",
        language="es",
        callbacks=callbacks()[0],
        connect=connect,
        connect_timeout=0.05,
        ready_timeout=0.15,
    )

    with pytest.raises(JarvisError):
        stt.start()

    assert stt.healthy is False
    stt.stop()


# ----------------------------------------------------------------------
# Modo por lotes
# ----------------------------------------------------------------------
def test_lote_transcribe_wav_y_borra_el_temporal(tmp_path: Path) -> None:
    seen = {}

    def transcribe(path: Path) -> str:
        with wave.open(str(path), "rb") as wav_file:
            seen["rate"] = wav_file.getframerate()
            seen["channels"] = wav_file.getnchannels()
            seen["frames"] = wav_file.getnframes()
        return "hola desde el lote"

    cb, data = callbacks()
    batch = BatchTranscriber(transcribe, cb, temp_dir=tmp_path)
    batch.start()
    batch.commit(pcm(2000, 480))

    assert wait_until(lambda: bool(data["finals"]))
    assert data["finals"] == [("hola desde el lote", 1)]
    assert seen == {"rate": 16_000, "channels": 1, "frames": 480}
    assert list(tmp_path.iterdir()) == []
    batch.stop()


def test_lote_cancelado_no_entrega_resultado() -> None:
    entered = threading.Event()
    release = threading.Event()

    def transcribe(path: Path) -> str:
        entered.set()
        release.wait(2.0)
        return "tarde"

    cb, data = callbacks()
    batch = BatchTranscriber(transcribe, cb)
    batch.start()
    batch.commit(pcm(2000))

    assert entered.wait(1.0)
    batch.cancel()
    release.set()
    time.sleep(0.2)

    assert data["finals"] == []
    batch.stop()


def test_lote_error_se_explica() -> None:
    def transcribe(path: Path) -> str:
        raise JarvisError("No se pudo transcribir la frase.")

    cb, data = callbacks()
    batch = BatchTranscriber(transcribe, cb)
    batch.start()
    batch.commit(pcm(2000))

    assert wait_until(lambda: bool(data["errors"]))
    assert data["errors"] == ["No se pudo transcribir la frase."]
    batch.stop()


def test_lote_vacio_no_hace_nada() -> None:
    calls = []

    def transcribe(path: Path) -> str:
        calls.append(path)
        return "x"

    cb, data = callbacks()
    batch = BatchTranscriber(transcribe, cb)
    batch.start()

    assert batch.commit(b"") == 0
    time.sleep(0.1)

    assert calls == []
    assert data["finals"] == []
    batch.stop()


# ----------------------------------------------------------------------
# Híbrido
# ----------------------------------------------------------------------
class FakeRealtime:
    def __init__(self) -> None:
        self.healthy = True
        self.callbacks = SttCallbacks()
        self.started = False
        self.stopped = False
        self.audio: list[bytes] = []
        self.commits: list[bytes] = []
        self.commit_error: BaseException | None = None
        self.start_error: BaseException | None = None
        self.auto_final = False
        self.final_text = "texto realtime"
        self.final_delay = 0.03

    def set_callbacks(self, cb: SttCallbacks) -> None:
        self.callbacks = cb

    def start(self) -> None:
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        self.healthy = True

    def push_audio(self, data: bytes) -> None:
        self.audio.append(data)

    def commit(self, segment: bytes) -> int:
        self.commits.append(segment)
        if self.commit_error is not None:
            raise self.commit_error
        utterance = len(self.commits)
        if self.auto_final:
            threading.Timer(
                self.final_delay,
                lambda: self.callbacks.on_final(self.final_text, utterance),
            ).start()
        return utterance

    def cancel(self) -> None:
        pass

    def stop(self) -> None:
        self.stopped = True
        self.healthy = False


def batch_for(cb, calls: list | None = None) -> BatchTranscriber:
    def transcribe(path: Path) -> str:
        if calls is not None:
            calls.append(path)
        return "texto por lotes"

    return BatchTranscriber(transcribe, cb)


def make_hybrid(realtime, cb, *, timeout: float = 1.0, calls=None):
    return HybridTranscriber(
        callbacks=cb,
        realtime=realtime,
        batch=batch_for(cb, calls),
        final_timeout=timeout,
    )


def test_hibrido_usa_realtime_y_entrega_una_sola_vez() -> None:
    cb, data = callbacks()
    calls: list[Path] = []
    realtime = FakeRealtime()
    realtime.auto_final = True
    realtime.final_text = " hola "
    hybrid = make_hybrid(realtime, cb, calls=calls)

    hybrid.start()
    hybrid.commit(pcm(2000))

    assert wait_until(lambda: bool(data["finals"]))
    assert data["finals"] == [("hola", 1)]
    assert calls == []
    hybrid.stop()


def test_hibrido_cae_a_lote_si_el_commit_falla() -> None:
    cb, data = callbacks()
    calls: list[Path] = []
    realtime = FakeRealtime()
    realtime.commit_error = RuntimeError("conexión perdida")
    hybrid = make_hybrid(realtime, cb, calls=calls)

    hybrid.start()
    hybrid.commit(pcm(2000))

    assert wait_until(lambda: bool(data["finals"]))
    assert data["finals"] == [("texto por lotes", 1)]
    assert len(calls) == 1
    assert any("lotes" in notice for notice in data["notices"])
    assert data["errors"] == []
    hybrid.stop()


def test_hibrido_cae_a_lote_si_no_llega_el_final() -> None:
    cb, data = callbacks()
    calls: list[Path] = []
    hybrid = make_hybrid(FakeRealtime(), cb, timeout=0.1, calls=calls)

    hybrid.start()
    started = time.monotonic()
    hybrid.commit(pcm(2000))

    assert wait_until(lambda: bool(data["finals"]))
    assert time.monotonic() - started < 1.0
    assert data["finals"] == [("texto por lotes", 1)]
    assert len(calls) == 1
    hybrid.stop()


def test_un_final_tardio_no_duplica_el_resultado() -> None:
    cb, data = callbacks()
    realtime = FakeRealtime()
    hybrid = make_hybrid(realtime, cb, timeout=0.1)

    hybrid.start()
    hybrid.commit(pcm(2000))
    assert wait_until(lambda: bool(data["finals"]))

    realtime.callbacks.on_final("respuesta tardía", 1)
    time.sleep(0.15)

    assert data["finals"] == [("texto por lotes", 1)]
    hybrid.stop()


def test_hibrido_sin_realtime_usa_lotes() -> None:
    cb, data = callbacks()
    hybrid = make_hybrid(None, cb)
    assert hybrid.mode == "batch"

    hybrid.start()
    hybrid.push_audio(b"\x01\x02")  # no debe fallar
    hybrid.commit(pcm(2000))

    assert wait_until(lambda: bool(data["finals"]))
    assert data["finals"] == [("texto por lotes", 1)]
    hybrid.stop()


def test_fallo_al_arrancar_realtime_avisa_y_sigue_por_lotes() -> None:
    cb, data = callbacks()
    realtime = FakeRealtime()
    realtime.start_error = RuntimeError("sin red")
    hybrid = make_hybrid(realtime, cb)

    hybrid.start()

    assert hybrid.realtime is None
    assert hybrid.mode == "batch"
    assert any("lotes" in notice for notice in data["notices"])
    assert data["errors"] == []

    hybrid.commit(pcm(2000))
    assert wait_until(lambda: bool(data["finals"]))
    assert data["finals"] == [("texto por lotes", 1)]
    hybrid.stop()


def test_audio_solo_se_reenvia_con_realtime_sano() -> None:
    cb, _ = callbacks()
    realtime = FakeRealtime()
    hybrid = make_hybrid(realtime, cb)
    hybrid.start()

    hybrid.push_audio(b"\x01\x02")
    assert realtime.audio == [b"\x01\x02"]

    realtime.healthy = False
    hybrid.push_audio(b"\x03\x04")

    assert realtime.audio == [b"\x01\x02"]
    hybrid.stop()


def test_cancelar_descarta_el_commit_pendiente() -> None:
    cb, data = callbacks()
    realtime = FakeRealtime()
    hybrid = make_hybrid(realtime, cb, timeout=5.0)
    hybrid.start()

    hybrid.commit(pcm(2000))
    assert wait_until(lambda: bool(realtime.commits))

    hybrid.cancel()
    assert wait_until(lambda: not hybrid._workers, timeout=1.0)

    assert data["finals"] == []
    hybrid.stop()


def test_los_avisos_no_se_repiten() -> None:
    cb, data = callbacks()
    hybrid = make_hybrid(FakeRealtime(), cb)
    hybrid.start()

    hybrid._realtime_error("La transcripción falló.")
    hybrid._realtime_error("La transcripción falló.")

    assert data["notices"] == ["La transcripción falló."]
    hybrid.stop()


def test_stop_cierra_realtime_y_lotes() -> None:
    cb, _ = callbacks()
    realtime = FakeRealtime()
    hybrid = make_hybrid(realtime, cb)
    hybrid.start()

    hybrid.stop()

    assert realtime.stopped is True
    assert hybrid.batch._stopped is True
    assert hybrid._workers == set()
