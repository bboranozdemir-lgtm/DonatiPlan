$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"
$vite = Join-Path $frontendDir "node_modules\vite\bin\vite.js"

function Test-LocalPort {
    param([int]$Port)

    try {
        $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        return $null -ne $connection
    }
    catch {
        return $false
    }
}

function Wait-LocalPort {
    param(
        [int]$Port,
        [int]$Seconds = 20
    )

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-LocalPort -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 400
    }
    return $false
}

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python sanal ortami bulunamadi: $python"
}

if (-not (Test-Path -LiteralPath $vite)) {
    throw "Frontend paketleri bulunamadi. Once frontend klasorunde 'pnpm install' calistirin."
}

$pnpm = Get-Command "pnpm.cmd" -ErrorAction SilentlyContinue
if ($null -eq $pnpm) {
    throw "pnpm bulunamadi. Node.js ve pnpm kurulu olmali."
}

Write-Host "DonatiPlan baslatiliyor..." -ForegroundColor Cyan

if (-not (Test-LocalPort -Port 8000)) {
    $apiArgs = @(
        "-m", "uvicorn",
        "rebarflow.api:app",
        "--app-dir", "src",
        "--host", "127.0.0.1",
        "--port", "8000",
        "--reload"
    )
    Start-Process `
        -FilePath $python `
        -ArgumentList $apiArgs `
        -WorkingDirectory $backendDir `
        -WindowStyle Minimized | Out-Null
    Write-Host "  API baslatildi (port 8000)."
}
else {
    Write-Host "  API zaten calisiyor (port 8000)."
}

if (-not (Test-LocalPort -Port 5173)) {
    Start-Process `
        -FilePath $pnpm.Source `
        -ArgumentList @("exec", "vite", "--host", "127.0.0.1", "--port", "5173") `
        -WorkingDirectory $frontendDir `
        -WindowStyle Minimized | Out-Null
    Write-Host "  Web arayuzu baslatildi (port 5173)."
}
else {
    Write-Host "  Web arayuzu zaten calisiyor (port 5173)."
}

$apiReady = Wait-LocalPort -Port 8000
$uiReady = Wait-LocalPort -Port 5173

if (-not $apiReady) {
    throw "API 20 saniye icinde hazir olmadi. Acilan API penceresindeki hatayi kontrol edin."
}
if (-not $uiReady) {
    throw "Web arayuzu 20 saniye icinde hazir olmadi. Acilan UI penceresindeki hatayi kontrol edin."
}

Write-Host "DonatiPlan hazir. Tarayici aciliyor..." -ForegroundColor Green
Start-Process "http://127.0.0.1:5173" | Out-Null
