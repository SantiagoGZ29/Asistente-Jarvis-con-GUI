"""Reconocimiento de voz: Scribe Realtime v2 con respaldo por lotes.

El SDK de ElevenLabs es asíncrono. ``RealtimeTranscriber`` ejecuta su
propio bucle de eventos en un hilo dedicado para no bloquear ni Qt ni la
captura. ``HybridTranscriber`` decide en caliente: si el tiempo real falla,
transcribe el segmento con la API por lotes sin pedir nada al usuario.
"""

from __future__ import annotations

import asyncio
import base64
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from jarvis.audio import dsp
from jarvis.core.errors import AudioError, JarvisError, classify_provider_error
from jarvis.core.logging_setup import get_logger

logger = get_logger("stt")


@dataclass
class SttCallbacks:
    """Eventos de transcripción.

    El identificador de intervención permite descartar resultados tardíos
    de una frase que el usuario ya canceló.
    """

    on_partial: Callable[[str, int], None] = lambda text, utterance: None
    on_final: Callable[[str, int], None] = lambda text, utterance: None
    on_error: Callable[[str], None] = lambda message: None
    on_notice: Callable[[str], None] = lambda message: None


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


class BatchTranscriber:
    """Transcribe el segmento completo al terminar la frase (respaldo)."""

    def __init__(
        self,
        transcribe: Callable[[Path], str],
        callbacks: SttCallbacks,
        *,
        sample_rate: int = dsp.SAMPLE_RATE,
        temp_dir: Path | str | None = None,
    ) -> None:
        self._transcribe = transcribe
        self.callbacks = callbacks
        self.sample_rate = sample_rate
        self._temp_dir = Path(temp_dir) if temp_dir else None
        self._utterance = 0
        self._lock = threading.Lock()
        self._threads: set[threading.Thread] = set()
        self._stopped = False

    def start(self) -> None:  # compatibilidad con la interfaz común
        self._stopped = False

    def push_audio(self, pcm: bytes) -> None:
        """El modo por lotes no necesita audio en tiempo real."""

    def commit(self, segment: bytes) -> int:
        """Encola la transcripción del segmento y devuelve su identificador."""
        if not segment:
            return self._utterance
        with self._lock:
            self._utterance += 1
            utterance = self._utterance
        thread = threading.Thread(
            target=self._worker,
            args=(segment, utterance),
            name="jarvis-stt-batch",
            daemon=True,
        )
        with self._lock:
            self._threads.add(thread)
        thread.start()
        return utterance

    def cancel(self) -> None:
        with self._lock:
            self._utterance += 1

    def stop(self) -> None:
        self._stopped = True
        self.cancel()
        deadline = time.monotonic() + 2.0
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)

    def _worker(self, segment: bytes, utterance: int) -> None:
        path: Path | None = None
        try:
            path = self._write_wav(segment)
            text = _clean(self._transcribe(path))
            if self._is_current(utterance) and text:
                self.callbacks.on_final(text, utterance)
        except JarvisError as exc:
            if self._is_current(utterance):
                self.callbacks.on_error(exc.user_message)
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning("Fallo al transcribir por lotes: %s", type(exc).__name__)
            if self._is_current(utterance):
                self.callbacks.on_error(
                    "No se pudo transcribir la frase. Inténtalo de nuevo o escríbela."
                )
        finally:
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:  # pragma: no cover
                    pass
            with self._lock:
                self._threads.discard(threading.current_thread())

    def _is_current(self, utterance: int) -> bool:
        with self._lock:
            return not self._stopped and utterance == self._utterance

    def _write_wav(self, segment: bytes) -> Path:
        handle = tempfile.NamedTemporaryFile(
            suffix=".wav",
            prefix="jarvis_stt_",
            dir=str(self._temp_dir) if self._temp_dir else None,
            delete=False,
        )
        path = Path(handle.name)
        try:
            handle.close()
            with wave.open(str(path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(segment)
        except Exception:
            handle.close()
            path.unlink(missing_ok=True)
            raise
        return path


async def default_realtime_connect(
    *, api_key: str, model_id: str, language: str | None
) -> Any:
    """Conexión real con el SDK oficial (importación diferida)."""
    from elevenlabs.client import ElevenLabs
    from elevenlabs.realtime.scribe import AudioFormat, CommitStrategy

    client = ElevenLabs(api_key=api_key)
    options: dict[str, Any] = {
        "model_id": model_id,
        "audio_format": AudioFormat.PCM_16000,
        "sample_rate": dsp.SAMPLE_RATE,
        "commit_strategy": CommitStrategy.MANUAL,
    }
    if language:
        options["language_code"] = language
    return await client.speech_to_text.realtime.connect(options)


class RealtimeTranscriber:
    """Scribe Realtime v2 en un hilo con su propio bucle asyncio."""

    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        language: str | None,
        callbacks: SttCallbacks,
        connect: Callable[..., Any] | None = None,
        connect_timeout: float = 8.0,
        ready_timeout: float | None = None,
    ) -> None:
        self._api_key = api_key
        self._model_id = model_id
        self._language = language
        self.callbacks = callbacks
        self._connect = connect or default_realtime_connect
        self._connect_timeout = connect_timeout
        self._ready_timeout = (
            max(0.1, ready_timeout)
            if ready_timeout is not None
            else connect_timeout + 2.0
        )

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._connection: Any | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._utterance = 0
        self._healthy = False
        self._closed = False
        self._send_failures = 0
        self._inflight = 0
        self._lock = threading.Lock()

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def utterance(self) -> int:
        return self._utterance

    def set_callbacks(self, callbacks: SttCallbacks) -> None:
        """Permite a otro componente (p. ej. el híbrido) enrutar los eventos."""
        self.callbacks = callbacks

    def start(self) -> None:
        if self._thread is not None:
            return
        self._ready.clear()
        self._start_error = None
        self._closed = False
        self._send_failures = 0
        with self._lock:
            self._inflight = 0
        self._thread = threading.Thread(
            target=self._run, name="jarvis-stt-realtime", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(self._ready_timeout):
            self.stop()
            raise AudioError(
                "El servicio de transcripción en tiempo real no respondió a tiempo."
            )
        if self._start_error is not None:
            error = self._start_error
            self.stop()
            if isinstance(error, JarvisError):
                raise error
            raise classify_provider_error(error, "ElevenLabs")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            connection = loop.run_until_complete(
                asyncio.wait_for(
                    self._connect(
                        api_key=self._api_key,
                        model_id=self._model_id,
                        language=self._language,
                    ),
                    timeout=self._connect_timeout,
                )
            )
            self._connection = connection
            self._subscribe(connection)
            if self._closed:
                # ``stop()`` se ejecutó mientras conectábamos: no dejamos la
                # conexión abierta ni arrancamos el bucle.
                loop.run_until_complete(connection.close())
                self._connection = None
                self._ready.set()
                return
            self._healthy = True
            self._ready.set()
            loop.run_forever()
        except BaseException as exc:  # noqa: BLE001 - se guarda para start()
            self._start_error = exc
            self._healthy = False
            self._ready.set()
            logger.info("Scribe realtime no disponible: %s", type(exc).__name__)
        finally:
            self._healthy = False
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:  # pragma: no cover
                pass
            loop.close()
            self._connection = None
            self._loop = None

    def _subscribe(self, connection: Any) -> None:
        try:
            from elevenlabs.realtime.connection import RealtimeEvents
        except Exception:  # pragma: no cover - SDK ausente
            return
        connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, self._partial)
        connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, self._committed)
        connection.on(RealtimeEvents.ERROR, self._error_event)
        connection.on(RealtimeEvents.CLOSE, self._close_event)

    # ------------------------------------------------------------------
    # Eventos del servidor
    # ------------------------------------------------------------------
    def _partial(self, data: Any) -> None:
        text = _clean((data or {}).get("transcript"))
        if text:
            self.callbacks.on_partial(text, self._utterance)

    def _committed(self, data: Any) -> None:
        text = _clean((data or {}).get("transcript"))
        if text:
            logger.info("Transcripción en tiempo real recibida (%d caracteres)", len(text))
            self.callbacks.on_final(text, self._utterance)

    def _error_event(self, data: Any) -> None:
        message = _clean((data or {}).get("error") or (data or {}).get("message"))
        logger.warning("Error de Scribe realtime: %s", message[:120] or "sin detalle")
        self._healthy = False
        self.callbacks.on_error(
            "La transcripción en tiempo real falló. Jarvis usará el modo por lotes."
        )

    def _close_event(self, data: Any) -> None:
        self._healthy = False

    # ------------------------------------------------------------------
    # Audio y ciclo de vida
    # ------------------------------------------------------------------
    def push_audio(self, pcm: bytes) -> None:
        if not self._healthy or not pcm:
            return
        loop = self._loop
        connection = self._connection
        if loop is None or connection is None or not loop.is_running():
            return
        with self._lock:
            if self._send_failures > 5 or self._inflight >= 32:
                return
            self._inflight += 1
        payload = base64.b64encode(pcm).decode("ascii")
        try:
            future = asyncio.run_coroutine_threadsafe(
                connection.send({"audio_base_64": payload}), loop
            )
        except Exception:
            with self._lock:
                self._inflight -= 1
                self._send_failures += 1
            return
        future.add_done_callback(self._send_done)

    def _send_done(self, future: Any) -> None:
        try:
            future.result()
            with self._lock:
                self._inflight -= 1
                self._send_failures = 0
        except Exception:
            with self._lock:
                self._inflight -= 1
                self._send_failures += 1
                failures = self._send_failures
            if failures == 3:
                logger.warning("No se pudo enviar audio a Scribe realtime")
                self.callbacks.on_notice(
                    "Se perdió la conexión de transcripción; se usará el modo por lotes."
                )
                self._healthy = False

    def commit(self, segment: bytes) -> int:
        loop = self._loop
        connection = self._connection
        if loop is None or connection is None or not self._healthy:
            raise AudioError("La transcripción en tiempo real no está disponible.")
        with self._lock:
            self._utterance += 1
            utterance = self._utterance
        future = asyncio.run_coroutine_threadsafe(connection.commit(), loop)
        future.result(timeout=3.0)
        return utterance

    def cancel(self) -> None:
        with self._lock:
            self._utterance += 1

    def stop(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._healthy = False
        loop = self._loop
        connection = self._connection
        if loop is not None and connection is not None and loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(connection.close(), loop)
                future.result(timeout=2.0)
            except Exception:
                pass
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(3.0)
        self._thread = None
        self._connection = None
        self._loop = None


class HybridTranscriber:
    """Usa tiempo real y cae a lotes sin intervención del usuario.

    Reglas de entrega:

    * Una intervención produce **un único** ``on_final``: el de Scribe o,
      si no llega a tiempo, el del modo por lotes.
    * Un resultado tardío de una intervención cancelada o ya resuelta se
      descarta en silencio.
    * Los commits se serializan para que un final del servidor no pueda
      asignarse a la frase siguiente.
    """

    def __init__(
        self,
        *,
        callbacks: SttCallbacks,
        realtime: RealtimeTranscriber | None,
        batch: BatchTranscriber,
        final_timeout: float = 6.0,
    ) -> None:
        self.callbacks = callbacks
        self.realtime = realtime
        self.batch = batch
        self.final_timeout = max(0.1, float(final_timeout))
        self._lock = threading.Lock()
        self._commit_lock = threading.Lock()
        self._pending: dict[int, threading.Event] = {}
        self._results: dict[int, str] = {}
        self._early: dict[int, str] = {}
        self._workers: set[threading.Thread] = set()
        self._generation = 0
        self._stopped = True
        self._last_notice = ""

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    @property
    def realtime_active(self) -> bool:
        return bool(self.realtime and self.realtime.healthy)

    @property
    def mode(self) -> str:
        return "realtime" if self.realtime_active else "batch"

    def _current(self, generation: int) -> bool:
        with self._lock:
            return not self._stopped and generation == self._generation

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            self._stopped = False
            self._generation += 1
            self._pending.clear()
            self._results.clear()
            self._early.clear()
            self._last_notice = ""
        self.batch.start()
        self._install_realtime_callbacks()
        if self.realtime is None:
            return
        try:
            self.realtime.start()
            logger.info("Transcripción en tiempo real activa")
        except Exception as exc:
            logger.info("Se usará transcripción por lotes: %s", type(exc).__name__)
            self.realtime = None
            if isinstance(exc, JarvisError):
                detail = exc.user_message
            else:
                detail = "el servicio no está disponible"
            self._notify(
                f"La transcripción en tiempo real no está disponible ({detail}). "
                "Jarvis usará el modo por lotes automáticamente."
            )

    def _install_realtime_callbacks(self) -> None:
        if self.realtime is None:
            return
        wrapped = SttCallbacks(
            on_partial=self._realtime_partial,
            on_final=self._realtime_final,
            on_error=self._realtime_error,
            on_notice=self._notify,
        )
        setter = getattr(self.realtime, "set_callbacks", None)
        if callable(setter):
            setter(wrapped)
        else:  # pragma: no cover - implementaciones mínimas en pruebas
            self.realtime.callbacks = wrapped  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Audio y envío
    # ------------------------------------------------------------------
    def push_audio(self, pcm: bytes) -> None:
        if not pcm or self._stopped or not self.realtime_active:
            return
        self.realtime.push_audio(pcm)  # type: ignore[union-attr]

    def commit(self, segment: bytes) -> None:
        if not segment or self._stopped:
            return
        if not self.realtime_active:
            self.batch.commit(segment)
            return
        with self._lock:
            generation = self._generation
            thread = threading.Thread(
                target=self._commit_realtime,
                args=(segment, generation),
                name="jarvis-stt-commit",
                daemon=True,
            )
            self._workers.add(thread)
        thread.start()

    def _commit_realtime(self, segment: bytes, generation: int) -> None:
        try:
            with self._commit_lock:
                self._commit_locked(segment, generation)
        finally:
            with self._lock:
                self._workers.discard(threading.current_thread())

    def _commit_locked(self, segment: bytes, generation: int) -> None:
        realtime = self.realtime
        if not self._current(generation) or realtime is None:
            return

        try:
            utterance = realtime.commit(segment)
        except Exception:
            logger.info("Commit en tiempo real falló; se transcribe por lotes")
            if self._current(generation):
                self._notify(
                    "La transcripción en tiempo real falló; se usará el modo por lotes."
                )
                self.batch.commit(segment)
            return

        event = threading.Event()
        with self._lock:
            self._pending[utterance] = event
            early = self._early.pop(utterance, None)
            if early is not None:
                self._results[utterance] = early
        if early is not None:
            event.set()

        received = event.wait(self.final_timeout)
        with self._lock:
            self._pending.pop(utterance, None)
            text = self._results.pop(utterance, "")

        # ``cancel()`` o ``stop()`` despiertan el evento sin entregar nada.
        if not self._current(generation):
            return
        if received and text:
            self.callbacks.on_final(text, utterance)
            return

        logger.info("Sin transcripción final en tiempo real; se usa el lote")
        self.batch.commit(segment)

    # ------------------------------------------------------------------
    # Eventos del tiempo real
    # ------------------------------------------------------------------
    def _realtime_partial(self, text: str, utterance: int) -> None:
        if text and not self._stopped:
            self.callbacks.on_partial(text, utterance)

    def _realtime_final(self, text: str, utterance: int) -> None:
        text = _clean(text)
        if not text or self._stopped:
            return
        with self._lock:
            event = self._pending.get(utterance)
            if event is None:
                # El servidor respondió antes de que el hilo del commit
                # registrara la intervención: se guarda para reclamarla.
                self._early[utterance] = text
                while len(self._early) > 8:
                    self._early.pop(next(iter(self._early)))
                return
            self._results[utterance] = text
        event.set()

    def _realtime_error(self, message: str) -> None:
        # El respaldo por lotes sigue disponible: es un aviso, no un fallo
        # definitivo. Si el lote también falla, ese error sí se mostrará.
        if not self._stopped:
            self._notify(message)

    def _notify(self, message: str) -> None:
        clean = " ".join((message or "").split())
        if not clean:
            return
        with self._lock:
            if clean == self._last_notice:
                return
            self._last_notice = clean
        self.callbacks.on_notice(clean)

    # ------------------------------------------------------------------
    # Cancelación y cierre
    # ------------------------------------------------------------------
    def cancel(self) -> None:
        with self._lock:
            self._generation += 1
            pending = list(self._pending.values())
            self._pending.clear()
            self._results.clear()
            self._early.clear()
        for event in pending:
            event.set()
        self.batch.cancel()
        if self.realtime is not None:
            self.realtime.cancel()

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
        self.cancel()
        if self.realtime is not None:
            self.realtime.stop()
        self.batch.stop()
        deadline = time.monotonic() + 2.0
        with self._lock:
            workers = list(self._workers)
        for thread in workers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(remaining)
