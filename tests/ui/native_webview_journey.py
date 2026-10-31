"""Gated native Tauri WebView2 content journey on the exact installed A5 server.

--prepare copies three verified released client files without opening the app.
--self-test exercises pure guards only. --execute-native-journey requires the
coordinator's explicit gate. It never launches Edge or alters the installation.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
import traceback
import unittest
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'build/connections/evidence/native-webview-cdp-r1'
PREP = BASE/'preparation'
INSTALL = ROOT/'build/workstation/test-install/provider-a2/application files'
STATE = ROOT/'build/workstation/test-install/provider-a2/state data/client'
FROZEN = ROOT/'build/release/v0.4.0-alpha.1/verification/payload/nsis-extracted'
ORIGIN = 'http://127.0.0.1:18746'
API = '/dragon/api/v1'
SOURCE = '7251f7fdded28f4f2af354313c0232a6d36cb8121d0eea746a9b3922b466566a'
CLIENT = '17b557c7a4f2524ace5769c3bace55583ce695a0f250771a3585ce954688f94b'
PORT = 19322
DEBUG_VARIABLES = {'PWDEBUG', 'DEBUG', 'DEBUG_FILE'}
DEBUG_ARGUMENTS = '--remote-debugging-address=127.0.0.1 --remote-debugging-port=19322'
FILES = {
    'DRAGONHYDRA-Client.exe': ('dragonhydra-desktop.exe', 8240128, CLIENT),
    'BUILD-INFO.json': ('BUILD-INFO.json', 191, '3f5882323f6c716d0a680599c9542eaddac1ff840e63097819a0122949eacb23'),
    'THIRD-PARTY-NOTICES.txt': ('THIRD-PARTY-NOTICES.txt', 2206151, 'e60dcba568f87127d2905cac7060f6eba21551d0f36915f8cfe9cc9893d93a8a'),
}
NOT_RUN = ['Native OS focus/keyboard/titlebar controls', 'Export or native SaveAs/file dialogs',
           'Installer/shortcut/clean-machine/missing-WebView installation', 'Provider retrieval/import',
           'Explanation/LLM jobs, model or credential configuration']


class Blocked(RuntimeError):
    pass


class ConcurrentChange(Blocked):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def owned_path(path, boundary):
    path, boundary = Path(path).resolve(), Path(boundary).resolve()
    if path == boundary or not path.is_relative_to(boundary):
        raise Blocked('PATH_OUTSIDE_OWNED_TEST_BOUNDARY')
    return path


def private_target(path):
    """Check the literal owned path BEFORE resolving any reparse point."""
    path = Path(path).absolute()
    if '..' in path.parts or path == BASE or not path.is_relative_to(BASE):
        raise Blocked('PRIVATE_COOKIE_PATH_OUTSIDE_OWNED_BOUNDARY')
    for parent in (path, *path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            pass
        else:
            if info.st_file_attributes & 0x400 or not stat.S_ISDIR(info.st_mode):
                raise Blocked('PRIVATE_COOKIE_PATH_REPARSE_OR_NOT_DIRECTORY')
        if parent == ROOT:
            break
    return path


def debug_environment(environment):
    """A copied map only: never change a parent/user/system environment."""
    return {name: value for name, value in environment.items() if name.upper() not in DEBUG_VARIABLES}


def strip_process_debug_environment():
    removed = []
    for name in tuple(os.environ):
        if name.upper() in DEBUG_VARIABLES:
            removed.append(name.upper())
            os.environ.pop(name, None)
    return sorted(removed)


def safe_url(value):
    """Never persist a token/query/unknown fragment from a CDP target."""
    try:
        parsed = urlsplit(str(value))
        origin = parsed.scheme+'://'+str(parsed.hostname or '')
        if parsed.port:
            origin += ':'+str(parsed.port)
        fragment = parsed.fragment
        allowed = re.fullmatch(r'(today|history|connections|match/[a-f0-9]{64}|team/[a-f0-9]{64}|standings/[a-f0-9]{64})', fragment)
        return origin+parsed.path+('#'+fragment if allowed else '#[REDACTED]' if fragment else '')
    except (TypeError, ValueError):
        return '[INVALID_URL]'


def allow_request(method, url):
    parsed = urlsplit(url)
    if parsed.scheme in ('data', 'blob'):
        return True
    if parsed.scheme+'://'+parsed.netloc != ORIGIN:
        return False
    return method in ('GET', 'HEAD') or method == 'POST' and parsed.path == API+'/session'


def source_guard(source):
    if source != SOURCE:
        raise ConcurrentChange('KERNEL_SOURCE_CHANGED_OR_NOT_EXACT_A5_R2')


def integrity_guard(value):
    if value != 'Medium':
        raise Blocked('STANDARD_USER_REQUIRED_NO_ELEVATION_OR_POLICY_WORKAROUND')


def listener_guard(rows, owned):
    if not rows:
        raise Blocked('OWNED_CDP_LISTENER_NOT_READY')
    for row in rows:
        if row['pid'] not in owned or row['address'] not in ('127.0.0.1', '::1') or row['port'] != PORT:
            raise Blocked('CDP_LISTENER_FOREIGN_OR_NON_LOOPBACK')


def close_target_guard(actual, expected):
    """A supported page close may address only the previously verified target."""
    parsed = urlsplit(actual.get('url', ''))
    if (not expected or actual.get('targetId') != expected.get('id') or actual.get('type') != 'page'
            or parsed.scheme+'://'+parsed.netloc != ORIGIN):
        raise Blocked('REFUSE_CLOSE_OF_UNVERIFIED_OR_DIFFERENT_WEBVIEW_TARGET')


class Windows:
    """Read-only process/token/socket inspection; owned lifecycle fallback."""
    def __init__(self):
        if os.name != 'nt':
            raise Blocked('THIS_NATIVE_JOURNEY_REQUIRES_WINDOWS')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        self.ip = ctypes.WinDLL('iphlpapi', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.kernel.LocalFree.argtypes = [ctypes.c_void_p]
        self.kernel.LocalFree.restype = ctypes.c_void_p
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
        self.advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        self.advapi.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_uint, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.advapi.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
        self.advapi.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
        self.advapi.GetSidSubAuthority.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        self.advapi.GetSidSubAuthority.restype = ctypes.POINTER(wintypes.DWORD)
        self.advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
        self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
        self.advapi.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
        self.advapi.SetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_uint, wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.advapi.SetNamedSecurityInfoW.restype = wintypes.DWORD
        self.advapi.GetNamedSecurityInfoW.argtypes = [wintypes.LPWSTR, ctypes.c_uint, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
        self.advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
        self.advapi.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
        self.advapi.GetAce.argtypes = [ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p)]
        self.kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        self.ip.GetExtendedTcpTable.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.DWORD, ctypes.c_uint, wintypes.DWORD]

    def _sid_text(self, sid):
        text = wintypes.LPWSTR()
        if not self.advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise Blocked('PRIVATE_ACL_SID_QUERY_FAILED')
        try:
            return text.value
        finally:
            self.kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))

    def _current_sid(self):
        process = self.kernel.OpenProcess(0x1000, False, os.getpid())
        token = wintypes.HANDLE()
        if not process or not self.advapi.OpenProcessToken(process, 8, ctypes.byref(token)):
            if process:
                self.kernel.CloseHandle(process)
            raise Blocked('PRIVATE_ACL_CURRENT_USER_QUERY_FAILED')
        try:
            length = wintypes.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(length))
            buffer = ctypes.create_string_buffer(length.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, length, ctypes.byref(length)):
                raise Blocked('PRIVATE_ACL_CURRENT_USER_QUERY_FAILED')
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
            return self._sid_text(sid)
        finally:
            self.kernel.CloseHandle(token)
            self.kernel.CloseHandle(process)

    def verify_private_acl(self, path, *, directory=True):
        path = Path(path).absolute()
        private_target(path if directory else path.parent)
        info = path.lstat()
        if info.st_file_attributes & 0x400 or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise Blocked('PRIVATE_COOKIE_OBJECT_REPARSE_OR_WRONG_TYPE')
        owner, acl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        code = self.advapi.GetNamedSecurityInfoW(str(path), 1, 0x00000005, ctypes.byref(owner), None, ctypes.byref(acl), None, ctypes.byref(descriptor))
        if code:
            raise Blocked('PRIVATE_COOKIE_ACL_READ_FAILED')
        try:
            user_sid = self._current_sid()
            if self._sid_text(owner) != user_sid or not acl.value:
                raise Blocked('PRIVATE_COOKIE_OWNER_OR_DACL_INVALID')
            control, revision = wintypes.WORD(), wintypes.DWORD()
            if not self.advapi.GetSecurityDescriptorControl(descriptor, ctypes.byref(control), ctypes.byref(revision)):
                raise Blocked('PRIVATE_COOKIE_DACL_CONTROL_QUERY_FAILED')
            protected = bool(control.value & 0x1000)
            if directory and not protected:
                raise Blocked('PRIVATE_COOKIE_DIRECTORY_INHERITANCE_NOT_DISABLED')
            # ACL header: revision/reserved,size,ACEcount,reserved.
            count = ctypes.c_ushort.from_address(acl.value+4).value
            trustees = []
            if count != 2:
                raise Blocked('PRIVATE_COOKIE_DACL_MUST_HAVE_EXACTLY_TWO_RULES')
            for index in range(count):
                ace = ctypes.c_void_p()
                if not self.advapi.GetAce(acl, index, ctypes.byref(ace)):
                    raise Blocked('PRIVATE_COOKIE_ACE_QUERY_FAILED')
                kind = ctypes.c_ubyte.from_address(ace.value).value
                flags = ctypes.c_ubyte.from_address(ace.value+1).value
                mask = wintypes.DWORD.from_address(ace.value+4).value
                if kind != 0 or mask & 0x1f01ff != 0x1f01ff or directory and (flags & 0x10 or flags & 3 != 3):
                    raise Blocked('PRIVATE_COOKIE_RULE_NOT_EXPLICIT_FULL_CONTROL')
                trustees.append(self._sid_text(ctypes.c_void_p(ace.value+8)))
            if set(trustees) != {user_sid, 'S-1-5-18'}:
                raise Blocked('PRIVATE_COOKIE_DACL_HAS_UNAUTHORIZED_TRUSTEES')
            return {'current_user_and_system_only': True, 'owner_current_user': True, 'ace_count': 2,
                    'inheritance_disabled': protected, 'reparse_points_rejected': True, 'object_type': 'directory' if directory else 'file'}
        finally:
            self.kernel.LocalFree(descriptor)

    def private_directory(self, path):
        path = private_target(path)
        if path.exists():
            return self.verify_private_acl(path)
        path.mkdir()
        # Empty owned directory only. No cookie/key exists before verified DACL.
        descriptor, acl = ctypes.c_void_p(), ctypes.c_void_p()
        sddl = 'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;'+self._current_sid()+')'
        if not self.advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None):
            raise Blocked('PRIVATE_COOKIE_DACL_CONSTRUCTION_FAILED')
        try:
            present, defaulted = wintypes.BOOL(), wintypes.BOOL()
            if not self.advapi.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)) or not present:
                raise Blocked('PRIVATE_COOKIE_DACL_CONSTRUCTION_FAILED')
            code = self.advapi.SetNamedSecurityInfoW(str(path), 1, 0x80000004, None, None, acl, None)
            if code:
                raise Blocked('PRIVATE_COOKIE_DACL_SET_FAILED')
        finally:
            self.kernel.LocalFree(descriptor)
        return self.verify_private_acl(path)

    def process(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            raise Blocked('OWNED_PROCESS_QUERY_FAILED')
        try:
            size = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(size.value)
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                raise Blocked('OWNED_PROCESS_IMAGE_QUERY_FAILED')
            values = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                raise Blocked('OWNED_PROCESS_CREATION_TIME_QUERY_FAILED')
            creation = values[0].dwHighDateTime << 32 | values[0].dwLowDateTime
            token = wintypes.HANDLE()
            if not self.advapi.OpenProcessToken(handle, 8, ctypes.byref(token)):
                raise Blocked('OWNED_PROCESS_INTEGRITY_QUERY_FAILED')
            try:
                length = wintypes.DWORD()
                self.advapi.GetTokenInformation(token, 25, None, 0, ctypes.byref(length))
                buffer = ctypes.create_string_buffer(length.value)
                if not self.advapi.GetTokenInformation(token, 25, buffer, length, ctypes.byref(length)):
                    raise Blocked('OWNED_PROCESS_INTEGRITY_QUERY_FAILED')
                sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
                count = self.advapi.GetSidSubAuthorityCount(sid).contents.value
                rid = self.advapi.GetSidSubAuthority(sid, count-1).contents.value
                level = 'SystemOrHigher' if rid >= 16384 else 'High' if rid >= 12288 else 'Medium' if rid >= 8192 else 'Low' if rid >= 4096 else 'Untrusted'
            finally:
                self.kernel.CloseHandle(token)
            return {'pid': pid, 'path': str(Path(path.value).resolve()), 'creation_filetime': creation, 'integrity_class': level}
        finally:
            self.kernel.CloseHandle(handle)

    def tree(self):
        class Entry(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                        ('module', wintypes.DWORD), ('threads', wintypes.DWORD), ('parent', wintypes.DWORD),
                        ('priority', wintypes.LONG), ('flags', wintypes.DWORD), ('name', wintypes.WCHAR*260)]
        first, next_ = self.kernel.Process32FirstW, self.kernel.Process32NextW
        for method in (first, next_):
            method.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        handle = self.kernel.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value:
            raise Blocked('PROCESS_TREE_QUERY_FAILED')
        try:
            entry = Entry()
            entry.size = ctypes.sizeof(entry)
            result = {}
            present = first(handle, ctypes.byref(entry))
            while present:
                result[entry.pid] = {'parent': entry.parent, 'name': entry.name}
                present = next_(handle, ctypes.byref(entry))
            return result
        finally:
            self.kernel.CloseHandle(handle)

    def descendants(self, pid):
        tree = self.tree()
        found = {pid}
        while True:
            more = {child for child, entry in tree.items() if entry['parent'] in found}
            if more <= found:
                return found
            found |= more

    def listeners(self):
        class V4(ctypes.Structure):
            _fields_ = [(name, wintypes.DWORD) for name in ('state', 'address', 'port', 'remote', 'remote_port', 'pid')]
        class V6(ctypes.Structure):
            _fields_ = [('address', ctypes.c_ubyte*16), ('scope', wintypes.DWORD), ('port', wintypes.DWORD),
                        ('remote', ctypes.c_ubyte*16), ('remote_scope', wintypes.DWORD), ('remote_port', wintypes.DWORD),
                        ('state', wintypes.DWORD), ('pid', wintypes.DWORD)]
        found = []
        for family, row_type in ((socket.AF_INET, V4), (socket.AF_INET6, V6)):
            length = wintypes.DWORD()
            code = self.ip.GetExtendedTcpTable(None, ctypes.byref(length), False, family, 5, 0)
            if code not in (0, 122):
                raise Blocked('CDP_LISTENER_QUERY_FAILED')
            buffer = ctypes.create_string_buffer(length.value)
            if self.ip.GetExtendedTcpTable(buffer, ctypes.byref(length), False, family, 5, 0):
                raise Blocked('CDP_LISTENER_QUERY_FAILED')
            count = wintypes.DWORD.from_buffer(buffer).value
            for index in range(count):
                row = row_type.from_buffer_copy(buffer, 4+index*ctypes.sizeof(row_type))
                port = socket.ntohs(row.port & 0xffff)
                if row.state != 2 or port != PORT:
                    continue
                address = socket.inet_ntoa(struct.pack('<L', row.address)) if family == socket.AF_INET else socket.inet_ntop(socket.AF_INET6, bytes(row.address))
                found.append({'address': address, 'port': port, 'pid': row.pid})
        return found

    def terminate_owned(self, expected):
        """Validate creation time/image on the SAME handle before fallback kill."""
        handle = self.kernel.OpenProcess(0x1001, False, expected['pid'])
        if not handle:
            return False
        try:
            count = wintypes.DWORD(32768)
            path = ctypes.create_unicode_buffer(count.value)
            values = [wintypes.FILETIME() for _ in range(4)]
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(count)) or not self.kernel.GetProcessTimes(handle, *(ctypes.byref(value) for value in values)):
                raise Blocked('REFUSE_CHILD_CLEANUP_WITHOUT_PROCESS_PROOF')
            creation = values[0].dwHighDateTime << 32 | values[0].dwLowDateTime
            if creation != expected['creation_filetime'] or str(Path(path.value).resolve()) != expected['path']:
                raise Blocked('PID_REUSE_OR_IMAGE_CHANGE_CHILD_NOT_TOUCHED')
            return bool(self.kernel.TerminateProcess(handle, 1))
        finally:
            self.kernel.CloseHandle(handle)


def prepare():
    windows = Windows()
    integrity = windows.process(os.getpid())['integrity_class']
    integrity_guard(integrity)
    manifest_path = INSTALL/'PAYLOAD-MANIFEST.json'
    manifest = json.loads(manifest_path.read_text())
    entries = {item['path'].removeprefix('client/'): item for item in manifest['files'] if item['path'].startswith('client/')}
    if set(entries) != set(FILES):
        raise Blocked('INSTALLED_CLIENT_ALLOWLIST_CHANGED')
    verified = []
    for name, (frozen_name, size, expected) in FILES.items():
        for candidate in (FROZEN/frozen_name, INSTALL/'client'/name):
            if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size != size or digest(candidate) != expected:
                raise Blocked('FROZEN_OR_INSTALLED_CLIENT_BYTES_CHANGED')
        if entries[name]['bytes'] != size or entries[name]['sha256'] != expected:
            raise Blocked('INSTALLED_PAYLOAD_MANIFEST_MISMATCH')
        verified.append({'filename': name, 'frozen_filename': frozen_name, 'bytes': size, 'sha256': expected})
    metadata_path = INSTALL/'server/_internal/dragonhydra/build_info.json'
    metadata = json.loads(metadata_path.read_text())
    source_guard(metadata.get('source_content_sha256'))
    endpoint = json.loads((STATE/'endpoint.json').read_text(encoding='utf-8-sig'))
    if endpoint.get('url') != ORIGIN:
        raise Blocked('EXACT_EXISTING_TEST_ENDPOINT_REQUIRED')
    if windows.listeners():
        raise Blocked('DEDICATED_DEBUG_PORT_ALREADY_OCCUPIED')
    acl_proof_path = BASE/'acl-probe-r2/verification.json'
    acl_proof = json.loads(acl_proof_path.read_text())
    if not acl_proof['passed'] or acl_proof['harness_sha256'] != digest(__file__):
        raise Blocked('CURRENT_NATIVE_PROFILE_ACL_PROOF_REQUIRED')
    test_app = PREP/'test-app'
    existing = test_app.exists()
    if existing and {path.name for path in test_app.iterdir()} != set(FILES):
        raise Blocked('PRESERVE_UNEXPECTED_TEST_APP_FILES')
    test_app.mkdir(parents=True, exist_ok=True)
    for item in verified:
        if not existing:
            shutil.copyfile(FROZEN/item['frozen_filename'], test_app/item['filename'])
        if digest(test_app/item['filename']) != item['sha256']:
            raise Blocked('ISOLATED_COPY_HASH_MISMATCH')
    contract = {'schema_version': 1, 'prepared_at': stamp(), 'status': 'PREPARED_NOT_LAUNCHED_AWAITING_COORDINATOR_GATE',
        'expected_kernel_source': SOURCE, 'kernel_family': 'Windows A5-r2', 'client_source_sha': 'a1380545bd3bb225f400e7e328535ff692c0123a',
        'expected_client_sha256': CLIENT, 'origin': ORIGIN, 'debug_port': PORT,
        'files': verified, 'harness_sha256': digest(__file__), 'current_integrity_class': integrity,
        'client_launched': False, 'child_integrity_tested': False, 'profile_created': False, 'api_requested': False,
        'existing_test_app_idempotently_verified': existing,
        'cleanup_policy': 'Only supported page.close on the verified existing target; otherwise guarded non-UI owned-process lifecycle termination with clean exit explicitly unverified.',
        'installed_client_manifest_sha256': digest(manifest_path), 'kernel_metadata_sha256': digest(metadata_path),
        'pairing_state_policy': 'Existing isolated workstation client state is read-only; no pairing/vault/database copy.',
        'profile_policy': 'Future run/profile only, new project-controlled WebView2 profile; do not distribute.',
        'environment': {'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS': DEBUG_ARGUMENTS, 'WEBVIEW2_USER_DATA_FOLDER': '<owned-run/profile>'},
        'diagnostic_logging': {'stripped_from_harness_process_and_owned_child_only': sorted(DEBUG_VARIABLES), 'global_environment_unchanged': True, 'values_not_recorded': True},
        'profile_protection': {'native_windows_acl': 'Current user and SYSTEM only; protected DACL, inheritance disabled, no reparse points',
            'applied_before_client_launch': True, 'actual_cookie_directories_created_now': False,
            'functional_probe': str(acl_proof_path.relative_to(ROOT)), 'functional_probe_sha256': digest(acl_proof_path)},
        'prior_a4_mismatch': {'prior_expected_source': '8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5',
            'observed_source': SOURCE, 'classification': 'Concurrent primary CLI A5-r2 install; coordinator explicitly retargeted this preparation to exact A5-r2.'},
        'proof_scope': 'Copied exact complete client payload3files, not a new client build, installation or elevation/policy bypass.',
        'not_run': NOT_RUN}
    (PREP/'CONTRACT.json').write_text(json.dumps(contract, indent=2)+'\n')
    print(json.dumps({'status': contract['status'], 'integrity_class': integrity, 'verified_copied_files': 3,
                      'client_launched': False, 'contract': str((PREP/'CONTRACT.json').relative_to(ROOT))}))


def execute(run_index=1):
    if type(run_index) is not int or not 1 <= run_index <= 100:
        raise Blocked('BOUNDED_EXPLICIT_RUN_INDEX_REQUIRED')
    stripped_debug = strip_process_debug_environment()
    contract = json.loads((PREP/'CONTRACT.json').read_text())
    if contract['harness_sha256'] != digest(__file__) or contract['expected_kernel_source'] != SOURCE:
        raise Blocked('REVIEWED_HARNESS_OR_CONTRACT_CHANGED')
    work = BASE/('run' if run_index == 1 else 'run-r'+str(run_index))
    if work.exists():
        raise Blocked('PRESERVE_FIRST_NATIVE_RUN_NO_AUTOMATIC_RETRY')
    windows = Windows()
    integrity_guard(windows.process(os.getpid())['integrity_class'])
    app = PREP/'test-app/DRAGONHYDRA-Client.exe'
    for name, (_, size, expected) in FILES.items():
        candidate = PREP/'test-app'/name
        if candidate.is_symlink() or candidate.stat().st_size != size or digest(candidate) != expected:
            raise Blocked('ISOLATED_CLIENT_PAYLOAD_CHANGED')
    if windows.listeners():
        raise Blocked('DEDICATED_DEBUG_PORT_ALREADY_OCCUPIED')
    work_protection = windows.private_directory(work)
    report = {'schema_version': 1, 'started_at': stamp(), 'passed': False, 'groups': [],
        'scope': 'Actual copied, byte-identical installed Tauri client WebView2 content via loopback CDP, exact A5-r2 service; not native focus/dialog/installer evidence.',
        'harness_sha256': digest(__file__), 'expected_kernel_source': SOURCE, 'client_sha256': CLIENT,
        'current_integrity_class': 'Medium', 'run_index': run_index, 'native_app_launched': False, 'provider_import_requested': False,
        'settings_changed': False, 'llm_requested': False, 'export_requested': False, 'not_run': NOT_RUN,
        'blocked_requests': [], 'api_responses': [], 'page_errors': [], 'screenshots': [],
        'private_cookie_directories': {'run': work_protection},
        'diagnostic_logging': {'removed_names_from_own_harness_process': stripped_debug,
            'owned_child_env_filtered': True, 'values_not_recorded': True, 'parent_user_system_environment_unchanged': True}}
    process = None
    pw = None
    page = None
    session = None
    client_info = None
    owned = {}
    token = ''
    opener = build_opener(ProxyHandler({}))
    def safe(value):
        value = str(value)
        if token:
            value = value.replace(token, '[REDACTED]')
        return re.sub(r'https?://[^\s\"\'<>]+', lambda match: safe_url(match[0]), value)
    def check(name, **details):
        report['groups'].append({'name': name, 'passed': True, **details})
        print(json.dumps(report['groups'][-1]), flush=True)
    def api(path):
        with opener.open(Request(ORIGIN+API+path, headers={'Authorization': 'Bearer '+token}), timeout=15) as response:
            if response.status != 200:
                raise Blocked('READONLY_API_PREFLIGHT_FAILED')
            return json.load(response)
    def state_snapshot():
        files = {'endpoint': STATE/'endpoint.json', 'pairing': STATE/'local-session.json',
            'kernel_metadata': INSTALL/'server/_internal/dragonhydra/build_info.json'}
        return {name: digest(path) for name, path in files.items()}
    def kernel():
        metadata = json.loads((INSTALL/'server/_internal/dragonhydra/build_info.json').read_text())
        source_guard(metadata.get('source_content_sha256'))
        system = api('/system')
        source_guard(system['build'].get('source_content_sha256'))
        if system.get('status') != 'ready':
            raise Blocked('EXACT_A5_TEST_SERVER_NOT_READY')
        return {'source_content_sha256': system['build']['source_content_sha256'], 'status': system['status']}
    def screenshot(name):
        if urlsplit(page.url).scheme+'://'+urlsplit(page.url).netloc != ORIGIN or '#token=' in page.url:
            raise Blocked('DO_NOT_CAPTURE_UNPAIRED_OR_FOREIGN_CONTENT')
        if page.locator('#login-dialog').is_visible():
            raise Blocked('DO_NOT_CAPTURE_PAIRING_DIALOG')
        destination = work/(name+'.png')
        page.screenshot(path=str(destination), full_page=True)
        report['screenshots'].append({'path': destination.name, 'bytes': destination.stat().st_size, 'sha256': digest(destination), 'route': safe_url(page.url), 'kind': 'CDP rendering of verified native WebView content, not desktop foreground/window chrome'})
    try:
        endpoint = json.loads((STATE/'endpoint.json').read_text(encoding='utf-8-sig'))
        if endpoint.get('url') != ORIGIN:
            raise ConcurrentChange('EXISTING_TEST_ENDPOINT_CHANGED')
        token = json.loads((STATE/'local-session.json').read_text(encoding='utf-8-sig'))['token']
        before_files = state_snapshot()
        report['before_kernel'] = kernel()
        before_counts = {item['id']: item['record_count'] for item in api('/connections')['items']}
        if before_counts.get('football-data-couk', 0) < 1:
            raise Blocked('NO_RETAINED_FOOTBALL_DATA_NO_IMPORT_WILL_BE_REQUESTED')
        report['before_counts'] = before_counts
        baseline_pids = set(windows.tree())
        profile = owned_path(work/'profile', work)
        if profile.exists():
            raise Blocked('FRESH_OWNED_PROFILE_REQUIRED')
        report['private_cookie_directories']['profile'] = windows.private_directory(profile)
        environment = debug_environment(os.environ)
        environment['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = DEBUG_ARGUMENTS
        environment['WEBVIEW2_USER_DATA_FOLDER'] = str(profile)
        if os.environ.get('WEBVIEW2_WAIT_FOR_SCRIPT_DEBUGGER') or os.environ.get('WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER'):
            raise Blocked('UNRELATED_PARENT_DEBUGGER_ENVIRONMENT_REQUIRES_REVIEW')
        argv = [str(app), '--state', str(STATE), '--profile', str(profile)]
        # This is the sole app launch. There is no shell, browser launch, broker,
        # elevation, privilege change, global env, policy or secondary server.
        process = subprocess.Popen(argv, cwd=app.parent, env=environment, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
        report['native_app_launched'] = True
        client_info = windows.process(process.pid)
        if process.pid in baseline_pids or Path(client_info['path']) != app.resolve():
            raise Blocked('NEW_EXACT_COPIED_CLIENT_IDENTITY_FAILED')
        integrity_guard(client_info['integrity_class'])
        report['client_process'] = client_info
        report['arguments'] = ['--state', str(STATE.relative_to(ROOT)), '--profile', str(profile.relative_to(ROOT))]
        deadline = time.monotonic()+45
        rows = []
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise Blocked('CLIENT_EXITED_BEFORE_CDP_READINESS')
            children = windows.descendants(process.pid)
            rows = windows.listeners()
            if rows:
                listener_guard(rows, children-{process.pid})
                for row in rows:
                    info = windows.process(row['pid'])
                    if Path(info['path']).name.lower() != 'msedgewebview2.exe' or row['pid'] in baseline_pids:
                        raise Blocked('CDP_LISTENER_NOT_NEW_OWNED_WEBVIEW2')
                    owned[row['pid']] = info
                break
            time.sleep(.15)
        else:
            raise Blocked('CDP_NOT_AVAILABLE_NO_POLICY_WORKAROUND')
        report['debug_listeners'] = rows
        report['webview_processes'] = list(owned.values())
        report['actual_listener_runtime_files'] = [{'path': item['path'], 'bytes': Path(item['path']).stat().st_size,
            'sha256': digest(item['path']), 'version_directory': Path(item['path']).parent.name} for item in owned.values()]
        check('Copied native client and its new WebView2 child run Medium integrity with owned loopback CDP listener', client_pid=process.pid, port=PORT)
        from playwright.sync_api import sync_playwright, expect
        if any(name.upper() in DEBUG_VARIABLES for name in os.environ):
            raise Blocked('PLAYWRIGHT_DEBUG_ENVIRONMENT_MUST_BE_EMPTY_BEFORE_DRIVER_START')
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp('http://127.0.0.1:'+str(PORT), timeout=15000)
        if len(browser.contexts) != 1:
            raise Blocked('AMBIGUOUS_NATIVE_WEBVIEW_CONTEXT')
        context = browser.contexts[0]
        deadline = time.monotonic()+30
        while time.monotonic() < deadline:
            matches = [candidate for candidate in context.pages if urlsplit(candidate.url).scheme+'://'+urlsplit(candidate.url).netloc == ORIGIN]
            if len(matches) == 1:
                page = matches[0]
                break
            time.sleep(.1)
        if page is None:
            raise Blocked('EXISTING_NATIVE_APP_PAGE_NOT_IDENTIFIED')
        page.set_default_timeout(15000)
        def guarded_route(route):
            request = route.request
            if allow_request(request.method, request.url):
                route.continue_()
            else:
                report['blocked_requests'].append({'method': request.method, 'url': safe_url(request.url)})
                route.abort('blockedbyclient')
        context.route('**/*', guarded_route)
        page.on('pageerror', lambda error: report['page_errors'].append(safe(error)))
        def observe(response):
            parsed = urlsplit(response.url)
            if parsed.path.startswith(API):
                report['api_responses'].append({'path': parsed.path, 'status': response.status, 'method': response.request.method})
        page.on('response', observe)
        expect(page.get_by_role('heading', name='Today’s football', exact=True)).to_be_visible(timeout=30000)
        expect(page.locator('#service-state')).to_have_text('Server ready · sqlite')
        if 'DRAGONHYDRA' not in page.title() or '#token=' in page.url:
            raise Blocked('NATIVE_APP_TITLE_OR_AUTHENTICATED_ROUTE_MISMATCH')
        session = context.new_cdp_session(page)
        target = session.send('Target.getTargetInfo')['targetInfo']
        source_guard(api('/system')['build'].get('source_content_sha256'))
        report['target'] = {'id': target['targetId'], 'type': target['type'], 'url': safe_url(target['url']), 'title': page.title(),
            'webview2_bridge_present': page.evaluate('Boolean(window.chrome && window.chrome.webview)'),
            'tauri_bridge_present': page.evaluate('Boolean(window.__TAURI_INTERNALS__)')}
        screenshot('today')
        check('Existing native WebView page authenticates to exact A5-r2 and renders Today/Ready; no external browser/page created')
        page.get_by_role('button', name='Browse retained matches', exact=True).first.click()
        expect(page.get_by_role('heading', name='Retained matches', exact=True)).to_be_visible()
        expect(page.locator('.match-card').first).to_be_visible()
        page.get_by_role('link', name='Connections', exact=True).click()
        page.locator('[data-provider="football-data-couk"]').get_by_role('button', name='Open imported data', exact=True).click()
        expect(page.get_by_role('table')).to_be_visible()
        page.get_by_role('combobox', name='Record type').select_option('historical_result')
        page.get_by_role('table').get_by_role('button').first.click()
        expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
        match_url = page.url
        match_id = urlsplit(match_url).fragment.removeprefix('match/')
        if not re.fullmatch('[a-f0-9]{64}', match_id):
            raise Blocked('REAL_CANONICAL_MATCH_ROUTE_REQUIRED')
        match = api('/matches/'+match_id)
        if match['source_id'] != 'football-data-couk' or match['status'] != 'finished':
            raise Blocked('SELECTED_RETAINED_FOOTBALL_SOURCE_MISMATCH')
        report['match'] = {key: match[key] for key in ('id', 'source_id', 'home', 'away', 'event_date', 'status', 'version')}
        screenshot('match')
        check('Real native controls browse retained records and select a finished canonical Football-Data match', match_id=match_id)
        team_button = page.locator('.team-button').first
        team_name = team_button.get_attribute('aria-label').removeprefix('View team ')
        team_button.click()
        expect(page.get_by_role('heading', name=team_name, exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Recent form', exact=True)).to_be_visible()
        screenshot('team')
        page.get_by_role('button', name='← Return to selected match', exact=True).click()
        expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
        if page.url != match_url:
            raise Blocked('SELECTED_MATCH_CONTEXT_LOST')
        page.get_by_role('button', name='Open standings', exact=True).click()
        expect(page.get_by_role('table')).to_be_visible()
        expect(page.get_by_text('RECONSTRUCTED', exact=True)).to_be_visible()
        screenshot('standings')
        page.get_by_role('button', name='← Return to selected match', exact=True).click()
        expect(page.get_by_role('heading', name='Match overview', exact=True)).to_be_visible()
        if page.url != match_url:
            raise Blocked('SELECTED_MATCH_CONTEXT_LOST')
        check('Native team/form and reconstructed standings controls return to the identical selected match')
        page.get_by_role('tab', name='Analysis', exact=True).click()
        expect(page.get_by_role('heading', name='Model probabilities', exact=True)).to_be_visible()
        prediction = api('/matches/'+match_id+'/predictions')
        if prediction.get('available'):
            expect(page.get_by_text('STATISTICAL FORECAST', exact=True)).to_be_visible()
        elif prediction.get('reason'):
            expect(page.get_by_text(prediction['reason'], exact=True)).to_be_visible()
        else:
            raise Blocked('ANALYSIS_AVAILABILITY_REASON_REQUIRED')
        report['analysis'] = {'available': prediction.get('available'), 'reason': prediction.get('reason'), 'read_only_get': True,
                              'llm_explanation_requested': False}
        screenshot('analysis')
        check('Native Analysis control shows actual same-match probabilities or explicit unavailable evidence reason without any job/model request')
        report['after_kernel'] = kernel()
        after_counts = {item['id']: item['record_count'] for item in api('/connections')['items']}
        if state_snapshot() != before_files or after_counts != before_counts or api('/matches/'+match_id)['version'] != match['version']:
            raise ConcurrentChange('PRIMARY_INSTALL_OR_RETAINED_STATE_CHANGED_DURING_NATIVE_TEST')
        if report['page_errors'] or report['blocked_requests']:
            raise Blocked('WEBVIEW_ERROR_OR_FORBIDDEN_REQUEST_OBSERVED')
        report['state_retained'] = {'pairing_endpoint_kernel_files_unchanged': True, 'record_counts_unchanged': True, 'selected_revision_unchanged': True,
                                   'authentication_session_row_may_be_created': True}
        check('Exact A5-r2 kernel, pairing/endpoint files, retained counts and selected revision remain unchanged')
        report['journey_passed'] = True
    except Exception as error:
        report['error'] = safe(type(error).__name__+': '+str(error))
        report['failure_class'] = 'concurrent_primary_change_not_application_defect' if isinstance(error, ConcurrentChange) else 'bounded_native_journey_failure_or_preflight_block'
        report['traceback'] = safe(traceback.format_exc())
    finally:
        # Browser.close and direct Windows UI controls are never used. Supported
        # page.close is scoped to the exact existing native WebView target.
        report['native_navigation_verified'] = bool(report.get('journey_passed'))
        report['clean_exit_verified'] = False
        report['forced_cleanup'] = False
        if page is not None and session is not None and report.get('target') and process is not None and process.poll() is None:
            try:
                current = windows.process(process.pid)
                if client_info is None or current['creation_filetime'] != client_info['creation_filetime'] or current['path'] != client_info['path']:
                    raise Blocked('REFUSE_PAGE_CLOSE_WITHOUT_EXACT_OWNED_HOST_IDENTITY')
                listener_guard(windows.listeners(), windows.descendants(process.pid)-{process.pid})
                current_target = session.send('Target.getTargetInfo')['targetInfo']
                close_target_guard(current_target, report['target'])
                report['supported_page_close_attempted'] = True
                page.close(run_before_unload=False, reason='Owned native WebView diagnostic complete')
                report['supported_page_close_returned'] = True
            except Exception as error:
                report['supported_page_close_error'] = safe(error)
        if session is not None:
            try:
                session.detach()
            except Exception:
                pass
        if pw is not None:
            try:
                pw.stop()
            except Exception as error:
                report['disconnect_error'] = safe(error)
        if process is not None:
            if process.poll() is None:
                try:
                    process.wait(timeout=12)
                except Exception as error:
                    report['host_exit_wait_error'] = safe(error)
                    # Popen's original process HANDLE cannot target a reused PID.
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=10)
                        report['forced_owned_client_termination'] = True
                        report['forced_cleanup'] = True
            report['client_exit_code'] = process.returncode
            deadline = time.monotonic()+10
            while time.monotonic() < deadline and windows.listeners():
                time.sleep(.2)
            remaining = windows.listeners()
            if remaining:
                fallback = []
                for row in remaining:
                    previous = owned.get(row['pid'])
                    if previous is None:
                        continue
                    try:
                        fallback.append({'pid': row['pid'], 'terminated': windows.terminate_owned(previous)})
                    except Exception as error:
                        fallback.append({'pid': row['pid'], 'terminated': False, 'error': safe(error)})
                if fallback:
                    report['bounded_owned_webview_fallback'] = fallback
                    report['forced_cleanup'] = True
                    deadline = time.monotonic()+5
                    while time.monotonic() < deadline and windows.listeners():
                        time.sleep(.15)
                    remaining = windows.listeners()
            report['debug_port_released'] = not remaining
            report['remaining_debug_listener_count'] = len(remaining)
        else:
            report['debug_port_released'] = not windows.listeners()
        report['clean_exit_verified'] = bool(report.get('supported_page_close_returned') and report.get('client_exit_code') == 0
            and report.get('debug_port_released') and not report['forced_cleanup'])
        report['passed'] = bool(report['native_navigation_verified'] and report['clean_exit_verified'])
        report['finished_at'] = stamp()
        (work/'verification.json').write_text(safe(json.dumps(report, indent=2))+'\n')
        print(json.dumps({'passed': report['passed'], 'groups': len(report['groups']), 'error': report.get('error'),
                          'client_exit_code': report.get('client_exit_code'), 'debug_port_released': report['debug_port_released'],
                          'native_navigation_verified': report['native_navigation_verified'], 'clean_exit_verified': report['clean_exit_verified'],
                          'forced_cleanup': report['forced_cleanup']}), flush=True)
    return 0 if report['passed'] else 1


class GuardTests(unittest.TestCase):
    def test_exact_source_only(self):
        source_guard(SOURCE)
        for value in ('', None, '8b3e7e0e440b9f4d090517237724999bcd824d86f460663e65d940c9c1d20fd5', 'a'*64):
            with self.assertRaises(ConcurrentChange):
                source_guard(value)
    def test_standard_user_only(self):
        integrity_guard('Medium')
        for value in ('High', 'SystemOrHigher', 'Low', 'Unknown'):
            with self.assertRaises(Blocked):
                integrity_guard(value)
    def test_no_mutations_except_local_session(self):
        self.assertTrue(allow_request('GET', ORIGIN+API+'/matches'))
        self.assertTrue(allow_request('POST', ORIGIN+API+'/session'))
        for method, path in (('POST', '/exports'), ('POST', '/connections/openfootball/sync'), ('POST', '/matches/any/local-explanations'), ('PUT', '/local-model/configuration')):
            self.assertFalse(allow_request(method, ORIGIN+API+path))
        self.assertFalse(allow_request('GET', 'https://example.com/'))
        original = {'DEBUG':'pw:protocol','PWDEBUG':'1','debug_file':'untrusted-log','KEEP':'unchanged'}
        filtered = debug_environment(original)
        self.assertEqual(filtered, {'KEEP':'unchanged'})
        self.assertEqual(original['DEBUG'], 'pw:protocol')
        self.assertIn('--remote-debugging-address=127.0.0.1', DEBUG_ARGUMENTS)
    def test_loopback_and_new_child_listener_only(self):
        listener_guard([{'address':'127.0.0.1','port':PORT,'pid':123}], {123})
        for row in ({'address':'0.0.0.0','port':PORT,'pid':123}, {'address':'127.0.0.1','port':PORT,'pid':456}, {'address':'::','port':PORT,'pid':123}):
            with self.assertRaises(Blocked):
                listener_guard([row], {123})
        expected = {'id':'owned-target'}
        close_target_guard({'targetId':'owned-target','type':'page','url':ORIGIN+'/#today'}, expected)
        for candidate in ({'targetId':'other','type':'page','url':ORIGIN}, {'targetId':'owned-target','type':'page','url':'https://example.com'}, {'targetId':'owned-target','type':'browser','url':ORIGIN}):
            with self.assertRaises(Blocked):
                close_target_guard(candidate, expected)
    def test_sensitive_url_parts_not_retained(self):
        value = safe_url(ORIGIN+'/?api_key=secret#token=private')
        self.assertNotIn('secret', value)
        self.assertNotIn('private', value)
        self.assertNotIn('token=', value)
        self.assertEqual(safe_url(ORIGIN+'/#match/'+'a'*64), ORIGIN+'/#match/'+'a'*64)
    def test_no_profile_escape(self):
        self.assertEqual(owned_path(BASE/'run/profile', BASE), (BASE/'run/profile').resolve())
        for value in (BASE, ROOT/'runtime/other-profile', BASE/'../escape'):
            with self.assertRaises(Blocked):
                owned_path(value, BASE)
            with self.assertRaises(Blocked):
                private_target(value)


def self_test():
    directory = BASE/'self-test-r5'
    if directory.exists():
        raise Blocked('PRESERVE_PRIOR_SELF_TEST')
    directory.mkdir(parents=True)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    (directory/'unittest.log').write_text(stream.getvalue())
    doc = {'passed': result.wasSuccessful(), 'unique_cases': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skips': len(result.skipped), 'harness_sha256': digest(__file__), 'client_launched': False, 'network_or_services_modified': False}
    (directory/'verification.json').write_text(json.dumps(doc, indent=2)+'\n')
    print(stream.getvalue())
    print(json.dumps(doc))
    return 0 if result.wasSuccessful() else 1


def acl_probe():
    """Real scoped Windows ACL proof, with a non-secret inheritance marker."""
    directory = BASE/'acl-probe-r2'
    if directory.exists():
        raise Blocked('PRESERVE_PRIOR_NATIVE_ACL_PROBE')
    directory.mkdir(parents=True)
    report = {'schema_version': 1, 'passed': False, 'harness_sha256': digest(__file__),
              'scope': 'New project-owned empty cookie-directory ACLs and non-secret inherited marker; no app, browser, cookie, service or global setting.',
              'client_launched': False, 'sids_or_tokens_recorded': False}
    try:
        windows = Windows()
        integrity_guard(windows.process(os.getpid())['integrity_class'])
        cookie_root = directory/'private-cookie-directory'
        nested = cookie_root/'nested-cookie-directory'
        report['root'] = windows.private_directory(cookie_root)
        report['nested'] = windows.private_directory(nested)
        marker = nested/'nonsecret-inheritance-marker.txt'
        marker.write_text('non-secret ACL inheritance proof\n')
        report['inherited_marker'] = windows.verify_private_acl(marker, directory=False)
        for outside in (BASE, ROOT/'runtime/unrelated-profile', BASE/'../escape'):
            try:
                windows.private_directory(outside)
            except Blocked:
                pass
            else:
                raise AssertionError('A forbidden directory was accepted')
        report['outside_boundary_rejected_without_mutation'] = True
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__+': '+str(error)
    (directory/'verification.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--prepare', action='store_true')
    actions.add_argument('--self-test', action='store_true')
    actions.add_argument('--acl-probe', action='store_true')
    actions.add_argument('--execute-native-journey', action='store_true')
    parser.add_argument('--run-index', type=int, default=1, help='Explicit fresh actual-run suffix; 1 preserves historical run, 2 uses run-r2. Existing evidence is never overwritten.')
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.prepare:
        prepare()
        return 0
    if args.acl_probe:
        return acl_probe()
    return execute(args.run_index)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Blocked as error:
        print(json.dumps({'passed': False, 'blocked': str(error), 'no_workaround_attempted': True}))
        raise SystemExit(2)
