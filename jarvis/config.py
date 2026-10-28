"""Carga y validación de la configuración de Mi Jarvis."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_STT_MODEL = "scribe_v2"
DEFAULT_REALTIME_MODEL = "scribe_v2_realtime"
DEFAULT_TTS_MODEL = "eleven_multilingual_v2"
DEFAULT_LANGUAGE = "es"
DEFAULT_STT_MODE = "realtime"

DEFAULT_GREETING = (
    "Hola. Soy Jarvis y estoy listo para ayudarte. Puedes pedirme que abra "
    "un documento, que lo resuma o que te explique su contenido."
)

MIN_CONTEXT_CHARS = 1000
MIN_BATCH_CHARS = 1000
MIN_CHUNK_CHARS = 200


def _as_str(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _as_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int = 10_000_000,
    warnings: list[str],
) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(float(raw.strip()))
    except ValueError:
        warnings.append(
            f"El valor de {name} no es un número válido ('{raw}'). Se usará {default}."
        )
        return default
    if value < minimum or value > maximum:
        warnings.append(
            f"El valor de {name} está fuera de rango ({value}). "
            f"Se usará {max(minimum, min(value, maximum))}."
        )
        return max(minimum, min(value, maximum))
    return value


def _as_float(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
    warnings: list[str],
) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip().replace(",", "."))
    except ValueError:
        warnings.append(
            f"El valor de {name} no es un número válido ('{raw}'). Se usará {default}."
        )
        return default
    if value < minimum or value > maximum:
        warnings.append(
            f"El valor de {name} está fuera de rango ({value}). "
            f"Se usará {max(minimum, min(value, maximum))}."
        )
        return max(minimum, min(value, maximum))
    return value


def _as_bool(name: str, default: bool, *, warnings: list[str]) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "si", "sí", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    warnings.append(
        f"El valor de {name} no es un booleano válido ('{raw}'). Se usará {default}."
    )
    return default


def _as_choice(
    name: str, default: str, choices: tuple[str, ...], *, warnings: list[str]
) -> str:
    raw = _as_str(name, default).lower()
    if raw not in choices:
        warnings.append(
            f"El valor de {name} no es válido ('{raw}'). "
            f"Se usará {default}. Opciones: {', '.join(choices)}."
        )
        return default
    return raw


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de una sesión de Jarvis."""

    gemini_api_key: str = ""
    gemini_model: str = DEFAULT_GEMINI_MODEL

    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_stt_model: str = DEFAULT_STT_MODEL
    elevenlabs_realtime_model: str = DEFAULT_REALTIME_MODEL
    elevenlabs_tts_model: str = DEFAULT_TTS_MODEL
    elevenlabs_language: str = DEFAULT_LANGUAGE

    max_context_chars: int = 12_000
    max_batch_chars: int = 9_000
    chunk_size_chars: int = 1_200
    max_record_seconds: float = 60.0
    sample_rate: int = 16_000
    speak_responses: bool = True
    log_level: str = "INFO"

    # Conversación por voz
    stt_mode: str = DEFAULT_STT_MODE
    auto_listen: bool = True
    input_device_key: str = ""
    vad_margin_db: float = 9.0
    vad_min_rms: float = 120.0
    silence_ms: int = 850
    preroll_ms: int = 300
    min_speech_ms: int = 250
    greeting_text: str = DEFAULT_GREETING

    # Búsqueda de documentos en Descargas
    downloads_max_depth: int = 3
    downloads_max_files: int = 2_000

    env_file: Path | None = field(default=DEFAULT_ENV_FILE)
    warnings: tuple[str, ...] = field(default=())

    # ------------------------------------------------------------------
    # Consultas de disponibilidad
    # ------------------------------------------------------------------
    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def elevenlabs_configured(self) -> bool:
        """Hay clave de ElevenLabs (suficiente para transcribir)."""
        return bool(self.elevenlabs_api_key)

    @property
    def elevenlabs_tts_configured(self) -> bool:
        """Hay clave y voz configuradas para leer respuestas en voz alta."""
        return bool(self.elevenlabs_api_key and self.elevenlabs_voice_id)

    @property
    def voice_ready(self) -> bool:
        return self.elevenlabs_configured

    @property
    def realtime_stt_enabled(self) -> bool:
        """El modo realtime solo tiene sentido con clave de ElevenLabs."""
        return self.stt_mode == "realtime" and self.elevenlabs_configured

    def describe(self) -> dict[str, str]:
        """Resumen apto para mostrar en pantalla (nunca incluye claves)."""
        return {
            "Modelo de Gemini": self.gemini_model,
            "Clave de Gemini": "configurada" if self.gemini_configured else "no configurada",
            "Clave de ElevenLabs": (
                "configurada" if self.elevenlabs_configured else "no configurada"
            ),
            "Voz de ElevenLabs": (
                "configurada" if self.elevenlabs_voice_id else "no configurada"
            ),
            "Modelo de transcripción": self.elevenlabs_stt_model,
            "Modelo de transcripción en tiempo real": self.elevenlabs_realtime_model,
            "Modo de transcripción": self.stt_mode,
            "Modelo de voz": self.elevenlabs_tts_model,
            "Idioma de voz": self.elevenlabs_language,
            "Modo de respuesta hablada": "sí" if self.speak_responses else "no",
            "Escucha automática": "sí" if self.auto_listen else "no",
            "Micrófono guardado": self.input_device_key or "predeterminado",
            "Fin de turno por silencio": f"{self.silence_ms} ms",
        }

    def validation_issues(self) -> list[str]:
        """Problemas que impiden o limitan el uso normal de la aplicación."""
        issues: list[str] = []
        if not self.gemini_configured:
            issues.append(
                "Falta GEMINI_API_KEY: Jarvis podrá leer el documento, pero no "
                "responder preguntas ni generar resúmenes."
            )
        if not self.elevenlabs_configured:
            issues.append(
                "Falta ELEVENLABS_API_KEY: el micrófono y la voz quedarán "
                "desactivados (el modo texto seguirá funcionando)."
            )
        elif not self.elevenlabs_voice_id:
            issues.append(
                "Falta ELEVENLABS_VOICE_ID: se podrá transcribir voz, pero no "
                "escuchar las respuestas."
            )
        if self.min_speech_ms >= self.silence_ms + 1_000:
            issues.append(
                "JARVIS_MIN_SPEECH_MS es demasiado alto respecto a "
                "JARVIS_SILENCE_MS: las frases cortas podrían descartarse."
            )
        return issues


def load_settings(
    env_file: Path | str | None = DEFAULT_ENV_FILE,
    *,
    load_env: bool = True,
) -> Settings:
    """Carga la configuración desde el archivo .env y el entorno.

    Los valores del entorno ya definidos tienen prioridad sobre el archivo.
    Nunca falla por una variable ausente: aplica valores por defecto y
    devuelve los avisos en ``Settings.warnings``.
    """
    warnings: list[str] = []
    env_path = Path(env_file) if env_file else None

    if load_env and env_path is not None and env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)

    log_level = _as_str("JARVIS_LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        warnings.append(
            f"JARVIS_LOG_LEVEL no reconocido ('{log_level}'). Se usará INFO."
        )
        log_level = "INFO"

    settings = Settings(
        gemini_api_key=_as_str("GEMINI_API_KEY"),
        gemini_model=_as_str("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        elevenlabs_api_key=_as_str("ELEVENLABS_API_KEY"),
        elevenlabs_voice_id=_as_str("ELEVENLABS_VOICE_ID"),
        elevenlabs_stt_model=_as_str("ELEVENLABS_STT_MODEL_ID", DEFAULT_STT_MODEL),
        elevenlabs_realtime_model=_as_str(
            "ELEVENLABS_REALTIME_MODEL_ID", DEFAULT_REALTIME_MODEL
        ),
        elevenlabs_tts_model=_as_str("ELEVENLABS_TTS_MODEL_ID", DEFAULT_TTS_MODEL),
        elevenlabs_language=_as_str("ELEVENLABS_LANGUAGE_CODE", DEFAULT_LANGUAGE),
        max_context_chars=_as_int(
            "JARVIS_MAX_CONTEXT_CHARS",
            12_000,
            minimum=MIN_CONTEXT_CHARS,
            warnings=warnings,
        ),
        max_batch_chars=_as_int(
            "JARVIS_MAX_CHUNK_BATCH_CHARS",
            9_000,
            minimum=MIN_BATCH_CHARS,
            warnings=warnings,
        ),
        chunk_size_chars=_as_int(
            "JARVIS_CHUNK_SIZE_CHARS",
            1_200,
            minimum=MIN_CHUNK_CHARS,
            maximum=20_000,
            warnings=warnings,
        ),
        max_record_seconds=_as_float(
            "JARVIS_MAX_RECORD_SECONDS",
            60.0,
            minimum=2.0,
            maximum=600.0,
            warnings=warnings,
        ),
        sample_rate=_as_int(
            "JARVIS_SAMPLE_RATE",
            16_000,
            minimum=8_000,
            maximum=48_000,
            warnings=warnings,
        ),
        speak_responses=_as_bool("JARVIS_SPEAK_RESPONSES", True, warnings=warnings),
        stt_mode=_as_choice(
            "JARVIS_STT_MODE", DEFAULT_STT_MODE, ("realtime", "batch"), warnings=warnings
        ),
        auto_listen=_as_bool("JARVIS_AUTO_LISTEN", True, warnings=warnings),
        input_device_key=_as_str("JARVIS_INPUT_DEVICE"),
        vad_margin_db=_as_float(
            "JARVIS_VAD_MARGIN_DB",
            9.0,
            minimum=2.0,
            maximum=30.0,
            warnings=warnings,
        ),
        vad_min_rms=_as_float(
            "JARVIS_VAD_MIN_RMS",
            120.0,
            minimum=10.0,
            maximum=5_000.0,
            warnings=warnings,
        ),
        silence_ms=_as_int(
            "JARVIS_SILENCE_MS",
            850,
            minimum=300,
            maximum=3_000,
            warnings=warnings,
        ),
        preroll_ms=_as_int(
            "JARVIS_PREROLL_MS",
            300,
            minimum=0,
            maximum=1_500,
            warnings=warnings,
        ),
        min_speech_ms=_as_int(
            "JARVIS_MIN_SPEECH_MS",
            250,
            minimum=100,
            maximum=2_000,
            warnings=warnings,
        ),
        greeting_text=_as_str("JARVIS_GREETING", DEFAULT_GREETING),
        downloads_max_depth=_as_int(
            "JARVIS_DOWNLOADS_MAX_DEPTH",
            3,
            minimum=0,
            maximum=6,
            warnings=warnings,
        ),
        downloads_max_files=_as_int(
            "JARVIS_DOWNLOADS_MAX_FILES",
            2_000,
            minimum=50,
            maximum=20_000,
            warnings=warnings,
        ),
        log_level=log_level,
        env_file=env_path,
        warnings=tuple(warnings),
    )
    return settings
