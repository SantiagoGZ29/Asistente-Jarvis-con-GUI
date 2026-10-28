"""Detección local de actividad de voz (VAD) por energía.

Se ejecuta en el hilo de captura, sin bibliotecas externas. Detecta el
inicio de una frase, su final por silencio y descarta ruidos demasiado
cortos. Incluye un búfer previo para no cortar la primera sílaba.

Los umbrales se ajustan desde ``Settings`` y se pueden cambiar sin tocar
el código. El nivel de ruido se adapta lentamente al entorno.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from jarvis.audio import dsp

# Dos tramas seguidas (40 ms) evitan que un golpe aislado abra un turno.
START_FRAMES = 2
# Al cerrar una frase se conserva una cola breve para no cortar la última sílaba.
TAIL_MS = 100
# Suelo de ruido inicial (RMS). Se adapta durante la sesión.
INITIAL_NOISE_FLOOR = 20.0


class VadEventType(str, Enum):
    SPEECH_START = "speech_start"
    SPEECH_END = "speech_end"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class VadEvent:
    kind: VadEventType
    segment: bytes | None = None
    duration_s: float = 0.0
    voiced_s: float = 0.0

    @property
    def is_valid_segment(self) -> bool:
        return self.kind is VadEventType.SPEECH_END and bool(self.segment)


@dataclass(frozen=True)
class VadUpdate:
    level: float
    speaking: bool
    events: tuple[VadEvent, ...] = field(default=())


class VoiceActivityDetector:
    """Segmenta un flujo PCM continuo en intervenciones de voz."""

    def __init__(
        self,
        *,
        sample_rate: int = dsp.SAMPLE_RATE,
        frame_ms: int = dsp.FRAME_MS,
        margin_db: float = 9.0,
        min_rms: float = 120.0,
        min_speech_ms: int = 250,
        silence_ms: int = 850,
        preroll_ms: int = 300,
        max_utterance_s: float = 30.0,
    ) -> None:
        if sample_rate <= 0 or frame_ms <= 0:
            raise ValueError("La frecuencia y la trama deben ser positivas")
        self.sample_rate = int(sample_rate)
        self.frame_ms = int(frame_ms)
        self.margin_db = float(margin_db)
        self.min_rms = float(min_rms)
        self.min_speech_ms = int(min_speech_ms)
        self.silence_ms = int(silence_ms)
        self.preroll_ms = int(preroll_ms)
        self.max_utterance_s = float(max_utterance_s)

        self.frame_samples = max(1, self.sample_rate * self.frame_ms // 1000)
        self.frame_bytes = self.frame_samples * dsp.BYTES_PER_SAMPLE
        self._preroll_frames = max(1, self.preroll_ms // self.frame_ms)
        self._silence_frames_needed = max(1, self.silence_ms // self.frame_ms)
        self._tail_frames = max(0, TAIL_MS // self.frame_ms)
        self._max_samples = max(self.frame_samples, int(self.max_utterance_s * self.sample_rate))

        self._noise_floor = INITIAL_NOISE_FLOOR
        self._buffer = b""
        self._preroll: deque[bytes] = deque(maxlen=self._preroll_frames)
        self._segment = bytearray()
        self._candidate_frames = 0
        self._silence_frames = 0
        self._preroll_bytes = 0
        self._wait_silence = False
        self._in_speech = False
        self._level = 0.0

    # ------------------------------------------------------------------
    # Propiedades de diagnóstico
    # ------------------------------------------------------------------
    @property
    def speaking(self) -> bool:
        return self._in_speech

    @property
    def level(self) -> float:
        return self._level

    @property
    def noise_floor(self) -> float:
        return self._noise_floor

    @property
    def threshold(self) -> float:
        adaptive = self._noise_floor * (10 ** (self.margin_db / 20.0))
        return max(self.min_rms, adaptive)

    def reset(self) -> None:
        """Olvida el estado de la frase actual (no toca el suelo de ruido)."""
        self._buffer = b""
        self._preroll.clear()
        self._segment = bytearray()
        self._candidate_frames = 0
        self._silence_frames = 0
        self._preroll_bytes = 0
        self._wait_silence = False
        self._in_speech = False
        self._level = 0.0

    def flush(self) -> VadEvent | None:
        """Cierra la frase en curso al pausar o detener la captura."""
        if not self._in_speech:
            self.reset()
            return None
        event = self._finish_speech()
        self.reset()
        return event

    # ------------------------------------------------------------------
    # Procesamiento
    # ------------------------------------------------------------------
    def feed(self, pcm: bytes) -> VadUpdate:
        """Procesa un bloque arbitrario y devuelve eventos de la frase."""
        if not pcm:
            return VadUpdate(level=self._level, speaking=self._in_speech)

        self._buffer += pcm
        events: list[VadEvent] = []
        while len(self._buffer) >= self.frame_bytes:
            frame = self._buffer[: self.frame_bytes]
            self._buffer = self._buffer[self.frame_bytes :]
            event = self._handle_frame(frame)
            if event is not None:
                events.append(event)
        return VadUpdate(
            level=self._level,
            speaking=self._in_speech,
            events=tuple(events),
        )

    def _handle_frame(self, frame: bytes) -> VadEvent | None:
        value = dsp.rms(frame)
        threshold = self.threshold
        self._level = dsp.level(value)

        # Tras cortar por duración máxima se espera un silencio real antes
        # de abrir otro turno; si no, la misma frase se partiría en dos.
        if self._wait_silence:
            if value < threshold:
                self._wait_silence = False
                self._candidate_frames = 0
            self._preroll.append(frame)
            return None

        if not self._in_speech:
            if value < threshold:
                # Media exponencial: se adapta a un ventilador o a una sala
                # ruidosa sin disparar por un ruido puntual.
                self._noise_floor = 0.95 * self._noise_floor + 0.05 * value
            self._preroll.append(frame)
            if value >= threshold:
                self._candidate_frames += 1
                if self._candidate_frames >= START_FRAMES:
                    return self._begin_speech()
            else:
                self._candidate_frames = 0
            return None

        self._segment.extend(frame)
        if value >= threshold:
            self._silence_frames = 0
        else:
            self._silence_frames += 1

        reached_silence = self._silence_frames >= self._silence_frames_needed
        too_long = len(self._segment) // dsp.BYTES_PER_SAMPLE >= self._max_samples
        if reached_silence:
            return self._finish_speech()
        if too_long:
            return self._finish_speech(wait_silence=True)
        return None

    def _begin_speech(self) -> VadEvent:
        self._in_speech = True
        self._candidate_frames = 0
        self._silence_frames = 0
        # El búfer previo incluye las tramas anteriores y las dos que
        # confirmaron la voz, así que no se pierde el arranque.
        self._segment = bytearray(b"".join(self._preroll))
        self._preroll_bytes = len(self._segment)
        self._preroll.clear()
        duration = self._segment_duration()
        return VadEvent(
            kind=VadEventType.SPEECH_START,
            duration_s=duration,
            voiced_s=0.0,
        )

    def _finish_speech(self, *, wait_silence: bool = False) -> VadEvent:
        total_samples = len(self._segment) // dsp.BYTES_PER_SAMPLE
        preroll_samples = self._preroll_bytes // dsp.BYTES_PER_SAMPLE
        voiced_samples = max(
            0,
            total_samples
            - preroll_samples
            - self._silence_frames * self.frame_samples,
        )
        self._in_speech = False

        if self._silence_frames:
            trim_frames = max(0, self._silence_frames - self._tail_frames)
            trim_bytes = trim_frames * self.frame_bytes
            if trim_bytes:
                del self._segment[-trim_bytes:]
        segment = bytes(self._segment)
        duration = len(segment) / dsp.BYTES_PER_SAMPLE / self.sample_rate
        voiced = voiced_samples / self.sample_rate
        self._segment = bytearray()
        self._silence_frames = 0
        self._candidate_frames = 0
        self._preroll.clear()
        self._preroll_bytes = 0
        self._wait_silence = wait_silence

        if voiced * 1000 < self.min_speech_ms:
            return VadEvent(
                kind=VadEventType.DISCARDED,
                segment=None,
                duration_s=duration,
                voiced_s=voiced,
            )
        return VadEvent(
            kind=VadEventType.SPEECH_END,
            segment=segment,
            duration_s=duration,
            voiced_s=voiced,
        )

    def _segment_duration(self) -> float:
        return len(self._segment) / dsp.BYTES_PER_SAMPLE / self.sample_rate

    def frame_levels(self, pcm: bytes) -> list[float]:
        """Niveles por trama de un bloque (útil para pruebas y diagnóstico)."""
        levels: list[float] = []
        buffer = pcm
        while len(buffer) >= self.frame_bytes:
            levels.append(dsp.level(dsp.rms(buffer[: self.frame_bytes])))
            buffer = buffer[self.frame_bytes :]
        return levels


def threshold_rms(noise_floor: float, margin_db: float, min_rms: float) -> float:
    """Umbral efectivo para un suelo de ruido dado (expuesto para pruebas)."""
    return max(min_rms, noise_floor * (10 ** (margin_db / 20.0)))


__all__ = [
    "INITIAL_NOISE_FLOOR",
    "START_FRAMES",
    "VadEvent",
    "VadEventType",
    "VadUpdate",
    "VoiceActivityDetector",
    "threshold_rms",
]
