"""GraphStack (opcional): FalkorDB en una EC2 chica, para correr el grafo
100% en AWS.

Por defecto el proyecto NO despliega grafo: FalkorDB corre en Docker local
en los dos modos (`local` y `aws`) y `SECOND_BRAIN_FALKOR_HOST` apunta a
`localhost`. Este stack existe para el caso en que se quiere el turno
completo consumiendo AWS (p.ej. grabar la demo con todo el backend allá):
levanta una `t4g.small` con el MISMO contenedor `falkordb/falkordb` que se
usa en local — motor único, cero cambios de código; apuntar el runtime es
completar `SECOND_BRAIN_FALKOR_HOST` con el output de este stack.

Decisiones que conviene conocer antes de desplegarlo:

- **VPC propia mínima** (1 AZ, solo subnet pública, sin NAT): el stack no
  asume que exista una VPC default en la cuenta (muchas cuentas gobernadas
  la eliminan) y una NAT Gateway costaría más que la instancia entera. La AZ
  se fija a `<región>a` en vez de `max_azs=1` para que `cdk synth` no
  dispare el context lookup de AZs (que exige credenciales activas incluso
  para sintetizar).
- **Sin puerto abierto por default.** FalkorDB corre sin autenticación, así
  que exponer el 6379 a `0.0.0.0/0` sería regalar el grafo (y la instancia,
  vía `EVAL`). El ingreso se habilita SOLO pasando el CIDR propio:
  `-c falkor_allowed_cidr=<tu-ip>/32` (o `SECOND_BRAIN_FALKOR_ALLOWED_CIDR`).
  Sin ese contexto el stack despliega igual pero nadie alcanza el puerto —
  fail-closed, misma política que el gate.
- **Sin SSH ni key pair**: administración por SSM Session Manager
  (`aws ssm start-session --target <instance-id>`), que no requiere ningún
  puerto de entrada.
- **El grafo es efímero a propósito**: no hay EBS extra ni snapshot — si la
  instancia se recicla, `python demo.py ingest` lo reconstruye del corpus en
  segundos. Persistirlo sería pagar durabilidad para datos derivados.
- **Costo**: t4g.small on-demand ≈ USD 0.017/h (~USD 12/mes si se deja
  prendida). El uso esperado es desplegar, grabar/probar y `cdk destroy`.
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from constructs import Construct

FALKOR_PORT = 6379
FALKOR_IMAGE = "falkordb/falkordb:latest"


class GraphStack(Stack):
    """FalkorDB en EC2 (t4g.small, Docker) — opcional, solo bajo bandera."""

    @property
    def availability_zones(self) -> list[str]:
        """Fija la AZ sin consultar AWS: el getter heredado dispara el
        context lookup de AZs en cada `cdk synth` (exige credenciales hasta
        para sintetizar), y para una sola instancia efímera cualquier AZ `a`
        de la región sirve igual.
        """
        return [f"{self.region}a"]

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        allowed_cidr: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "GraphVpc",
            max_azs=1,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="publica", subnet_type=ec2.SubnetType.PUBLIC, cidr_mask=24
                )
            ],
        )

        security_group = ec2.SecurityGroup(
            self,
            "FalkorSecurityGroup",
            vpc=vpc,
            description="FalkorDB de la demo: 6379 solo desde el CIDR permitido",
            allow_all_outbound=True,
        )
        if allowed_cidr:
            security_group.add_ingress_rule(
                ec2.Peer.ipv4(allowed_cidr),
                ec2.Port.tcp(FALKOR_PORT),
                "FalkorDB desde la IP del presentador",
            )

        role = iam.Role(
            self,
            "GraphInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                )
            ],
        )

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "dnf install -y docker",
            "systemctl enable --now docker",
            (
                f"docker run -d --name falkordb --restart unless-stopped "
                f"-p {FALKOR_PORT}:{FALKOR_PORT} {FALKOR_IMAGE}"
            ),
        )

        instance = ec2.Instance(
            self,
            "FalkorInstance",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.SMALL
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(
                cpu_type=ec2.AmazonLinuxCpuType.ARM_64
            ),
            security_group=security_group,
            role=role,
            user_data=user_data,
            associate_public_ip_address=True,
        )

        CfnOutput(
            self,
            "FalkorHostOutput",
            value=instance.instance_public_ip,
            description="Mapea a SECOND_BRAIN_FALKOR_HOST en .env",
        )
        CfnOutput(
            self,
            "FalkorInstanceIdOutput",
            value=instance.instance_id,
            description="Para SSM: aws ssm start-session --target <este id>",
        )
