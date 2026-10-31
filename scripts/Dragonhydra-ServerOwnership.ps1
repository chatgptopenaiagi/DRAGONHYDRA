# Shared ownership checks for the project-local development launchers.
# This file never starts or stops a process.
function Assert-DragonhydraProjectPath([string]$Path,[string]$ProjectRoot) {
    $full=[IO.Path]::GetFullPath($Path)
    $root=[IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\','/')
    if(-not $full.StartsWith($root+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Development paths must stay inside the project.'
    }
    $cursor=$full
    while($cursor.Length -gt $root.Length) {
        if(Test-Path -LiteralPath $cursor) {
            $item=Get-Item -LiteralPath $cursor -Force
            if($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Development launch paths cannot traverse links or junctions.' }
        }
        $cursor=Split-Path $cursor -Parent
    }
    return $full
}

function Resolve-DragonhydraServer([string]$ProjectRoot,[string]$State,[string]$ServerBinary) {
    if(-not $State) { $State=Join-Path $ProjectRoot 'runtime\product' }
    $statePath=Assert-DragonhydraProjectPath $State $ProjectRoot
    if(-not $ServerBinary) {
        $python=Join-Path $ProjectRoot 'runtime\server-env\Scripts\python.exe'
        if(-not(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Project server environment is missing. See the verified build/status record for setup.' }
        $basePython=(& $python -I -B -c 'import sys; print(sys._base_executable)').Trim()
        if($LASTEXITCODE -ne 0 -or -not $basePython) { throw 'The existing project Python runtime could not be verified.' }
        return [pscustomobject]@{mode='source';state=$statePath;executable=$python;base_python=$basePython;source_content_sha256=$null}
    }
    $binary=Assert-DragonhydraProjectPath $ServerBinary $ProjectRoot
    $payload=Split-Path $binary -Parent
    $dist=Split-Path $payload -Parent
    $build=Split-Path $dist -Parent
    $buildBoundary=(Join-Path $ProjectRoot 'build\connections')+[IO.Path]::DirectorySeparatorChar
    if([IO.Path]::GetFileName($binary) -cne 'DRAGONHYDRA-Server.exe' -or
       (Split-Path $payload -Leaf) -cne 'DRAGONHYDRA-Server-x64' -or (Split-Path $dist -Leaf) -cne 'dist' -or
       -not $build.StartsWith($buildBoundary,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'ServerBinary must select a verified connector development payload beneath build\connections.'
    }
    $report=Get-Content -LiteralPath (Join-Path $build 'BUILD-REPORT.json') -Raw | ConvertFrom-Json
    $info=Get-Content -LiteralPath (Join-Path $payload 'BUILD-INFO.json') -Raw | ConvertFrom-Json
    if($report.status -ne 'verified_current_host' -or [IO.Path]::GetFullPath($report.payload) -ine $payload -or
       $info.build_kind -cne 'connector-development-snapshot' -or $null -ne $info.source_sha -or
       $info.source_content_sha256 -cnotmatch '^[a-f0-9]{64}$' -or
       $info.source_content_sha256 -cne $report.source_content_sha256 -or
       $report.binary_sha256 -cne (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash.ToLowerInvariant()) {
        throw 'The selected server does not match its verified development build identity.'
    }
    # Validate all private-runtime dependencies as well as the EXE. A matching
    # executable beside changed Python/DLL/dashboard bytes is not this payload.
    $manifest=Get-Content -LiteralPath (Join-Path $build 'PAYLOAD-MANIFEST.json') -Raw | ConvertFrom-Json
    $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach($entry in $manifest.files) {
        if(-not $entry.path -or [IO.Path]::IsPathRooted($entry.path) -or -not $seen.Add($entry.path)) { throw 'Invalid or duplicated development payload manifest path.' }
        $path=Assert-DragonhydraProjectPath (Join-Path $payload $entry.path) $ProjectRoot
        if(-not $path.StartsWith($payload+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase) -or
           -not(Test-Path -LiteralPath $path -PathType Leaf) -or
           (Get-Item -LiteralPath $path).Length -ne $entry.bytes -or
           (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.sha256) {
            throw 'The selected development payload failed its file integrity check.'
        }
    }
    if($seen.Count -ne $report.payload_files -or @(Get-ChildItem -LiteralPath $payload -File -Recurse).Count -ne $seen.Count) {
        throw 'The selected development payload contains missing or unexpected files.'
    }
    return [pscustomobject]@{mode='frozen';state=$statePath;executable=$binary;base_python=$null;source_content_sha256=$info.source_content_sha256}
}

function Split-DragonhydraCommandLine([string]$CommandLine) {
    if(-not ('DragonhydraLauncherCommandLine' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DragonhydraLauncherCommandLine {
    [DllImport("shell32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    private static extern IntPtr CommandLineToArgvW(string command, out int count);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
    public static string[] Split(string command) {
        int count; IntPtr ptr=CommandLineToArgvW(command,out count);
        if(ptr==IntPtr.Zero) throw new InvalidOperationException("Cannot parse process arguments.");
        try {
            string[] result=new string[count];
            for(int i=0;i<count;i++) result[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(ptr,i*IntPtr.Size));
            return result;
        } finally { LocalFree(ptr); }
    }
}
'@
    }
    return [DragonhydraLauncherCommandLine]::Split($CommandLine)
}

function Get-DragonhydraOwnedEndpoint($Selection,[switch]$Probe) {
    $endpointFile=Join-Path $Selection.state 'endpoint.json'
    if(-not(Test-Path -LiteralPath $endpointFile -PathType Leaf)) { return $null }
    $endpoint=Get-Content -LiteralPath $endpointFile -Raw | ConvertFrom-Json
    $processId=0
    if(-not [int]::TryParse([string]$endpoint.pid,[ref]$processId) -or $processId -le 0) { throw 'The existing endpoint has an invalid process identity; no server was started or stopped.' }
    $proc=Get-CimInstance Win32_Process -Filter "ProcessId=$processId"
    if(-not $proc) { return $null }
    $tokens=@(Split-DragonhydraCommandLine $proc.CommandLine)
    $valid=$tokens.Count -ge 3 -and $tokens[0] -ieq $Selection.executable
    if($Selection.mode -eq 'source') {
        $valid=$valid -and $proc.ExecutablePath -in @($Selection.executable,$Selection.base_python)
        $modulePositions=@(for($i=0;$i -lt $tokens.Count;$i++) { if($tokens[$i] -ceq '-m') { $i } })
        $valid=$valid -and $modulePositions.Count -eq 1 -and $modulePositions[0]+1 -lt $tokens.Count -and $tokens[$modulePositions[0]+1] -ceq 'dragonhydra.server'
    } else { $valid=$valid -and $proc.ExecutablePath -ieq $Selection.executable }
    $stateArguments=@(for($i=1;$i -lt $tokens.Count;$i++) {
        if($tokens[$i] -ceq '--state' -and $i+1 -lt $tokens.Count) { $tokens[$i+1] }
        elseif($tokens[$i].StartsWith('--state=',[StringComparison]::Ordinal)) { $tokens[$i].Substring(8) }
    })
    $valid=$valid -and $stateArguments.Count -eq 1 -and $stateArguments[0] -ieq $Selection.state
    if(-not $valid) { throw 'Endpoint PID does not belong to the selected server binary and exact state; no process was started or stopped.' }
    $uri=[Uri]$endpoint.url
    if(-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'http' -or $uri.Host -ne '127.0.0.1' -or $uri.UserInfo -or
       $uri.AbsolutePath -notin @('','/') -or $uri.Query -or $uri.Fragment -or $uri.Port -le 0) {
        throw 'Refusing an invalid product loopback endpoint.'
    }
    if($Probe) {
        $token=(Get-Content -LiteralPath (Join-Path $Selection.state 'local-session.json') -Raw | ConvertFrom-Json).token
        $health=Invoke-RestMethod -Uri ($endpoint.url.TrimEnd('/')+'/dragon/api/v1/health/ready') -Headers @{Authorization=('Bearer '+$token)} -TimeoutSec 3
        if($health.status -notin @('ready','ok')) { throw 'The owned server did not return a ready product health response.' }
    }
    return $endpoint
}
