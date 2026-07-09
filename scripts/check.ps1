$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"
$bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$bundledNodeDir = Split-Path -Parent $bundledNode

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend sanal ortami yok. Once RebarFlow-Kur.cmd calistirin."
}

if (Test-Path -LiteralPath $bundledNode) {
    $env:PATH = "$bundledNodeDir;$env:PATH"
}

& $python -m unittest discover -s (Join-Path $backend "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Backend testleri basarisiz." }

$pnpm = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
if ($null -eq $pnpm) {
    $pnpmJs = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs"
    if (-not (Test-Path $bundledNode) -or -not (Test-Path $pnpmJs)) {
        throw "pnpm bulunamadi."
    }
    Push-Location $frontend
    try { & $bundledNode $pnpmJs run build }
    finally { Pop-Location }
}
else {
    Push-Location $frontend
    try { & $pnpm.Source run build }
    finally { Pop-Location }
}
if ($LASTEXITCODE -ne 0) { throw "Frontend derlemesi basarisiz." }

Write-Host "Tum kontroller basarili." -ForegroundColor Green
