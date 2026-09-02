"""Store LOCAL de memoria: RAM pura, sin AWS y sin persistencia a disco.

A diferencia de `adapters.local.memory_vector_store.MemoryVectorStore` (que
sí persiste a `<path>.npz`/`<path>.json` porque `ingest`/`query` corren en
procesos CLI separados), este store vive solo en RAM del `Stack` en curso:
alcanza porque los escenarios de memoria de la demo siempre corren dentro de
un único proceso (`demo.py check`, `demo.py chat`), nunca entre dos
invocaciones separadas de `demo.py query` — ver Decisión 10 de
`openspec/changes/agregar-memoria-second-brain/design.md` ("se descarta
persistencia a disco por complejidad innecesaria para lo que la demo
necesita mostrar").

Guarda tres cosas por separado, calcando la forma real de AgentCore Memory
(`adapters.aws.agentcore_memory_store.AgentCoreMemoryStore`): hechos
(estrategia SEMANTIC), preferencias (USER_PREFERENCE) y turnos de la
ventana de corto plazo (STM, por `actor_id` + `session_id`).
`seed_hecho`/`seed_preferencia` quedan FUERA de `MemoryPort` a propósito:
son atajos para plantar determinísticamente los escenarios de la demo
(incluida la "memoria mentirosa": un hecho falso sembrado acá pasa por el
MISMO anclaje al grafo que uno inventado por el modelo, sin código nuevo
de detección).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from second_brain.adapters.local.tokenization import tokenize
from second_brain.ports import MemoryHint

_MAX_TURNOS_STM = 6
"""Ventana de turnos recientes que `recall` trae de memoria de corto plazo
por sesión: alcanza para el escenario de continuidad conversacional sin
dejar crecer sin límite el bloque de pistas inyectado al LLM."""


class FakeMemoryStore:
    """`MemoryPort` en RAM (sin persistencia) para modo local."""

    def __init__(self) -> None:
        self._hechos: dict[str, list[dict[str, Any]]] = {}
        self._preferencias: dict[str, list[dict[str, Any]]] = {}
        self._turnos: dict[str, list[dict[str, Any]]] = {}

    def seed_hecho(self, actor_id: str, texto: str, *, namespace: str | None = None) -> None:
        """Planta un hecho (verdadero o falso) para `actor_id`, fuera de `MemoryPort`.

        Sembrar un hecho FALSO acá es exactamente el escenario (c) de la
        demo: `recall` lo va a devolver como pista igual que uno real, y
        es el anclaje al grafo (`agent.postprocess`) el que lo degrada al
        no encontrar arista que lo sostenga — este método no sabe ni le
        importa si el texto es cierto.
        """
        self._hechos.setdefault(actor_id, []).append(
            {"texto": texto, "namespace": namespace or self._namespace_hechos(actor_id)}
        )

    def seed_preferencia(self, actor_id: str, texto: str, *, namespace: str | None = None) -> None:
        """Planta una preferencia para `actor_id`. Cambia FORMA, nunca hechos."""
        self._preferencias.setdefault(actor_id, []).append(
            {"texto": texto, "namespace": namespace or self._namespace_preferencias(actor_id)}
        )

    def recall(self, actor_id: str, session_id: str, query: str) -> list[MemoryHint]:
        return [
            *self._recall_preferencias(actor_id),
            *self._recall_hechos(actor_id, query),
            *self._recall_turnos(actor_id, session_id),
        ]

    def remember_turn(
        self, actor_id: str, session_id: str, question: str, answer_text: str
    ) -> None:
        clave = self._clave_sesion(actor_id, session_id)
        turno = {
            "pregunta": question,
            "respuesta": answer_text,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._turnos.setdefault(clave, []).append(turno)

    def _recall_preferencias(self, actor_id: str) -> list[MemoryHint]:
        return [
            MemoryHint(
                text=item["texto"], kind="preferencia", namespace=item["namespace"], score=1.0
            )
            for item in self._preferencias.get(actor_id, [])
        ]

    def _recall_hechos(self, actor_id: str, query: str) -> list[MemoryHint]:
        """Rankea los hechos sembrados por solapamiento léxico con `query`.

        No filtra por solapamiento cero (mismo criterio que
        `adapters.local.fake_rerank.FakeRerank`): con pocos hechos
        sembrados por actor, es preferible traer siempre todo, ordenado,
        antes que arriesgarse a esconder el hecho plantado por una
        fraseo distinto al de la pregunta.
        """
        tokens_query = Counter(tokenize(query))
        candidatos = self._hechos.get(actor_id, [])
        puntuados = [
            (self._solapamiento(tokens_query, item["texto"]), item) for item in candidatos
        ]
        puntuados.sort(key=lambda par: par[0], reverse=True)
        return [
            MemoryHint(
                text=item["texto"], kind="hecho", namespace=item["namespace"], score=float(score)
            )
            for score, item in puntuados
        ]

    def _recall_turnos(self, actor_id: str, session_id: str) -> list[MemoryHint]:
        clave = self._clave_sesion(actor_id, session_id)
        recientes = self._turnos.get(clave, [])[-_MAX_TURNOS_STM:]
        return [
            MemoryHint(
                text=f"P: {turno['pregunta']}\nR: {turno['respuesta']}",
                kind="turno_stm",
                namespace=None,
                score=None,
            )
            for turno in recientes
        ]

    @staticmethod
    def _solapamiento(tokens_query: Counter[str], texto: str) -> int:
        tokens_texto = Counter(tokenize(texto))
        return sum(min(cantidad, tokens_texto[token]) for token, cantidad in tokens_query.items())

    @staticmethod
    def _namespace_hechos(actor_id: str) -> str:
        return f"second_brain/{actor_id}/hechos"

    @staticmethod
    def _namespace_preferencias(actor_id: str) -> str:
        return f"second_brain/{actor_id}/preferencias"

    @staticmethod
    def _clave_sesion(actor_id: str, session_id: str) -> str:
        return f"{actor_id}::{session_id}"
