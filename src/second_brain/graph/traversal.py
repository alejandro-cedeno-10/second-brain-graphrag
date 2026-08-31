"""Traversal multi-hop sobre el grafo de dependencias: el corazón de P2.

"Si modifico la API de `core-billing`, ¿qué módulos se rompen?" no se
responde leyendo `core-billing.md` — la respuesta está repartida en los
documentos de los consumidores (`pagos`, `reportes-backend`,
`notificaciones`). `blast_radius` es la operación que junta esa respuesta:
recorre el grafo desde la entidad modificada hasta `max_hops` de distancia
y devuelve cada camino con su provenance, para que la síntesis pueda citar
de qué documento salió cada salto.

La consulta openCypher equivalente (la que la charla muestra con `[*1..3]`)
ya vive en `FalkorGraphStore.neighbors` — este módulo no la duplica, la usa
como primitiva de UN salto (`neighbors(nodo, 1)`) en cada capa de su propio
BFS. Hace falta un BFS propio, en vez de pedirle a `neighbors` los `N`
saltos de una sola vez, por la guarda anti-hub: solo controlando la
expansión salto a salto se puede decidir, en cada nodo, si su grado amerita
cortar ahí la búsqueda.

Las tres funciones toman `stack` (no solo `graph_store`) para tener siempre
a mano un `Settings`/`Stack` uniforme, aunque la firma abreviada de la
consigna solo lo muestra en `blast_radius` — sin él, `path_between` y
`neighbors_of` no tendrían forma de llegar al grafo.
"""

from __future__ import annotations

from second_brain.config import Stack
from second_brain.ports import GraphStorePort, Path, TraceStep

MAX_DEGREE_DEFAULT = 20

CYPHER_BLAST_RADIUS_DOC = (
    "MATCH camino = (consumidor:Entidad)-[:RELACION*1..N]-(raiz:Entidad {id: $entidad}) "
    "RETURN camino"
)
"""Documenta el equivalente openCypher de `blast_radius` (el `[*1..N]` de la
charla), con `N` = `max_hops`, tal como lo ejecuta `FalkorGraphStore.neighbors`
en local y en modo `aws` (el grafo entra por `GraphStorePort`, y hoy lo
implementa FalkorDB en los dos). `traversal.py` no ejecuta este texto
directamente porque necesita cortar la expansión salto a salto (guarda
anti-hub); queda acá como referencia legible del query declarado.
"""


def blast_radius(
    entity: str,
    stack: Stack,
    max_hops: int = 3,
    *,
    max_degree: int = MAX_DEGREE_DEFAULT,
    trace: list[TraceStep] | None = None,
) -> list[Path]:
    """Quién depende de `entity`, transitivamente, hasta `max_hops`.

    Cada `Path` resultante empieza en `entity` (`nodes[0] == entity`) y
    trae su provenance documento a documento. Puede haber más de un camino
    al mismo nodo (p.ej. `reportes-backend` aparece 1 salto directo y 2
    saltos vía `pagos`): ambos son información real, ninguno se descarta.
    """
    return _bfs(stack.graph_store, entity, max_hops, max_degree, trace)


def path_between(
    source: str,
    target: str,
    stack: Stack,
    max_hops: int = 3,
    *,
    max_degree: int = MAX_DEGREE_DEFAULT,
    trace: list[TraceStep] | None = None,
) -> list[Path]:
    """Todos los caminos de `source` a `target` con `max_hops` o menos."""
    caminos = _bfs(stack.graph_store, source, max_hops, max_degree, trace)
    return [camino for camino in caminos if camino.nodes[-1] == target]


def neighbors_of(entity: str, stack: Stack, max_hops: int = 1) -> list[Path]:
    """Vecindario directo (o hasta `max_hops`) de `entity`, sin guarda anti-hub.

    Pensada para inspección puntual ("¿con qué conecta X?"), no para blast
    radius: por eso no aplica el corte de grado — quien la llama ya está
    pidiendo explícitamente el vecindario completo de un nodo.
    """
    return stack.graph_store.neighbors(entity, max_hops)


def _bfs(
    graph_store: GraphStorePort,
    origen: str,
    max_hops: int,
    max_degree: int,
    trace: list[TraceStep] | None,
) -> list[Path]:
    resultados: list[Path] = []
    frontera = [Path(nodes=[origen])]
    for _ in range(max_hops):
        siguiente_frontera: list[Path] = []
        for camino in frontera:
            siguiente_frontera.extend(
                _expand_one_hop(graph_store, camino, max_degree, trace, resultados)
            )
        frontera = siguiente_frontera
    return resultados


def _expand_one_hop(
    graph_store: GraphStorePort,
    path: Path,
    max_degree: int,
    trace: list[TraceStep] | None,
    results: list[Path],
) -> list[Path]:
    nodo_actual = path.nodes[-1]
    directos = graph_store.neighbors(nodo_actual, 1)
    if len(directos) > max_degree:
        _record_anti_hub_guard(trace, nodo_actual, len(directos), max_degree)
        return []
    nuevos_caminos = []
    for directo in directos:
        vecino = directo.nodes[-1]
        if vecino in path.nodes:
            continue
        nuevo = _extend_path(path, directo, vecino)
        results.append(nuevo)
        nuevos_caminos.append(nuevo)
    return nuevos_caminos


def _extend_path(path: Path, directo: Path, vecino: str) -> Path:
    """Agrega un salto conservando su SENTIDO, no solo su tipo.

    El BFS recorre el grafo como no dirigido para poder contestar "quién
    depende de X", así que sin arrastrar `directions` el camino resultante
    no sabe cuál extremo de cada arista es el que el corpus declara como
    origen — y quien después la verbalice afirmará la relación al revés.
    """
    tipo = directo.relations[0] if directo.relations else ""
    origen_provenance = directo.provenance[0] if directo.provenance else ""
    directa = directo.directions[0] if directo.directions else True
    return Path(
        nodes=[*path.nodes, vecino],
        relations=[*path.relations, tipo],
        provenance=[*path.provenance, origen_provenance],
        directions=[*path.directions, directa],
    )


def _record_anti_hub_guard(
    trace: list[TraceStep] | None, node: str, grado: int, max_degree: int
) -> None:
    """Deja constancia en la traza de que se cortó la expansión de un hub.

    Es el failure mode que la charla enseña al cierre de la demo: un nodo de
    grado desmesurado (un servicio del que "todo depende", o un error de
    extracción que lo conectó con medio corpus) puede volver el blast radius
    inservible por ruido. Cortar ahí, en vez de explotar combinatoriamente,
    es la guarda; que quede en la traza es lo que la vuelve auditable.
    """
    if trace is None:
        return
    trace.append(
        TraceStep(
            stage="grafo.traversal.guardia_anti_hub",
            detail=(
                f"'{node}' tiene grado {grado} (> {max_degree}); "
                "se corta su expansión para no inundar el blast radius"
            ),
            metadata={"nodo": node, "grado": grado, "grado_maximo": max_degree},
        )
    )
