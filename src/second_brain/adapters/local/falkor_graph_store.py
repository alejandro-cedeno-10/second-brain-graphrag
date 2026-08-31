"""Cliente FalkorDB (openCypher real) para el ensayo local del grafo.

Es también el adapter de `GraphStorePort` en modo `aws` (ver
`config.py::_stack_aws`): FalkorDB es el motor de grafo único del proyecto,
en los dos modos, apuntando por variable de entorno a `localhost` (default),
a un contenedor Docker, o a un host remoto el día que exista uno.

Usa, cuando está disponible, el conector FalkorDB REAL del GraphRAG Toolkit
de AWS Labs (`adapters.graphrag_toolkit.falkordb_graph_store`, que registra
el contrib `graphrag-toolkit-lexical-graph-falkordb` sobre el
`GraphStoreFactory` del toolkit). Así "qué conector usa el toolkit para
hablarle a FalkorDB" es real y verificable sin tocar una cuenta de AWS.

Si el toolkit (o su contrib de FalkorDB) no está instalado, no pudo
importarse, o el nombre del grafo no es alfanumérico (el contrib lo exige;
ver `graphrag_toolkit.falkordb_graph_store`), este adapter cae a hablarle
directo al cliente oficial `falkordb` — mismo Cypher, mismo esquema
(`Entidad`/`RELACION`), sin que el resto del sistema note la diferencia. La
demo tiene que arrancar igual sin el toolkit instalado.
"""

from __future__ import annotations

from typing import Any

from second_brain.adapters.graphrag_toolkit import falkordb_graph_store
from second_brain.ports import Path

_SIN_RESOLVER = object()


class FalkorGraphStore:
    """Grafo openCypher sobre un FalkorDB local (`docker run falkordb/falkordb`).

    Los nodos se guardan bajo la etiqueta genérica `Entidad` con un `id`
    único como clave de `MERGE`; las relaciones se guardan como aristas
    `RELACION` con un atributo `tipo` (en vez de un tipo de arista por
    relación) para poder recorrer cualquier tipo de vínculo con un único
    patrón `[*1..N]` en `neighbors`.
    """

    def __init__(
        self, host: str = "localhost", port: int = 6379, graph_name: str = "secondbrain"
    ) -> None:
        self._host = host
        self._port = port
        self._graph_name = graph_name
        self._toolkit_store_lazy: Any = _SIN_RESOLVER
        self._fallback_graph_lazy: Any | None = None

    @property
    def _toolkit_store(self) -> Any | None:
        """Resuelve una única vez si hay conector real del toolkit disponible."""
        if self._toolkit_store_lazy is _SIN_RESOLVER:
            self._toolkit_store_lazy = falkordb_graph_store(
                self._host, self._port, self._graph_name
            )
        return self._toolkit_store_lazy

    @property
    def _fallback_graph(self) -> Any:
        """Cliente `falkordb` directo, diferido al primer uso real (ver docstring de arriba).

        `FalkorDB(...)` (a diferencia de `redis.Redis(...)`) valida la
        conexión en el constructor; sin este diferimiento, construir el
        `Stack` local rompería en cualquier entorno sin FalkorDB levantado
        (por ejemplo, tests que ni siquiera ejercitan el grafo).
        """
        if self._fallback_graph_lazy is None:
            from falkordb import FalkorDB

            self._fallback_graph_lazy = FalkorDB(host=self._host, port=self._port).select_graph(
                self._graph_name
            )
        return self._fallback_graph_lazy

    def _execute(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Corre el Cypher por el conector del toolkit si hay uno, si no por el cliente directo.

        `GraphStore.execute_query` del toolkit ya devuelve `list[dict]`
        (columnas resueltas); el cliente `falkordb` crudo devuelve un
        `QueryResult` con `.header`/`.result_set` que hay que combinar a
        mano. Normalizar acá adentro es lo que le permite al resto de la
        clase no saber cuál de los dos backends está corriendo.
        """
        toolkit_store = self._toolkit_store
        if toolkit_store is not None:
            return toolkit_store.execute_query(cypher, params)
        result = self._fallback_graph.query(cypher, params)
        columns = [name for _, name in result.header]
        return [dict(zip(columns, row, strict=True)) for row in result.result_set]

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            properties = {key: value for key, value in node.items() if key != "id"}
            self._execute(
                "MERGE (n:Entidad {id: $id}) SET n += $props",
                {"id": node["id"], "props": properties},
            )

    def upsert_edges(self, edges: list[dict[str, Any]]) -> None:
        """Crea o actualiza cada arista, con cualquier propiedad extra como provenance.

        La identidad de `MERGE` es `(origen, tipo, destino)` — eso es lo que
        hace idempotente reconstruir el grafo desde el mismo corpus. Cualquier
        clave adicional del dict (`document_id`, `fragmento`, ...) se guarda
        como propiedad de la arista vía `SET +=`, para que `neighbors` pueda
        devolver de qué documento salió cada salto (el provenance que permite
        citar un camino de grafo, no solo enumerarlo).
        """
        for edge in edges:
            properties = {
                key: value
                for key, value in edge.items()
                if key not in ("origen", "destino", "tipo")
            }
            self._execute(
                "MATCH (a:Entidad {id: $origen}), (b:Entidad {id: $destino}) "
                "MERGE (a)-[r:RELACION {tipo: $tipo}]->(b) "
                "SET r += $props",
                {
                    "origen": edge["origen"],
                    "destino": edge["destino"],
                    "tipo": edge["tipo"],
                    "props": properties,
                },
            )

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._execute(cypher, params or {})

    def neighbors(self, entity: str, max_hops: int) -> list[Path]:
        """Recorre hasta `max_hops` desde `entity`, en cualquier dirección.

        El límite superior del rango `[*1..N]` no puede parametrizarse en
        openCypher (debe ser un literal), por eso se interpola directamente;
        es seguro porque `max_hops` es un entero, no texto de usuario.
        """
        cypher = (
            "MATCH camino = (origen:Entidad {id: $entidad})"
            f"-[*1..{int(max_hops)}]-(destino:Entidad) "
            "RETURN camino"
        )
        filas = self._execute(cypher, {"entidad": entity})
        return [self._convert_path(fila["camino"]) for fila in filas]

    def _convert_path(self, path: Any) -> Path:
        """Convierte un camino de FalkorDB conservando el SENTIDO real de cada arista.

        El patron `-[*1..N]-` es no dirigido a proposito (asi "quien depende
        de X" encuentra a sus dependientes), pero cada arista si tiene un
        origen declarado. Comparar el nodo de origen de la arista con el nodo
        por el que el camino venia es lo que distingue "A consume a B" de su
        inverso; sin eso la evidencia verbaliza la relacion al reves.

        Funciona igual sea cual sea el backend que resolvió `_execute`: el
        conector del toolkit y el cliente directo devuelven las mismas
        clases `falkordb.path.Path` / `.node.Node` / `.edge.Edge` (el
        contrib envuelve el mismo cliente oficial por dentro).
        """
        path_nodes = path.nodes()
        ids = [node.properties.get("id", "") for node in path_nodes]
        relations: list[str] = []
        provenance: list[str] = []
        directions: list[bool] = []
        for index, edge in enumerate(path.edges()):
            relations.append(edge.properties.get("tipo", edge.relation))
            provenance.append(edge.properties.get("documento_id", ""))
            directions.append(edge.src_node == path_nodes[index].id)
        return Path(nodes=ids, relations=relations, provenance=provenance, directions=directions)
