"""`ToolkitGraphStore`: lectura del grafo que construye el GraphRAG Toolkit.

Los tres filtros de `neighbors` no son cosmética: cada uno responde a un
comportamiento MEDIDO de la extracción por LLM del toolkit sobre el corpus
de la demo, y sin ellos se rompe de formas concretas que estos tests
documentan. No hacen falta ni FalkorDB ni el toolkit instalado: el conector se
sustituye por un doble que devuelve filas con la forma exacta que produce
`_CYPHER_VECINOS`.
"""

from __future__ import annotations

from typing import Any

import pytest

from second_brain.adapters.toolkit_graph_store import ToolkitGraphStore


class _ConectorFalso:
    """Doble del graph store del toolkit: devuelve filas fijas por query."""

    def __init__(self, filas: list[dict[str, Any]]) -> None:
        self._filas = filas
        self.consultas: list[tuple[str, dict[str, Any]]] = []

    def execute_query(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.consultas.append((cypher, params))
        return self._filas


def _fila(
    vecino: str, relacion: str, directa: bool = True, provenance: list[str] | None = None
) -> dict[str, Any]:
    return {
        "vecino": vecino,
        "relacion": relacion,
        "directa": directa,
        "provenance": provenance if provenance is not None else ["core-billing"],
    }


def test_traduce_una_fila_a_path_con_sentido_y_provenance() -> None:
    store = ToolkitGraphStore(
        _ConectorFalso([_fila("pagos", "CONSUMES", directa=False, provenance=["reportes-backend"])])
    )

    (camino,) = store.neighbors("core-billing", 1)

    assert camino.nodes == ["core-billing", "pagos"]
    assert camino.relations == ["CONSUMES"]
    assert camino.provenance == ["reportes-backend"]
    # `directions[0] is False` significa que el camino recorrió la arista en
    # contra: la relación real es `pagos -> core-billing`. Sin este dato, la
    # síntesis afirmaría lo inverso (ver `ports.py`).
    assert camino.directions == [False]


def test_descarta_relaciones_negadas() -> None:
    """Un predicado que NIEGA la relación es una afirmación invertida.

    La extracción por LLM del toolkit las emite como aristas positivas, sobre
    pares que el documento fuente describe como NO dependientes. El extractor
    propio nunca las creó porque tiene `_NEGATION_PATTERN`. Publicarlas como
    dependencia rompería la promesa central del sistema.
    """
    store = ToolkitGraphStore(
        _ConectorFalso(
            [
                _fila("servicio-b", "DOES NOT CALL"),
                _fila("servicio-c", "DECOUPLED FROM"),
                _fila("pagos", "CONSUMES"),
            ]
        )
    )

    caminos = store.neighbors("core-billing", 1)

    assert [c.nodes[1] for c in caminos] == ["pagos"]


def test_proyecta_a_entidades_que_tienen_documento() -> None:
    """La extracción por LLM crea entidades que no se pueden citar.

    Sobre este corpus produjo 495 entidades contra las 14 del extractor por
    patrones: además de los servicios aparecen la organización entera,
    equipos, personas y cabeceras HTTP. Un salto hacia una entidad sin
    documento no es citable.
    """
    store = ToolkitGraphStore(
        _ConectorFalso(
            [
                _fila("pagos", "CONSUMES"),
                _fila("entidad-sin-documento", "PROVIDED BY"),
                _fila("otra-sin-documento", "USES"),
            ]
        ),
        entidades_con_documento={"pagos", "core-billing"},
    )

    caminos = store.neighbors("core-billing", 1)

    assert [c.nodes[1] for c in caminos] == ["pagos"]


def test_sin_allowlist_devuelve_el_grafo_crudo() -> None:
    """`entidades_con_documento=None` desactiva la proyección a propósito.

    Es el modo que permite mostrar en la charla la diferencia entre el grafo
    crudo del toolkit y el proyectado.
    """
    store = ToolkitGraphStore(
        _ConectorFalso(
            [_fila("pagos", "CONSUMES"), _fila("entidad-sin-documento", "PROVIDED BY")]
        )
    )

    caminos = store.neighbors("core-billing", 1)

    assert {c.nodes[1] for c in caminos} == {"pagos", "entidad-sin-documento"}


def test_deduplica_predicados_sinonimos_del_mismo_par() -> None:
    """El toolkit emite varios predicados casi sinónimos para el mismo par.

    Sobre el corpus real llegó a emitir cuatro predicados distintos entre un
    mismo par de servicios, todos afirmando la misma dependencia.
    Contarlos como aristas distintas infla el grado sin agregar información y
    dispara la guarda anti-hub (`MAX_DEGREE_DEFAULT = 20`), que cortaría la
    expansión y dejaría el blast radius en cero caminos.
    """
    store = ToolkitGraphStore(
        _ConectorFalso(
            [
                _fila("reportes-backend", "CALLS"),
                _fila("reportes-backend", "PREDICADO SINONIMO 2"),
                _fila("reportes-backend", "PREDICADO SINONIMO 3"),
                _fila("reportes-backend", "PREDICADO SINONIMO 4"),
            ]
        )
    )

    caminos = store.neighbors("core-billing", 1)

    assert len(caminos) == 1
    assert caminos[0].relations == ["CALLS"]


def test_no_deduplica_cuando_el_sentido_difiere() -> None:
    """Los dos sentidos entre el mismo par son información distinta.

    Sobre el corpus real hay pares que aparecen en ambos sentidos:
    colapsarlos perdería la mitad de la relación.
    """
    store = ToolkitGraphStore(
        _ConectorFalso(
            [
                _fila("cola-eventos", "PUBLICA EN", directa=False),
                _fila("cola-eventos", "CONSUME DE", directa=True),
            ]
        )
    )

    caminos = store.neighbors("core-billing", 1)

    assert len(caminos) == 2
    assert {c.directions[0] for c in caminos} == {True, False}


def test_provenance_vacio_no_rompe() -> None:
    """El join de provenance puede no resolver: `Path` acepta el hueco."""
    store = ToolkitGraphStore(_ConectorFalso([_fila("pagos", "CONSUMES", provenance=[])]))

    (camino,) = store.neighbors("core-billing", 1)

    assert camino.provenance == [""]


def test_los_upserts_estan_prohibidos() -> None:
    """Escribir el grafo es del toolkit: un upsert a mano reintroduce el problema.

    Toda la migración existe para que las aristas vengan del pipeline del
    toolkit. Permitir un upsert por este adapter volvería a meter aristas de
    otra procedencia en el mismo esquema.
    """
    store = ToolkitGraphStore(_ConectorFalso([]))

    with pytest.raises(NotImplementedError):
        store.upsert_nodes([{"id": "x"}])
    with pytest.raises(NotImplementedError):
        store.upsert_edges([{"origen": "a", "destino": "b", "tipo": "CONSUME"}])


def test_resolve_entity_prefiere_el_match_exacto() -> None:
    class _ConectorExacto(_ConectorFalso):
        def execute_query(self, cypher: str, params: dict[str, Any]):
            self.consultas.append((cypher, params))
            return [{"valor": "core-billing"}] if "e.value = $nombre" in cypher else []

    store = ToolkitGraphStore(_ConectorExacto([]))

    assert store.resolve_entity("core-billing") == ["core-billing"]


def test_resolve_entity_cae_a_las_entidades_mencionadas() -> None:
    """Existe porque la migración rompe `entidad == nombre de archivo`.

    `web/api.py` deriva la raíz del subgrafo del stem del documento, y el
    toolkit nombra las entidades con lo que decida el LLM: un documento puede
    no existir como entidad y sin embargo mencionar varias.
    """

    class _ConectorPorMenciones(_ConectorFalso):
        def execute_query(self, cypher: str, params: dict[str, Any]):
            self.consultas.append((cypher, params))
            if "e.value = $nombre" in cypher:
                return []
            return [
                {"valor": "notificaciones", "menciones": 9},
                {"valor": "core-billing", "menciones": 4},
            ]

    store = ToolkitGraphStore(_ConectorPorMenciones([]))

    assert store.resolve_entity("decisiones") == ["notificaciones", "core-billing"]
