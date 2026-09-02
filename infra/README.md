# Infra — el CDK de deploy simple

`cdk deploy --all` reproduce en tu cuenta el second brain que la charla
describe: stacks chicos, cada uno con una responsabilidad, pensados para
que `cdk destroy --all` limpie todo de verdad (`RemovalPolicy.DESTROY` en
cada recurso donde es seguro).

| Stack | Qué crea | Bandera |
|---|---|---|
| `SecondBrainStorageStack` | Bucket S3 del corpus + bucket e índice de **Amazon S3 Vectors** (1024 dims, coseno — igual que Cohere Embed Multilingual v3) + (opcional) **Bedrock Knowledge Base** sobre ese índice | KB bajo `enable_knowledge_base` |
| `SecondBrainAgentStack` | **Amazon Bedrock Guardrails** (contextual grounding) + el rol IAM del agente, permisos mínimos | siempre |
| `SecondBrainObservabilityStack` | Log group del agente + (si `enable_agentcore`) log group del Runtime + alarma de **AWS Budgets** | siempre (parte condicional bajo `enable_agentcore`) |
| `SecondBrainAgentCoreStack` | **AgentCore**: Runtime (ECR + rol de ejecución), Memory (STM+LTM), Gateway + target Lambda para las tools | completa bajo `enable_agentcore` |

No es la demo en vivo de la charla (esa corre 100% local con FalkorDB, ver
`../README.md`) — es la arquitectura de la narrativa, la que hace real la
promesa del abstract de "un repo abierto para reproducir la demo completa".

## No hay Neptune — FalkorDB es el motor único de grafo, en los dos modos

Este CDK **ya no despliega Neptune**, y el código **ya no tiene ningún adapter
de Neptune**: se borró. El plan original (`PLAN_SERVICIOS_REALES.md`) asumía
Neptune como motor de producción porque se creía que FalkorDB solo soportaba
búsqueda semantic-guided. El spike de compatibilidad
(`SPIKE_COMPATIBILIDAD.md` §2) **refutó eso**: FalkorDB corriendo Cypher real
soporta traversal multi-hop (`*1..N`) igual que Neptune openCypher. Con la
razón técnica caída, se sacó `GraphStack` (VPC + Neptune Serverless + Lambda
"sandman") entero, y después se sacó también `neptune_graph_store.py` del
código de adapters: `src/second_brain/config.py::_stack_aws` conecta hoy el
mismo `FalkorGraphStore` que usa el modo local, apuntado por
`SECOND_BRAIN_FALKOR_HOST`/`FALKOR_PORT`/`FALKOR_GRAPH_NAME` — las mismas
tres variables en los dos modos, no un segundo juego de configuración.

**Consecuencia real, pendiente de decisión del usuario**: esas variables
apuntan por default a `localhost`. Eso alcanza para correr `SECOND_BRAIN_MODE=aws`
desde tu máquina (Bedrock + S3 Vectors reales, grafo contra tu FalkorDB local)
pero **no alcanza si el agente corre dentro de AgentCore Runtime**: ese
proceso no tiene ningún `localhost:6379` al que conectarse, así que el grafo
se degradaría a fail-open (evidencia solo vectorial/léxica, nunca un
stacktrace — ver `agent/orchestrator.py::_traverse_graph_fail_open`) en vez
de responder con el grafo real. Las dos opciones (ninguna implementada más
allá de dejar la variable en su default) están documentadas en detalle en el
docstring de `stacks/agentcore_stack.py`
("Sin FalkorDB gestionado en AWS: qué implica para el grafo en modo `aws`"):

- **(a)** FalkorDB en ECS/Fargate, con `SECOND_BRAIN_FALKOR_HOST` apuntando a
  su Service — reintroduce VPC y un costo fijo ~24/7 (~$9-10/mes mínimo), y
  el mismo dilema NAT-vs-endpoints si el Runtime necesita alcanzarlo desde
  fuera de esa VPC.
- **(b)** *(el default de hoy)* Dejar las variables en su default. El modo
  `aws` despliega la parte de recuperación (Bedrock + S3 Vectors + KB
  opcional) de verdad; el grafo se sigue mostrando en vivo desde el proceso
  local con FalkorDB, no desde el Runtime en AWS.
- **(c)** *(opt-in, ya implementada)* FalkorDB en una EC2 chica con el
  `GraphStack` opcional (`-c enable_graph_ec2=true`) — ver la sección
  "Grafo en AWS (opcional)" más abajo. Resuelve el "todo corre en AWS" para
  el proceso local que apunta allá; para alcanzarlo desde AgentCore Runtime
  seguiría faltando red entre el Runtime y esa VPC.

Esto **no se resuelve solo**: es una decisión del usuario antes de correr el
agente dentro de AgentCore Runtime, no algo que este código elige por su
cuenta.

## Prerequisitos

- Cuenta de AWS con acceso a **Amazon Bedrock** habilitado para los modelos
  Cohere Embed Multilingual v3, Cohere Rerank 3.5 y Amazon Nova Micro/Pro (algunos
  requieren "model access" manual una vez por cuenta/región en la consola de
  Bedrock).
- Región recomendada: **us-west-2 (Oregon)** — es donde el plan de la charla
  confirma disponibilidad de Rerank + S3 Vectors + AgentCore juntos. Otra
  región con esos servicios sirve igual.
- Python 3.11+ y Node.js (para el CLI de `cdk`).
- Credenciales de AWS activas (`aws sts get-caller-identity` debe responder).

```bash
cd demo/infra
python -m venv .venv
# Windows: .venv\Scripts\activate   |   bash/zsh: source .venv/bin/activate
pip install -r requirements.txt
npm install -g aws-cdk   # si no tenés el CLI de CDK instalado
```

## Bootstrap (una vez por cuenta/región)

```bash
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

## Deploy

```bash
# Stack mínimo (storage + agent + observability, sin KB ni AgentCore):
cdk deploy --all -c budget_alert_email=vos@tu-correo.com

# Con Knowledge Base y AgentCore:
cdk deploy --all \
  -c budget_alert_email=vos@tu-correo.com \
  -c enable_knowledge_base=true \
  -c enable_agentcore=true

# Deploy COMPLETO (todo lo anterior + el grafo también en AWS):
cdk deploy --all \
  -c budget_alert_email=vos@tu-correo.com \
  -c enable_knowledge_base=true \
  -c enable_agentcore=true \
  -c enable_graph_ec2=true \
  -c falkor_allowed_cidr=$(curl -s ifconfig.me)/32
```

- `budget_alert_email` es el único contexto obligatorio para tener alertas.
  Sin él, la alarma de Budgets se crea igual (protección aunque nadie la
  mire) pero sin suscriptor de notificación — `cdk deploy` no falla, pero no
  te avisa nada.
- `enable_knowledge_base`/`enable_agentcore` (o `SECOND_BRAIN_ENABLE_KB`/
  `SECOND_BRAIN_ENABLE_AGENTCORE` por variable de entorno) son opt-in: sin
  pasarlas, el deploy no arrastra la KB ni ningún recurso de AgentCore.
- **AgentCore Runtime necesita una imagen real en ECR antes de poder
  invocarse.** El deploy crea el repositorio ECR vacío (`AgentRuntimeEcrRepositoryUriOutput`);
  el build/push de la imagen del agente Strands es un paso manual posterior,
  fuera de este `cdk deploy` (no hay Dockerfile de esa imagen en este repo
  todavía).
- Sin `enable_graph_ec2`, **no hay ninguna VPC en este CDK** — el `cdk
  synth`/`cdk deploy` mínimo no dispara el lookup de AZs que sí necesitaba
  el viejo stack de Neptune. `cdk.context.json` puede quedar vacío.

## Grafo en AWS (opcional): FalkorDB en EC2

Por default el grafo corre en tu máquina (Docker) incluso en modo `aws` — ver
la sección de arriba. Para el turno completo consumiendo AWS (p.ej. grabar la
demo end-to-end), `enable_graph_ec2` suma `SecondBrainGraphStack`: una
`t4g.small` (~US$0.017/h) en una VPC mínima propia (1 AZ, solo subnet
pública, sin NAT) que corre el MISMO contenedor `falkordb/falkordb` que usás
en local.

- **El puerto 6379 no se abre a nadie por default.** FalkorDB no tiene
  autenticación, así que el ingreso se habilita SOLO con tu CIDR:
  `-c falkor_allowed_cidr=<tu-ip>/32` (o `SECOND_BRAIN_FALKOR_ALLOWED_CIDR`).
  Sin ese contexto el stack despliega igual pero nada alcanza el puerto.
- **Sin SSH**: administración por SSM
  (`aws ssm start-session --target <FalkorInstanceIdOutput>`).
- **El grafo es efímero**: si la instancia se recicla,
  `python demo.py ingest` lo reconstruye del corpus en segundos.
- `despues-del-deploy.py` detecta el stack y escribe
  `SECOND_BRAIN_FALKOR_HOST=<ip pública>` en el `.env` — después de eso,
  `SECOND_BRAIN_MODE=aws make demo-aws` (o la UI web) navega el grafo en esa
  EC2 en vez del local.
- Terminaste: `cdk destroy SecondBrainGraphStack` (o el `destroy --all`).

## Por qué no hay NAT Gateway ni ALB

La "trampa de presupuesto" del plan: un NAT Gateway (~$32/mes) o un ALB
(~$22/mes) no tienen ninguna función en esta infra — y ahora, sin `GraphStack`,
**no hay ninguna VPC que pudiera necesitarlos**. AgentCore Runtime corre en
modo de red pública gestionado (no en una VPC de cliente); ver el docstring
de `stacks/agentcore_stack.py` para por qué no se metió una VPC ahí tampoco.

## Conectar los outputs del deploy con el `.env` del modo `aws`

Los `CfnOutput` de los stacks mapean 1:1 con las variables `SECOND_BRAIN_*`
que lee `src/second_brain/config.py` (ver también `.env.example`):

| CfnOutput | Stack | Variable en `.env` |
|---|---|---|
| `S3VectorsBucketOutput` | Storage | `SECOND_BRAIN_S3_VECTORS_BUCKET` |
| `S3VectorsIndexNameOutput` | Storage | `SECOND_BRAIN_S3_VECTORS_INDEX_NAME` |
| `BedrockKnowledgeBaseIdOutput` | Storage (si `enable_knowledge_base`) | `SECOND_BRAIN_BEDROCK_KB_ID` |
| `BedrockGuardrailIdOutput` | Agent | `SECOND_BRAIN_BEDROCK_GUARDRAIL_ID` |
| `BedrockGuardrailVersionOutput` | Agent | `SECOND_BRAIN_BEDROCK_GUARDRAIL_VERSION` |
| `AgentMemoryIdOutput` | AgentCore (si `enable_agentcore`) | `SECOND_BRAIN_AGENTCORE_MEMORY_ID` |

`CorpusBucketNameOutput` y `AgentRoleArnOutput` son informativos — `config.py`
no los lee hoy (el demo carga el corpus desde el filesystem local, no desde
S3; el rol IAM es para cuando el agente corra como servicio, no para el CLI).

**`AgentMemoryIdOutput` todavía NO está en `OUTPUT_TO_ENV_VAR`** (el dict que
`despues-del-deploy.py` de verdad recorre): el `CfnOutput` ya declara el
mapeo en su `description` (ver `stacks/agentcore_stack.py`), pero
`make aws-env`/`python despues-del-deploy.py` hoy no lo escribe solo — es un
gap conocido, no una decisión de diseño. Hasta que se agregue esa entrada,
copiá el valor a mano desde el output del stack (`aws cloudformation
describe-stacks --stack-name SecondBrainAgentCoreStack --query
"Stacks[0].Outputs"`) a `SECOND_BRAIN_AGENTCORE_MEMORY_ID` en tu `.env`. Ver
"Memoria del agente" en [`../README.md`](../README.md) para el resto de la
activación (`SECOND_BRAIN_MEMORY_ENABLED` + `--actor-id`/`--session-id` +
`--agentic`) y cómo se prueba en local sin tocar este recurso.

En vez de copiar esos ARNs a mano en vivo, corré esto después del
`cdk deploy --all`:

```bash
# desde demo/infra/, con las credenciales AWS que usaste para deployar:
python despues-del-deploy.py --region us-west-2

# o, desde demo/, con `make`:
make aws-env
```

Escribe `demo/.env` con `SECOND_BRAIN_MODE=aws` y las variables de la tabla
ya completadas. Después:

```bash
cd demo
SECOND_BRAIN_MODE=aws make demo-aws
```

## Destroy

```bash
cdk destroy --all
```

Todos los recursos con estado tienen `RemovalPolicy.DESTROY`. Una excepción
a tener en cuenta: **si cargaste el corpus completo en el índice de S3
Vectors**, `cdk destroy` puede fallar al borrar `VectorBucket`/`VectorIndex`
por la misma razón que un bucket S3 no vacío falla al borrarse — S3 Vectors
todavía no tiene un equivalente a `autoDeleteObjects`. Si pasa, vaciá el
índice (`aws s3vectors delete-vectors` o recreando el índice) antes de
reintentar el destroy. Ver el docstring de `stacks/storage_stack.py`.

## Costos (ver también las tablas por-stack en cada docstring y el spike §7)

```
Second brain · ~10K docs · desarrollo/demo, sin Neptune

  S3 Vectors (10M vectores, 1M queries)              ~$11
  Bedrock (embeddings + Nova + rerank)               ~$17–35
  Guardrails                                          insignificante
  Knowledge Base (si enable_knowledge_base)          ~$1–3
  AgentCore Runtime+Memory+Gateway (si enable_agentcore) ~$3–5 en desarrollo
  ────────────────────────────────────────────────────────────
  TOTAL desarrollo/demo, todo activado               ~$35–55/mes
```

Verificar vigencia de estos números antes de citarlos en vivo — la tabla
completa con fuente y qué está verificado contra pricing oficial vive en
`SPIKE_COMPATIBILIDAD.md` §7.

## Verificación sin desplegar (`cdk synth`)

```bash
cd demo/infra
python -m venv .venv && source .venv/bin/activate  # o .venv\Scripts\activate en Windows
pip install -r requirements.txt
cdk synth --all
cdk synth --all -c enable_knowledge_base=true -c enable_agentcore=true
```

Sin `GraphStack`, este CDK ya no tiene ninguna VPC — `cdk synth` no dispara
ningún lookup de AZs ni necesita credenciales AWS válidas para sintetizar
limpio.
