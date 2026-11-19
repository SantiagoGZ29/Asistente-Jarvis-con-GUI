"""Integraciones externas de solo lectura.

La integración de correo y agenda usa Gmail y Google Calendar mediante las
bibliotecas oficiales de Google. El paquete no importa Qt: los servicios se
pueden probar con respuestas simuladas y el controlador decide cuándo ejecutar
cada consulta.
"""

from __future__ import annotations

GMAIL_URL = "https://mail.google.com/"
GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/"

DEFAULT_GOOGLE_TIMEZONE = "America/Santiago"
DEFAULT_GOOGLE_OAUTH_CLIENT_FILE = "credentials.json"

# Permisos mínimos de solo lectura. Nunca se solicita escritura.
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"
GOOGLE_SCOPES = (GMAIL_SCOPE, CALENDAR_SCOPE)

__all__ = [
    "CALENDAR_SCOPE",
    "DEFAULT_GOOGLE_OAUTH_CLIENT_FILE",
    "DEFAULT_GOOGLE_TIMEZONE",
    "GMAIL_SCOPE",
    "GMAIL_URL",
    "GOOGLE_CALENDAR_URL",
    "GOOGLE_SCOPES",
]
