"""Headless acceptance of the real Debian bytes on the named Linux target.

The Debian archive is inspected and extracted into a fresh project-owned root.
No package manager installation, system account, systemd activation or host
configuration mutation is performed. The extracted private libraries must work
without checkout imports or globally installed FastAPI libraries.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import sqlite3
import subprocess
import sys
import tarfile
import time
import traceback
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
API = '/dragon/api/v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_file(path):
    return json.loads(Path(path).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--public-provider', choices=['football-data-couk'], default=None)
    args = parser.parse_args()
    artifact, work = args.artifact.resolve(), args.work.resolve()
    boundary = ROOT/'build/linux/native-kernel-20261031'
    if platform.system() != 'Linux' or not work.is_relative_to(boundary) or work == boundary or work.exists():
        raise SystemExit('Use a fresh owned acceptance directory beneath build/linux/native-kernel-20261031 on Linux')
    if not artifact.is_relative_to(ROOT/'dist/linux/native-kernel-20261031'):
        raise SystemExit('Use the explicit owned native artifact directory')
    work.mkdir(parents=True)
    report = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'scope': 'Debian-format inspection, isolated extraction and actual headless server launch on WSL Ubuntu26.04.1; no system installation/activation or desktop claim',
              'environment': {'platform': platform.platform(), 'python': platform.python_version(), 'architecture': platform.machine(), 'uid': os.getuid()},
              'artifact': {'filename': artifact.name, 'bytes': artifact.stat().st_size, 'sha256': digest(artifact)},
              'checks': [], 'commands': [], 'system_install_tested': False, 'systemd_activation_tested': False,
              'desktop_tested': False, 'host_services_changed': False, 'network_acquisition': False}
    secret = None
    process = None
    records = []

    def run(name, command, *, env=None):
        started = time.monotonic()
        result = subprocess.run(list(map(str, command)), cwd=work, env=env, capture_output=True, text=True, timeout=90)
        (work/(name+'.stdout.log')).write_text(result.stdout)
        (work/(name+'.stderr.log')).write_text(result.stderr)
        report['commands'].append({'name': name, 'argv': list(map(str, command)), 'exit_code': result.returncode,
                                   'seconds': round(time.monotonic()-started, 3)})
        if result.returncode:
            raise RuntimeError(name+' failed: '+result.stderr[-1500:])
        return result.stdout

    def check(name, **details):
        report['checks'].append({'name': name, 'passed': True, **details})
        print(json.dumps({'passed': name, **details}), flush=True)

    opener = build_opener(ProxyHandler({}))
    base = ''

    def request(path, method='GET', payload=None, *, authenticate=True, expect=200):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {'Content-Type': 'application/json'}
        if authenticate:
            headers['Authorization'] = 'Bearer '+secret
        req = Request(base+API+path, data=data, headers=headers, method=method)
        try:
            response = opener.open(req, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read(4*1024*1024)
            if response.status != expect:
                raise RuntimeError(f'{method} {path}: expected HTTP{expect}, actualHTTP{response.status}: '+raw.decode(errors='replace')[:300])
            return json.loads(raw) if response.headers.get_content_type() == 'application/json' else raw

    def job(path, payload):
        queued = request(path, 'POST', payload, expect=202)
        deadline = time.monotonic()+90
        while time.monotonic()<deadline:
            result = request('/jobs/'+queued['id'])
            if result['status'] == 'succeeded':
                return result['result']
            if result['status'] in ('failed', 'cancelled', 'interrupted'):
                raise RuntimeError('Worker job did not succeed: '+json.dumps(result.get('error')))
            time.sleep(.2)
        raise RuntimeError('Worker job deadline exceeded')

    state = work/'state'
    state.mkdir()
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': str(work/'home'), 'TMPDIR': str(work/'scratch')}
    Path(env['HOME']).mkdir()
    Path(env['TMPDIR']).mkdir()

    def start(phase):
        nonlocal process, base, secret
        endpoint = state/'endpoint.json'
        endpoint.unlink(missing_ok=True)
        out = (work/(phase+'.stdout.log')).open('wb')
        err = (work/(phase+'.stderr.log')).open('wb')
        process = subprocess.Popen([str(launcher), '--state', str(state), '--port', '0'], cwd=work, env=env,
                                   stdout=out, stderr=err, start_new_session=True)
        out.close()
        err.close()
        deadline = time.monotonic()+60
        while time.monotonic()<deadline:
            if process.poll() is not None:
                raise RuntimeError('Extracted server exited before readiness: '+str(process.returncode))
            if endpoint.exists() and (state/'local-session.json').exists():
                doc = json_file(endpoint)
                if doc.get('pid') == process.pid:
                    base = doc['url']
                    secret = json_file(state/'local-session.json')['token']
                    try:
                        ready = request('/health/ready')
                        if ready['status']=='ready':
                            records.append({'phase': phase, 'pid': process.pid, 'url': base})
                            return ready
                    except (URLError, OSError, ValueError):
                        pass
            time.sleep(.1)
        raise RuntimeError('Extracted server readiness deadline exceeded')

    def stop():
        if process and process.poll() is None:
            request('/system/shutdown', 'POST', {})
            code = process.wait(timeout=20)
            if code != 0:
                raise RuntimeError('Owned server shutdown failed: '+str(code))
            records[-1]['exit_code'] = code

    def snapshot():
        page = request('/matches?limit=1')
        with sqlite3.connect(state/'core.sqlite3') as db:
            tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'public_%'")]
            counts = {name: db.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in tables}
        return {'count': page['total'], 'match_id': page['items'][0]['id'], 'version': page['items'][0]['version'],
                'pairing_sha256': hashlib.sha256(secret.encode()).hexdigest(), 'public_sql_counts': counts}

    try:
        os_release = Path('/etc/os-release').read_text()
        report['environment']['os_release'] = os_release
        assert 'VERSION_ID="26.04"' in os_release and sys.version_info[:2] == (3, 14)
        info = run('dpkg-info', ['dpkg-deb', '--info', artifact])
        contents = run('dpkg-contents', ['dpkg-deb', '--contents', artifact])
        assert 'Package: dragonhydra-api' in info and 'Architecture: amd64' in info
        raw_tar = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(artifact)])
        with tarfile.open(fileobj=io.BytesIO(raw_tar), mode='r:') as archive:
            for item in archive:
                name = PurePosixPath(item.name)
                assert not name.is_absolute() and '..' not in name.parts
                assert item.uid==item.gid==0 and not item.issym() and not item.islnk()
                assert item.mode in (0o600, 0o644, 0o755)
        check('Native dpkg reader accepts Debian package and explicit root-owned safe archive modes')
        extracted = work/'extracted'
        run('dpkg-extract', ['dpkg-deb', '--extract', artifact, extracted])
        prefix = extracted/'opt/dragonhydra/api'
        launcher = prefix/'bin/dragonhydra-server'
        identity = json_file(prefix/'BUILD-IDENTITY.json')
        report['source_content_sha256'] = identity['source_content_sha256']
        report['dependencies'] = identity['dependencies']
        probe = '''import sys,json,importlib.metadata as m;from pathlib import Path
site=Path(sys.argv[1]).resolve();sys.path.insert(0,str(site))
import dragonhydra,fastapi,uvicorn,openpyxl,tzdata,pydantic_core
mods=[dragonhydra,fastapi,uvicorn,openpyxl,tzdata,pydantic_core]
assert all(Path(mod.__file__).resolve().is_relative_to(site) for mod in mods)
print(json.dumps({mod.__name__:mod.__file__ for mod in mods},indent=2))'''
        paths = json.loads(run('installed-imports', ['/usr/bin/python3', '-I', '-S', '-B', '-c', probe, prefix/'site-packages'], env=env))
        check('All application and server imports resolve inside extracted prefix with source and global packages disabled', imported_modules=list(paths))
        runtime = json.loads(run('native-runtime-info', [launcher, '--native-runtime-info'], env=env))
        assert runtime['timezone_path']==[] and runtime['tzdata_version']=='2026.2'
        assert runtime['timezone_probe']=='America/New_York'
        assert all(Path(path).resolve().is_relative_to(prefix/'site-packages') for path in runtime['modules'].values())
        report['native_runtime'] = runtime
        check('Actual native launcher pins timezone resolution to vendored2026.2 without changing the host timezone')
        run('build-info', [launcher, '--build-info'], env=env)
        assert json_file(work/'build-info.stdout.log')['source_content_sha256'] == identity['source_content_sha256']
        so = next((prefix/'site-packages/pydantic_core').glob('*.so'))
        abi = run('native-elf', ['readelf', '-h', so])
        assert 'Advanced Micro Devices X86-64' in abi and 'cpython-314' in so.name
        run('native-libraries', ['ldd', so])
        check('Native CPython314 AMD64 extension loads and linked OS libraries resolve')
        start('first')
        request('/matches', authenticate=False, expect=401)
        imported = job('/connections/openfootball/sync', {'mode': 'retained'})
        assert imported['record_count']==760 and imported['inserted']==760
        check('Extracted server starts with private libraries, rejects anonymous browsing and imports760 bundled real source records', records=760)
        match = request('/matches?status=finished&limit=1')['items'][0]
        assert request('/matches/'+match['id'])['id']==match['id']
        assert request('/teams/'+match['home']['id'])['name']==match['home']['name']
        standings = request('/competitions/'+match['competition_id']+'/standings')
        assert len(standings['items'])==20 and standings['official'] is False
        assert request('/matches/'+match['id']+'/predictions')['available'] is False
        explanation = job('/matches/'+match['id']+'/explanations', {})
        assert explanation['kind']=='deterministic' and explanation['evidence'][0]['id']==match['evidence_id']
        evidence = request('/evidence/'+match['evidence_id'])
        raw_source = state/'raw'/(evidence['source_hash']+'.json')
        assert digest(raw_source)==evidence['source_hash']
        check('Same retained match opens related team,20-team reconstructed standings and deterministic cited evidence', match_id=match['id'], source_id=match['source_id'])
        exported = job('/exports', {'match_id': match['id'], 'format': 'xlsx'})
        workbook = opener.open(Request(base+exported['download_url'], headers={'Authorization': 'Bearer '+secret}), timeout=30).read()
        (work/'football-match.xlsx').write_bytes(workbook)
        with ZipFile(io.BytesIO(workbook)) as archive:
            assert '[Content_Types].xml' in archive.namelist() and b'Metadata' in archive.read('xl/workbook.xml')
            assert match['id'].encode() in archive.read('xl/worksheets/sheet1.xml')
        check('Actual Excel workbook downloads for the selected canonical match', bytes=len(workbook), sha256=hashlib.sha256(workbook).hexdigest())
        before = snapshot()
        stop()
        start('restart')
        after = snapshot()
        assert before==after and before['count']==760
        duplicate = job('/connections/openfootball/sync', {'mode': 'retained'})
        assert duplicate['inserted']==0 and duplicate['record_count']==760
        with sqlite3.connect(state/'core.sqlite3') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        report['persistence'] = {'before': before, 'after': after, 'duplicate_inserted': 0}
        check('Restart retains760 records, SQL evidence counts, canonical identities and pairing; duplicate import inserts0')
        stop()
        if args.public_provider:
            state = work/'public-state'
            state.mkdir()
            report['public_probe'] = {'provider': args.public_provider, 'requested': True, 'passed': False,
                                      'scope': 'One bounded HTTPS provider sync in separate fresh state; no TLS bypass'}
            start('public-provider')
            try:
                result = job('/connections/'+args.public_provider+'/sync', {})
                rows = request('/matches?provider='+args.public_provider+'&limit=1')
                assert result['record_count']==380 and result['normalized_rows']==380 and result['quarantined']==0
                assert rows['total']==380
                proof = request('/connections')['items']
                provider = next(c for c in proof if c['id']==args.public_provider)
                assert provider['status']=='working'
                acquisition = result['acquisitions'][0]
                assert digest(state/'raw/connectors'/(acquisition['sha256']+'.payload'))==acquisition['sha256']
                report['public_probe'].update(passed=True, records=380, acquisitions=result['acquisitions'],
                                              diagnostic_status=provider['status'], tls_verification='default OS trust verification')
                check('Linux extracted runtime retrieves380 real public CSV matches over verified HTTPS and retains exact provenance', provider=args.public_provider, records=380)
            except Exception as error:
                report['public_probe']['error'] = type(error).__name__+': '+str(error)
                print('PUBLIC_PROBE_FAILED: '+str(error), flush=True)
            finally:
                stop()
        check('All owned server processes exit0 without activating or stopping any system service', processes=records)
        report['passed'] = True
    except Exception as exc:
        report['error'] = type(exc).__name__+': '+str(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            report['forced_cleanup'] = True
        report['processes'] = records
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['unique_check_groups'] = len(report['checks'])
        serialized = json.dumps(report, indent=2)
        if secret:
            serialized = serialized.replace(secret, '[REDACTED]')
        (work/'verification.json').write_text(serialized+'\n')
        print(json.dumps({'passed': report['passed'], 'groups': len(report['checks']), 'error': report.get('error'),
                          'evidence': str(work/'verification.json')}, indent=2), flush=True)
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
