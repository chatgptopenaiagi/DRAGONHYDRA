#requires -Version 7.0
[CmdletBinding()]
param([string]$Version='2026.10.6')
$ErrorActionPreference='Stop'
$deploymentRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolRoot=Join-Path $deploymentRoot 'cloudflare'
$binary=Join-Path $toolRoot 'bin\cloudflared.exe'
$receiptFile=Join-Path $toolRoot 'install-receipt.json'
New-Item -ItemType Directory -Path (Split-Path $binary -Parent) -Force | Out-Null
if(Test-Path -LiteralPath $receiptFile){
    $receipt=Get-Content -LiteralPath $receiptFile -Raw|ConvertFrom-Json
    if($Version -and $receipt.release -ne $Version){throw 'A verified project cloudflared version is already present. Version replacement requires an explicit upgrade workflow.'}
    if(-not(Test-Path -LiteralPath $binary) -or (Get-FileHash -LiteralPath $binary -Algorithm SHA256).Hash -ne $receipt.sha256){throw 'Previously verified project cloudflared binary is missing or changed.'}
    $receipt|ConvertTo-Json -Depth 7
    return
}
$api=if($Version){'https://api.github.com/repos/cloudflare/cloudflared/releases/tags/'+[Uri]::EscapeDataString($Version)}else{'https://api.github.com/repos/cloudflare/cloudflared/releases/latest'}
$release=Invoke-RestMethod -Uri $api -Headers @{'User-Agent'='DRAGONHYDRA-public-demo';Accept='application/vnd.github+json'} -TimeoutSec 30
$asset=@($release.assets|Where-Object {$_.name -eq 'cloudflared-windows-amd64.exe'})
if($asset.Count -ne 1){throw 'Official release does not contain exactly one Windows amd64 executable.'}
$asset=$asset[0]
if($asset.browser_download_url -notlike 'https://github.com/cloudflare/cloudflared/releases/download/*/cloudflared-windows-amd64.exe'){throw 'Unexpected cloudflared artifact origin.'}
$expected=$null
$digestSource=$null
if($asset.digest -match '^sha256:([a-fA-F0-9]{64})$'){$expected=$Matches[1].ToUpperInvariant();$digestSource='GitHub release asset digest'}
if($release.body -match 'cloudflared-windows-amd64\.exe:\s*([a-fA-F0-9]{64})'){
    $bodyHash=$Matches[1].ToUpperInvariant()
    if($expected -and $expected -ne $bodyHash){throw 'Official release checksum sources disagree.'}
    $expected=$bodyHash;$digestSource=if($digestSource){'GitHub release asset digest and release SHA256 checksums'}else{'Release SHA256 checksums'}
}
if(-not $expected){throw 'Official release has no usable SHA-256 for the Windows executable.'}
$release|ConvertTo-Json -Depth 20|Set-Content -LiteralPath (Join-Path $toolRoot 'release-metadata.json') -Encoding utf8
$part=Join-Path $toolRoot 'bin\cloudflared.download.exe'
Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $part -TimeoutSec 90
$actual=(Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash
if($actual -ne $expected){throw 'Cloudflared downloaded bytes do not match the official SHA-256.'}
$signature=Get-AuthenticodeSignature -LiteralPath $part
if([string]$signature.Status -eq 'HashMismatch'){throw 'Cloudflared executable signature reports a hash mismatch.'}
Move-Item -LiteralPath $part -Destination $binary
$versionOutput=(& $binary --version 2>&1|Out-String).Trim()
if($LASTEXITCODE -ne 0 -or $versionOutput -notlike ('*'+$release.tag_name+'*')){throw 'Downloaded cloudflared version execution does not match its release.'}
$receipt=@{
    schema_version=1;installed_at=[DateTime]::UtcNow.ToString('o');release=$release.tag_name
    executable=$binary;version_output=$versionOutput;architecture='windows-amd64';bytes=(Get-Item -LiteralPath $binary).Length
    sha256=$actual;expected_sha256=$expected;checksum_source=$digestSource;release_api=$api
    upstream_release=$release.html_url;artifact_url=$asset.browser_download_url
    authenticode=@{status=[string]$signature.Status;signer=if($signature.SignerCertificate){$signature.SignerCertificate.Subject}else{$null}}
    scope='Project-local binary; no global install, service registration, network adapter or VPN change'
}
$receipt|ConvertTo-Json -Depth 7|Set-Content -LiteralPath $receiptFile -Encoding utf8
$receipt|ConvertTo-Json -Depth 7

