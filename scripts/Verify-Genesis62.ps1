#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$taskSource=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskLane=Split-Path $taskSource -Parent
$taskEvidence=Join-Path $taskLane 'evidence'
$taskOutput=[IO.Path]::GetFullPath($OutputDirectory)
if(-not $taskOutput.StartsWith($taskEvidence+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'GENESIS62_OUTPUT_OUTSIDE_OWN_EVIDENCE'}
if(Test-Path -LiteralPath $taskOutput){throw 'GENESIS62_NEW_EVIDENCE_REQUIRED'}
$taskWalk=$taskOutput
while($taskWalk){
    if((Test-Path -LiteralPath $taskWalk) -and ((Get-Item -LiteralPath $taskWalk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'GENESIS62_REPARSE_EVIDENCE_REJECTED'}
    $taskNext=Split-Path $taskWalk -Parent;if($taskNext -eq $taskWalk){break};$taskWalk=$taskNext
}
$taskPython='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
$taskGit='C:\Program Files\Git\cmd\git.exe'
New-Item -ItemType Directory -Path $taskOutput > $null
$taskPreviousPath=$env:PYTHONPATH
$taskPreviousBytecode=$env:PYTHONDONTWRITEBYTECODE
$taskReceipt=[ordered]@{schema_version='dragonhydra.genesis62-verification/1';status='RUNNING';synthetic=$true;source=(& $taskGit -C $taskSource rev-parse HEAD);source_dirty=[bool](& $taskGit -C $taskSource status --porcelain);scope='Virtual logistics tests, new package integrity tests and benchmark guards; original220 baseline separate';real_connections='NOT_RUN'}
function Get-TaskPins {
    $taskPins=[ordered]@{}
    foreach($taskFile in (Get-ChildItem -LiteralPath (Join-Path $taskSource 'src\dragonhydra\cognitive_logistics') -File -Filter '*.py' | Sort-Object Name)){$taskPins[$taskFile.Name]=(Get-FileHash -LiteralPath $taskFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    return ($taskPins | ConvertTo-Json -Compress)
}
$taskPinsBefore=Get-TaskPins
try{
    $env:PYTHONPATH=Join-Path $taskSource 'src';$env:PYTHONDONTWRITEBYTECODE='1'
    Push-Location -LiteralPath $taskSource
    & $taskPython -B -m unittest discover -s tests -p 'test_logistics*.py' -v 1> (Join-Path $taskOutput 'tests.stdout.txt') 2> (Join-Path $taskOutput 'tests.stderr.txt')
    $taskReceipt.logistics_tests_exit=$LASTEXITCODE;if($LASTEXITCODE -ne 0){throw 'GENESIS62_LOGISTICS_TESTS_FAILED'}
    & $taskPython -B -m unittest discover -s tests -p 'test_genesis62_package.py' -v 1> (Join-Path $taskOutput 'package.stdout.txt') 2> (Join-Path $taskOutput 'package.stderr.txt')
    $taskReceipt.package_tests_exit=$LASTEXITCODE;if($LASTEXITCODE -ne 0){throw 'GENESIS62_PACKAGE_TESTS_FAILED'}
    & $taskPython -B scripts\benchmark_genesis62.py --self-test 1> (Join-Path $taskOutput 'benchmark-guards.stdout.txt') 2> (Join-Path $taskOutput 'benchmark-guards.stderr.txt')
    $taskReceipt.benchmark_guards_exit=$LASTEXITCODE;if($LASTEXITCODE -ne 0){throw 'GENESIS62_BENCHMARK_GUARDS_FAILED'}
    if((Get-TaskPins) -cne $taskPinsBefore){throw 'GENESIS62_SOURCE_CHANGED_DURING_VERIFICATION'}
    $taskReceipt.selected_source_sha256=($taskPinsBefore | ConvertFrom-Json -AsHashtable)
    $taskReceipt.status='PASS'
}catch{$taskReceipt.status='FAILED';$taskReceipt.failure=$_.Exception.Message;throw}
finally{
    Pop-Location
    $env:PYTHONPATH=$taskPreviousPath;$env:PYTHONDONTWRITEBYTECODE=$taskPreviousBytecode
    $taskReceipt | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $taskOutput 'VERIFICATION.json') -Encoding utf8
}
$taskReceipt | ConvertTo-Json -Depth 3
