"""AgentCoreStack: Runtime + Memory + Gateway + Identity, todo bajo la
bandera `enable_agentcore` (stack completa, nada arrastra a las demás si no
se activa).

## Qué hay de verdad en `aws_cdk.aws_bedrockagentcore` (verificado en el venv
de este repo, `aws-cdk-lib==2.267.0`, `SPIKE_COMPATIBILIDAD.md` §5)

El plan original asumía que había que ir todo por `Cfn*` (L1). Es al revés:
hay **L2 reales** para los cuatro componentes que pide la charla —
`Runtime` (alias `AgentCoreRuntime`, mismo símbolo), `Memory`, `Gateway` +
`GatewayTarget`, y el `RuntimeAuthorizerConfiguration` /
`GatewayAuthorizer` para identidad. Solo dos piezas no tienen L2 y se
declaran explícitamente como tal más abajo en vez de fingir que existen:
ver "Lo que NO se declaró" al final de este docstring.

## Runtime — imagen de contenedor

`AgentRuntimeArtifact.from_asset(...)` construye una imagen Docker *en
tiempo de synth* (invoca al daemon de Docker) — inaceptable para un
`cdk synth` que tiene que quedar limpio sin depender de que haya Docker
corriendo en la máquina que sintetiza. Por eso se usa
`from_ecr_repository(repo, tag=...)`, que solo referencia un repositorio
ECR (vacío al principio): el build/push de la imagen real del agente
Strands es un paso posterior, fuera de este `cdk synth`, documentado en el
README de este directorio.

## Protocolo: MCP configurado, A2A servido por el mismo contenedor

`protocol_configuration` de `Runtime` acepta un único `ProtocolType` — es el
contrato de invocación que AgentCore usa para hablarle al contenedor, no una
restricción sobre qué expone el contenedor puertas adentro. Se configura
`ProtocolType.MCP` porque es el protocolo que consume el Gateway (abajo).
El servidor A2A (`strands.multiagent.a2a.A2AServer`, verificado end-to-end
en el spike §4, dos procesos locales reales) corre en el mismo artefacto de
contenedor, en un puerto/proceso propio — AgentCore Runtime no tiene hoy una
forma de declarar "dos protocolos a la vez" en CDK, así que decirlo así en
la charla es más honesto que forzar el campo.

## Memory — STM de sesión + LTM de hechos/preferencias

`Memory` (L2) + dos `ManagedMemoryStrategy` (`SEMANTIC` para hechos,
`USER_PREFERENCE` para preferencias) son la LTM. La STM no es una
"estrategia": es la ventana de retención de eventos de sesión que gobierna
`expiration_duration` en el propio recurso `Memory` — confirma
`SPIKE_COMPATIBILIDAD.md` §5 (`AgentCoreMemorySessionManager` para STM,
`AgentCoreMemoryStore` para LTM, ambos del lado del SDK de Strands; acá solo
se declara el recurso `Memory` que ambos consumen).

## Gateway — por qué Lambda y no OpenAPI/Smithy/mcpServer/apiGateway

El spike confirmó cinco tipos de target: `lambda`, `openApiSchema`,
`smithyModel`, y dos no documentados en el plan original: `mcpServer`
(proxy a un servidor MCP externo) y `apiGateway` (API Gateway REST directo).
Se elige **Lambda** porque:
- Las tools del second brain (`buscar_documentos`, `navegar_grafo`) son
  funciones Python propias, no una API HTTP con spec OpenAPI/Smithy ya
  publicada — envolverlas en Lambda no exige inventar un contrato nuevo.
- `apiGateway` metería una API Gateway REST completa (superficie y costo
  nuevos) solo para desde ahí volver a golpear una Lambda — Lambda directo
  es el mismo resultado con un salto menos.
- `mcpServer` sería la opción correcta el día que el second brain corra
  como servidor MCP propio de forma persistente (§4/§6 del spike, FastMCP) —
  hoy ese servidor no está desplegado como servicio de larga vida en AWS
  (corre local en la demo), así que no hay un endpoint `mcpServer` real al
  que apuntar todavía. Documentado como el camino de upgrade, no como algo
  que ya exista.

## Identity — entrada y salida, sin inventar infraestructura no pedida

- **Entrada** (quién invoca al agente): `RuntimeAuthorizerConfiguration.using_iam()`
  — SigV4/IAM, coherente con el resto del repo (S3 Vectors y la KB también
  se autorizan por IAM, no por usuario/contraseña). El upgrade a Cognito/JWT
  (`using_cognito()`/`using_jwt()`, soportado por el mismo L2) queda
  documentado pero no declarado: no hay ningún caller externo no-AWS en el
  alcance de la charla, y levantar un User Pool solo para esto sería
  infraestructura sin usuario que la ejercite.
- **Salida** (con qué credenciales el agente llega a S3/KB): el
  `execution_role` del propio `Runtime`, con los mismos permisos mínimos que
  ya arma `AgentStack.agent_role` (Bedrock InvokeModel, S3 Vectors, lectura
  del bucket de corpus, y `Retrieve` sobre la KB si está activa) — sin
  permisos de grafo, porque el grafo no tiene infraestructura CDK detrás
  (ver la sección siguiente). `bedrock_agentcore.identity`
  (`WorkloadIdentity` + `OAuth2CredentialProvider`, también con L2 real) es
  el mecanismo para *terceros* no-AWS (Slack, GitHub, etc.) — no aplica hoy
  porque las tools del second brain solo hablan con servicios AWS, así que
  declararlo sería el mismo error que `apiGateway` de arriba:
  infraestructura sin tráfico.

## Sin FalkorDB gestionado en AWS: qué implica para el grafo en modo `aws` (DECISIÓN PENDIENTE DEL USUARIO)

`GraphStack` (VPC + Neptune Database Serverless) se dio de baja: el spike de
compatibilidad refutó la razón técnica que la justificaba — FalkorDB soporta
traversal multi-hop real, no solo búsqueda semantic-guided — así que FalkorDB
es el motor único de grafo del proyecto, en los dos modos (`local` y `aws`).
Esta stack no declara ningún recurso de grafo: `config.py::_stack_aws` conecta
el mismo `FalkorGraphStore` que el modo local, apuntado por
`SECOND_BRAIN_FALKOR_HOST`/`FALKOR_PORT`/`FALKOR_GRAPH_NAME`. Consecuencia
real, no cosmética: esas variables apuntan por default a `localhost`, que
**no es alcanzable desde dentro de AgentCore Runtime** — si el agente
corriera en Runtime sin configurar un host remoto, el grafo se degrada a
fail-open (evidencia solo vectorial/léxica, ver
`agent/orchestrator.py::_traverse_graph_fail_open`), no un endpoint roto.

El análisis completo de qué hacer con esto — FalkorDB en ECS/Fargate
(reintroduce VPC y ~$9-10/mes fijos) frente a dejarlo como está hoy — vive en
`README.md` de este directorio ("No hay Neptune") y **queda pendiente que el
usuario decida**; este código no lo resuelve por su cuenta.

## Lo que NO se declaró (honestidad explícita, no silencio)

- **AgentCore Payments, Browser, Code Interpreter, Evaluator**: existen como
  L1/L2 en el mismo paquete pero no los pide la charla — no se declaran.

## Costos (tabla del spike §7, verificado contra pricing oficial de AWS)

| Recurso | Modelo | Demo 45min | Mes desarrollo (~20h) |
|---|---|---|---|
| Runtime | $0.0895/vCPU-h + $0.00945/GB-h, por segundo, idle gratis | <$0.02 | ~$2 |
| Memory STM | $0.25/1000 eventos nuevos | <$0.01 | <$0.10 |
| Memory LTM | storage $0.75/1000 registros/mes + retrieval $0.50/1000 | <$0.01 | <$0.50 |
| Gateway | invoc. $0.005/1000, search $0.025/1000, indexado $0.02/100 tools/mes | <$0.01 | <$1 |
| ECR (repo vacío hasta el push) | storage $0.10/GB/mes | ~$0 | <$0.10 con una imagen chica |

Cada recurso queda con `RemovalPolicy.DESTROY` explícita.
"""

from __future__ import annotations

from aws_cdk import ArnFormat, CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_bedrockagentcore as bac
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct

BEDROCK_MODEL_IDS = [
    "amazon.nova-2-multimodal-embeddings-v1:0",
    "cohere.embed-multilingual-v3",
    "cohere.rerank-v3-5:0",
    "amazon.nova-micro-v1:0",
    "amazon.nova-pro-v1:0",
]

STM_EXPIRATION_DAYS = 30


class AgentCoreStack(Stack):
    """Runtime + Memory + Gateway + Identity de AgentCore para el second brain."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        corpus_bucket: s3.Bucket | None,
        vector_bucket_name: str,
        vector_index_name: str,
        runtime_log_group: logs.ILogGroup,
        knowledge_base_id: str | None = None,
        runtime_image_ready: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.runtime_role = self._build_runtime_execution_role(
            corpus_bucket=corpus_bucket,
            vector_bucket_name=vector_bucket_name,
            vector_index_name=vector_index_name,
            knowledge_base_id=knowledge_base_id,
        )

        self.runtime_repository = ecr.Repository(
            self,
            "AgentRuntimeRepository",
            repository_name="second-brain-agent-runtime",
            removal_policy=RemovalPolicy.DESTROY,
            empty_on_delete=True,
        )

        # AgentCore Runtime VALIDA en el create que la imagen exista en el
        # repositorio ("The specified image identifier does not exist") — el
        # supuesto original de "repo vacio, push despues" era falso. Por eso el
        # Runtime va detras de `runtime_image_ready` (contexto CDK): primer
        # deploy sin Runtime (crea repo/Memory/Gateway/Identity), build+push de
        # la imagen linux/arm64 (AgentCore solo acepta ARM64), y recien el
        # segundo deploy con `-c runtime_image_ready=true` lo crea.
        self.runtime = None
        if runtime_image_ready:
            self._grant_runtime_operational_baseline(self.runtime_role)
            self.runtime = bac.Runtime(
            self,
            "AgentRuntime",
            runtime_name="second_brain_agent",
            description="Runtime del agente Strands del second brain (MCP hacia el "
            "Gateway; A2A servido por el mismo contenedor en un puerto propio — ver "
            "docstring del stack).",
            agent_runtime_artifact=bac.AgentRuntimeArtifact.from_ecr_repository(
                self.runtime_repository, tag="latest"
            ),
            execution_role=self.runtime_role,
            protocol_configuration=bac.ProtocolType.MCP,
            authorizer_configuration=bac.RuntimeAuthorizerConfiguration.using_iam(),
            tracing_enabled=True,
            logging_configs=[
                bac.LoggingConfig(
                    destination=bac.LoggingDestination.cloud_watch_logs(runtime_log_group),
                    log_type=bac.LogType.APPLICATION_LOGS,
                )
            ],
            environment_variables={
                **self._otel_environment_variables(),
                "SECOND_BRAIN_MODE": "aws",
                "SECOND_BRAIN_S3_VECTORS_BUCKET": vector_bucket_name,
                "SECOND_BRAIN_S3_VECTORS_INDEX_NAME": vector_index_name,
            },
        )
            self.runtime.apply_removal_policy(RemovalPolicy.DESTROY)

        self.memory = bac.Memory(
            self,
            "AgentMemory",
            memory_name="second_brain_memory",
            description="STM de sesión (ventana de expiración de eventos) + LTM de "
            "hechos y preferencias. La memoria orienta la búsqueda; nunca funda una "
            "respuesta citada — el corpus/grafo siguen siendo la única evidencia "
            "citable (ver PLAN_SERVICIOS_REALES.md §5).",
            expiration_duration=Duration.days(STM_EXPIRATION_DAYS),
            memory_strategies=[
                bac.ManagedMemoryStrategy(
                    bac.MemoryStrategyType.SEMANTIC,
                    strategy_name="hechos_arquitectura",
                    namespaces=["second_brain/{actorId}/hechos"],
                ),
                bac.ManagedMemoryStrategy(
                    bac.MemoryStrategyType.USER_PREFERENCE,
                    strategy_name="preferencias_usuario",
                    namespaces=["second_brain/{actorId}/preferencias"],
                ),
            ],
        )
        self.memory.node.find_child("Memory").apply_removal_policy(RemovalPolicy.DESTROY)

        self.gateway = bac.Gateway(
            self,
            "AgentGateway",
            gateway_name="second-brain-gateway",
            description="Expone buscar_documentos/navegar_grafo como tools MCP para "
            "cualquier cliente MCP (Claude Code incluido) sin pasar por el Runtime.",
            protocol_configuration=bac.McpProtocolConfiguration(
                instructions="Herramientas de recuperación del second brain: búsqueda "
                "híbrida en el corpus (buscar_documentos) y navegación del grafo de "
                "conocimiento Nexora (navegar_grafo)."
            ),
            authorizer_configuration=bac.GatewayAuthorizer.using_aws_iam(),
        )
        self.gateway.apply_removal_policy(RemovalPolicy.DESTROY)

        self.tools_function = self._build_tools_lambda()
        self.tools_target = self.gateway.add_lambda_target(
            "ToolsTarget",
            lambda_function=self.tools_function,
            tool_schema=bac.ToolSchema.from_inline(
                [
                    bac.ToolDefinition(
                        name="buscar_documentos",
                        description="Busca documentos relevantes en el corpus del "
                        "second brain (híbrida + RRF + rerank).",
                        input_schema=bac.SchemaDefinition(
                            type=bac.SchemaDefinitionType.OBJECT,
                            properties={
                                "query": bac.SchemaDefinition(
                                    type=bac.SchemaDefinitionType.STRING,
                                    description="Consulta en lenguaje natural.",
                                )
                            },
                            required=["query"],
                        ),
                    ),
                    bac.ToolDefinition(
                        name="navegar_grafo",
                        description="Devuelve dependencias conocidas de una entidad "
                        "del grafo de conocimiento Nexora.",
                        input_schema=bac.SchemaDefinition(
                            type=bac.SchemaDefinitionType.OBJECT,
                            properties={
                                "entidad": bac.SchemaDefinition(
                                    type=bac.SchemaDefinitionType.STRING,
                                    description="Nombre de la entidad a explorar.",
                                )
                            },
                            required=["entidad"],
                        ),
                    ),
                ]
            ),
        )
        self.tools_target.apply_removal_policy(RemovalPolicy.DESTROY)

        if self.runtime is not None:
            CfnOutput(
                self,
                "AgentRuntimeArnOutput",
                value=self.runtime.agent_runtime_arn,
                description="Mapea a SECOND_BRAIN_AGENTCORE_RUNTIME_ARN en .env",
            )
        CfnOutput(
            self,
            "AgentRuntimeEcrRepositoryUriOutput",
            value=self.runtime_repository.repository_uri,
            description="Push de la imagen del agente Strands acá (fuera de "
            "cdk synth/deploy) antes de que el Runtime pueda invocarse de verdad.",
        )
        CfnOutput(
            self,
            "AgentMemoryIdOutput",
            value=self.memory.memory_id,
            description="Mapea a SECOND_BRAIN_AGENTCORE_MEMORY_ID en .env",
        )
        CfnOutput(
            self,
            "AgentGatewayUrlOutput",
            value=self.gateway.gateway_url,
            description="Endpoint MCP del Gateway — cualquier cliente MCP lo puede "
            "consumir con credenciales IAM (SigV4).",
        )

    def _grant_runtime_operational_baseline(self, role: iam.Role) -> None:
        """Permisos operativos que AgentCore Runtime necesita para EXISTIR
        (bajar su imagen de ECR, escribir sus logs, emitir trazas y métricas)
        — distintos de los permisos de DATOS del agente. El L2 los auto-crea
        cuando no le pasás `execution_role`; al pasar un rol propio se pierden
        y el Runtime muere sin poder ni hacer pull de la imagen (verificado:
        AccessDenied en ecr:GetAuthorizationToken / logs:CreateLogStream).
        Set tomado de la política documentada en runtime-permissions.html.
        """
        runtimes_prefix = self.format_arn(
            service="logs",
            resource="log-group",
            resource_name="/aws/bedrock-agentcore/runtimes/*",
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrImagePull",
                actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                resources=[self.runtime_repository.repository_arn],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="EcrToken", actions=["ecr:GetAuthorizationToken"], resources=["*"]
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:DescribeLogStreams",
                    "logs:CreateLogGroup",
                    "logs:PutResourcePolicy",
                ],
                resources=[runtimes_prefix],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(actions=["logs:DescribeLogGroups"], resources=["*"])
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[runtimes_prefix + ":log-stream:*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                resources=["*"],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(actions=["cloudwatch:PutMetricData"], resources=["*"])
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:GetWorkloadAccessToken"],
                resources=[
                    self.format_arn(
                        service="bedrock-agentcore",
                        resource="workload-identity-directory",
                        resource_name="default*",
                        arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                    )
                ],
            )
        )

    def _build_runtime_execution_role(
        self,
        *,
        corpus_bucket: s3.Bucket | None,
        vector_bucket_name: str,
        vector_index_name: str,
        knowledge_base_id: str | None,
    ) -> iam.Role:
        role = iam.Role(
            self,
            "AgentRuntimeExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Identidad de salida del Runtime: mismos permisos mínimos que "
            "AgentStack.agent_role (Bedrock, S3 Vectors, corpus, y Retrieve sobre la "
            "KB si está activa) - sin permisos de grafo, ver docstring del stack.",
        )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="InvokeBedrockModels",
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
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
        role.add_to_policy(
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
        if knowledge_base_id:
            role.add_to_policy(
                iam.PolicyStatement(
                    sid="RetrieveFromKnowledgeBase",
                    actions=["bedrock:Retrieve"],
                    resources=[
                        self.format_arn(
                            service="bedrock",
                            resource="knowledge-base",
                            resource_name=knowledge_base_id,
                            arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                        )
                    ],
                )
            )
        role.add_to_policy(
            iam.PolicyStatement(
                sid="GenAiObservabilityTraces",
                actions=["xray:PutTraceSegments", "xray:PutSpans", "xray:PutSpansForIndexing"],
                resources=["*"],
            )
        )
        if corpus_bucket is not None:
            corpus_bucket.grant_read(role)
        return role

    def _build_tools_lambda(self) -> lambda_.Function:
        log_group = logs.LogGroup(
            self,
            "ToolsFunctionLogGroup",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )
        return lambda_.Function(
            self,
            "ToolsFunction",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambda/second_brain_tools"),
            timeout=Duration.seconds(30),
            log_group=log_group,
        )

    @staticmethod
    def _otel_environment_variables() -> dict[str, str]:
        return {
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
            "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_PYTHON_DISTRO": "aws_distro",
            "OTEL_PYTHON_CONFIGURATOR": "aws_configurator",
            "OTEL_SEMCONV_STABILITY_OPT_IN": "gen_ai_latest_experimental,gen_ai_tool_definitions",
            "OTEL_SERVICE_NAME": "second-brain-agent",
        }
