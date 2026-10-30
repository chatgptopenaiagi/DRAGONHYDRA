#requires -Version 7.0
[CmdletBinding()]
param([ValidateRange(0,65535)][int]$Port=18734,[string]$ConfigFile,[string]$Python,[string]$StateDirectory)
$ErrorActionPreference='Stop'
$deploymentRoot=Split-Path $PSScriptRoot -Parent
$projectRoot=Split-Path (Split-Path $deploymentRoot -Parent) -Parent
if(-not $ConfigFile){$ConfigFile=Join-Path $deploymentRoot 'gateway.json'}
$ConfigFile=[IO.Path]::GetFullPath($ConfigFile)
if(-not(Test-Path -LiteralPath $ConfigFile -PathType Leaf)){throw 'Copy gateway.example.json to gateway.json and set the existing server state and Joomla origin.'}
if(-not $StateDirectory){$StateDirectory=if(Test-Path -LiteralPath (Join-Path $deploymentRoot 'evidence\gateway-process.json')){Join-Path $deploymentRoot 'evidence'}else{Join-Path $deploymentRoot 'state'}}
$StateDirectory=[IO.Path]::GetFullPath($StateDirectory)
New-Item -ItemType Directory -Force -Path $StateDirectory|Out-Null
if(-not $Python){$Python=$env:DRAGONHYDRA_PYTHON}
if(-not $Python){
    $candidates=@((Join-Path $deploymentRoot '.venv\Scripts\python.exe'),(Join-Path $projectRoot 'runtime\server-env\Scripts\python.exe'))
    $Python=$candidates|Where-Object{Test-Path -LiteralPath $_ -PathType Leaf}|Select-Object -First 1
}
if(-not $Python -or -not(Test-Path -LiteralPath $Python -PathType Leaf)){throw 'Set -Python to the private Python interpreter with requirements.txt installed, or create .venv beside this package.'}
$Python=[IO.Path]::GetFullPath($Python)
$script=Join-Path $deploymentRoot 'reverse-proxy\gateway.py'
$receipt=Join-Path $StateDirectory 'gateway-process.json'
function Owned-Gateway {
    if(-not(Test-Path -LiteralPath $receipt)){return $null}
    $record=Get-Content -LiteralPath $receipt -Raw|ConvertFrom-Json
    if([IO.Path]::GetFullPath([string]$record.config) -ne $ConfigFile){throw 'This state belongs to a gateway using another configuration. Choose a separate StateDirectory.'}
    $owned=Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$record.pid)"
    if(-not $owned){return $null}
    if(-not $owned.CommandLine.Contains($script) -or -not $owned.CommandLine.Contains($ConfigFile)){throw 'Recorded PID ownership changed; no process was changed.'}
    try{$health=Invoke-RestMethod -Uri "http://127.0.0.1:$($record.port)/public-health" -TimeoutSec 3}catch{return $null}
    if($health.status -eq 'ready'){return $record}
    return $null
}
$old=Owned-Gateway
if($old){@{pid=$old.pid;url="http://127.0.0.1:$($old.port)";reused=$true;state=$StateDirectory}|ConvertTo-Json -Compress;return}
if($Port -gt 0 -and (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)){throw "Public gateway port $Port is already occupied. No process was stopped."}
$arguments=@('-B',('"'+$script+'"'),'--config',('"'+$ConfigFile+'"'),'--port',[string]$Port,'--state',('"'+$StateDirectory+'"'))
$process=Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $deploymentRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $StateDirectory 'gateway.stdout.log') -RedirectStandardError (Join-Path $StateDirectory 'gateway.stderr.log')
$deadline=[DateTime]::UtcNow.AddSeconds(20)
do{
    Start-Sleep -Milliseconds 200
    $process.Refresh()
    if($process.HasExited){throw 'Public gateway exited. Inspect gateway.stderr.log in the selected StateDirectory.'}
    $running=Owned-Gateway
}while(-not $running -and [DateTime]::UtcNow -lt $deadline)
if(-not $running){throw 'Public gateway readiness timed out; inspect the owned logs.'}
@{pid=$running.pid;url="http://127.0.0.1:$($running.port)";reused=$false;state=$StateDirectory}|ConvertTo-Json -Compress
