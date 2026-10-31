#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$InstallRoot,
    [Parameter(Mandatory)][string]$StateRoot,
    [Parameter(Mandatory)][string]$ServiceName,
    [Parameter(Mandatory)][string]$Output,
    [ValidateSet('Client','Setup')][string]$Phase='Client',
    [string]$InstallerPath,
    [int]$SetupProcessId,
    [switch]$Unelevated,
    [string]$ExpectedMatchId,
    [string]$ExpectedMatchLabel
)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$testBase=[IO.Path]::GetFullPath((Join-Path $project 'build\workstation\test-install'))+[IO.Path]::DirectorySeparatorChar
$install=[IO.Path]::GetFullPath($InstallRoot)
$state=[IO.Path]::GetFullPath($StateRoot)
foreach($path in @($install,$state)){
    if(-not $path.StartsWith($testBase,[StringComparison]::OrdinalIgnoreCase)){throw 'Native acceptance is restricted to build/workstation/test-install; no live installation is touched.'}
    if($path -match '[\r\n"]'){throw 'Invalid test path.'}
    $ancestor=$path
    while($ancestor -and $ancestor.Length -ge $testBase.TrimEnd('\').Length){
        if(Test-Path -LiteralPath $ancestor){$item=Get-Item -LiteralPath $ancestor -Force;if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Acceptance paths may not traverse a junction or symbolic link.'}}
        $ancestor=Split-Path $ancestor -Parent
    }
}
if($ServiceName -notmatch '^[A-Za-z0-9_.-]{1,120}$'){throw 'Invalid exact service name.'}
$outputPath=[IO.Path]::GetFullPath($Output)
$evidenceBase=[IO.Path]::GetFullPath((Join-Path $project 'build\workstation\evidence'))+[IO.Path]::DirectorySeparatorChar
if(-not $outputPath.StartsWith($evidenceBase,[StringComparison]::OrdinalIgnoreCase)){throw 'Native receipts must stay inside build/workstation/evidence.'}
New-Item -ItemType Directory -Force -Path (Split-Path $outputPath -Parent) | Out-Null
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Drawing
if(-not ('DragonWorkstationWindows' -as [type])){
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public static class DragonWorkstationWindows {
    public delegate bool EnumCallback(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left,Top,Right,Bottom; }
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumCallback callback, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd,StringBuilder text,int count);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd,out Rect rect);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd,IntPtr hdc,uint flags);
    [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr hWnd);
    [DllImport("user32.dll",CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr hWnd,StringBuilder text,int count);
    [DllImport("user32.dll",SetLastError=true)] public static extern bool PostMessage(IntPtr hWnd,uint message,IntPtr wParam,IntPtr lParam);
    [DllImport("oleacc.dll")] public static extern int AccessibleObjectFromWindow(IntPtr window,uint id,ref Guid iid,[MarshalAs(UnmanagedType.Interface)] out object result);
    [DllImport("kernel32.dll",SetLastError=true)] public static extern bool GetExitCodeProcess(IntPtr process,out uint exitCode);
    [DllImport("advapi32.dll",SetLastError=true)] public static extern bool OpenProcessToken(IntPtr process,uint access,out IntPtr token);
    [DllImport("advapi32.dll",SetLastError=true)] public static extern bool GetTokenInformation(IntPtr token,int informationClass,out int information,int informationSize,out int returnSize);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr handle);
    public static bool IsElevated(IntPtr process) {
        IntPtr token;
        if(!OpenProcessToken(process,0x0008,out token)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
        try {
            int elevated,size;
            if(!GetTokenInformation(token,20,out elevated,4,out size)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            return elevated!=0;
        } finally { CloseHandle(token); }
    }
    public static bool ClickOwnedButton(IntPtr handle,int pid) {
        uint owner; GetWindowThreadProcessId(handle,out owner);
        var name=new StringBuilder(128);GetClassName(handle,name,name.Capacity);
        if(owner!=(uint)pid || name.ToString()!="Button" || !IsWindowEnabled(handle)) return false;
        // Activation is queued because Install may legitimately run for minutes.
        // The caller verifies actual subsequent page/state, never queueing as success.
        return PostMessage(handle,0x00F5,IntPtr.Zero,IntPtr.Zero);
    }
    public static IntPtr Find(int pid,string title,int minWidth,int minHeight,bool exact) {
        IntPtr found=IntPtr.Zero;
        EnumWindows((handle,unused)=>{
            uint owner; GetWindowThreadProcessId(handle,out owner);
            if(owner!=(uint)pid || !IsWindowVisible(handle)) return true;
            var text=new StringBuilder(512);GetWindowText(handle,text,text.Capacity);
            string name=text.ToString();
            if(exact ? name!=title : name.IndexOf(title,StringComparison.OrdinalIgnoreCase)<0) return true;
            Rect rect; if(!GetWindowRect(handle,out rect)) return true;
            if(rect.Right-rect.Left<minWidth || rect.Bottom-rect.Top<minHeight) return true;
            found=handle;return false;
        },IntPtr.Zero);
        return found;
    }
}
'@
}
$checks=[Collections.Generic.List[object]]::new()
$result=[ordered]@{schema_version=1;started_at=[DateTime]::UtcNow.ToString('o');phase=$Phase;install_root=$install;state_root=$state;service_name=$ServiceName;passed=$false;checks=$checks;driver='Microsoft UI Automation and Win32 named-window geometry';clean_machine_test=$false;requested_unelevated=[bool]$Unelevated}
$window=$null;$client=$null;$launcher=$null;$setup=$null;$clientHandle=[IntPtr]::Zero
function Wait-Window([int]$ProcessId,[string]$Title,[int]$Width,[int]$Height,[bool]$Exact,[int]$Seconds=40){
    $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
    do{
        $hwnd=[DragonWorkstationWindows]::Find($ProcessId,$Title,$Width,$Height,$Exact)
        if($hwnd -ne [IntPtr]::Zero){return $hwnd}
        Start-Sleep -Milliseconds 150
    }while([DateTime]::UtcNow -lt $deadline)
    throw "No normal-sized named native window appeared for owned PID $ProcessId."
}
function Find-Named([string]$Name){
    $window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::NameProperty,$Name))
}
function Wait-Named([string]$Name,[int]$Seconds=30){
    $deadline=[DateTime]::UtcNow.AddSeconds($Seconds)
    do{$control=Find-Named $Name;if($control){return $control};Start-Sleep -Milliseconds 150}while([DateTime]::UtcNow -lt $deadline)
    throw "Installed native control did not appear: $Name"
}
function Invoke-Control($Control){
    $pattern=$null
    if($Control.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)){$pattern.Invoke()}
    elseif($Control.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$pattern)){$pattern.Select()}
    elseif($Control.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern,[ref]$pattern)){$pattern.Expand()}
    elseif($Phase -eq 'Setup' -and $setup -and $Control.Current.ClassName -eq 'Button' -and $Control.Current.NativeWindowHandle -ne 0){
        # NSIS's standard HWND buttons can be exposed as UIA Pane with no patterns.
        # BM_CLICK is allowed only for an enabled native Button owned by this exact installer PID.
        if(-not [DragonWorkstationWindows]::ClickOwnedButton([IntPtr]$Control.Current.NativeWindowHandle,$setup.Id)){throw 'The exact installer-owned native button could not be activated.'}
    }
    else{throw 'The visible native control exposes no supported activation pattern.'}
    Start-Sleep -Milliseconds 180
}
function Invoke-Named([string]$Name){Invoke-Control (Wait-Named $Name)}
function Save-Screenshot([string]$Suffix){
    try{
    $bounds=$window.Current.BoundingRectangle
    if($bounds.Width -lt 400 -or $bounds.Height -lt 300){throw 'Refusing a startup-placeholder screenshot.'}
    $bitmap=[Drawing.Bitmap]::new([int]$bounds.Width,[int]$bounds.Height)
    $graphics=[Drawing.Graphics]::FromImage($bitmap)
    try{
        # Never capture the desktop or steal focus: the user may be working in another window.
        $hdc=$graphics.GetHdc()
        try{$captured=[DragonWorkstationWindows]::PrintWindow([IntPtr]$window.Current.NativeWindowHandle,$hdc,2)}finally{$graphics.ReleaseHdc($hdc)}
        if(-not $captured){$result.native_capture='PrintWindow unsupported; native UI Automation assertions are retained without visual proof';return $null}
        $path=Join-Path (Split-Path $outputPath -Parent) $Suffix
        $bitmap.Save($path,[Drawing.Imaging.ImageFormat]::Png)
        $result.native_capture='Owned-window PrintWindow only; WebView compositor contents are not independently validated. Native UI Automation is the interaction evidence.'
        return $path
    }
    finally{$graphics.Dispose();$bitmap.Dispose()}
    }catch{
        $result.capture_errors=@($result.capture_errors)+$_.Exception.Message
        return $null
    }
}
function Get-OwnedClient {
    $binary=Join-Path $install 'client\DRAGONHYDRA-Client.exe'
    @(Get-CimInstance Win32_Process -Filter "Name='DRAGONHYDRA-Client.exe'" | Where-Object {$_.ExecutablePath -eq $binary -and $_.CommandLine.Contains((Join-Path $state 'client'))})
}
function Read-SetupDetails {
    $list=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)|Where-Object {$_.Current.ClassName -eq 'SysListView32' -and $_.Current.ProcessId -eq $setup.Id}|Select-Object -First 1
    if(-not $list){return @()}
    $guid=[Guid]'618736E0-3C3D-11CF-810C-00AA00389B71'
    $accessible=$null
    $code=[DragonWorkstationWindows]::AccessibleObjectFromWindow([IntPtr]$list.Current.NativeWindowHandle,[uint32]4294967292,[ref]$guid,[ref]$accessible)
    if($code -ne 0){return @()}
    $type=$accessible.GetType()
    $count=$type.InvokeMember('accChildCount',[Reflection.BindingFlags]::GetProperty,$null,$accessible,@())
    $lines=[Collections.Generic.List[string]]::new()
    $result.installer_details_total_children=$count
    $indices=@(1..([Math]::Min($count,20)))+@(([Math]::Max(21,$count-99))..$count)|Where-Object {$_ -ge 1 -and $_ -le $count}|Sort-Object -Unique
    foreach($index in $indices){
        try{$line=$type.InvokeMember('accName',[Reflection.BindingFlags]::GetProperty,$null,$accessible,[object[]]@([int]$index));if($line){$lines.Add(([string]$index)+': '+[string]$line)}}catch{}
    }
    $result.installer_details_retention='First20 and last100 accessible items; gap omitted when total exceeds120.'
    return @($lines)
}
try{
    if($Unelevated -and $Phase -ne 'Client'){throw 'Unelevated mode applies only to the installed client, never to setup or service operations.'}
    if($Phase -eq 'Setup'){
        if(-not $InstallerPath -or -not(Test-Path -LiteralPath $InstallerPath -PathType Leaf)){throw 'Setup UI phase requires the actual installer artifact.'}
        $result.installer=[IO.Path]::GetFullPath($InstallerPath)
        $result.installer_sha256=(Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $before=@(Get-OwnedClient | Select-Object -ExpandProperty ProcessId)
        # NSIS /D must be last and consumes the remaining unquoted directory text.
        $arguments='/STATE="'+$state+'" /SERVICE='+$ServiceName+' /D='+$install
        if($SetupProcessId){
            $owned=Get-CimInstance Win32_Process -Filter ("ProcessId="+$SetupProcessId)
            if(-not $owned -or $owned.ExecutablePath -ne [IO.Path]::GetFullPath($InstallerPath)){throw 'Attach PID is not the exact selected installer artifact.'}
            if(-not $owned.CommandLine.Contains($install) -or -not $owned.CommandLine.Contains($state) -or -not $owned.CommandLine.Contains('/SERVICE='+$ServiceName)){throw 'Attach PID does not declare this exact isolated installation, state, and service.'}
            $setup=Get-Process -Id $SetupProcessId
            $result.attached_existing_installer=$true
        }else{$setup=Start-Process -FilePath $InstallerPath -ArgumentList $arguments -PassThru}
        $handle=Wait-Window $setup.Id 'DRAGONHYDRA' 400 300 $false 40
        $window=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
        $checks.Add(@{name='actual-installer-native-ui';passed=$true;pid=$setup.Id})
        $actions=[Collections.Generic.List[string]]::new()
        $deadline=[DateTime]::UtcNow.AddMinutes(8)
        $finished=$false
        while([DateTime]::UtcNow -lt $deadline -and -not $finished){
            $setup.Refresh()
            if($setup.HasExited){break}
            if(-not $window.Current.IsEnabled -and (Find-Named 'OK')){
                $messages=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)|Where-Object {$_.Current.ClassName -eq 'Static' -and $_.Current.IsEnabled -and $_.Current.Name.Length -gt 10}|ForEach-Object {$_.Current.Name}|Select-Object -Unique
                $result.installer_details=Read-SetupDetails
                throw ('The owned installer opened a blocking modal: '+($messages -join ' '))
            }
            $activated=$false
            foreach($name in @('Finish','&Finish','Install','&Install','I Agree','I &Agree','Next >','&Next >','Next','&Next')){
                $button=Find-Named $name
                if($button -and $button.Current.IsEnabled){
                    $actions.Add($name)
                    Invoke-Control $button
                    $activated=$true
                    if($name -match 'Finish'){$finished=$true}
                    break
                }
            }
            if(-not $activated){Start-Sleep -Milliseconds 300}
        }
        if(-not $finished){$result.failure_screenshot=Save-Screenshot 'workstation-setup-failure.png';throw 'Installer did not reach and activate its Finish page.'}
        if(-not $setup.WaitForExit(30000)){throw 'Installer did not exit after Finish.'}
        if($setup.ExitCode -ne 0){throw "Installer returned exit $($setup.ExitCode)."}
        if(-not($actions|Where-Object {$_ -match 'Install'})){throw 'No actual Install control was exercised.'}
        $checks.Add(@{name='installer-next-install-finish';passed=$true;actions=@($actions);exit_code=$setup.ExitCode})
        $deadline=[DateTime]::UtcNow.AddSeconds(65)
        do{$candidate=Get-OwnedClient|Where-Object {$_.ProcessId -notin $before}|Select-Object -First 1;if($candidate){$client=Get-Process -Id $candidate.ProcessId;$clientHandle=$client.Handle;break};Start-Sleep -Milliseconds 200}while([DateTime]::UtcNow -lt $deadline)
        if(-not $client){throw 'Installer Finish did not launch the installed main application.'}
        $handle=Wait-Window $client.Id 'DRAGONHYDRA' 600 400 $true 45
        $window=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
        Wait-Named 'Browse retained matches' 45 | Out-Null
        $checks.Add(@{name='finish-default-launch-opens-ready-main-application';passed=$true;pid=$client.Id;normal_window=$true})
        $result.screenshot=Save-Screenshot 'workstation-setup-main.png'
    }else{
        $svc=Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
        if(-not $svc -or $svc.State -ne 'Running' -or -not $svc.PathName.Replace('/','\').ToLowerInvariant().Contains($install.ToLowerInvariant()) -or -not $svc.PathName.Replace('/','\').ToLowerInvariant().Contains($state.ToLowerInvariant())){throw 'The exact test-owned installed service is not running with the expected isolated paths.'}
        $before=@(Get-OwnedClient|Select-Object -ExpandProperty ProcessId)
        $launcherPath=Join-Path $install 'workstation\DragonhydraLauncher.exe'
        if(-not(Test-Path -LiteralPath $launcherPath)){throw 'Installed main launcher is missing.'}
        $suffix=if($ServiceName -eq 'DragonhydraWorkstation'){''}else{' - '+$ServiceName}
        $shortcutPath=Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) ('DRAGONHYDRA Workstation'+$suffix+'.lnk')
        if(-not(Test-Path -LiteralPath $shortcutPath -PathType Leaf)){throw 'The installed main desktop shortcut is missing.'}
        $shell=New-Object -ComObject WScript.Shell
        try{
            $shortcut=$shell.CreateShortcut($shortcutPath)
            if($shortcut.TargetPath -ne $launcherPath -or $shortcut.Arguments -ne ('--state "'+$state+'"')){throw 'The installed desktop shortcut does not belong to this exact isolated launcher and state.'}
        }finally{[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)}
        $checks.Add(@{name='actual-main-desktop-shortcut-target-and-state';passed=$true;shortcut=[IO.Path]::GetFileName($shortcutPath)})
        # Launch the installed shortcut itself, rather than bypassing it with the EXE.
        if($Unelevated){
            try{
                $explorerShell=New-Object -ComObject Shell.Application
                $shellWindows=$explorerShell.Windows()
                $desktopHandle=0
                $desktop=$shellWindows.FindWindowSW(0,0,8,[ref]$desktopHandle,1)
                if(-not $desktop){throw 'Existing Explorer desktop broker is unavailable.'}
                $brokerOwner=[uint32]0
                [void][DragonWorkstationWindows]::GetWindowThreadProcessId([IntPtr]$desktopHandle,[ref]$brokerOwner)
                $brokerProcess=Get-Process -Id $brokerOwner
                if($brokerProcess.ProcessName -ne 'explorer' -or [DragonWorkstationWindows]::IsElevated($brokerProcess.Handle)){throw 'The existing Explorer desktop broker is not an unelevated Explorer process.'}
                $result.launch_broker=@{method='Existing Explorer desktop IShellDispatch ShellExecute';pid=$brokerOwner;token_elevated=$false;desktop_hwnd=$desktopHandle}
                $desktop.Document.Application.ShellExecute($shortcutPath,'','','open',1)
            }catch{
                $result.status='not_run'
                $result.not_run='Unelevated Explorer launch could not be established; no UAC or operating-system setting was changed.'
                throw
            }
        }else{Start-Process -FilePath $shortcutPath | Out-Null}
        $deadline=[DateTime]::UtcNow.AddSeconds(65)
        do{$candidate=Get-OwnedClient|Where-Object {$_.ProcessId -notin $before}|Select-Object -First 1;if($candidate){$client=Get-Process -Id $candidate.ProcessId;$clientHandle=$client.Handle;break};Start-Sleep -Milliseconds 200}while([DateTime]::UtcNow -lt $deadline)
        if(-not $client){throw 'Installed launcher did not create its configured installed client.'}
        $result.driver_token_elevated=[DragonWorkstationWindows]::IsElevated([Diagnostics.Process]::GetCurrentProcess().Handle)
        $result.client_token_elevated=[DragonWorkstationWindows]::IsElevated($clientHandle)
        if($Unelevated -and $result.client_token_elevated){throw 'Explorer launch produced an elevated client; ordinary-user execution was not verified.'}
        $result.client_binary=$candidate.ExecutablePath
        $result.client_sha256=(Get-FileHash -LiteralPath $candidate.ExecutablePath -Algorithm SHA256).Hash.ToLowerInvariant()
        $handle=Wait-Window $client.Id 'DRAGONHYDRA' 600 400 $true 45
        $window=[System.Windows.Automation.AutomationElement]::FromHandle($handle)
        $bounds=$window.Current.BoundingRectangle
        $checks.Add(@{name='normal-native-client-window';passed=$true;pid=$client.Id;title=$window.Current.Name;width=$bounds.Width;height=$bounds.Height;startup_16x16_rejected=$true})
        Wait-Named 'Browse retained matches' 45 | Out-Null
        Invoke-Named 'Browse retained matches'
        $deadline=[DateTime]::UtcNow.AddSeconds(30)
        do{
            $nodes=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
            $match=$nodes|Where-Object {$_.Current.Name.StartsWith('Open match:') -and (-not $ExpectedMatchLabel -or $_.Current.Name -eq $ExpectedMatchLabel)}|Select-Object -First 1
            if(-not $match){Start-Sleep -Milliseconds 150}
        }while(-not $match -and [DateTime]::UtcNow -lt $deadline)
        if(-not $match){throw 'Installed client did not display the expected real match.'}
        $result.selected_match=$match.Current.Name
        Invoke-Control $match
        Wait-Named 'Open standings'|Out-Null
        if($ExpectedMatchId){Invoke-Named 'Technical details';Wait-Named $ExpectedMatchId|Out-Null}
        $checks.Add(@{name='installed-native-canonical-match';passed=$true;match_id=$ExpectedMatchId})
        $buttons=$window.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.PropertyCondition]::new([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::Button))
        $team=$buttons|Where-Object {$_.Current.Name.StartsWith('View team ')}|Select-Object -First 1
        if(-not $team){throw 'Native team action is missing.'}
        Invoke-Control $team
        Wait-Named 'Recent form'|Out-Null
        Invoke-Named '← Return to selected match'
        Invoke-Named 'Open standings'
        Wait-Named 'RECONSTRUCTED'|Out-Null
        Invoke-Named '← Return to selected match'
        Wait-Named 'Open standings'|Out-Null
        $checks.Add(@{name='installed-native-team-standings-back-context';passed=$true})
        Invoke-Named 'View model probabilities'
        Wait-Named 'Explain this match'|Out-Null
        Invoke-Named 'Explain this match'
        Wait-Named 'DETERMINISTIC EVIDENCE SUMMARY' 45|Out-Null
        $checks.Add(@{name='installed-native-model-explanation-job';passed=$true})
        $result.analysis_screenshot=Save-Screenshot 'workstation-native-analysis.png'
        Invoke-Named 'Overview'
        $exportRoot=Join-Path $state 'kernel\exports'
        $oldFiles=@(Get-ChildItem -LiteralPath $exportRoot -Filter '*.xlsx' -File -ErrorAction SilentlyContinue|Select-Object -ExpandProperty FullName)
        Invoke-Named 'Export to Excel'
        Wait-Named 'Report ready' 45|Out-Null
        Wait-Named 'Download Excel report'|Out-Null
        $created=Get-ChildItem -LiteralPath $exportRoot -Filter '*.xlsx' -File|Where-Object {$_.FullName -notin $oldFiles}|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
        if(-not $created){throw 'The native Export action did not create its workbook in this installed state.'}
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $book=[IO.Compression.ZipFile]::OpenRead($created.FullName)
        try{$entry=$book.GetEntry('xl/worksheets/sheet1.xml');if(-not $entry){throw 'Native export is not an Excel worksheet.'};$reader=[IO.StreamReader]::new($entry.Open());try{$sheet=$reader.ReadToEnd()}finally{$reader.Dispose()};if($ExpectedMatchId -and -not $sheet.Contains($ExpectedMatchId)){throw 'Native export belongs to another match.'}}finally{$book.Dispose()}
        $checks.Add(@{name='installed-native-export-action-real-workbook';passed=$true;filename=$created.Name;sha256=(Get-FileHash -LiteralPath $created.FullName -Algorithm SHA256).Hash.ToLowerInvariant();native_download_dialog='not invoked; same installed dashboard browser download is tested separately'})
        $result.screenshot=Save-Screenshot 'workstation-native-export.png'
    }
    $result.passed=$true
}catch{
    $result.error=$_.Exception.Message
    if($window){try{$result.failure_screenshot=Save-Screenshot 'workstation-native-failure.png'}catch{}}
    throw
}finally{
    if($client){
        $client.Refresh()
        if(-not $client.HasExited){
            $client.CloseMainWindow()|Out-Null
            if(-not $client.WaitForExit(12000)){
                $result.client_exit='close requested; process did not exit before deadline'
                $result.passed=$false
                if(-not $result.error){$result.error='The owned installed client did not exit gracefully before the deadline; no process was killed.'}
            }else{
                $nativeExit=[uint32]0
                if($clientHandle -eq [IntPtr]::Zero -or -not [DragonWorkstationWindows]::GetExitCodeProcess($clientHandle,[ref]$nativeExit)){
                    $result.client_exit='unknown';$result.passed=$false
                    if(-not $result.error){$result.error='The owned client closed, but an actual exit code could not be observed; no zero code is assumed.'}
                }else{
                    $result.client_exit='graceful';$result.client_exit_code=$nativeExit
                    $result.client_exit_observation='Win32 GetExitCodeProcess using a handle acquired while the exact client was alive'
                    if($nativeExit -ne 0){$result.passed=$false;if(-not $result.error){$result.error='The owned installed client exited with an observed nonzero code.'}}
                }
            }
        }else{$result.client_exit='already exited';$result.client_exit_code=$client.ExitCode;$result.passed=$false;if(-not $result.error){$result.error='The owned installed client exited before the normal close check.'}}
    }
    $result.finished_at=[DateTime]::UtcNow.ToString('o')
    $result|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $outputPath -Encoding utf8
    $result|ConvertTo-Json -Depth 8
}
if(-not $result.passed){exit 1}
