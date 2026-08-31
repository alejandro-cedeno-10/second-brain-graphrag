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

**No hay `GraphStack`/Neptune acá.** Se dio de baja porque el spike de
compatibilidad refutó la razón técnica que la justificaba (FalkorDB sí
soporta traversal multi-hop real) — FalkorDB es el motor único de grafo del
proyecto, en los dos modos (`local` y `aws`). Ver el docstring de
`stacks/agentcore_stack.py` ("Sin FalkorDB gestionado en AWS: qué implica
para el grafo en modo `aws`") para lo que falta para que ese grafo sea
alcanzable desde AgentCore Runtime — es una decisión pendiente de
confirmación del usuario, no un hecho consumado.
"""

from __future__ import annotations

import os

import aws_cdk as cdk
from stacks.agent_stack import AgentStack
from stacks.agentcore_stack import AgentCoreStack
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

# La SCP de la organización de la organización DENIEGA la creación de
# recursos (lambda:CreateFunction verificado; s3:CreateBucket también) si el
# request no llega con los tags de gobernanza que usa toda la cuenta — el
# conjunto se relevó empíricamente de las Lambdas existentes de Expenses
# (`aws lambda list-tags` sobre al-purchase-orders-*). CloudFormation propaga
# los tags del stack a cada Create*, así que declararlos acá alcanza para
# todos los recursos taggeables. (S3 clásico queda igual bloqueado: su
# CreateBucket no acepta tags en el request, ver stacks/storage_stack.py.)
_GOVERNANCE_TAGS = {
    "proyecto": "second-brain-graphrag-demo",
    "Environment": "test",
    "Owner": "Expenses",
    "Project": "second-brain-graphrag-demo",
    "ProjectName": "second-brain",
    "Repository": "second-brain-graphrag-demo-presentacion",
    "IsCritical": "false",
    "IsTemporal": "true",
}

for stack in stacks:
    for tag_key, tag_value in _GOVERNANCE_TAGS.items():
        cdk.Tags.of(stack).add(tag_key, tag_value)

app.synth()
