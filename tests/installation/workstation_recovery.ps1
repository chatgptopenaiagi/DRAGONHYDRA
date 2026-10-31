#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$InstallRoot,[Parameter(Mandatory)][string]$StateRoot,[string]$ServiceName='DragonhydraWorkstationTest',[Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$InstallRoot=[IO.Path]::GetFullPath($InstallRoot).TrimEnd('\');$StateRoot=[IO.Path]::GetFullPath($StateRoot).TrimEnd('\');$Output=[IO.Path]::GetFullPath($Output)
$boundary=(Join-Path $project 'build\workstation\test-install')+'\'
foreach($path in @($InstallRoot,$StateRoot)){if(-not $path.StartsWith($boundary,[StringComparison]::OrdinalIgnoreCase)){throw 'Recovery is restricted to owned workstation test installations.'}}
if(-not $Output.StartsWith((Join-Path $project 'build\workstation\evidence')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Evidence output is outside the project test directory.'}
if($ServiceName -notmatch '^Dragonhydra[A-Za-z0-9_-]{0,60}$'){throw 'Invalid service name.'}
$cfg=Get-Content -LiteralPath (Join-Path $StateRoot 'workstation.json') -Raw|ConvertFrom-Json
if($cfg.install_root -ne $InstallRoot -or $cfg.state_root -ne $StateRoot -or $cfg.service_name -ne $ServiceName){throw 'Test state ownership mismatch.'}
$expected='"'+(Join-Path $InstallRoot 'workstation\DragonhydraService.exe')+'" --state "'+$StateRoot+'" --name '+$ServiceName
$service=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if(-not $service -or $service.PathName -cne $expected -or $service.State -ne 'Running'){throw 'The exact test-owned service is not running; no process changed.'}
$headers=@{Authorization=('Bearer '+(Get-Content -LiteralPath (Join-Path $StateRoot 'client\local-session.json') -Raw|ConvertFrom-Json).token)}
$base='http://127.0.0.1:'+$cfg.api_port+'/dragon/api/v1'
function Api([string]$path){Invoke-RestMethod -Uri ($base+$path) -Headers $headers -TimeoutSec 10}
$page=Api '/matches?limit=1';$match=$page.items[0]
$endpoint=Get-Content -LiteralPath (Join-Path $StateRoot 'kernel\endpoint.json') -Raw|ConvertFrom-Json
$kernel=Get-CimInstance Win32_Process -Filter ('ProcessId='+[int]$endpoint.pid)
$kernelPath=Join-Path $InstallRoot 'server\DRAGONHYDRA-Server.exe'
if(-not $kernel -or $kernel.ExecutablePath -cne $kernelPath -or -not $kernel.CommandLine.Contains((Join-Path $StateRoot 'kernel'))){throw 'Kernel process ownership changed; failure injection refused.'}
$protected=@(Get-NetTCPConnection -State Listen|Where-Object {$_.LocalPort -in 18732,18733,18734}|Select-Object LocalAddress,LocalPort,OwningProcess)
$before=[ordered]@{count=$page.total;match_id=$match.id;evidence_version=$match.version;source_id=$match.source_id;kernel_pid=$endpoint.pid;service_pid=$service.ProcessId}
$checks=[Collections.Generic.List[object]]::new()
$record=[ordered]@{schema_version=1;started_at=[DateTime]::UtcNow.ToString('o');passed=$false;scope='One forced failure of only the path-verified isolated kernel; SCM recovery is automatic';before=$before;checks=$checks}
try{
    # The kernel is a child of our product job, not an unrelated Python process.
    # No service restart command is issued: this must exercise configured SCM recovery.
    # LocalService owns the child. -Force suppresses the cross-account confirm
    # prompt after the exact executable/state checks above; it cannot select
    # another process or broaden the scope of this deliberate failure test.
    Stop-Process -Id $kernel.ProcessId -Force -ErrorAction Stop
    $timer=[Diagnostics.Stopwatch]::StartNew()
    $observedFailure=$false
    $deadline=[DateTime]::UtcNow.AddSeconds(240)
    do{
        try{
            $status=Get-Content -LiteralPath (Join-Path $StateRoot 'status.json') -Raw|ConvertFrom-Json
            $current=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
            if($status.stage -ne 'ready' -or $current.State -ne 'Running'){$observedFailure=$true}
            $nextEndpoint=Get-Content -LiteralPath (Join-Path $StateRoot 'kernel\endpoint.json') -Raw|ConvertFrom-Json
            if($observedFailure -and $status.stage -eq 'ready' -and $current.State -eq 'Running' -and $current.ProcessId -ne $before.service_pid -and $nextEndpoint.pid -ne $before.kernel_pid -and (Api '/health/ready').status -eq 'ready'){break}
        }catch{}
        Start-Sleep -Milliseconds 500
    }while([DateTime]::UtcNow -lt $deadline)
    if(-not $observedFailure -or $current.State -ne 'Running' -or $status.stage -ne 'ready' -or $current.ProcessId -eq $before.service_pid){throw 'SCM did not automatically recover the complete workstation before its deadline.'}
    $afterPage=Api '/matches?limit=1';$afterMatch=Api ('/matches/'+$match.id)
    if($afterPage.total -ne $before.count -or $afterMatch.version -ne $before.evidence_version){throw 'Data or revision identity changed across failure recovery.'}
    $checks.Add(@{name='automatic-bounded-SCM-recovery-after-owned-kernel-failure';passed=$true;seconds=[Math]::Round($timer.Elapsed.TotalSeconds,3);old_service_pid=$before.service_pid;new_service_pid=$current.ProcessId;old_kernel_pid=$before.kernel_pid;new_kernel_pid=$nextEndpoint.pid})
    $checks.Add(@{name='record-count-and-canonical-evidence-retained';passed=$true;before_count=$before.count;after_count=$afterPage.total;match_id=$match.id;evidence_version=$afterMatch.version})
    $web=Invoke-WebRequest -Uri ('http://127.0.0.1:'+$cfg.web_port+'/') -TimeoutSec 20
    $admin=Invoke-WebRequest -Uri ('http://127.0.0.1:'+$cfg.web_port+'/administrator/') -TimeoutSec 20
    if($web.StatusCode -ne 200 -or $admin.StatusCode -ne 200){throw 'Joomla did not recover.'}
    $checks.Add(@{name='Apache-PHP-Joomla-recovered';passed=$true;homepage=[int]$web.StatusCode;administrator=[int]$admin.StatusCode})
    $afterProtected=@(Get-NetTCPConnection -State Listen|Where-Object {$_.LocalPort -in 18732,18733,18734}|Select-Object LocalAddress,LocalPort,OwningProcess)
    if(($protected|Sort-Object LocalPort|ConvertTo-Json -Compress) -ne ($afterProtected|Sort-Object LocalPort|ConvertTo-Json -Compress)){throw 'A protected original listener changed; inspect concurrent activity.'}
    $checks.Add(@{name='original-listeners-preserved';passed=$true;ports=@(18732,18733,18734)})
    $record.after=@{count=$afterPage.total;service_pid=$current.ProcessId;kernel_pid=$nextEndpoint.pid;api_url=('http://127.0.0.1:'+$cfg.api_port);joomla_url=('http://127.0.0.1:'+$cfg.web_port)}
    $record.passed=$true
}catch{$record.error=$_.Exception.Message;throw}
finally{
    $record.finished_at=[DateTime]::UtcNow.ToString('o')
    New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent)|Out-Null
    $record|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $Output -Encoding utf8
    Write-Output ('Owned workstation failure recovery: passed='+$record.passed+'; checks='+$checks.Count)
}
