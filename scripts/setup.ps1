$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"

Write-Host "DonatiPlan kurulumu basliyor..." -ForegroundColor Cyan

function Assert-LastExitCode {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

function Add-NodePathFromPnpm {
    param([string]$PnpmPath)
    $pnpmDir = Split-Path -Parent $PnpmPath
    $nodeDir = Join-Path (Split-Path -Parent $pnpmDir) "node\bin"
    if ((Get-Command "node.exe" -ErrorAction SilentlyContinue) -eq $null -and (Test-Path -LiteralPath (Join-Path $nodeDir "node.exe"))) {
        $env:PATH = "$nodeDir;$env:PATH"
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        & $pyLauncher.Source -3 -m venv (Join-Path $backend ".venv")
    }
    elseif ($null -ne $python) {
        & $python.Source -m venv (Join-Path $backend ".venv")
    }
    else {
        throw "Python 3.11 veya uzeri bulunamadi."
    }
    Assert-LastExitCode "Python sanal ortami olusturulamadi."
}

Write-Host "Backend paketleri kuruluyor..."
& $venvPython -m pip install --upgrade pip
Assert-LastExitCode "pip guncellemesi basarisiz."
& $venvPython -m pip install --upgrade setuptools wheel
Assert-LastExitCode "setuptools/wheel kurulumu basarisiz."
& $venvPython -m pip install --no-build-isolation -e "$backend[test]"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Backend paket kurulumu pip ile tamamlanamadi. Mevcut ortam dogrulaniyor..."
    & $venvPython -c "import rebarflow, fastapi, openpyxl, ortools, qrcode, reportlab, uvicorn, httpx"
    Assert-LastExitCode "Backend paket kurulumu basarisiz ve mevcut ortam dogrulanamadi."
}

Write-Host "Frontend paketleri kuruluyor..."
Push-Location $frontend
try {
    $pnpm = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
    if ($null -eq $pnpm) {
        throw "pnpm bulunamadi. Node.js ve pnpm kurun."
    }
    Add-NodePathFromPnpm $pnpm.Source
    & $pnpm.Source install
    Assert-LastExitCode "Frontend paket kurulumu basarisiz."
}
finally { Pop-Location }

Write-Host "Kurulum dogrulaniyor..."
& $venvPython -m unittest discover -s (Join-Path $backend "tests") -v
Assert-LastExitCode "Backend testleri basarisiz."
Write-Host "Kurulum tamamlandi. RebarFlow-Baslat.cmd dosyasini calistirin." -ForegroundColor Green
