"""Lectura y fragmentación de documentos."""

from jarvis.documents.chunker import (  # noqa: F401
    Chunk,
    batch_chunks,
    chunk_document,
    chunks_for_heading,
)
from jarvis.documents.docx_loader import load_document  # noqa: F401
from jarvis.documents.models import (  # noqa: F401
    DocumentModel,
    Paragraph,
    Section,
    TableBlock,
)
from jarvis.documents.retriever import (  # noqa: F401
    Retriever,
    SearchHit,
    resolve_section,
)
