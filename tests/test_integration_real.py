"""Pruebas de integración real (excluidas por defecto).

Solo se ejecutan si hay claves válidas en el entorno y se pide explícitamente:

    python -m pytest -m integration

Requieren conexión a Internet y pueden consumir cuota gratuita de los
proveedores. Nunca se ejecutan como parte de la suite normal.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Las pruebas de integración usan las mismas claves que la aplicación: se leen
# del archivo .env del proyecto (nunca se imprimen). Los valores ya definidos en
# el entorno del sistema tienen prioridad y no se sobrescriben.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE, override=False)

pytestmark = pytest.mark.integration


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def test_gemini_responde_de_verdad() -> None:
    api_key = _env("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY no configurada: no se prueba la integración real")

    from jarvis.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider(
        api_key=api_key,
        model=_env("GEMINI_MODEL") or "gemini-3.8-flash",
    )
    answer = provider.complete(
        prompt="Responde únicamente con la palabra OK.",
        system_instruction="Eres un asistente muy breve que responde en español.",
        temperature=0.0,
        max_output_tokens=200,
    )
    assert answer.strip()


def test_asistente_documental_con_gemini_real(tmp_path) -> None:
    api_key = _env("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY no configurada: no se prueba la integración real")

    from docx import Document

    from jarvis.assistants.document_assistant import NO_INFO_MARKER, DocumentAssistant
    from jarvis.config import load_settings
    from jarvis.documents.docx_loader import load_document
    from jarvis.providers.gemini_provider import GeminiProvider

    path = tmp_path / "integracion.docx"
    document = Document()
    document.add_heading("Politica de vacaciones", level=1)
    document.add_paragraph(
        "Cada empleado dispone de veinte dias laborables de vacaciones al ano."
    )
    document.add_paragraph("Las solicitudes deben enviarse con dos semanas de antelacion.")
    document.save(str(path))

    settings = load_settings(load_env=False)
    provider = GeminiProvider(api_key=api_key, model=settings.gemini_model)
    assistant = DocumentAssistant(
        provider,
        load_document(path),
        max_context_chars=2_000,
        chunk_size_chars=500,
    )

    answer = assistant.ask("¿Cuántos días de vacaciones hay al año?")
    assert answer.text
    assert NO_INFO_MARKER not in answer.text


def test_elevenlabs_sintetiza_de_verdad() -> None:
    if _env("JARVIS_RUN_VOICE_INTEGRATION") != "1":
        pytest.skip(
            "Prueba de voz real desactivada. Para ejecutarla define "
            "JARVIS_RUN_VOICE_INTEGRATION=1 (consume cuota de ElevenLabs)."
        )
    api_key = _env("ELEVENLABS_API_KEY")
    voice_id = _env("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        pytest.skip("Faltan ELEVENLABS_API_KEY o ELEVENLABS_VOICE_ID")

    from jarvis.config import load_settings
    from jarvis.providers.elevenlabs_provider import ElevenLabsProvider

    settings = load_settings(load_env=False)
    provider = ElevenLabsProvider(
        api_key=api_key,
        voice_id=voice_id,
        tts_model=settings.elevenlabs_tts_model,
    )
    audio = provider.synthesize("Prueba de voz de Mi Jarvis.")
    assert len(audio) > 0


def test_elevenlabs_transcribe_el_audio_sintetizado(tmp_path) -> None:
    """Ida y vuelta real: sintetiza una frase y la vuelve a transcribir."""
    if _env("JARVIS_RUN_VOICE_INTEGRATION") != "1":
        pytest.skip(
            "Prueba de voz real desactivada. Para ejecutarla define "
            "JARVIS_RUN_VOICE_INTEGRATION=1 (consume cuota de ElevenLabs)."
        )
    api_key = _env("ELEVENLABS_API_KEY")
    voice_id = _env("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        pytest.skip("Faltan ELEVENLABS_API_KEY o ELEVENLABS_VOICE_ID")

    import wave

    from jarvis.config import load_settings
    from jarvis.providers.elevenlabs_provider import (
        PCM_SAMPLE_RATE,
        ElevenLabsProvider,
    )

    settings = load_settings(load_env=False)
    provider = ElevenLabsProvider(
        api_key=api_key,
        voice_id=voice_id,
        stt_model=settings.elevenlabs_stt_model,
        tts_model=settings.elevenlabs_tts_model,
        language_code=settings.elevenlabs_language,
    )
    pcm = provider.synthesize("Jarvis, prepara el resumen del documento.")
    assert pcm

    path = tmp_path / "voz.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(PCM_SAMPLE_RATE)
        wav_file.writeframes(pcm)

    transcript = provider.transcribe(path)
    assert transcript.strip()
    assert "resumen" in transcript.lower()
