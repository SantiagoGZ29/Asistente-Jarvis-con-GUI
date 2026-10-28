"""Pruebas del procesamiento PCM sin dependencias externas."""

from __future__ import annotations

import math

import pytest

from jarvis.audio import dsp
from jarvis.audio.dsp import LevelSmoother, StreamResampler


def _pcm(*samples: int) -> bytes:
    return b"".join(int(sample).to_bytes(2, "little", signed=True) for sample in samples)


def test_conversion_ida_y_vuelta() -> None:
    data = _pcm(0, 1, -1, 1000, -1000, 32767, -32768)
    samples = dsp.pcm16_to_samples(data)

    assert list(samples) == [0, 1, -1, 1000, -1000, 32767, -32768]
    assert dsp.samples_to_pcm16(samples) == data


def test_byte_impar_se_descarta() -> None:
    samples = dsp.pcm16_to_samples(b"\x01\x02\x03")
    assert len(samples) == 1


def test_rms_y_pico() -> None:
    signal = _pcm(*([1000] * 100))
    assert dsp.rms(signal) == pytest.approx(1000.0)
    assert dsp.peak(signal) == 1000
    assert dsp.rms(b"") == 0.0
    assert dsp.peak(b"") == 0


def test_dbfs() -> None:
    assert dsp.dbfs(32768.0) == pytest.approx(0.0)
    assert dsp.dbfs(0.0) == -90.0
    assert dsp.dbfs(3276.8) == pytest.approx(-20.0, abs=0.01)


def test_nivel_normalizado_es_monotono() -> None:
    niveles = [dsp.level(value) for value in (0.0, 10.0, 100.0, 1000.0, 20000.0)]

    assert niveles[0] == 0.0
    assert niveles == sorted(niveles)
    assert niveles[-1] == 1.0
    assert 0.0 < dsp.level(_pcm(*([800] * 320))) < 1.0


def test_suavizado_con_ataque_rapido_y_caida_lenta() -> None:
    smoother = LevelSmoother(attack=0.03, release=0.40)

    subida = smoother.update(1.0, 0.05)
    assert subida > 0.7

    bajada = smoother.update(0.0, 0.05)
    assert 0.0 < bajada < subida

    for _ in range(100):
        smoother.update(0.0, 0.05)
    assert smoother.value == 0.0


def test_suavizado_sin_tiempo_no_cambia() -> None:
    smoother = LevelSmoother()
    smoother.update(0.8, 0.1)

    assert smoother.update(0.0, 0.0) == smoother.value


def test_remuestreo_48k_a_16k() -> None:
    entrada = _pcm(*([500] * 4800))
    salida = dsp.resample_pcm16(entrada, 48_000, 16_000)

    assert len(salida) // 2 == pytest.approx(1600, abs=2)


def test_remuestreo_44k_a_16k() -> None:
    entrada = _pcm(*([500] * 4410))
    salida = dsp.resample_pcm16(entrada, 44_100, 16_000)

    assert len(salida) // 2 == pytest.approx(1600, abs=3)


def test_remuestreo_conserva_la_amplitud_media() -> None:
    entrada = _pcm(*([1200] * 9600))
    salida = dsp.resample_pcm16(entrada, 48_000, 16_000)

    assert dsp.rms(salida) == pytest.approx(1200, rel=0.05)


def test_remuestreo_sin_cambio_es_passthrough() -> None:
    resampler = StreamResampler(16_000, 16_000)
    data = _pcm(1, 2, 3)

    assert resampler.passthrough is True
    assert resampler.process(data) == data


def test_remuestreo_continuo_equivale_a_un_solo_bloque() -> None:
    entrada = _pcm(*([int(3000 * math.sin(i / 10)) for i in range(4800)]))

    completo = dsp.resample_pcm16(entrada, 48_000, 16_000)

    resampler = StreamResampler(48_000, 16_000)
    por_trozos = b"".join(
        resampler.process(entrada[inicio : inicio + 640])
        for inicio in range(0, len(entrada), 640)
    )

    assert len(por_trozos) // 2 == pytest.approx(len(completo) // 2, abs=1)
    # La diferencia máxima entre ambos métodos debe ser un sample como mucho.
    a = dsp.pcm16_to_samples(completo)
    b = dsp.pcm16_to_samples(por_trozos)
    limite = min(len(a), len(b))
    assert max(abs(a[i] - b[i]) for i in range(limite)) <= 2


def test_remuestreo_con_bytes_impares_entre_bloques() -> None:
    resampler = StreamResampler(48_000, 16_000)
    salida = resampler.process(_pcm(*([400] * 10)) + b"\x00") + resampler.process(
        _pcm(*([400] * 10))
    )

    assert len(salida) % 2 == 0
    assert len(salida) // 2 >= 5


def test_frecuencia_invalida() -> None:
    with pytest.raises(ValueError):
        StreamResampler(0, 16_000)


def test_duracion_y_silencio() -> None:
    assert dsp.duration_seconds(_pcm(*([0] * 16_000))) == pytest.approx(1.0)
    assert len(dsp.silence(0.5)) == 16_000
