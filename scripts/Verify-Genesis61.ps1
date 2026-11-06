[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [switch]$Benchmark,
    [ValidateSet(100,1000,10000)][int[]]$BenchmarkSizes = @(100,1000,10000)
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'GENESIS61_POWERSHELL_7_REQUIRED' }
$SourceRoot = Split-Path -Parent $PSScriptRoot
$LaneRoot = Split-Path -Parent $SourceRoot
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $LaneRoot 'evidence'))
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $EvidenceRoot 'verification-r1' }
if ([IO.Path]::GetFullPath($OutputDirectory) -ne $OutputDirectory -and '..' -in ([IO.Path]::GetRelativePath((Get-Location).Path,$OutputDirectory).Split([IO.Path]::DirectorySeparatorChar))) {
    throw 'GENESIS61_EVIDENCE_PARENT_TRAVERSAL'
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $OutputDirectory.StartsWith($EvidenceRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
    throw 'GENESIS61_EVIDENCE_OUTSIDE_OWN_LANE'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'GENESIS61_EVIDENCE_ALREADY_EXISTS' }
$walk = $OutputDirectory
while ($walk) {
    if ((Test-Path -LiteralPath $walk) -and ((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'GENESIS61_REPARSE_EVIDENCE_REJECTED'
    }
    $next = Split-Path -Parent $walk
    if ($next -eq $walk) { break }
    $walk = $next
}
$Python = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
$Git = 'C:\Program Files\Git\cmd\git.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'GENESIS61_REGISTERED_PYTHON_UNAVAILABLE' }
$Commit = & $Git --no-optional-locks -C $SourceRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'GENESIS61_SOURCE_IDENTITY_UNAVAILABLE' }
$Dirty = & $Git --no-optional-locks -C $SourceRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'GENESIS61_SOURCE_STATUS_UNAVAILABLE' }
function Get-SelectedPins {
    $files = @(Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'src\dragonhydra\future_relevance') -File -Filter '*.py')
    $files += @(Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'tests') -File -Filter 'test_future*.py')
    $files += @(Get-Item -LiteralPath $PSCommandPath,(Join-Path $PSScriptRoot 'benchmark_genesis61.py'))
    $files += @('src\dragonhydra\realtime\models.py','src\dragonhydra\realtime\events.py','src\dragonhydra\realtime\worlds.py','src\dragonhydra\cognition\models.py' | ForEach-Object { Get-Item -LiteralPath (Join-Path $SourceRoot $_) })
    $pins = [ordered]@{}
    foreach ($file in $files | Sort-Object FullName -Unique) {
        $relative = [IO.Path]::GetRelativePath($SourceRoot,$file.FullName).Replace('\','/')
        $pins[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    return $pins
}
$Pins = Get-SelectedPins
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$Receipt = [ordered]@{
    schema_version='dragonhydra.genesis61-verification/1'; status='RUNNING'; synthetic=$true
    source_root=$SourceRoot; source_commit=([string]$Commit).Trim(); working_tree_has_changes=[bool]$Dirty
    python_executable=$Python; selected_source_inputs_sha256=$Pins
    scope='New virtual future-relevance focused tests and benchmark guards only'
    inherited_142_baseline='NOT_RUN_BY_THIS_COMMAND; separate root-owned verification'
    old_data_bearing_global_suite='NOT_RUN'
    real_provider_openai_sql_scm_operations='NOT_RUN'
    tests='unittest discover -s tests -p test_future*.py -v'
    benchmark_requested=[bool]$Benchmark; benchmark_sizes=$BenchmarkSizes
}
$Receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'PLAN.json') -Encoding utf8
$PreviousPath = $env:PYTHONPATH
$PreviousBytecode = $env:PYTHONDONTWRITEBYTECODE
$PreviousDirectory = Get-Location
try {
    $env:PYTHONPATH = Join-Path $SourceRoot 'src'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Set-Location -LiteralPath $SourceRoot
    & $Python -m unittest discover -s tests -p 'test_future*.py' -v 1> (Join-Path $OutputDirectory 'tests.stdout.txt') 2> (Join-Path $OutputDirectory 'tests.stderr.txt')
    $Receipt.tests_exit_code=$LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'GENESIS61_FOCUSED_TESTS_FAILED' }
    & $Python (Join-Path $PSScriptRoot 'benchmark_genesis61.py') --self-test 1> (Join-Path $OutputDirectory 'benchmark-guards.stdout.txt') 2> (Join-Path $OutputDirectory 'benchmark-guards.stderr.txt')
    $Receipt.benchmark_guards_exit_code=$LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'GENESIS61_BENCHMARK_GUARDS_FAILED' }
    if ($Benchmark) {
        $arguments = @((Join-Path $PSScriptRoot 'benchmark_genesis61.py'),'--output',(Join-Path $OutputDirectory 'benchmark'),'--sizes')
        $arguments += @($BenchmarkSizes | ForEach-Object { [string]$_ })
        & $Python @arguments 1> (Join-Path $OutputDirectory 'benchmark.stdout.txt') 2> (Join-Path $OutputDirectory 'benchmark.stderr.txt')
        $Receipt.benchmark_exit_code=$LASTEXITCODE
        if ($LASTEXITCODE -ne 0) { throw 'GENESIS61_BENCHMARK_FAILED' }
    }
    $AfterPins = Get-SelectedPins
    if (($Pins | ConvertTo-Json -Compress) -ne ($AfterPins | ConvertTo-Json -Compress)) {
        $Receipt.selected_source_inputs_after=$AfterPins
        throw 'GENESIS61_SELECTED_SOURCE_CHANGED_DURING_VERIFICATION'
    }
    $Receipt.status='PASS'
} catch {
    $Receipt.status='FAILED'
    $Receipt.failure=$_.Exception.Message
    throw
} finally {
    $Receipt.evidence_files=@(Get-ChildItem -LiteralPath $OutputDirectory -File | ForEach-Object {
        [ordered]@{name=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    $Receipt | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'VERIFICATION.json') -Encoding utf8
    Set-Location -LiteralPath $PreviousDirectory
    $env:PYTHONPATH=$PreviousPath
    $env:PYTHONDONTWRITEBYTECODE=$PreviousBytecode
}
$Receipt | ConvertTo-Json -Depth 12
