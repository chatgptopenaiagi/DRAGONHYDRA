#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$ProfilePath,[Parameter(Mandatory)][string]$BaselinePayloadRoot,
      [string]$OutputRoot,[string]$ServerPayloadRoot,[string]$ClientPayloadRoot,[string]$JoomlaPackagePath)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $project 'packaging\windows\workstation\CoreNextProfile.ps1')
$profile=Read-CoreNextProfile $ProfilePath -CheckService
$lab=$profile.lab_root
if(-not $OutputRoot){$OutputRoot=$profile.install_root}
$destination=Assert-CoreNextOrdinaryPath $OutputRoot $lab
if(Test-Path -LiteralPath $destination){throw 'CORE_NEXT_FRESH_PAYLOAD_DESTINATION_REQUIRED'}
$baseline=Assert-CoreNextOrdinaryPath $BaselinePayloadRoot $lab
if($destination.StartsWith($baseline+'\',[StringComparison]::OrdinalIgnoreCase) -or $baseline.StartsWith($destination+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'CORE_NEXT_PAYLOAD_SOURCE_DESTINATION_OVERLAP'}
function Hash([string]$path){(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Read-VerifiedPayload([string]$root,[string]$manifestName='PAYLOAD-MANIFEST.json'){
    $null=Assert-CoreNextOrdinaryPath $root $lab
    $manifestPath=Assert-CoreNextOrdinaryPath (Join-Path $root $manifestName) $lab
    $manifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
    $entries=@($manifest.files);$seen=@{}
    $python=Join-Path $lab 'tools-env\Scripts\python.exe'
    $checked=& $python -I (Join-Path $PSScriptRoot 'verify_core_next_payload.py') --root $root --lab $lab
    if($LASTEXITCODE -ne 0 -or -not($checked|ConvertFrom-Json).verified){throw 'CORE_NEXT_PAYLOAD_VERIFICATION_FAILED'}
    return [pscustomobject]@{root=$root;manifest=$manifest;manifest_sha256=(Hash $manifestPath);entries=$entries}

}
$base=Read-VerifiedPayload $baseline
foreach($required in @('server\DRAGONHYDRA-Server.exe','client\DRAGONHYDRA-Client.exe','workstation\DragonhydraService.exe','web\manage.php','web\payload-manifest.json')){if(-not(Test-Path -LiteralPath (Join-Path $baseline $required))){throw 'CORE_NEXT_BASELINE_COMPONENT_MISSING'}}
if($profile.environment_id -eq 'candidate' -and (-not $ServerPayloadRoot -or -not $ClientPayloadRoot -or -not $JoomlaPackagePath)){throw 'CORE_NEXT_CANDIDATE_SOURCE_PAYLOADS_REQUIRED'}
$overrides=@{}
foreach($pair in @(@('server',$ServerPayloadRoot),@('client',$ClientPayloadRoot))){
    if(-not $pair[1]){continue};$owned=Assert-CoreNextOrdinaryPath $pair[1] $lab
    if($owned -ieq $destination -or $owned.StartsWith($destination+'\',[StringComparison]::OrdinalIgnoreCase) -or $destination.StartsWith($owned+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'CORE_NEXT_CANDIDATE_PAYLOAD_OVERLAP'}
    $verified=Read-VerifiedPayload $owned
    $identity=Get-Content -LiteralPath (Join-Path $owned 'BUILD-INFO.json') -Raw|ConvertFrom-Json
    if($identity.source_sha -cne $profile.source_commit -or $identity.version -cne $profile.version -or $identity.api_namespace -cne '/dragon/api/v1' -or $identity.schema_version -ne 1){throw 'CORE_NEXT_CANDIDATE_BUILD_IDENTITY_MISMATCH'}
    $overrides[$pair[0]]=$verified
}
$extension=$null
if($JoomlaPackagePath){
    $extension=Assert-CoreNextOrdinaryPath $JoomlaPackagePath $lab
    $receiptPath=Assert-CoreNextOrdinaryPath ([IO.Path]::ChangeExtension($extension,'.manifest.json')) $lab
    $receipt=Get-Content -LiteralPath $receiptPath -Raw|ConvertFrom-Json
    if($receipt.built -isnot [bool] -or -not $receipt.built -or $receipt.version -cne $profile.version -or $receipt.source_sha -cne $profile.source_commit -or $receipt.sha256 -cne (Hash $extension) -or $receipt.bytes -ne (Get-Item -LiteralPath $extension).Length){throw 'CORE_NEXT_JOOMLA_PACKAGE_IDENTITY_MISMATCH'}
    # A same-version sidecar must not relabel an older embedded component.
    function Read-CoreNextJoomlaText($archive,[string]$name){
        $entries=@($archive.Entries|Where-Object FullName -IEQ $name)
        if($entries.Count -ne 1 -or $entries[0].FullName -cne $name -or $entries[0].Length -gt 65536){throw 'UNIQUE_BOUNDED_JOOMLA_ENTRY_REQUIRED'}
        $reader=[IO.StreamReader]::new($entries[0].Open())
        try{return $reader.ReadToEnd()}finally{$reader.Dispose()}
    }
    function Read-CoreNextJoomlaVersion($archive,[string]$name){
        $text=Read-CoreNextJoomlaText $archive $name
        $settings=[Xml.XmlReaderSettings]::new();$settings.DtdProcessing=[Xml.DtdProcessing]::Prohibit;$settings.XmlResolver=$null
        $reader=[Xml.XmlReader]::Create([IO.StringReader]::new($text),$settings)
        try{
            $xml=[Xml.XmlDocument]::new();$xml.XmlResolver=$null;$xml.Load($reader)
            $versions=$xml.SelectNodes('/extension/version')
            if($versions.Count -ne 1){throw 'UNIQUE_JOOMLA_VERSION_REQUIRED'}
            return $versions[0].InnerText
        }finally{$reader.Dispose()}
    }
    $package=$component=$componentBytes=$componentStream=$identityReader=$null
    try{
        $package=[IO.Compression.ZipFile]::OpenRead($extension)
        if((Read-CoreNextJoomlaVersion $package 'pkg_dragonhydra.xml') -cne $profile.version){throw 'PACKAGE_VERSION_MISMATCH'}
        $parts=@($package.Entries|Where-Object FullName -IEQ 'constituents/com_dragonhydra.zip')
        if($parts.Count -ne 1 -or $parts[0].FullName -cne 'constituents/com_dragonhydra.zip' -or $parts[0].Length -gt 16777216){throw 'COMPONENT_IDENTITY_REQUIRED'}
        $componentBytes=[IO.MemoryStream]::new()
        $componentStream=$parts[0].Open();$componentStream.CopyTo($componentBytes);$componentStream.Dispose();$componentStream=$null
        $componentBytes.Position=0
        $component=[IO.Compression.ZipArchive]::new($componentBytes,[IO.Compression.ZipArchiveMode]::Read)
        if((Read-CoreNextJoomlaVersion $component 'dragonhydra.xml') -cne $profile.version){throw 'COMPONENT_VERSION_MISMATCH'}
        $identities=@($component.Entries|Where-Object FullName -IEQ 'admin/build-info.json')
        if($identities.Count -ne 1 -or $identities[0].FullName -cne 'admin/build-info.json' -or $identities[0].Length -gt 65536){throw 'COMPONENT_IDENTITY_REQUIRED'}
        $identityReader=[IO.StreamReader]::new($identities[0].Open())
        $embedded=$identityReader.ReadToEnd()|ConvertFrom-Json
        if($embedded.source_sha -cne $profile.source_commit -or $embedded.version -cne $profile.version -or $embedded.api_namespace -cne '/dragon/api/v1' -or ($embedded.kernel_schema_version -isnot [int] -and $embedded.kernel_schema_version -isnot [long]) -or $embedded.kernel_schema_version -ne 1){throw 'COMPONENT_IDENTITY_MISMATCH'}
    }catch{throw 'CORE_NEXT_JOOMLA_EMBEDDED_IDENTITY_MISMATCH'}finally{
        foreach($resource in @($identityReader,$component,$componentStream,$componentBytes,$package)){if($null -ne $resource){$resource.Dispose()}}
    }
}
# Inputs are completely checked before a fresh destination is created.
$python=Join-Path $lab 'tools-env\Scripts\python.exe'
$copyArgs=@('-B',(Join-Path $PSScriptRoot 'verify_core_next_payload.py'),'--root',$baseline,'--lab',$lab,'--destination',$destination)
foreach($component in $overrides.Keys){$copyArgs+=@('--exclude-component',$component)}
& $python @copyArgs
if($LASTEXITCODE){throw 'CORE_NEXT_BASELINE_COPY_FAILED'}
foreach($component in $overrides.Keys){
    & $python -B (Join-Path $PSScriptRoot 'verify_core_next_payload.py') --root $overrides[$component].root --lab $lab --destination (Join-Path $destination $component)
    if($LASTEXITCODE){throw 'CORE_NEXT_CANDIDATE_COPY_FAILED'}
}
$runtime=Join-Path $destination 'workstation'
& (Join-Path $project 'packaging\windows\workstation\Build-Runtime.ps1') -OutputRoot $runtime
if($LASTEXITCODE){throw 'CORE_NEXT_DEPLOYMENT_RUNTIME_BUILD_FAILED'}
Copy-Item -LiteralPath (Join-Path $project 'packaging\windows\workstation\CoreNext-InstallerChecks.ps1') -Destination (Join-Path $runtime 'Installer-Checks.ps1') -Force
foreach($file in @('manage.php','CoreNextProfile.php','README.md')){Copy-Item -LiteralPath (Join-Path $project ('packaging\windows\workstation\web\'+$file)) -Destination (Join-Path $destination ('web\'+$file)) -Force}
if($extension){Copy-Item -LiteralPath $extension -Destination (Join-Path $destination 'web\extension.zip') -Force}
$ini="[Product]`r`nIdentity=DRAGONHYDRA CORE NEXT v1`r`nInstallRoot=$($profile.install_root)`r`nStateRoot=$($profile.state_root)`r`nServiceName=$($profile.service_name)`r`nInstallationId=$($profile.installation_id)`r`nProfilePath=$ProfilePath`r`nShortcutName=$($profile.shortcut_name)`r`nUninstallId=$($profile.uninstall_id)`r`nVersion=$($profile.version)`r`n"
[IO.File]::WriteAllText((Join-Path $runtime 'installer.ini'),$ini,[Text.Encoding]::Unicode)
& $python -B (Join-Path $PSScriptRoot 'finalize_core_next_payload.py') --profile $ProfilePath --output $destination --baseline $baseline
if($LASTEXITCODE){throw 'CORE_NEXT_PAYLOAD_FINALIZATION_FAILED'}


