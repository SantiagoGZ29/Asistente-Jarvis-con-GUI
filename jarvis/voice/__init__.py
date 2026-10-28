"""Voz de Mi Jarvis: reconocimiento (STT) y salida hablada (TTS)."""

from jarvis.voice.speech import (  # noqa: F401
    SpeechCallbacks,
    SpeechOutput,
)
from jarvis.voice.stt import (  # noqa: F401
    BatchTranscriber,
    HybridTranscriber,
    RealtimeTranscriber,
    SttCallbacks,
)
