#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputRoot)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'CoreNextProfile.ps1')
$OutputRoot=Assert-CoreNextOrdinaryPath $OutputRoot 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
$compiler=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if(-not(Test-Path -LiteralPath $compiler)){throw 'The existing .NET Framework x64 compiler is unavailable.'}
New-Item -ItemType Directory -Path $OutputRoot -Force|Out-Null
$atomicArguments=@('/nologo','/optimize+','/platform:anycpu','/target:library',('/out:'+(Join-Path $OutputRoot 'DragonhydraAtomicFile.dll')),(Join-Path $PSScriptRoot 'DragonhydraAtomicFile.cs'))
& $compiler @atomicArguments
if($LASTEXITCODE -ne 0){throw 'Atomic file helper compilation failed.'}
foreach($name in @('DragonhydraService','DragonhydraLauncher')){
    $references=if($name -eq 'DragonhydraService'){@('/r:System.ServiceProcess.dll')}else{@('/r:System.Windows.Forms.dll','/r:System.Drawing.dll','/r:System.Web.Extensions.dll',('/r:'+(Join-Path $OutputRoot 'DragonhydraAtomicFile.dll')))}
    $compileArguments=@('/nologo','/optimize+','/platform:x64','/target:winexe',('/out:'+(Join-Path $OutputRoot ($name+'.exe'))))+@($references)+@(Join-Path $PSScriptRoot ($name+'.cs'))
    & $compiler @compileArguments
    if($LASTEXITCODE -ne 0){throw "$name compilation failed."}
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Workstation.ps1') -Destination $OutputRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'CoreNextProfile.ps1') -Destination $OutputRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'Configure-CoreNextSqlResearch.ps1') -Destination $OutputRoot
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'SQL-RESEARCH.md') -Destination $OutputRoot
'Compiled native SCM service host and interactive launcher against installed .NET Framework.'
