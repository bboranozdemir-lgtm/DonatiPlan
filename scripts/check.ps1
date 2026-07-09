$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Backend sanal ortami yok. Once RebarFlow-Kur.cmd calistirin."
}

& $python -m unittest discover -s (Join-Path $backend "tests") -v
if ($LASTEXITCODE -ne 0) { throw "Backend testleri basarisiz." }

$pnpm = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
if ($null -eq $pnpm) {
    throw "pnpm bulunamadi."
}
Push-Location $frontend
try { & $pnpm.Source run build }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "Frontend derlemesi basarisiz." }

Write-Host "Tum kontroller basarili." -ForegroundColor Green
