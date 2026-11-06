[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [switch]$Benchmark,
    [int[]]$BenchmarkSizes = @(100, 1000, 10000)
)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'GENESIS6_POWERSHELL_7_REQUIRED' }
$SourceRoot = Split-Path -Parent $PSScriptRoot
$LaneRoot = Split-Path -Parent $SourceRoot
$EvidenceRoot = [IO.Path]::GetFullPath((Join-Path $LaneRoot 'evidence'))
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $EvidenceRoot 'verification-r1' }
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $OutputDirectory.StartsWith($EvidenceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'GENESIS6_EVIDENCE_OUTSIDE_ISOLATED_LANE'
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'GENESIS6_EVIDENCE_ALREADY_EXISTS' }
$walk = $OutputDirectory
while ($walk) {
    if (Test-Path -LiteralPath $walk) {
        if ((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'GENESIS6_REPARSE_EVIDENCE_REJECTED'
        }
    }
    $next = Split-Path -Parent $walk
    if ($next -eq $walk) { break }
    $walk = $next
}
$Python = 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\tools-env\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'GENESIS6_VERIFIED_PYTHON_UNAVAILABLE' }
$Git = 'C:\Program Files\Git\cmd\git.exe'
$SourceCommit = & $Git -C $SourceRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'GENESIS6_SOURCE_IDENTITY_UNAVAILABLE' }
$SourceStatus = & $Git -C $SourceRoot status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'GENESIS6_SOURCE_STATUS_UNAVAILABLE' }
$SourceFiles = @(Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'src\dragonhydra\realtime') -File -Filter '*.py')
$SourceFiles += @(Get-ChildItem -LiteralPath (Join-Path $SourceRoot 'tests') -File -Filter 'test_realtime*.py')
$SourceFiles += @(Get-Item -LiteralPath $PSCommandPath, (Join-Path $PSScriptRoot 'benchmark_genesis6.py'))
$SourcePins = [ordered]@{}
foreach ($sourceFile in $SourceFiles | Sort-Object FullName) {
    $relative = [IO.Path]::GetRelativePath($SourceRoot, $sourceFile.FullName).Replace('\', '/')
    $SourcePins[$relative] = (Get-FileHash -LiteralPath $sourceFile.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$Receipt = [ordered]@{
    schema_version = 'dragonhydra.genesis6-verification/1'; synthetic = $true
    status = 'RUNNING'; python_executable = $Python; source_root = $SourceRoot
    source_commit = ([string]$SourceCommit).Trim(); working_tree_has_changes = [bool]$SourceStatus
    selected_source_inputs_sha256 = $SourcePins
    tests = 'unittest discover -s tests -p test_realtime*.py -v'
    benchmark_requested = [bool]$Benchmark; benchmark_sizes = $BenchmarkSizes
    network_provider_sql_scm_operations = 'NOT_RUN'
}
$Receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'PLAN.json') -Encoding utf8
$previousPythonPath = $env:PYTHONPATH
$previousBytecode = $env:PYTHONDONTWRITEBYTECODE
$previousLocation = Get-Location
try {
    $env:PYTHONPATH = Join-Path $SourceRoot 'src'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    Set-Location -LiteralPath $SourceRoot
    & $Python -m unittest discover -s tests -p 'test_realtime*.py' -v 1> (Join-Path $OutputDirectory 'tests.stdout.txt') 2> (Join-Path $OutputDirectory 'tests.stderr.txt')
    $Receipt.tests_exit_code = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'GENESIS6_FOCUSED_TESTS_FAILED' }
    & $Python (Join-Path $PSScriptRoot 'benchmark_genesis6.py') --self-test 1> (Join-Path $OutputDirectory 'benchmark-guards.stdout.txt') 2> (Join-Path $OutputDirectory 'benchmark-guards.stderr.txt')
    $Receipt.benchmark_guards_exit_code = $LASTEXITCODE
    if ($LASTEXITCODE -ne 0) { throw 'GENESIS6_BENCHMARK_GUARDS_FAILED' }
    if ($Benchmark) {
        $benchmarkArguments = @((Join-Path $PSScriptRoot 'benchmark_genesis6.py'), '--output', (Join-Path $OutputDirectory 'benchmark'), '--sizes')
        $benchmarkArguments += @($BenchmarkSizes | ForEach-Object { [string]$_ })
        & $Python @benchmarkArguments 1> (Join-Path $OutputDirectory 'benchmark.stdout.txt') 2> (Join-Path $OutputDirectory 'benchmark.stderr.txt')
        $Receipt.benchmark_exit_code = $LASTEXITCODE
        if ($LASTEXITCODE -ne 0) { throw 'GENESIS6_BENCHMARK_FAILED' }
    }
    $changed = @()
    foreach ($relative in $SourcePins.Keys) {
        $currentHash = (Get-FileHash -LiteralPath (Join-Path $SourceRoot $relative) -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($currentHash -ne $SourcePins[$relative]) { $changed += $relative }
    }
    if ($changed.Count) {
        $Receipt.changed_selected_source_files = $changed
        throw 'GENESIS6_SELECTED_SOURCE_CHANGED_DURING_VERIFICATION'
    }
    $Receipt.status = 'PASS'
} catch {
    $Receipt.status = 'FAILED'
    $Receipt.failure = $_.Exception.Message
    throw
} finally {
    $Receipt.evidence_files = @(Get-ChildItem -LiteralPath $OutputDirectory -File | ForEach-Object {
        [ordered]@{name=$_.Name;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    })
    $Receipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $OutputDirectory 'VERIFICATION.json') -Encoding utf8
    Set-Location -LiteralPath $previousLocation
    $env:PYTHONPATH = $previousPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $previousBytecode
}
$Receipt | ConvertTo-Json -Depth 10
