param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8123,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$VenvDir = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\\python.exe"
$LanggraphExe = Join-Path $VenvDir "Scripts\\langgraph.exe"

if (!(Test-Path $VenvPython)) {
    Write-Host "Creating .venv with Python 3.12..."
    py -3.12 -m venv .venv
}

Write-Host "Using Python:" $VenvPython
& $VenvPython -m pip install --upgrade pip setuptools wheel

if (-not $SkipInstall) {
    Write-Host "Installing backend dependencies (editable)..."
    & $VenvPython -m pip install -e ".\\surfsense_backend"
    Write-Host "Installing LangGraph CLI..."
    & $VenvPython -m pip install "langgraph-cli[inmem]"
}

if (!(Test-Path $LanggraphExe)) {
    throw "Could not find langgraph.exe in .venv. Run again without -SkipInstall."
}

Write-Host "Starting LangGraph Studio on http://$Host`:$Port ..."
& $LanggraphExe dev --config "langgraph.json" --host $Host --port $Port
