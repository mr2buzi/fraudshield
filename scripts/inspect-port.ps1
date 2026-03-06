param(
    [Parameter(Mandatory = $true)]
    [int]$Port
)

$ErrorActionPreference = "Stop"

$matches = netstat -ano -p tcp | Select-String -Pattern "LISTENING\s+(\d+)$" | Where-Object {
    $_.Line -match "127\.0\.0\.1:$Port|0\.0\.0\.0:$Port|\[::\]:$Port"
}

if (-not $matches) {
    Write-Host "No listening TCP process found on port $Port."
    exit 0
}

foreach ($match in $matches) {
    $parts = ($match.Line -replace "\s+", " ").Trim().Split(" ")
    $processId = [int]$parts[-1]
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "Port $Port -> PID $processId ($($process.ProcessName))"
    }
    else {
        Write-Host "Port $Port -> PID $processId"
    }
}
