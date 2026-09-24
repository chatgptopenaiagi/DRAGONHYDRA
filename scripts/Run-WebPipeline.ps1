param([ValidateSet('fetch-demo','process','synthetic-demo','summary')][string]$Command='process')
$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH=Join-Path $project 'src'
$env:PYTHONDONTWRITEBYTECODE='1'
& 'C:\Users\Administrator\anaconda3\envs\codex-pytorch\python.exe' -m dragonhydra.web.pipeline $Command
exit $LASTEXITCODE
