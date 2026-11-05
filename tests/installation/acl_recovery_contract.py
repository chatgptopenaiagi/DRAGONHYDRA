"""Read-only reconciliation guards; never start a service or certify a release.

The owner binds a new operation to immutable failed installation inputs. A valid
contract permits the separately reviewed controller to continue; it says nothing
about effective token access, startup, SQL authentication or application health.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

LAB = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')


class RecoveryContractError(Exception):
    pass


def need(condition, code):
    if not condition:
        raise RecoveryContractError(code)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ordinary(value):
    path = Path(value)
    need(path.is_absolute() and '..' not in path.parts, 'ABSOLUTE_ORDINARY_RECOVERY_PATH_REQUIRED')
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise RecoveryContractError('RECOVERY_PATH_ACCESS_DENIED: ' + str(part)) from error
        need(not part.is_symlink() and not getattr(info, 'st_file_attributes', 0) & 0x400,
             'REPARSE_RECOVERY_PATH_REJECTED')
    return path


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def bound(spec):
    need(isinstance(spec, dict) and re.fullmatch('[a-f0-9]{64}', str(spec.get('sha256', ''))),
         'RECOVERY_INPUT_HASH_REQUIRED')
    path = ordinary(spec['path'])
    need(path.is_file() and digest(path) == spec['sha256'], 'RECOVERY_INPUT_CHANGED')
    return path


def validate_recovery(operation_path, expected_sha256, *, lab_root=LAB):
    """Validate evidence only. lab_root is injectable for disposable unit fixtures."""
    lab = ordinary(lab_root)
    path = bound({'path': str(operation_path), 'sha256': expected_sha256})
    op = load(path)
    need(op.get('schema_version') == 'core-next.acl-recovery-operation/1', 'RECOVERY_SCHEMA_REQUIRED')
    need(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{7,127}', str(op.get('operation_id', ''))),
         'NEW_RECOVERY_OPERATION_ID_REQUIRED')
    operation_root = ordinary(op['operation_root'])
    need(path.parent == operation_root and operation_root.is_relative_to(lab)
         and operation_root != lab and operation_root.is_dir(), 'PRIVATE_RECOVERY_OPERATION_REQUIRED')
    need(op.get('automatic_retry') is False and op.get('original_outcome') == 'FAIL_PRESERVED',
         'FAILED_OUTCOME_MUST_REMAIN_FAILED')
    need(op.get('service_account') == r'NT AUTHORITY\LocalService', 'RECOVERY_SERVICE_ACCOUNT_MISMATCH')
    inputs = {name: bound(op['original_' + name]) for name in ('receipt', 'plan', 'bindings', 'install_script')}
    original = inputs['plan'].parent
    need(original.is_relative_to(lab) and original != lab and original != operation_root,
         'DISTINCT_RECOVERY_OPERATION_REQUIRED')
    names = {'receipt': 'phase-InstallFresh.json', 'plan': 'PLAN.json', 'bindings': 'BINDINGS.json',
             'install_script': 'InstallFresh.ps1'}
    need(all(file.parent == original and file.name == names[name] for name, file in inputs.items()),
         'ORIGINAL_INSTALL_OPERATION_BINDING_REQUIRED')
    receipt, plan, bindings = (load(inputs[key]) for key in ('receipt', 'plan', 'bindings'))
    need(receipt.get('schema_version') == 'core-next.dev7-windows-phase/1'
         and receipt.get('phase') == 'InstallFresh' and receipt.get('passed') is False
         and receipt.get('stage') == 'failed_reconciliation_required'
         and receipt.get('failure_code') == 'INSTALLER_FAILED_RECONCILE_NO_RETRY'
         and receipt.get('automatic_retry') is False and receipt.get('installer_exit_code') == 1,
         'EXACT_FAILED_INSTALL_PREDECESSOR_REQUIRED')
    need(plan.get('schema_version') == 'core-next.dev7-windows-install-plan/1'
         and bindings.get('schema_version') == 'core-next.dev7-install-draft-bindings/1',
         'ORIGINAL_INSTALL_SCHEMA_REQUIRED')
    need(bindings.get('plan_sha256') == digest(inputs['plan']) == receipt.get('plan_sha256')
         and bindings.get('install_fresh_sha256') == digest(inputs['install_script']),
         'ORIGINAL_INSTALL_HASH_BINDING_MISMATCH')
    identity = op.get('installation_id', '')
    source = op.get('source_commit', '')
    need(re.fullmatch('core-next-[a-f0-9]{32}', identity), 'RECOVERY_INSTALLATION_ID_REQUIRED')
    need(re.fullmatch('[a-f0-9]{40}', source), 'RECOVERY_SOURCE_ID_REQUIRED')
    need(all(doc.get('installation_id') == identity and doc.get('source_commit') == source
             for doc in (receipt, plan)), 'RECOVERY_PREDECESSOR_IDENTITY_MISMATCH')
    need(bindings.get('frozen_source_commit') == source, 'RECOVERY_FROZEN_SOURCE_MISMATCH')
    profile_path = bound(plan['profile'])
    need(profile_path == lab / 'profiles' / identity / 'installation-profile.json',
         'UNAUTHORIZED_PROFILE_DIRECTORY')
    profile = load(profile_path)
    need(profile.get('product') == 'DRAGONHYDRA CORE NEXT' and profile.get('edition') == 'CORE NEXT'
         and profile.get('schema_version') == 1 and profile.get('environment_id') == 'candidate'
         and profile.get('installation_id') == identity and profile.get('source_commit') == source,
         'RECOVERY_PROFILE_IDENTITY_MISMATCH')
    need(ordinary(profile['lab_root']) == lab, 'RECOVERY_LAB_IDENTITY_MISMATCH')
    root = lab / 'profiles' / identity
    need(all(ordinary(profile[field]) == root / child for field, child in
             [('install_root', 'application'), ('state_root', 'state'), ('browser_user_data', 'browser')]),
         'UNAUTHORIZED_INSTALLATION_DIRECTORY')
    service = 'DragonhydraCoreNextcandidate' + identity[-12:]
    need(op.get('service_name') == plan.get('service_name') == profile.get('service_name') == service,
         'RECOVERY_SERVICE_IDENTITY_MISMATCH')
    need(receipt.get('version') == plan.get('version') == profile.get('version')
         and plan.get('build_id') == profile.get('build_id'), 'RECOVERY_BUILD_IDENTITY_MISMATCH')
    need(plan.get('ports') == profile.get('ports'), 'RECOVERY_PORT_IDENTITY_MISMATCH')
    ports = profile.get('ports', {})
    need(set(ports) == {'api', 'web', 'database'} and len(set(ports.values())) == 3
         and all(type(port) is int and 18800 <= port <= 65535 for port in ports.values()),
         'RECOVERY_ISOLATED_PORTS_REQUIRED')
    need(op.get('profile_sha256_before') == plan['profile']['sha256'] == receipt.get('profile_sha256')
         == digest(profile_path), 'ACL_ONLY_PROFILE_HASH_CHANGED')
    setup, helper = (bound(plan[key]) for key in ('setup', 'profile_helper'))
    need(setup.is_relative_to(lab / 'dist') and setup.suffix.lower() == '.exe', 'OWNED_SETUP_REQUIRED')
    need(receipt.get('setup_sha256') == plan['setup']['sha256'], 'ORIGINAL_SETUP_BINDING_MISMATCH')
    need(helper.is_relative_to(lab) and helper.name == 'CoreNextProfile.ps1', 'OWNED_PROFILE_HELPER_REQUIRED')
    return {'schema_version': 'core-next.acl-recovery-contract/1', 'validated': True,
            'operation_id': op['operation_id'], 'installation_id': identity,
            'source_commit': source, 'service_name': service, 'original_outcome': 'FAIL_PRESERVED',
            'profile_sha256': digest(profile_path), 'service_actions': 0, 'release_accepted': False,
            'scope': 'Evidence and identity guards only; effective token access and startup require execution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation', required=True)
    parser.add_argument('--operation-sha256', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_recovery(args.operation, args.operation_sha256)))
        return 0
    except (RecoveryContractError, KeyError, TypeError, ValueError, OSError) as error:
        print(json.dumps({'validated': False, 'code': str(error) if isinstance(error, RecoveryContractError)
                          else 'INVALID_RECOVERY_INPUT', 'service_actions': 0, 'release_accepted': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
