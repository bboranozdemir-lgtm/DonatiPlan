$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$venvPython = Join-Path $backend ".venv\Scripts\python.exe"
$bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
$bundledPnpm = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\pnpm\bin\pnpm.mjs"

Write-Host "DonatiPlan kurulumu basliyor..." -ForegroundColor Cyan

function Assert-LastExitCode {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -eq $python -and (Test-Path -LiteralPath $bundledPython)) {
        $pythonPath = $bundledPython
    }
    elseif ($null -ne $python) {
        $pythonPath = $python.Source
    }
    else {
        throw "Python 3.11 veya uzeri bulunamadi."
    }
    & $pythonPath -m venv (Join-Path $backend ".venv")
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
    if ((Test-Path -LiteralPath $bundledNode) -and (Test-Path -LiteralPath $bundledPnpm)) {
        $nodeDir = Split-Path -Parent $bundledNode
        $env:PATH = "$nodeDir;$env:PATH"
        & $bundledNode $bundledPnpm install
        Assert-LastExitCode "Frontend paket kurulumu basarisiz."
    }
    else {
        $pnpm = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
        if ($null -eq $pnpm) {
            throw "pnpm bulunamadi. Node.js ve pnpm kurun."
        }
        & $pnpm.Source install
        Assert-LastExitCode "Frontend paket kurulumu basarisiz."
    }
}
finally { Pop-Location }

Write-Host "Kurulum dogrulaniyor..."
& $venvPython -m unittest discover -s (Join-Path $backend "tests") -v
Assert-LastExitCode "Backend testleri basarisiz."
Write-Host "Kurulum tamamlandi. RebarFlow-Baslat.cmd dosyasini calistirin." -ForegroundColor Green
