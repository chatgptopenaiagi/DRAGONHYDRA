#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('status','run-stage','validate','publish','verify-downloads')][string]$Action,
    [string]$Tag='v0.4.0-alpha.1',
    [Parameter(ValueFromRemainingArguments)][string[]]$StageArguments
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$python=Join-Path $projectRoot 'runtime\server-env\Scripts\python.exe'
$arguments=@('-B',(Join-Path $PSScriptRoot 'release_coordinator.py'),'--root',$projectRoot,'--tag',$Tag,$Action)+$StageArguments
& $python @arguments
if($LASTEXITCODE -ne 0){throw "Release stage $Action failed with exit code $LASTEXITCODE"}
