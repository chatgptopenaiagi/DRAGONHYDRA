#requires -Version 7.0
[CmdletBinding()]
param([string]$StateDirectory)
$ErrorActionPreference='Stop'
$deploymentRoot=Split-Path $PSScriptRoot -Parent
if(-not $StateDirectory){$StateDirectory=if(Test-Path -LiteralPath (Join-Path $deploymentRoot 'evidence\gateway-process.json')){Join-Path $deploymentRoot 'evidence'}else{Join-Path $deploymentRoot 'state'}}
$receipt=Join-Path ([IO.Path]::GetFullPath($StateDirectory)) 'gateway-process.json'
if(-not(Test-Path -LiteralPath $receipt)){return}
$record=Get-Content -LiteralPath $receipt -Raw|ConvertFrom-Json
$owned=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$record.pid)"
$script=Join-Path $deploymentRoot 'reverse-proxy\gateway.py'
if($owned){
    if(-not $owned.CommandLine.Contains($script) -or -not $owned.CommandLine.Contains([string]$record.config)){throw 'PID ownership changed; refusing to stop another process.'}
    if($record.state -and -not $owned.CommandLine.Contains([string]$record.state)){throw 'PID does not belong to the selected gateway state.'}
    Stop-Process -Id $owned.ProcessId -ErrorAction Stop
}
Remove-Item -LiteralPath $receipt
@{stopped_gateway=$record.pid;application_services_untouched=$true;state=$StateDirectory}|ConvertTo-Json -Compress
