"""ObservabilityStack: log group del agente, destino OTel del Runtime de
AgentCore (bajo `enable_agentcore`), y la alarma de AWS Budgets.

El plan de la charla la exige explícitamente en el cierre y en el checklist
del speaker ("AWS Budgets con alarma configurada — mencionarlo en el slide
30"). `CfnBudget` es el único recurso de Budgets: no tiene L2 en
`aws-cdk-lib` todavía.

`budget_email` llega por contexto de CDK (`-c budget_alert_email=...`) o
variable de entorno `SECOND_BRAIN_BUDGET_EMAIL` — ver `app.py` y el README.
Si queda vacío, el budget igual se crea (protección aunque nadie lo mire),
pero sin suscriptor de notificación: `cdk deploy` no falla, pero el README
insiste en pasar el email antes de dejar esto corriendo sin supervisión.

## OTel → CloudWatch (Strands emite trazas nativas, verificado en el spike §3)

Strands **no necesita ningún SDK de tracing propio**: ya emite OpenTelemetry
sobre el protocolo OTLP estándar (`strands-agents[otel]`). Lo que este stack
declara es el **destino**: un log group dedicado para las trazas/logs de
aplicación del Runtime (`AgentCoreRuntimeLogGroup`, referenciado por
`AgentCoreStack.runtime.logging_configs`) y los permisos de X-Ray que ese
Runtime necesita para escribir spans (declarados en el `execution_role` de
`AgentCoreStack`, no acá, porque ese rol vive en el otro stack).

**Variables de entorno que debe tener el proceso del Runtime** (ya cableadas
como `environment_variables` de `bac.Runtime` en `AgentCoreStack`, repetidas
acá para que quede documentado junto al resto de observability):

```
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_TRACES_EXPORTER=otlp
OTEL_PYTHON_DISTRO=aws_distro
OTEL_PYTHON_CONFIGURATOR=aws_configurator
OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental,gen_ai_tool_definitions
OTEL_SERVICE_NAME=second-brain-agent
```

`aws_distro`/`aws_configurator` son el ADOT Python Distro (`opentelemetry-distro`
+ `aws-opentelemetry-distro`): firma las exportaciones OTLP con SigV4 hacia
el endpoint OTLP de X-Ray/CloudWatch GenAI Observability, algo que un
exporter OTLP genérico no hace solo. **NO VERIFICADO en el spike** (no se
generaron spans reales — prohibido llamar a AWS): la URL exacta del
endpoint OTLP regional y el nombre exacto del paquete ADOT Python no se
confirmaron contra documentación oficial en esta pasada. Confirmarlo con la
skill `aws-observability` antes de la charla, no asumir el string de arriba
como definitivo.

`tracing_enabled=True` en `bac.Runtime` (visto en su firma real) es la
bandera nativa de CDK para que el propio Runtime habilite X-Ray — belt and
suspenders con las variables OTel de Strands, no un reemplazo.

No se declara un dashboard de CloudWatch ni un `CfnResourcePolicy` de
"GenAI Observability" aparte: a la fecha de este repo esa vista es un panel
gestionado por consola (Bedrock > AgentCore > Observability) sobre los
mismos spans de X-Ray, no un recurso de CloudFormation propio que declarar.

## Costos

Log groups: `logs:PutLogEvents` no tiene cargo por debajo de los free tier
de CloudWatch para el volumen de una demo; storage de logs
$0.03/GB (Standard) — insignificante a esta escala. X-Ray: $5/millón de
traces registrados después de las primeras 100,000/mes gratis — la demo no
se acerca a ese volumen.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_logs as logs
from constructs import Construct

MONTHLY_BUDGET_LIMIT_USD = 70.0  # ver la tabla de costos del plan: ~$45-70/mes en modo demo


class ObservabilityStack(Stack):
    """Log group del agente + destino OTel del Runtime + alarma de AWS Budgets."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        budget_alert_email: str = "",
        enable_agentcore: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.agent_log_group = logs.LogGroup(
            self,
            "AgentLogGroup",
            log_group_name="/second-brain/agent",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.runtime_log_group = None
        if enable_agentcore:
            self.runtime_log_group = logs.LogGroup(
                self,
                "AgentCoreRuntimeLogGroup",
                log_group_name="/second-brain/agentcore-runtime",
                retention=logs.RetentionDays.TWO_WEEKS,
                removal_policy=RemovalPolicy.DESTROY,
            )

        subscribers = (
            [
                budgets.CfnBudget.SubscriberProperty(
                    address=budget_alert_email,
                    subscription_type="EMAIL",
                )
            ]
            if budget_alert_email
            else []
        )

        budgets.CfnBudget(
            self,
            "SecondBrainBudget",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=MONTHLY_BUDGET_LIMIT_USD,
                    unit="USD",
                ),
                budget_name="second-brain-demo",
            ),
            notifications_with_subscribers=(
                [
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            notification_type="ACTUAL",
                            comparison_operator="GREATER_THAN",
                            threshold=80,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=subscribers,
                    )
                ]
                if subscribers
                else []
            ),
        )

        CfnOutput(
            self,
            "AgentLogGroupNameOutput",
            value=self.agent_log_group.log_group_name,
            description="Informativo — no lo lee config.py",
        )
        if self.runtime_log_group is not None:
            CfnOutput(
                self,
                "AgentCoreRuntimeLogGroupNameOutput",
                value=self.runtime_log_group.log_group_name,
                description="Destino de application logs del Runtime de AgentCore "
                "(AgentCoreStack.runtime.logging_configs).",
            )
        CfnOutput(
            self,
            "BudgetAlertStatusOutput",
            value=(
                f"Alarma activa, notificando a {budget_alert_email}"
                if budget_alert_email
                else "Budget creado SIN suscriptor de email — pasar "
                "-c budget_alert_email=tu@correo antes de dejarlo corriendo solo"
            ),
        )
