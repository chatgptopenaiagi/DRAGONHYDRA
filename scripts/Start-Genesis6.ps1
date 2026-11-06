#requires -Version 7.0
<# Foreground synthetic research launcher. No installer, service or software setup. #>
[CmdletBinding()]
param(
    [string]$Python = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe',
    [string]$State,
    [ValidateRange(1024,65535)][int]$Port = 19380
)
$ErrorActionPreference='Stop'
$taskSource=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskLane=Split-Path $taskSource -Parent
if((Split-Path $taskLane -Leaf) -cne 'GENESIS-6-REALTIME-INTELLIGENCE'){throw 'GENESIS6_SOURCE_LANE_REQUIRED'}
if($Port -ge 18740 -and $Port -le 18751){throw 'GENESIS6_PORT_NOT_PERMITTED'}
$taskPython=(Resolve-Path -LiteralPath $Python).Path
if(-not(Test-Path -LiteralPath $taskPython -PathType Leaf)){throw 'EXISTING_PYTHON_REQUIRED_NO_INSTALL'}
if(-not $State){$State=Join-Path $taskLane 'runtime\web'}
$taskPreviousPythonPath=$env:PYTHONPATH
try{
    $env:PYTHONPATH=Join-Path $taskSource 'src'
    Write-Host 'SIMULATION ONLY: fictional data, virtual credentials, no external providers.'
    Write-Host 'Virtual pairing token: virtual-session-only-not-a-real-account-1234'
    & $taskPython -B -m dragonhydra.realtime.server --state $State --port $Port
    if($LASTEXITCODE -ne 0){throw ('GENESIS6_SERVER_EXIT_'+$LASTEXITCODE)}
}finally{
    $env:PYTHONPATH=$taskPreviousPythonPath
}
