"""Pruebas de carga y validación de configuración."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.config import Settings, load_settings

ROOT = Path(__file__).resolve().parents[1]

_ENV_VARIABLES = (
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "ELEVENLABS_STT_MODEL_ID",
    "ELEVENLABS_REALTIME_MODEL_ID",
    "ELEVENLABS_TTS_MODEL_ID",
    "ELEVENLABS_LANGUAGE_CODE",
    "JARVIS_MAX_CONTEXT_CHARS",
    "JARVIS_MAX_CHUNK_BATCH_CHARS",
    "JARVIS_CHUNK_SIZE_CHARS",
    "JARVIS_MAX_RECORD_SECONDS",
    "JARVIS_SAMPLE_RATE",
    "JARVIS_SPEAK_RESPONSES",
    "JARVIS_LOG_LEVEL",
    "JARVIS_STT_MODE",
    "JARVIS_AUTO_LISTEN",
    "JARVIS_INPUT_DEVICE",
    "JARVIS_VAD_MARGIN_DB",
    "JARVIS_VAD_MIN_RMS",
    "JARVIS_SILENCE_MS",
    "JARVIS_PREROLL_MS",
    "JARVIS_MIN_SPEECH_MS",
    "JARVIS_GREETING",
    "JARVIS_DOWNLOADS_MAX_DEPTH",
    "JARVIS_DOWNLOADS_MAX_FILES",
    "JARVIS_SPREADSHEET_MAX_FILE_MB",
    "JARVIS_SPREADSHEET_MAX_ROWS",
    "JARVIS_SPREADSHEET_MAX_COLUMNS",
    "JARVIS_SPREADSHEET_MAX_CELLS",
    "JARVIS_SPREADSHEET_MAX_QUERY_ROWS",
    "JARVIS_SPREADSHEET_MAX_CONTEXT_CHARS",
    "JARVIS_SPREADSHEET_HEADER_SCAN_ROWS",
    "JARVIS_SPREADSHEET_TIMEOUT_S",
)


def _clear_environment(monkeypatch) -> None:
    for name in _ENV_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_valores_por_defecto(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    settings = load_settings(load_env=False)

    assert settings.gemini_model == "gemini-3.6-flash"
    assert settings.elevenlabs_stt_model == "scribe_v2"
    assert settings.elevenlabs_realtime_model == "scribe_v2_realtime"
    assert settings.elevenlabs_tts_model == "eleven_multilingual_v2"
    assert settings.elevenlabs_language == "es"
    assert settings.stt_mode == "realtime"
    assert settings.silence_ms == 850
    assert settings.preroll_ms == 300
    assert settings.min_speech_ms == 250
    assert settings.auto_listen is True
    assert settings.downloads_max_depth == 3
    assert settings.max_context_chars == 12_000
    assert settings.chunk_size_chars == 1_200
    assert settings.speak_responses is True
    assert settings.gemini_configured is False
    assert settings.elevenlabs_configured is False
    assert settings.elevenlabs_tts_configured is False


    assert settings.spreadsheet_max_file_mb == 25.0
    assert settings.spreadsheet_max_rows == 10_000
    assert settings.spreadsheet_max_columns == 60
    assert settings.spreadsheet_max_cells == 300_000
    assert settings.spreadsheet_max_query_rows == 10_000
    assert settings.spreadsheet_max_context_chars == 6_000
    assert settings.spreadsheet_header_scan_rows == 12
    assert settings.spreadsheet_timeout_s == 20.0


def test_configuracion_de_excel(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("JARVIS_SPREADSHEET_MAX_FILE_MB", "12.5")
    monkeypatch.setenv("JARVIS_SPREADSHEET_MAX_ROWS", "250")
    monkeypatch.setenv("JARVIS_SPREADSHEET_MAX_COLUMNS", "20")
    monkeypatch.setenv("JARVIS_SPREADSHEET_MAX_CELLS", "5000")
    monkeypatch.setenv("JARVIS_SPREADSHEET_MAX_QUERY_ROWS", "500")
    monkeypatch.setenv("JARVIS_SPREADSHEET_MAX_CONTEXT_CHARS", "2000")
    monkeypatch.setenv("JARVIS_SPREADSHEET_HEADER_SCAN_ROWS", "6")
    monkeypatch.setenv("JARVIS_SPREADSHEET_TIMEOUT_S", "9.5")

    settings = load_settings(load_env=False)

    assert settings.spreadsheet_max_file_mb == 12.5
    assert settings.spreadsheet_max_rows == 250
    assert settings.spreadsheet_max_columns == 20
    assert settings.spreadsheet_max_cells == 5_000
    assert settings.spreadsheet_max_query_rows == 500
    assert settings.spreadsheet_max_context_chars == 2_000
    assert settings.spreadsheet_header_scan_rows == 6
    assert settings.spreadsheet_timeout_s == 9.5


def test_variables_del_entorno(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "clave-gemini")
    monkeypatch.setenv("GEMINI_MODEL", "modelo-personalizado")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "clave-voz")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voz-1")
    monkeypatch.setenv("JARVIS_MAX_CONTEXT_CHARS", "8000")
    monkeypatch.setenv("JARVIS_SPEAK_RESPONSES", "false")

    settings = load_settings(load_env=False)

    assert settings.gemini_configured is True
    assert settings.gemini_model == "modelo-personalizado"
    assert settings.elevenlabs_tts_configured is True
    assert settings.max_context_chars == 8_000
    assert settings.speak_responses is False
    assert settings.validation_issues() == []


def test_valor_numerico_invalido_genera_aviso(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("JARVIS_MAX_CONTEXT_CHARS", "mucho")
    settings = load_settings(load_env=False)

    assert settings.max_context_chars == 12_000
    assert any("JARVIS_MAX_CONTEXT_CHARS" in warning for warning in settings.warnings)


def test_valor_booleano_invalido_genera_aviso(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("JARVIS_SPEAK_RESPONSES", "quizas")
    settings = load_settings(load_env=False)

    assert settings.speak_responses is True
    assert any("JARVIS_SPEAK_RESPONSES" in warning for warning in settings.warnings)


def test_modo_de_transcripcion_invalido_genera_aviso(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("JARVIS_STT_MODE", "telepatia")

    settings = load_settings(load_env=False)

    assert settings.stt_mode == "realtime"
    assert any("JARVIS_STT_MODE" in warning for warning in settings.warnings)


def test_modo_batch_y_umbrales_desde_el_entorno(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("JARVIS_STT_MODE", "batch")
    monkeypatch.setenv("JARVIS_SILENCE_MS", "1200")
    monkeypatch.setenv("JARVIS_PREROLL_MS", "0")
    monkeypatch.setenv("JARVIS_VAD_MARGIN_DB", "12,5")

    settings = load_settings(load_env=False)

    assert settings.stt_mode == "batch"
    assert settings.silence_ms == 1_200
    assert settings.preroll_ms == 0
    assert settings.vad_margin_db == pytest.approx(12.5)
    assert settings.realtime_stt_enabled is False


def test_frecuencias_de_vad_fuera_de_rango_se_corrigen(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    monkeypatch.setenv("JARVIS_SILENCE_MS", "50")
    monkeypatch.setenv("JARVIS_PREROLL_MS", "99999")

    settings = load_settings(load_env=False)

    assert settings.silence_ms == 300
    assert settings.preroll_ms == 1_500
    assert len(settings.warnings) == 2


def test_avisos_por_claves_ausentes(monkeypatch) -> None:
    _clear_environment(monkeypatch)
    settings = load_settings(load_env=False)
    issues = " ".join(settings.validation_issues())

    assert "GEMINI_API_KEY" in issues
    assert "ELEVENLABS_API_KEY" in issues
    # Sin clave de voz no se debe afirmar que el texto está bloqueado.
    assert "modo texto" in issues


def test_los_avisos_no_revelan_claves() -> None:
    settings = Settings(
        gemini_api_key="secreto-super-privado",
        elevenlabs_api_key="otro-secreto",
        elevenlabs_voice_id="voz",
    )
    description = " ".join(settings.describe().values())

    assert "secreto" not in description
    assert "configurada" in description


def test_env_example_documenta_las_variables() -> None:
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()

    for name in _ENV_VARIABLES:
        assert name in values, f"Falta {name} en .env.example"

    assert values["GEMINI_API_KEY"] == ""
    assert values["ELEVENLABS_API_KEY"] == ""
    assert values["ELEVENLABS_VOICE_ID"] == ""


def test_gitignore_protege_el_env() -> None:
    content = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content
    assert ".venv/" in content
    assert "__pycache__/" in content


def test_env_local_documenta_las_variables() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return  # el usuario puede no haber creado el archivo todavía
    content = env_path.read_text(encoding="utf-8")
    for name in ("GEMINI_API_KEY", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        assert any(
            line.strip().startswith(f"{name}=") for line in content.splitlines()
        ), f"Falta {name} en .env"
