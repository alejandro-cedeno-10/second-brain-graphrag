"""Ingesta del corpus: parseo de Markdown con frontmatter, chunking con
provenance y volcado al vector store del stack.

Esta es la Falla 1 de la charla ("trae basura") vista desde el otro
extremo: si el chunking pierde de dónde vino cada fragmento (`doc_id`,
sección, offset), no hay manera honesta de citar la fuente después —
el agente terminaría inventando una cita o abstenniéndose de más de lo
necesario. Todo el diseño de este módulo gira alrededor de conservar ese
provenance intacto desde el `.md` hasta el `Chunk` final.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from second_brain.config import Stack
from second_brain.ports import Chunk

_FRONTMATTER_PATTERN = re.compile(r"\A---\n(?P<bloque>.*?)\n---\n?(?P<cuerpo>.*)\Z", re.DOTALL)
_SECTION_PATTERN = re.compile(r"^#{1,6}\s+(?P<titulo>.+?)\s*$")


@dataclass
class Document:
    """Un `.md` del corpus ya parseado: metadata de frontmatter + cuerpo.

    `doc_id` es la ruta relativa al `.md` (p.ej. `servicios/pagos.md`): es
    justo lo que se necesita citar, porque es lo único que identifica al
    documento fuente de forma estable entre corridas.
    """

    doc_id: str
    title: str
    metadata: dict[str, Any] = field(default_factory=dict)
    body: str = ""


@dataclass
class IndexStats:
    """Resultado observable de una corrida de `index`, para reportar en CLI/logs."""

    documents: int
    chunks: int
    embeddings_dim: int


def load_corpus(path: str | Path) -> list[Document]:
    """Lee todos los `.md` bajo `path` (recursivo), salvo `README.md`.

    El `README.md` de la raíz del corpus es el contrato de diseño para
    humanos (ver `corpus/README.md`), no contenido indexable.
    """
    raiz = Path(path)
    archivos = sorted(p for p in raiz.rglob("*.md") if p.name != "README.md")
    return [_load_document(raiz, archivo) for archivo in archivos]


def _load_document(raiz: Path, file: Path) -> Document:
    texto = file.read_text(encoding="utf-8")
    metadata, cuerpo = _parse_frontmatter(texto)
    doc_id = file.relative_to(raiz).as_posix()
    titulo = metadata.get("titulo", doc_id)
    return Document(doc_id=doc_id, title=titulo, metadata=metadata, body=cuerpo)


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parsea el frontmatter YAML plano (clave: valor, sin anidar) del corpus.

    No se usa una librería YAML completa a propósito: el frontmatter de
    este corpus es intencionalmente plano (ver `corpus/README.md`), y
    resolverlo con un parser propio de una línea por clave evita sumar una
    dependencia nueva solo para tres campos (`titulo`, `tipo`, `equipo`).
    """
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    metadata = {}
    for linea in match.group("bloque").splitlines():
        clave, separador, valor = linea.partition(":")
        if not separador:
            continue
        metadata[clave.strip()] = valor.strip()
    return metadata, match.group("cuerpo")


def chunk_document(doc: Document, size: int = 512, overlap: float = 0.1) -> list[Chunk]:
    """Divide `doc` en chunks de ~`size` palabras, con `overlap` de continuidad.

    Empaca párrafos completos hasta llenar el presupuesto de palabras:
    nunca corta una oración a la mitad, salvo que un único párrafo ya
    exceda `size` por sí solo (caso borde raro en este corpus, pero el
    chunking debe seguir siendo correcto si aparece un documento así). El
    solape retoma las últimas `size * overlap` palabras del chunk anterior
    al abrir el siguiente, para que una idea partida justo en el borde no
    pierda contexto en ninguno de los dos lados.

    Cada chunk conserva en su `metadata` el `titulo_seccion` (el último
    encabezado visto antes del párrafo) y el `offset` (índice de palabra
    donde arranca el contenido nuevo del chunk dentro del documento): esto,
    junto con `document_id`, es el provenance completo que permite citar
    con precisión más adelante.
    """
    overlap_words = max(int(size * overlap), 0)
    pieces = _bounded_pieces(_paragraphs(doc.body), size)
    return _pack_pieces(doc, pieces, size, overlap_words)


def _paragraphs(cuerpo: str) -> list[tuple[str, str, int]]:
    """Devuelve `(titulo_seccion, texto_parrafo, offset_en_palabras)` en orden de aparición."""
    seccion_actual = ""
    offset = 0
    resultado: list[tuple[str, str, int]] = []
    for bloque in re.split(r"\n\s*\n", cuerpo):
        bloque = bloque.strip()
        if not bloque:
            continue
        match_seccion = _SECTION_PATTERN.match(bloque)
        if match_seccion:
            seccion_actual = match_seccion.group("titulo")
            continue
        resultado.append((seccion_actual, bloque, offset))
        offset += len(bloque.split())
    return resultado


def _bounded_pieces(
    parrafos: list[tuple[str, str, int]], size: int
) -> list[tuple[str, list[str], int]]:
    """Convierte párrafos a `(seccion, palabras, offset)`, partiendo los que excedan `size`."""
    piezas: list[tuple[str, list[str], int]] = []
    for seccion, texto, offset in parrafos:
        palabras = texto.split()
        if len(palabras) <= size:
            piezas.append((seccion, palabras, offset))
            continue
        for inicio in range(0, len(palabras), size):
            piezas.append((seccion, palabras[inicio : inicio + size], offset + inicio))
    return piezas


def _pack_pieces(
    doc: Document,
    piezas: list[tuple[str, list[str], int]],
    size: int,
    overlap_words: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    buffer: list[str] = []
    seccion_buffer = ""
    offset_buffer = 0
    for seccion, palabras, offset in piezas:
        if not buffer:
            seccion_buffer, offset_buffer = seccion, offset
        elif len(buffer) + len(palabras) > size:
            chunks.append(_create_chunk(doc, len(chunks), buffer, seccion_buffer, offset_buffer))
            cola = buffer[-overlap_words:] if overlap_words else []
            buffer = list(cola)
            seccion_buffer, offset_buffer = seccion, offset - len(cola)
        buffer.extend(palabras)
    if buffer:
        chunks.append(_create_chunk(doc, len(chunks), buffer, seccion_buffer, offset_buffer))
    return chunks


def _create_chunk(
    doc: Document, index: int, palabras: list[str], seccion: str, offset: int
) -> Chunk:
    metadata = {
        **doc.metadata,
        "doc_id": doc.doc_id,
        "doc_titulo": doc.title,
        "titulo_seccion": seccion,
        "offset": max(offset, 0),
    }
    return Chunk(
        id=f"{doc.doc_id}#{index}",
        document_id=doc.doc_id,
        text=" ".join(palabras),
        metadata=metadata,
    )


def index(
    corpus: list[Document], stack: Stack, size: int = 512, overlap: float = 0.1
) -> IndexStats:
    """Embebe todos los chunks del corpus y los sube al vector store del stack.

    Idempotente porque `VectorStorePort.upsert` actualiza por `id` de
    chunk (`doc_id#indice`): reindexar el mismo corpus sobreescribe cada
    entrada con el mismo contenido en vez de duplicarla.
    """
    chunks = [chunk for doc in corpus for chunk in chunk_document(doc, size=size, overlap=overlap)]
    if chunks:
        vectores = stack.embeddings.embed([chunk.text for chunk in chunks])
        for chunk, vector in zip(chunks, vectores, strict=True):
            chunk.embedding = vector
        stack.vector_store.upsert(chunks)
    return IndexStats(
        documents=len(corpus), chunks=len(chunks), embeddings_dim=stack.embeddings.dim
    )
