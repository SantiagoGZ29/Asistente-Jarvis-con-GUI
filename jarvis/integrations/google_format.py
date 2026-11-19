"""Formato en español de fechas y horas de Google.

Todas las funciones reciben ``datetime`` ya convertidos a la zona horaria
local configurada (``GOOGLE_TIMEZONE``). Nunca se presenta una hora UTC como
si fuera local.
"""

from __future__ import annotations

from datetime import datetime

WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
WEEKDAYS_LONG = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)
MONTHS = (
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


def format_date(value: datetime) -> str:
    return f"{WEEKDAYS[value.weekday()]} {value.day} {MONTHS[value.month - 1]}"


def format_date_year(value: datetime) -> str:
    return f"{format_date(value)} {value.year}"


def format_datetime(value: datetime) -> str:
    return f"{format_date_year(value)}, {value:%H:%M}"


def format_range(start: datetime, end: datetime, *, all_day: bool = False) -> str:
    if all_day:
        if start.date() == end.date():
            return f"{format_date_year(start)} · todo el día"
        return (
            f"{format_date_year(start)} a {format_date_year(end)} · todo el día"
        )
    if start.date() == end.date():
        return f"{format_date_year(start)}, {start:%H:%M}–{end:%H:%M}"
    return f"{format_datetime(start)} a {format_datetime(end)}"


__all__ = [
    "MONTHS",
    "WEEKDAYS",
    "WEEKDAYS_LONG",
    "format_date",
    "format_date_year",
    "format_datetime",
    "format_range",
]
