"""Captura continua del micrófono con detección de voz local.

``sounddevice.RawInputStream`` entrega bytes PCM sin necesitar NumPy. El
callback de PortAudio solo copia el bloque a una cola; todo el trabajo
(remuestreo, VAD, niveles) ocurre en un hilo propio, nunca en el hilo de
Qt ni en el de PortAudio.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from jarvis.audio import dsp
from jarvis.audio.devices import InputDevice, explain_audio_error
from jarvis.audio.vad import VadEventType, VoiceActivityDetector
from jarvis.core.errors import AudioError
from jarvis.core.logging_setup import get_logger

logger = get_logger("capture")

LevelCallback = Callable[[float, bool], None]
SpeechStartCallback = Callable[[], None]
SpeechEndCallback = Callable[[bytes, float], None]
DurationCallback = Callable[[float], None]
SimpleCallback = Callable[[], None]
ErrorCallback = Callable[[str], None]
AudioCallback = Callable[[bytes], None]

_QUEUE_SIZE = 256
_STOP_TIMEOUT = 2.0
_STALL_SECONDS = 5.0


class AudioCapture:
    """Micrófono continuo con VAD, niveles y cierre ordenado.

    Los callbacks se invocan desde el hilo de captura. El controlador es
    responsable de reenviarlos al hilo de interfaz que corresponda.
    """

    on_level: LevelCallback | None = None
    on_speech_start: SpeechStartCallback | None = None
    on_speech_end: SpeechEndCallback | None = None
    on_discard: DurationCallback | None = None
    on_streaming: SimpleCallback | None = None
    on_error: ErrorCallback | None = None
    # Audio PCM ya remuestreado a la frecuencia objetivo, para el STT en
    # tiempo real. Se entrega antes del VAD y solo con la captura activa.
    on_audio: AudioCallback | None = None

    def __init__(
        self,
        device: InputDevice,
        *,
        backend: Any | None = None,
        sample_rate: int = dsp.SAMPLE_RATE,
        vad: VoiceActivityDetector | None = None,
        queue_size: int = _QUEUE_SIZE,
    ) -> None:
        self.device = device
        self._backend = backend
        self.target_rate = int(sample_rate)
        self.vad = vad or VoiceActivityDetector(sample_rate=self.target_rate)
        if self.vad.sample_rate != self.target_rate:
            raise ValueError("El VAD y la captura deben usar la misma frecuencia")
        self._queue_size = queue_size

        self._queue: queue.Queue[bytes | None] = queue.Queue(maxsize=queue_size)
        self._running = threading.Event()
        self._suspended = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream: Any | None = None
        self._lock = threading.Lock()
        self._resampler = dsp.StreamResampler(self.target_rate, self.target_rate)

        self._actual_rate = self.target_rate
        self._streaming = False
        self._suspended_applied = False
        self._reset_requested = False
        self._max_level = 0.0
        self._frames_received = 0
        self._dropped_blocks = 0
        self._status_flags = 0
        self._last_chunk_at = 0.0
        self._stall_reported = False
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Estado observable
    # ------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def actual_sample_rate(self) -> int:
        return self._actual_rate

    @property
    def suspended(self) -> bool:
        return self._suspended.is_set()

    @property
    def max_level(self) -> float:
        return self._max_level

    @property
    def frames_received(self) -> int:
        return self._frames_received

    @property
    def dropped_blocks(self) -> int:
        return self._dropped_blocks

    @property
    def status_flags(self) -> int:
        return self._status_flags

    @property
    def last_error(self) -> str | None:
        return self._last_error

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Abre el flujo al ritmo adecuado y arranca el hilo consumidor."""
        with self._lock:
            if self._running.is_set():
                return
            self._close_stream()
            self._queue = queue.Queue(maxsize=self._queue_size)
            self._resampler = dsp.StreamResampler(self.target_rate, self.target_rate)
            self._suspended.clear()
            self._suspended_applied = False
            self._reset_requested = False
            self._max_level = 0.0
            self._frames_received = 0
            self._dropped_blocks = 0
            self._status_flags = 0
            self._streaming = False
            self._stall_reported = False
            self._last_error = None
            self.vad.reset()

            self._open_stream()
            self._running.set()
            self._last_chunk_at = time.monotonic()
            self._thread = threading.Thread(
                target=self._consume,
                name="jarvis-capture",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Cierra el flujo y espera al hilo; nunca deja el micrófono abierto."""
        with self._lock:
            was_running = self._running.is_set()
            self._running.clear()

        self._close_stream()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(_STOP_TIMEOUT)
            if thread.is_alive():  # pragma: no cover - cierre defensivo
                logger.warning("El hilo de captura no terminó a tiempo")
        self._thread = None
        self._streaming = False
        self.vad.reset()
        self._emit_level(0.0, False)
        if was_running:
            logger.info(
                "Captura detenida (dispositivo=%s, muestras=%d, descartes=%d)",
                self.device.index,
                self._frames_received,
                self._dropped_blocks,
            )

    close = stop

    def suspend(self) -> None:
        """Ignora el audio entrante (por ejemplo, mientras Jarvis habla)."""
        self._suspended.set()
        self._emit_level(0.0, False)

    def resume(self) -> None:
        self._suspended.clear()

    def reset_utterance(self) -> None:
        """Descarta la frase en curso sin detener el flujo."""
        self._reset_requested = True

    # ------------------------------------------------------------------
    # Apertura del flujo
    # ------------------------------------------------------------------
    def _open_stream(self) -> None:
        sound = self._backend
        if sound is None:
            import sounddevice

            sound = sounddevice

        native = int(self.device.default_samplerate or self.target_rate)
        candidates: list[int] = [self.target_rate]
        if native != self.target_rate:
            candidates.append(native)

        errors: list[BaseException] = []
        for rate in candidates:
            stream = None
            try:
                stream = sound.RawInputStream(
                    device=self.device.index,
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    blocksize=max(1, int(rate * self.vad.frame_ms / 1000)),
                    callback=self._callback,
                )
                stream.start()
            except Exception as exc:
                errors.append(exc)
                self._safe_close(stream)
                logger.info(
                    "No se pudo abrir el micrófono %s a %d Hz: %s",
                    self.device.index,
                    rate,
                    type(exc).__name__,
                )
                continue

            self._stream = stream
            self._actual_rate = rate
            self._resampler = dsp.StreamResampler(rate, self.target_rate)
            logger.info(
                "Micrófono abierto: dispositivo=%s frecuencia=%d Hz",
                self.device.index,
                rate,
            )
            return

        last = errors[-1] if errors else RuntimeError("sin flujo de entrada")
        message = explain_audio_error(last, self.device)
        self._last_error = message
        raise AudioError(message, detail=type(last).__name__)

    def _callback(self, indata, frames, time_info, status) -> None:
        """Callback de PortAudio: solo copia y sale."""
        try:
            if status:
                self._status_flags += 1
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            self._dropped_blocks += 1
        except Exception:  # pragma: no cover - nunca debe tumbar PortAudio
            self._dropped_blocks += 1

    # ------------------------------------------------------------------
    # Hilo consumidor
    # ------------------------------------------------------------------
    def _consume(self) -> None:
        while self._running.is_set():
            try:
                chunk = self._queue.get(timeout=0.2)
            except queue.Empty:
                self._check_stall()
                continue
            if chunk is None:
                break
            self._last_chunk_at = time.monotonic()
            if not self._streaming:
                self._streaming = True
                self._invoke(self.on_streaming)

            if self._suspended.is_set():
                if not self._suspended_applied:
                    self.vad.reset()
                    self._suspended_applied = True
                self._emit_level(0.0, False)
                continue
            if self._suspended_applied:
                self._suspended_applied = False
                self.vad.reset()

            if self._reset_requested:
                self._reset_requested = False
                self.vad.reset()

            data = self._resampler.process(chunk)
            if not data:
                continue

            self._frames_received += len(data) // dsp.BYTES_PER_SAMPLE
            self._invoke(self.on_audio, data)
            update = self.vad.feed(data)
            if update.level > self._max_level:
                self._max_level = update.level
            self._emit_level(update.level, update.speaking)

            for event in update.events:
                if event.kind is VadEventType.SPEECH_START:
                    self._invoke(self.on_speech_start)
                elif event.kind is VadEventType.SPEECH_END:
                    self._invoke(self.on_speech_end, event.segment, event.duration_s)
                elif event.kind is VadEventType.DISCARDED:
                    self._invoke(self.on_discard, event.duration_s)

    def _check_stall(self) -> None:
        if self._stall_reported or not self._running.is_set():
            return
        if time.monotonic() - self._last_chunk_at < _STALL_SECONDS:
            return
        self._stall_reported = True
        message = (
            "El micrófono dejó de enviar audio. Comprueba que siga conectado "
            "o elige otro dispositivo de entrada."
        )
        self._last_error = message
        logger.warning("Captura estancada en el dispositivo %s", self.device.index)
        self._invoke(self.on_error, message)

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _emit_level(self, value: float, speaking: bool) -> None:
        self._invoke(self.on_level, value, speaking)

    def _invoke(self, callback: Callable | None, *args: Any) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # pragma: no cover - un callback roto no detiene el audio
            logger.exception("Fallo en un callback de captura")

    def _close_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        try:
            stream.stop()
        except Exception:  # pragma: no cover - el flujo pudo cerrarse solo
            pass
        self._safe_close(stream)

    @staticmethod
    def _safe_close(stream: Any | None) -> None:
        if stream is None:
            return
        try:
            stream.close()
        except Exception:  # pragma: no cover
            pass

    def __enter__(self) -> "AudioCapture":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
