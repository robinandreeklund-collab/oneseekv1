param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8123,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

function Import-DotEnvFile {
    param([string]$Path)
    if (!(Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if ($name) {
            [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

# Load local .env values for Studio defaults (e.g. STUDIO_RECURSION_LIMIT)
# without requiring manual export in the shell.
$RootDotEnv = Join-Path $RepoRoot ".env"
$BackendDotEnv = Join-Path $RepoRoot "surfsense_backend\\.env"
if (Test-Path $RootDotEnv) {
    Import-DotEnvFile -Path $RootDotEnv
} elseif (Test-Path $BackendDotEnv) {
    Import-DotEnvFile -Path $BackendDotEnv
}

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

Write-Host "Starting LangGraph Studio on http://$BindHost`:$Port ..."
if ($env:STUDIO_RECURSION_LIMIT) {
    Write-Host "STUDIO_RECURSION_LIMIT=$($env:STUDIO_RECURSION_LIMIT)"
}
& $LanggraphExe dev --config "langgraph.json" --host $BindHost --port $Port
