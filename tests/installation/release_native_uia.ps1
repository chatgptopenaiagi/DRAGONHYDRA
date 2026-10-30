#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Binary,
    [Parameter(Mandatory)][string]$State,
    [Parameter(Mandatory)][string]$Output,
    [ValidateSet('journey','unpaired','rejected')][string]$Mode='journey',
    [string]$ServerState
)
$ErrorActionPreference='Stop'
New-Item -ItemType Directory -Path (Split-Path $Output -Parent) -Force|Out-Null
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
$checks=[Collections.Generic.List[object]]::new()
$app=$null
$profile=Join-Path (Split-Path $Output -Parent) ('webview-'+[Guid]::NewGuid().ToString('N'))
$result=@{binary=$Binary;sha256=(Get-FileHash -LiteralPath $Binary -Algorithm SHA256).Hash.ToLowerInvariant();mode=$Mode;driver='Microsoft UI Automation';profile=$profile;test_state=$State;scope='Actual compiled native client and isolated server/profile; current Windows host, not clean-machine testing';checks=$checks;passed=$false;started_at=[DateTime]::UtcNow.ToString('o')}
function Find-Named([string]$Name){$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$Name))}
function Wait-Named([string]$Name,[int]$Seconds=25){$deadline=[DateTime]::UtcNow.AddSeconds($Seconds);do{$found=Find-Named $Name;if($found){return $found};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline);throw "Native control did not appear: $Name"}
function Invoke-Named([string]$Name){
    $control=Wait-Named $Name;$pattern=$null
    if($control.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)){$pattern.Invoke()}
    elseif($control.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$pattern)){$pattern.Select()}
    else{throw "Native control has no supported activation pattern: $Name"}
    Start-Sleep -Milliseconds 250
}
function Set-Value([string]$Name,[string]$Value){
    $condition=[System.Windows.Automation.AndCondition]::new(
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$Name),
        [System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Edit))
    $control=$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$condition)
    if(-not $control){throw "Native editable control did not appear: $Name"}
    $pattern=$null
    if($control.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)){$pattern.SetValue($Value)}
    else{
        Add-Type -AssemblyName System.Windows.Forms
        $control.SetFocus()
        [System.Windows.Forms.SendKeys]::SendWait('^a')
        [System.Windows.Forms.SendKeys]::SendWait($Value)
    }
}
function Snapshot([string]$Suffix){
    $bounds=$window.Current.BoundingRectangle
    $bitmap=[Drawing.Bitmap]::new([int]$bounds.Width,[int]$bounds.Height)
    $graphics=[Drawing.Graphics]::FromImage($bitmap)
    try{$graphics.CopyFromScreen([int]$bounds.Left,[int]$bounds.Top,0,0,$bitmap.Size);$bitmap.Save(([IO.Path]::ChangeExtension($Output,$null)+'-'+$Suffix+'.png'),[Drawing.Imaging.ImageFormat]::Png)}finally{$graphics.Dispose();$bitmap.Dispose()}
}
try{
    $app=Start-Process -FilePath $Binary -ArgumentList @('--state="'+$State+'"','--profile="'+$profile+'"') -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(25)
    do{Start-Sleep -Milliseconds 200;$app.Refresh()}while(-not $app.MainWindowHandle -and [DateTime]::UtcNow -lt $deadline)
    if(-not $app.MainWindowHandle){throw 'Native application window did not appear.'}
    $window=[System.Windows.Automation.AutomationElement]::FromHandle($app.MainWindowHandle)
    if($Mode -eq 'unpaired' -or $Mode -eq 'rejected'){
        Wait-Named 'Connect to your server'|Out-Null
        Wait-Named 'Server address (optional when opened from your server)'|Out-Null
        Wait-Named 'Pairing token'|Out-Null
        $checks.Add(@{name=if($Mode -eq 'unpaired'){'native-first-run-connection-fields'}else{'native-rejected-token-pairing-recovery'};passed=$true})
        if($ServerState){
            $endpoint=Get-Content -LiteralPath (Join-Path $ServerState 'endpoint.json') -Raw|ConvertFrom-Json
            $session=Get-Content -LiteralPath (Join-Path $ServerState 'local-session.json') -Raw|ConvertFrom-Json
            Set-Value 'Server address (optional when opened from your server)' $endpoint.url
            Set-Value 'Pairing token' $session.token
            Invoke-Named 'Connect'
            Wait-Named 'Browse retained matches'|Out-Null
            $checks.Add(@{name='native-system-server-address-and-token-entry';passed=$true})
        }
    }else{
        Wait-Named 'Browse retained matches'|Out-Null
        $checks.Add(@{name='native-window-server-pairing';passed=$true})
        Invoke-Named 'Browse retained matches'
        $deadline=[DateTime]::UtcNow.AddSeconds(20)
        do{
            $nodes=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
            $match=$nodes|Where-Object {$_.Current.Name.StartsWith('Open match:')}|Select-Object -First 1
            if(-not $match){Start-Sleep -Milliseconds 200}
        }while(-not $match -and [DateTime]::UtcNow -lt $deadline)
        if(-not $match){throw 'Retained match control not found.'}
        $matchName=$match.Current.Name
        $match.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        Wait-Named 'Open standings'|Out-Null
        $checks.Add(@{name='native-open-real-match';passed=$true;match=$matchName})
        Invoke-Named 'Open standings'
        Wait-Named 'RECONSTRUCTED'|Out-Null
        Invoke-Named '← Return to selected match'
        Wait-Named 'Open standings'|Out-Null
        $checks.Add(@{name='native-same-match-standings-and-return';passed=$true})
        Invoke-Named 'View model probabilities'
        Wait-Named 'Explain this match'|Out-Null
        Invoke-Named 'Explain this match'
        Wait-Named 'DETERMINISTIC EVIDENCE SUMMARY' 35|Out-Null
        $checks.Add(@{name='native-evidence-explanation-job';passed=$true})
        Snapshot 'analysis'
        Invoke-Named 'Overview'
        Invoke-Named 'Export to Excel'
        Wait-Named 'Report ready' 35|Out-Null
        Wait-Named 'Download Excel report'|Out-Null
        $checks.Add(@{name='native-excel-export-control-and-ready-link';passed=$true;note='Workbook fetched and verified by the release runner; no user Downloads directory used.'})
    }
    Snapshot 'final'
    $result.passed=$true
}catch{$result.error=$_.Exception.Message;throw}
finally{
    if($app -and -not $app.HasExited){$app.CloseMainWindow()|Out-Null;if(-not $app.WaitForExit(15000)){$result.clean_exit=$false;$result.passed=$false;$result.error='Test-owned native client did not exit after CloseMainWindow.'}else{$result.clean_exit=($app.ExitCode -eq 0);$result.exit_code=$app.ExitCode}}
    $result.finished_at=[DateTime]::UtcNow.ToString('o')
    $result|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $Output -Encoding utf8
    $result|ConvertTo-Json -Depth 8
}
