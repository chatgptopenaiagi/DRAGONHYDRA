"""Optional AI ownership, secret handling and rollback at an isolated OS boundary.

Fake service operations cannot reach PID1. Files are temporary project-owned
fixtures; modes/UIDs are explicitly simulated for deterministic DrvFS checks.
"""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('dragonhydra_optional_ai_control', ROOT/'packaging/linux-native/configure_local_ai.py')
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class FakeFiles(module.FileStore):
    def __init__(self, root):
        self.root = root
        self.attributes = {}
        self.attributes[Path('/')] = {'kind': 'dir', 'mode': 0o755, 'uid': 0, 'gid': 0}
        self.links = set()
        self.targets = {}
        self.hash_calls = []
        self.fail_write = None
        self.on_lock = None

    def path(self, path):
        return self.root/Path(path).relative_to('/')

    def info(self, path):
        path = Path(path)
        if path in self.links:
            return {'kind': 'link', 'mode': 0o777, 'uid': 0, 'gid': 0}
        return dict(self.attributes[path]) if path in self.attributes else None

    def seed(self, path, body=b'', mode=0o644):
        path = Path(path)
        self.path(path).parent.mkdir(parents=True, exist_ok=True)
        for parent in path.parents:
            self.attributes.setdefault(parent, {'kind': 'dir', 'mode': 0o755, 'uid': 0, 'gid': 0})
        self.path(path).write_bytes(body)
        self.attributes[path] = {'kind': 'file', 'mode': mode, 'uid': 0, 'gid': 0}

    def mkdir(self, path, mode):
        self.safe(path, managed=True)
        self.path(path).mkdir()
        self.attributes[Path(path)] = {'kind': 'dir', 'mode': mode, 'uid': 0, 'gid': 0}

    def atomic(self, path, body, mode):
        self.safe(path, managed=True)
        if self.fail_write == path:
            self.fail_write = None
            raise OSError('Injected isolated write failure')
        self.seed(path, body, mode)

    def remove(self, path):
        self.safe(path, managed=True)
        self.path(path).unlink(missing_ok=True)
        self.attributes.pop(Path(path), None)

    def rmdir(self, path):
        self.path(path).rmdir()
        self.attributes.pop(Path(path), None)

    def sha(self, path):
        self.hash_calls.append(Path(path))
        return super().sha(path)

    def readlink(self, path):
        return self.targets[Path(path)]

    def resolve(self, path):
        path = Path(path)
        for _ in range(16):
            if path not in self.links: return path
            path = path.parent/self.targets[path]
        raise AssertionError('Fake link loop')

    @contextmanager
    def lock(self):
        if not self.info(module.LOCK):
            self.seed(module.LOCK, b'', 0o600)
        if self.on_lock:
            callback, self.on_lock = self.on_lock, None
            callback()
        yield

    def all_bytes(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}


class FakeHost:
    def __init__(self, files):
        self.files = files
        self.commands = []
        self.available_calls = []
        self.busy = False
        self.root = True
        self.memory = 8*1024**3
        self.fail_command = None
        self.fail_ready = False
        self.api = {'ActiveState': 'active', 'UnitFileState': 'enabled', 'FragmentPath': '/usr/lib/systemd/system/'+module.API,
                    'DynamicUser': 'yes', 'ExecStart': '/opt/dragonhydra/api/bin/dragonhydra-server --state /var/lib/dragonhydra-api --port 0'}
        self.model = {'ActiveState': 'inactive', 'UnitFileState': 'not-found', 'FragmentPath': ''}
        self.current = {'endpoint': '', 'configured': False, 'endpoint_source': 'none', 'credential_source': 'none'}

    def require_root(self):
        if not self.root:
            module.fail('ROOT_REQUIRED', 'Fake root precondition')

    def environment(self):
        return self.memory

    def state(self, unit):
        return dict(self.api if unit == module.API else self.model)

    def command(self, action, unit=None):
        self.commands.append((action, unit))
        if self.fail_command == (action, unit):
            self.fail_command = None
            if unit == module.API and action == 'restart':
                self.api['ActiveState'] = 'inactive'
            module.fail('SERVICE_COMMAND_FAILED', 'Injected isolated service failure')
        if action == 'daemon-reload':
            if self.files.info(module.UNIT):
                self.model['FragmentPath'] = str(module.UNIT)
                self.model['ExecStart'] = str(module.SERVER)
                self.model['DynamicUser'] = 'yes'
            else:
                self.model = {'ActiveState': 'inactive', 'UnitFileState': 'not-found', 'FragmentPath': ''}
        elif unit == module.MODEL:
            if action == 'enable': self.model['UnitFileState'] = 'enabled'
            if action == 'disable': self.model['UnitFileState'] = 'disabled'
            if action in ('start', 'restart'): self.model['ActiveState'] = 'active'
            if action == 'stop': self.model['ActiveState'] = 'inactive'
        elif unit == module.API and action == 'restart':
            self.api['ActiveState'] = 'active'
            self.current = {'endpoint': '', 'configured': False, 'endpoint_source': 'none', 'credential_source': 'none'}
            if self.files.info(module.DROPIN) and self.files.info(module.ENV):
                endpoint = self.files.read(module.ENV).decode().splitlines()[0].split('=', 1)[1]
                self.current = {'endpoint': endpoint, 'configured': True, 'endpoint_source': 'environment', 'credential_source': 'environment'}

    def available(self, port):
        self.available_calls.append(port)
        if self.busy:
            module.fail('PORT_BUSY', 'Injected existing listener; no process stopped')

    def model_ready(self, port, key):
        if self.fail_ready:
            self.fail_ready = False
            module.fail('MODEL_NOT_READY', 'Injected bounded model load failure')
        if self.files.read(module.KEY).decode().rstrip('\n') != key:
            raise AssertionError('Model service must receive exactly the stored key')

    def api_configuration(self, wait=False):
        if self.api['ActiveState'] != 'active':
            module.fail('API_NOT_READY', 'Fake API is inactive')
        return dict(self.current)


class OptionalAIConfiguration(unittest.TestCase):
    def setUp(self):
        scratch = ROOT/'build/linux/local-ai-20261031/configuration-r2/scratch'
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch, prefix='os-fake-')
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(self.root.is_relative_to(scratch.resolve()) and self.root != scratch.resolve())
        self.addCleanup(self.temporary.cleanup)
        self.files = FakeFiles(self.root)
        self.host = FakeHost(self.files)
        self.model = Path('/models/compact model.gguf')
        body = b'GGUF labelled isolated test fixture'
        self.files.seed(self.model, body)
        self.files.seed(module.SERVER, b'isolated fake executable', 0o755)
        self.library = module.RUNTIME/'bin/libggml-real.so'
        self.files.seed(self.library, b'isolated fake private library')
        alias = module.RUNTIME/'bin/libggml.so'
        self.files.links.add(alias)
        self.files.targets[alias] = 'libggml-real.so'
        runtime_identity = {'component': 'dragonhydra-local-ai-runtime', 'upstream_commit': '2280f0fd163b03d4331d49e08460f66502e35854',
            'runtime_files': [{'path': p.relative_to(module.RUNTIME).as_posix(), 'bytes': self.files.path(p).stat().st_size, 'sha256': self.files.sha(p)} for p in (module.SERVER, self.library)],
            'relative_soname_links': [{'path': alias.relative_to(module.RUNTIME).as_posix(), 'target': 'libggml-real.so',
                'resolved_path': self.library.relative_to(module.RUNTIME).as_posix(), 'resolved_sha256': self.files.sha(self.library), 'safe_contained_resolution': True}]}
        self.files.seed(module.RUNTIME_IDENTITY, module.canonical(runtime_identity))
        profile = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(), 'verified_context_tokens': 2048,
                   'verified_compute_threads': 4, 'verified_parallel_slots': 1, 'verified_gpu_layers': 0}
        self.files.seed(module.PROFILE, module.canonical(profile))
        contract = replace(module.Contract(), profile_sha256=self.files.sha(module.PROFILE), server_sha256=self.files.sha(module.SERVER),
                           runtime_identity_sha256=self.files.sha(module.RUNTIME_IDENTITY), runtime_files=2, runtime_links=1)
        self.files.seed('/opt/dragonhydra/api/BUILD-IDENTITY.json', module.canonical({'debian_version': contract.api_version, 'source_content_sha256': contract.api_effective}))
        self.files.seed('/etc/dragonhydra/api.env', b'# Existing sports provider configuration is unrelated.\n', 0o600)
        self.files.path('/etc/systemd/system').mkdir(parents=True)
        for parent in (Path('/etc/systemd/system'), Path('/etc/systemd')):
            self.files.attributes[parent] = {'kind': 'dir', 'mode': 0o755, 'uid': 0, 'gid': 0}
        self.controller = module.Controller(self.files, self.host, contract)
        self.before = self.files.all_bytes()

    def assert_original_files_with_stable_lock(self):
        expected = {**self.before, module.LOCK.relative_to('/').as_posix(): b''}
        self.assertEqual(self.files.all_bytes(), expected)
        self.assertEqual(self.files.info(module.LOCK)['mode'], 0o600)
        self.assertEqual(self.files.info(module.DIRECTORY)['mode'], 0o700)

    def enable(self):
        return self.controller.enable(self.model, 18765)

    def assert_error(self, code, call):
        with self.assertRaises(module.ConfigurationError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_read_only_preflight_does_not_create_private_files_or_control_units(self):
        result = self.controller.enable(self.model, 18765, preflight_only=True)
        self.assertFalse(result['changed'])
        self.assertEqual(self.files.all_bytes(), self.before)
        self.assertEqual(self.host.commands, [])
        self.assertIsNone(self.files.info(module.DIRECTORY))

    def test_enable_uses_same_generated_root600_key_without_secret_output_or_api_dependency(self):
        result = self.enable()
        raw = self.files.read(module.KEY)
        self.assertRegex(raw, rb'^[a-f0-9]{64}\n$')
        key = raw.decode().rstrip('\n')
        self.assertEqual(self.files.read(module.ENV), self.controller.environment(18765, key))
        for path in (module.KEY, module.ENV, module.MARKER, module.LOCK):
            self.assertEqual(self.files.info(path)['mode'], 0o600)
        self.assertEqual(self.files.info(module.DIRECTORY)['mode'], 0o700)
        self.assertNotIn(key, json.dumps(result)+json.dumps(self.host.commands)+self.files.read(module.UNIT).decode())
        dropin = self.files.read(module.DROPIN).decode()
        self.assertIn('EnvironmentFile=-/etc/dragonhydra/local-ai/api.env', dropin)
        for forbidden in ('ExecStart', 'Requires', 'Wants', 'After='):
            self.assertNotIn(forbidden, dropin)
        self.assertIn('LoadCredential=local-ai-key:/etc/dragonhydra/local-ai/key', self.files.read(module.UNIT).decode())
        self.assertIn('--api-key-file %d/local-ai-key', self.files.read(module.UNIT).decode())

    def test_spaces_and_systemd_expansion_characters_in_model_path_are_escaped(self):
        selected = Path('/models/with space "$100%.gguf')
        self.files.seed(selected, self.files.read(self.model))
        self.controller.enable(selected, 18765)
        unit = self.files.read(module.UNIT).decode()
        self.assertIn('--model "/models/with space \\"$$100%%.gguf"', unit)

    def test_second_enable_reuses_key_and_does_not_restart_or_probe_its_own_busy_port(self):
        self.enable()
        key, commands, available = self.files.read(module.KEY), list(self.host.commands), list(self.host.available_calls)
        self.host.busy = True
        result = self.enable()
        self.assertFalse(result['changed'])
        self.assertEqual(key, self.files.read(module.KEY))
        self.assertEqual(commands, self.host.commands)
        self.assertEqual(available, self.host.available_calls)

    def test_enabled_but_unhealthy_model_is_not_reported_as_success_without_mutation(self):
        self.enable()
        before, commands = self.files.all_bytes(), list(self.host.commands)
        self.host.fail_ready = True
        self.assert_error('MODEL_NOT_READY', self.enable)
        self.assertEqual(self.files.all_bytes(), before)
        self.assertEqual(self.host.commands, commands)

    def test_disable_preserves_key_environment_model_profile_and_existing_api_env(self):
        self.enable()
        retained = {p: self.files.read(p) for p in (module.KEY, module.ENV, module.PROFILE, self.model, Path('/etc/dragonhydra/api.env'))}
        self.controller.disable()
        for p, body in retained.items(): self.assertEqual(self.files.read(p), body)
        self.assertIsNone(self.files.info(module.DROPIN))
        self.assertFalse(self.files.json(module.MARKER)['enabled'])
        self.assertFalse(self.host.api_configuration()['configured'])
        self.assertEqual(self.host.model['ActiveState'], 'inactive')
        self.assertEqual(self.host.model['UnitFileState'], 'disabled')

    def test_disable_never_starts_a_previously_inactive_api(self):
        self.enable()
        self.host.api['ActiveState'] = 'inactive'
        self.host.commands.clear()
        self.controller.disable()
        self.assertNotIn(('restart', module.API), self.host.commands)
        self.assertEqual(self.host.api['ActiveState'], 'inactive')

    def test_missing_api_env_is_optional_and_disable_still_succeeds(self):
        self.enable()
        self.files.remove(module.ENV)
        self.host.command('restart', module.API)
        self.assertFalse(self.host.api_configuration()['configured'])
        self.controller.disable()
        self.assertEqual(self.host.api['ActiveState'], 'active')

    def test_missing_owned_model_key_does_not_trigger_implicit_rotation_or_block_disable(self):
        self.enable()
        self.files.remove(module.KEY)
        self.assert_error('OWNED_KEY_MISSING', self.enable)
        self.controller.disable()
        self.assertEqual(self.host.api['ActiveState'], 'active')

    def test_busy_port_cannot_write_configuration_or_stop_an_existing_process(self):
        self.host.busy = True
        self.assert_error('PORT_BUSY', self.enable)
        self.assertEqual(self.files.all_bytes(), self.before)
        self.assertEqual(self.host.commands, [])

    def test_invalid_model_hash_is_rejected_before_any_apply(self):
        self.files.seed(self.model, b'wrong bytes with other length')
        self.assert_error('MODEL_HASH_MISMATCH', self.enable)
        self.assertEqual(self.host.commands, [])

    def test_profile_or_runtime_hash_drift_is_rejected(self):
        self.files.seed(module.SERVER, b'changed executable', 0o755)
        self.assert_error('INSTALLED_PROFILE_MISMATCH', self.enable)
        self.assertEqual(self.host.commands, [])

    def test_low_available_memory_is_a_preflight_failure(self):
        self.host.memory = 2*1024**3
        self.assert_error('INSUFFICIENT_MEMORY', self.enable)
        self.assertEqual(self.files.all_bytes(), self.before)

    def test_foreign_api_configuration_is_preserved(self):
        self.host.current = {'endpoint': '', 'configured': False, 'endpoint_source': 'none', 'credential_source': 'environment'}
        self.assert_error('FOREIGN_API_CONFIGURATION', self.enable)
        self.assertEqual(self.files.all_bytes(), self.before)

    def test_explicit_known_r7_and_r8_version_source_pairs_are_accepted(self):
        for version, effective in module.Contract().known_api_pairs:
            self.files.seed('/opt/dragonhydra/api/BUILD-IDENTITY.json', module.canonical({'debian_version': version, 'source_content_sha256': effective}))
            guarded = self.controller.api_guard()
            self.assertEqual((guarded['api_version'], guarded['api_effective_sha256']), (version, effective))
        self.assertEqual(self.host.commands, [])

    def test_unknown_or_mismatched_api_version_source_pairs_are_rejected(self):
        old, new = module.Contract().known_api_pairs
        for version, effective in ((new[0], old[1]), (old[0], new[1]), ('unknown-version', new[1]), (new[0], '0'*64)):
            self.files.seed('/opt/dragonhydra/api/BUILD-IDENTITY.json', module.canonical({'debian_version': version, 'source_content_sha256': effective}))
            self.assert_error('FOREIGN_API_UNIT', self.controller.api_guard)
        self.assertEqual(self.host.commands, [])

    def test_unmarked_existing_key_or_foreign_marker_is_never_overwritten(self):
        self.files.path(module.DIRECTORY).mkdir()
        self.files.attributes[module.DIRECTORY] = {'kind': 'dir', 'mode': 0o700, 'uid': 0, 'gid': 0}
        self.files.seed(module.KEY, b'foreign file\n', 0o600)
        self.assert_error('FOREIGN_CONFIGURATION', self.enable)
        self.assertEqual(self.files.read(module.KEY), b'foreign file\n')
        self.files.remove(module.KEY)
        self.files.seed(module.MARKER, module.canonical({'owner': 'other-product'}), 0o600)
        self.assert_error('FOREIGN_MARKER', self.enable)

    def test_wrong_private_permissions_and_symbolic_link_are_rejected(self):
        self.enable()
        self.files.attributes[module.KEY]['mode'] = 0o644
        self.assert_error('UNSAFE_PERMISSIONS', self.enable)
        self.files.attributes[module.KEY]['mode'] = 0o600
        self.files.links.add(module.KEY)
        self.assert_error('SYMLINK_REJECTED', self.enable)

    def test_foreign_unit_override_prevents_disable_of_that_service(self):
        self.enable()
        self.host.model['FragmentPath'] = '/usr/lib/systemd/system/another.service'
        self.host.commands.clear()
        self.assert_error('FOREIGN_MODEL_UNIT', self.controller.disable)
        self.assertEqual(self.host.commands, [])

    def test_invalid_port_control_characters_and_model_symlink_are_rejected(self):
        self.assert_error('INVALID_PORT', lambda: self.controller.enable(self.model, 0))
        self.assert_error('UNSAFE_MODEL_PATH', lambda: self.controller.enable('/models/bad\npath.gguf', 18765))
        self.files.links.add(self.model)
        self.assert_error('SYMLINK_REJECTED', self.enable)

    def test_key_changes_require_explicit_future_rotation_not_silent_replacement(self):
        self.enable()
        self.files.seed(module.KEY, b'0'*64+b'\n', 0o600)
        self.assert_error('OWNED_KEY_CHANGED', self.enable)

    def test_model_start_failure_restores_original_files_and_api_state(self):
        self.host.fail_ready = True
        self.assert_error('MODEL_NOT_READY', self.enable)
        self.assert_original_files_with_stable_lock()
        self.assertEqual(self.host.api['ActiveState'], 'active')
        self.assertFalse(self.host.current['configured'])

    def test_write_failure_before_model_unit_publication_rolls_back_without_foreign_stop(self):
        self.files.fail_write = module.UNIT
        with self.assertRaises(OSError): self.enable()
        self.assert_original_files_with_stable_lock()
        self.assertNotIn(('stop', module.MODEL), self.host.commands)

    def test_api_restart_failure_restores_initial_bytes_and_ready_api(self):
        self.host.fail_command = ('restart', module.API)
        self.assert_error('SERVICE_COMMAND_FAILED', self.enable)
        self.assert_original_files_with_stable_lock()
        self.assertEqual(self.host.api['ActiveState'], 'active')
        self.assertFalse(self.host.api_configuration()['configured'])

    def test_disable_failure_restores_exact_enabled_configuration(self):
        self.enable()
        before = self.files.all_bytes()
        self.host.fail_command = ('restart', module.API)
        self.assert_error('SERVICE_COMMAND_FAILED', self.controller.disable)
        self.assertEqual(self.files.all_bytes(), before)
        self.assertEqual(self.host.model['ActiveState'], 'active')
        self.assertEqual(self.host.model['UnitFileState'], 'enabled')
        self.assertTrue(self.host.api_configuration()['configured'])

    def test_status_performs_no_model_hash_or_service_mutation(self):
        self.enable()
        self.files.hash_calls.clear()
        self.host.commands.clear()
        result = self.controller.status()
        self.assertTrue(result['key_present'])
        self.assertNotIn(self.model, self.files.hash_calls)
        self.assertEqual(self.host.commands, [])

    def test_full_private_runtime_library_and_soname_alias_are_verified(self):
        self.files.seed(self.library, b'modified private companion')
        self.assert_error('INSTALLED_RUNTIME_MISMATCH', self.enable)
        self.assertEqual(self.host.commands, [])

    def test_private_runtime_alias_cannot_be_redirected(self):
        self.files.targets[module.RUNTIME/'bin/libggml.so'] = '../../foreign.so'
        self.assert_error('INSTALLED_RUNTIME_MISMATCH', self.enable)
        self.assertEqual(self.host.commands, [])

    def test_foreign_model_dropin_is_not_controlled(self):
        self.enable()
        self.host.model['DropInPaths'] = '/etc/systemd/system/dragonhydra-local-ai.service.d/foreign.conf'
        self.host.commands.clear()
        self.assert_error('FOREIGN_MODEL_DROPIN', self.controller.disable)
        self.assertEqual(self.host.commands, [])

    def test_protect_home_hidden_model_locations_are_rejected_before_hashing(self):
        for path in ('/home/operator/model.gguf', '/root/model.gguf', '/run/user/1000/model.gguf'):
            self.assert_error('MODEL_HIDDEN_BY_PROTECT_HOME', lambda: self.controller.enable(path, 18765))
        self.assertEqual(self.host.commands, [])

    def test_concurrent_completed_enable_is_revalidated_under_lock_not_overwritten(self):
        saved = {}
        def completed_other_action():
            self.controller.enable(self.model, 18766)
            saved['files'] = self.files.all_bytes()
            saved['commands'] = list(self.host.commands)
        self.files.on_lock = completed_other_action
        self.assert_error('DISABLE_BEFORE_CHANGE', self.enable)
        self.assertEqual(self.files.all_bytes(), saved['files'])
        self.assertEqual(self.host.commands, saved['commands'])
        self.assertEqual(self.files.json(module.MARKER)['port'], 18766)

    def test_concurrent_completed_disable_is_not_rolled_back_to_stale_enabled_snapshot(self):
        self.enable()
        saved = {}
        def completed_other_disable():
            self.controller.disable()
            saved['files'] = self.files.all_bytes()
            saved['commands'] = list(self.host.commands)
        self.files.on_lock = completed_other_disable
        result = self.controller.disable()
        self.assertFalse(result['changed'])
        self.assertEqual(self.files.all_bytes(), saved['files'])
        self.assertEqual(self.host.commands, saved['commands'])
        self.assertFalse(self.files.json(module.MARKER)['enabled'])

    def test_rollback_failure_preserves_both_primary_and_restoration_codes(self):
        self.host.fail_ready = True
        self.host.fail_command = ('stop', module.MODEL)
        with self.assertRaises(module.ConfigurationError) as caught:
            self.enable()
        self.assertEqual(caught.exception.code, 'ROLLBACK_FAILED')
        self.assertEqual(caught.exception.details, {'primary_error': 'MODEL_NOT_READY', 'rollback_error': 'SERVICE_COMMAND_FAILED', 'restore_gap': True})

    def native_health_host(self, body=b'{"status":"ok"}', listener=True, auth_error=False):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, size): return body
        class Opener:
            def __init__(self): self.calls = []
            def open(self, request, timeout):
                self.calls.append(request.full_url)
                if auth_error:
                    raise HTTPError('http://127.0.0.1:18765/health', 401, 'Unauthorized', {}, io.BytesIO(b'{}'))
                return Response()
        host = module.NativeHost(self.files)
        host.opener = Opener()
        sequence = iter((True, False)) if listener is False else None
        host.owns_model_listener = lambda port: next(sequence) if sequence else True
        return host

    def test_unrelated_http200_is_not_model_readiness(self):
        self.assert_error('MODEL_LISTENER_MISMATCH', lambda: self.native_health_host(listener=False).model_ready(18765, 'fake-only'))

    def test_invalid_health_json_or_status_is_rejected(self):
        for body in (b'not JSON', b'{"status":"loading"}'):
            self.assert_error('MODEL_HEALTH_INVALID', lambda: self.native_health_host(body=body).model_ready(18765, 'fake-only'))

    def test_healthy_owned_model_and_authentication_failure_paths(self):
        self.native_health_host().model_ready(18765, 'fake-only')
        self.assert_error('MODEL_AUTH_FAILED', lambda: self.native_health_host(auth_error=True).model_ready(18765, 'fake-only'))

    def test_no_key_is_sent_to_an_unowned_listener(self):
        host = self.native_health_host()
        host.owns_model_listener = lambda port: False
        host.state = lambda unit: {'ActiveState': 'failed'}
        self.assert_error('MODEL_NOT_READY', lambda: host.model_ready(18765, 'fake-only'))
        self.assertEqual(host.opener.calls, [])


if __name__ == '__main__':
    unittest.main()
