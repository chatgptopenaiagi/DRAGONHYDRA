"""Fixed b447 continuation prerequisites. No HTTP, job or lifecycle operations."""
import hashlib,json,os,re,stat
from pathlib import Path
ROOT=Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/forensics/forecast-preservation-20261103')
OLD=Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/continuation-20261102/disposable-dev5-lifecycle-r1')
OP=Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/continuation-20261103/disposable-dev5-b447-reconciled-r1')
ID='core-next-b447d99ab9524197af09c235077685de';SOURCE='ed78fab282599a181d4254ab65a2fc2eaa5b7f50'
SETUP='8d5a790ac54b4cca3c51d08746db80a5551c211474bcdead7dc86a44b3a8e553';VERSION='0.5.0-dev.5';OPID='dev5-b447-forecast-reconciled-20261103-r1'
TARGET='de2c0fb3d3215eb157292f0941def2d44aa520a79db77dc73e40d13f88014aea';FORECAST='9cbe1c2be77d46a49c692b5cb8bf8f2b';EVALUATION='c4be90b6379d44309f9faeb696975b4f'
HISTORY='b0998ba044a1c29fea65d12dce6f1c3e59cdbc4763362db8b242a2f5ef77790d';AUDITOR='94b98d6e030a2090ee99f55abffa72f0e5e6ef1f148f47c707d4035cb03d6478'
BEFORE='0fbc6c70e5bd78db53f82ba75cabd841d4e85dba152b13d4e9881954610c2c48';AFTER='b7c0c52c694f1ade073dee0589985853b9b881fe81dfcba14e973f345f46c187'
PHASE_SHA='e25a958d991987b0a017a9423a8d97ca853719cddaecf4fa3699f4e41a10b9a6';WORKFLOW_SHA='ff643cf602c118dac689874106a045220e29b79098b91dc147de5e5d4da92e37'
class Refused(Exception):pass
def need(v,code):
    if not v:raise Refused(code)
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def ordinary(path,root,exists=True):
    p=Path(path);r=Path(root)
    need(p.is_absolute() and '..' not in p.parts,'ABSOLUTE_ORDINARY_PATH_REQUIRED')
    p=Path(os.path.abspath(p));r=Path(os.path.abspath(r))
    need(os.path.normcase(str(p)).startswith(os.path.normcase(str(r))+os.sep),'PATH_OUTSIDE_BOUND_ROOT')
    walk=p
    while True:
        try:s=walk.lstat()
        except FileNotFoundError:s=None
        if s is not None:need(not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&0x400,'REPARSE_ANCESTOR_REJECTED')
        if walk.parent==walk:break
        walk=walk.parent
    if exists:need(p.is_file(),'REFERENCE_FILE_REQUIRED')
    return p
def ref_bytes(ref,root=ROOT):
    need(isinstance(ref,dict) and bool(re.fullmatch('[a-f0-9]{64}',str(ref.get('sha256','')))),'HASH_BOUND_REFERENCE_REQUIRED')
    raw=ordinary(ref.get('path',''),root).read_bytes();need(sha(raw)==ref['sha256'],'REFERENCE_HASH_CHANGED');return raw
def ref_json(ref,root=ROOT):return json.loads(ref_bytes(ref,root))
def all_pass(checks,names):
    need(isinstance(checks,list),'NAMED_CHECKS_REQUIRED');mapping={x.get('name'):x.get('status') for x in checks};need(len(mapping)==len(checks) and all(x.get('status')=='PASS' for x in checks) and all(mapping.get(n)=='PASS' for n in names),'REQUIRED_NAMED_PROOF_MISSING')
def common(receipt,approval):
    need(receipt.get('schema_version')=='dev5.forecast-reconciliation/1' and receipt.get('status')=='VERIFIED' and receipt.get('verdict')=='EXPECTED_WORKFLOW_DELTA_VERIFIED','VERIFIED_RECONCILIATION_REQUIRED')
    for x in (receipt,approval):
        need(all(x.get(k)==v for k,v in {'operation_id':OPID,'operation_root':str(OP),'installation_id':ID,'source_commit':SOURCE,'version':VERSION,'setup_sha256':SETUP}.items()),'EXACT_NEW_OPERATION_INSTANCE_SOURCE_REQUIRED')
    need(receipt.get('original_operation_root')==str(OLD) and receipt.get('original_forecast_status')=='FAIL' and receipt.get('earlier_phase_status_override_allowed') is False and receipt.get('resubmit_allowed') is False,'OLD_FAILURE_AND_NO_RESUBMIT_REQUIRED')
    need(approval.get('schema_version')=='dev5.forecast-reconciliation-approval/1' and approval.get('approval_kind')=='COORDINATOR_HASH_ATTESTATION' and approval.get('approved') is True and approval.get('approved_phase')=='ReconcileForecast' and approval.get('approved_source_owner')=='root','ROOT_HASH_ATTESTATION_REQUIRED')
    need(receipt.get('forecast_job_id')==FORECAST and receipt.get('evaluation_job_id')==EVALUATION and receipt.get('match_id')==TARGET and receipt.get('history_records_sha256')==HISTORY,'EXACT_TWO_ORIGINAL_JOBS_REQUIRED')
    for key,value in {'original_phase':PHASE_SHA,'original_workflow':WORKFLOW_SHA,'before_snapshot':BEFORE,'after_snapshot':AFTER}.items():need(receipt.get(key,{}).get('sha256')==value,'ORIGINAL_FAILED_ATTEMPT_HASH_REQUIRED')
def audit_semantics(a,first=True):
    need(a.get('schema_version')=='workflow-preservation/1' and a.get('passed') is True and a.get('errors')==[],'STRICT_AUDIT_FAILED')
    expected={'added_schema_objects':27 if first else 0,'new_jobs':2 if first else 0,'new_cognitive_records':10 if first else 0,'new_cognitive_receipts':10 if first else 0,'new_events':8 if first else 0,'protected_retained_rows':760}
    need(all(type(a.get('counts',{}).get(k)) is int and a['counts'][k]==v for k,v in expected.items()),'EXACT_AUDIT_COUNTS_REQUIRED')
    need(bool(re.fullmatch('[a-f0-9]{64}',str(a.get('schema_contract_sha256','')))),'CANONICAL_SCHEMA_HASH_REQUIRED')
def proof_semantics(receipt,bodies):
    cause=bodies['root_cause'];need(cause.get('classification')=='B_ACCEPTANCE_HARNESS_DEFECT' and cause.get('application_source')==SOURCE and cause.get('original_failure_preserved') is True and cause.get('status')=='ROOT_CAUSE_VERIFIED_BY_INDEPENDENT_FROZEN_RUNTIME_REPRODUCTION','ROOT_CAUSE_NOT_FINAL')
    repair=bodies['repair_verification'];need(repair.get('passed') is True and repair.get('installation_id')==ID and repair.get('source_commit',repair.get('application_source'))==SOURCE and repair.get('original_forecast_status')=='FAIL' and repair.get('auditor_sha256')==AUDITOR,'SEMANTIC_REPAIR_VERIFICATION_REQUIRED')
    a=bodies['original_audit'];audit_semantics(a);need(a.get('before_sha256')==BEFORE and a.get('after_sha256')==AFTER and a.get('auditor_sha256')==AUDITOR and a.get('frozen_application_source')==SOURCE,'ORIGINAL_AUDIT_BINDING_MISMATCH')
    need(receipt['corrected_contract']['sha256']==AUDITOR and receipt['corrected_contract'].get('exact_schema_objects_sha256')==a['schema_contract_sha256'],'EXACT_CORRECTED_AUDITOR_REQUIRED')
    tests=bodies['contract_tests'];need(tests.get('status')=='PASS' and tests.get('source_application_commit')==SOURCE and type(tests.get('tests_run')) is int and tests['tests_run']>=30 and tests.get('passed')==tests['tests_run'] and tests.get('failed')==tests.get('errors')==tests.get('not_run')==0 and len(set(tests.get('case_ids',[])))==tests['tests_run'],'ACTUAL_NAMED_CONTRACT_TESTS_REQUIRED')
    r=bodies['isolated_reproduction'];need(r.get('passed') is True and r.get('source')==SOURCE and r.get('version')==VERSION and r.get('installation_id')!=ID and bool(re.fullmatch('core-next-[a-f0-9]{32}',str(r.get('installation_id','')))) and r.get('auditor_sha256')==AUDITOR and r.get('copied_credential_files') is False and r.get('automatic_retry') is False and r.get('no_provider_import_local_ai_joomla_scm_browser_or_installer_actions') is True,'INDEPENDENT_SOURCE_BOUND_REPRO_REQUIRED')
    all_pass(r.get('checks'),['first_source_profile_ready','passive_registry_history_reads_no_database_or_job_writes','forecast_exact_duplicate_returns_same_job_result','evaluation_exact_duplicate_and_honest_pending','actual_persisted_history_matches_job_outputs','independent_canonical_workflow_preservation_audit','old_comparison_falsefailure_reproduced_on_audited_positive','owned_clean_shutdown_1','restart_source_profile_ready','restart_history_jobs_and_own_pairing_preserved','restart_is_replay_only_without_new_records_jobs_events','owned_clean_shutdown_2','original_before_and_all_other_profiles_unchanged'])
    audit_semantics(r.get('preservation_audit',{}));audit_semantics(r.get('restart_audit',{}),False)
    old=r.get('old_comparison_reproduction',{});need(old.get('passed') is False and old.get('old_helper_sha256')=='47d5ffc472bbb0675ab8942c77fccb14e9a780e8f40acff2e397fe5e1c197f0b' and old.get('code')=='WORKFLOW_CHANGED_RETAINED_INPUTS_OR_PROVIDER_SETTINGS','ORIGINAL_FALSE_FAILURE_REPRO_REQUIRED')
    need(len(r.get('lifetimes',[]))==2 and all(x.get('exit_code')==0 and x.get('endpoint_removed') is True and x.get('port_free') is True for x in r['lifetimes']),'REPRO_CLEAN_SHUTDOWN_REQUIRED')
    installed=bodies['installed_identity'];need(installed.get('schema_version')=='dragonhydra.forecast-installed-readback/1' and installed.get('passed') is True and installed.get('source')==SOURCE and installed.get('installation_id')==ID and installed.get('mutating_requests')==0,'ACTUAL_INSTALLED_IDENTITY_REQUIRED')
    w=installed.get('workflow',{});need(w.get('forecast_job_id')==FORECAST and w.get('evaluation_job_id')==EVALUATION and w.get('history_records_sha256')==HISTORY and w.get('new_operations_submitted')==0,'INSTALLED_ORIGINAL_WORKFLOW_REQUIRED')
    live=bodies['preapproval_live_readback'];need(live.get('schema_version')=='joomla.retained-history-readback/1' and live.get('passed') is True and live.get('source_commit')==SOURCE and live.get('installation_id')==ID and live.get('product_action_post_count')==0,'RICH_INSTALLED_BASELINE_REQUIRED')
    all_pass(live.get('checks'),['joomla_bridge_renders_all_ten_original_records','joomla_original_job_views_and_session_continuity','normal_logout_and_fresh_anonymous_protection','consistent_sqlite_and_configuration_preservation','no_known_credentials_in_responses_or_public_evidence'])
    b=live.get('database_after',{});need(b.get('consistent_backup') is True and b.get('integrity_check')=='ok' and b.get('job_count')==3 and len(b.get('protected_tables',{}))>=20 and isinstance(live.get('configuration_fingerprints'),dict),'COMPLETE_PRIVATE_BASELINE_REQUIRED')
    return live
def validate(receipt_ref,approval_ref):
    receipt=ref_json(receipt_ref);approval=ref_json(approval_ref);common(receipt,approval);need(approval.get('reconciliation_sha256')==receipt_ref['sha256'],'APPROVAL_RECEIPT_HASH_MISMATCH')
    for name in ('original_phase','original_workflow','before_snapshot','after_snapshot','forensic_manifest','corrected_contract'):ref_bytes(receipt[name])
    m=ref_json(receipt['forensic_manifest']);need(m.get('installation_id')==ID and m.get('frozen_source')==SOURCE,'ORIGINAL_MANIFEST_INSTANCE_MISMATCH')
    for a in m['artifacts']:
        need(a['original_path'].startswith(str(OLD)+os.sep) or a['original_path']==str(LAB_HELPER),'ORIGINAL_ARTIFACT_SCOPE_MISMATCH')
        root=OLD if a['original_path']!=str(LAB_HELPER) else LAB_HELPER.parent
        ref_bytes({'path':a['original_path'],'sha256':a['sha256']},root);ref_bytes({'path':str(ROOT/a['relative_copy_path']),'sha256':a['sha256']})
    names=('root_cause','repair_verification','original_audit','contract_tests','isolated_reproduction','installed_identity','preapproval_live_readback')
    bodies={n:ref_json(receipt[n]) for n in names};live=proof_semantics(receipt,bodies)
    ref_bytes(receipt_ref);ref_bytes(approval_ref)
    return receipt,live
LAB_HELPER=Path('C:/xampp/DRAGONHYDRA-CORE-NEXT-LAB/verify_disposable_workstation_dev5.py')
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--receipt',required=True);p.add_argument('--receipt-sha256',required=True);p.add_argument('--approval',required=True);p.add_argument('--approval-sha256',required=True);a=p.parse_args()
    try:
        r,b=validate({'path':a.receipt,'sha256':a.receipt_sha256},{'path':a.approval,'sha256':a.approval_sha256});print(json.dumps({'passed':True,'operation_id':OPID,'baseline_path':r['preapproval_live_readback']['path'],'baseline_sha256':r['preapproval_live_readback']['sha256']}))
    except Exception as e:print(json.dumps({'passed':False,'error_code':str(e) if re.fullmatch('[A-Z0-9_]+',str(e)) else 'PREREQUISITE_INVALID'}));raise SystemExit(2)
