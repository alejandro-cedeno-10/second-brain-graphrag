"""`GraphStorePort` sobre el esquema PROPIO del GraphRAG Toolkit.

Este es el adapter de la migración total: el grafo lo construye
`LexicalGraphIndex` del toolkit (ver `scripts/toolkit_extract_build.py`) y
este módulo solo lo LEE, traduciendo el esquema del toolkit al `Path` que
consumen `graph/traversal.py`, el CLI (`--trace`) y la UI web
(`web/api.py::_path_to_dict` -> `PanelGrafo.vue`).

Diferencias con `adapters/local/falkor_graph_store.py`, que este módulo
reemplaza en el camino migrado:

- Nodos `__Entity__` (clave `entityId`, nombre humano en `value`) en vez de
  `Entidad` (clave `id`).
- Aristas `__RELATION__` con el predicado en `value` en vez de `RELACION`
  con `tipo`. La forma es la misma —una sola clase de arista con el
  predicado como propiedad— porque el toolkit tomó la misma decisión de
  diseño (`entity_relation_graph_builder.py:78-82`).
- El PROVENANCE no vive en la arista: hay que recorrer
  `__Fact__ -[__SUPPORTS__]-> __Statement__ -[__MENTIONED_IN__]-> __Chunk__
  -[__EXTRACTED_FROM__]-> __Source__` y leer `__Source__.stem`. Esa
  topología está verificada contra un grafo real construido por el toolkit,
  no supuesta.

`upsert_nodes`/`upsert_edges` levantan `NotImplementedError` a propósito:
escribir el grafo es responsabilidad del toolkit, y un upsert a mano sobre
este esquema volvería a meter aristas que no vienen de su pipeline —
exactamente lo que la migración quiere eliminar.
"""

from __future__ import annotations

from typing import Any

from second_brain.ports import Path

# Un salto desde una entidad, con el sentido real de la arista y el documento
# del que salió. Se pide de a UN salto porque `graph/traversal.py` hace su
# propio BFS para poder aplicar la guarda anti-hub nodo por nodo — con el
# grafo del toolkit esa guarda pasa de anécdota a requisito, porque la
# extracción por LLM crea entidades-hub que inundan cualquier blast radius.
_CYPHER_VECINOS = """
MATCH (a:`__Entity__`)-[r:`__RELATION__`]-(b:`__Entity__`)
WHERE a.value = $entidad
OPTIONAL MATCH (a)-[:`__SUBJECT__`|`__OBJECT__`]->(f:`__Fact__`)<-[:`__SUBJECT__`|`__OBJECT__`]-(b)
OPTIONAL MATCH (f)-[:`__SUPPORTS__`]->(:`__Statement__`)-[:`__MENTIONED_IN__`]->
               (:`__Chunk__`)-[:`__EXTRACTED_FROM__`]->(src:`__Source__`)
RETURN b.value AS vecino,
       r.value AS relacion,
       startNode(r).entityId = a.entityId AS directa,
       collect(DISTINCT src.stem) AS provenance
"""

# Resolución entidad<->documento. La UI parte de un `doc_id` del corpus y le
# saca el stem (`web/api.py::_entity_from_doc_id`), asumiendo que ese string
# es un id de nodo. En el grafo propio eso era cierto por construcción; en el
# del toolkit las entidades las nombra el LLM, así que `pagos` puede existir
# como entidad o no. Este query busca la entidad por nombre exacto y, si no
# la encuentra, cae a las entidades que el documento menciona.
_CYPHER_ENTIDAD_EXACTA = """
MATCH (e:`__Entity__`) WHERE e.value = $nombre RETURN e.value AS valor LIMIT 1
"""

_CYPHER_ENTIDADES_DEL_DOCUMENTO = """
MATCH (src:`__Source__`)<-[:`__EXTRACTED_FROM__`]-(:`__Chunk__`)<-[:`__MENTIONED_IN__`]-
      (st:`__Statement__`)<-[:`__SUPPORTS__`]-(f:`__Fact__`)<-[:`__SUBJECT__`]-(e:`__Entity__`)
WHERE src.stem = $stem
RETURN e.value AS valor, count(*) AS menciones
ORDER BY menciones DESC
LIMIT $limite
"""


# Predicados que NIEGAN la relación. El pipeline del toolkit las emite como
# aristas positivas: sobre este corpus produjo dos aristas entre un par de
# servicios que el documento fuente describe como NO dependientes. El
# extractor propio nunca las creó porque tiene `_NEGATION_PATTERN`
# (`graph/extraction.py:44`).
#
# Sin este filtro, verbalizar el salto afirma lo INVERSO de lo que sostiene
# el corpus — el mismo problema que `Path.directions` existe para evitar
# (`ports.py:66-74`). Un sistema que promete no inventar no puede publicar
# una arista negada como si fuera una dependencia.
_PREDICADOS_NEGADOS = (
    "DOES NOT",
    "DO NOT",
    "DID NOT",
    "NOT ",
    "DETACHED",
    "DECOUPLED",
    "NEVER",
    "NO LONGER",
    "WITHOUT",
)


def _es_negado(relacion: str) -> bool:
    return any(marca in relacion.upper() for marca in _PREDICADOS_NEGADOS)


class ToolkitGraphStore:
    """Lee el grafo que construyó el toolkit, hablándole por su propio conector.

    `graph_store` es el objeto que devuelve
    `GraphStoreFactory.for_graph_store("falkordb://...")` — el mismo camino
    que ya usaba `FalkorGraphStore`, salvo que acá NO hay fallback al cliente
    `falkordb` directo: si el toolkit no está disponible no hay grafo que
    leer, porque es el toolkit el que lo escribió.

    `entidades_con_documento` es el conjunto de nombres de entidad que el
    corpus respalda con un documento propio (los stems de los `.md`). Existe
    porque la extracción por LLM del toolkit produjo **495 entidades** sobre
    este corpus contra las 14 del extractor por patrones: además de los
    servicios aparecen la organización entera, equipos, personas, atributos
    y cabeceras HTTP. Proyectar el grafo sobre las entidades que TIENEN
    documento no es esconder ruido: es el invariante que el grafo de
    respuestas ya tenía (`graph/extraction.py:130` filtraba igual), y es lo
    que permite que cada salto se pueda CITAR. Una arista hacia una entidad
    sin documento no es citable, y una respuesta que no se puede citar es
    justo lo que este sistema promete no dar.

    Pasar `None` desactiva la proyección y devuelve el grafo crudo del
    toolkit — útil para mostrar en la charla la diferencia entre los dos.
    """

    def __init__(
        self, graph_store: Any, entidades_con_documento: set[str] | None = None
    ) -> None:
        self._store = graph_store
        self._entidades_con_documento = entidades_con_documento

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._store.execute_query(cypher, params or {})

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> None:
        raise NotImplementedError(
            "El grafo lo escribe LexicalGraphIndex del toolkit "
            "(scripts/toolkit_extract_build.py), no este adapter."
        )

    def upsert_edges(self, edges: list[dict[str, Any]]) -> None:
        raise NotImplementedError(
            "El grafo lo escribe LexicalGraphIndex del toolkit "
            "(scripts/toolkit_extract_build.py), no este adapter."
        )

    def neighbors(self, entity: str, max_hops: int) -> list[Path]:
        """Vecinos de `entity`, un salto por llamada.

        `max_hops` se acepta por compatibilidad con `GraphStorePort` pero solo
        se honra `1`: pedir más saltos de una sola vez impediría la guarda
        anti-hub del BFS de `graph/traversal.py`, que con este grafo es
        indispensable. Un `max_hops` mayor se resuelve encadenando llamadas,
        que es exactamente lo que ese BFS ya hace.

        Aplica tres filtros, en este orden, y cada uno responde a un
        comportamiento MEDIDO de la extracción del toolkit sobre este corpus:

        1. **Negados** — descarta los predicados de `_PREDICADOS_NEGADOS`:
           son afirmaciones invertidas respecto del documento fuente.
        2. **Proyección a entidades con documento** — ver el docstring de la
           clase. Sin esto `core-billing` tiene grado 44 y `auth-cache` 61,
           así que la guarda anti-hub (`MAX_DEGREE_DEFAULT = 20`) corta su
           expansión y `blast_radius` devuelve CERO caminos: la demo abstiene
           en la pregunta del blast radius.
        3. **Dedup por (vecino, sentido)** — el toolkit emite varios
           predicados casi sinónimos para el mismo par: sobre este corpus
           llegó a cuatro predicados distintos entre un mismo par de
           servicios, todos afirmando la misma dependencia. Contarlos como
           aristas distintas infla el grado sin agregar información. El
           extractor propio deduplicaba igual, por `(origen, tipo, destino)`
           (`graph/extraction.py`, conjunto `seen`).

        Con los tres, el grado máximo en todo el corpus baja de 61 a **11**.
        """
        filas = self.query(_CYPHER_VECINOS, {"entidad": entity})
        vistos: set[tuple[str, bool]] = set()
        caminos: list[Path] = []
        for fila in filas:
            camino = self._fila_a_path(entity, fila)
            if _es_negado(camino.relations[0]):
                continue
            if (
                self._entidades_con_documento is not None
                and camino.nodes[1] not in self._entidades_con_documento
            ):
                continue
            clave = (camino.nodes[1], camino.directions[0])
            if clave in vistos:
                continue
            vistos.add(clave)
            caminos.append(camino)
        return caminos

    def _fila_a_path(self, origen: str, fila: dict[str, Any]) -> Path:
        """Traduce una fila del query a un `Path` de un salto.

        `directa` viene del propio grafo (`startNode(r) == a`), no de una
        heurística: el toolkit escribe la arista `subject -> object`, así que
        el sentido que el corpus declara se conserva. Sin esto, verbalizar el
        salto produce la afirmación invertida — el bug que `Path.directions`
        existe para evitar (ver `ports.py`).
        """
        provenance = fila.get("provenance") or []
        return Path(
            nodes=[origen, fila["vecino"]],
            relations=[fila.get("relacion") or ""],
            provenance=[provenance[0] if provenance else ""],
            directions=[bool(fila.get("directa"))],
        )

    def resolve_entity(self, doc_stem: str, *, limite: int = 3) -> list[str]:
        """Del stem de un documento a las entidades del grafo del toolkit.

        Existe porque la migración rompe la identidad `entidad == nombre de
        archivo` que el frontend asume (`web/api.py:193`): el extractor propio
        solo admitía entidades cuyo id era el nombre del documento
        (`graph/extraction.py:130`), mientras el toolkit las nombra con lo que
        el LLM decida. Verificado sobre un grafo real: `dashboard`,
        `auth-cache` y `reportes-backend` sí coinciden con su stem, pero
        muchas de las entidades que el LLM promueve no existen como documento.

        Devuelve el match exacto si lo hay; si no, las entidades que ese
        documento menciona, ordenadas por cantidad de menciones.
        """
        exacta = self.query(_CYPHER_ENTIDAD_EXACTA, {"nombre": doc_stem})
        if exacta:
            return [exacta[0]["valor"]]
        candidatas = self.query(
            _CYPHER_ENTIDADES_DEL_DOCUMENTO, {"stem": doc_stem, "limite": limite}
        )
        return [fila["valor"] for fila in candidatas]
