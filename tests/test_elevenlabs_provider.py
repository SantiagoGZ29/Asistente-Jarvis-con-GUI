"""Pruebas del proveedor de voz de ElevenLabs con clientes simulados."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.errors import (
    AudioError,
    ProviderAuthError,
    ProviderNotConfiguredError,
    ProviderPlanError,
    ProviderResponseError,
)
from jarvis.providers.elevenlabs_provider import (
    PCM_OUTPUT_FORMAT,
    ElevenLabsProvider,
)


class FakeTranscription:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeSpeechToText:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.kwargs: dict | None = None

    def convert(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return self.response


class FakeTextToSpeech:
    def __init__(self, chunks=(b"pcm-", b"data"), error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error
        self.kwargs: dict | None = None

    def convert(self, **kwargs):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return iter(self.chunks)


class FakeClient:
    def __init__(
        self,
        *,
        transcription=None,
        stt_error: Exception | None = None,
        tts_error: Exception | None = None,
    ) -> None:
        self.speech_to_text = FakeSpeechToText(transcription, stt_error)
        self.text_to_speech = FakeTextToSpeech(error=tts_error)


class FakeStatusError(Exception):
    def __init__(self, status_code: int, message: str = "error") -> None:
        self.status_code = status_code
        super().__init__(message)


def _provider(client: FakeClient, *, voice_id: str = "voz-123") -> ElevenLabsProvider:
    return ElevenLabsProvider(
        api_key="clave-simulada",
        voice_id=voice_id,
        client=client,
    )


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "grabacion.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 100)
    return path


def test_transcribe_envia_audio_con_modelo_e_idioma(
    audio_file: Path,
) -> None:
    client = FakeClient(transcription=FakeTranscription("Hola Jarvis, hazme un resumen"))
    provider = _provider(client)

    result = provider.transcribe(audio_file)

    assert result == "Hola Jarvis, hazme un resumen"
    kwargs = client.speech_to_text.kwargs
    assert kwargs["model_id"] == "scribe_v2"
    assert kwargs["language_code"] == "es"
    filename, handle, mime = kwargs["file"]
    assert filename == "grabacion.wav"
    assert mime == "audio/wav"
    assert handle.closed  # el archivo se cierra tras la petición


def test_transcripcion_vacia_genera_mensaje_claro(audio_file: Path) -> None:
    provider = _provider(FakeClient(transcription=FakeTranscription("")))
    with pytest.raises(ProviderResponseError) as error:
        provider.transcribe(audio_file)
    assert "audio" in error.value.user_message.lower()


def test_audio_inexistente(tmp_path: Path) -> None:
    provider = _provider(FakeClient(transcription=FakeTranscription("x")))
    with pytest.raises(AudioError):
        provider.transcribe(tmp_path / "no-existe.wav")


def test_audio_vacio(tmp_path: Path) -> None:
    path = tmp_path / "vacio.wav"
    path.write_bytes(b"")
    provider = _provider(FakeClient(transcription=FakeTranscription("x")))
    with pytest.raises(AudioError):
        provider.transcribe(path)


def test_error_de_credenciales_stt(audio_file: Path) -> None:
    provider = _provider(FakeClient(stt_error=FakeStatusError(401, "invalid api key")))
    with pytest.raises(ProviderAuthError):
        provider.transcribe(audio_file)


def test_sin_clave_no_se_puede_transcribir(audio_file: Path) -> None:
    provider = ElevenLabsProvider(api_key="", voice_id="voz", client=FakeClient())
    with pytest.raises(ProviderNotConfiguredError):
        provider.transcribe(audio_file)


def test_sintetiza_pcm_y_reproduce() -> None:
    client = FakeClient()
    played: list[bytes] = []
    provider = ElevenLabsProvider(
        api_key="clave-simulada",
        voice_id="voz-123",
        client=client,
        player=played.append,
    )

    provider.speak("Hola, soy Jarvis")

    assert played == [b"pcm-data"]
    kwargs = client.text_to_speech.kwargs
    assert kwargs["voice_id"] == "voz-123"
    assert kwargs["output_format"] == PCM_OUTPUT_FORMAT
    assert kwargs["model_id"] == "eleven_multilingual_v2"
    assert kwargs["text"] == "Hola, soy Jarvis"


def test_sin_voz_configurada_no_sintetiza() -> None:
    provider = ElevenLabsProvider(
        api_key="clave-simulada",
        voice_id="",
        client=FakeClient(),
    )
    with pytest.raises(ProviderNotConfiguredError) as error:
        provider.synthesize("hola")
    assert "ELEVENLABS_VOICE_ID" in error.value.user_message


def test_texto_vacio_no_se_envia() -> None:
    provider = _provider(FakeClient())
    with pytest.raises(ProviderResponseError):
        provider.synthesize("   ")


def test_error_de_sintesis_controlado() -> None:
    provider = _provider(FakeClient(tts_error=FakeStatusError(500, "server error")))
    with pytest.raises(Exception) as error:
        provider.synthesize("hola")
    assert "ElevenLabs" in str(error.value) or "error" in str(error.value).lower()


def test_voz_no_disponible_en_el_plan_gratuito() -> None:
    provider = _provider(
        FakeClient(
            tts_error=FakeStatusError(
                402, "paid_plan_required: free users cannot use library voices"
            )
        )
    )
    with pytest.raises(ProviderPlanError) as error:
        provider.synthesize("hola")

    message = error.value.user_message.lower()
    assert "plan" in message
    assert "premade" in message
    assert "pago" in message
