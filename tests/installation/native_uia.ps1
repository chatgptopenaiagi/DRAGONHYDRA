#requires -Version 7.0
[CmdletBinding()]
param([string]$Binary,[string]$State,[string]$Output)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if(-not $Binary){$Binary=Join-Path $projectRoot 'dist\DRAGONHYDRA-Client-x64.exe'}
if(-not $State){$State=Join-Path $projectRoot 'runtime\product'}
if(-not $Output){$Output=Join-Path $projectRoot 'runtime\evidence\installation\native-uia.json'}
New-Item -ItemType Directory -Path (Split-Path $Output -Parent) -Force|Out-Null
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
$checks=[Collections.Generic.List[object]]::new()
$app=$null
$result=@{binary=$Binary;sha256=(Get-FileHash -LiteralPath $Binary -Algorithm SHA256).Hash;driver='Microsoft UI Automation (.NET UIAutomationClient)';scope='Compiled Windows native Tauri/WebView2 client; accessible controls invoked through native accessibility API';checks=$checks;passed=$false}
function Find-Named([string]$Name){$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$Name))}
function Wait-Named([string]$Name,[int]$Seconds=20){$deadline=[DateTime]::UtcNow.AddSeconds($Seconds);do{$found=Find-Named $Name;if($found){return $found};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline);throw "Native control did not appear: $Name"}
function Invoke-Named([string]$Name){$control=Wait-Named $Name;$pattern=$control.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern);$pattern.Invoke();Start-Sleep -Milliseconds 250}
try {
    $app=Start-Process -FilePath $Binary -ArgumentList ('--state="'+$State+'"') -PassThru
    $deadline=[DateTime]::UtcNow.AddSeconds(20)
    do{Start-Sleep -Milliseconds 200;$app.Refresh()}while(-not $app.MainWindowHandle -and [DateTime]::UtcNow -lt $deadline)
    if(-not $app.MainWindowHandle){throw 'Native application window did not appear.'}
    $window=[System.Windows.Automation.AutomationElement]::FromHandle($app.MainWindowHandle)
    Wait-Named 'Browse retained matches'|Out-Null
    $checks.Add(@{name='native-window-server-pairing';passed=$true})
    Invoke-Named 'Browse retained matches'
    $deadline=[DateTime]::UtcNow.AddSeconds(15)
    do{
        $nodes=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
        $match=$nodes|Where-Object {$_.Current.Name.StartsWith('Open match:')}|Select-Object -First 1
        if(-not $match){Start-Sleep -Milliseconds 200}
    }while(-not $match -and [DateTime]::UtcNow -lt $deadline)
    if(-not $match){throw 'Real retained match control not found.'}
    $matchName=$match.Current.Name
    $match.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    Wait-Named 'Open standings'|Out-Null
    $checks.Add(@{name='native-open-real-match';passed=$true;match=$matchName})
    Invoke-Named 'Open standings'
    Wait-Named 'RECONSTRUCTED'|Out-Null
    $checks.Add(@{name='native-standings-navigation';passed=$true})
    Invoke-Named '← Return to selected match'
    Wait-Named 'Open standings'|Out-Null
    $checks.Add(@{name='native-return-to-selected-match';passed=$true})
    Invoke-Named 'View model probabilities'
    Wait-Named 'Explain this match'|Out-Null
    Invoke-Named 'Explain this match'
    Wait-Named 'DETERMINISTIC EVIDENCE SUMMARY' 30|Out-Null
    $checks.Add(@{name='native-explanation-job-visible';passed=$true})
    $bounds=$window.Current.BoundingRectangle
    $bitmap=[Drawing.Bitmap]::new([int]$bounds.Width,[int]$bounds.Height)
    $graphics=[Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen([int]$bounds.Left,[int]$bounds.Top,0,0,$bitmap.Size)
    $screen=[IO.Path]::ChangeExtension($Output,'.png')
    $bitmap.Save($screen,[Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose();$bitmap.Dispose()
    $result.passed=$true;$result.screenshot=$screen;$result.pid=$app.Id
} catch {$result.error=$_.Exception.Message;throw}
finally {
    if($app -and -not $app.HasExited){$app.CloseMainWindow()|Out-Null}
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $Output -Encoding utf8
    $result | ConvertTo-Json -Depth 7
}
