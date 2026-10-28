"""Procesamiento de audio PCM sin dependencias externas.

Todo el audio de Jarvis es PCM entero de 16 bits, mono, ordenador pequeño
(el que usan PortAudio y ElevenLabs). Se evita NumPy a propósito: la
captura con ``sounddevice.RawInputStream`` no lo necesita y así el proyecto
mantiene una única dependencia de audio.
"""

from __future__ import annotations

import math
import sys
from array import array

SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320
FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE  # 640

# Rango útil para el visualizador: silencio de fondo -> voz cercana.
_LEVEL_FLOOR_DB = -60.0
_LEVEL_CEILING_DB = -10.0
_SILENCE_RMS = 1.0


def _is_little_endian() -> bool:
    return sys.byteorder == "little"


def pcm16_to_samples(data: bytes) -> array:
    """Convierte bytes PCM int16 en un array de enteros (sin copia doble)."""
    if len(data) % BYTES_PER_SAMPLE:
        # Un byte suelto no forma una muestra; se descarta en el borde.
        data = data[: len(data) - 1]
    samples = array("h")
    samples.frombytes(data)
    if not _is_little_endian():
        samples.byteswap()
    return samples


def samples_to_pcm16(samples: array) -> bytes:
    """Convierte enteros en bytes PCM int16 con recorte de seguridad."""
    if not _is_little_endian():
        copy = array("h", samples)
        copy.byteswap()
        return copy.tobytes()
    return samples.tobytes()


def clamp_sample(value: float) -> int:
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return int(value)


def rms(pcm: bytes) -> float:
    """Nivel eficaz de la señal (0..32767). Devuelve 0 si no hay muestras."""
    samples = pcm16_to_samples(pcm)
    if not samples:
        return 0.0
    total = 0
    for sample in samples:
        total += sample * sample
    return math.sqrt(total / len(samples))


def peak(pcm: bytes) -> int:
    samples = pcm16_to_samples(pcm)
    return max((abs(sample) for sample in samples), default=0)


def dbfs(value: float, reference: float = 32768.0) -> float:
    """Convierte un nivel absoluto en dBFS (siempre negativo o cero)."""
    if value <= _SILENCE_RMS:
        return -90.0
    return max(-90.0, 20.0 * math.log10(value / reference))


def level(pcm_or_rms: bytes | float) -> float:
    """Nivel normalizado 0..1 para los visualizadores.

    Se usa una escala logarítmica: un micrófono típico entrega RMS de ~10
    en silencio y ~2000 al hablar, y una escala lineal dejaría la animación
    pegada al cero.
    """
    value = rms(pcm_or_rms) if isinstance(pcm_or_rms, (bytes, bytearray)) else pcm_or_rms
    db = dbfs(value)
    span = _LEVEL_CEILING_DB - _LEVEL_FLOOR_DB
    return max(0.0, min(1.0, (db - _LEVEL_FLOOR_DB) / span))


class LevelSmoother:
    """Suaviza el nivel con ataque rápido y caída lenta (por tiempo real).

    Se pasa ``dt`` en segundos para que el resultado no dependa de la tasa
    de refresco de la interfaz.
    """

    def __init__(self, *, attack: float = 0.04, release: float = 0.30) -> None:
        self.attack = max(1e-3, attack)
        self.release = max(1e-3, release)
        self._value = 0.0

    @property
    def value(self) -> float:
        return self._value

    def reset(self, value: float = 0.0) -> None:
        self._value = max(0.0, min(1.0, value))

    def update(self, target: float, dt: float) -> float:
        target = max(0.0, min(1.0, target))
        tau = self.attack if target > self._value else self.release
        if dt <= 0:
            return self._value
        alpha = 1.0 - math.exp(-dt / tau)
        self._value += (target - self._value) * alpha
        if self._value < 1e-4:
            self._value = 0.0
        return self._value


class StreamResampler:
    """Remuestreo continuo int16 mono por interpolación lineal.

    Mantiene la posición fraccionaria entre bloques para no introducir
    clics en cada frontera. Es suficiente para voz destinada a STT; no se
    usa para música ni para análisis espectral fino.
    """

    def __init__(self, source_rate: int, target_rate: int) -> None:
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError("Las frecuencias deben ser positivas")
        self.source_rate = int(source_rate)
        self.target_rate = int(target_rate)
        self._ratio = self.source_rate / self.target_rate
        self._position = 0.0
        self._carry = b""

    @property
    def ratio(self) -> float:
        return self._ratio

    @property
    def passthrough(self) -> bool:
        return self.source_rate == self.target_rate

    def reset(self) -> None:
        self._position = 0.0
        self._carry = b""

    def process(self, data: bytes) -> bytes:
        if not data:
            return b""
        if self.passthrough:
            return data

        buffer = self._carry + data
        if len(buffer) % BYTES_PER_SAMPLE:
            self._carry = buffer[-1:]
            buffer = buffer[:-1]
        else:
            self._carry = b""
        if not buffer:
            return b""

        samples = pcm16_to_samples(buffer)
        count = len(samples)
        ratio = self._ratio
        position = self._position
        output = array("h")

        while position < count:
            index = int(position)
            fraction = position - index
            first = samples[index]
            if index + 1 < count:
                second = samples[index + 1]
            else:
                second = first
            output.append(clamp_sample(first + (second - first) * fraction))
            position += ratio

        self._position = position - count
        return samples_to_pcm16(output)


def resample_pcm16(data: bytes, source_rate: int, target_rate: int) -> bytes:
    """Remuestrea un bloque completo (sin estado entre llamadas)."""
    return StreamResampler(source_rate, target_rate).process(data)


def duration_seconds(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> float:
    if sample_rate <= 0:
        return 0.0
    return (len(pcm) // BYTES_PER_SAMPLE) / sample_rate


def silence(seconds: float, sample_rate: int = SAMPLE_RATE) -> bytes:
    count = max(0, int(seconds * sample_rate))
    return b"\x00\x00" * count
