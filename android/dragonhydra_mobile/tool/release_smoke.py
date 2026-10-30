"""Install and exercise a final APK on an explicitly isolated release emulator.

No live server is started/stopped. The caller supplies isolated server/session
files, and ADB forwards only this emulator's local test port. Tokens stay private.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--adb', type=Path, required=True)
    parser.add_argument('--serial', default='emulator-5584')
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--endpoint-file', type=Path, required=True)
    parser.add_argument('--session-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--version-code', default='4')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = 'ai.dragonhydra.mobile'
    checks, commands = [], []
    token = json.loads(args.session_file.read_text(encoding='utf-8-sig'))['token']
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,200}', token):
        raise ValueError('Unexpected test pairing token format')
    endpoint = json.loads(args.endpoint_file.read_text(encoding='utf-8-sig'))['url']
    from urllib.parse import urlsplit
    parsed = urlsplit(endpoint)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1':
        raise ValueError('An isolated loopback server endpoint is required')

    def adb(*argv, timeout=50):
        result = subprocess.run([str(args.adb), '-s', args.serial, *argv], capture_output=True, timeout=timeout)
        text = result.stdout.decode('utf-8', errors='replace')
        error = result.stderr.decode('utf-8', errors='replace')
        commands.append({'args': [str(x).replace(token, '[redacted-test-token]') for x in argv],
                         'exit_code': result.returncode, 'stdout': text.replace(token, '[redacted-test-token]'),
                         'stderr': error.replace(token, '[redacted-test-token]')})
        if result.returncode:
            raise RuntimeError('ADB operation failed: ' + ' '.join(str(v).replace(token, '[redacted]') for v in argv[:3]))
        return text

    avd = adb('shell', 'getprop', 'ro.boot.qemu.avd_name').strip()
    if not avd.startswith('DRAGONHYDRA_RELEASE_'):
        raise ValueError('Refusing installation on a user device or unrelated emulator')

    def dump():
        adb('shell', 'uiautomator', 'dump', '/sdcard/dragonhydra-release-ui.xml')
        raw = adb('shell', 'cat', '/sdcard/dragonhydra-release-ui.xml')
        return ET.fromstring(raw)

    def label(node):
        return node.get('content-desc', '') + '\n' + node.get('text', '')

    def wait(text, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tree = dump()
            if any(text in label(n) for n in tree.iter('node')):
                return tree
            time.sleep(0.25)
        raise AssertionError('Visible result missing: '+text)

    def tap_label(text, exact=False):
        for direction in (0, 1, 1, 1, -1, -1, -1):
            if direction:
                adb('shell', 'input', 'swipe', '540', '1700' if direction>0 else '700', '540', '700' if direction>0 else '1700', '250')
            tree = dump()
            for n in tree.iter('node'):
                visible_label = label(n)
                found = text in (n.get('content-desc',''),n.get('text','')) if exact else text in visible_label
                if found and n.get('clickable') == 'true':
                    x1,y1,x2,y2 = map(int, re.findall(r'\d+',n.get('bounds','')))
                    adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))
                    return
        raise AssertionError('Clickable control missing: '+text)

    def field(index, value):
        tree = dump()
        fields = [n for n in tree.iter('node') if n.get('class')=='android.widget.EditText']
        n=fields[index]
        x1,y1,x2,y2=map(int,re.findall(r'\d+',n.get('bounds','')))
        adb('shell','input','tap',str((x1+x2)//2),str((y1+y2)//2))
        adb('shell','input','keyevent','123')
        adb('shell','input','keyevent',*(['67']*200))
        adb('shell','input','text',value)
        adb('shell','input','keyevent','4')

    def screenshot(name):
        remote='/sdcard/dragonhydra-release-'+name+'.png'
        adb('shell','screencap','-p',remote)
        adb('pull',remote,str(args.output/(name+'.png')))
        tree=dump()
        sanitized=ET.tostring(tree,encoding='unicode').replace(token,'[redacted-test-token]')
        (args.output/(name+'.xml')).write_text(sanitized,encoding='utf-8')

    before = adb('shell','dumpsys','package',app)
    installed=adb('install','-r',str(args.apk),timeout=120)
    if 'Success' not in installed:
        raise AssertionError('Final APK installation did not succeed')
    after=adb('shell','dumpsys','package',app)
    if 'versionCode='+args.version_code not in after:
        raise AssertionError('Installed versionCode differs from the release')
    if 'firstInstallTime=' in before:
        old_time=re.search(r'firstInstallTime=([^\r\n]+)',before).group(1)
        new_time=re.search(r'firstInstallTime=([^\r\n]+)',after).group(1)
        if old_time!=new_time:
            raise AssertionError('Upgrade did not retain the existing package installation')
        checks.append('Prior Android alpha upgraded in place with firstInstallTime preserved')
    checks.append('Final signed APK installed with expected versionCode')
    adb('shell','am','force-stop',app)
    adb('shell','am','start','-n',app+'/.MainActivity')
    wait('Intelligence,')
    screenshot('offline-home')
    checks.append('Installed APK launched and rendered existing offline Home')
    tap_label('Connect to DRAGONHYDRA server')
    wait('Server address')
    field(0,'http://127.0.0.1:1')
    tap_label('Connect and browse')
    wait('Server unavailable')
    wait('Retry server')
    screenshot('server-unavailable')
    checks.append('Unavailable server has a visible error and Retry control')
    adb('reverse','tcp:18745','tcp:'+str(parsed.port))
    field(0,'http://127.0.0.1:18745')
    field(1,'wrong-test-only-pairing-token')
    tap_label('Retry server')
    wait('Authentication rejected')
    checks.append('Wrong pairing token is rejected visibly')
    field(1,token)
    tap_label('Retry server')
    wait('Connected:')
    request=Request(endpoint+'/dragon/api/v1/matches?limit=25',headers={'Authorization':'Bearer '+token})
    with urlopen(request,timeout=10) as response:
        data=json.load(response)
    match=data['items'][0]
    title=match['home']['name']+' vs '+match['away']['name']
    tap_label(title)
    wait('Server match')
    wait(match['id'])
    screenshot('canonical-match')
    checks.append('Server address reached the versioned API and opened the same canonical match')
    tap_label(match['home']['name'])
    wait('Recent form')
    screenshot('team-form')
    adb('shell','input','keyevent','4')
    wait('Server match')
    tap_label('Open standings')
    wait('Unofficial reconstructed standings')
    screenshot('standings')
    adb('shell','input','keyevent','4')
    wait('Server match')
    tap_label('Model probabilities')
    wait('Model probabilities')
    screenshot('probabilities')
    checks.append('Related team/form, labelled standings and available analysis controls were exercised')
    adb('shell','am','force-stop',app)
    adb('shell','am','start','-n',app+'/.MainActivity')
    wait('Intelligence,')
    tap_label('Connect to DRAGONHYDRA server')
    wait('http://127.0.0.1:18745')
    checks.append('Configured address retained after process restart through encrypted settings')
    adb('shell','input','keyevent','4')
    tap_label('Open navigation menu')
    tap_label('Settings',exact=True)
    wait('Settings & connections')
    for _ in range(5):
        tree=dump()
        if args.source_sha in ET.tostring(tree,encoding='unicode'):
            break
        adb('shell','input','swipe','540','1800','540','650','350')
    else:
        raise AssertionError('Frozen source SHA not visible in installed Settings/About')
    screenshot('build-source')
    checks.append('Installed About displays the exact frozen source SHA')
    adb('reverse','--remove','tcp:18745')
    result={'schema_version':1,'status':'passed','completed_at':datetime.now(timezone.utc).isoformat(),
        'source_sha':args.source_sha,'version_code':int(args.version_code),'app_id':app,'serial':args.serial,'avd':avd,
        'android_sdk':adb('shell','getprop','ro.build.version.sdk').strip(),
        'abi_list':adb('shell','getprop','ro.product.cpu.abilist').strip(),
        'artifact':args.apk.name,'bytes':args.apk.stat().st_size,'sha256':hashlib.sha256(args.apk.read_bytes()).hexdigest(),
        'assertions':checks,'user_device_modified':False,'live_services_stopped':False,
        'installation_kind':'Project-owned API37 emulator using existing x86_64/ARM64 translation image'}
    (args.output/'android-smoke.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (args.output/'commands-private.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
