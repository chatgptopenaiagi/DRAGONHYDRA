"""Stage explicit verified native-component bytes and sanitized public metadata.

No software payload, installed service, earlier candidate or release is changed.
Raw logs, databases, session secrets and test backups stay in private build state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT/'build/linux/native-kernel-20261031'
DIST = ROOT/'dist/linux/native-kernel-20261031'


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    if path.exists():
        raise ValueError('Final metadata exists; preserve it: '+path.name)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def public_build(build):
    keys = ('schema_version', 'started_at', 'finished_at', 'status', 'version', 'python', 'target', 'scope',
            'source_sha', 'base_source_content_sha256', 'source_content_sha256', 'source_transforms',
            'application_snapshot_sha256', 'linux_support_snapshot_sha256',
            'built', 'artifact', 'payload_files', 'dependencies', 'signing')
    return {key: build[key] for key in keys if key in build}


def application_origin(build, prefix, external_manifest=None, external_proof=None):
    """Verify application equivalence without inventing an embedded origin.

    A composed bundle may embed its origin; a directly reused Linux wheel does
    not. External comparison evidence is required for the latter case.
    """
    docs = prefix.parents[2]/'usr/share/doc/dragonhydra-api'
    source = load(docs/'SOURCE-MANIFEST.json')
    canonical = lambda files: hashlib.sha256(json.dumps(
        files, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if canonical(source['files']) != build['base_source_content_sha256']:
        raise ValueError('Packaged base source identity differs from this build')
    embedded = build.get('application_snapshot_sha256')
    origin_path = Path(external_manifest) if external_manifest else docs/'A4-ORIGIN-SOURCE-MANIFEST.json'
    if not origin_path.resolve().is_relative_to(ROOT/'build') or not origin_path.is_file() or origin_path.is_symlink():
        raise ValueError('A verified project-local application origin is required')
    origin = load(origin_path)
    origin_hash = canonical(origin['files'])
    if origin.get('source_sha') is not None or origin.get('content_sha256') != origin_hash:
        raise ValueError('Application origin manifest identity is inconsistent')
    app = lambda document: {item['path']: item for item in document['files']
                            if item['path'].startswith('src/dragonhydra/')}
    if not app(source) or app(source) != app(origin):
        raise ValueError('Complete application bytes differ from the declared origin')
    if embedded:
        if embedded != origin_hash:
            raise ValueError('Embedded application origin differs from supplied manifest')
    else:
        if not external_proof:
            raise ValueError('Direct frozen wheel needs separately verified origin evidence')
        raw_proof_path = Path(external_proof)
        proof_path = raw_proof_path.resolve()
        if raw_proof_path.is_symlink() or not proof_path.is_relative_to(ROOT/'build'):
            raise ValueError('Origin comparison proof must remain project-local')
        proof = load(proof_path)
        if (proof.get('passed') is not True
                or proof.get('source_content_sha256') != build['base_source_content_sha256']
                or proof.get('windows_application_origin') != origin_hash
                or proof.get('checks', {}).get('identical_application_files') != len(app(source))):
            raise ValueError('Origin comparison evidence does not describe this candidate')
    return {'application_snapshot_sha256': origin_hash,
            'application_file_count': len(app(source)),
            'origin_embedded_in_software': bool(embedded),
            'origin_relationship': 'Complete source/resource entries equal the Windows frozen application manifest',
            'base_source_content_sha256': build['base_source_content_sha256'],
            'origin_manifest_sha256': sha(origin_path)}, origin_path


def context_reader_summary(proof, build):
    checks = proof.get('checks', [])
    if (proof.get('passed') is not True or not checks or not all(c.get('passed') is True for c in checks)
            or proof.get('effective_source_content_sha256') != build['source_content_sha256']
            or proof.get('fresh_provider_http') is not False or proof.get('retained_replay') is not True
            or proof.get('system_service_changes') is not False
            or proof.get('process', {}).get('exit_code') != 0
            or proof.get('database_readonly', {}).get('identical_schema_and_counts') is not True
            or proof.get('database_readonly', {}).get('context_tables_before_after') != []
            or proof.get('retained_parent', {}).get('repeat_inserted') != 0
            or not any(c.get('availability') == 'not_requested' for c in checks)):
        raise ValueError('Retained context-reader proof does not describe this candidate and read-only scope')
    return {'passed': True, 'groups': len(checks), 'retained_parent_records': proof['retained_parent']['inserted'],
            'repeat_inserted': 0, 'availability': 'not_requested', 'schema_and_counts_unchanged': True,
            'context_tables_created': 0, 'fresh_provider_http': False, 'system_service_changes': False,
            'qualification': 'Actual extracted API readers over retained StatsBomb parents; no event/lineup context ingestion, context job, UI or installed-service proof.'}


def optional_ai_summary(proof, build):
    """Bind optional service proof to this exact API, preserving its limits."""
    identity = proof.get('api_identity', {})
    restored = proof.get('restored', {})
    configuration = restored.get('api_configuration', {})
    model = restored.get('model_state', {})
    jobs = [proof.get('first', {}), proof.get('after_restart', {})]
    checks = proof.get('checks', [])
    if (proof.get('passed') is not True or proof.get('error') or proof.get('cleanup_error')
            or identity.get('source_content_sha256') != build['source_content_sha256']
            or identity.get('debian_version') != build['version']
            or len(checks) < 7 or not all(c.get('passed') is True for c in checks)
            or any(j.get('kind') != 'local_llm' or j.get('mode') != 'constrained_source_fact_selection' for j in jobs)
            or not jobs[0].get('evidence_id') or jobs[0].get('evidence_id') != jobs[1].get('evidence_id')
            or not jobs[0].get('raw_sha256') or jobs[0].get('raw_sha256') != jobs[1].get('raw_sha256')
            or any(restored.get(key) is not True for key in (
                'canonical_raw_pairing_base_config_equal', 'all_retained_tables_equal',
                'connector_and_cognitive_included', 'disabled_key_configuration_hashes_equal',
                'api_dropin_absent', 'key_retained_root0600', 'profile_retained'))
            or restored.get('ownership_enabled') is not False
            or type(restored.get('records')) is not int or restored['records'] < 0
            or configuration.get('configured') is not False or configuration.get('endpoint') != ''
            or configuration.get('credential_source') != 'none'
            or model.get('ActiveState') != 'inactive' or model.get('UnitFileState') != 'disabled'
            or str(model.get('MainPID')) != '0'):
        raise ValueError('Optional model proof is not accepted for this exact API and restored-state contract')
    return {'passed': True, 'milestones': len(checks), 'accepted_model_jobs': 2,
            'mode': 'constrained_source_fact_selection', 'profile': 'Qwen3-4B Q4_K_M / CPU4 / context2048 / slot1',
            'same_retained_evidence_across_model_restart': True,
            'records_retained': restored['records'], 'original_disabled_configuration_restored': True,
            'credential_storage': 'Protected root0600 local plaintext, not an encrypted vault',
            'runtime_or_model_or_controller_bundled_in_api_deb': False,
            'qualification': 'Actual separately installed CPU runtime and managed optional service on host loopback. Not a network-isolated test or new free-form sports analysis.'}


def supplement(revision):
    """Add later measured results without hiding an earlier successful phase."""
    out, build_dir = DIST/('r'+revision), WORK/('build-'+revision)
    addendum = out/'VERIFICATION-ADDENDUM.json'
    if addendum.exists():
        raise ValueError('Supplement already exists; retain its evidence.')
    for line in (out/'SHA256SUMS.txt').read_text().splitlines():
        expected, name = line.split('  ', 1)
        if Path(name).name != name or sha(out/name) != expected:
            raise ValueError('Prior finalized asset changed: '+name)
    manifest = load(out/'ARTIFACT-MANIFEST.json')
    software = manifest['artifacts'][0]
    if sha(out/software['filename']) != software['sha256']:
        raise ValueError('Software bytes changed before supplement.')
    core = load(WORK/('installed-regression-'+revision)/'run-r1/verification.json')
    fresh = load(WORK/('public-sync-'+revision)/'SUMMARY.json')
    fresh_detail = load(WORK/('public-sync-'+revision)/'run/verification.json')
    browser = load(WORK/('browser-'+revision)/'STATUS.json')
    network = load(WORK/('service-network-probe-'+revision)/'STATUS.json')
    prefix_probe = load(WORK/('network-probe-'+revision)/'verification.json')
    if (not core.get('passed') or core.get('exit_code') != 0 or not core.get('source_fingerprints_unchanged')
            or not core.get('installed_fingerprints_unchanged')
            or fresh.get('fresh_sync_passed') is not False or fresh_detail.get('pending_owned_jobs')
            or not network.get('diagnostic_passed') or browser.get('browser_tested') is not False):
        raise ValueError('Later verification facts do not match this supplement contract.')
    record = {
        'schema_version': 1, 'observed_at': datetime.now(timezone.utc).isoformat(),
        'artifact': {'filename': software['filename'], 'sha256': software['sha256']},
        'all_requested_verifications_passed': False,
        'offline_core_and_installation_passed': True,
        'installed_core_regression': {'passed': True, 'unique_cases': core['unique_cases'],
            'existing_cases': core['existing_cases'], 'additional_known_answer_cases': core['additional_known_answer_cases'],
            'test_result': core['test_result'], 'loaded_application_modules': len(core['module_origins']),
            'network_calls_attempted': core['network_calls_attempted'], 'qualification': 'Scoped installed core cohort, not the full application suite.'},
        'fresh_service_sync': {'passed': False, 'exit_code': fresh['native_sync_exit_code'], 'providers': fresh['providers'],
            'pending_owned_jobs': [], 'new_acquisitions': 0, 'new_observations': 0,
            'cached_records_retained': 760, 'cached_match_team_evidence_browsing_passed': True,
            'qualification': 'Three actual API jobs, six worker attempts, then deadline cancellation. No successful provider response or normalization.'},
        'underlying_transport_probe': {
            'diagnostic_passed': True, 'provider_retrieval_succeeded': False,
            'root_exception': network['root_underlying_exception'],
            'service_context_exception': network['service_context_underlying_exception'],
            'identity_coverage': network['matching_identity_coverage'],
            'qualification': 'EAI_AGAIN reproduced for the original Football-Data.co.uk hostname; raw reasons for the other providers were not separately captured.'},
        'separate_bare_hostname_prefix_probe': {
            'http_status': prefix_probe['https_get']['result']['http_status'],
            'bytes': prefix_probe['https_get']['result']['bytes_read'],
            'qualification': 'Root-context verified-TLS prefix only, different hostname/time. Not a complete import or service connection proof.'},
        'windows_browser_gate': {'passed': False, 'browser_tested': False, 'code': browser['windows_gap']['code'],
            'error': browser['windows_gap']['message'], 'linux_api_inside_wsl_ready': True,
            'qualification': 'Windows refused localhost while bounded WSL foreground session was active. No routing/firewall changes.'},
        'wsl_host_lifetime': 'Systemd units do not keep WSL alive. Enabled service starts when Ubuntu is activated; no continuous WSL hosting or reboot proof.',
        'host_network_or_vpn_settings_changed': False,
        'evidence_paths': [f'build/linux/native-kernel-20261031/{name}-{revision}' for name in
            ('installed-regression', 'public-sync', 'service-network-probe', 'network-probe', 'browser')],
    }
    backup = build_dir/'pre-supplement-metadata'
    backup.mkdir()
    for name in ('ARTIFACT-MANIFEST.json', 'TEST-REPORT.json', 'INSTALLATION.md', 'SHA256SUMS.txt'):
        shutil.copyfile(out/name, backup/name)
    save(addendum, record)
    manifest['status'] = 'OFFLINE_API_COMPONENT_VERIFIED_FRESH_SERVICE_SYNC_AND_HOST_BROWSER_BLOCKED'
    manifest['all_requested_verifications_passed'] = False
    software['INSTALLED_CORE_REGRESSION_CASES'] = core['unique_cases']
    software['FRESH_PUBLIC_SYNC_VERIFIED'] = False
    software['WINDOWS_TO_WSL_BROWSER_VERIFIED'] = False
    # These are later evidence updates, never a software replacement. Retain the
    # original immutable phase reports in the private pre-supplement snapshot.
    (out/'ARTIFACT-MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    report = load(out/'TEST-REPORT.json')
    report.update(passed=False, offline_core_and_installation_passed=True,
                  all_requested_verifications_passed=False, verification_addendum=addendum.name,
                  installed_core_regression=record['installed_core_regression'],
                  fresh_provider_http=record['fresh_service_sync'], windows_browser_gate=record['windows_browser_gate'])
    report['not_run'] = [value for value in report['not_run'] if value != 'Windows browser reachability to this WSL loopback endpoint']
    report['not_run'].append('Browser UI journey: blocked by measured Windows-to-WSL localhost refusal while WSL was active')
    (out/'TEST-REPORT.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    with (out/'INSTALLATION.md').open('a', encoding='utf-8') as output:
        output.write('''
## Later verification results

The actual installed core cohort passed113 cases, zero failures/errors/skips, with all23 application modules from the installed prefix. This is separate from the9 extracted,12 installed-runtime and11 retained-provider groups.

Actual fresh service syncs were then attempted for Football-Data.co.uk, StatsBomb and Cricsheet. All returned NETWORK_UNAVAILABLE before any payload; six worker attempts produced zero acquisitions/observations. Each of the three jobs was cancelled at the test deadline; no queued retry or periodic schedule remains. Cached760-record match/team/evidence browsing continued to work. TEST-REPORT now records overall requested checks as failed while preserving the successful offline/core/installation phases.

The original Football-Data.co.uk hostname produced URLError → gaierror -3 EAI_AGAIN (temporary name-resolution failure) in root and a diagnostic matching the service UID/GID and mount/network namespaces. That diagnostic did not match its cgroup/seccomp/environment and did not capture the other two providers' raw errors. A separate root request to the resolved bare hostname returned a1024-byte HTTPS206 prefix; it is not a complete import or service proof. No DNS/VPN/TLS/routing settings were changed.

Windows-to-WSL localhost remained refused while a bounded WSL foreground holder was active, so the browser journey was not run and no session token was transferred. Systemd services do not keep WSL alive; an idle stopped WSL runtime is not continuous hosting. Native Linux API functionality was verified inside Ubuntu. See VERIFICATION-ADDENDUM.json for exact scope and retained failures. Full Linux desktop/web/database integration remains unfinished.
''')
    files = sorted(path for path in out.iterdir() if path.is_file() and path.name != 'SHA256SUMS.txt')
    (out/'SHA256SUMS.txt').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in files), encoding='ascii')
    save(build_dir/'SUPPLEMENT.json', {'passed': True, 'software_bytes_changed': False,
         'artifact_sha256': sha(out/software['filename']), 'public_files_checksummed': len(files),
         'tool_sha256': sha(Path(__file__))})
    print(json.dumps({'status': manifest['status'], 'software_sha256': software['sha256'],
                      'public_files_checksummed': len(files), 'installed_core_cases_passed': core['unique_cases'],
                      'fresh_service_sync_passed': False}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--provider-proof', type=Path)
    parser.add_argument('--application-origin', type=Path, help='Exact Windows frozen source manifest for a directly reused wheel')
    parser.add_argument('--application-origin-proof', type=Path, help='Separate verified source comparison receipt')
    parser.add_argument('--context-proof', type=Path, help='Separate extracted retained-parent/context-reader verification')
    parser.add_argument('--optional-ai-proof', type=Path, help='Separate actual optional model/service proof bound to this API identity')
    parser.add_argument('--supplement', action='store_true', help='Append separately scoped later core/network/browser observations')
    args = parser.parse_args()
    if not 7 <= args.revision <= 999:
        parser.error('Use this evidence contract for sequence7 or later.')
    revision = str(args.revision)
    if args.supplement:
        supplement(revision)
        return
    build_dir, out = WORK/('build-'+revision), DIST/('r'+revision)
    build = load(build_dir/'BUILD-REPORT.json')
    extracted = load(WORK/('acceptance-'+revision)/'verification.json')
    archive = load(WORK/('artifact-audit-'+revision)/'verification.json')
    installed_dir = WORK/('system-install-'+revision)
    installed = load(installed_dir/'STATUS.json')
    runtime = load(installed_dir/'runtime/verification.json')
    upgrade = load(installed_dir/'run/verification.json')
    filename = build['artifact']['filename']
    if Path(filename).name != filename or not filename.endswith('_amd64.deb'):
        raise ValueError('Invalid explicit software filename')
    artifact = out/filename
    prefix = WORK/('acceptance-'+revision)/'extracted/opt/dragonhydra/api'
    origin, origin_path = application_origin(build, prefix, args.application_origin, args.application_origin_proof)
    source_copy = build_dir/'packaging-source'
    if source_copy.exists() or (build_dir/'METADATA-TOOL.json').exists() or (build_dir/'FINALIZATION.json').exists():
        raise ValueError('Finalization evidence exists; preserve this candidate.')
    if (artifact.is_symlink() or sha(artifact) != build['artifact']['sha256']
            or artifact.stat().st_size != build['artifact']['bytes']
            or not all(proof.get('passed') for proof in (extracted, archive, installed, runtime, upgrade))
            or archive.get('findings') or runtime.get('gaps')
            or runtime.get('endpoint_persistent') is not True
            or installed['artifact']['sha256'] != sha(artifact)
            or installed['native_upgrade']['exit_code'] != 0
            or installed['native_version_comparison']['exit_code'] != 0
            or installed['frozen_contract']['base_source_content_sha256'] != build['base_source_content_sha256']
            or installed['frozen_contract']['effective_source_content_sha256'] != build['source_content_sha256']
            or installed['frozen_contract']['application_origin_content_sha256'] != origin['application_snapshot_sha256']):
        raise ValueError('Exact installed-candidate verification gate failed')
    identity = load(prefix/'BUILD-IDENTITY.json')
    if (identity['source_content_sha256'] != build['source_content_sha256']
            or identity['debian_version'] != build['version']
            or identity.get('application_snapshot_sha256') != build.get('application_snapshot_sha256')):
        raise ValueError('Extracted package and build identity mismatch')
    inputs = {item['path']: item for item in identity['packaging_inputs']}
    for name, entry in inputs.items():
        source = Path(__file__).parent/name
        if Path(name).name != name or source.stat().st_size != entry['bytes'] or sha(source) != entry['sha256']:
            raise ValueError('Packaging input changed since this build: '+name)
    if sha(Path(__file__).with_name('build_deb.py')) != identity['builder_sha256']:
        raise ValueError('Builder changed since this candidate; do not bind newer source')
    if any(path.name != filename for path in out.iterdir()):
        raise ValueError('Output already contains metadata or unexpected files')
    replay = None
    context = None
    optional_ai = None
    if args.provider_proof:
        proof_path = args.provider_proof.resolve()
        if not proof_path.is_relative_to(WORK):
            raise ValueError('Provider evidence must remain in owned build state')
        replay = load(proof_path)
        if (not replay.get('passed') or replay.get('fresh_http') is not False
                or replay.get('network_calls_attempted') != 0
                or replay['package']['effective_source_content_sha256'] != build['source_content_sha256']
                or replay['package']['debian_version'] != build['version']
                or replay['package']['verified_payload_files'] != build['payload_files']):
            raise ValueError('Retained-provider replay gate failed')
    if args.context_proof:
        context_path = args.context_proof.resolve()
        if args.context_proof.is_symlink() or not context_path.is_relative_to(WORK):
            raise ValueError('Context evidence must remain in owned build state')
        context = context_reader_summary(load(context_path), build)
    if args.optional_ai_proof:
        ai_path = args.optional_ai_proof.resolve()
        if args.optional_ai_proof.is_symlink() or not ai_path.is_relative_to(ROOT/'build/linux/local-ai-20261031'):
            raise ValueError('Optional model evidence must remain in its owned build state')
        optional_ai = optional_ai_summary(load(ai_path), build)
    software = {
        'filename': filename, 'role': 'Linux API-server component', 'debian_version': build['version'],
        'application_version': identity['application_version'], 'python_distribution_version': identity['python_version'],
        'platform': build['target'], 'architecture': 'amd64', 'bytes': artifact.stat().st_size, 'sha256': sha(artifact),
        'signing': build['signing'], 'source_sha': None,
        **origin,
        'base_source_content_sha256': build['base_source_content_sha256'],
        'source_content_sha256': build['source_content_sha256'], 'source_transforms': build['source_transforms'],
        'prerequisites': ['OS CPython>=3.14,<3.15', 'libc6>=2.17', 'libgcc-s1', 'ca-certificates', 'init-system-helpers', 'systemd for managed startup'],
        'api_namespace': '/dragon/api/v1', 'api_schema_version': 1, 'selected_backend': 'sqlite',
        'bundled_dependencies': build['dependencies'], 'BUILT': True, 'PACKAGE_TESTED': True,
        'EXTRACTED_RUNTIME_TESTED': True, 'INSTALL_TESTED': True, 'UPGRADE_TESTED': True, 'SYSTEMD_TESTED': True,
        'RETAINED_PROVIDER_REPLAY_TESTED': replay is not None, 'FRESH_PUBLIC_HTTP_VERIFIED': False,
        'OPTIONAL_LOCAL_MODEL_COMPATIBILITY_TESTED': optional_ai is not None,
        'FRESH_EMPTY_STATE_SYSTEM_INSTALL_TESTED': False, 'CLEAN_MACHINE_TESTED': False,
        'DESKTOP_TESTED': False, 'REBOOT_TESTED': False, 'BYTE_REBUILD_VERIFIED': False,
    }
    save(out/'ARTIFACT-MANIFEST.json', {'schema_version': 1, 'published': False,
        'status': 'OFFLINE_API_COMPONENT_VERIFIED_FULL_LINUX_WORKSTATION_UNFINISHED',
        'all_requested_verifications_passed': False, 'artifacts': [software],
        'omitted_targets': ['Complete Linux desktop/Joomla/PHP/MariaDB workstation', 'RPM', 'Optional model runtime and weights within this API component']})
    save(out/'BUILD-REPORT.json', public_build(build))
    command = installed['native_upgrade']
    test = {
        'schema_version': 1, 'verified_at': datetime.now(timezone.utc).isoformat(), 'passed': False,
        'offline_core_and_installation_passed': True, 'all_requested_verifications_passed': False,
        'scope': build['scope'], 'extracted_runtime_groups': len(extracted['checks']),
        'independent_archive_checks': len(archive['checks']),
        'installed_runtime_groups': len(runtime['checks']), 'full_runtime_repeated_for_changed_application': True,
        'native_upgrade': {key: command[key] for key in ('name', 'exit_code', 'seconds')},
        'native_version_increase_exit_code': installed['native_version_comparison']['exit_code'],
        'records_before': runtime['persistence']['before']['count'], 'records_after': runtime['persistence']['after']['count'],
        'endpoint_persistent': runtime['endpoint_persistent'],
        'records_raw_evidence_pairing_cache_config_protections_retained': installed['retained_public_rows_raw_evidence_pairing_configuration_cache_protections_unchanged'],
        'controlled_crash_recovery': installed['installed_runtime']['controlled_failure'],
        'final_state': installed['last_observed_ready']['service']['ActiveState'],
        'reused_lifecycle_proof': {'revision': 6, 'reason': 'All four lifecycle scripts are byte-identical; R6 remove/reinstall verified cleanup and retained state.',
                                 'remove_reinstall_repeated_on_this_revision': False},
        'fresh_provider_http': {'run': False, 'verified': False, 'historical_linux_probe': 'Earlier R7 jobs failed NETWORK_UNAVAILABLE and its original COUK hostname probe returned EAI_AGAIN. Not rerun on this candidate; no TLS/VPN/DNS changes.'},
        'not_run': ['Clean-machine, reboot or fresh-empty-state system package installation',
                    'Native Linux desktop/full web and database workstation', 'Optional-model compatibility for this API candidate',
                    'Production signing', 'Windows browser reachability to this WSL loopback endpoint'],
        'linux_ai_credentials': 'Windows DPAPI key-save fails explicitly VAULT_PLATFORM; use protected service environment configuration. Blank configuration gives deterministic fallback.',
        'evidence_paths': [str(path.relative_to(ROOT)).replace('\\', '/') for path in
            (build_dir, WORK/('acceptance-'+revision), WORK/('artifact-audit-'+revision), installed_dir)],
    }
    if replay:
        test['retained_provider_replay'] = {
            'passed': True, 'groups': len(replay['checks']), 'mode': replay['mode'], 'analysis_mode': replay['analysis_mode'],
            'stored_counts': replay['stored_counts'], 'network_calls_attempted': replay['network_calls_attempted'],
            'fresh_http': False, 'operational_database_modified': False, 'model_executed': False,
            'qualification': 'Real retained source bytes parsed and stored in an isolated SQLite database; not fresh HTTP, installed-source status or browser verification.',
        }
        test['evidence_paths'].append(str(proof_path.relative_to(ROOT)).replace('\\', '/'))
    if context:
        test['retained_context_readers'] = context
        test['evidence_paths'].append(str(context_path.relative_to(ROOT)).replace('\\', '/'))
    if optional_ai:
        test['optional_local_model_compatibility'] = optional_ai
        test['not_run'].remove('Optional-model compatibility for this API candidate')
        test['evidence_paths'].append(str(ai_path.relative_to(ROOT)).replace('\\', '/'))
    save(out/'TEST-REPORT.json', test)
    for name in ('INPUT-MANIFEST.json', 'PAYLOAD-MANIFEST.json'):
        shutil.copyfile(build_dir/name, out/name)
    docs = prefix.parents[2]/'usr/share/doc/dragonhydra-api'
    for name in ('SOURCE-MANIFEST.json', 'EFFECTIVE-SOURCE-MANIFEST.json',
                 'A4-ORIGIN-SOURCE-MANIFEST.json', 'LINUX-SUPPORT-ORIGIN-SOURCE-MANIFEST.json'):
        if (docs/name).is_file():
            shutil.copyfile(docs/name, out/name)
    save(out/'APPLICATION-ORIGIN.json', origin)
    if not origin['origin_embedded_in_software']:
        shutil.copyfile(origin_path, out/'WINDOWS-APPLICATION-ORIGIN-SOURCE-MANIFEST.json')
    wheels = load(build_dir/'INPUT-MANIFEST.json')['files']
    (out/'requirements.lock').write_text(''.join(item['name']+'=='+item['version']+' --hash=sha256:'+item['sha256']+'\n'
        for item in wheels if item['name'].lower() != 'dragonhydra'), encoding='ascii')
    (out/'INSTALLATION.md').write_text(f'''# Native Linux API-server component

`{filename}` is an unsigned Ubuntu26.04 x86_64 development package. It includes the complete frozen application, reusable web assets and17 pinned private Python libraries. OS CPython3.14 and the declared system libraries are prerequisites. SQLite is the selected sports backend. Desktop executable, Apache/PHP/Joomla, MariaDB and model weights are not included.

```sh
sha256sum -c SHA256SUMS.txt
sudo dpkg --install './{filename}'
sudo systemctl status dragonhydra-api.service
sudo cat /var/lib/dragonhydra-api/endpoint.json
```

The actual native upgrade exited0 in{command['seconds']} seconds, one attempt. All760 installed records, raw evidence, pairing, cache and configuration survived. The changed application passed{len(extracted['checks'])} extracted and{len(runtime['checks'])} actual installed-runtime groups: match/team/standings, cited deterministic explanation, real XLSX, restart, stop/start and one controlled process failure. The final owned unit is active/Ready at the same private address. These are separate scopes, not one inflated suite count.

Configuration: `/etc/dragonhydra/api.env`; binaries: `/opt/dragonhydra/api`; state: `/var/lib/dragonhydra-api`. The managed service keeps its selected loopback port in `managed-port.json`. Current readiness/address is in `endpoint.json`. An explicit DRAGONHYDRA_PORT overrides the saved choice. Normal CLI `--port 0` remains ephemeral. Busy listeners produce an errno; no unrelated process is stopped. Native state0700, local-session0600, managed-port0600 and root config0600 are enforced. Pair using the protected local-session flow as server administrator. No credentials or public/LAN exposure are bundled. A WSL loopback URL refers to Linux. Windows host-browser reachability was not rerun on this candidate; the earlier R7 gate refused localhost while WSL was active. No network settings were changed.

The source includes all{origin['application_file_count']} frozen application/resource files (Windows application origin{origin['application_snapshot_sha256']}), verified Linux build support and an explicit Linux socket patch. Base{build['base_source_content_sha256']}; effective{build['source_content_sha256']}. APPLICATION-ORIGIN.json distinguishes an embedded origin from a separately verified complete-application comparison. The packaged source manifests and wheel RECORD retain their original identities. Version sequence precedes the content hash so newer source cannot sort as a downgrade. No Git commit or byte-identical rebuild is claimed.

The unchanged lifecycle scripts reuse revision6's real remove/reinstall proof: removed unit not-found, no dangling enablement link/listener, retained data/configuration, then enabled/Ready after reinstall. Removal clears only this unit's helper bookkeeping. No database/package purge was executed. Back up protected state before changes.

Retained public-data replay results, when included in TEST-REPORT.json, belong to a separate isolated test database and do not claim fresh provider connectivity or UI status. Public HTTP remains unverified for this candidate. The installed service retains760 OpenFootball records. Windows DPAPI is not a Linux credential vault: key-save fails explicitly VAULT_PLATFORM; configure supported keys through the protected service environment. Missing AI configuration gives an explicitly deterministic fallback. Optional runtime/model proofs are separate from this API candidate's core verification.

Fresh-empty-state system installation, clean machine/reboot, native Linux desktop, complete web/database workstation and production signing remain unfinished. Only the features and evidence scopes recorded in TEST-REPORT.json are verified. Existing Windows installations and all prior artifacts/releases were preserved.
The report's overall passed flag remains false for those unfulfilled requested
checks; offline_core_and_installation_passed records the successful component
gates separately. Systemd units do not keep an idle WSL distribution running;
the enabled unit starts when Ubuntu is activated. Continuous hosting and host
reboot behavior were not established.
''', encoding='utf-8')
    if optional_ai:
        with (out/'INSTALLATION.md').open('a', encoding='utf-8') as instructions:
            instructions.write('''
The separate optional CPU runtime and controller passed two real cited-fact jobs
across a model-service restart on this exact API version. Stopping the model or
removing its optional environment file left browsing ready. All retained data,
pairing and protected disabled configuration were restored. That host-loopback
test is separate from the earlier network-isolated runtime proof. Runtime,
weights and setup helper are not inside this API DEB; ordinary startup does not
require them. Local credentials use protected root0600 plaintext, not an encrypted
vault. See TEST-REPORT.json for the exact scope.
''')
    source_copy.mkdir()
    for name in ('build_deb.py', *inputs):
        shutil.copyfile(Path(__file__).parent/name, source_copy/name)
    save(build_dir/'METADATA-TOOL.json', {'path': str(Path(__file__).relative_to(ROOT)).replace('\\', '/'), 'sha256': sha(Path(__file__))})
    files = sorted(path for path in out.iterdir() if path.is_file())
    (out/'SHA256SUMS.txt').write_text(''.join(sha(path)+'  '+path.name+'\n' for path in files), encoding='ascii')
    save(build_dir/'FINALIZATION.json', {'passed': True, 'artifact': filename, 'sha256': sha(artifact),
         'public_files_checksummed': len(files), 'software_bytes_changed': False})
    print(json.dumps({'status': 'FINALIZED_VERIFIED_COMPONENT', 'artifact': filename, 'bytes': artifact.stat().st_size,
                      'sha256': sha(artifact), 'public_files_checksummed': len(files)}, indent=2))


if __name__ == '__main__':
    main()
