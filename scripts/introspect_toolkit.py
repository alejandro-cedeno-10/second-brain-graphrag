"""Fase 0 de la migración: volcar la API REAL del GraphRAG Toolkit instalado.

No se escribe una línea de la migración basándose en memoria o en docs de
internet: `graphrag-lexical-graph` está pinneado a 3.19.1 y su contrib de
FalkorDB a un SHA de git, así que la única fuente de verdad es el paquete
instalado en ESTA imagen. Este script lo introspecciona y deja el volcado en
stdout para poder diseñar contra la superficie que de verdad existe.

Correr dentro del contenedor (el toolkit no está instalado en el host):

    docker compose run --rm demo python scripts/introspect_toolkit.py

Cada bloque va en su propio try/except: que falte un submódulo no debe
impedir descubrir el resto. Un bloque que falla imprime por qué — eso
también es información de diseño.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import traceback


def _titulo(texto: str) -> None:
    print(f"\n{'=' * 78}\n== {texto}\n{'=' * 78}")


def _seccion(texto: str) -> None:
    print(f"\n--- {texto} ---")


def _firma(objeto: object, nombre: str) -> None:
    """Imprime la firma de un callable sin romper si no es introspectable."""
    try:
        print(f"  {nombre}{inspect.signature(objeto)}")
    except (TypeError, ValueError) as exc:
        print(f"  {nombre}(???)  # no introspectable: {exc}")


def _publicos(modulo: object) -> list[str]:
    return sorted(n for n in dir(modulo) if not n.startswith("_"))


def versiones() -> None:
    _titulo("VERSIONES INSTALADAS")
    for dist in (
        "graphrag-lexical-graph",
        "graphrag-toolkit-lexical-graph-falkordb",
        "llama-index-core",
        "falkordb",
        "strands-agents",
    ):
        try:
            from importlib.metadata import version

            print(f"  {dist}: {version(dist)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {dist}: NO INSTALADO ({type(exc).__name__})")


def arbol_de_modulos() -> None:
    """Lista los submódulos del toolkit: el mapa de dónde buscar cada cosa."""
    _titulo("ÁRBOL DE MÓDULOS DEL TOOLKIT")
    for raiz in ("graphrag_toolkit", "graphrag_toolkit_contrib"):
        _seccion(raiz)
        try:
            paquete = importlib.import_module(raiz)
        except Exception as exc:  # noqa: BLE001
            print(f"  no importa: {exc}")
            continue
        rutas = getattr(paquete, "__path__", [])
        for info in pkgutil.walk_packages(rutas, prefix=f"{raiz}."):
            # Solo el esqueleto: submódulos de storage/indexing/retrieval son
            # los que importan para la migración.
            if info.name.count(".") <= 4:
                print(f"  {'[pkg] ' if info.ispkg else '      '}{info.name}")


def api_lexical_graph() -> None:
    _titulo("API PÚBLICA DE graphrag_toolkit.lexical_graph")
    try:
        modulo = importlib.import_module("graphrag_toolkit.lexical_graph")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return
    print("  exportados:", _publicos(modulo))

    for nombre in _publicos(modulo):
        objeto = getattr(modulo, nombre)
        if not inspect.isclass(objeto):
            continue
        _seccion(f"class {nombre}")
        _firma(objeto, "__init__")
        metodos = [
            n
            for n in dir(objeto)
            if not n.startswith("_") and callable(getattr(objeto, n, None))
        ]
        for metodo in sorted(metodos):
            _firma(getattr(objeto, metodo), f".{metodo}")


def api_query_engine() -> None:
    """El camino de LECTURA: lo que reemplaza a `graph/traversal.py`.

    Es el hueco más grande del diseño actual — hoy el proyecto no usa NINGÚN
    retriever del toolkit, así que hay que descubrir cuáles existen, qué
    stores exigen y qué devuelven (¿trae provenance por salto? ¿trae el
    sentido de cada arista, que es lo que `Path.directions` necesita?).
    """
    _titulo("CAMINO DE LECTURA — query engines y retrievers")
    candidatos = [
        "graphrag_toolkit.lexical_graph.LexicalGraphQueryEngine",
        "graphrag_toolkit.lexical_graph.retrieval",
        "graphrag_toolkit.lexical_graph.retrieval.retrievers",
        "graphrag_toolkit.lexical_graph.retrieval.post_processors",
    ]
    for ruta in candidatos:
        _seccion(ruta)
        modulo_ruta, _, atributo = ruta.rpartition(".")
        try:
            if atributo and atributo[0].isupper():
                modulo = importlib.import_module(modulo_ruta)
                objeto = getattr(modulo, atributo)
                _firma(objeto, "__init__")
                for metodo in sorted(
                    n for n in dir(objeto) if not n.startswith("_")
                ):
                    _firma(getattr(objeto, metodo), f".{metodo}")
            else:
                modulo = importlib.import_module(ruta)
                print("  exportados:", _publicos(modulo))
        except Exception as exc:  # noqa: BLE001
            print(f"  no disponible: {type(exc).__name__}: {exc}")


def modelo_de_datos() -> None:
    """El esquema propio del toolkit: Document/Chunk/Topic/Statement/Fact/Entity.

    `Fact` es la pieza clave para la migración: si expone subject/predicate/
    object, el SENTIDO de cada relación se puede reconstruir y
    `Path.directions` (y con él la flecha del cytoscape y el guard de
    anclaje) sobrevive. Si no, el frontend pierde dirección y hay que
    decidir qué hacer.
    """
    _titulo("MODELO DE DATOS DEL TOOLKIT (clave para Path.directions)")
    for ruta in (
        "graphrag_toolkit.lexical_graph.indexing.model",
        "graphrag_toolkit.lexical_graph.indexing",
    ):
        _seccion(ruta)
        try:
            modulo = importlib.import_module(ruta)
        except Exception as exc:  # noqa: BLE001
            print(f"  no disponible: {exc}")
            continue
        print("  exportados:", _publicos(modulo))
        for nombre in _publicos(modulo):
            objeto = getattr(modulo, nombre)
            if not inspect.isclass(objeto):
                continue
            campos = getattr(objeto, "model_fields", None)  # pydantic
            if campos:
                print(f"    {nombre}: {sorted(campos)}")


def api_graph_store() -> None:
    """La parte que YA usamos: factory + `execute_query`.

    Interesa qué MÁS expone `GraphStore` además de `execute_query`, porque
    la migración debería usar sus primitivas en vez del Cypher a mano de
    `adapters/local/falkor_graph_store.py`.
    """
    _titulo("GraphStoreFactory / GraphStore — qué más expone")
    try:
        from graphrag_toolkit.lexical_graph.storage.graph_store_factory import (
            GraphStoreFactory,
        )

        _seccion("GraphStoreFactory")
        for metodo in sorted(n for n in dir(GraphStoreFactory) if not n.startswith("_")):
            _firma(getattr(GraphStoreFactory, metodo), f".{metodo}")
    except Exception:  # noqa: BLE001
        traceback.print_exc()

    for ruta, clase in (
        ("graphrag_toolkit.lexical_graph.storage.graph", "GraphStore"),
        ("graphrag_toolkit.lexical_graph.storage.graph.graph_store", "GraphStore"),
    ):
        _seccion(f"{ruta}.{clase}")
        try:
            modulo = importlib.import_module(ruta)
            objeto = getattr(modulo, clase)
            for metodo in sorted(n for n in dir(objeto) if not n.startswith("_")):
                _firma(getattr(objeto, metodo), f".{metodo}")
        except Exception as exc:  # noqa: BLE001
            print(f"  no disponible: {type(exc).__name__}: {exc}")


def vector_stores_disponibles() -> None:
    """¿Hay un vector store del toolkit que corra 100% local?

    `LexicalGraphIndex`/los retrievers piden vector store además de graph
    store. Hoy el proyecto usa su propio `MemoryVectorStore`, que el toolkit
    no conoce. Si no hay una opción local soportada, la migración del camino
    de lectura queda atada a AWS (OpenSearch/Neptune) y eso hay que saberlo
    ANTES de escribir código.
    """
    _titulo("VECTOR STORES DEL TOOLKIT (¿alguno local?)")
    for ruta in (
        "graphrag_toolkit.lexical_graph.storage.vector_store_factory",
        "graphrag_toolkit.lexical_graph.storage.vector",
        "graphrag_toolkit_contrib.lexical_graph.storage.vector",
    ):
        _seccion(ruta)
        try:
            modulo = importlib.import_module(ruta)
            print("  exportados:", _publicos(modulo))
        except Exception as exc:  # noqa: BLE001
            print(f"  no disponible: {type(exc).__name__}: {exc}")


def main() -> None:
    versiones()
    arbol_de_modulos()
    api_lexical_graph()
    api_query_engine()
    modelo_de_datos()
    api_graph_store()
    vector_stores_disponibles()
    print("\n== FIN DEL VOLCADO ==")


if __name__ == "__main__":
    main()
