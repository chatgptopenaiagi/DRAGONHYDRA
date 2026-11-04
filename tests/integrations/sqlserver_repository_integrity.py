"""Explicit owned-lab archive replay and immutable-trigger acceptance."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3

def run(root, profile_path, output):
    from dragonhydra.installation_profile import kernel_configuration
    from dragonhydra.product import Product
    from dragonhydra.research_storage.base import StorageError
    root, output=Path(root).resolve(),Path(output).resolve()
    assert output.is_relative_to(root/'runtime/sqlserver-evidence') and not output.exists()
    profile=json.loads(Path(profile_path).read_text())
    assert profile['installation_id']=='core-next-254b30ff0a0242b8bc90bd2fe789fbeb'
    state=Path(profile['state_root'])/'kernel'
    output.mkdir()
    p=Product(state,kernel_config=kernel_configuration(profile));repo=p.research
    assert repo.provider=='sqlserver' and repo.config.database=='DRAGONHYDRA_CORE_NEXT_SQL_LAB'
    archive_id='db1f5485749ecebfc019100e5ead5732699d1c9d99744cf1d7ad5de470d218e7'
    def sql_fingerprint():
        values={}
        with repo._reading() as c:
            for table in ('owner','migrations','archives','models','predictions','inputs','notes','note_audit'):
                rows=sorted(repr(tuple(r)) for r in c.execute('SELECT * FROM dbo.dh_research_'+table))
                values[table]={'rows':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
        return values
    before=sql_fingerprint();saved=repo.get(archive_id)
    replay=p.kernel.execute('memory','archive_forecast',saved['archive']['match_id'],saved['archive']['forecast_run_id'])
    checks={'actual_sql_repository_reuses_exact_archive':replay['archive_id']==archive_id and replay['storage']['duplicate'] is True}
    class UnexpectedMutationAllowed(Exception):pass
    denial=None
    try:
        with repo.transaction() as c:
            c.execute('UPDATE dbo.dh_research_archives SET home_name=? WHERE scope=? AND archive_id=?',
                'MUST NEVER COMMIT',profile['installation_id'],archive_id)
            # Even a missing trigger must never allow this test to commit.
            raise UnexpectedMutationAllowed()
    except StorageError as error:
        denial={'code':error.code,'sqlstate':error.sqlstate,'uncertain_write':error.uncertain_write}
    except UnexpectedMutationAllowed:pass
    checks['actual_sql_immutable_archive_update_denied']=bool(denial and denial['code']=='SQLSERVER_WRITE_FAILED' and denial['sqlstate']=='42000' and not denial['uncertain_write'])
    checks['replay_and_rejected_mutation_leave_every_sql_row_unchanged']=before==sql_fingerprint() and repo.get(archive_id)==saved
    receipt={'status':'PASS' if all(checks.values()) else 'FAIL','scope':'Owned existing SQL lab only; explicit application publication replay plus rolled-back immutable archive UPDATE test','checks':checks,'denial':denial,'replay':replay,'before':before}
    (output/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return receipt

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--profile',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    receipt=run(Path(__file__).resolve().parents[2],args.profile,args.output)
    print(json.dumps({k:v for k,v in receipt.items() if k!='before'}));raise SystemExit(0 if receipt['status']=='PASS' else 1)
