"""Read-only publisher-signing preflight. No key creation, build or publication.

All private inputs come from the current process environment. Missing signing
inputs stop before tool execution or file creation; diagnostics never include values.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys


PREFIX = 'DRAGONHYDRA_ANDROID_'
REQUIRED = ('KEYSTORE', 'KEY_ALIAS', 'STORE_PASSWORD', 'KEY_PASSWORD', 'CERT_SHA256')
DEBUG_CERTIFICATE = 'd77e623706f0146bc495904affe310cb492d67277ecf70b28455d1f5e138e419'
KEYTOOL = Path(r'C:\Program Files\Android\openjdk\jdk-21.0.8\bin\keytool.exe')


class SigningError(Exception):
    pass


def fingerprint(value):
    normalized = value.replace(':', '').lower() if isinstance(value, str) else ''
    if not re.fullmatch('[a-f0-9]{64}', normalized):
        raise SigningError('expected_public_certificate_required')
    if normalized == DEBUG_CERTIFICATE:
        raise SigningError('debug_identity_rejected')
    return normalized


def validate_identity(actual, expected, subject='', entry_type='PrivateKeyEntry'):
    expected = fingerprint(expected)
    if actual == DEBUG_CERTIFICATE or re.search(r'(?:^|,)\s*CN\s*=\s*Android Debug(?:,|$)', subject, re.I):
        raise SigningError('debug_identity_rejected')
    if entry_type != 'PrivateKeyEntry':
        raise SigningError('publisher_private_key_entry_required')
    if actual != expected:
        raise SigningError('certificate_fingerprint_mismatch')
    return expected


def preflight(environment=None, *, run=subprocess.run):
    environment = dict(os.environ if environment is None else environment)
    missing = [PREFIX+name for name in REQUIRED if not environment.get(PREFIX+name)]
    common = {'files_changed': False, 'build_started': False, 'apk_created': False,
              'publisher_key_created': False, 'published': False}
    if missing:
        return {**common, 'status': 'requires_signing_configuration', 'missing_environment': missing,
                'message': 'Existing publisher signing inputs and an independently confirmed public certificate have not been supplied.'}
    try:
        expected = fingerprint(environment[PREFIX+'CERT_SHA256'])
        key_file = Path(environment[PREFIX+'KEYSTORE'])
        alias = environment[PREFIX+'KEY_ALIAS']
        if not key_file.is_absolute() or not key_file.is_file():
            raise SigningError('existing_publisher_keystore_required')
        if any('\0' in environment[PREFIX+name] or '\n' in environment[PREFIX+name]
               or '\r' in environment[PREFIX+name] for name in REQUIRED):
            raise SigningError('invalid_signing_input')
        if not KEYTOOL.is_file():
            raise SigningError('existing_keytool_unavailable')
        base = [str(KEYTOOL), '-J-Duser.language=en', '-J-Duser.country=US',
                '-keystore', str(key_file), '-alias', alias, '-storepass:env', PREFIX+'STORE_PASSWORD']
        listed = run([*base, '-list', '-v'], env=environment, capture_output=True, timeout=20, check=False)
        if listed.returncode:
            raise SigningError('signing_certificate_unavailable')
        text = listed.stdout.decode('utf-8', errors='replace')
        entry = re.search(r'^Entry type:\s*(\S+)', text, re.M)
        owner = re.search(r'^Owner:\s*(.*)', text, re.M)
        exported = run([*base, '-exportcert', '-rfc'], env=environment, capture_output=True, timeout=20, check=False)
        if exported.returncode:
            raise SigningError('signing_certificate_unavailable')
        match = re.search(rb'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----', exported.stdout)
        if not match:
            raise SigningError('signing_certificate_unavailable')
        certificate = ssl.PEM_cert_to_DER_cert(match.group().decode('ascii'))
        actual = hashlib.sha256(certificate).hexdigest()
        validate_identity(actual, expected, owner.group(1) if owner else '', entry.group(1) if entry else '')
        return {**common, 'status': 'certificate_configuration_verified', 'certificate_sha256': actual,
                'private_key_password_verified': False,
                'message': 'Certificate and private-key entry match. The opt-in Gradle profile separately verifies key-password access and certificate validity before building.'}
    except SigningError as error:
        return {**common, 'status': 'invalid_signing_configuration', 'code': str(error),
                'message': 'Publisher signing configuration was rejected; no build or identity change was attempted.'}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {**common, 'status': 'invalid_signing_configuration', 'code': 'signing_certificate_unavailable',
                'message': 'The existing signing identity could not be verified; private diagnostics are omitted.'}


def main():
    if len(sys.argv) != 1:
        print(json.dumps({'status': 'invalid_request', 'message': 'Provide signing inputs through the protected process environment only.'}))
        return 2
    result = preflight()
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'certificate_configuration_verified' else 2


if __name__ == '__main__':
    sys.exit(main())
