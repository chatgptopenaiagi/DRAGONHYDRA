"""Read-only HTTP acceptance after the explicit isolated A8-profile A9 upgrade.
Secrets remain in process memory; no browser/native UI input or provider requests.
"""
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import http.cookiejar
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'build/workstation/test-install/genesis-a8/state data'
OUT = ROOT / 'build/master-release-20261101/windows-http-acceptance.json'

class Form(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden={}; self.actions=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='input' and a.get('type')=='hidden' and a.get('name'): self.hidden[a['name']]=a.get('value','')
        if tag=='form': self.actions.append(a.get('action',''))

def main():
    assert not OUT.exists()
    cfg=json.loads((STATE/'workstation.json').read_text(encoding='utf-8-sig'))
    assert cfg['service_name']=='DragonhydraGenesisA8Test' and cfg['web_port']==18750 and cfg['api_port']==18749
    origin='http://127.0.0.1:18750'; api='http://127.0.0.1:18749/dragon/api/v1'
    token=json.loads((STATE/'client/local-session.json').read_text(encoding='utf-8-sig'))['token']
    jar=http.cookiejar.CookieJar(); opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPCookieProcessor(jar))
    report={'schema_version':1,'passed':False,'started_at':datetime.now(timezone.utc).isoformat(),'scope':'HTTP against isolated A8 installation after full A9 installer upgrade, not new native-client UI acceptance','origin':origin,'backend':api,'checks':[],'secrets_logged':False,'provider_requests':False}
    def check(name,ok,**evidence):
        report['checks'].append({'name':name,'status':'PASS' if ok else 'FAIL',**evidence}); assert ok,name
    def request(url,form=None,auth=False):
        assert url.startswith(origin+'/') or url.startswith(api+'/')
        headers={'User-Agent':'DRAGONHYDRA-A9-release-acceptance'}
        if auth: assert url.startswith(api+'/');headers['Authorization']='Bearer '+token
        req=urllib.request.Request(url,data=None if form is None else urllib.parse.urlencode(form).encode(),headers=headers)
        with opener.open(req,timeout=30) as r:return r.status,r.read().decode(),r.geturl()
    try:
        _,html,_=request(origin+'/')
        check('new_native_home_and_anonymous_private_data_protection','dragonhydra-workspace' in html and 'Welcome to Joomla' not in html and 'data-total="total_matches"' not in html)
        login_match=re.search(r'<a[^>]+href="([^"]+)"[^>]*>Sign in to your workspace',html)
        assert login_match
        login_url=urllib.parse.urljoin(origin,unescape(login_match.group(1)));_,html,_=request(login_url)
        p=Form();p.feed(html);action=urllib.parse.urljoin(origin,unescape(p.actions[0]));assert action.startswith(origin+'/')
        check('actual_site_login_csrf_and_cookie',any(re.fullmatch('[a-f0-9]{32}',key) for key in p.hidden) and len(list(jar))>0)
        _,html,_=request(action,p.hidden|{'username':cfg['admin_user'],'password':cfg['admin_password']})
        _,html,_=request(origin+'/')
        _,body,_=request(api+'/matches?limit=1',auth=True);backend=json.loads(body);record=backend['items'][0]
        check('genuine_site_login_backend_totals',re.search(r'data-total="total_matches"[^>]*>\s*'+str(backend['total'])+r'\s*<',html) is not None,total=backend['total'])
        url=origin+'/index.php?'+urllib.parse.urlencode({'option':'com_dragonhydra','section':'matches','match_id':record['id']})
        _,html,_=request(url)
        check('real_retained_record_via_joomla',record['id'] in html and 'dragonhydra-workspace' in html,match_id=record['id'],backend_record_sha256=hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        admin=origin+'/administrator/';_,html,_=request(admin);p=Form();p.feed(html)
        assert 'mod-login-username' in html
        action=urllib.parse.urljoin(admin,p.actions[0]);assert action==admin+'index.php'
        _,html,_=request(action,p.hidden|{'username':cfg['admin_user'],'passwd':cfg['admin_password'],'option':'com_login','task':'login'})
        _,html,_=request(admin+'index.php?option=com_dragonhydra&section=sources')
        check('genuine_admin_login_component_bridge','dragonhydra-administration' in html and 'Data sources' in html and 'mod-login-username' not in html)
        _,html,_=request(origin+'/index.php?option=com_dragonhydra&section=teams')
        check('subsequent_authenticated_navigation','dragonhydra-workspace' in html and 'Sign in to your workspace' not in html)
        report['passed']=True
    except Exception as error:
        report['failure_class']=type(error).__name__;report['raw_exception_omitted']=True
    report['finished_at']=datetime.now(timezone.utc).isoformat();OUT.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return 0 if report['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
