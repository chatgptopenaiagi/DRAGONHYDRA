"""Actual Windows Tauri/WebView2 external-link acceptance, against existing API.

Launches one byte-exact client copy with private profile and process-only CDP.
No mock browser, shell replacement, provider retrieval, configuration writes or
service controls occur. Only matching expected public URLs from new default
browser process command lines are retained; unrelated command lines are not.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit, unquote
from urllib.request import build_opener, ProxyHandler
import winreg

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = ROOT/'build/connections/external-links-20261101'
PROVIDERS = ('api-football', 'the-odds-api', 'sportmonks')
TITLE_PATTERNS = {
    'api-football': re.compile(r'API[- ]Football|API[- ]SPORTS', re.I),
    'the-odds-api': re.compile(r'The Odds API|Odds API', re.I),
    'sportmonks': re.compile(r'Sportmonks|Fixtures.*API 3\.0|Fixtures.*Football API', re.I),
}
API = '/dragon/api/v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def default_browser():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice') as key:
        progid = winreg.QueryValueEx(key, 'ProgId')[0]
    with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid+r'\shell\open\command') as key:
        command = winreg.QueryValueEx(key, None)[0]
    executable = command.split('"')[1] if command.startswith('"') else command.split(' ')[0]
    return {'progid': progid, 'executable': str(Path(executable).resolve()),
            'process_name': Path(executable).name.lower()}


class BrowserObserver:
    """Read-only bounded process observer; only expected URL matches survive."""
    def __init__(self, windows, browser, expected):
        self.windows, self.browser, self.expected = windows, browser, expected
        self.baseline = set(windows.tree())
        self.observed = []
        self.stop_event = threading.Event()
        self.ntdll = ctypes.WinDLL('ntdll')
        self.query = self.ntdll.NtQueryInformationProcess
        self.query.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p,
                               wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
        self.query.restype = wintypes.LONG
        self.thread = threading.Thread(target=self.run, daemon=True)

    def process_command(self, pid):
        class UnicodeString(ctypes.Structure):
            _fields_ = [('length', wintypes.USHORT), ('maximum', wintypes.USHORT),
                        ('buffer', ctypes.c_void_p)]
        handle = self.windows.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            length = wintypes.ULONG()
            self.query(handle, 60, None, 0, ctypes.byref(length))
            if not 0 < length.value < 1024*1024:
                return None
            data = ctypes.create_string_buffer(length.value)
            if self.query(handle, 60, data, length.value, ctypes.byref(length)) < 0:
                return None
            value = UnicodeString.from_buffer(data)
            return ctypes.wstring_at(value.buffer, value.length//2) if value.buffer else None
        finally:
            self.windows.kernel.CloseHandle(handle)

    def run(self):
        seen = set(self.baseline)
        while not self.stop_event.is_set():
            try:
                for pid, item in self.windows.tree().items():
                    if pid in seen or item['name'].lower() != self.browser['process_name']:
                        continue
                    command = self.process_command(pid)
                    if command is None:
                        continue
                    seen.add(pid)
                    matches = [url for url in self.expected if url in command]
                    if matches:
                        info = self.windows.process(pid)
                        if Path(info['path']) == Path(self.browser['executable']):
                            self.observed.append({'pid': pid, 'executable': info['path'],
                                                  'urls': matches, 'observed_at': datetime.now(timezone.utc).isoformat()})
                    # The command value is intentionally never stored/logged.
            except (OSError, RuntimeError):
                pass
            self.stop_event.wait(.005)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=3)

    def matches(self, url):
        return [item for item in self.observed if url in item['urls']]


def browser_window_receipts(windows, browser, pattern):
    """Read native top-level title/PID metadata, never invoke UI Automation."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextLengthW.argtypes=[wintypes.HWND]
    user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    tree=windows.tree(); receipts=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @callback_type
    def callback(hwnd,_):
        if not user.IsWindowVisible(hwnd): return True
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if tree.get(pid.value,{}).get('name','').lower()!=browser['process_name']:return True
        length=user.GetWindowTextLengthW(hwnd)
        text=ctypes.create_unicode_buffer(length+1);user.GetWindowTextW(hwnd,text,length+1)
        if not pattern.search(text.value):return True
        try:
            info=windows.process(pid.value)
            if Path(info['path'])==Path(browser['executable']):
                receipts.append({'hwnd':hwnd,'pid':pid.value,'executable':info['path'],'title':text.value})
        except (OSError,RuntimeError):pass
        return True
    user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user.EnumWindows(callback,0)
    return receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True, help='Existing owner-readable client pairing metadata only')
    parser.add_argument('--output', type=Path, required=True, help='Fresh directory below the dedicated test boundary')
    parser.add_argument('--expect-opening', choices=('yes', 'no'), required=True)
    parser.add_argument('--keep-open', action='store_true')
    parser.add_argument('--run-in-place', action='store_true',
                        help='Run only the exact authorized installed provider-a2 client, without copying it')
    args = parser.parse_args()
    binary, state, output = args.binary.resolve(), args.state.resolve(), args.output.resolve()
    if os.name != 'nt' or not output.is_relative_to(BOUNDARY) or output == BOUNDARY or output.exists():
        parser.error('Use Windows and a fresh owned output below '+str(BOUNDARY))
    if args.run_in_place:
        installed=(ROOT/'build/workstation/test-install/provider-a2/application files/client/DRAGONHYDRA-Client.exe').resolve()
        if not installed.is_relative_to(ROOT) or binary!=installed:
            parser.error('--run-in-place is restricted to the exact authorized installed provider-a2 client')
    output.mkdir(parents=True)
    # Reuse existing capability-aware native process/ACL/listener inspection.
    spec = importlib.util.spec_from_file_location('native_process_evidence', ROOT/'tests/ui/native_webview_journey.py')
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    native.BASE = BOUNDARY
    windows = native.Windows()
    # The reused inspector configures ctypes function argument types using a
    # local structure class. Serialize snapshots across observer/main threads.
    snapshot_lock=threading.RLock()
    original_tree=windows.tree
    def process_tree():
        with snapshot_lock:
            return original_tree()
    windows.tree=process_tree
    windows.private_directory(output/'profile')
    owned = binary if args.run_in_place else output/'client-copy.exe'
    if not args.run_in_place:
        shutil.copyfile(binary, owned)
    assert digest(binary) == digest(owned)
    endpoint = json.loads((state/'endpoint.json').read_text(encoding='utf-8-sig'))
    origin = endpoint['url']
    parsed = urlsplit(origin)
    assert parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and not parsed.username and not parsed.password
    source_hashes = {name:digest(state/name) for name in ('endpoint.json','local-session.json')}
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0)); port = probe.getsockname()[1]
    environment = {name:value for name,value in os.environ.items()
                   if name.upper() not in ('PWDEBUG','DEBUG','DEBUG_FILE') and not name.startswith('WEBVIEW2_')}
    environment['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = f'--remote-debugging-address=127.0.0.1 --remote-debugging-port={port}'
    environment['WEBVIEW2_USER_DATA_FOLDER'] = str(output/'profile')
    report = {'schema_version':1, 'passed':False, 'started_at':datetime.now(timezone.utc).isoformat(),
              'scope':'Actual copied Windows Tauri client/WebView2 DOM clicks and actual default-browser process dispatch',
              'binary':str(binary),'binary_sha256':digest(binary),'harness_sha256':digest(__file__),
              'actual_installed_binary_executed':args.run_in_place,
              'launched_executable':str(owned),
              'expected_opening':args.expect_opening,'default_browser':default_browser(),
              'providers_requested':False,'settings_writes_requested':False,'checks':[], 'console_errors':[],
              'blocked_requests':[], 'failed_requests':[]}
    process, pw, page, observer = None, None, None, None
    try:
        process = subprocess.Popen([str(owned),'--state',str(state),'--profile',str(output/'profile')],
                                   env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        info = windows.process(process.pid)
        assert Path(info['path']) == owned and info['integrity_class'] == 'Medium'
        report['client_process'] = info
        native.PORT = port
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic()+45
        while time.monotonic()<deadline:
            assert process.poll() is None, 'Native client exited before debugging readiness'
            listeners = windows.listeners()
            if listeners:
                native.listener_guard(listeners, windows.descendants(process.pid)-{process.pid})
                break
            time.sleep(.1)
        else:
            raise TimeoutError('Native WebView CDP listener unavailable')
        report['cdp'] = {'port':port,'listeners':listeners,'owned_webview2':True}
        from playwright.sync_api import sync_playwright, expect
        pw = sync_playwright().start()
        browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}',timeout=15000)
        assert len(browser.contexts)==1
        context = browser.contexts[0]
        deadline = time.monotonic()+30
        while time.monotonic()<deadline:
            pages=[p for p in context.pages if p.url.startswith(origin+'/')]
            if len(pages)==1:
                page=pages[0];break
            time.sleep(.1)
        assert page is not None, 'No unique native API dashboard target'
        page.set_default_timeout(15000)
        def request_label(request):
            url=urlsplit(request.url)
            return {'method':request.method,'url':url.scheme+'://'+str(url.hostname or '')+url.path}
        def guard(route):
            request=route.request;url=urlsplit(request.url)
            opener_ipc=(url.scheme in ('http','ipc') and url.hostname in ('ipc.localhost','localhost')
                        and unquote(url.path)=='/plugin:opener|open_url' and request.method in ('POST','OPTIONS'))
            if opener_ipc or url.scheme in ('data','blob') or (url.scheme+'://'+url.netloc==origin and
                (request.method in ('GET','HEAD') or request.method=='POST' and url.path==API+'/session')):
                route.continue_()
            else:
                report['blocked_requests'].append(request_label(request))
                route.abort('blockedbyclient')
        context.route('**/*',guard)
        page.on('pageerror',lambda error:report['console_errors'].append(str(error).split('#token=')[0][:300]))
        page.on('requestfailed',lambda request:report['failed_requests'].append(request_label(request)))
        expect(page.locator('#service-state')).to_have_text('Server ready · sqlite',timeout=30000)
        assert '#token=' not in page.url
        assert page.evaluate('Boolean(window.chrome?.webview && window.__TAURI_INTERNALS__)')
        page.get_by_role('link',name='Connections',exact=True).click()
        expect(page.locator('[data-provider="api-football"]')).to_be_visible()
        data=page.evaluate("async()=>await (await fetch('/dragon/api/v1/connections')).json()")
        def settings_hash(data):
            settings=[{k:item.get(k) for k in ('id','config','interval_seconds','credential_configured')}
                      for item in data['items']]
            return hashlib.sha256(canonical(settings)).hexdigest()
        report['settings_before_sha256']=settings_hash(data)
        report['record_counts_before']={item['id']:item['record_count'] for item in data['items']}
        urls={item['id']:item['registration_url'] for item in data['items'] if item['id'] in PROVIDERS}
        assert len(urls)==3 and all(urlsplit(url).scheme=='https' for url in urls.values())
        # Tauri's invoke property is deliberately immutable. Read existing
        # handler source through CDP; observe click state without replacing it.
        cdp=context.new_cdp_session(page)
        listeners=cdp.send('Runtime.evaluate',{'expression':'getEventListeners(window).click.map(e=>String(e.listener))',
            'includeCommandLineAPI':True,'returnByValue':True})['result'].get('value',[])
        official_handler=any('plugin:opener|open_url' in text for text in listeners)
        report['official_opener_click_handler_present']=official_handler
        page.evaluate("""() => {
          window.__dragonLinkProbe=[];
          window.addEventListener('click',event=>{
            const anchor=event.composedPath().find(node=>node instanceof Node&&node.nodeName==='A');
            if(anchor?.target==='_blank') window.__dragonLinkProbe.push({url:anchor.href,defaultPrevented:event.defaultPrevented});
          });
        }""")
        observer=BrowserObserver(windows,report['default_browser'],urls.values());observer.start()
        # Switching providers first avoids mistaking an already active API docs
        # tab (from an earlier diagnostic) for a fresh browser receipt.
        order=('the-odds-api','sportmonks','api-football') if args.expect_opening=='yes' else PROVIDERS
        for provider in order:
            url=urls[provider]
            link=page.locator(f'[data-provider="{provider}"]').get_by_role('link',name='Register / get API key ↗',exact=True)
            assert link.get_attribute('href')==url and link.get_attribute('target')=='_blank'
            before=page.url
            browser_before=browser_window_receipts(windows,report['default_browser'],TITLE_PATTERNS[provider])
            link.click()
            deadline=time.monotonic()+(20 if args.expect_opening=='yes' else 2)
            click_events=[];browser_receipts=[]
            while time.monotonic()<deadline:
                click_events=[item for item in page.evaluate('window.__dragonLinkProbe') if item['url']==url]
                browser_receipts=browser_window_receipts(windows,report['default_browser'],TITLE_PATTERNS[provider])
                if args.expect_opening=='yes' and browser_receipts:
                    break
                page.wait_for_timeout(50)
            dispatched=observer.matches(url)
            assert process.poll() is None and page.url==before and '#connections' in page.url
            if args.expect_opening=='yes':
                assert official_handler and click_events and click_events[-1]['defaultPrevented'], 'Native plugin did not handle anchor click for '+provider
                assert browser_receipts, 'Registered default browser did not show expected provider title for '+provider
            else:
                assert not official_handler and click_events and not click_events[-1]['defaultPrevented'] and not dispatched, 'Original unexpectedly dispatched '+provider
            report['checks'].append({'provider':provider,'expected_url':url,
                                     'click_events':click_events,
                                     'browser_windows_before':browser_before,
                                     'default_browser_window_receipts':browser_receipts,
                                     'native_opener_handoff_verified':bool(official_handler and click_events and click_events[-1]['defaultPrevented']),
                                     'default_browser_process_dispatch_observed':bool(dispatched),
                                     'dispatch_processes':dispatched,'native_application_still_open':True,
                                     'native_route_unchanged':True})
        observer.stop()
        after=page.evaluate("async()=>await (await fetch('/dragon/api/v1/connections')).json()")
        report['settings_after_sha256']=settings_hash(after)
        report['record_counts_after']={item['id']:item['record_count'] for item in after['items']}
        assert report['settings_before_sha256']==report['settings_after_sha256']
        assert report['record_counts_before']==report['record_counts_after']
        assert source_hashes=={name:digest(state/name) for name in source_hashes}
        assert digest(binary)==report['binary_sha256'], 'Selected executable changed during verification'
        report['connection_settings_unchanged']=True
        report['pairing_and_endpoint_unchanged']=True
        report['native_route']=origin+'/#connections'
        report['native_page_target_id']=context.new_cdp_session(page).send('Target.getTargetInfo')['targetInfo']['targetId']
        page.screenshot(path=str(output/'connections.png'),full_page=True)
        report['screenshot_sha256']=digest(output/'connections.png')
        report['defect_reproduced']=args.expect_opening=='no'
        report['default_browser_delivery_verification']=(
            'actual_default_browser_window_title_receipts_after_native_clicks; exact_clicked_URLs_verified; addressbar_UI_comparison_is_separate'
            if args.expect_opening=='yes' else 'not_expected_for_original_defect')
        report['passed']=True
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error).split('#token=')[0][:700]}
    finally:
        if observer is not None:observer.stop()
        if process is not None:
            report['native_application_alive_after_checks']=process.poll() is None
            if not args.keep_open and process.poll() is None:
                # Exact own Popen handle only; no user client, service or browser.
                process.terminate();process.wait(timeout=10)
                report['owned_copy_cleanup']={'method':'Exact owned process handle terminated after checks',
                                              'installed_executable':args.run_in_place,'exit_code':process.returncode}
            else:
                report['owned_copy_left_open']=process.poll() is None
        if pw is not None:pw.stop()
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        temporary=output/'verification.json.tmp'
        temporary.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        temporary.replace(output/'verification.json')
    print(json.dumps({'passed':report['passed'],'checks':len(report['checks']),
                      'defect_reproduced':report.get('defect_reproduced'),
                      'error':report.get('error'),'report':str(output/'verification.json')}))
    return 0 if report['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
