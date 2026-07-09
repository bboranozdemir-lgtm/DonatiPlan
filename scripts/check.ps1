$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend sanal ortami yok. Once RebarFlow-Kur.cmd calistirin."
}

function Add-NodePathFromPnpm {
    param([string]$PnpmPath)
    $pnpmDir = Split-Path -Parent $PnpmPath
    $nodeDir = Join-Path (Split-Path -Parent $pnpmDir) "node\bin"
    if ((Get-Command "node.exe" -ErrorAction SilentlyContinue) -eq $null -and (Test-Path -LiteralPath (Join-Path $nodeDir "node.exe"))) {
        $env:PATH = "$nodeDir;$env:PATH"
    }
}

& $python -m unittest discover -s (Join-Path $backend "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Backend testleri basarisiz." }

$pnpm = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
if ($null -eq $pnpm) {
    throw "pnpm bulunamadi."
}
Add-NodePathFromPnpm $pnpm.Source
Push-Location $frontend
try { & $pnpm.Source run build }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "Frontend derlemesi basarisiz." }

Write-Host "Tum kontroller basarili." -ForegroundColor Green
