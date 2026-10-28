"""Captura explícita de audio del micrófono.

No hay escucha permanente ni palabra de activación: la grabación empieza
solo cuando el usuario lo pide y termina cuando lo detiene (o al alcanzar
el límite configurado). El archivo temporal se elimina al terminar.
"""

from __future__ import annotations

import importlib
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

from jarvis.core.errors import AudioError, AudioNotAvailableError
from jarvis.core.logging_setup import get_logger

logger = get_logger("recorder")


class AudioRecorder:
    """Graba audio mono de 16 bits en un archivo WAV temporal."""

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        max_seconds: float = 60.0,
        backend: Any | None = None,
        temp_dir: Path | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.max_seconds = max_seconds
        self._backend = backend
        self._temp_dir = Path(temp_dir) if temp_dir else None
        self._stream: Any | None = None
        self._frames: list[bytes] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._started_at = 0.0
        self._active = False
        self._last_path: Path | None = None

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def is_recording(self) -> bool:
        return self._active

    def _load_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        try:
            self._backend = importlib.import_module("sounddevice")
        except Exception as exc:  # pragma: no cover - depende del sistema
            raise AudioNotAvailableError(
                "No se pudo cargar el sistema de audio (sounddevice). "
                "Comprueba que esté instalado con 'pip install -r requirements.txt'."
            ) from exc
        return self._backend

    def is_available(self) -> bool:
        """Comprueba si hay algún dispositivo de entrada disponible."""
        try:
            backend = self._load_backend()
            devices = backend.query_devices()
            return bool(devices)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Grabación
    # ------------------------------------------------------------------
    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        if status:
            logger.debug("Aviso del flujo de audio: %s", status)
        if not self._active:
            return
        data = bytes(indata)
        if data:
            self._frames.append(data)

    def start(self) -> None:
        """Inicia la grabación; el usuario decide cuándo detenerla."""
        if self._active:
            raise AudioError("Ya hay una grabación en curso.")
        backend = self._load_backend()

        self._frames = []
        self._last_path = None
        self._started_at = time.monotonic()
        self._active = True
        try:
            stream = backend.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=self._callback,
            )
            stream.start()
        except Exception as exc:
            self._active = False
            raise AudioNotAvailableError(
                "No se pudo abrir el micrófono. Comprueba que esté conectado y "
                "que otra aplicación no lo esté usando."
            ) from exc
        self._stream = stream

        if self.max_seconds > 0:
            self._timer = threading.Timer(self.max_seconds, self._stop_by_timer)
            self._timer.daemon = True
            self._timer.start()

        logger.info("Grabación iniciada (máx. %.0f s)", self.max_seconds)

    def _stop_by_timer(self) -> None:
        if not self._active:
            return
        logger.info("Límite de grabación alcanzado")
        try:
            self.stop()
        except AudioError:  # pragma: no cover - carrera con stop manual
            pass

    def stop(self) -> Path:
        """Detiene la grabación y devuelve la ruta del WAV temporal.

        Si el límite de tiempo ya detuvo la grabación, devuelve el archivo
        generado por ese cierre automático.
        """
        with self._lock:
            if not self._active or self._stream is None:
                if self._last_path is not None:
                    return self._last_path
                raise AudioError("No hay ninguna grabación en curso.")
            self._active = False
            stream = self._stream
            self._stream = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

            try:
                stream.stop()
                stream.close()
            except Exception:  # pragma: no cover - cierre defensivo
                logger.warning("No se pudo cerrar el flujo de audio correctamente")

            frames = self._frames
            self._frames = []
            elapsed = time.monotonic() - self._started_at

        if not frames:
            raise AudioError(
                "No se capturó audio. Comprueba el micrófono e inténtalo de nuevo."
            )
        if elapsed < 0.3:
            logger.info("Grabación demasiado corta (%.1f s)", elapsed)

        path = self._write_wav(frames)
        with self._lock:
            self._last_path = path
        return path

    def _write_wav(self, frames: list[bytes]) -> Path:
        directory = str(self._temp_dir) if self._temp_dir else None
        handle = tempfile.NamedTemporaryFile(
            prefix="jarvis_voz_",
            suffix=".wav",
            delete=False,
            dir=directory,
        )
        path = Path(handle.name)
        handle.close()
        try:
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(b"".join(frames))
        except Exception as exc:  # pragma: no cover - disco lleno, permisos
            self.delete_file(path)
            raise AudioError(
                "No se pudo guardar la grabación temporal. Comprueba el espacio "
                "en disco y los permisos de la carpeta temporal."
            ) from exc
        logger.info("Grabación guardada temporalmente (%d bytes)", path.stat().st_size)
        return path

    def cancel(self) -> None:
        """Cancela la grabación en curso sin generar archivo."""
        with self._lock:
            if not self._active or self._stream is None:
                return
            self._active = False
            stream = self._stream
            self._stream = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            try:
                stream.stop()
                stream.close()
            except Exception:  # pragma: no cover
                pass
            self._frames = []

    def record_for(self, seconds: float) -> Path:
        """Graba durante un tiempo fijo (útil en pruebas y entornos sin teclado)."""
        self.start()
        time.sleep(max(0.0, seconds))
        return self.stop()

    @staticmethod
    def delete_file(path: str | Path | None) -> bool:
        """Elimina un archivo temporal de audio. Devuelve True si lo borró."""
        if not path:
            return False
        target = Path(path)
        try:
            target.unlink(missing_ok=True)
            return True
        except OSError:
            logger.warning("No se pudo eliminar el archivo temporal de audio")
            return False

    def __enter__(self) -> "AudioRecorder":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._active:
            try:
                path = self.stop()
            except AudioError:
                self.cancel()
                return
            if exc_type is not None:
                self.delete_file(path)
        else:
            self.cancel()
