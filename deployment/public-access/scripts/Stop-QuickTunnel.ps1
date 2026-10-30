#requires -Version 7.0
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$deploymentRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolRoot=Join-Path $deploymentRoot 'cloudflare'
$stateFile=Join-Path $toolRoot 'quick-tunnel.json'
if(-not(Test-Path -LiteralPath $stateFile)){return}
$state=Get-Content -LiteralPath $stateFile -Raw|ConvertFrom-Json
$binary=Join-Path $toolRoot 'bin\cloudflared.exe'
$config=Join-Path $toolRoot 'quick-tunnel.yml'
$proc=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$state.pid)"
if($proc){
    if($proc.ExecutablePath -ne $binary -or -not $proc.CommandLine.Contains($config) -or -not $proc.CommandLine.Contains([string]$state.target)){throw 'Tunnel PID is not the verified project Quick Tunnel. No process was stopped.'}
    Stop-Process -Id $proc.ProcessId -ErrorAction Stop
}
$state.status='stopped'
$state|Add-Member -NotePropertyName stopped_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $stateFile -Encoding utf8
$state|ConvertTo-Json -Depth 6

