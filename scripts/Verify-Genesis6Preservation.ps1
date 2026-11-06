#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$OutputDirectory)
$ErrorActionPreference='Stop'
$taskLane=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$taskEvidence=Join-Path $taskLane 'evidence'
$taskOutput=[IO.Path]::GetFullPath($OutputDirectory)
if(-not $taskOutput.StartsWith($taskEvidence+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)-or(Test-Path -LiteralPath $taskOutput)){throw 'NEW_OWNED_EVIDENCE_REQUIRED'}
$walk=$taskOutput
while($walk){if((Test-Path -LiteralPath $walk)-and((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'REPARSE_EVIDENCE_REJECTED'};$next=Split-Path $walk -Parent;if($next -eq $walk){break};$walk=$next}
New-Item -ItemType Directory -Path $taskOutput|Out-Null
$git='C:\Program Files\Git\cmd\git.exe'
$gh='C:\Program Files\GitHub CLI\gh.exe'
$lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'
$before=Get-Content (Join-Path $taskEvidence 'BEFORE.json') -Raw|ConvertFrom-Json
function HashText([string]$Text){[Convert]::ToHexStringLower([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Text)))}
function HashFile([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
$report=[ordered]@{schema_version='dragonhydra.genesis6-preservation/1';observed_at=[DateTime]::UtcNow.ToString('o');status='RUNNING';differences=@();services=@();historical_failures=@();packages=@();worktrees=@();database_scope='No original sporting database opened or modified by GENESIS6; active database bytes are not asserted static';Codex=@{}}
try{
    foreach($old in $before.protected_services){
        $service=Get-CimInstance Win32_Service -Filter ("Name='"+$old.name+"'")
        if(-not $service){throw 'PROTECTED_SERVICE_MISSING'}
        $current=[ordered]@{name=$service.Name;state=$service.State;pid=[int]$service.ProcessId;account=$service.StartName;start_mode=$service.StartMode;commandline_sha256=(HashText $service.PathName)}
        $changes=@('state','pid','account','start_mode','commandline_sha256'|Where-Object {$current[$_] -cne $old.$_})
        $current.matches=$changes.Count -eq 0;$current.changed_fields=$changes;$report.services+=,$current
        if($changes.Count){$report.differences+=('Service: '+$old.name)}
    }
    $codexHash=HashFile $before.Codex.path
    $report.Codex=@{sha256=$codexHash;matches=$codexHash -eq $before.Codex.sha256;executed=$false;updated=$false;configuration_modified=$false}
    if(-not $report.Codex.matches){$report.differences+='Codex executable'}
    $failedRoot=Join-Path $lab 'continuation-20261102\disposable-dev5-lifecycle-r1'
    $failedPins=@{'phase-Forecast.json'='e25a958d991987b0a017a9423a8d97ca853719cddaecf4fa3699f4e41a10b9a6';'Forecast.started.lock'='36b6c6ada192dead54a343b48f179febc4d523276c01e4db263bb28525527072';'PLAN.json'='5bcf53a0077440d7537e659bc94b5cf3dbb5e29ae1428d207b19a5f8a4a47b7c';'BINDINGS.json'='df0260dd0f54a5bab7a3e62e6359259da5db7db9572c366aabf67b43f87cc2c7'}
    foreach($name in $failedPins.Keys|Sort-Object){$hash=HashFile (Join-Path $failedRoot $name);$match=$hash -eq $failedPins[$name];$report.historical_failures+=@{name=$name;sha256=$hash;matches=$match;rerun=$false};if(-not $match){$report.differences+=('Original failed receipt: '+$name)}}
    $detailHash=HashFile $before.historical_failed_forecast.path
    $report.historical_workflow=@{matches=$detailHash -eq $before.historical_failed_forecast.sha256;sha256=$detailHash}
    if(-not $report.historical_workflow.matches){$report.differences+='Original workflow receipt'}
    foreach($folder in @('v0.5.0-dev.7-core-next','v0.5.0-dev.8-core-next-acl-held-r1','v0.5.0-dev.8-core-next-r2-held-sid-r4')){
        $root=Join-Path $lab ('dist\'+$folder);$manifest=Join-Path $root 'ARTIFACT-MANIFEST.json';$m=Get-Content $manifest -Raw|ConvertFrom-Json
        foreach($artifact in $m.artifacts){$hash=HashFile (Join-Path $root $artifact.filename);$match=$hash -eq $artifact.sha256;$report.packages+=@{generation=$folder;filename=$artifact.filename;sha256=$hash;matches=$match};if(-not $match){$report.differences+=('Sealed package: '+$artifact.filename)}}
    }
    $blocks=(Get-Content (Join-Path $taskEvidence 'WORKTREES-BEFORE.txt') -Raw)-split '(?:\r?\n){2,}'
    foreach($block in $blocks){if($block -match '(?m)^worktree (.+)\r?$'){$path=$Matches[1].Trim();if($block -notmatch '(?m)^HEAD ([a-f0-9]{40})\r?$'){throw 'BASELINE_WORKTREE_HEAD_REQUIRED'};$head=$Matches[1];$oldBranch=if($block -match '(?m)^branch (.+)\r?$'){$Matches[1].Trim()}else{''};$actual=(& $git --no-optional-locks -C $path rev-parse HEAD).Trim();if($LASTEXITCODE -ne 0){throw 'WORKTREE_READ_FAILED'};$branch=(& $git --no-optional-locks -C $path symbolic-ref -q HEAD);$branch=([string]$branch).Trim();$match=$head -eq $actual -and $oldBranch -eq $branch;$report.worktrees+=@{path=$path;head=$actual;branch=$branch;matches=$match};if(-not $match){$report.differences+=('Worktree binding: '+$path)}}}
    $remoteTags=& $git ls-remote origin 'refs/tags/*'
    if($LASTEXITCODE -ne 0){throw 'REMOTE_TAG_READ_FAILED'}
    $originalTags=@(Get-Content (Join-Path $taskEvidence 'TAGS-BEFORE.txt')|Where-Object {$_}|Sort-Object)
    $tagDiff=@(Compare-Object $originalTags @($remoteTags|Where-Object {$_}|Sort-Object))
    $report.tags=@{matches=$tagDiff.Count -eq 0;count=$originalTags.Count}
    if($tagDiff.Count){$report.differences+='Remote historical tags'}
    $remote=& $gh api 'repos/chatgptopenaiagi/DRAGONHYDRA/releases?per_page=100' --paginate --slurp
    if($LASTEXITCODE -ne 0){throw 'REMOTE_RELEASE_READ_FAILED'}
    $remote|Set-Content (Join-Path $taskOutput 'RELEASES-AFTER.json') -Encoding utf8
    function ReleasePins($InputValue){$list=[Collections.Generic.List[object]]::new();foreach($item in $InputValue){if($item -is [array]){foreach($nested in $item){$list.Add($nested)}}else{$list.Add($item)}};@($list|ForEach-Object {[ordered]@{id=$_.id;tag=$_.tag_name;target=$_.target_commitish;name=$_.name;draft=$_.draft;prerelease=$_.prerelease;published_at=$_.published_at;updated_at=$_.updated_at;body_sha256=(HashText $_.body);assets=@($_.assets|Sort-Object id|ForEach-Object {[ordered]@{id=$_.id;name=$_.name;bytes=$_.size;digest=$_.digest;state=$_.state;updated_at=$_.updated_at}})}}|Sort-Object id)}
    $oldPins=ReleasePins (Get-Content (Join-Path $taskEvidence 'RELEASES-BEFORE.json') -Raw|ConvertFrom-Json -NoEnumerate)
    $newPins=ReleasePins ($remote|ConvertFrom-Json -NoEnumerate)
    $oldJson=$oldPins|ConvertTo-Json -Depth 10 -Compress;$newJson=$newPins|ConvertTo-Json -Depth 10 -Compress
    $report.releases=@{matches=$oldJson -ceq $newJson;count=$oldPins.Count;asset_count=($oldPins.assets|Measure-Object).Count;old_pins_sha256=(HashText $oldJson);new_pins_sha256=(HashText $newJson);download_counts='Expected mutable counters excluded from immutable metadata comparison'}
    if(-not $report.releases.matches){$report.differences+='Historical release identity or asset metadata'}
    $report.status=if($report.differences.Count){'FAILED'}else{'PASS'}
}catch{$report.status='FAILED';$report.failure=$_.Exception.Message;throw}
finally{$report|ConvertTo-Json -Depth 15|Set-Content (Join-Path $taskOutput 'PRESERVATION.json') -Encoding utf8}
if($report.status -ne 'PASS'){throw 'GENESIS6_PRESERVATION_DIFFERENCES'}
[ordered]@{status=$report.status;services=$report.services.Count;packages=$report.packages.Count;worktrees=$report.worktrees.Count;releases=$report.releases.count;assets=$report.releases.asset_count;report=(Join-Path $taskOutput 'PRESERVATION.json')}|ConvertTo-Json
