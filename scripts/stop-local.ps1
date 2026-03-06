$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $repoRoot ".runtime\processes.json"

if (-not (Test-Path $statePath)) {
    Write-Host "No local FraudShield processes are recorded."
    exit 0
}

$state = Get-Content $statePath | ConvertFrom-Json
$stopped = @()
$failed = @()

foreach ($processId in @($state.backend_pid, $state.frontend_pid)) {
    if (-not $processId) {
        continue
    }
    try {
        $process = Get-Process -Id $processId -ErrorAction Stop
        taskkill /PID $processId /T /F | Out-Null
        $stopped += "$($process.ProcessName) ($processId)"
    }
    catch {
        $failed += $processId
    }
}

if ($stopped.Count -gt 0) {
    Write-Host "Stopped:"
    $stopped | ForEach-Object { Write-Host "  $_" }
}

if ($failed.Count -eq 0) {
    Remove-Item $statePath -Force
}
else {
    Write-Host "Some recorded processes could not be stopped. The runtime state file was kept."
    $failed | ForEach-Object { Write-Host "  PID $_" }
}

if ($stopped.Count -eq 0 -and $failed.Count -eq 0) {
    Write-Host "No running recorded processes were found."
}
