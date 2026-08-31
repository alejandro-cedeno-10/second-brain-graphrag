"""Grafo de conocimiento en memoria (dict de adyacencia), fake del `GraphStorePort`.

Existe para poder testear la extracción y el traversal del grafo (P2 de la
demo) sin depender de Docker/FalkorDB: el mismo `LexicalGraph` que se upsertea
acá se upsertea, sin cambiar una línea del código que llama, contra FalkorDB
real (ver `tests/test_graph.py`, el test marcado `docker`). No interpreta
openCypher — solo implementa `neighbors` con una búsqueda en anchura sobre el
dict, que es la única primitiva que `graph/traversal.py` necesita.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from second_brain.ports import Path


@dataclass
class _Edge:
    destination: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)
    forward: bool = True
    """False cuando esta entrada es el reverso sintetico de la arista real.

    La adyacencia guarda los dos sentidos para poder recorrer el grafo en
    cualquier direccion; este campo recuerda cual de los dos es el que el
    corpus afirma, para que verbalizar el salto no invierta la relacion.
    """


class MemoryGraphStore:
    """Adyacencia no dirigida en RAM: cada arista se guarda en ambos sentidos.

    FalkorGraphStore recorre con el patrón `-[*1..N]-` (sin flecha, cualquier
    dirección) precisamente porque en el dominio de la demo las relaciones de
    dependencia convergen en un nodo raíz (`core-billing`, sin salientes) —
    recorrer sin dirección desde la raíz encuentra exactamente a quienes
    dependen de ella. Este fake replica esa misma semántica para que los
    tests no-Docker vean el mismo comportamiento que el FalkorDB real.
    """

    def __init__(self) -> None:
        self._adjacency: dict[str, list[_Edge]] = {}

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            self._adjacency.setdefault(node["id"], [])

    def upsert_edges(self, edges: list[dict[str, Any]]) -> None:
        """MERGE por `(origen, tipo, destino)`: reconstruir el grafo es idempotente."""
        for edge in edges:
            origen, destino, tipo = edge["origen"], edge["destino"], edge["tipo"]
            properties = {
                key: value
                for key, value in edge.items()
                if key not in ("origen", "destino", "tipo")
            }
            self._add_direction(origen, destino, tipo, properties, forward=True)
            self._add_direction(destino, origen, tipo, properties, forward=False)

    def _add_direction(
        self, source: str, target: str, type_: str, properties: dict[str, Any], *, forward: bool
    ) -> None:
        lista = self._adjacency.setdefault(source, [])
        self._adjacency.setdefault(target, [])
        for existing in lista:
            if existing.destination == target and existing.type == type_:
                existing.properties.update(properties)
                return
        lista.append(
            _Edge(destination=target, type=type_, properties=dict(properties), forward=forward)
        )

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "MemoryGraphStore no interpreta openCypher: es un fake pensado para "
            "traversal.py, que solo usa upsert_nodes/upsert_edges/neighbors. "
            "Para correr Cypher de verdad usar FalkorGraphStore."
        )

    def neighbors(self, entity: str, max_hops: int) -> list[Path]:
        """Todos los caminos simples (sin repetir nodo) de largo 1..`max_hops`."""
        resultados: list[Path] = []
        self._explore(entity, [entity], [], [], [], max_hops, resultados)
        return resultados

    def _explore(
        self,
        current: str,
        nodes: list[str],
        relations: list[str],
        provenance: list[str],
        directions: list[bool],
        remaining: int,
        results: list[Path],
    ) -> None:
        if remaining == 0:
            return
        for edge in self._adjacency.get(current, []):
            if edge.destination in nodes:
                continue
            new_nodes = [*nodes, edge.destination]
            new_relations = [*relations, edge.type]
            new_provenance = [*provenance, edge.properties.get("documento_id", "")]
            new_directions = [*directions, edge.forward]
            results.append(
                Path(
                    nodes=new_nodes,
                    relations=new_relations,
                    provenance=new_provenance,
                    directions=new_directions,
                )
            )
            self._explore(
                edge.destination,
                new_nodes,
                new_relations,
                new_provenance,
                new_directions,
                remaining - 1,
                results,
            )
