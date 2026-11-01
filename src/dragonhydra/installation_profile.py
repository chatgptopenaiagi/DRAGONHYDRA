"""Read-only CORE NEXT server binding. Missing identity never selects another backend."""
from pathlib import Path, PurePosixPath
import json
import os
import re

WINDOWS_LAB_ROOT = Path(r'C:\xampp\DRAGONHYDRA-CORE-NEXT-LAB')
POSIX_LAB_ROOT = '/var/lib/dragonhydra-core-next-lab'


def posix_lab_root(value):
    """Validate the explicit POSIX root without interpreting Windows paths."""
    raw = str(value)
    path = PurePosixPath(raw)
    if (not path.is_absolute() or path == PurePosixPath('/') or '..' in path.parts
            or raw.startswith('//') or '\\' in raw or any(ord(c) < 32 for c in raw)):
        raise ValueError('CORE_NEXT_ABSOLUTE_ISOLATED_POSIX_LAB_REQUIRED')
    return str(path)


def selected_lab_root(environment=None):
    # Windows deployments retain their fixed root even if another environment
    # happens to define the POSIX override. No inherited original state is used.
    if os.name == 'nt':
        return WINDOWS_LAB_ROOT
    environment = os.environ if environment is None else environment
    return Path(posix_lab_root(environment.get('DRAGONHYDRA_CORE_NEXT_LAB_ROOT', POSIX_LAB_ROOT)))


LAB_ROOT = selected_lab_root()


def isolated_environment(environment):
    """Only explicit CORE NEXT variables may feed inherited credential adapters.

    Return a new process environment; never change machine/user environment.
    Values are deliberately not logged or returned in diagnostic payloads.
    """
    prefix = 'DRAGONHYDRA_CORE_NEXT_'
    scoped = {key[len(prefix):]:value for key,value in environment.items() if key.startswith(prefix)}
    result = {key:value for key,value in environment.items() if not key.startswith('DRAGONHYDRA_')}
    for suffix,value in scoped.items():
        if re.fullmatch(r'[A-Z][A-Z0-9_]*',suffix):
            result['DRAGONHYDRA_'+suffix] = value
    return result


def ordinary(path, root=None):
    root = selected_lab_root() if root is None else Path(root)
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('CORE_NEXT_ABSOLUTE_PATH_REQUIRED')
    current = path
    while current != current.parent:
        if current.is_symlink() or getattr(current, 'is_junction', lambda:False)():
            raise ValueError('CORE_NEXT_REPARSE_PATH_REJECTED')
        current = current.parent
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved == root.resolve():
        raise ValueError('CORE_NEXT_PATH_OUTSIDE_LAB')
    return resolved


def load_binding(state=None, profile_path=None, *, lab_root=None):
    """Validate deployment identity before creating directories or opening state."""
    lab = Path(lab_root) if lab_root else selected_lab_root()
    if state is not None:
        state = ordinary(state, lab)
    if profile_path is None and state is not None:
        identity_file = state/'product.json'
        if identity_file.is_file():
            identity = json.loads(identity_file.read_text(encoding='utf-8-sig'))
            profile_path = identity.get('profile_path')
    if not profile_path:
        raise ValueError('CORE_NEXT_INSTALLATION_PROFILE_REQUIRED')
    profile_path = ordinary(profile_path, lab)
    profile = json.loads(profile_path.read_text(encoding='utf-8-sig'))
    identifier = profile.get('installation_id','')
    if (profile.get('schema_version') != 1 or profile.get('product') != 'DRAGONHYDRA CORE NEXT'
            or profile.get('edition') != 'CORE NEXT' or not re.fullmatch(r'core-next-[0-9a-f]{32}', identifier)
            or profile.get('environment_id') not in {'baseline','candidate'}):
        raise ValueError('CORE_NEXT_PROFILE_IDENTITY_REQUIRED')
    root = lab/'profiles'/identifier
    if profile_path != (root/'installation-profile.json').resolve() or Path(profile['lab_root']).resolve() != lab.resolve():
        raise ValueError('CORE_NEXT_PROFILE_PATH_IDENTITY_MISMATCH')
    for field, child in [('install_root','application'),('state_root','state'),('browser_user_data','browser')]:
        if ordinary(profile[field],lab) != (root/child).resolve():
            raise ValueError('CORE_NEXT_PROFILE_PATH_IDENTITY_MISMATCH')
    expected_state = ordinary(Path(profile['state_root'])/'kernel',lab)
    if state is not None and state != expected_state:
        raise ValueError('CORE_NEXT_SERVER_STATE_MISMATCH')
    ports = [profile['ports'][key] for key in ['api','web','database']]
    if len(set(ports)) != 3 or any(type(p) is not int or not 18800 <= p <= 65535 for p in ports):
        raise ValueError('CORE_NEXT_DISTINCT_ISOLATED_PORTS_REQUIRED')
    if profile.get('copy_credentials') is not False or profile.get('provider_schedules') != 'disabled':
        raise ValueError('CORE_NEXT_FRESH_PRIVATE_STATE_REQUIRED')
    suffix = identifier[-12:]
    if profile.get('service_name') != 'DragonhydraCoreNext'+profile['environment_id']+suffix:
        raise ValueError('CORE_NEXT_SERVICE_IDENTITY_MISMATCH')
    if not re.fullmatch(r'[0-9a-f]{40}',profile.get('source_commit','')):
        raise ValueError('CORE_NEXT_SOURCE_IDENTITY_REQUIRED')
    if state is not None and (state/'product.json').is_file():
        identity = json.loads((state/'product.json').read_text(encoding='utf-8-sig'))
        for key in ['installation_id','environment_id','product','edition']:
            if identity.get(key) != profile[key]:
                raise ValueError('CORE_NEXT_PERSISTED_IDENTITY_MISMATCH')
    return profile, expected_state


def kernel_configuration(profile):
    from .kernel.contracts import KernelConfig
    return KernelConfig(**{key:profile[key] for key in ['installation_id','environment_id','product','edition',
        'build_id','source_commit','version']})
