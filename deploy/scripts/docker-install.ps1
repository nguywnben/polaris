# Guided Docker installation; no Git, Python, Bash or repository clone required.
# Requires Windows PowerShell 5.1+ or PowerShell 7 and a local Linux/amd64 engine.
[CmdletBinding()]
param(
    [switch]$Local,
    [string]$PublicHost = '',
    [switch]$AcceptInsecureHttp,
    [ValidatePattern('\A[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}\z')][string]$Name = 'polaris',
    [ValidateRange(1, 65535)][int]$Port = 4283,
    [ValidatePattern('\A[a-zA-Z0-9][a-zA-Z0-9._/:@-]*\z')][string]$Image = 'nguywnben/polaris:1.0.0',
    [ValidateSet('always', 'never')][string]$Pull = 'always',
    [ValidateRange(1, 900)][int]$WaitSeconds = 120,
    [switch]$Help
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-PolarisDocker {
    param([string[]]$Arguments)
    $output = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker $($Arguments[0]) failed. Check Docker Desktop/Engine and retry; existing data is preserved." }
    return $output
}

function New-PolarisRandomHex {
    param([int]$Bytes)
    $buffer = New-Object byte[] $Bytes
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($buffer) } finally { $random.Dispose() }
    return ([BitConverter]::ToString($buffer)).Replace('-', '').ToLowerInvariant()
}

function Read-PolarisChoice {
    param([string]$Question)
    try { return Read-Host $Question }
    catch { throw 'Interactive input is unavailable. Use -Local, or -PublicHost IP -AcceptInsecureHttp after reviewing the HTTP warning.' }
}

function Install-Polaris {
    if ($Help) {
        Write-Host 'Polaris Docker installer (local Linux/amd64 engine required)'
        Write-Host '.\docker-install.ps1 [-Local | -PublicHost IP -AcceptInsecureHttp]'
        Write-Host 'Options: -Name NAME -Port PORT -Image IMAGE -Pull always|never -WaitSeconds N'
        Write-Host 'Existing containers/volumes are never replaced. This is not an updater.'
        return
    }
    if ($Local -and $PublicHost) { throw 'Choose only one access mode.' }
    if ($PublicHost -and $PublicHost -notmatch '\A[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?\z') {
        throw 'Enter an IPv4 address or hostname only (no scheme, port or path).'
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop from https://docs.docker.com/desktop/setup/install/windows-install/ and start its Linux engine, then rerun this installer. No system settings were changed.'
    }
    $engine = (Invoke-PolarisDocker @('info', '--format', '{{.OSType}}/{{.Architecture}}') | Out-String).Trim()
    if ($engine -notin @('linux/x86_64', 'linux/amd64')) {
        throw "Unsupported engine: $engine. This release requires Linux amd64; native ARM64 is not published. No resources created."
    }
    $endpoint = $env:DOCKER_HOST
    if ($env:DOCKER_CONTEXT -or -not $endpoint) {
        $endpoint = (Invoke-PolarisDocker @('context', 'inspect', '--format', '{{.Endpoints.docker.Host}}') | Out-String).Trim()
    }
    if ($endpoint -notmatch '^(unix|npipe)://') { throw 'Use a local Docker daemon, not a remote Docker context.' }
    if (-not $Local -and -not $PublicHost) {
        $choice = Read-PolarisChoice 'Where will you use Polaris? [1] This computer (default) [2] VPS/public IP'
        switch ($choice) {
            '' { $Local = $true }
            '1' { $Local = $true }
            '2' { $PublicHost = Read-PolarisChoice 'Public IPv4 address or hostname (no scheme or port)' }
            default { throw 'Choose 1 or 2, then run the installer again.' }
        }
    }
    $bind = '127.0.0.1'
    $address = '127.0.0.1'
    if (-not $Local) {
        if ($PublicHost -notmatch '\A[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?\z') {
            throw 'Enter an IPv4 address or hostname only.'
        }
        Write-Warning 'HTTP does not encrypt passwords, setup codes, sessions or API traffic. Anyone intercepting the connection can read them. HTTPS is recommended.'
        if (-not $AcceptInsecureHttp -and (Read-PolarisChoice 'Allow public HTTP anyway? Type YES to accept') -cne 'YES') {
            throw 'HTTP access declined. No container created.'
        }
        $bind = '0.0.0.0'
        $address = $PublicHost
    }
    $containers = @(Invoke-PolarisDocker @('container', 'ls', '--all', '--format', '{{.Names}}'))
    if ($containers -contains $Name) {
        throw "Container $Name already exists and is preserved. This installer is not an updater. Inspect: docker logs --tail 50 $Name. See docs/docker-maintenance.md."
    }
    $volumes = @(Invoke-PolarisDocker @('volume', 'ls', '--format', '{{.Name}}'))
    if ($volumes -contains "$Name-data") {
        throw "Volume $Name-data already exists and is preserved. Use the backup/recovery guide or a different -Name for a separate installation."
    }
    Write-Host "Preparing $Image..."
    if ($Pull -eq 'always') { Invoke-PolarisDocker @('pull', $Image) | Out-Host }
    $imageId = (Invoke-PolarisDocker @('image', 'inspect', '--format', '{{.Id}}', $Image) | Out-String).Trim()
    if (-not $imageId) { throw 'Image is unavailable; no data volume created.' }
    # Single quotes inside Python survive Windows PowerShell's native argument passing.
    $probe = "from pathlib import Path; raise SystemExit(0 if 'SETUP_ALLOW_INSECURE_HTTP' in Path('core/panel/setup_preflight.py').read_text() else 1)"
    Invoke-PolarisDocker @('run', '--rm', '--network', 'none', '--read-only', '--entrypoint', 'python', '--workdir', '/app/backend', $imageId, '-c', $probe) | Out-Null
    $token = New-PolarisRandomHex 32
    $installId = New-PolarisRandomHex 16
    $priorToken = [Environment]::GetEnvironmentVariable('SETUP_TOKEN', 'Process')
    $resourcesStarted = $false
    $containerCreated = $false
    try {
        # Docker inherits the secret from this process, never from its argument list.
        $env:SETUP_TOKEN = $token
        Invoke-PolarisDocker @('volume', 'create', '--label', 'io.polaris.install=guided', '--label', "io.polaris.install-id=$installId", "$Name-data") | Out-Null
        $resourcesStarted = $true
        $volume = @(Invoke-PolarisDocker @('volume', 'inspect', "$Name-data") | ConvertFrom-Json)[0]
        if ($volume.Labels.'io.polaris.install-id' -cne $installId) {
            throw 'Volume ownership changed during installation. Data is preserved; no application started.'
        }
        $create = @(
            'create', '--name', $Name, '--label', 'io.polaris.install=guided',
            '--restart', 'unless-stopped', '--init', '--read-only', '--stop-timeout', '45',
            '--publish', "${bind}:${Port}:4283", '--env', 'SETUP_TOKEN',
            '--env', 'SETUP_ALLOW_INSECURE_HTTP=true', '--env', 'HOST=0.0.0.0', '--env', 'PORT=4283',
            '--env', 'WORKERS=1', '--env', 'POLARIS_RUNTIME_MODE=standalone', '--env', 'POLARIS_REPLICA_COUNT=1',
            '--mount', "type=volume,src=$Name-data,dst=/app/backend/data", '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
            '--security-opt', 'no-new-privileges:true', '--log-driver', 'json-file',
            '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3', $imageId
        )
        Invoke-PolarisDocker $create | Out-Null
        $containerCreated = $true
        Invoke-PolarisDocker @('start', $Name) | Out-Null
        Write-Host "Waiting for readiness (up to $WaitSeconds seconds)..."
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while ($timer.Elapsed.TotalSeconds -lt $WaitSeconds) {
            $health = (Invoke-PolarisDocker @('inspect', '--format', '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}', $Name) | Out-String).Trim()
            if ($health -eq 'healthy') {
                Write-Host "Ready: http://${address}:$Port"
                Write-Host "Setup code: $token"
                Write-Host 'Open the address, paste the setup code, and create your owner password.'
                Write-Host 'Keep this code private; it is not your login password. Do not share terminal screenshots.'
                Write-Host "Data volume: $Name-data. Docker must start on host boot for automatic recovery."
                if (-not $Local) { Write-Host "If unreachable, allow TCP $Port in your cloud/host firewall. No firewall rules were changed." }
                return
            }
            if ($health -in @('unhealthy', 'missing')) { throw 'Container did not become ready.' }
            Start-Sleep -Seconds 1
        }
        throw 'Timed out waiting for readiness.'
    }
    catch {
        if ($containerCreated) {
            Write-Warning "Existing resources are preserved. Inspect: docker logs --tail 50 $Name. After resolving the issue: docker start $Name. See docs/docker-maintenance.md; do not delete the data volume."
        } elseif ($resourcesStarted) {
            Write-Warning "Volume $Name-data is preserved; this installer did not create an application container. See volume recovery in docs/docker-maintenance.md. Do not start an existing container or delete the volume."
        }
        throw
    }
    finally { [Environment]::SetEnvironmentVariable('SETUP_TOKEN', $priorToken, 'Process') }
}

# Keep execution last: the complete script must download/parse before installation.
Install-Polaris
