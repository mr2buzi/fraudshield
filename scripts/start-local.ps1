param(
    [int]$PreferredBackendPort = 8010,
    [int]$PreferredFrontendPort = 4173
)

$ErrorActionPreference = "Stop"

function Get-FreePort {
    param([int]$StartPort)

    for ($port = $StartPort; $port -lt ($StartPort + 100); $port++) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
        try {
            $listener.Start()
            $listener.Stop()
            return $port
        }
        catch {
            if ($listener) {
                try { $listener.Stop() } catch {}
            }
        }
    }

    throw "Unable to find a free port starting from $StartPort."
}

function Wait-ForUrl {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing | Out-Null
            return $true
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    return $false
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeDir = Join-Path $repoRoot ".runtime"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$backendPort = Get-FreePort -StartPort $PreferredBackendPort
$frontendPort = Get-FreePort -StartPort $PreferredFrontendPort
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$backendLog = Join-Path $runtimeDir "backend.out.log"
$backendErrorLog = Join-Path $runtimeDir "backend.err.log"
$frontendLog = Join-Path $runtimeDir "frontend.out.log"
$frontendErrorLog = Join-Path $runtimeDir "frontend.err.log"
$statePath = Join-Path $runtimeDir "processes.json"

if (Test-Path $statePath) {
    Write-Host "Existing runtime state found. Stopping previous local processes first..."
    & (Join-Path $PSScriptRoot "stop-local.ps1")
}

$backendCommand = "Set-Location '$backendDir'; python -m uvicorn app.main:app --host 127.0.0.1 --port $backendPort"
$frontendCommand = "Set-Location '$frontendDir'; `$env:VITE_API_BASE_URL='http://127.0.0.1:$backendPort'; npm run dev -- --host=127.0.0.1 --port=$frontendPort"

$backendProcess = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoLogo", "-NoProfile", "-Command", $backendCommand `
    -RedirectStandardOutput $backendLog `
    -RedirectStandardError $backendErrorLog `
    -WindowStyle Hidden `
    -PassThru

$frontendProcess = Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoLogo", "-NoProfile", "-Command", $frontendCommand `
    -RedirectStandardOutput $frontendLog `
    -RedirectStandardError $frontendErrorLog `
    -WindowStyle Hidden `
    -PassThru

$state = @{
    backend_pid = $backendProcess.Id
    frontend_pid = $frontendProcess.Id
    backend_port = $backendPort
    frontend_port = $frontendPort
    started_at = (Get-Date).ToString("o")
    backend_log = $backendLog
    backend_error_log = $backendErrorLog
    frontend_log = $frontendLog
    frontend_error_log = $frontendErrorLog
}
$state | ConvertTo-Json | Set-Content -Path $statePath

$backendReady = Wait-ForUrl -Url "http://127.0.0.1:$backendPort/api/v1/health"
$frontendReady = Wait-ForUrl -Url "http://127.0.0.1:$frontendPort"

if (-not $backendReady -or -not $frontendReady) {
    & (Join-Path $PSScriptRoot "stop-local.ps1") | Out-Null
    Write-Host "Startup failed. Recent logs:"
    if (Test-Path $backendLog) {
        Write-Host "`n[backend.out.log]"
        Get-Content $backendLog -Tail 20
    }
    if (Test-Path $backendErrorLog) {
        Write-Host "`n[backend.err.log]"
        Get-Content $backendErrorLog -Tail 20
    }
    if (Test-Path $frontendLog) {
        Write-Host "`n[frontend.out.log]"
        Get-Content $frontendLog -Tail 20
    }
    if (Test-Path $frontendErrorLog) {
        Write-Host "`n[frontend.err.log]"
        Get-Content $frontendErrorLog -Tail 20
    }
    throw "FraudShield did not start cleanly."
}

Write-Host ""
Write-Host "FraudShield is running."
Write-Host "Frontend: http://127.0.0.1:$frontendPort"
Write-Host "Backend:  http://127.0.0.1:$backendPort"
Write-Host "Health:   http://127.0.0.1:$backendPort/api/v1/health"
Write-Host ""
Write-Host "Logs:"
Write-Host "  $backendLog"
Write-Host "  $backendErrorLog"
Write-Host "  $frontendLog"
Write-Host "  $frontendErrorLog"
Write-Host ""
Write-Host "Stop with: .\scripts\stop-local.ps1"
