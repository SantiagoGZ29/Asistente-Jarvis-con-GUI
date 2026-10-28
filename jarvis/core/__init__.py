"""Paquete de utilidades internas de Jarvis."""

from jarvis.core.consent import (  # noqa: F401
    ELEVENLABS_STT,
    ELEVENLABS_TTS,
    GEMINI_CHAT,
    GEMINI_DOCUMENT,
    ConsentManager,
    ConsentRequest,
)
from jarvis.core.errors import (  # noqa: F401
    AudioError,
    AudioNotAvailableError,
    ConfigError,
    ConsentDeniedError,
    DocumentEmptyError,
    DocumentError,
    DocumentFormatError,
    DocumentNotFoundError,
    DocumentProtectedError,
    JarvisError,
    ProviderAuthError,
    ProviderError,
    ProviderModelError,
    ProviderNetworkError,
    ProviderNotConfiguredError,
    ProviderPlanError,
    ProviderRateLimitError,
    ProviderResponseError,
    classify_provider_error,
)
