#requires -Version 7.0
[CmdletBinding()]
param([Parameter(Mandatory)][string]$ProfilePath,[Parameter(Mandatory)][string]$BaselinePayloadRoot,
      [Parameter(Mandatory)][string]$BuildRoot,[Parameter(Mandatory)][string]$OutputRoot,
      [Parameter(Mandatory)][string]$ServerPayloadRoot,[Parameter(Mandatory)][string]$ClientPayloadRoot,
      [Parameter(Mandatory)][string]$JoomlaPackagePath,[string]$MakeNsis='C:\Users\LOVE\AppData\Local\tauri\NSIS\makensis.exe')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $project 'packaging\windows\workstation\CoreNextProfile.ps1')
$profile=Read-CoreNextProfile $ProfilePath
if($profile.environment_id -cne 'candidate' -or $profile.version -cne '0.5.0-dev.1'){throw 'CORE_NEXT_CANDIDATE_PACKAGE_PROFILE_REQUIRED'}
$work=Assert-CoreNextOrdinaryPath $BuildRoot $profile.lab_root;$output=Assert-CoreNextOrdinaryPath $OutputRoot $profile.lab_root
if($work -ieq $output -or $work.StartsWith($output+'\',[StringComparison]::OrdinalIgnoreCase) -or $output.StartsWith($work+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'CORE_NEXT_SEPARATE_BUILD_AND_RELEASE_ROOTS_REQUIRED'}
if((Test-Path -LiteralPath $work) -or (Test-Path -LiteralPath $output)){throw 'CORE_NEXT_FRESH_PACKAGE_OUTPUT_REQUIRED'}
$head=(& 'C:\Program Files\Git\cmd\git.exe' -C $project rev-parse HEAD).Trim()
& 'C:\Program Files\Git\cmd\git.exe' -C $project diff --quiet HEAD --
if($LASTEXITCODE -ne 0 -or $head -cne $profile.source_commit){throw 'CORE_NEXT_CLEAN_FROZEN_PACKAGE_SOURCE_REQUIRED'}
New-Item -ItemType Directory -Path $work,$output|Out-Null
$stage=Join-Path $work 'stage'
& (Join-Path $PSScriptRoot 'Prepare-CoreNextPayload.ps1') -ProfilePath $ProfilePath -BaselinePayloadRoot $BaselinePayloadRoot -OutputRoot $stage -ServerPayloadRoot $ServerPayloadRoot -ClientPayloadRoot $ClientPayloadRoot -JoomlaPackagePath $JoomlaPackagePath
$manifestPath=Join-Path $stage 'PAYLOAD-MANIFEST.json'
Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $work 'PRE-INSTANCE-PAYLOAD-MANIFEST.json')
$webManifestPath=Join-Path $stage 'web\payload-manifest.json'
$webManifest=Get-Content -LiteralPath $webManifestPath -Raw|ConvertFrom-Json
$webManifest|Add-Member -NotePropertyName core_next_deployment -NotePropertyValue @{product='DRAGONHYDRA CORE NEXT';edition='CORE NEXT';version=$profile.version;source_commit=$profile.source_commit;scope='Release payload; installation identity is generated during Setup'} -Force
$webManifest|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $webManifestPath -Encoding utf8
$staticManifest=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
$staticManifest.files=@($staticManifest.files|Where-Object {$_.path -cne 'workstation/installer.ini' -and $_.path -cne 'CORE-NEXT-PAYLOAD.json'})
$webEntry=@($staticManifest.files|Where-Object path -CEQ 'web/payload-manifest.json')[0]
$webEntry.sha256=(Get-FileHash -LiteralPath $webManifestPath -Algorithm SHA256).Hash.ToLowerInvariant();$webEntry.bytes=(Get-Item -LiteralPath $webManifestPath).Length
$staticManifest|Add-Member -NotePropertyName kind -NotePropertyValue 'Immutable installer payload; deployment profiles and markers are created only at installation' -Force
$staticManifest|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $manifestPath -Encoding utf8
$prerequisites=Join-Path $BaselinePayloadRoot '$PLUGINSDIR'
$bootstrap=Join-Path $prerequisites 'MicrosoftEdgeWebview2Setup.exe'
$signature=Get-AuthenticodeSignature -LiteralPath $bootstrap
if($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation'){throw 'CORE_NEXT_EXISTING_MICROSOFT_BOOTSTRAPPER_SIGNATURE_REQUIRED'}
$artifact=Join-Path $output ('DRAGONHYDRA-CORE-NEXT-'+$profile.version+'-Workstation-win-x64-Setup.exe')
$args=@('/V3',('/DSTAGE='+$stage),('/DOUTPUT='+$artifact),('/DPREREQUISITES='+$prerequisites),('/DVERSION='+$profile.version),'/DNUMERICVERSION=0.5.0.1',('/DSOURCE_COMMIT='+$profile.source_commit),(Join-Path $project 'packaging\windows\workstation\installer.nsi'))
& $MakeNsis @args 2>&1|Tee-Object -LiteralPath (Join-Path $work 'nsis-build.log')
if($LASTEXITCODE -ne 0 -or -not(Test-Path -LiteralPath $artifact)){throw 'CORE_NEXT_WORKSTATION_PACKAGE_BUILD_FAILED'}
$receipt=@{schema_version=1;status='BUILT';installed=$false;product='DRAGONHYDRA CORE NEXT';version=$profile.version;source_sha=$head;profile_path=$ProfilePath;installation_id=$profile.installation_id;artifact=$artifact;bytes=(Get-Item -LiteralPath $artifact).Length;sha256=(Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant();payload_manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $stage 'PAYLOAD-MANIFEST.json') -Algorithm SHA256).Hash.ToLowerInvariant();baseline_third_party_payload_reused=$true;original_installation_mutated=$false;finished_utc=[DateTime]::UtcNow.ToString('o')}
$receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $output 'WORKSTATION-BUILD.json') -Encoding utf8
$receipt|ConvertTo-Json -Depth 8
