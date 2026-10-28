"""Punto de entrada de Mi Jarvis."""

from __future__ import annotations

import argparse
import platform
import sys
from dataclasses import replace

from jarvis import __app_name__, __version__
from jarvis.config import Settings, load_settings
from jarvis.core.errors import JarvisError
from jarvis.core.logging_setup import get_logger, setup_logging
from jarvis.ui.console import ConsoleApp

logger = get_logger("main")

_DEPENDENCIES = (
    ("google-genai", "Google Gemini"),
    ("elevenlabs", "ElevenLabs"),
    ("python-docx", "Lectura de Word"),
    ("sounddevice", "Captura de audio"),
    ("python-dotenv", "Configuracion .env"),
    ("PySide6-Essentials", "Interfaz grafica"),
    ("pytest", "Pruebas automatizadas"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jarvis",
        description=(
            "Mi Jarvis: asistente documental por voz y texto. "
            "Lee un documento .docx y responde preguntas sobre su contenido."
        ),
    )
    parser.add_argument(
        "--document",
        metavar="RUTA",
        help="Abrir directamente un documento .docx al iniciar.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Usar la interfaz de consola en lugar de la ventana grafica.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Comprobar configuracion, dependencias y microfono sin iniciar la sesion.",
    )
    parser.add_argument(
        "--no-voice",
        action="store_true",
        help="Forzar el modo texto y desactivar la lectura en voz alta.",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Nivel de detalle del registro tecnico.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {__version__}",
    )
    return parser


def _dependency_status() -> list[tuple[str, str, bool]]:
    from importlib import metadata

    results: list[tuple[str, str, bool]] = []
    for package, purpose in _DEPENDENCIES:
        try:
            version = metadata.version(package)
            results.append((purpose, version, True))
        except metadata.PackageNotFoundError:
            results.append((purpose, "no instalada", False))
    return results


def _microphone_available(settings: Settings) -> bool:
    try:
        from jarvis.audio.recorder import AudioRecorder

        recorder = AudioRecorder(
            sample_rate=settings.sample_rate,
            max_seconds=settings.max_record_seconds,
        )
        return recorder.is_available()
    except Exception:
        return False


def _tkinter_available() -> bool:
    try:
        import tkinter  # noqa: F401

        return True
    except Exception:
        return False


def _qt_available() -> bool:
    try:
        import PySide6.QtWidgets  # noqa: F401

        return True
    except Exception:
        return False


def check_environment(settings: Settings) -> int:
    print("=" * 64)
    print(f"  {__app_name__} {__version__} - comprobacion del entorno")
    print("=" * 64)
    print(f"Python:   {platform.python_version()} ({platform.architecture()[0]})")
    print(f"Sistema:  {platform.system()} {platform.release()}")
    print(f"Carpeta:  {settings.env_file.parent if settings.env_file else '.'}")
    print("")

    print("Dependencias:")
    missing = []
    for purpose, version, installed in _dependency_status():
        mark = "OK " if installed else "FALTA"
        print(f"  [{mark}] {purpose}: {version}")
        if not installed:
            missing.append(purpose)
    print("")

    print("Configuracion (sin mostrar claves):")
    for key, value in settings.describe().items():
        print(f"  {key}: {value}")
    print("")

    issues = settings.validation_issues()
    if issues:
        print("Avisos de configuracion:")
        for issue in issues:
            print(f"  - {issue}")
    for warning in settings.warnings:
        print(f"  - {warning}")

    print("")
    print("Componentes del sistema:")
    qt = _qt_available()
    print(f"  [{'OK ' if qt else 'FALTA'}] Ventana PySide6")
    print(f"  [{'OK ' if _tkinter_available() else 'FALTA'}] Selector de archivos auxiliar (tkinter)")
    mic = _microphone_available(settings)
    print(f"  [{'OK ' if mic else 'NO DISPONIBLE'}] Microfono")
    if not mic and settings.elevenlabs_configured:
        print("     (Puedes seguir usando el modo texto.)")

    print("")
    if missing:
        print("Faltan dependencias. Ejecuta en PowerShell:")
        print("  python -m pip install -r requirements.txt")
        return 1

    if settings.validation_issues():
        print("Jarvis puede iniciarse, pero algunas funciones no estaran disponibles.")
        print("Copia .env.example a .env y completa las claves que necesites.")
    else:
        print("Configuracion completa. Puedes iniciar Jarvis con: python main.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows puede no usar UTF-8 por defecto.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()
    setup_logging(args.log_level or settings.log_level)

    if args.check:
        return check_environment(settings)

    if not settings.gemini_configured:
        logger.warning("GEMINI_API_KEY no configurada; solo funciones locales")
    if not settings.elevenlabs_configured:
        logger.warning("ELEVENLABS_API_KEY no configurada; modo texto")

    if args.console:
        if args.no_voice:
            settings = replace(settings, speak_responses=False)
        app = ConsoleApp(settings)
        if args.document:
            if not app.load_document_file(args.document):
                return 2
            app.run(select_on_start=False)
        else:
            app.run(select_on_start=True)
        return 0

    try:
        from jarvis.ui.gui import run_gui
    except ImportError as exc:
        print("No se pudo cargar la interfaz grafica (PySide6).")
        print("Instala las dependencias en PowerShell:")
        print("  python -m pip install -r requirements.txt")
        print(f"Detalle: {exc}")
        return 1

    return run_gui(
        settings,
        document=args.document,
        force_text=args.no_voice,
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except JarvisError as error:
        print(f"Error: {error.user_message}")
        raise SystemExit(1)
