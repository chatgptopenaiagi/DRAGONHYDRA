#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Helper,
    [Parameter(Mandatory)][string]$WorkRoot,
    [Parameter(Mandatory)][string]$Output
)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'This regression must run under Windows PowerShell 5.1.'}
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$boundary=(Join-Path $project 'build\workstation\evidence').TrimEnd('\')+'\'
$WorkRoot=[IO.Path]::GetFullPath($WorkRoot)
$Output=[IO.Path]::GetFullPath($Output)
foreach($path in @($WorkRoot,$Output)){if(-not $path.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)){throw 'Regression files must stay in workstation evidence.'}}
$run=Join-Path $WorkRoot ('atomic files '+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $run,(Split-Path $Output -Parent)|Out-Null
Add-Type -Path ([IO.Path]::GetFullPath($Helper))
Add-Type -TypeDefinition 'public static class DragonhydraTestReader { public static void ReleaseAfter(System.IDisposable handle,int milliseconds) { System.Threading.ThreadPool.QueueUserWorkItem(delegate { System.Threading.Thread.Sleep(milliseconds);handle.Dispose(); }); } }'
$checks=New-Object Collections.Generic.List[object]
$record=[ordered]@{schema_version=1;started_at=[DateTime]::UtcNow.ToString('o');powershell=$PSVersionTable.PSVersion.ToString();process_64bit=[Environment]::Is64BitProcess;helper_sha256=(Get-FileHash -LiteralPath $Helper -Algorithm SHA256).Hash.ToLowerInvariant();work_root=$run;passed=$false;checks=$checks}
function Check([string]$name,[bool]$value){if(-not $value){throw "Regression failed: $name"};$checks.Add(@{name=$name;passed=$true})}
function Text([string]$name,[string]$value){$p=Join-Path $run $name;[IO.File]::WriteAllText($p,$value);return $p}
try{
    Check 'all-file-operations-run-in-a-path-containing-spaces' $run.Contains('atomic files ')
    $source=Text 'original.next' 'new';$destination=Text 'original.json' 'old'
    $originalFailed=$false
    try{[IO.File]::Replace($source,$destination,$null)}catch{
        $originalFailed=$true
        $record.original_exception=$_.Exception.InnerException.GetType().FullName
        $record.original_error=$_.Exception.InnerException.Message
    }
    Check 'original-PS51-null-backup-binding-failure-reproduced' $originalFailed
    Check 'original-failure-kept-both-input-files' (([IO.File]::ReadAllText($source) -eq 'new') -and ([IO.File]::ReadAllText($destination) -eq 'old'))
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination)
    Check 'existing-destination-atomic-replacement-without-backup' (([IO.File]::ReadAllText($destination) -eq 'new') -and -not [IO.File]::Exists($source))
    Check 'no-backup-created-by-default' (@(Get-ChildItem -LiteralPath $run -Filter '*.bak').Count -eq 0)
    $source=Text 'missing.next' 'created';$destination=Join-Path $run 'missing.json'
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination)
    Check 'missing-destination-atomic-move' (([IO.File]::ReadAllText($destination) -eq 'created') -and -not [IO.File]::Exists($source))
    $source=Text 'backup.next' 'new-v2';$destination=Text 'backup.json' 'old-v1';$backup=Text 'previous.bak' 'obsolete-backup'
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination,$backup)
    Check 'explicit-backup-retains-previous-destination' (([IO.File]::ReadAllText($backup) -eq 'old-v1') -and ([IO.File]::ReadAllText($destination) -eq 'new-v2'))
    $source=Text 'missing-with-backup.next' 'new';$destination=Join-Path $run 'missing-with-backup.json';$backup=Join-Path $run 'unused.bak'
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination,$backup)
    Check 'new-destination-does-not-invent-a-backup' (([IO.File]::ReadAllText($destination) -eq 'new') -and -not [IO.File]::Exists($backup))
    $source=Text 'missing-keeps-backup.next' 'new';$destination=Join-Path $run 'missing-keeps-backup.json';$backup=Text 'retained.bak' 'retain-existing-backup'
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination,$backup)
    Check 'new-destination-keeps-an-already-existing-backup' ([IO.File]::ReadAllText($backup) -eq 'retain-existing-backup')
    $source=Text 'empty-backup.next' 'new';$destination=Text 'empty-backup.json' 'old'
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination,'')
    Check 'empty-optional-backup-normalized-inside-typed-helper' ([IO.File]::ReadAllText($destination) -eq 'new')
    $source=Text 'same-target.next' 'new';$destination=Text 'same-target.json' 'keep'
    $rejected=$false
    try{[Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination,$destination)}catch{$rejected=$true}
    Check 'invalid-backup-rejected-without-destroying-committed-data' ($rejected -and ([IO.File]::ReadAllText($destination) -eq 'keep') -and [IO.File]::Exists($source))
    $source=Text 'locked.next' 'new';$destination=Text 'locked.json' 'keep'
    $stream=[IO.File]::Open($destination,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::None)
    $rejected=$false
    try{try{[Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination)}catch{$rejected=$true}}finally{$stream.Dispose()}
    Check 'locked-destination-failure-preserves-source-and-old-content' ($rejected -and ([IO.File]::ReadAllText($destination) -eq 'keep') -and [IO.File]::Exists($source))
    $source=Text 'transient-reader.next' 'new';$destination=Text 'transient-reader.json' 'old'
    $reader=[IO.File]::Open($destination,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    [DragonhydraTestReader]::ReleaseAfter($reader,150)
    $watch=[Diagnostics.Stopwatch]::StartNew()
    [Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination)
    Check 'bounded-retry-recovers-from-a-transient-deny-delete-reader' (([IO.File]::ReadAllText($destination) -eq 'new') -and $watch.ElapsedMilliseconds -ge 100 -and $watch.ElapsedMilliseconds -lt 2000)
    $source=Text 'shared-reader.next' 'new';$destination=Text 'shared-reader.json' 'old'
    $reader=[IO.File]::Open($destination,[IO.FileMode]::Open,[IO.FileAccess]::Read,([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    try{[Dragonhydra.Workstation.AtomicFile]::Commit($source,$destination)}finally{$reader.Dispose()}
    Check 'delete-sharing-reader-does-not-block-atomic-replacement' ([Dragonhydra.Workstation.AtomicFile]::Read($destination) -eq 'new')
    $destination=Join-Path $run 'status.json'
    $unicode='Fu'+[char]0x00df+'ball'
    for($i=0;$i -lt 20;$i++){
        [Dragonhydra.Workstation.AtomicFile]::Write($destination,(@{stage='running';sequence=$i;unicode=$unicode}|ConvertTo-Json))
        $current=[Dragonhydra.Workstation.AtomicFile]::Read($destination)|ConvertFrom-Json
        if($current.sequence -ne $i -or $current.unicode -ne $unicode){throw 'Repeated JSON replacement or UTF8 failed.'}
    }
    Check 'first-write-and-20-repeated-UTF8-status-updates' $true
    Check 'successful-writes-leave-no-owned-pending-files' (@(Get-ChildItem -LiteralPath $run -Filter 'status.json.next.*').Count -eq 0)
    $record.passed=$true
}catch{$record.error=$_.Exception.Message;throw}
finally{
    $record.finished_at=[DateTime]::UtcNow.ToString('o')
    $record|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Output -Encoding UTF8
    Write-Output ('PS5.1 atomic replacement regression: passed='+$record.passed+'; checks='+$checks.Count+'; evidence='+$Output)
}
