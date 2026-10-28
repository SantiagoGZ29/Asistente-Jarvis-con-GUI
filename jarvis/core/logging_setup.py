"""Registro técnico seguro.

Regla de oro: nunca se escriben en el registro el contenido de los
documentos, las transcripciones ni las claves de API. Solo se registran
eventos técnicos (nombres de archivo, longitudes, códigos de error).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "jarvis"
_configured = False


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> logging.Logger:
    """Configura el registro de Jarvis una sola vez."""
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    logger.addHandler(console)

    directory = log_dir or (Path(__file__).resolve().parent.parent.parent / "logs")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            directory / "jarvis.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Si no se puede escribir el archivo, el registro en consola basta.
        logger.warning("No se pudo crear el archivo de registro en %s", directory)

    _configured = True
    return logger


def get_logger(component: str | None = None) -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME if not component else f"{_LOGGER_NAME}.{component}")
