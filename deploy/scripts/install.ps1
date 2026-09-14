# Compatibility path for native Python installs. Canonical production: docs/installation.md.
$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Write-Fail {
    param([string]$Message)
    Write-Error "[ERROR] $Message"
    exit 1
}

if (-not (Get-Command scoop -ErrorAction SilentlyContinue)) {
    Write-Info "Installing Scoop for the current user..."
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
    Invoke-RestMethod get.scoop.sh | Invoke-Expression
}

foreach ($tool in @("git", "uv")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Info "Installing $tool..."
        scoop install $tool
    }
}

$ProjectDir = if ($env:PROJECT_DIR) { $env:PROJECT_DIR } else { "polaris" }
$RepositoryUrl = $env:REPOSITORY_URL

if (Test-Path -LiteralPath "./backend/main.py") {
    Write-Info "Using current project checkout."
}
elseif (Test-Path -LiteralPath (Join-Path $ProjectDir "backend/main.py")) {
    Set-Location $ProjectDir
}
else {
    if (-not $RepositoryUrl) {
        Write-Fail "Set REPOSITORY_URL or run this script from the project root."
    }
    Write-Info "Cloning repository..."
    git clone $RepositoryUrl $ProjectDir
    Set-Location $ProjectDir
}

if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
    Write-Info "Creating virtual environment..."
    uv venv
}

Write-Info "Installing Python dependencies..."
uv pip install --require-hashes -r requirements.lock

Write-Info "Starting Polaris..."
& ".venv/Scripts/python.exe" "backend/main.py"
