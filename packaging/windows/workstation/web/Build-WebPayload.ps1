[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputRoot,
    [string]$ExtensionPath,
    [Parameter(Mandatory)][string]$SourceSha,
    [Parameter(Mandatory)][string]$Version,
    [string]$ApacheRoot = 'C:\xampp\apache',
    [string]$MariaDbRoot = 'C:\xampp\mysql',
    [string]$PhpArchive,
    [string]$JoomlaArchive
)
$ErrorActionPreference = 'Stop'
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
if (-not $ExtensionPath) {
    $componentVersion = ([xml](Get-Content -LiteralPath (Join-Path $project 'server\joomla\pkg_dragonhydra.xml') -Raw)).extension.version
    $ExtensionPath = Join-Path $project ('dist\pkg_dragonhydra-'+$componentVersion+'.zip')
}
if (-not (Test-Path -LiteralPath $ExtensionPath -PathType Leaf)) { throw 'Build scripts/build_joomla.py first, or supply the verified current frontend package with -ExtensionPath.' }
if (-not $PhpArchive) { $PhpArchive = Join-Path $project 'runtime\scratch\joomla-integration\downloads\php-8.4.27-1-Win32-vs17-x64.zip' }
if (-not $JoomlaArchive) { $JoomlaArchive = Join-Path $project 'runtime\scratch\joomla-integration\downloads\Joomla_6-2-0-Stable-Full_Package.zip' }
$arguments = @('-3.14', '-B', (Join-Path $PSScriptRoot 'prepare_payload.py'),
    '--destination', ([IO.Path]::GetFullPath($OutputRoot)),
    '--apache-root', ([IO.Path]::GetFullPath($ApacheRoot)),
    '--mariadb-root', ([IO.Path]::GetFullPath($MariaDbRoot)),
    '--php-zip', ([IO.Path]::GetFullPath($PhpArchive)),
    '--joomla-zip', ([IO.Path]::GetFullPath($JoomlaArchive)),
    '--extension', ([IO.Path]::GetFullPath($ExtensionPath)), '--source-sha', $SourceSha, '--version', $Version)
& py @arguments
if ($LASTEXITCODE -ne 0) { throw "Private web payload preparation failed with exit code $LASTEXITCODE." }
