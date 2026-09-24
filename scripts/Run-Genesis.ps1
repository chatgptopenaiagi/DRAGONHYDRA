param(
    [string]$Python = 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe'
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$checkpointName = 'genesis-' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)
$checkpoint = Join-Path $project ('runtime\checkpoints\' + $checkpointName)
New-Item -ItemType Directory -Path $checkpoint -ErrorAction Stop | Out-Null
$env:PYTHONPATH = Join-Path $project 'src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP = Join-Path $project 'runtime\tmp'
$env:TMP = $env:TEMP
$stages = @()
Push-Location $project
try {
    foreach ($stage in @(@{name='diagnostics';file='diagnostics.json'}, @{name='probe';file='bridge.json'}, @{name='inventory';file='inventory.json'})) {
        & $Python -m dragonhydra $stage.name --output (Join-Path $checkpoint $stage.file) 2>&1 | Tee-Object -FilePath (Join-Path $checkpoint ($stage.name + '.log'))
        $stages += [ordered]@{name=$stage.name;exit_code=$LASTEXITCODE}
    }
    & $Python (Join-Path $PSScriptRoot 'run_tests.py') --output (Join-Path $checkpoint 'tests.json') 2>&1 | Tee-Object -FilePath (Join-Path $checkpoint 'tests.log')
    $stages += [ordered]@{name='tests';exit_code=$LASTEXITCODE}
} finally {
    Pop-Location
    [ordered]@{checkpoint=$checkpointName;finished_utc=(Get-Date).ToUniversalTime().ToString('o');stages=$stages} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $checkpoint 'checkpoint.json') -Encoding utf8
}
Write-Output ('CHECKPOINT=' + $checkpoint)
if (@($stages | Where-Object {$_.exit_code -ne 0}).Count -gt 0) { exit 1 }
