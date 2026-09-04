"""Vuelca el esquema REAL que hay hoy en FalkorDB: el baseline de la migración.

Se corre DOS veces y se comparan las salidas:

  1. Antes de migrar, sobre el grafo actual  -> `Entidad` / `RELACION`
  2. Después de `extract_and_build`          -> el esquema del toolkit
                                                (Document/Chunk/Topic/
                                                 Statement/Fact/Entity)

Esa comparación es lo que dice, con datos y no con suposiciones, cuánto del
contrato que consume el frontend (`nodos`/`relaciones`/`provenance`/
`direcciones`, ver `web/api.py::_path_to_dict`) se puede reconstruir desde
el esquema del toolkit — y cuánto no.

    docker compose run --rm demo python scripts/dump_graph_schema.py
    docker compose run --rm demo python scripts/dump_graph_schema.py --grafo otronombre
"""

from __future__ import annotations

import argparse
import os
from typing import Any


def _conectar(host: str, port: int, grafo: str) -> Any:
    from falkordb import FalkorDB

    return FalkorDB(host=host, port=port).select_graph(grafo)


def _consultar(g: Any, cypher: str) -> list[list[Any]]:
    """Corre Cypher devolviendo filas crudas, tolerando el grafo vacío.

    Un grafo recién creado hace que FalkorDB responda con error a consultas
    sobre labels inexistentes; acá eso no es una falla, es "todavía no hay
    nada" — se reporta como lista vacía.
    """
    try:
        return g.query(cypher).result_set
    except Exception as exc:  # noqa: BLE001
        print(f"    (sin datos: {type(exc).__name__}: {exc})")
        return []


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SECOND_BRAIN_FALKOR_HOST", "localhost"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("SECOND_BRAIN_FALKOR_PORT", "6379"))
    )
    parser.add_argument(
        "--grafo", default=os.environ.get("SECOND_BRAIN_FALKOR_GRAPH_NAME", "secondbrain")
    )
    args = parser.parse_args()

    print(f"== Grafo '{args.grafo}' en {args.host}:{args.port} ==")
    g = _conectar(args.host, args.port, args.grafo)

    print("\n-- Labels de nodo --")
    for fila in _consultar(g, "CALL db.labels()"):
        etiqueta = fila[0]
        total = _consultar(g, f"MATCH (n:`{etiqueta}`) RETURN count(n)")
        cantidad = total[0][0] if total else "?"
        print(f"  {etiqueta}: {cantidad} nodos")
        propiedades = _consultar(
            g, f"MATCH (n:`{etiqueta}`) RETURN keys(n) AS k LIMIT 1"
        )
        if propiedades:
            print(f"    propiedades: {propiedades[0][0]}")

    print("\n-- Tipos de relación --")
    for fila in _consultar(g, "CALL db.relationshipTypes()"):
        tipo = fila[0]
        total = _consultar(g, f"MATCH ()-[r:`{tipo}`]->() RETURN count(r)")
        cantidad = total[0][0] if total else "?"
        print(f"  {tipo}: {cantidad} aristas")
        propiedades = _consultar(
            g, f"MATCH ()-[r:`{tipo}`]->() RETURN keys(r) AS k LIMIT 1"
        )
        if propiedades:
            print(f"    propiedades: {propiedades[0][0]}")

    print("\n-- Muestra de aristas con su sentido declarado --")
    filas = _consultar(
        g,
        "MATCH (a)-[r]->(b) "
        "RETURN labels(a), a.id, type(r), r.tipo, labels(b), b.id LIMIT 15",
    )
    for fila in filas:
        etiquetas_a, id_a, tipo_arista, tipo_prop, etiquetas_b, id_b = fila
        print(
            f"  ({etiquetas_a} {id_a}) -[{tipo_arista} tipo={tipo_prop}]-> "
            f"({etiquetas_b} {id_b})"
        )

    print("\n== FIN ==")


if __name__ == "__main__":
    main()
