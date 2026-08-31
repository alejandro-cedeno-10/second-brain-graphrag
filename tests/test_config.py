"""La fábrica `build_stack` es el corazón del agnosticismo: local vs AWS
por config, nunca por código de dominio distinto.

El test más importante del archivo es `test_local_mode_never_imports_boto3`:
verifica, en un proceso limpio, que ensayar en modo local no necesita
`boto3` instalado ni tocado — ese es el requisito duro de "0% AWS" del plan.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from second_brain.adapters.aws.bedrock_embeddings import BedrockEmbeddings
from second_brain.adapters.aws.bedrock_llm import BedrockLlm
from second_brain.adapters.aws.bedrock_rerank import BedrockRerank
from second_brain.adapters.aws.s3_vectors_store import S3VectorsStore
from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.config import Settings, build_stack


def test_settings_default_is_local() -> None:
    assert Settings().mode == "local"


def test_build_stack_local_mode_returns_local_adapters() -> None:
    stack = build_stack(Settings(mode="local"))

    assert isinstance(stack.embeddings, FakeEmbeddings)
    assert isinstance(stack.vector_store, MemoryVectorStore)
    assert isinstance(stack.graph_store, FalkorGraphStore)
    assert isinstance(stack.rerank, FakeRerank)
    assert isinstance(stack.llm, ScriptedLlm)


def test_build_stack_aws_mode_returns_aws_adapters_without_invoking_them() -> None:
    stack = build_stack(
        Settings(
            mode="aws",
            s3_vectors_bucket="nexora-corp-vectores",
            s3_vectors_index_name="nexora-corp-indice",
        )
    )

    assert isinstance(stack.embeddings, BedrockEmbeddings)
    assert isinstance(stack.vector_store, S3VectorsStore)
    assert isinstance(stack.graph_store, FalkorGraphStore)
    assert isinstance(stack.rerank, BedrockRerank)
    assert isinstance(stack.llm, BedrockLlm)


def test_build_stack_aws_mode_graph_store_is_configurable_by_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El bug que este cambio arregla: sin Neptune desplegado (cero VPCs), el
    modo `aws` tiene que apuntar el grafo a donde diga la variable de
    entorno, nunca a un endpoint Neptune inexistente que rompería el grafo en
    un deploy real.
    """
    monkeypatch.setenv("SECOND_BRAIN_MODE", "aws")
    monkeypatch.setenv("SECOND_BRAIN_FALKOR_HOST", "falkordb.remoto.invalid")
    monkeypatch.setenv("SECOND_BRAIN_FALKOR_PORT", "16379")
    monkeypatch.setenv("SECOND_BRAIN_FALKOR_GRAPH_NAME", "nexoracorp")
    monkeypatch.setenv("SECOND_BRAIN_S3_VECTORS_BUCKET", "nexora-corp-vectores")
    monkeypatch.setenv("SECOND_BRAIN_S3_VECTORS_INDEX_NAME", "nexora-corp-indice")

    stack = build_stack(Settings.from_env())

    assert isinstance(stack.graph_store, FalkorGraphStore)
    assert stack.graph_store._host == "falkordb.remoto.invalid"
    assert stack.graph_store._port == 16379
    assert stack.graph_store._graph_name == "nexoracorp"


def test_build_stack_invalid_mode_fails_explicitly() -> None:
    try:
        build_stack(Settings(mode="produccion-mala"))
    except ValueError as error:
        assert "SECOND_BRAIN_MODE" in str(error)
    else:
        raise AssertionError("se esperaba ValueError para un modo desconocido")


def test_local_mode_never_imports_boto3() -> None:
    """Test de import-graph: en un intérprete limpio, armar y usar el stack
    local (incluyendo importar el paquete `adapters.aws` completo) no debe
    dejar `boto3` en `sys.modules`. Corre en subprocess para no heredar el
    estado de módulos de otros tests de este mismo archivo.
    """

    script = (
        "import sys\n"
        "import second_brain\n"
        "import second_brain.ports\n"
        "import second_brain.config as config\n"
        "import second_brain.adapters.local.fake_embeddings\n"
        "import second_brain.adapters.local.fake_rerank\n"
        "import second_brain.adapters.local.falkor_graph_store\n"
        "import second_brain.adapters.local.memory_vector_store\n"
        "import second_brain.adapters.local.scripted_llm\n"
        "import second_brain.adapters.aws.bedrock_embeddings\n"
        "import second_brain.adapters.aws.bedrock_llm\n"
        "import second_brain.adapters.aws.bedrock_rerank\n"
        "import second_brain.adapters.aws.s3_vectors_store\n"
        "stack = config.build_stack(config.Settings(mode='local'))\n"
        "stack.embeddings.embed(['ping'])\n"
        "assert 'boto3' not in sys.modules, sys.modules.keys()\n"
        "print('OK')\n"
    )

    resultado = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "OK" in resultado.stdout
