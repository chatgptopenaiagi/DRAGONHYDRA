"""Explicit host-only negative acceptance; never stops a database/service."""
from contextlib import closing
from pathlib import Path
import json
import secrets
import sqlite3
import time


def run(root, output):
    from fastapi.testclient import TestClient
    from dragonhydra.api import create_app
    from dragonhydra.product import Product
    root, output = Path(root).resolve(), Path(output).resolve()
    assert output.is_relative_to(root/'runtime/sqlserver-evidence') and not output.exists()
    output.mkdir(); state=output/'unavailable';state.mkdir()
    baseline=root.parent/'forensics/forecast-preservation-20261103/originals/operation/acceptance/workflow/private/before-reads.sqlite3'
    with closing(sqlite3.connect(baseline.as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(state/'core.sqlite3')) as b:a.backup(b)
    # A deliberately nonexistent LOCAL instance. No SQL/Windows service is changed.
    settings={'schema_version':1,'provider':'sqlserver','sqlserver':{
        'server':r'lpc:DESKTOP-44UK3UB\DRAGONHYDRA_NONEXISTENT_GENESIS7',
        'trust_server_certificate':True,'connection_timeout_seconds':1,'query_timeout_seconds':1}}
    (state/'research-storage.json').write_text(json.dumps(settings))
    app=create_app(state,local_token=secrets.token_urlsafe(48),start_worker=False)
    token=json.loads((state/'local-session.json').read_text())['token']
    start=time.monotonic()
    try:
        with TestClient(app,raise_server_exceptions=False) as client:
            client.headers['Authorization']='Bearer '+token
            health=client.get('/dragon/api/v1/research/storage')
            failed=client.get('/dragon/api/v1/research/archives/'+'a'*64)
            matches=client.get('/dragon/api/v1/matches?limit=1')
            checks={
                'real_driver_reports_unavailable':health.status_code==200 and health.json()['research']['ready'] is False,
                'failed_sql_read_is_503_not_false_success':failed.status_code==503 and failed.json()['error']['code']=='SQLSERVER_CONNECTION_FAILED',
                'canonical_sqlite_remains_readable':matches.status_code==200 and matches.json()['total']==760,
                'no_silent_provider_fallback':app.state.product.research.provider=='sqlserver' and not (state/'research.sqlite3').exists()}
    finally:app.state.jobs.close()
    independent=Product(output/'independent-sqlite')
    independent.research.initialize()
    checks['independently_selected_sqlite_still_operates']=independent.research.provider=='sqlite' and independent.research.health()['connected']
    receipt={'status':'PASS' if all(checks.values()) else 'FAIL','scope':'Real ODBC failure through in-process application API; no service disruption; explicit SQLite selection separate',
        'checks':checks,'elapsed_seconds':time.monotonic()-start,'diagnostic':health.json()['research'],'error':failed.json()['error']}
    (output/'verification.json').open('x').write(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    receipt=run(Path(__file__).resolve().parents[2],args.output)
    print(json.dumps(receipt));raise SystemExit(0 if receipt['status']=='PASS' else 1)
