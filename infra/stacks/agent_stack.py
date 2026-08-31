"""AgentStack: el guardrail de Bedrock (contextual grounding) + el rol IAM
del agente con permisos mínimos.

Umbrales de `contextualGroundingPolicyConfig` (0.75 grounding / 0.65
relevance): son los del plan de la charla — "ajustar con el set de
evaluación" antes de production real, nunca quedarse con el default de un
ejemplo.

El guardrail se publica en dos piezas porque así lo modela CloudFormation:
`CfnGuardrail` crea el guardrail (siempre tiene una versión `DRAFT`
editable) y `CfnGuardrailVersion` publica un snapshot inmutable numerado.
`BedrockLlm` (`src/second_brain/adapters/aws/bedrock_llm.py`) recibe
`guardrail_id` + `guardrail_version` por separado — por eso ambos se
exponen como CfnOutput independientes.

El rol IAM del agente NO asume que existan las otras stacks: recibe el ARN
del bucket/índice de S3 Vectors y del bucket de corpus como parámetros del
constructor (wireados en `app.py`), y arma sus statements de permisos
mínimos a partir de esos ARNs.

## Sin Neptune: FalkorDB es el motor único de grafo

`GraphStack` (VPC + Neptune Database Serverless + Lambda "sandman") se dio
de baja: el spike de compatibilidad refutó la razón técnica que la
justificaba — FalkorDB sí soporta traversal multi-hop real (`*1..N` en
Cypher openCypher), no solo búsqueda semantic-guided como se pensaba — así
que FalkorDB es el motor único de grafo del proyecto, en los dos modos
(`local` y `aws`). Este rol no incluye ningún permiso de grafo (no hay
cluster gestionado al que conectarse; en modo `aws`, `config.py::_stack_aws`
conecta el mismo `FalkorGraphStore` que el modo local, apuntado por
variable de entorno) — ver el docstring de `agentcore_stack.py` para el
análisis de qué implica esto para el modo `aws` con AgentCore Runtime.
"""

from __future__ import annotations

from aws_cdk import ArnFormat, CfnOutput, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct

GROUNDING_THRESHOLD = 0.75
RELEVANCE_THRESHOLD = 0.65

# Modelos de Bedrock que el agente invoca (ver .env.example / config.py):
# Cohere Embed Multilingual v3, Cohere Rerank 3.5, Amazon Nova Pro.
BEDROCK_MODEL_IDS = [
    "amazon.nova-2-multimodal-embeddings-v1:0",
    "cohere.embed-multilingual-v3",
    "cohere.rerank-v3-5:0",
    "amazon.nova-micro-v1:0",
    "amazon.nova-pro-v1:0",
]


class AgentStack(Stack):
    """Guardrail de Bedrock (contextual grounding) + rol IAM del agente."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        corpus_bucket: s3.Bucket | None,
        vector_bucket_name: str,
        vector_index_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.guardrail = bedrock.CfnGuardrail(
            self,
            "SecondBrainGuardrail",
            name="second-brain-grounding",
            description="Anti-alucinación después de generar: contextual "
            "grounding sobre la evidencia recuperada (vector + grafo).",
            blocked_input_messaging="No puedo procesar esa solicitud.",
            blocked_outputs_messaging="No tengo evidencia suficiente para responder eso.",
            contextual_grounding_policy_config=bedrock.CfnGuardrail.ContextualGroundingPolicyConfigProperty(
                filters_config=[
                    bedrock.CfnGuardrail.ContextualGroundingFilterConfigProperty(
                        type="GROUNDING",
                        threshold=GROUNDING_THRESHOLD,
                    ),
                    bedrock.CfnGuardrail.ContextualGroundingFilterConfigProperty(
                        type="RELEVANCE",
                        threshold=RELEVANCE_THRESHOLD,
                    ),
                ]
            ),
        )

        self.guardrail_version = bedrock.CfnGuardrailVersion(
            self,
            "SecondBrainGuardrailVersion",
            guardrail_identifier=self.guardrail.attr_guardrail_id,
            description="Versión publicada para la charla — repetir este "
            "recurso (o el CfnGuardrailVersion) tras cada cambio de umbrales.",
        )

        self.agent_role = iam.Role(
            self,
            "AgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Permisos mínimos del second brain: invocar los 3 "
            "modelos de Bedrock usados, leer/escribir su índice de S3 "
            "Vectors, y leer el bucket de corpus.",
        )

        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeBedrockModels",
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    # ARN de foundation model: arn:aws:bedrock:{region}::foundation-model/{id}
                    # (sin account-id — es un recurso global de Bedrock por región).
                    self.format_arn(
                        service="bedrock",
                        account="",
                        resource="foundation-model",
                        resource_name=model_id,
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    )
                    for model_id in BEDROCK_MODEL_IDS
                ],
            )
        )
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                sid="ApplyGuardrail",
                actions=["bedrock:ApplyGuardrail"],
                resources=[self.guardrail.attr_guardrail_arn],
            )
        )
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                sid="S3VectorsReadWrite",
                actions=[
                    "s3vectors:PutVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:GetIndex",
                    "s3vectors:ListVectors",
                ],
                resources=[
                    self.format_arn(
                        service="s3vectors",
                        resource="bucket",
                        resource_name=f"{vector_bucket_name}/index/{vector_index_name}",
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    )
                ],
            )
        )
        if corpus_bucket is not None:
            corpus_bucket.grant_read(self.agent_role)

        CfnOutput(
            self,
            "BedrockGuardrailIdOutput",
            value=self.guardrail.attr_guardrail_id,
            description="Mapea a SECOND_BRAIN_BEDROCK_GUARDRAIL_ID en .env",
        )
        CfnOutput(
            self,
            "BedrockGuardrailVersionOutput",
            value=self.guardrail_version.attr_version,
            description="Mapea a SECOND_BRAIN_BEDROCK_GUARDRAIL_VERSION en .env",
        )
        CfnOutput(
            self,
            "AgentRoleArnOutput",
            value=self.agent_role.role_arn,
            description="Rol IAM del agente (informativo — no lo lee config.py)",
        )
