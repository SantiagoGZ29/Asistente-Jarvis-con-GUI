"""Pruebas de la detección de voz local."""

from __future__ import annotations

import pytest

from jarvis.audio.vad import (
    VadEventType,
    VoiceActivityDetector,
    threshold_rms,
)

RATE = 16_000
FRAME = 320


def pcm(amplitude: int, samples: int = FRAME) -> bytes:
    value = int(amplitude).to_bytes(2, "little", signed=True)
    return value * samples


def frames(amplitude: int, count: int) -> bytes:
    return pcm(amplitude, FRAME * count)


def feed_all(detector: VoiceActivityDetector, data: bytes, block: int = FRAME * 2):
    events = []
    for start in range(0, len(data), block):
        events.extend(detector.feed(data[start : start + block]).events)
    return events


def test_silencio_no_abre_turno() -> None:
    detector = VoiceActivityDetector()

    events = feed_all(detector, frames(5, 50))

    assert events == []
    assert detector.speaking is False
    assert detector.level < 0.1


def test_voz_sostenida_abre_y_cierra_turno() -> None:
    detector = VoiceActivityDetector()

    events = feed_all(detector, frames(2500, 40) + frames(5, 50))

    kinds = [event.kind for event in events]
    assert kinds[0] is VadEventType.SPEECH_START
    assert kinds[-1] is VadEventType.SPEECH_END
    end = events[-1]
    assert end.segment
    assert end.voiced_s >= 0.3
    assert detector.speaking is False


def test_frase_demasiado_corta_se_descarta() -> None:
    detector = VoiceActivityDetector(min_speech_ms=400)

    events = feed_all(detector, frames(2500, 6) + frames(5, 50))

    kinds = [event.kind for event in events]
    assert VadEventType.SPEECH_START in kinds
    assert VadEventType.SPEECH_END not in kinds
    assert kinds[-1] is VadEventType.DISCARDED


def test_el_buffer_previo_conserva_el_arranque() -> None:
    detector = VoiceActivityDetector(preroll_ms=300, silence_ms=400)

    events = feed_all(detector, frames(5, 40) + frames(2500, 20) + frames(5, 30))

    end = [event for event in events if event.kind is VadEventType.SPEECH_END][-1]
    assert end.duration_s >= end.voiced_s + 0.2
    assert end.duration_s - end.voiced_s < 0.55


def test_el_ruido_de_fondo_se_adapta() -> None:
    detector = VoiceActivityDetector(min_rms=120, margin_db=9)
    inicial = detector.noise_floor

    feed_all(detector, frames(40, 100))

    assert detector.noise_floor > inicial
    assert detector.threshold >= 120
    assert detector.speaking is False


def test_un_ruido_puntual_no_abre_turno() -> None:
    detector = VoiceActivityDetector()

    events = feed_all(detector, frames(5, 10) + frames(3000, 1) + frames(5, 10))

    assert events == []


def test_flush_cierra_la_frase_y_limpia_el_estado() -> None:
    detector = VoiceActivityDetector()
    feed_all(detector, frames(2500, 20))
    assert detector.speaking is True

    event = detector.flush()

    assert event is not None
    assert event.kind is VadEventType.SPEECH_END
    assert detector.speaking is False
    assert detector.flush() is None


def test_duracion_maxima_cierra_la_frase() -> None:
    detector = VoiceActivityDetector(max_utterance_s=0.5)

    events = feed_all(detector, frames(2500, 40))

    assert any(event.kind is VadEventType.SPEECH_END for event in events)
    assert detector.speaking is False


def test_bloques_de_tamano_irregular_no_pierden_audio() -> None:
    detector = VoiceActivityDetector(silence_ms=400)
    data = frames(2500, 20) + frames(5, 30)

    events = []
    for start in range(0, len(data), 333):
        events.extend(detector.feed(data[start : start + 333]).events)

    end = [event for event in events if event.kind is VadEventType.SPEECH_END][-1]
    assert end.segment


def test_nivel_refleja_la_amplitud() -> None:
    detector = VoiceActivityDetector()

    bajo = detector.feed(frames(20, 2)).level
    alto = detector.feed(frames(8000, 2)).level

    assert 0.0 <= bajo < alto <= 1.0


def test_umbral_efectivo() -> None:
    assert threshold_rms(10, 9, 120) == 120
    assert threshold_rms(1000, 6, 120) == pytest.approx(1995.26, rel=0.01)


def test_parametros_invalidos() -> None:
    with pytest.raises(ValueError):
        VoiceActivityDetector(sample_rate=0)
    with pytest.raises(ValueError):
        VoiceActivityDetector(frame_ms=0)
