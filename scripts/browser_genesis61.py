"""Real Edge interaction with the virtual loopback dashboard, including restart inspection."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect

TOKEN='virtual-genesis61-session-not-a-real-account-1234'

def sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--url',default='http://127.0.0.1:19390')
    parser.add_argument('--resume',type=Path)
    args=parser.parse_args(argv);url=args.url.rstrip('/');address=urlparse(url)
    if address.scheme!='http' or address.hostname!='127.0.0.1' or address.port==19380 or address.path:raise ValueError('GENESIS61_EXACT_NEW_LOOPBACK_REQUIRED')
    output=args.output.absolute()
    if output.exists():raise ValueError('NEW_BROWSER_EVIDENCE_REQUIRED')
    output.mkdir(parents=True)
    report={'schema_version':'dragonhydra.genesis61-browser/1','synthetic':True,'status':'RUNNING','checks':[],'page_errors':[],'external_requests_blocked':[]}
    def check(name,condition):
        report['checks'].append({'name':name,'status':'PASS' if condition else 'FAIL'})
        if not condition:raise AssertionError(name)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',headless=True,args=['--disable-background-networking','--disable-component-update','--no-first-run'])
            report['browser']=browser.version
            context=browser.new_context(viewport={'width':1440,'height':1080},locale='en-GB')
            def route(r):
                a=urlparse(r.request.url)
                if a.hostname!='127.0.0.1' or a.port!=address.port:
                    report['external_requests_blocked'].append(r.request.url);r.abort()
                else:r.continue_()
            context.route('**/*',route)
            page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
            page.set_default_timeout(30000)
            page.goto(url+'/#future')
            expect(page.locator('#login-dialog')).to_be_visible()
            page.locator('#pairing-token').fill(TOKEN)
            page.get_by_role('button',name='Connect',exact=True).click()
            expect(page.locator('#login-dialog')).not_to_be_visible()
            page.goto(url+'/#future')
            expect(page.get_by_role('heading',name='Future relevance research',exact=True)).to_be_visible()
            check('VIRTUAL_LABEL_VISIBLE',page.get_by_text('SIMULATION · SYNTHETIC FUTURE RELEVANCE ONLY',exact=True).is_visible())
            report['backend_build']=context.request.get(url+'/dragon/api/v1/system').json()['build']
            local=Path(__file__).absolute().parents[1]
            seal=local/'GENESIS61-BUILD.json'
            if seal.exists():
                expected=json.loads(seal.read_text(encoding='utf-8'))['source_sha']
                check('PACKAGED_BACKEND_SOURCE_BOUND',report['backend_build']['source_sha']==expected and report['backend_build'].get('payload_verified') is True and report['backend_build']['source_dirty'] is False)
            for name in ('future.js','future.css','app.js','index.html','realtime.js'):
                check('SERVED_'+name,context.request.get(url+'/'+name).body()==(local/'src/dragonhydra/resources/web'/name).read_bytes())
            def api(path):
                response=context.request.get(url+'/dragon/api/v1/future'+path)
                if response.status!=200:raise AssertionError(str((path,response.status,response.text()[:200])))
                return response.json()
            def ready():expect(page.locator('[data-action=future-refresh]')).to_be_enabled()
            if args.resume:
                previous=json.loads(args.resume.read_text(encoding='utf-8'))
                eid=previous['episode_id']
                page.locator('#future-episode').select_option(eid);ready()
                state=api('/episodes/'+eid)
                check('RESTART_IMMUTABLE_DECISIONS',sha(state['decisions'])==previous['decisions_sha256'])
                check('RESTART_EVALUATIONS',sha(state['evaluations'])==previous['evaluations_sha256'])
                check('RESTART_NO_DUPLICATE_COST',api('/status')['acquisition_budget_spent']==previous['spent'])
                check('RESTART_FROZEN_MODEL',api('/status')['active_model_id']==previous['model_id'])
                report.update(episode_id=eid,decisions_sha256=sha(state['decisions']),evaluations_sha256=sha(state['evaluations']))
            else:
                check('PASSIVE_VIEW_HAS_NO_EPISODES',api('/episodes')['items']==[])
                page.locator('#future-training-cases-per-family').fill('10')
                page.locator('[data-action=future-train]').click();ready()
                model_id=api('/status')['active_model_id']
                check('ACTUAL_TRAINED_MODEL_RETAINED',model_id.startswith('ridge-future-relevance/1-'))
                check('FIVE_POLICY_ROWS_VISIBLE',page.locator('tr').filter(has_text='acquire_none').count()==1 and page.locator('tr').filter(has_text='learned').count()==1)
                page.locator('#future-universe').select_option('noisy_signal')
                page.locator('[data-action=future-create]').click();ready()
                eid=page.locator('#future-episode').input_value()
                before=api('/episodes/'+eid)
                check('UNREVEALED_FATIGUE_PREDICTED',not before['snapshot']['acquired'] and any(e['category']=='fatigue' and isinstance(e['estimated_value'],float) for e in before['estimates']))
                page.locator('#future-policy').select_option('learned')
                page.locator('[data-action=future-decide]').click();ready()
                first=api('/episodes/'+eid)['decisions'][0];first_hash=sha(first)
                check('UI_DEFER_BEFORE_INFORMATION_EXISTS',first['actions'][-1]['action']=='DEFER' and first['acquisition_cost']==0)
                page.locator('#future-advance-minutes').fill('2')
                page.locator('[data-action=future-advance]').click();ready()
                state=api('/episodes/'+eid);resumed=state['decisions'][-1]
                check('UI_AUTONOMOUS_ELIGIBLE_ACQUISITION',resumed.get('resumes_decision_id')==first['decision_id'] and 'fatigue' in state['snapshot']['acquired'])
                check('ACTUAL_COST_AND_SAME_TIME_FORECAST',resumed['acquisition_cost']>0 and resumed['before']['cutoff']==resumed['after']['cutoff'])
                check('NO_PREMATURE_OUTCOME',state['evaluations']==[])
                page.locator('#future-advance-minutes').fill('9')
                page.locator('[data-action=future-advance]').click();ready()
                state=api('/episodes/'+eid)
                check('LATER_USEFULNESS_MEASURED',len(state['evaluations'])==2 and any(e['deferred_future_relevance'] for e in state['evaluations']))
                check('HISTORICAL_FORECAST_IMMUTABLE',sha(state['decisions'][0])==first_hash)
                page.get_by_text('Eligible retrospective paired evaluations',exact=True).click()
                check('ACTUAL_EVALUATION_DISPLAYED','observed_local_improvement' in page.locator('.fu-workspace').inner_text())
                page.get_by_role('heading',name='Advance virtual time and evaluate eligible outcomes',exact=True).scroll_into_view_if_needed()
                page.screenshot(path=str(output/'evaluation.png'))
                spent=api('/status')['acquisition_budget_spent']
                page.locator('[data-action=future-refresh]').click();ready()
                check('REFRESH_IS_PASSIVE',api('/status')['acquisition_budget_spent']==spent)
                page.locator('#future-target').select_option('FULL_TIME_RESULT')
                check('TARGET_DEPENDENT_HORIZON_CONTROL',page.locator('#future-horizon option').count()==1 and page.locator('#future-horizon').input_value()=='FULL_TIME')
                page.locator('#future-seed').fill('-1');page.locator('#future-minute').click()
                expect(page.locator('.fu-error')).to_contain_text('Invalid Seed')
                check('VALIDATION_ERROR_VISIBLE',len(api('/episodes')['items'])==1)
                page.goto(url+'/#research')
                expect(page.get_by_role('heading',name='Realtime research',exact=True)).to_be_visible()
                page.locator('#research-seed').fill('61')
                page.get_by_role('button',name='New standard simulation',exact=True).click()
                expect(page.locator('#research-match')).to_be_visible()
                page.get_by_role('button',name='Refresh research',exact=True).wait_for(state='visible')
                expect(page.get_by_role('button',name='Refresh research',exact=True)).to_be_enabled()
                page.get_by_role('button',name='Step',exact=True).click()
                expect(page.get_by_role('button',name='Refresh research',exact=True)).to_be_enabled()
                mid=page.locator('#research-match').input_value()
                old=context.request.get(url+'/dragon/api/v1/realtime/matches/'+mid).json()
                check('ORIGINAL_REPLAY_NAVIGATION_AND_STEP',old['state']['revision']==1)
                page.goto(url+'/#future');expect(page.locator('[data-action=future-refresh]')).to_be_enabled()
                report.update(episode_id=eid,decisions_sha256=sha(state['decisions']),evaluations_sha256=sha(state['evaluations']),spent=spent,model_id=model_id)
            page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(output/'workspace.png'))
            page.set_viewport_size({'width':520,'height':900});page.screenshot(path=str(output/'narrow.png'))
            check('NARROW_LAYOUT_NO_DOCUMENT_OVERFLOW',page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
            check('NO_BROWSER_ERRORS',not report['page_errors'])
            context.close();browser.close()
        report['status']='PASS'
    except BaseException as error:
        report.update(status='FAILED',failure=f'{type(error).__name__}: {error}')
        raise
    finally:
        (output/'BROWSER.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'output':str(output)}))

if __name__=='__main__':main()
