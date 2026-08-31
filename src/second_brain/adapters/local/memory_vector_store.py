"""Índice vectorial en memoria (numpy), sustituto local de S3 Vectors.

Persiste opcionalmente a disco (`.npz` + `.json` para la metadata) para que
la ingesta no se tenga que rehacer entre corridas de ensayo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from second_brain.ports import Chunk, Hit


class MemoryVectorStore:
    """Búsqueda por coseno sobre una matriz numpy mantenida en RAM.

    El `.npz` guarda los vectores; un `.json` al lado guarda ids, textos y
    metadata (numpy no maneja bien arrays de dicts heterogéneos). Ambos se
    derivan de `persistence_path` cambiando la extensión, así el llamador
    solo pasa un único path lógico.
    """

    def __init__(self, persistence_path: str | None = None) -> None:
        self._persistence_path = persistence_path
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metadatas: list[dict[str, Any]] = []
        self._vectors: np.ndarray = np.zeros((0, 0), dtype=np.float64)
        if persistence_path and self._vectors_path.exists():
            self._load()

    @property
    def _vectors_path(self) -> Path:
        return Path(self._persistence_path).with_suffix(".npz")

    @property
    def _metadata_path(self) -> Path:
        return Path(self._persistence_path).with_suffix(".json")

    def upsert(self, items: list[Chunk]) -> None:
        for item in items:
            if item.embedding is None:
                raise ValueError(f"el chunk '{item.id}' no tiene embedding calculado")
            self._upsert_one(item)
        if self._persistence_path:
            self._save()

    def _upsert_one(self, item: Chunk) -> None:
        vector = np.asarray(item.embedding, dtype=np.float64)
        if item.id in self._ids:
            indice = self._ids.index(item.id)
            self._texts[indice] = item.text
            self._metadatas[indice] = item.metadata
            self._vectors[indice] = vector
            return
        self._ids.append(item.id)
        self._texts.append(item.text)
        self._metadatas.append(item.metadata)
        if self._vectors.size == 0:
            self._vectors = vector.reshape(1, -1)
        else:
            self._vectors = np.vstack([self._vectors, vector])

    def search(
        self, vector: list[float], top_k: int, filter: dict[str, Any] | None = None
    ) -> list[Hit]:
        if self._vectors.shape[0] == 0:
            return []
        indices_candidatos = self._indices_que_pasan_filtro(filter)
        if not indices_candidatos:
            return []
        consulta = np.asarray(vector, dtype=np.float64)
        similitudes = self._cosine_similarity(consulta, indices_candidatos)
        orden = np.argsort(similitudes)[::-1][:top_k]
        return [
            Hit(
                chunk_id=self._ids[indices_candidatos[i]],
                text=self._texts[indices_candidatos[i]],
                score=float(similitudes[i]),
                metadata=self._metadatas[indices_candidatos[i]],
            )
            for i in orden
        ]

    def _indices_que_pasan_filtro(self, filter: dict[str, Any] | None) -> list[int]:
        if not filter:
            return list(range(len(self._ids)))
        return [
            i
            for i, metadata in enumerate(self._metadatas)
            if all(metadata.get(clave) == valor for clave, valor in filter.items())
        ]

    def _cosine_similarity(self, query: np.ndarray, indices: list[int]) -> np.ndarray:
        submatriz = self._vectors[indices]
        norma_consulta = np.linalg.norm(query) or 1.0
        normas_filas = np.linalg.norm(submatriz, axis=1)
        normas_filas[normas_filas == 0.0] = 1.0
        return (submatriz @ query) / (normas_filas * norma_consulta)

    def _save(self) -> None:
        np.savez(self._vectors_path, vectores=self._vectors)
        metadata_serializada = {
            "ids": self._ids,
            "textos": self._texts,
            "metadatos": self._metadatas,
        }
        self._metadata_path.write_text(
            json.dumps(metadata_serializada, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self) -> None:
        with np.load(self._vectors_path) as datos:
            self._vectors = datos["vectores"]
        metadata_serializada = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        self._ids = metadata_serializada["ids"]
        self._texts = metadata_serializada["textos"]
        self._metadatas = metadata_serializada["metadatos"]
