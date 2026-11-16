# E.D.I.T.H. Brain Core Windows Service Startup Script (PowerShell)
# Binds to loopback interface 127.0.0.1 for local trust boundary enforcement.

param (
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

# Ensure script runs from project root
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " E.D.I.T.H. Brain Core - Starting Local Intelligence Service" -ForegroundColor Cyan
Write-Host " Host: $HostAddress | Port: $Port" -ForegroundColor Cyan
Write-Host " Directory: $ProjectRoot" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Verify Python installation
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Runtime: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Error "Python 3.13+ is required but was not found on PATH."
    exit 1
}

# Add src directory to PYTHONPATH
$env:PYTHONPATH = (Join-Path $ProjectRoot "src")

# Build uvicorn command
$uvicornArgs = @(
    "-m", "uvicorn",
    "edith_brain.api.app:create_app",
    "--factory",
    "--host", $HostAddress,
    "--port", $Port
)

if ($Reload) {
    $uvicornArgs += "--reload"
}

Write-Host "Executing: python $($uvicornArgs -join ' ')" -ForegroundColor Yellow
& python $uvicornArgs
