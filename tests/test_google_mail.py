"""Pruebas de Gmail: solo lectura, multipart, Base64 URL-safe y contexto."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

import pytest

from google_helpers import FakeGmailClient, FakeProvider, allowed_consent, gmail_message

from jarvis.core.errors import GoogleApiError
from jarvis.integrations.google_mail import (
    GMAIL_METADATA_FIELDS,
    GmailAssistant,
    GmailService,
    MailDetail,
    MailMessage,
    extract_body,
    html_to_text,
)


def ms(year: int, month: int, day: int, hour: int, minute: int = 0) -> int:
    return int(
        datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def b64(value: str, *, pad: bool = False) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return encoded if pad else encoded.rstrip("=")


def raw_message(
    message_id: str = "gmail-1",
    *,
    subject: str = "Informe mensual",
    name: str = "Ana Pérez",
    address: str = "ana@example.com",
    internal: int | None = None,
    labels: tuple[str, ...] = ("INBOX",),
    snippet: str = "Vista previa",
    parts: list[dict[str, Any]] | None = None,
    headers: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, Any]:
    return gmail_message(
        message_id,
        subject=subject,
        name=name,
        address=address,
        internal_date=internal or ms(2026, 11, 17, 12),
        labels=labels,
        snippet=snippet,
        parts=parts,
        headers=headers,
    )


def service(client: FakeGmailClient) -> GmailService:
    return GmailService(client, limit=20)


# ----------------------------------------------------------------------
# Lista y metadatos
# ----------------------------------------------------------------------
def test_lista_pide_metadatos_y_solo_la_bandeja() -> None:
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "gmail-1"}]}],
        metadata={"gmail-1": raw_message("gmail-1")},
    )

    messages = service(client).list_recent()

    assert len(messages) == 1
    assert messages[0].subject == "Informe mensual"
    assert client.list_calls[0]["max_results"] == 20
    assert client.list_calls[0]["page_token"] is None
    call = client.metadata_calls[0]
    assert call["format"] == "metadata"
    assert call["metadata_headers"] == ("From", "Subject", "Date")
    assert call["fields"] == GMAIL_METADATA_FIELDS
    assert client.full_calls == []


def test_paginacion_hasta_completar_el_limite() -> None:
    client = FakeGmailClient(
        list_payloads=[
            {"messages": [{"id": "a"}], "nextPageToken": "pagina-2"},
            {"messages": [{"id": "b"}], "nextPageToken": "pagina-3"},
            {"messages": [{"id": "c"}]},
        ],
        metadata={
            "a": raw_message("a", internal=ms(2026, 11, 17, 10)),
            "b": raw_message("b", internal=ms(2026, 11, 17, 11)),
            "c": raw_message("c", internal=ms(2026, 11, 17, 12)),
        },
    )

    messages = service(client).list_recent(3)

    assert [item.id for item in messages] == ["c", "b", "a"]
    assert [call["page_token"] for call in client.list_calls] == [
        None,
        "pagina-2",
        "pagina-3",
    ]


def test_limite_nunca_supera_veinte() -> None:
    client = FakeGmailClient()
    assert service(client).limit == 20
    big = GmailService(client, limit=500)
    assert big.limit == 20


def test_bandeja_vacia() -> None:
    messages = service(FakeGmailClient()).list_recent()
    assert messages == ()


def test_formato_inesperado_en_la_lista() -> None:
    client = FakeGmailClient(list_payloads=[{"messages": ["no-es-un-mapa"]}])
    assert service(client).list_recent() == ()

    client = FakeGmailClient(list_payloads=[{"messages": "texto"}])
    with pytest.raises(GoogleApiError):
        service(client).list_recent()


def test_no_leidos_importancia_adjuntos_y_orden() -> None:
    attachment_parts = [
        {
            "mimeType": "text/plain",
            "filename": "",
            "body": {"data": b64("Hola")},
        },
        {
            "mimeType": "application/pdf",
            "filename": "informe.pdf",
            "body": {"attachmentId": "adj-1", "size": 1234},
        },
    ]
    client = FakeGmailClient(
        list_payloads=[
            {"messages": [{"id": "leido"}, {"id": "nuevo"}]},
        ],
        metadata={
            "leido": raw_message(
                "leido",
                subject="Leído",
                labels=("INBOX",),
                internal=ms(2026, 11, 16, 9),
            ),
            "nuevo": raw_message(
                "nuevo",
                subject="Sin leer",
                labels=("INBOX", "UNREAD", "IMPORTANT"),
                internal=ms(2026, 11, 17, 9),
                parts=attachment_parts,
            ),
        },
    )

    messages = service(client).list_recent()

    assert [item.id for item in messages] == ["nuevo", "leido"]
    unread = messages[0]
    assert unread.is_read is False
    assert unread.importance == "high"
    assert unread.importance_label == "alta"
    assert unread.has_attachments is True
    assert messages[1].is_read is True
    assert messages[1].has_attachments is False


def test_describe_indica_estado_y_adjuntos() -> None:
    item = MailMessage(
        id="1",
        subject="Hola",
        sender_name="Ana",
        sender_address="ana@example.com",
        received=datetime(2026, 11, 17, 9, tzinfo=timezone.utc),
        is_read=False,
        importance="normal",
        has_attachments=True,
    )
    text = item.describe(index=2)
    assert text.startswith("2. Ana — «Hola»")
    assert "sin leer" in text
    assert "con adjuntos" in text


# ----------------------------------------------------------------------
# Detalle, multipart y Base64 URL-safe
# ----------------------------------------------------------------------
def test_detalle_prioriza_texto_plano_sin_padding() -> None:
    full = raw_message(
        "gmail-1",
        parts=[
            {
                "mimeType": "text/plain",
                "body": {"data": b64("Hola equipo:\n\nInforme adjunto.")},
            },
            {
                "mimeType": "text/html",
                "body": {"data": b64("<p>Versión HTML</p>")},
            },
        ],
    )
    client = FakeGmailClient(full={"gmail-1": full})

    detail = service(client).get_message("gmail-1")

    assert "Hola equipo" in detail.body_text
    assert "<p>" not in detail.body_text
    assert client.full_calls[0]["format"] == "full"
    assert client.metadata_calls == []
    assert "To" in client.full_calls[0]["metadata_headers"]


def test_detalle_toma_html_cuando_no_hay_texto_plano() -> None:
    full = raw_message(
        "gmail-1",
        parts=[
            {
                "mimeType": "text/html",
                "body": {
                    "data": b64(
                        "<html><head><style>.x{color:red}</style></head>"
                        "<body><p>Hola <b>equipo</b></p>"
                        "<script>alert('x')</script></body></html>"
                    )
                },
            }
        ],
    )
    client = FakeGmailClient(full={"gmail-1": full})

    detail = service(client).get_message("gmail-1")

    assert "Hola equipo" in detail.body_text
    assert "alert" not in detail.body_text
    assert "color:red" not in detail.body_text


def test_detalle_multipart_anidado_y_adjunto_ignorado() -> None:
    full = raw_message(
        "gmail-1",
        parts=[
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": b64("Cuerpo real del correo.")},
                    }
                ],
            },
            {
                "mimeType": "application/pdf",
                "filename": "contrato.pdf",
                "body": {"attachmentId": "adj-2"},
            },
        ],
    )
    client = FakeGmailClient(full={"gmail-1": full})

    detail = service(client).get_message("gmail-1")

    assert detail.body_text == "Cuerpo real del correo."
    # Solo se pidió el mensaje completo elegido; ningún adjunto.
    assert len(client.full_calls) == 1
    assert client.full_calls[0]["id"] == "gmail-1"


class _BrokenClient(FakeGmailClient):
    def gmail_get_message(self, message_id: str, **kwargs: Any) -> Any:
        return "esto no es un mapa"


def test_correo_sin_identificador_o_respuesta_invalida() -> None:
    gmail = service(FakeGmailClient(full={"gmail-1": raw_message("gmail-1")}))

    with pytest.raises(GoogleApiError):
        gmail.get_message("  ")
    with pytest.raises(GoogleApiError):
        service(_BrokenClient()).get_message("gmail-1")


def test_mensaje_sin_cuerpo_legible() -> None:
    client = FakeGmailClient(full={"gmail-1": raw_message("gmail-1")})
    detail = service(client).get_message("gmail-1")
    assert detail.body_text == ""


def test_direcciones_de_destinatarios() -> None:
    full = raw_message(
        "gmail-1",
        headers=(
            ("From", "Ana Pérez <ana@example.com>"),
            ("Subject", "Hola"),
            ("To", "Jarvis <jarvis@example.com>, Luis <luis@example.com>"),
            ("Cc", "Copia <copia@example.com>"),
        ),
    )
    client = FakeGmailClient(full={"gmail-1": full})

    detail = service(client).get_message("gmail-1")

    assert detail.to == (
        "Jarvis <jarvis@example.com>",
        "Luis <luis@example.com>",
    )
    assert detail.cc == ("Copia <copia@example.com>",)


def test_html_a_texto_limpia_entidades_y_bloques() -> None:
    text = html_to_text(
        "<div>Hola&nbsp;mundo</div><p>Segunda l&iacute;nea</p>",
        content_type="html",
    )
    assert "Hola" in text
    assert "mundo" in text
    assert "Segunda línea" in text
    assert "<" not in text


def test_extract_body_prefiere_el_plano_y_acepta_base64_con_padding() -> None:
    payload = {
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": b64("Texto plano", pad=True)},
            },
            {
                "mimeType": "text/html",
                "body": {"data": b64("<p>HTML</p>", pad=True)},
            },
        ]
    }
    assert extract_body(payload) == "Texto plano"


# ----------------------------------------------------------------------
# Asistente
# ----------------------------------------------------------------------
def assistant(client: FakeGmailClient, **kwargs: Any) -> GmailAssistant:
    return GmailAssistant(
        service(client),
        consent=allowed_consent(),
        **kwargs,
    )


def test_revisar_lista_y_cuenta_no_leidos() -> None:
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "a"}, {"id": "b"}]}],
        metadata={
            "a": raw_message("a", internal=ms(2026, 11, 17, 12), labels=("INBOX",)),
            "b": raw_message(
                "b",
                subject="Urgente",
                internal=ms(2026, 11, 17, 13),
                labels=("INBOX", "UNREAD"),
            ),
        },
    )
    bot = assistant(client)

    answer = bot.review()

    assert answer.grounded is True
    assert "2 correos recientes" in answer.text
    assert "1 sin leer" in answer.text
    assert "Urgente" in answer.text
    assert bot.last_query.startswith("Bandeja de entrada de Gmail")


def test_conteo_con_adjuntos_e_importancia() -> None:
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "a"}]}],
        metadata={
            "a": raw_message(
                "a",
                labels=("INBOX", "UNREAD", "IMPORTANT"),
                parts=[
                    {
                        "mimeType": "application/pdf",
                        "filename": "x.pdf",
                        "body": {"attachmentId": "adj"},
                    }
                ],
            )
        },
    )

    answer = assistant(client).count()

    assert "1 sin leer" in answer.text
    assert "importancia alta" in answer.text
    assert "con adjuntos" in answer.text


def test_bandeja_vacia_en_revisar_y_contar() -> None:
    bot = assistant(FakeGmailClient())
    assert "No hay correos" in bot.review().text
    assert "No hay correos" in assistant(FakeGmailClient()).count().text


def test_leer_el_ultimo_correo_usa_el_mas_reciente() -> None:
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "a"}, {"id": "b"}]}],
        metadata={
            "a": raw_message("a", subject="Viejo", internal=ms(2026, 11, 16, 8)),
            "b": raw_message("b", subject="Reciente", internal=ms(2026, 11, 17, 8)),
        },
        full={"b": raw_message("b", subject="Reciente")},
    )
    bot = assistant(client)
    bot.review()

    answer = bot.read_last()

    assert "Reciente" in answer.text
    assert bot.active is not None
    assert bot.active.message.id == "b"


def test_buscar_por_remitente_y_por_asunto() -> None:
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "a"}, {"id": "b"}]}],
        metadata={
            "a": raw_message("a", subject="Propuesta", name="Ana Pérez"),
            "b": raw_message(
                "b", subject="Factura", name="Luis Soto", address="luis@example.com"
            ),
        },
        full={
            "a": raw_message("a", subject="Propuesta", name="Ana Pérez"),
            "b": raw_message(
                "b", subject="Factura", name="Luis Soto", address="luis@example.com"
            ),
        },
    )
    bot = assistant(client)
    bot.review()

    assert "Propuesta" in bot.read_matching("Ana").text
    assert "Factura" in bot.read_matching("factura", mode="subject").text


def test_busqueda_ambigua_y_sin_resultados() -> None:
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "a"}, {"id": "b"}]}],
        metadata={
            "a": raw_message("a", subject="Informe enero", name="Ana"),
            "b": raw_message("b", subject="Informe febrero", name="Ana"),
        },
        full={
            "a": raw_message("a", subject="Informe enero", name="Ana"),
            "b": raw_message("b", subject="Informe febrero", name="Ana"),
        },
    )
    bot = assistant(client)
    bot.review()

    ambiguous = bot.read_matching("Ana")
    assert "varios correos parecidos" in ambiguous.text

    missing = bot.read_matching("zzzz")
    assert "No encontré ningún correo" in missing.text


def test_seguimiento_sobre_el_correo_activo() -> None:
    full = raw_message(
        "gmail-1",
        subject="Plan semanal",
        parts=[
            {
                "mimeType": "text/plain",
                "body": {"data": b64("Revisamos el plan el lunes.")},
            }
        ],
        headers=(
            ("From", "Ana Pérez <ana@example.com>"),
            ("Subject", "Plan semanal"),
            ("To", "Jarvis <jarvis@example.com>"),
        ),
    )
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "gmail-1"}]}],
        metadata={"gmail-1": raw_message("gmail-1", subject="Plan semanal")},
        full={"gmail-1": full},
    )
    bot = assistant(client)
    bot.read_last()

    assert "Plan semanal" in bot.follow_up("¿cuál es el asunto?").text
    assert "ana@example.com" in bot.follow_up("¿quién lo envió?").text
    assert "recibió" in bot.follow_up("¿cuándo llegó?").text
    assert "no tiene adjuntos" in bot.follow_up("¿tiene adjuntos?").text
    assert "marcado como leído" in bot.follow_up("¿está leído?").text
    assert "importancia" in bot.follow_up("¿es importante?").text
    assert "jarvis@example.com" in bot.follow_up("¿cuáles son los destinatarios?").text
    assert "Plan semanal" in bot.follow_up("¿qué dice el cuerpo?").text


def test_seguimiento_sin_correo_abierto() -> None:
    bot = assistant(FakeGmailClient())
    answer = bot.follow_up("¿de quién es?")
    assert "Todavía no he leído ningún correo" in answer.text


def test_resumen_con_gemini_y_con_consentimiento() -> None:
    full = raw_message(
        "gmail-1",
        subject="Presupuesto",
        parts=[
            {
                "mimeType": "text/plain",
                "body": {"data": b64("El presupuesto se aprueba el viernes.")},
            }
        ],
    )
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "gmail-1"}]}],
        metadata={"gmail-1": raw_message("gmail-1", subject="Presupuesto")},
        full={"gmail-1": full},
    )
    provider = FakeProvider(replies=["Se aprueba el viernes."])
    bot = assistant(client, provider=provider)
    bot.read_last()

    answer = bot.summarize_active()

    assert answer.text == "Se aprueba el viernes."
    prompt = provider.prompts[0]
    assert "Presupuesto" in prompt
    assert "presupuesto se aprueba" in prompt
    assert "contenido no confiable" in prompt


def test_resumen_sin_consentimiento_es_local() -> None:
    full = raw_message(
        "gmail-1",
        parts=[
            {
                "mimeType": "text/plain",
                "body": {"data": b64("Primera frase. Segunda frase. Tercera.")},
            }
        ],
    )
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "gmail-1"}]}],
        metadata={"gmail-1": raw_message("gmail-1")},
        full={"gmail-1": full},
    )
    provider = FakeProvider()
    bot = GmailAssistant(
        service(client),
        provider=provider,
        consent=allowed_consent(),
    )
    bot.read_last()

    # Se deniega el consentimiento explícitamente.
    from jarvis.core.consent import ConsentManager

    bot.consent = ConsentManager(lambda request: False)
    answer = bot.summarize_active()

    assert "Resumen local" in answer.text
    assert answer.notice and "no se envió" in answer.notice
    assert provider.prompts == []


def test_pregunta_sin_proveedor_no_inventa() -> None:
    bot = assistant(
        FakeGmailClient(
            list_payloads=[{"messages": [{"id": "a"}]}],
            metadata={"a": raw_message("a")},
            full={"a": raw_message("a")},
        )
    )
    bot.read_last()

    answer = bot.ask("¿cuánto cuesta?")

    assert "No puedo interpretar" in answer.text
    assert answer.grounded is True


def test_pregunta_con_proveedor_usa_solo_el_correo_activo() -> None:
    full = raw_message(
        "a",
        subject="Compra",
        parts=[
            {
                "mimeType": "text/plain",
                "body": {"data": b64("El costo es 100 euros.")},
            }
        ],
    )
    client = FakeGmailClient(
        list_payloads=[{"messages": [{"id": "a"}]}],
        metadata={"a": raw_message("a", subject="Compra")},
        full={"a": full},
    )
    provider = FakeProvider(replies=["Cuesta 100 euros."])
    bot = assistant(client, provider=provider)
    bot.read_last()

    answer = bot.ask("¿cuánto cuesta?")

    assert answer.text == "Cuesta 100 euros."
    assert "PREGUNTA DEL USUARIO" in provider.prompts[0]
    assert "100 euros" in provider.prompts[0]
