#!/usr/bin/env python3
"""CDK app del second brain — stacks chicos, un `cdk deploy --all`.

Ver `README.md` en este directorio para el flujo completo (bootstrap,
deploy, cómo llenar el `.env` del modo `aws`, destroy).

`budget_alert_email` se pasa por contexto: `cdk deploy --all -c
budget_alert_email=vos@tu-correo.com`. Sin ese contexto, `ObservabilityStack`
igual crea el budget (protección aunque nadie lo mire) pero sin suscriptor.

`enable_knowledge_base` y `enable_agentcore` son las banderas de
`PLAN_SERVICIOS_REALES.md`: sin pasarlas, `cdk deploy --all` levanta
exactamente el mismo stack mínimo (storage + agent + observability), sin la
Knowledge Base ni ningún recurso de AgentCore. Se activan por contexto
(`-c enable_knowledge_base=true -c enable_agentcore=true`) o por variable de
entorno (`SECOND_BRAIN_ENABLE_KB`, `SECOND_BRAIN_ENABLE_AGENTCORE`).
`enable_graph_ec2` (o `SECOND_BRAIN_ENABLE_GRAPH_EC2`) suma el `GraphStack`
opcional: FalkorDB en una EC2 chica para correr el grafo también en AWS —
ver `stacks/graph_stack.py` y la sección correspondiente del README.

**El grafo por default sigue siendo local.** El `GraphStack` de Neptune se
dio de baja porque el spike de compatibilidad refutó la razón técnica que lo
justificaba (FalkorDB sí soporta traversal multi-hop real) — FalkorDB es el
motor único de grafo del proyecto, en los dos modos (`local` y `aws`). El
`GraphStack` actual (bajo `enable_graph_ec2`) es otra cosa: el MISMO
FalkorDB, en una EC2 chica, para quien quiere el turno completo consumiendo
AWS (p.ej. grabar la demo end-to-end) — ver `stacks/graph_stack.py`.
"""

from __future__ import annotations

import json
import os

import aws_cdk as cdk
from stacks.agent_stack import AgentStack
from stacks.agentcore_stack import AgentCoreStack
from stacks.graph_stack import GraphStack
from stacks.observability_stack import ObservabilityStack
from stacks.storage_stack import StorageStack


def _flag(context_key: str, env_var: str) -> bool:
    raw = app.node.try_get_context(context_key)
    if raw is None:
        raw = os.environ.get(env_var, "")
    return str(raw).strip().lower() in ("1", "true", "yes")


app = cdk.App()

env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-west-2"),
)

budget_alert_email = app.node.try_get_context("budget_alert_email") or os.environ.get(
    "SECOND_BRAIN_BUDGET_EMAIL", ""
)
enable_knowledge_base = _flag("enable_knowledge_base", "SECOND_BRAIN_ENABLE_KB")
enable_agentcore = _flag("enable_agentcore", "SECOND_BRAIN_ENABLE_AGENTCORE")
enable_graph_ec2 = _flag("enable_graph_ec2", "SECOND_BRAIN_ENABLE_GRAPH_EC2")
falkor_allowed_cidr = app.node.try_get_context("falkor_allowed_cidr") or os.environ.get(
    "SECOND_BRAIN_FALKOR_ALLOWED_CIDR", ""
)

storage = StorageStack(
    app,
    "SecondBrainStorageStack",
    env=env,
    enable_knowledge_base=enable_knowledge_base,
)
agent = AgentStack(
    app,
    "SecondBrainAgentStack",
    env=env,
    corpus_bucket=storage.corpus_bucket,
    vector_bucket_name=storage.vector_bucket.vector_bucket_name,
    vector_index_name=storage.vector_index.index_name,
)
agent.add_dependency(storage)

observability = ObservabilityStack(
    app,
    "SecondBrainObservabilityStack",
    env=env,
    budget_alert_email=budget_alert_email,
    enable_agentcore=enable_agentcore,
)

stacks = [storage, agent, observability]

agentcore = None
if enable_agentcore:
    agentcore = AgentCoreStack(
        app,
        "SecondBrainAgentCoreStack",
        env=env,
        corpus_bucket=storage.corpus_bucket,
        vector_bucket_name=storage.vector_bucket.vector_bucket_name,
        vector_index_name=storage.vector_index.index_name,
        runtime_log_group=observability.runtime_log_group,
        runtime_image_ready=_flag("runtime_image_ready", "SECOND_BRAIN_RUNTIME_IMAGE_READY"),
        knowledge_base_id=(
            storage.knowledge_base.attr_knowledge_base_id if storage.knowledge_base else None
        ),
    )
    agentcore.add_dependency(storage)
    agentcore.add_dependency(observability)
    stacks.append(agentcore)

if enable_graph_ec2:
    graph = GraphStack(
        app,
        "SecondBrainGraphStack",
        env=env,
        allowed_cidr=falkor_allowed_cidr or None,
    )
    stacks.append(graph)

# Algunas cuentas gobernadas por una SCP de organización DENIEGAN la creación
# de recursos si el request no llega con tags de gobernanza obligatorios.
# CloudFormation propaga los tags del stack a cada Create*, así que declarar
# acá los que exija tu organización alcanza para todos los recursos
# taggeables (S3 clásico es la excepción: su CreateBucket no acepta tags en
# el request, ver stacks/storage_stack.py). Los defaults de abajo son
# genéricos; para una cuenta con SCP propia, completalos/pisalos con
# `SECOND_BRAIN_GOVERNANCE_TAGS` (JSON plano, p.ej.
# '{"Owner": "mi-equipo", "Environment": "test"}').
_GOVERNANCE_TAGS = {
    "Project": "second-brain-graphrag-demo",
    "ProjectName": "second-brain",
    "Repository": "second-brain-graphrag",
    "IsCritical": "false",
    "IsTemporal": "true",
}
_extra_tags_raw = os.environ.get("SECOND_BRAIN_GOVERNANCE_TAGS", "")
if _extra_tags_raw:
    _GOVERNANCE_TAGS.update(json.loads(_extra_tags_raw))

for stack in stacks:
    for tag_key, tag_value in _GOVERNANCE_TAGS.items():
        cdk.Tags.of(stack).add(tag_key, tag_value)

app.synth()
