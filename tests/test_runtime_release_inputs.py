"""Regressions for a public dependency lock lost by broad runtime ignores."""
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_release_builder', ROOT / 'scripts/release_wheel.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
runtime_spec = importlib.util.spec_from_file_location('runtime_fresh_acceptance', ROOT / 'scripts/verify_linux_fresh_runtime.py')
runtime = importlib.util.module_from_spec(runtime_spec)
runtime_spec.loader.exec_module(runtime)


class RuntimeReleaseInputsTests(unittest.TestCase):
    def test_windows_owned_child_endpoint_is_accepted_without_relaxing_posix(self):
        self.assertTrue(runtime.owned_endpoint_pid(100, 100, windows=False))
        self.assertTrue(runtime.owned_endpoint_pid(100, 101, windows=True, parents={101: 100}))
        self.assertTrue(runtime.owned_endpoint_pid(100, 102, windows=True, parents={102: 101, 101: 100}))
        self.assertFalse(runtime.owned_endpoint_pid(100, 101, windows=False, parents={101: 100}))
        self.assertFalse(runtime.owned_endpoint_pid(100, 103, windows=True, parents={103: 999}))
        self.assertFalse(runtime.owned_endpoint_pid(100, 103, windows=True, parents={103: 104, 104: 103}))
        self.assertFalse(runtime.owned_endpoint_pid(100, True, windows=True, parents={}))

    def test_real_source_staging_keeps_public_lock_but_excludes_private_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); source = base/'original'; stage = base/'staged'
            files = {'config/runtime/server-python314.lock.txt':'fastapi==0.162.0\n',
                     'config/runtime/private.json':'SYNTHETIC private configuration',
                     'runtime/private.json':'SYNTHETIC runtime state', 'build/output.txt':'SYNTHETIC build',
                     'dist/output.txt':'SYNTHETIC artifact', '.git':'SYNTHETIC worktree binding',
                     'src/dragonhydra/product.py':'# SYNTHETIC source\n'}
            for relative, text in files.items():
                path=source/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
            shutil.copytree(source,stage,ignore=builder.source_ignores(source))
            self.assertEqual((stage/'config/runtime/server-python314.lock.txt').read_text(),files['config/runtime/server-python314.lock.txt'])
            self.assertTrue((stage/'src/dragonhydra/product.py').is_file())
            for relative in ('config/runtime/private.json','runtime','build','dist','.git'):
                self.assertFalse((stage/relative).exists(),relative)

    def test_sdist_verifies_public_lock_and_generated_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dragonhydra-0.4.0a1.tar.gz';lock=b'fastapi==0.162.0\n'
            info={'python_version':'0.4.0a1','source_sha':'a'*40}
            with tarfile.open(path,'w:gz') as archive:
                for name,data in [('config/runtime/server-python314.lock.txt',lock),('src/dragonhydra/build_info.json',json.dumps(info).encode())]:
                    member=tarfile.TarInfo('dragonhydra-0.4.0a1/'+name);member.size=len(data);archive.addfile(member,io.BytesIO(data))
            self.assertEqual(builder.inspect_sdist(path,info,lock)['members'],2)
            with self.assertRaises(RuntimeError):
                builder.inspect_sdist(path,info,b'fastapi==0.0.0\n')

    def test_source_archive_rejects_private_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'dragonhydra-0.4.0a1.tar.gz'
            with tarfile.open(path,'w:gz') as archive:
                data=b'SYNTHETIC private state';member=tarfile.TarInfo('dragonhydra-0.4.0a1/runtime/local-session.json');member.size=len(data);archive.addfile(member,io.BytesIO(data))
            with self.assertRaises(RuntimeError):
                builder.inspect_sdist(path,{'python_version':'0.4.0a1','source_sha':'a'*40},b'')


if __name__ == '__main__':
    unittest.main()
