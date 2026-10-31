#requires -Version 5.1
[CmdletBinding()]
param([Parameter(Mandatory)][string]$InstallRoot,[Parameter(Mandatory)][string]$StateRoot,[Parameter(Mandatory)][string]$Output,[switch]$RunChild)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$InstallRoot=[IO.Path]::GetFullPath($InstallRoot);$StateRoot=[IO.Path]::GetFullPath($StateRoot);$Output=[IO.Path]::GetFullPath($Output)
$testRoot=(Join-Path $project 'build\workstation\test-install')+'\'
foreach($path in @($InstallRoot,$StateRoot)){if(-not $path.StartsWith($testRoot,[StringComparison]::OrdinalIgnoreCase) -or $path.Contains('"')){throw 'Only owned workstation test directories are accepted.'}}
if(($Output.Contains('"')) -or (-not $Output.StartsWith((Join-Path $project 'build\workstation\evidence')+'\',[StringComparison]::OrdinalIgnoreCase) -and -not $Output.StartsWith($StateRoot+'\',[StringComparison]::OrdinalIgnoreCase))){throw 'Regression output must stay inside owned test state or project evidence.'}
$php=Join-Path $InstallRoot 'web\php\php.exe'
$test=Join-Path $PSScriptRoot 'joomla_extension_staging.php'
$cfg=Join-Path $StateRoot 'workstation.json'
if($RunChild){
    if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne 'S-1-5-19'){throw 'This regression child must run as the actual LocalService identity.'}
    $env:PSModulePath=Join-Path $PSHOME 'Modules'
    $env:PATH=(Join-Path $InstallRoot 'web\php')+';'+(Join-Path $InstallRoot 'web\apache\bin')+';'+(Join-Path $InstallRoot 'web\mariadb\bin')+';'+$env:WINDIR+'\System32;'+$env:WINDIR
    & $php -c (Join-Path $StateRoot 'web-config\php.ini') $test $cfg $Output
    exit $LASTEXITCODE
}
foreach($path in @($php,$test,$cfg)){if(-not(Test-Path -LiteralPath $path -PathType Leaf)){throw 'Regression prerequisite missing.'}}
if(Test-Path -LiteralPath $Output){throw 'Use a new evidence output; earlier regression receipts are preserved.'}
New-Item -ItemType Directory -Force -Path (Split-Path $Output -Parent)|Out-Null
$name='DRAGONHYDRA-Extension-Regression-'+[Guid]::NewGuid().ToString('N')
$powershell=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments='-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$PSCommandPath+'" -RunChild -InstallRoot "'+$InstallRoot+'" -StateRoot "'+$StateRoot+'" -Output "'+$Output+'"'
$action=New-ScheduledTaskAction -Execute $powershell -Argument $arguments -WorkingDirectory $StateRoot
$principal=New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -MultipleInstances IgnoreNew
$registered=$false
try{
    if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'Unique regression task name already exists; not changed.'}
    $null=Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Settings $settings
    $registered=$true
    Start-ScheduledTask -TaskName $name
    $deadline=[DateTime]::UtcNow.AddSeconds(180)
    do{
        Start-Sleep -Milliseconds 500
        $info=Get-ScheduledTaskInfo -TaskName $name
        $current=Get-ScheduledTask -TaskName $name
        if($info.LastRunTime -gt [DateTime]::Now.AddMinutes(-3) -and $current.State -ne 'Running' -and $current.State -ne 'Queued'){break}
    }while([DateTime]::UtcNow -lt $deadline)
    if(-not(Test-Path -LiteralPath $Output)){throw ('LocalService regression produced no receipt; task result='+$info.LastTaskResult)}
    $receipt=Get-Content -LiteralPath $Output -Raw|ConvertFrom-Json
    if($info.LastTaskResult -ne 0 -or -not $receipt.passed){throw ('LocalService Joomla staging regression failed; task result='+$info.LastTaskResult)}
    Write-Output ('LocalService Joomla staging regression passed; task exit='+$info.LastTaskResult+'; evidence='+$Output)
}finally{
    if($registered){
        $owned=Get-ScheduledTask -TaskName $name
        $principalSid=$owned.Principal.UserId
        if(-not $principalSid.StartsWith('S-')){try{$principalSid=(New-Object Security.Principal.NTAccount($principalSid)).Translate([Security.Principal.SecurityIdentifier]).Value}catch{$principalSid='unresolved'}}
        if($owned.Actions[0].Execute -eq $powershell -and $owned.Actions[0].Arguments -eq $arguments -and $principalSid -eq 'S-1-5-19'){
            if($owned.State -eq 'Running'){Stop-ScheduledTask -TaskName $name}
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
        }else{throw 'Regression task ownership changed; task was not removed.'}
    }
}
exit 0
