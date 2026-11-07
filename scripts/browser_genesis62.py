"""Real Edge acceptance of the owned virtual logistics UI; never starts a server.

Default journey mutates only synthetic state on 127.0.0.1:19400. --resume is
strictly read-only and compares retained state after a separately proven restart.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
import uuid

TOKEN='virtual-genesis62-session-not-a-real-account-1234'
EDGE=Path(r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')
SCHEMA='dragonhydra.genesis62-browser/1'
VERSION='0.3.0-virtual-experimental'
BASE='/dragon/api/v1/logistics'
COSTS=('holding','ordering','shortage','transport','spoilage','acquisition','computation')
PANELS=('inventory','demand','replenishment','network','relevance','analytics','time')
ASSETS=('index.html','app.js','style.css','favicon.svg','realtime.js','realtime.css','future.js','future.css','logistics.js','logistics.css')

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def diagnostic(value):return str(value).replace(TOKEN,'[VIRTUAL_PAIRING_MARKER_OMITTED]')
def need(condition,code):
    if not condition:raise AssertionError(code)
def ordinary(value):
    path=Path(value)
    need('..' not in path.parts,'PARENT_PATH_REJECTED');path=path.absolute()
    for p in (path,*path.parents):
        if p.is_symlink() or (p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400):
            raise ValueError('REPARSE_PATH_REJECTED')
    return path
def endpoint(value):
    parsed=urlparse(value.rstrip('/'))
    need(parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port==19400
         and not any((parsed.username,parsed.password,parsed.path,parsed.query,parsed.fragment)),
         'EXACT_OWNED_LOGISTICS_LOOPBACK_REQUIRED')
    return value.rstrip('/')
def fingerprint(view):
    snap=view['snapshot']
    return {'inventory_sha256':sha(snap['inventory']),'snapshot_sha256':sha(snap),
        'decisions_sha256':sha(view['decisions']),'evaluations_sha256':sha(view['evaluations']),
        'metrics_sha256':sha(view['metrics']),'network_sha256':sha(view['network']),
        'forecasts_sha256':sha(view['current_forecasts']),'analyses_sha256':sha(view['analyses']),
        'day':snap['day'],'revision':snap['revision'],'budget_remaining':snap['budget_remaining'],
        'model_id':view.get('model_id')}
def inventory_valid(view):
    inv=view['snapshot']['inventory'];conservation=inv.get('conservation',inv.get('global',{}))
    rows=[row for skus in inv['by_location'].values() for row in skus.values()]
    return (bool(rows) and conservation.get('valid') is True
        and all(r['atp']==r['on_hand']-r['reserved'] and r['inventory_position']==r['on_hand']+r['on_order']-r['backorder']
                and 0<=r['reserved']<=r['on_hand']<=r['capacity'] and 0<=r['in_transit']<=r['on_order'] for r in rows)
        and sum(r['on_hand'] for r in rows)==conservation['on_hand']
        and sum(r['in_transit'] for r in rows)==conservation['in_transit']
        and conservation['physical_total']==conservation['physical_expected']
        and conservation['physical_expected']==conservation['initial']+conservation['production']-conservation['fulfilled']-conservation['spoilage'])
def acquisition_valid(receipt,before):
    candidates={r['category']:r for r in before['snapshot']['candidates']};seen=set();spent=0.
    for row in receipt['acquisitions']:
        category=row['category'];quote=candidates.get(category)
        if not quote or category in seen or quote['availability']!='AVAILABLE' or quote['available_day']>before['snapshot']['day']:return False
        if not math.isclose(row['actual_cost'],quote['cost'],abs_tol=1e-9,rel_tol=0):return False
        spent+=row['actual_cost'];seen.add(category)
    return spent<=before['snapshot']['budget_remaining']+1e-9

def self_test():
    need(endpoint('http://127.0.0.1:19400/')=='http://127.0.0.1:19400','VALID_ENDPOINT')
    for url in ('http://127.0.0.1:19380','http://127.0.0.1:19390','https://127.0.0.1:19400','http://localhost:19400','http://user:pass@127.0.0.1:19400','http://127.0.0.1:19400/old','http://outside.invalid:19400'):
        try:endpoint(url)
        except (ValueError,AssertionError):pass
        else:raise AssertionError('UNSAFE_ENDPOINT_ACCEPTED')
    need(sha({'a':1,'b':2})==sha({'b':2,'a':1}),'CANONICAL_FINGERPRINT')
    before={'snapshot':{'day':28,'budget_remaining':0,'candidates':[{'category':'x','availability':'AVAILABLE','available_day':28,'cost':.1}]}}
    need(acquisition_valid({'acquisitions':[]},before),'ZERO_BUDGET_EMPTY_SUBSET')
    need(not acquisition_valid({'acquisitions':[{'category':'x','actual_cost':.1}]},before),'ZERO_BUDGET_SPEND_REJECTED')
    print(json.dumps({'status':'PASS_PURE_GUARDS_ONLY','browser_started':False,'server_started':False,'network_calls':0}));return 0

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--url',default='http://127.0.0.1:19400')
    parser.add_argument('--source-root',type=Path,default=Path(__file__).absolute().parents[1])
    parser.add_argument('--expected-source')
    parser.add_argument('--resume',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args(argv)
    if args.self_test:return self_test()
    if not args.output:parser.error('--output is required for browser execution')
    url=endpoint(args.url);source=ordinary(args.source_root);lane=source.parent
    need(source.name=='source' and lane.name=='GENESIS-6.2-COGNITIVE-LOGISTICS','EXACT_SOURCE_LANE_REQUIRED')
    output=ordinary(args.output)
    need(output.is_relative_to(lane/'evidence') and output!=lane/'evidence' and not output.exists(),'NEW_OWNED_EVIDENCE_REQUIRED')
    previous=None
    if args.resume:
        prior=ordinary(args.resume);need(prior.is_file() and prior.stat().st_size<2*1024*1024,'BOUNDED_PRIOR_RECEIPT_REQUIRED')
        previous=json.loads(prior.read_text(encoding='utf-8'))
        need(previous.get('schema_version')==SCHEMA and previous.get('status')=='PASS'
             and previous.get('synthetic') is True and previous.get('retained'),'SUCCESSFUL_PRIOR_RECEIPT_REQUIRED')
        need(1<=len(previous['retained']['episodes'])<=10 and all(
            isinstance(item.get('episode_id'),str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',item['episode_id'])
            for item in previous['retained']['episodes'].values()),'BOUNDED_PRIOR_EPISODES_REQUIRED')
    output.mkdir(parents=True)
    report={'schema_version':SCHEMA,'synthetic':True,'status':'RUNNING','started_at':datetime.now(timezone.utc).isoformat(),
        'mode':'READ_ONLY_RESTART_COMPARISON' if previous else 'ACTUAL_UI_JOURNEY',
        'checks':[],'page_errors':[],'external_requests_blocked':[],'mutating_requests':[],
        'process_restart_proof':'OWNER_ORCHESTRATION_SEPARATE_NOT_INFERRED_FROM_STABLE_STATE',
        'training_scope':'DASHBOARD_PREVIEW_NOT_THE_PREDECLARED_OFFLINE_STUDY','server_started':False,
        'actual_provider_or_operational_data_used':False,'active_operation':None,'browser_started':False,'browser_closed':False,
        'controller_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def save():
        report['updated_at']=datetime.now(timezone.utc).isoformat();temp=output/('BROWSER.tmp-'+uuid.uuid4().hex)
        with temp.open('xb') as f:f.write(json.dumps(report,indent=2,allow_nan=False).encode()+b'\n');f.flush();os.fsync(f.fileno())
        os.replace(temp,output/'BROWSER.json')
    def check(name,condition):
        report['checks'].append({'name':name,'status':'PASS' if condition else 'FAIL'});save();need(condition,name)
    with (output/'RUN.started.lock').open('x',encoding='utf-8') as f:f.write(SCHEMA+'\n')
    save()
    try:
        sys.path.insert(0,str(source/'src'))
        identity=importlib.import_module('dragonhydra.cognitive_logistics.server').source_identity()
        expected=args.expected_source or identity['source_sha']
        check('LOCAL_SOURCE_IDENTITY_CLEAN',re.fullmatch('[a-f0-9]{40}',expected) is not None
              and expected==identity['source_sha'] and identity['component_version']==VERSION and identity['source_dirty'] is False)
        report['source_sha']=expected;report['local_source_identity']=identity
        check('CONTROLLER_MATCHES_BOUND_SOURCE',ordinary(source/'scripts/browser_genesis62.py').read_bytes()==Path(__file__).read_bytes())
        if previous:check('PRIOR_SOURCE_BINDING',previous.get('source_sha')==expected)
        if args.resume:report['prior_receipt_sha256']=hashlib.sha256(args.resume.read_bytes()).hexdigest()
        check('EXISTING_EDGE_AVAILABLE',EDGE.is_file())
        from playwright.sync_api import sync_playwright,expect
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=str(EDGE),headless=True,args=['--disable-background-networking','--disable-component-update','--no-first-run'])
            report['browser_started']=True;save()
            try:
                report['browser']=browser.version
                context=browser.new_context(viewport={'width':1440,'height':1080},locale='en-GB',
                    extra_http_headers={'Authorization':'Bearer '+TOKEN} if previous else {})
                def route(r):
                    target=urlparse(r.request.url)
                    if target.scheme!='http' or target.hostname!='127.0.0.1' or target.port!=19400 or target.username or target.password:
                        report['external_requests_blocked'].append({'scheme':target.scheme,'host':target.hostname,'port':target.port});r.abort()
                    elif previous and r.request.method not in ('GET','HEAD','OPTIONS'):
                        report['mutating_requests'].append({'path':target.path,'method':r.request.method,'blocked':True});r.abort()
                    else:
                        if r.request.method not in ('GET','HEAD','OPTIONS'):report['mutating_requests'].append({'path':target.path,'method':r.request.method})
                        r.continue_()
                context.route('**/*',route)
                page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(diagnostic(e)))
                page.set_default_timeout(30000)
                def read(path):
                    response=context.request.get(url+path,max_redirects=0,timeout=30000)
                    need(response.status==200,'AUTHENTICATED_READ_FAILED_'+path);return response.json()
                def api(path):return read(BASE+path)
                def ready(timeout=30000):
                    expect(page.locator('[data-action=logistics-refresh]')).to_be_enabled(timeout=timeout)
                def select_episode(eid):
                    page.locator('#lg-episode').select_option(eid);ready();need(api('/episodes/'+eid)['episode_id']==eid,'EPISODE_SELECTION_UNVERIFIED')
                def click(action,timeout=30000,expect_error=False):
                    report['active_operation']=action;save()
                    with page.expect_response(lambda r:r.request.method=='POST' and r.url.startswith(url+BASE+'/'),timeout=timeout) as pending:
                        page.locator('[data-action='+action+']').click()
                    response=pending.value
                    # Refresh enables only after response JSON and UI readbacks complete.
                    ready(timeout)
                    report['active_operation']=None;save()
                    if not expect_error:need(response.status==200,'UI_MUTATION_FAILED_'+action);expect(page.locator('.lg-error')).to_have_count(0)
                    return response
                def fill(selector,value):
                    page.locator(selector).fill(str(value));page.get_by_role('heading',name='Cognitive logistics',exact=True).click()
                def state_facts(eid):return fingerprint(api('/episodes/'+eid))
                def global_facts():
                    status=api('/status')
                    return {'decisions':status['decisions'],'acquisition_spent':status['acquisition_spent'],
                        'active_model_id':status['active_model_id'],'models_sha256':sha(api('/models')),'experiments_sha256':sha(api('/experiments'))}
                page.goto(url+'/#logistics',wait_until='domcontentloaded')
                if not previous:
                    expect(page.locator('#login-dialog')).to_be_visible();page.locator('#pairing-token').fill(TOKEN)
                    page.get_by_role('button',name='Connect',exact=True).click();expect(page.locator('#login-dialog')).not_to_be_visible()
                expect(page.get_by_role('heading',name='Cognitive logistics',exact=True)).to_be_visible();ready()
                check('SIMULATION_BANNER_VISIBLE',page.get_by_text('SIMULATION · SYNTHETIC COGNITIVE LOGISTICS',exact=True).is_visible())
                build=read('/dragon/api/v1/system')['build'];report['backend_build']=build
                check('BACKEND_SOURCE_COMPONENT_MATCH',build.get('source_sha')==expected and build.get('component_version')==VERSION and build.get('source_dirty') is False)
                live=read('/dragon/api/v1/health/live');health=read('/dragon/api/v1/health/ready')
                report['installation']=live.get('installation');report['health']=health
                check('AUTHENTICATED_APPLICATION_READY',live.get('product')=='DRAGONHYDRA CORE NEXT' and health.get('status')=='ready' and health.get('backend')=='sqlite' and health.get('source_sha')==expected)
                if (source/'GENESIS62-BUILD.json').exists():check('SEALED_PAYLOAD_BACKEND_VERIFIED',identity.get('payload_verified') is True and build.get('payload_verified') is True)
                report['served_ui_sha256']={}
                for name in ASSETS:
                    response=context.request.get(url+'/'+name,max_redirects=0)
                    actual=response.body();local=ordinary(source/'src/dragonhydra/resources/web'/name).read_bytes()
                    check('SERVED_'+name,response.status==200 and actual==local);report['served_ui_sha256'][name]=hashlib.sha256(actual).hexdigest()
                if previous:
                    check('RESTART_SERVED_BYTES_MATCH',report['served_ui_sha256']==previous['served_ui_sha256'])
                    for alias,item in previous['retained']['episodes'].items():
                        select_episode(item['episode_id']);check('RETAINED_'+alias.upper(),state_facts(item['episode_id'])==item['fingerprint'])
                    check('RETAINED_GLOBAL_MODEL_BUDGET_COUNTS',global_facts()==previous['retained']['global'])
                    report['retained']=previous['retained'];select_episode(previous['primary_episode_id'])
                    check('RESUME_HAS_ZERO_MUTATING_REQUESTS',not report['mutating_requests'])
                else:
                    ids_before={e['episode_id'] for e in api('/episodes')['items']}
                    page.locator('#lg-universe').select_option('stable');page.locator('#lg-demand-mode').select_option('lost_sales')
                    fill('#lg-seed',400042);fill('#lg-duration-days',60);fill('#lg-information-budget',10)
                    click('logistics-create');main_id=page.locator('#lg-episode').input_value();view=api('/episodes/'+main_id)
                    check('UI_CREATED_FRESH_CANONICAL_EPISODE',main_id not in ids_before and view['snapshot']['day']==28 and not view['decisions'])
                    for name in PANELS:check('PANEL_'+name.upper(),page.locator('#logistics-'+name).count()==1)
                    check('INVENTORY_ATP_POSITION_CONSERVATION',inventory_valid(view))
                    for location,skus in view['snapshot']['inventory']['by_location'].items():
                        for sku,row in skus.items():
                            cells=page.locator('#logistics-inventory tbody tr').filter(has_text=location).filter(has_text=sku).locator('td').all_text_contents()
                            numbers=[float(x.replace(',','')) for x in cells[2:]]
                            check('ACTUAL_INVENTORY_ROW_'+location,numbers==[row[k] for k in ('on_hand','reserved','atp','on_order','in_transit','backorder','inventory_position','capacity')])
                    page.locator('#lg-inventory-policy').select_option('order_up_to');page.locator('#lg-acquisition-policy').select_option('none')
                    click('logistics-decide');view=api('/episodes/'+main_id);none=view['decisions'][-1]
                    orders={r['order_id']:r for r in view['snapshot']['inventory']['orders']}
                    check('NONE_ACQUISITION_WITH_REAL_REPLENISHMENT',not none['acquisitions'] and len(none['shipments'])>0 and all(orders[s['shipment_id']].get('ordered_qty',orders[s['shipment_id']].get('qty'))==s['quantity']>0 for s in none['shipments']))
                    check('NONE_PHYSICAL_STATE_VALID',inventory_valid(view))
                    before_day=view['snapshot']['day'];fill('#lg-advance-days',1);click('logistics-advance');view=api('/episodes/'+main_id)
                    check('EXPLICIT_DAY_ADVANCE',view['snapshot']['day']==before_day+1 and inventory_valid(view))
                    check('ACTUAL_FORECAST_AND_SEVEN_COST_COMPONENTS',set(view['current_forecasts'])=={'retail_a','retail_b'} and set(view['metrics']['costs'])==set(COSTS) and all(f['horizon']==5 and type(f['mean']) in (int,float) and math.isfinite(f['mean']) for f in view['current_forecasts'].values()))
                    for location,forecast in view['current_forecasts'].items():
                        title=location.replace('_',' ').title()
                        card=page.locator('#logistics-demand .lg-card').filter(has=page.get_by_role('heading',name=title,exact=True))
                        cells=card.locator('table').first.locator('tbody tr').first.locator('td').all_text_contents()
                        values=[float(x.replace(',','')) for x in cells[:4]]
                        check('DISPLAYED_FORECAST_'+location,all(math.isclose(a,b,abs_tol=1e-6,rel_tol=0) for a,b in zip(values,[forecast['horizon'],forecast['mean'],forecast['daily_mean'],forecast['variance']])) and cells[4]==forecast['method'])
                    for category,cost in view['metrics']['costs'].items():
                        cells=page.locator('#logistics-analytics tbody tr').filter(has_text=category).locator('td').all_text_contents()
                        check('DISPLAYED_COST_'+category,bool(cells) and math.isclose(float(cells[-1].replace(',','')),cost,abs_tol=1e-6,rel_tol=0))
                    check('ACTUAL_NETWORK_TOPOLOGY_DISPLAYED',page.locator('#logistics-network .lg-node').count()==len(view['network']['nodes']) and page.locator('#logistics-network .lg-edge').count()==len(view['network']['edges']))
                    before=view;before_count=len(view['decisions']);page.locator('#lg-acquisition-policy').select_option('all');click('logistics-decide');view=api('/episodes/'+main_id);all_plan=view['decisions'][-1]
                    check('ALL_ONE_EXPLICIT_PLAN_AND_PRICED_SUBSET',len(view['decisions'])==before_count+1 and acquisition_valid(all_plan,before) and {r['category'] for r in all_plan['acquisitions']}=={r['category'] for r in before['snapshot']['candidates'] if r['availability']=='AVAILABLE'})
                    for method in ('compare_methods','bounded_method_search','counterfactual'):
                        page.locator('#lg-analysis-method').select_option(method);click('logistics-analyze');analysis=api('/episodes/'+main_id)['analyses'][-1]
                        check('ACTUAL_BOUNDED_ANALYSIS_'+method,analysis['method']==method and analysis['status']=='COMPLETED' and analysis['original_unchanged'] is True and analysis['computation_units']>0 and bool(analysis.get('hypotheses')) and all('HYPOTHESIS' in h.get('classification','') for h in analysis['hypotheses']))
                    fill('#lg-seed',400043);fill('#lg-information-budget',0);click('logistics-create');zero_id=page.locator('#lg-episode').input_value();zero=api('/episodes/'+zero_id)
                    page.locator('#lg-acquisition-policy').select_option('none');click('logistics-decide');zero=api('/episodes/'+zero_id)
                    page.locator('#lg-acquisition-policy').select_option('all');click('logistics-decide');zero=api('/episodes/'+zero_id)
                    check('ZERO_BUDGET_NONE_AND_ALL_EMPTY_SUBSETS',zero['snapshot']['budget_remaining']==0 and all(not d['acquisitions'] for d in zero['decisions']) and inventory_valid(zero))
                    facts=global_facts();episode_count=len(api('/episodes')['items']);negative=[]
                    for body in ({'budget':-1},{'budget':101},{'days':121},{'universe':'LIVE'},{'actual_demand':[1]}):
                        response=context.request.post(url+BASE+'/episodes',data=body,max_redirects=0);negative.append(response.status)
                        report['mutating_requests'].append({'path':BASE+'/episodes','method':'POST','negative_probe':True,'status':response.status})
                    check('INVALID_API_INPUTS_REJECTED_WITHOUT_DOMAIN_DELTA',negative==[422]*5 and len(api('/episodes')['items'])==episode_count and global_facts()==facts)
                    fill('#lg-information-budget',-1);expect(page.locator('.lg-error')).to_contain_text('Invalid');check('UI_INVALID_BUDGET_VISIBLE',len(api('/episodes')['items'])==episode_count)
                    page.locator('[data-action=logistics-refresh]').click();ready();select_episode(main_id)
                    experiments_before={e['experiment_id'] for e in api('/experiments')['items']};fill('#lg-training-cases',10);fill('#lg-training-seed',42)
                    click('logistics-train',timeout=620000);experiments=api('/experiments')['items'];new=[e for e in experiments if e['experiment_id'] not in experiments_before]
                    check('ACTUAL_FROZEN_TRAINING_PREVIEW_CREATED',len(new)==1 and new[0]['model']['frozen'] is True and api('/status')['active_model_id']==new[0]['model']['model_id'])
                    experiment=new[0];study=experiment['report'];comparison=study['policy_comparison']
                    check('PREVIEW_SCOPE_AND_NINE_ARMS_HONEST',len(comparison)==9 and study['evaluation_cases_per_family']==2 and study['final_test_root_groups']==2 and study['small_sample'] is True and 'preview' in study['scope'].lower())
                    comparison_table=page.locator('#logistics-analytics table').filter(has=page.get_by_role('columnheader',name='Inventory policy',exact=True))
                    displayed=comparison_table.locator('tbody tr')
                    check('POLICY_COMPARISON_ACTUALLY_DISPLAYED',displayed.count()==9 and all(
                        displayed.nth(i).locator('td').all_text_contents()[:2]==[r['inventory_policy'],r['acquisition_policy']]
                        for i,r in enumerate(comparison)))
                    model=experiment['model'];check('FROZEN_MODEL_AND_PRIOR_NEGATIVE_RESULT',model['frozen'] is True and 'NO_ESTABLISHED' in model.get('prior_genesis61_result','') and study.get('net_decision_success','').startswith('NOT_ESTABLISHED'))
                    models_details=page.locator('#logistics-analytics details').filter(has=page.get_by_text('Actual retained frozen models',exact=True))
                    models_details.locator('summary').click();expect(models_details.locator('pre')).to_be_visible()
                    check('FROZEN_MODEL_ID_VISIBLE',model['model_id'] in models_details.locator('pre').inner_text())
                    report_details=page.locator('#logistics-analytics details').filter(has=page.get_by_text('Actual training, split, comparison and limitation report',exact=True))
                    report_details.locator('summary').click();expect(report_details.locator('pre')).to_be_visible()
                    check('PREVIEW_AND_NO_SUPERIORITY_VISIBLE','NOT_ESTABLISHED' in report_details.locator('pre').inner_text() and 'Dashboard preview' in report_details.locator('pre').inner_text())
                    before=state_facts(main_id);page.locator('#lg-inventory-policy').select_option('reorder_point');page.locator('#lg-acquisition-policy').select_option('learned')
                    response=click('logistics-decide',expect_error=True);expect(page.locator('.lg-error')).to_be_visible();code=response.json().get('error',{}).get('code','')
                    check('UNSUPPORTED_LEARNED_CONTEXT_VISIBLE_NO_DELTA',response.status in (400,409) and 'CONTEXT' in code and state_facts(main_id)==before)
                    fill('#lg-seed',400044);fill('#lg-information-budget',10);click('logistics-create');learned_id=page.locator('#lg-episode').input_value()
                    page.locator('#lg-inventory-policy').select_option('order_up_to');page.locator('#lg-acquisition-policy').select_option('learned');click('logistics-decide')
                    learned_view=api('/episodes/'+learned_id);learned=learned_view['decisions'][-1]
                    check('LEARNED_PLAN_REAL_FROZEN_MODEL_BOUND',learned['model_id']==model['model_id'] and all(a['action'] in ('ACQUIRE','DEFER','IGNORE','DO_NOTHING') for a in learned['actions']))
                    report['learned_actions']=[{'category':a.get('category'),'action':a['action'],'estimated_value':a.get('estimated_value'),'reason':a.get('reason')} for a in learned['actions']]
                    report['learned_positive_information_required']=False
                    select_episode(main_id);before=state_facts(main_id);global_before=global_facts();page.locator('[data-action=logistics-refresh]').click();ready()
                    check('REFRESH_IS_DOMAIN_PASSIVE',state_facts(main_id)==before and global_facts()==global_before)
                    old_future=read('/dragon/api/v1/future/episodes');old_realtime=read('/dragon/api/v1/realtime/matches')
                    page.goto(url+'/#future');expect(page.get_by_role('heading',name='Future relevance research',exact=True)).to_be_visible();expect(page.locator('[data-action=future-refresh]')).to_be_enabled()
                    page.goto(url+'/#research');expect(page.get_by_role('heading',name='Realtime research',exact=True)).to_be_visible()
                    check('OLDER_PAGES_PASSIVE_NAVIGATION_PRESERVED',sha(read('/dragon/api/v1/future/episodes'))==sha(old_future) and sha(read('/dragon/api/v1/realtime/matches'))==sha(old_realtime))
                    page.goto(url+'/#logistics');ready();select_episode(main_id)
                    report['primary_episode_id']=main_id
                    report['retained']={'episodes':{name:{'episode_id':eid,'fingerprint':state_facts(eid)} for name,eid in (('main',main_id),('zero_budget',zero_id),('learned',learned_id))},'global':global_facts()}
                    report['preview']={'experiment_id':experiment['experiment_id'],'model_id':model['model_id'],'scope':study['scope'],'policy_rows':len(comparison),'small_sample':study['small_sample']}
                if previous:report['primary_episode_id']=previous['primary_episode_id']
                for name in PANELS:
                    page.locator('#logistics-'+name).scroll_into_view_if_needed();page.screenshot(path=str(output/(name+'.png')),full_page=False)
                page.evaluate('window.scrollTo(0,0)');page.screenshot(path=str(output/'workspace.png'),full_page=False)
                page.set_viewport_size({'width':520,'height':900});page.screenshot(path=str(output/'narrow.png'),full_page=False)
                check('NARROW_LAYOUT_NO_DOCUMENT_OVERFLOW',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                check('NO_PAGE_ERRORS',not report['page_errors']);check('NO_EXTERNAL_PAGE_REQUESTS',not report['external_requests_blocked'])
                if previous:check('READ_ONLY_RESUME_NO_MUTATION',not report['mutating_requests'])
                context.close()
            finally:
                browser.close();report['browser_closed']=True;save()
        report['status']='PASS';report['completed_at']=datetime.now(timezone.utc).isoformat();save()
    except BaseException as error:
        report['status']='FAILED';report['failure']=f'{type(error).__name__}: {diagnostic(error)}';save();raise
    finally:
        report['evidence_files']=[{'name':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.iterdir()) if p.is_file() and p.name!='BROWSER.json' and not p.name.startswith('BROWSER.tmp-')]
        save()
    print(json.dumps({'status':report['status'],'checks':len(report['checks']),'mode':report['mode'],'receipt':str(output/'BROWSER.json')}));return 0

if __name__=='__main__':raise SystemExit(main())
