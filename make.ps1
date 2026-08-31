# Equivalente PowerShell del Makefile, para el dueño de la demo en Windows
# nativo (sin WSL/Git Bash). Uso: .\make.ps1 <target>, p.ej. `.\make.ps1 up`.

param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "up", "down", "ingest", "demo", "test", "lint", "demo-aws", "web", "web-dev-api",
        "web-dev-ui", "mcp-server", "a2a-demo"
    )]
    [string]$Target = "up"
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$Preguntas = @(
    "¿Quién lidera el Proyecto Beta?",
    "Si modifico la API de core-billing, ¿qué módulos se rompen?",
    "¿Cuál fue la facturación del Q4 2025?",
    "¿Quién es la CTO y cuánto gana?",
    "¿Por qué el frontend de reportes no emite eventos de Amplitude?"
)

function Invoke-Up {
    docker compose up -d --build
}

function Invoke-Down {
    docker compose down
}

function Invoke-Ingest {
    docker compose run --rm demo python demo.py ingest
}

function Invoke-Demo {
    foreach ($pregunta in $Preguntas) {
        Write-Host ""
        Write-Host "=================================================================="
        Write-Host "PREGUNTA: $pregunta"
        Write-Host "=================================================================="
        docker compose run --rm demo python demo.py query --trace $pregunta
        Read-Host "-- Presioná ENTER para la próxima pregunta --" | Out-Null
    }
}

function Invoke-Test {
    docker compose --profile test run --rm test
}

function Invoke-Lint {
    docker compose --profile test run --rm test python -m ruff check src tests demo.py
}

function Invoke-DemoAws {
    if ($env:SECOND_BRAIN_MODE -ne "aws") {
        Write-Error "make.ps1 demo-aws requiere SECOND_BRAIN_MODE=aws explícito. Uso: `$env:SECOND_BRAIN_MODE='aws'; .\make.ps1 demo-aws"
        exit 1
    }
    docker compose --profile aws run --rm demo-aws python demo.py check
}

function Invoke-Web {
    docker compose --profile web up -d --build web
}

function Invoke-WebDevApi {
    python -m uvicorn web.api:app --reload --port 8000
}

function Invoke-WebDevUi {
    Push-Location web/ui
    try {
        pnpm install
        pnpm run dev
    }
    finally {
        Pop-Location
    }
}

function Invoke-McpServer {
    # stdio por default: el mismo transporte que espera un cliente de
    # escritorio como Claude Code (ver el README para el bloque de
    # configuración). No necesita el extra `[a2a]` — `mcp` llega
    # transitivo de `strands-agents` base.
    python demo.py mcp-server
}

function Invoke-A2ADemo {
    # La demo de cierre: DOS procesos locales reales (servidor A2A +
    # "agente de soporte" cliente), 100% offline. Requiere `ingest`
    # corrido antes y el extra `[a2a]` instalado (`pip install -e ".[a2a]"`).
    $proc = Start-Process -FilePath "python" `
        -ArgumentList "demo.py", "a2a-server", "--host", "127.0.0.1", "--port", "9500" `
        -PassThru -NoNewWindow
    try {
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 250
            try {
                Invoke-WebRequest -Uri "http://127.0.0.1:9500/.well-known/agent-card.json" `
                    -UseBasicParsing -TimeoutSec 1 | Out-Null
                $ready = $true
                break
            }
            catch { }
        }
        if (-not $ready) {
            throw "El servidor A2A no respondió a tiempo en http://127.0.0.1:9500."
        }
        python demo.py a2a-client --endpoint http://127.0.0.1:9500
    }
    finally {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

switch ($Target) {
    "up"          { Invoke-Up }
    "down"        { Invoke-Down }
    "ingest"      { Invoke-Ingest }
    "demo"        { Invoke-Demo }
    "test"        { Invoke-Test }
    "lint"        { Invoke-Lint }
    "demo-aws"    { Invoke-DemoAws }
    "web"         { Invoke-Web }
    "web-dev-api" { Invoke-WebDevApi }
    "web-dev-ui"  { Invoke-WebDevUi }
    "mcp-server"  { Invoke-McpServer }
    "a2a-demo"    { Invoke-A2ADemo }
}
