#requires -Version 7.0
[CmdletBinding()]
param([ValidateSet('Preview','ReconcileForecast','Backup','Restart','Repair','UninstallRetain','ReinstallRetained','FinalUninstall')][string]$Phase='Preview',[switch]$Apply,[switch]$ValidateOnly,
 [Alias('Bindings')][string]$BindingsPath,[string]$ExpectedBindingsSha256,[string]$ReconciliationReceipt,[string]$ExpectedReconciliationSha256,[string]$CoordinatorApproval,[string]$ExpectedApprovalSha256)
$ErrorActionPreference='Stop';$PSNativeCommandUseErrorActionPreference=$false
$newRoot='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\continuation-20261103\disposable-dev5-b447-reconciled-r1'
$forensic='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\forensics\forecast-preservation-20261103';$old='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\continuation-20261102\disposable-dev5-lifecycle-r1'
function Assert-StringWalk([string]$Path,[string]$Root,[switch]$Leaf){
    if(-not[IO.Path]::IsPathRooted($Path) -or $Path -match '(?:^|[\\/])\.\.(?:[\\/]|$)' -or $Path.IndexOfAny([char[]]"`"`r`n") -ge 0 -or $Path.Substring(2).Contains(':')){throw 'ORDINARY_ABSOLUTE_PATH_REQUIRED'}
    $full=[IO.Path]::GetFullPath($Path);if(-not $full.StartsWith($Root.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'PATH_OUTSIDE_BOUND_ROOT'}
    for($walk=$full;$walk;){if((Test-Path -LiteralPath $walk) -and ((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'REPARSE_ANCESTOR_REJECTED'};$next=Split-Path -Path $walk -Parent;if($next -eq $walk){break};$walk=$next}
    if($Leaf -and -not(Test-Path -LiteralPath $full -PathType Leaf)){throw 'BOUND_FILE_REQUIRED'};$full
}
function Digest([string]$Path){(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
function Import-ExactFunctions([string]$Path,[string]$Sha,[string[]]$Names){
    $allowedRoot=if($Path.StartsWith('C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB\',[StringComparison]::OrdinalIgnoreCase)){'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB'}elseif($Path.StartsWith('C:\xampp\DRAGONHYDRA-CORE-NEXT\',[StringComparison]::OrdinalIgnoreCase)){'C:\xampp\DRAGONHYDRA-CORE-NEXT'}else{throw 'FUNCTION_SOURCE_OUTSIDE_APPROVED_ROOT'}
    $Path=Assert-StringWalk $Path $allowedRoot -Leaf
    if((Digest $Path) -cne $Sha){throw 'AUDITED_FUNCTION_SOURCE_CHANGED'}
    $tokens=$null;$errors=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($Path,[ref]$tokens,[ref]$errors);if($errors.Count){throw 'AUDITED_FUNCTION_PARSE_FAILED'}
    foreach($name in $Names){$nodes=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true));if($nodes.Count -ne 1){throw 'EXACT_FUNCTION_REQUIRED'}
        $target=if($name -ceq 'Save-PrivateJson'){'Save-AuditedPrivateJson'}else{$name}
        $text=[regex]::Replace($nodes[0].Extent.Text,('^function\s+'+[regex]::Escape($name)+'(?=[\s({])'),('function script:'+$target),1)
        Invoke-Expression $text # Verified full function definition only; no original script statements.
    }
}
if(-not$Apply -and -not$ValidateOnly){@{status='PREVIEW_ONLY_NOT_EXECUTED';operation_id='dev5-b447-forecast-reconciled-20261103-r1';operation_root=$newRoot;implemented_for_review=@('ReconcileForecast','Backup');not_implemented=@('Restart','Repair','UninstallRetain','ReinstallRetained','FinalUninstall');original_forecast_status='FAIL';actions_performed=$false;gui='BLOCKED_NO_NATIVE_LAUNCH';live_sql_restore='NOT_RUN';bindings_required=$true}|ConvertTo-Json;return}
if($Phase -ceq 'Preview'){throw 'EXPLICIT_PHASE_REQUIRED'}
if($Phase -cin @('Restart','Repair','UninstallRetain','ReinstallRetained','FinalUninstall')){throw 'NOT_IMPLEMENTED_BEFORE_MARKER'}
$BindingsPath=Assert-StringWalk $BindingsPath $forensic -Leaf;if($ExpectedBindingsSha256 -cnotmatch '^[a-f0-9]{64}$' -or (Digest $BindingsPath) -cne $ExpectedBindingsSha256){throw 'ROOT_REVIEWED_BINDINGS_REQUIRED'}
$newBindings=Get-Content -LiteralPath $BindingsPath -Raw|ConvertFrom-Json
if($newBindings.schema_version -cne 'dev5.forecast-continuation-code-bindings/1' -or $newBindings.operation_id -cne 'dev5-b447-forecast-reconciled-20261103-r1' -or $newBindings.installation_id -cne 'core-next-b447d99ab9524197af09c235077685de' -or $newBindings.source_commit -cne 'ed78fab282599a181d4254ab65a2fc2eaa5b7f50' -or $newBindings.setup_sha256 -cne '8d5a790ac54b4cca3c51d08746db80a5551c211474bcdead7dc86a44b3a8e553'){throw 'EXACT_NEW_CODE_BINDINGS_REQUIRED'}
foreach($pair in @(@($PSCommandPath,$newBindings.new_controller_sha256),@((Join-Path $PSScriptRoot 'continuation_contract.py'),$newBindings.contract_sha256),@((Join-Path $PSScriptRoot 'Read-Continuation.py'),$newBindings.reader_sha256))){$null=Assert-StringWalk $pair[0] $forensic -Leaf;if((Digest $pair[0]) -cne $pair[1]){throw 'NEW_REVIEWED_CODE_CHANGED'}}
$oldPlanPath=Assert-StringWalk (Join-Path $old 'PLAN.json') 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB' -Leaf
$oldBindingPath=Assert-StringWalk (Join-Path $old 'BINDINGS.json') 'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB' -Leaf
if((Digest $oldPlanPath) -cne '5bcf53a0077440d7537e659bc94b5cf3dbb5e29ae1428d207b19a5f8a4a47b7c' -or (Digest $oldBindingPath) -cne 'df0260dd0f54a5bab7a3e62e6359259da5db7db9572c366aabf67b43f87cc2c7'){throw 'ORIGINAL_CONTROLS_CHANGED'}
$plan=Get-Content -LiteralPath $oldPlanPath -Raw|ConvertFrom-Json
$identity=[Security.Principal.WindowsIdentity]::GetCurrent();if($identity.User.Value -cne $plan.owner_sid){throw 'MATCHING_ORIGINAL_OWNER_REQUIRED'}
if($Phase -cne 'ReconcileForecast' -and -not([Security.Principal.WindowsPrincipal]::new($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'MATCHING_ELEVATED_OWNER_REQUIRED'}
$lab='C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB';$python=Join-Path $lab 'tools-env\Scripts\python.exe';$ps5=Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
Set-Variable -Name operation -Scope Script -Value $newRoot -Option ReadOnly
$oldBindings=Get-Content -LiteralPath $oldBindingPath -Raw|ConvertFrom-Json
Set-Variable -Name bindings -Scope Script -Value $oldBindings -Option ReadOnly # Explicit immutable compatibility binding for exact imported functions.
if((Digest (Join-Path $old 'BINDINGS.json')) -cne 'df0260dd0f54a5bab7a3e62e6359259da5db7db9572c366aabf67b43f87cc2c7' -or (Digest (Join-Path $old 'PLAN.json')) -cne '5bcf53a0077440d7537e659bc94b5cf3dbb5e29ae1428d207b19a5f8a4a47b7c'){throw 'ORIGINAL_CONTROLS_CHANGED'}
Import-ExactFunctions $oldBindings.profile_helper $oldBindings.profile_helper_sha256 @('Assert-CoreNextOrdinaryPath','Assert-CoreNextProfile','Read-CoreNextProfile','Assert-CoreNextConfig')
Import-ExactFunctions $oldBindings.upgrade_helper $oldBindings.upgrade_helper_sha256 @('Invoke-CoreNextBackupCopy','Copy-CoreNextProtectedBackup')
Import-ExactFunctions (Join-Path $old 'Invoke-Dev5Phase.ps1') '125748d3a31714f02c0c47c3218573cf948e1d5018af465e424c0d045276d6fd' @('Hash','Assert-OperationFile','Save-PrivateJson','Assert-Protected','Assert-BackupMember','Assert-NoDisposableGui','Assert-Installed')
Import-ExactFunctions (Join-Path $old 'Backup-Disposable.ps1') 'b42c3ea720026872077f9db9c92d4370e0c2246fb6d55123cfae1d830b336178' @('Backup-Dev5Disposable')
# Override only new-context path/receipt/write bindings; old files are never modified.
function Assert-OperationFile([string]$Path){Assert-StringWalk $Path $operation -Leaf}
function Assert-CoreNextOrdinaryPath([string]$Path,[string]$Root){Assert-StringWalk $Path $Root}
function Save-PrivateJson([string]$Path,$Value){$Path=Assert-StringWalk $Path $operation;Save-AuditedPrivateJson $Path $Value}
function Save-Phase([string]$Stage){$record.stage=$Stage;$record.observed_at=[DateTime]::UtcNow.ToString('o');Save-PrivateJson (Join-Path $operation ('phase-'+$Phase+'.json')) $record}
$aliases=@{ReconcileForecast='reconcile';Backup='backup';Restart='restart';Repair='repair';UninstallRetain='uninstalled';ReinstallRetained='reinstalled';FinalUninstall='final-uninstalled'}
function Assert-Receipt($r){if($r.schema_version -cne 'dev5.forecast-continuation-readback/1' -or $r.passed -isnot [bool] -or -not$r.passed -or $r.operation_id -cne 'dev5-b447-forecast-reconciled-20261103-r1' -or $r.installation_id -cne $plan.installation_id -or $r.expected_source -cne $plan.source_commit -or $r.version -cne $plan.version -or $r.setup_sha256 -cne $plan.setup_sha256 -or $r.helper_sha256 -cne $newBindings.reader_sha256 -or $r.reconciliation_sha256 -cne $ExpectedReconciliationSha256 -or $r.approval_sha256 -cne $ExpectedApprovalSha256){throw 'NEW_SUCCESSFUL_READER_RECEIPT_REQUIRED'}}
function Read-Predecessor([string]$Name){
    $path=Assert-OperationFile (Join-Path $operation ('phase-'+$Name+'.json'));$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json
    if($r.schema_version -cne 'dev5.forecast-continuation-phase/1' -or $r.operation_id -cne 'dev5-b447-forecast-reconciled-20261103-r1' -or $r.passed -isnot [bool] -or -not$r.passed -or $r.stage -cne 'passed' -or $r.phase -cne $Name -or $r.source_commit -cne $plan.source_commit -or $r.installation_id -cne $plan.installation_id -or $r.setup_sha256 -cne $plan.setup_sha256 -or $r.bindings_sha256 -cne $ExpectedBindingsSha256){throw 'NEW_SUCCESSFUL_PREDECESSOR_REQUIRED'}
    $a=Assert-OperationFile $r.acceptance.path;if($a -ine (Join-Path $operation ('acceptance\'+$aliases[$Name]+'\verification.json')) -or (Hash $a) -cne $r.acceptance.sha256){throw 'PREDECESSOR_ACCEPTANCE_CHANGED'}
    $v=Get-Content -LiteralPath $a -Raw|ConvertFrom-Json;Assert-Receipt $v;if($v.phase -cne $aliases[$Name]){throw 'NEW_PREDECESSOR_PHASE_REQUIRED'};$r
}
function Run-Acceptance([string]$Name,$Previous){
    $out=Assert-StringWalk (Join-Path $operation ('acceptance\'+$Name)) $operation;if(Test-Path -LiteralPath $out){throw 'FRESH_READER_OUTPUT_REQUIRED'}
    $arguments=@('-I','-B',(Join-Path $PSScriptRoot 'Read-Continuation.py'),'--receipt',$ReconciliationReceipt,'--receipt-sha256',$ExpectedReconciliationSha256,'--approval',$CoordinatorApproval,'--approval-sha256',$ExpectedApprovalSha256,'--phase',$Name,'--output',$out)
    if($Previous){$arguments+=@('--previous',$Previous.acceptance.path)}
    & $python @arguments *> (Join-Path $operation ($Name+'.private.log'));if($LASTEXITCODE){throw 'NEW_READBACK_FAILED_NO_RETRY'}
    $path=Assert-OperationFile (Join-Path $out 'verification.json');$r=Get-Content -LiteralPath $path -Raw|ConvertFrom-Json;Assert-Receipt $r;if($r.phase -cne $Name){throw 'REQUESTED_READER_PHASE_MISMATCH'}
    $record.acceptance=@{path=$path;sha256=(Hash $path)};$path
}
function Assert-BackupSources{
    $stack=[Collections.Generic.Stack[string]]::new();$stack.Push($p.install_root)
    foreach($relative in @('kernel\raw','kernel\exports','kernel\vault')){$path=Join-Path $p.state_root $relative;if(Test-Path -LiteralPath $path){$stack.Push($path)}}
    $count=0
    while($stack.Count){$path=$stack.Pop();$null=Assert-StringWalk $path $lab;$item=Get-Item -LiteralPath $path -Force;if(++$count -gt 25000){throw 'BOUNDED_BACKUP_INVENTORY_REQUIRED'};if($item.PSIsContainer){foreach($child in Get-ChildItem -LiteralPath $path -Force){$stack.Push($child.FullName)}}}
    foreach($relative in @('workstation.json','first-run.json','client\local-session.json','kernel\product.json','kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json','web-config\httpd.conf','web-config\php.ini','web-config\my.ini','web-config\extension-installed.json','site\configuration.php')){$path=Join-Path $p.state_root $relative;if(Test-Path -LiteralPath $path){$null=Assert-StringWalk $path $lab -Leaf}}
}
function Assert-NewBackupIntegrity{
    $root=Join-Path $operation 'private-backup';$integrity=Assert-OperationFile (Join-Path $root 'backup-integrity.json')
    if($record.backup.passed -isnot [bool] -or -not$record.backup.passed -or $record.backup.path -cne $root -or (Hash $integrity) -cne $record.backup.integrity_sha256){throw 'VERIFIED_NEW_BACKUP_REQUIRED'}
    $proof=Get-Content -LiteralPath $integrity -Raw|ConvertFrom-Json
    foreach($pair in @(@('original-profile.json',$proof.profile_sha256),@('runtime-manifest.json',$proof.runtime_manifest_sha256),@('state-file-manifest.json',$proof.state_file_manifest_sha256),@('state-tree-manifest.json',$proof.state_tree_manifest_sha256),@('core.sqlite3',$proof.sqlite_sha256),@('joomla-and-reserved-core.sql',$proof.sql_sha256))){if((Hash (Assert-OperationFile (Join-Path $root $pair[0]))) -cne $pair[1]){throw 'NEW_BACKUP_PROOF_CHANGED'}}
    $runtime=Get-Content -LiteralPath (Join-Path $root 'runtime-manifest.json') -Raw|ConvertFrom-Json
    if(-not$runtime.files -or @($runtime.files).Count -lt 1){throw 'RUNTIME_BACKUP_MEMBERS_REQUIRED'}
    foreach($m in $runtime.files){Assert-BackupMember (Join-Path $root 'application-before') $m.path $m.sha256 $m.bytes}
    $state=Get-Content -LiteralPath (Join-Path $root 'state-file-manifest.json') -Raw|ConvertFrom-Json
    if(-not$state.files -or @($state.files).Count -lt 1){throw 'STATE_BACKUP_MEMBERS_REQUIRED'}
    foreach($m in $state.files){Assert-BackupMember (Join-Path $root 'state-files') $m.path $m.sha256 $m.bytes}
    foreach($m in $state.protected_backup_copies){if($m.path -cnotin @('kernel\local-session.json','kernel\joomla-bridge.json','kernel\local-ai.json')){throw 'EXACT_PROTECTED_BACKUP_MEMBER_REQUIRED'};Assert-BackupMember (Join-Path $root 'state-files') $m.path $m.backup_sha256 $m.bytes}
    $trees=Get-Content -LiteralPath (Join-Path $root 'state-tree-manifest.json') -Raw|ConvertFrom-Json
    foreach($tree in $trees.trees){if($tree.path -cnotin @('kernel\raw','kernel\exports','kernel\vault')){throw 'EXACT_STATE_TREE_REQUIRED'};foreach($m in $tree.files){Assert-BackupMember (Join-Path (Join-Path $root 'state-trees') $tree.path) $m.path $m.sha256 $m.bytes}}
}
$p=Read-CoreNextProfile $plan.profile -CheckService
if($p.installation_id -cne 'core-next-b447d99ab9524197af09c235077685de' -or $p.source_commit -cne 'ed78fab282599a181d4254ab65a2fc2eaa5b7f50' -or $p.version -cne '0.5.0-dev.5' -or $p.ports.api -ne 18860 -or $p.ports.web -ne 18861 -or $p.ports.database -ne 18862 -or (Hash $plan.profile) -cne $plan.profile_sha256 -or (Hash $plan.setup) -cne $plan.setup_sha256){throw 'EXACT_ORIGINAL_DISPOSABLE_BINDING_REQUIRED'}
if($Phase -cne 'ReconcileForecast'){
    $firstPath=Assert-OperationFile (Join-Path $operation 'phase-ReconcileForecast.json');$first=Get-Content -LiteralPath $firstPath -Raw|ConvertFrom-Json
    $ReconciliationReceipt=$first.reconciliation.path;$ExpectedReconciliationSha256=$first.reconciliation.sha256;$CoordinatorApproval=$first.approval.path;$ExpectedApprovalSha256=$first.approval.sha256
}
$proofArgs=@('-I','-B',(Join-Path $PSScriptRoot 'continuation_contract.py'),'--receipt',$ReconciliationReceipt,'--receipt-sha256',$ExpectedReconciliationSha256,'--approval',$CoordinatorApproval,'--approval-sha256',$ExpectedApprovalSha256)
$proof=& $python @proofArgs;if($LASTEXITCODE -or -not($proof|ConvertFrom-Json).passed){throw 'SEMANTIC_ROOT_PREREQUISITES_REQUIRED'}
$acl=Get-Acl -LiteralPath $forensic;$allowed=@($plan.owner_sid,'S-1-5-18','S-1-5-32-544');if(-not$acl.AreAccessRulesProtected -or @($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|Where-Object {$_.AccessControlType -ne 'Allow' -or $_.IdentityReference.Value -notin $allowed}).Count){throw 'OWNER_RESTRICTED_APPROVAL_EVIDENCE_REQUIRED'}
Assert-Protected;Assert-NoDisposableGui
$previous=$null;$parents=@{Backup='ReconcileForecast'}
if($parents.ContainsKey($Phase)){$previous=Read-Predecessor $parents[$Phase]}
if($Phase -ceq 'ReconcileForecast'){
    Assert-Installed;if(Test-Path -LiteralPath $operation){throw 'NEW_OPERATION_ALREADY_EXISTS_NO_RETRY'}
    if($ValidateOnly){
        $validationArgs=@('-I','-B',(Join-Path $PSScriptRoot 'Read-Continuation.py'),'--receipt',$ReconciliationReceipt,'--receipt-sha256',$ExpectedReconciliationSha256,'--approval',$CoordinatorApproval,'--approval-sha256',$ExpectedApprovalSha256,'--phase','reconcile','--output',(Join-Path $operation 'acceptance\reconcile'),'--validate-only')
        $validation=& $python @validationArgs;if($LASTEXITCODE){throw 'READONLY_FULL_PREFLIGHT_FAILED'};$v=$validation|ConvertFrom-Json
        if($v.passed -isnot [bool] -or -not$v.passed -or $v.validate_only -ne $true -or $v.output_created -ne $false -or $v.installation_id -cne $plan.installation_id -or $v.expected_source -cne $plan.source_commit){throw 'TYPED_FULL_PREFLIGHT_RESULT_REQUIRED'}
        Assert-Protected;@{status='VALIDATED_ONLY_NO_OPERATION_OUTPUT';passed=$true;operation_id=$v.operation_id;installation_id=$v.installation_id;source_commit=$v.expected_source;api_methods=@('GET');operation_directory_created=$false;phase_marker_created=$false}|ConvertTo-Json;return
    }
    $null=Assert-StringWalk (Join-Path $operation 'new-root-check') $lab;New-Item -ItemType Directory -Path $operation -Force|Out-Null;Set-Acl -LiteralPath $operation -AclObject $acl
}else{Assert-Installed;if($ValidateOnly){throw 'VALIDATE_ONLY_SUPPORTED_FOR_INITIAL_RECONCILE_ONLY'}}
$operationAcl=Get-Acl -LiteralPath $operation
if(-not$operationAcl.AreAccessRulesProtected -or @($operationAcl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])|Where-Object {$_.AccessControlType -ne 'Allow' -or $_.IdentityReference.Value -notin $allowed}).Count){throw 'OWNER_RESTRICTED_NEW_OPERATION_REQUIRED'}
$marker=Assert-StringWalk (Join-Path $operation ($Phase+'.started.lock')) $operation;$lock=[IO.File]::Open($marker,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
$record=[ordered]@{schema_version='dev5.forecast-continuation-phase/1';operation_id='dev5-b447-forecast-reconciled-20261103-r1';phase=$Phase;source_commit=$plan.source_commit;installation_id=$plan.installation_id;setup_sha256=$plan.setup_sha256;bindings_sha256=$ExpectedBindingsSha256;reconciliation=@{path=$ReconciliationReceipt;sha256=$ExpectedReconciliationSha256};approval=@{path=$CoordinatorApproval;sha256=$ExpectedApprovalSha256};operation_acl_verified=$true;original_forecast_status='FAIL';passed=$false;stage='claimed';started_at=[DateTime]::UtcNow.ToString('o');automatic_retry=$false;gui='BLOCKED_NO_NATIVE_ACTION';live_sql_restore='NOT_RUN'}
try{
    $claim=[Text.Encoding]::UTF8.GetBytes((@{phase=$Phase;pid=$PID;process_start_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o');started_at=$record.started_at;automatic_retry=$false}|ConvertTo-Json));$lock.Write($claim,0,$claim.Length);$lock.Flush($true);Save-Phase 'validated_before_action'
    switch($Phase){
        ReconcileForecast{$null=Run-Acceptance 'reconcile' $null}
        Backup{Assert-BackupSources;$receipt=Run-Acceptance 'backup' $previous;Backup-Dev5Disposable $p $receipt;Assert-NewBackupIntegrity}
        default{throw 'NOT_IMPLEMENTED_PENDING_SEPARATE_REVIEW_NO_ACTION'}
    }
    Assert-Protected;Assert-NoDisposableGui;$record.passed=$true;Save-Phase 'passed'
}catch{$record.error_type=$_.Exception.GetType().Name;$record.error_code=if($_.Exception.Message -cmatch '^[A-Z0-9_]+$'){$_.Exception.Message}else{'SANITIZED_FAILURE_RECONCILE_NO_RETRY'};Save-Phase 'failed_reconciliation_required';throw $record.error_code}finally{$lock.Dispose()}
