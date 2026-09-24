param([ValidateRange(1,25)][int]$Limit=10)
$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH=Join-Path $project 'src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -m dragonhydra handoff consume --once --limit $Limit
exit $LASTEXITCODE
