"""Extracción y construcción del grafo 100% con el GraphRAG Toolkit.

Reemplaza el extractor propio por `LexicalGraphIndex`, en DOS FASES para no
perder el ensayo offline (ver `PLAN_MIGRACION_TOOLKIT.md`, Fase 0):

    extract  ->  necesita un LLM real (Nova por Bedrock). Corre UNA vez y
                 deja los nodos extraídos como JSON en `--docs-dir`, que se
                 versiona en git.
    build    ->  no necesita LLM. Lee ese JSON y escribe el grafo en
                 FalkorDB con el esquema propio del toolkit
                 (`__Source__`/`__Chunk__`/`__Statement__`/`__Fact__`/
                 `__Entity__`). Es el paso que corre en cada ensayo y el día
                 de la charla.

    python scripts/toolkit_extract_build.py extract   # con credenciales AWS
    python scripts/toolkit_extract_build.py build     # offline
    python scripts/toolkit_extract_build.py both

El LLM se cablea por `GraphRAGConfig.extraction_llm`, NO por
`llama_index.Settings.llm`: el toolkit ignora ese último (bug encontrado en
`adapters/graphrag_toolkit.py:113`, ver el plan).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("toolkit_extract_build")


def _documentos_llama(ruta_corpus: str, limite: int | None = None) -> list:
    """Los `.md` del corpus como `Document` de LlamaIndex.

    Excluye `README.md` igual que `ingestion.load_corpus` (`ingestion.py:57`):
    es el contrato de diseño para humanos, no contenido indexable. El
    extractor propio NO lo excluía y por eso el grafo actual tiene una arista
    cuyo provenance es `README` — ver el plan.
    """
    from llama_index.core.schema import Document as LlamaDocument

    raiz = Path(ruta_corpus)
    archivos = sorted(p for p in raiz.rglob("*.md") if p.name != "README.md")
    documentos = []
    for archivo in archivos:
        doc_id = archivo.relative_to(raiz).as_posix()
        documentos.append(
            LlamaDocument(
                text=archivo.read_text(encoding="utf-8"),
                doc_id=doc_id,
                metadata={"source": doc_id, "stem": archivo.stem},
            )
        )
    if limite:
        documentos = documentos[:limite]
        logger.info("LIMITADO a %d documentos (smoke test)", limite)
    logger.info("corpus: %d documentos (README.md excluido)", len(documentos))
    return documentos


def _configurar(modelo_llm: str, region: str) -> None:
    from graphrag_toolkit.lexical_graph import GraphRAGConfig

    GraphRAGConfig.aws_region = region
    GraphRAGConfig.extraction_llm = modelo_llm
    logger.info("extraction_llm=%s region=%s", modelo_llm, region)


def _graph_store(uri: str, database: str):
    """El graph store del toolkit vía su factory + el contrib de FalkorDB."""
    from graphrag_toolkit.lexical_graph.storage.graph_store_factory import (
        GraphStoreFactory,
    )
    from graphrag_toolkit_contrib.lexical_graph.storage.graph.falkordb import (
        FalkorDBGraphStoreFactory,
    )

    GraphStoreFactory.register(FalkorDBGraphStoreFactory)
    store = GraphStoreFactory.for_graph_store(uri, database=database)
    logger.info("graph store: %s (%s) -> %s", uri, database, type(store).__name__)
    return store


def _indice(graph_store, docs_dir: str, vector_store: str):
    """`LexicalGraphIndex` del toolkit.

    `vector_store` NO es opcional en la práctica: aunque la firma lo declara
    `Optional[...] = None`, `__init__` se lo pasa igual a
    `VectorStoreFactory.for_vector_store()`, que hace `.startswith()` sobre
    el valor y rompe con `None`. `dummy://` es el URI que reconoce
    `DummyVectorIndexFactory` — alcanza para indexar y construir el grafo
    sin ningún servicio de vectores. La búsqueda semántica real necesita
    `postgresql://...` (`PGVectorIndexFactory`), que corre local en Docker.
    """
    from graphrag_toolkit.lexical_graph import LexicalGraphIndex

    return LexicalGraphIndex(
        graph_store=graph_store, vector_store=vector_store, extraction_dir=docs_dir
    )


def _file_based_docs(docs_dir: str, collection_id: str):
    """`FileBasedDocs` con un `collection_id` EXPLÍCITO y estable.

    Sin él, `FileBasedDocs` usa `datetime.now().strftime('%Y%m%d-%H%M%S')`
    (`file_based_docs.py:90`), o sea que cada instancia apunta a una
    colección nueva: `build()` leería un directorio vacío y construiría un
    grafo de cero nodos. Fijarlo es lo que vuelve los artefactos de
    extracción reproducibles y versionables — la base del ensayo offline.
    """
    from graphrag_toolkit.lexical_graph.indexing.load import FileBasedDocs

    return FileBasedDocs(docs_directory=docs_dir, collection_id=collection_id)


def comando_extract(args: argparse.Namespace) -> None:
    _configurar(args.modelo, args.region)
    store = _graph_store(args.uri, args.database)
    indice = _indice(store, args.docs_dir, args.vector_store)
    docs = _file_based_docs(args.docs_dir, args.collection_id)
    documentos = _documentos_llama(args.corpus, args.limit)

    logger.info("extract(): LLM real, esto tarda y cuesta — una sola vez")
    indice.extract(documentos, handler=docs, show_progress=True)
    logger.info("extract() completo -> %s", args.docs_dir)
    _resumen_docs(args.docs_dir)


def _silenciar_llm() -> None:
    from graphrag_toolkit.lexical_graph import GraphRAGConfig
    from llama_index.core.base.llms.types import LLMMetadata
    from llama_index.core.llms import CustomLLM

    class _NoOp(CustomLLM):
        @property
        def metadata(self) -> LLMMetadata:
            return LLMMetadata(context_window=8192, num_output=512)

        def complete(self, prompt: str, formatted: bool = False, **kwargs):
            raise RuntimeError("build() no debe invocar un LLM")

        def stream_complete(self, prompt: str, formatted: bool = False, **kwargs):
            raise RuntimeError("build() no debe invocar un LLM")

    GraphRAGConfig.extraction_llm = _NoOp()
    logger.info("extraction_llm = no-op (build offline, sin Bedrock)")


def comando_build(args: argparse.Namespace) -> None:
    _silenciar_llm()
    store = _graph_store(args.uri, args.database)
    indice = _indice(store, args.docs_dir, args.vector_store)
    docs = _file_based_docs(args.docs_dir, args.collection_id)

    logger.info("build(): sin LLM, desde %s", args.docs_dir)
    indice.build(docs.docs(), show_progress=True)
    logger.info("build() completo")
    try:
        logger.info("stats: %s", indice.get_stats())
    except Exception as exc:  # noqa: BLE001 - get_stats es informativo
        logger.info("get_stats() no disponible: %s", exc)


def _resumen_docs(docs_dir: str) -> None:
    raiz = Path(docs_dir)
    if not raiz.exists():
        logger.warning("%s no existe: extract() no escribió nada", docs_dir)
        return
    archivos = sorted(raiz.rglob("*"))
    solo_archivos = [a for a in archivos if a.is_file()]
    total = sum(a.stat().st_size for a in solo_archivos)
    logger.info("%d archivos, %.1f KB en %s", len(solo_archivos), total / 1024, docs_dir)
    for a in solo_archivos[:8]:
        logger.info("  %s (%d B)", a.relative_to(raiz), a.stat().st_size)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("comando", choices=["extract", "build", "both"])
    parser.add_argument("--corpus", default="corpus")
    parser.add_argument("--docs-dir", default=".data/extraccion_toolkit")
    parser.add_argument(
        "--uri", default=f"falkordb://{os.environ.get('SECOND_BRAIN_FALKOR_HOST', 'falkordb')}:6379"
    )
    # Alfanumérico obligatorio: es una validación real del contrib
    # (`FalkorDBDatabaseClient` exige `database.isalnum()`).
    parser.add_argument("--database", default="toolkitgrafo")
    parser.add_argument(
        "--vector-store", default="dummy://", help="dummy:// (offline) o postgresql://..."
    )
    parser.add_argument(
        "--collection-id",
        default="nexora",
        help="id estable de la coleccion extraida (sin esto FileBasedDocs usa un timestamp)",
    )
    parser.add_argument("--modelo", default="amazon.nova-pro-v1:0")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    parser.add_argument(
        "--limit", type=int, default=None, help="solo N documentos (validar cableado barato)"
    )
    args = parser.parse_args()

    if args.comando in ("extract", "both"):
        comando_extract(args)
    if args.comando in ("build", "both"):
        comando_build(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
