param([switch]$PrintOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if ($PrintOnly) {
    Get-Content -LiteralPath (Join-Path $projectRoot 'RESUME-CODEX.md')
    return
}
$codexCommand = Get-Command codex.exe -ErrorAction SilentlyContinue
$codexPath = if ($codexCommand) { $codexCommand.Source } else { 'C:\Users\LOVE\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe' }
if (-not (Test-Path -LiteralPath $codexPath -PathType Leaf)) { throw 'Existing Codex CLI not found; no installation was attempted.' }
& $codexPath -C $projectRoot 'Read RESUME-CODEX.md and its referenced preservation/handoff files. Verify current repository, environment, artifacts and service ownership, then resume the highest-priority unfinished objective under UNENDLESS CODING MODE. A6 preflight is prepared only; never begin by applying the installer.'
exit $LASTEXITCODE
