"""Salida de voz: síntesis en streaming y reproducción PCM con niveles.

La síntesis de ElevenLabs llega en fragmentos. Escribirlos según se reciben
reduce la latencia y permite detener la voz casi al instante. Todo ocurre en
un hilo propio: ni Qt ni la captura del micrófono se bloquean.

Los niveles que se publican son los del audio realmente escrito en el
dispositivo de salida, no una animación inventada.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from jarvis.audio import dsp
from jarvis.core.errors import AudioError, JarvisError
from jarvis.core.logging_setup import get_logger

logger = get_logger("speech")

# Bloques de escritura: 20 ms permiten atender una parada con prontitud sin
# provocar continuas interrupciones del flujo de salida.
_BLOCK_MS = 20
_STOP_TIMEOUT = 2.0


def _split_pcm(data: bytes, block_bytes: int) -> Iterable[bytes]:
    """Trocea PCM conservando muestras completas (2 bytes)."""
    step = max(2, block_bytes - (block_bytes % 2))
    for start in range(0, len(data), step):
        yield data[start : start + step]


def _chain_first(first: bytes, rest: Iterable[bytes]) -> Iterable[bytes]:
    yield first
    yield from rest


@dataclass
class SpeechCallbacks:
    """Eventos de la salida de voz.

    ``on_started`` se emite con el primer fragmento de audio, no al pedir la
    síntesis: así la interfaz no anuncia «hablando» mientras aún espera.
    ``on_done`` se emite siempre al terminar, también tras un error o una
    parada manual.
    """

    on_started: Callable[[], None] = lambda: None
    on_level: Callable[[float], None] = lambda level: None
    on_done: Callable[[], None] = lambda: None
    on_error: Callable[[str], None] = lambda message: None


class SpeechOutput:
    """Reproduce texto en voz alta con parada inmediata y niveles reales."""

    def __init__(
        self,
        stream_factory: Callable[[str], Iterable[bytes]],
        *,
        backend: Any | None = None,
        sample_rate: int = dsp.SAMPLE_RATE,
        block_ms: int = _BLOCK_MS,
        stop_timeout: float = _STOP_TIMEOUT,
        callbacks: SpeechCallbacks | None = None,
    ) -> None:
        if sample_rate <= 0:
            raise ValueError("La frecuencia de salida debe ser positiva")
        self._stream_factory = stream_factory
        self._backend = backend
        self.sample_rate = int(sample_rate)
        self.block_ms = max(10, int(block_ms))
        self._block_bytes = max(
            2, self.sample_rate * self.block_ms // 1000 * dsp.BYTES_PER_SAMPLE
        )
        self._block_frames = max(1, self.sample_rate * self.block_ms // 1000)
        self._stop_timeout = max(0.1, float(stop_timeout))
        self.callbacks = callbacks or SpeechCallbacks()

        self._active = threading.Event()
        self._stop_requested = threading.Event()
        self._done = threading.Event()
        self._done.set()
        self._thread: threading.Thread | None = None
        self._stream: Any | None = None
        self._lock = threading.Lock()
        self._level = 0.0

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def is_speaking(self) -> bool:
        return self._active.is_set()

    @property
    def level(self) -> float:
        return self._level

    @property
    def thread_alive(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def speak(self, text: str) -> bool:
        """Inicia la reproducción. Devuelve ``False`` si ya estaba hablando."""
        clean = " ".join((text or "").split())
        if not clean:
            return False
        with self._lock:
            if self._active.is_set():
                return False
            self._active.set()
            self._stop_requested.clear()
            self._done.clear()
            self._level = 0.0
            thread = threading.Thread(
                target=self._run,
                args=(clean,),
                name="jarvis-speech",
                daemon=True,
            )
            self._thread = thread
        thread.start()
        return True

    def stop(self) -> None:
        """Detiene la síntesis y la reproducción en curso."""
        if not self._active.is_set():
            return
        self._stop_requested.set()
        stream = self._current_stream()
        if stream is not None:
            self._abort(stream)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(self._stop_timeout)
        self._emit_level(0.0)

    def wait_until_done(self, timeout: float | None = None) -> bool:
        return self._done.wait(timeout)

    def shutdown(self) -> None:
        """Parada definitiva al cerrar la aplicación."""
        self.stop()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(self._stop_timeout)

    # ------------------------------------------------------------------
    # Hilo de reproducción
    # ------------------------------------------------------------------
    def _run(self, text: str) -> None:
        stream: Any | None = None
        started = False
        try:
            chunks = iter(self._stream_factory(text))
            # Se espera al primer fragmento antes de abrir la salida: si la
            # síntesis falla de inmediato, Windows no abre un dispositivo
            # de audio para nada.
            first: bytes | None = None
            for chunk in chunks:
                if self._stop_requested.is_set():
                    return
                if chunk:
                    first = chunk
                    break
            if first is None:
                raise JarvisError(
                    "ElevenLabs no devolvió audio para leer. Inténtalo de nuevo."
                )

            stream = self._open_stream()
            with self._lock:
                self._stream = stream
            for chunk in _chain_first(first, chunks):
                if self._stop_requested.is_set():
                    break
                if not chunk:
                    continue
                if not started:
                    started = True
                    self._invoke(self.callbacks.on_started)
                self._play(stream, chunk)
        except JarvisError as exc:
            if not self._stop_requested.is_set():
                logger.warning("Fallo de voz: %s", type(exc).__name__)
                self._invoke(self.callbacks.on_error, exc.user_message)
        except Exception as exc:  # pragma: no cover - defensivo
            if not self._stop_requested.is_set():
                logger.warning("Fallo al reproducir la voz: %s", type(exc).__name__)
                self._invoke(
                    self.callbacks.on_error,
                    "La voz se generó, pero no se pudo reproducir. Comprueba "
                    "que haya un dispositivo de salida disponible.",
                )
        finally:
            if stream is not None:
                self._close_stream(stream)
            with self._lock:
                self._stream = None
                self._thread = None
            self._level = 0.0
            self._active.clear()
            self._emit_level(0.0)
            self._done.set()
            self._invoke(self.callbacks.on_done)

    def _play(self, stream: Any, chunk: bytes) -> None:
        for piece in _split_pcm(chunk, self._block_bytes):
            if self._stop_requested.is_set():
                return
            level = dsp.level(piece)
            self._level = level
            self._emit_level(level)
            try:
                stream.write(piece)
            except Exception:
                if self._stop_requested.is_set():
                    return
                raise

    # ------------------------------------------------------------------
    # Dispositivo de salida
    # ------------------------------------------------------------------
    def _open_stream(self) -> Any:
        backend = self._backend
        if backend is None:
            import sounddevice

            backend = sounddevice
        try:
            stream = backend.RawOutputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._block_frames,
            )
            stream.start()
            return stream
        except Exception as exc:
            raise AudioError(
                "No se pudo abrir la salida de audio. Comprueba que haya "
                "altavoces o auriculares conectados y que Windows no los esté "
                "usando en exclusiva.",
                detail=type(exc).__name__,
            ) from exc

    def _current_stream(self) -> Any | None:
        with self._lock:
            return self._stream

    @staticmethod
    def _abort(stream: Any) -> None:
        abort = getattr(stream, "abort", None)
        if callable(abort):
            try:
                abort()
                return
            except Exception:  # pragma: no cover - el flujo pudo cerrarse solo
                pass
        stop = getattr(stream, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:  # pragma: no cover
                pass

    @staticmethod
    def _close_stream(stream: Any) -> None:
        for name in ("stop", "close"):
            action = getattr(stream, name, None)
            if callable(action):
                try:
                    action()
                except Exception:  # pragma: no cover
                    pass

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _emit_level(self, value: float) -> None:
        self._invoke(self.callbacks.on_level, value)

    def _invoke(self, callback: Callable | None, *args: Any) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # pragma: no cover - un callback roto no detiene la voz
            logger.exception("Fallo en un callback de voz")


__all__ = [
    "SpeechCallbacks",
    "SpeechOutput",
]
