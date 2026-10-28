"""Integración con ElevenLabs: transcripción (STT) y voz (TTS)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from jarvis.core.errors import (
    AudioError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    classify_provider_error,
)
from jarvis.core.logging_setup import get_logger

logger = get_logger("elevenlabs")

PROVIDER_NAME = "ElevenLabs"
PCM_OUTPUT_FORMAT = "pcm_16000"
PCM_SAMPLE_RATE = 16_000

_MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}


class ElevenLabsProvider:
    """Cliente de voz de ElevenLabs con SDK oficial."""

    def __init__(
        self,
        api_key: str,
        *,
        voice_id: str = "",
        stt_model: str = "scribe_v2",
        tts_model: str = "eleven_multilingual_v2",
        language_code: str = "es",
        client: Any | None = None,
        player: Callable[[bytes], None] | None = None,
    ) -> None:
        self._api_key = api_key
        self._voice_id = voice_id
        self._stt_model = stt_model
        self._tts_model = tts_model
        self._language_code = language_code
        self._client = client
        self._player = player

    # ------------------------------------------------------------------
    # Propiedades
    # ------------------------------------------------------------------
    @property
    def stt_model(self) -> str:
        return self._stt_model

    @property
    def tts_model(self) -> str:
        return self._tts_model

    @property
    def voice_configured(self) -> bool:
        return bool(self._voice_id)

    # ------------------------------------------------------------------
    # Cliente
    # ------------------------------------------------------------------
    def _ensure_client(self) -> Any:
        if not self._api_key:
            raise ProviderNotConfiguredError(
                "No hay clave de ElevenLabs configurada (ELEVENLABS_API_KEY). "
                "El modo texto sigue disponible."
            )
        if self._client is None:
            try:
                from elevenlabs.client import ElevenLabs
            except ImportError as exc:  # pragma: no cover - dependencia opcional
                raise ProviderNotConfiguredError(
                    "La biblioteca 'elevenlabs' no está instalada. "
                    "Ejecuta: pip install -r requirements.txt"
                ) from exc
            self._client = ElevenLabs(api_key=self._api_key)
        return self._client

    # ------------------------------------------------------------------
    # Speech to text
    # ------------------------------------------------------------------
    def transcribe(self, audio_path: str | Path) -> str:
        """Transcribe un archivo de audio grabado explícitamente."""
        path = Path(audio_path)
        if not path.is_file():
            raise AudioError("No se encontró el archivo de audio de la grabación.")
        if path.stat().st_size == 0:
            raise AudioError(
                "La grabación está vacía. Comprueba el micrófono e inténtalo de nuevo."
            )

        client = self._ensure_client()
        mime = _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
        try:
            with path.open("rb") as handle:
                response = client.speech_to_text.convert(
                    model_id=self._stt_model,
                    file=(path.name, handle, mime),
                    language_code=self._language_code or None,
                    tag_audio_events=False,
                    diarize=False,
                )
        except Exception as exc:
            logger.warning(
                "Error de transcripción con ElevenLabs: %s", type(exc).__name__
            )
            raise classify_provider_error(exc, PROVIDER_NAME) from exc

        text = self._extract_transcript(response)
        logger.info("Transcripción completada (%d caracteres)", len(text))
        return text

    @staticmethod
    def _extract_transcript(response: Any) -> str:
        text = getattr(response, "text", "") or ""
        if not text.strip():
            transcripts = getattr(response, "transcripts", None) or []
            pieces = [
                getattr(item, "text", "") or ""
                for item in transcripts
            ]
            text = " ".join(piece for piece in pieces if piece)
        text = " ".join(text.split())
        if not text:
            raise ProviderResponseError(
                "No se pudo entender el audio. Habla un poco más cerca del "
                "micrófono e inténtalo de nuevo, o escribe tu orden por teclado."
            )
        return text

    # ------------------------------------------------------------------
    # Text to speech
    # ------------------------------------------------------------------
    def synthesize(self, text: str) -> bytes:
        """Convierte texto en audio PCM de 16 kHz listo para reproducir."""
        if not text or not text.strip():
            raise ProviderResponseError("No hay texto para leer en voz alta.")
        if not self._voice_id:
            raise ProviderNotConfiguredError(
                "No hay voz de ElevenLabs configurada (ELEVENLABS_VOICE_ID). "
                "Puedes copiar el identificador de tu voz desde el panel de ElevenLabs."
            )

        client = self._ensure_client()
        try:
            audio = client.text_to_speech.convert(
                voice_id=self._voice_id,
                text=text,
                model_id=self._tts_model,
                output_format=PCM_OUTPUT_FORMAT,
            )
            data = b"".join(chunk for chunk in audio if chunk)
        except Exception as exc:
            logger.warning("Error de síntesis de voz: %s", type(exc).__name__)
            raise classify_provider_error(exc, PROVIDER_NAME) from exc

        if not data:
            raise ProviderResponseError(
                "ElevenLabs no devolvió audio. Inténtalo de nuevo."
            )
        logger.info("Audio generado (%d bytes)", len(data))
        return data

    def stream(self, text: str):
        """Genera audio PCM en fragmentos, según llegan del servicio.

        Se usa ``text_to_speech.stream`` del SDK oficial; los errores que
        ocurren durante la iteración también se traducen a errores de Jarvis.
        """
        if not text or not text.strip():
            raise ProviderResponseError("No hay texto para leer en voz alta.")
        if not self._voice_id:
            raise ProviderNotConfiguredError(
                "No hay voz de ElevenLabs configurada (ELEVENLABS_VOICE_ID). "
                "Puedes copiar el identificador de tu voz desde el panel de ElevenLabs."
            )

        client = self._ensure_client()
        try:
            audio = client.text_to_speech.stream(
                voice_id=self._voice_id,
                text=text,
                model_id=self._tts_model,
                output_format=PCM_OUTPUT_FORMAT,
            )
        except Exception as exc:
            logger.warning("Error al iniciar la voz: %s", type(exc).__name__)
            raise classify_provider_error(exc, PROVIDER_NAME) from exc

        def generate():
            try:
                for chunk in audio:
                    if chunk:
                        yield chunk
            except Exception as exc:
                logger.warning("Error durante la voz: %s", type(exc).__name__)
                raise classify_provider_error(exc, PROVIDER_NAME) from exc

        return generate()

    def play(self, pcm_data: bytes) -> None:
        """Reproduce audio PCM mono de 16 bits y 16 kHz."""
        if self._player is not None:
            self._player(pcm_data)
            return
        try:
            import sounddevice as sd

            with sd.RawOutputStream(
                samplerate=PCM_SAMPLE_RATE,
                channels=1,
                dtype="int16",
            ) as stream:
                stream.write(pcm_data)
        except Exception as exc:
            logger.warning("Error al reproducir audio: %s", type(exc).__name__)
            raise AudioError(
                "El audio se generó, pero no se pudo reproducir. "
                "Comprueba que haya un dispositivo de salida disponible."
            ) from exc

    def speak(self, text: str) -> None:
        """Sintetiza y reproduce el texto indicado."""
        self.play(self.synthesize(text))
