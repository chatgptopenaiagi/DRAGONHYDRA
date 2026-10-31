"""Read-only Python3.14 DB-API parity against an already-created test schema.

Never creates schemas, updates canonical tables, runs write/rollback probes or
switches the backend. Protected credentials are read only in process memory.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import base64
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
TARGET=ROOT/'runtime/mysql-driver/site'
OUTPUT=ROOT/'build/connections/evidence/mysql-driver-proof'
SCHEMA='dragonhydra_migration_connections_20261031_a'
CONFIG=ROOT/'build/workstation/test-install/state data/workstation.json'
SQL_BUNDLE=ROOT/'runtime/migrations/connections-20261031-mariadb-sql-1'
SNAPSHOT=ROOT/'runtime/migrations/connections-20261031-prepare-1'
sys.path.insert(0,str(TARGET))
import pymysql


def canonical(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode('utf-8')


def ident(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z][a-z0-9_]*',value):
        raise ValueError('IDENTIFIER_NOT_ALLOWLISTED')
    return '`'+value+'`'


def safe_file(base, relative):
    result=(base/relative).resolve()
    if not result.is_relative_to(base.resolve()) or result.is_symlink():
        raise ValueError('SNAPSHOT_PATH_ESCAPE')
    return result


def compare_cell(expected, actual, column, storage_counts, driver_counts):
    kind=expected[0]
    storage_counts[kind]+=1
    driver_counts[type(actual).__name__]+=1
    if kind=='null':
        if actual is not None:raise ValueError('NULL_VALUE_MISMATCH')
    elif kind=='int':
        if type(actual) is not int or actual!=int(expected[1]):raise ValueError('INTEGER_VALUE_MISMATCH')
    elif kind=='float':
        if type(actual) is not float or struct.pack('>d',actual)!=struct.pack('>d',float.fromhex(expected[1])):
            raise ValueError('DOUBLE_BIT_MISMATCH')
    elif kind=='blob':
        if not isinstance(actual,bytes) or actual!=base64.b64decode(expected[1],validate=True):
            raise ValueError('BLOB_VALUE_MISMATCH')
    elif kind=='text':
        if column['binary_text']:
            if not isinstance(actual,bytes) or actual!=expected[1].encode('utf-8'):
                raise ValueError('BINARY_TEXT_VALUE_MISMATCH')
        elif not isinstance(actual,str) or actual!=expected[1]:
            raise ValueError('UNICODE_TEXT_VALUE_MISMATCH')
    else:raise ValueError('SOURCE_TYPE_UNSUPPORTED')


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    started=datetime.now(timezone.utc)
    record={'started_at':started.isoformat(),'passed':False,'database_writes':False,
            'schema_created':False,'backend_changed':False,'schema':SCHEMA,
            'python':sys.version,'python_executable':sys.executable,
            'driver':{'distribution':'PyMySQL','version':importlib.metadata.version('PyMySQL'),
                      'module':str(Path(pymysql.__file__).resolve()),'apilevel':pymysql.apilevel,
                      'paramstyle':pymysql.paramstyle,'threadsafety':pymysql.threadsafety},
            'queries':[],'checks':[],'tables':[],
            'scope':'Current Windows Python3.14 read-only driver proof; not an operational MariaDB kernel backend.'}
    connection=None
    sensitive=[]
    stage='input'
    try:
        if sys.version_info[:2]!=(3,14):raise ValueError('EXPECTED_VERIFIED_PYTHON314')
        if not Path(pymysql.__file__).resolve().is_relative_to(TARGET.resolve()):raise ValueError('DRIVER_TARGET_MISMATCH')
        cfg=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        sensitive=[value for key,value in cfg.items() if isinstance(value,str) and any(word in key.lower() for word in ('password','secret','token'))]
        if cfg['database_port']!=18741 or cfg['service_name']!='DragonhydraWorkstationTest':
            raise ValueError('PRIVATE_TEST_INSTANCE_MISMATCH')
        if cfg['kernel_backend']!='sqlite':raise ValueError('ORIGINAL_BACKEND_EXPECTED_SQLITE')
        mapping=json.loads((SQL_BUNDLE/'manifest.json').read_text())
        source=json.loads((SNAPSHOT/'manifest.json').read_text())
        if mapping['schema']!=SCHEMA or mapping['source_bundle']!=SNAPSHOT.relative_to(ROOT).as_posix():
            raise ValueError('RETAINED_SOURCE_SCOPE_MISMATCH')
        if mapping['source_manifest_sha256']!=source['manifest_sha256']:
            raise ValueError('SOURCE_MANIFEST_IDENTITY_MISMATCH')
        tables={table['name']:table for table in source['tables']}
        if len(tables)!=16 or sum(t['row_count'] for t in tables.values())!=3121:
            raise ValueError('SOURCE_EXPECTED_COUNTS_MISMATCH')
        for table in source['tables']:
            path=safe_file(SNAPSHOT,table['path'])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=table['sha256']:
                raise ValueError('SOURCE_ROWS_HASH_MISMATCH')
        record['checks'].append({'name':'Protected instance/source inputs and all16 source files verified','passed':True})
        stage='connection'
        connection=pymysql.connect(host='127.0.0.1',port=18741,user='root',password=cfg['root_password'],
            database=SCHEMA,charset='utf8mb4',use_unicode=True,connect_timeout=10,read_timeout=20,
            write_timeout=10,autocommit=False,local_infile=False)
        def read(query,params=None):
            if not query.lstrip().upper().startswith(('SELECT ','SHOW ')):
                raise ValueError('READ_ONLY_QUERY_REQUIRED')
            record['queries'].append(query)
            with connection.cursor() as cursor:
                cursor.execute(query,params)
                return cursor.fetchall()
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION TRANSACTION READ ONLY')
            cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT')
        record['transaction_setup']=['SET SESSION TRANSACTION READ ONLY','START TRANSACTION WITH CONSISTENT SNAPSHOT']
        server=read('SELECT @@version,@@port,@@datadir,@@bind_address,DATABASE(),@@session.tx_read_only,CURRENT_USER()')[0]
        expected_data=(Path(cfg['state_root'])/'mysql-data').resolve().as_posix().lower().rstrip('/')
        if not server[0].startswith('10.11.16-MariaDB') or int(server[1])!=18741 or str(server[2]).replace('\\','/').lower().rstrip('/')!=expected_data:
            raise ValueError('SERVER_IDENTITY_MISMATCH')
        if server[3]!='127.0.0.1' or server[4]!=SCHEMA or server[5]!=1:
            raise ValueError('READ_ONLY_LOOPBACK_SCOPE_MISMATCH')
        cipher=read("SHOW SESSION STATUS LIKE 'Ssl_cipher'")[0][1]
        record['server']={'version':server[0],'port':server[1],'datadir':server[2],'bind_address':server[3],
                          'database':server[4],'transaction_read_only':bool(server[5]),'authenticated_identity':server[6],
                          'transport':'loopback TCP','tls_cipher':cipher or None,'encrypted':bool(cipher)}
        target_tables={row[0] for row in read('SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE=%s ORDER BY TABLE_NAME',(SCHEMA,'BASE TABLE'))}
        if target_tables!=set(tables):raise ValueError('TARGET_TABLE_SET_MISMATCH')
        record['checks'].append({'name':'Actual MariaDB10.11.16/port/datadir/schema and read-only transaction verified','passed':True})
        stage='typed_rows'
        storage_counts=Counter();driver_counts=Counter(); total=0
        for table in mapping['mapping']['tables']:
            name=table['name'];original=tables[name]
            if [c['name'] for c in original['columns']]!=[c['name'] for c in table['columns']]:
                raise ValueError('SOURCE_COLUMN_ORDER_MISMATCH')
            query='SELECT '+','.join(ident(c['name']) for c in table['columns'])+' FROM '+ident(name)+' ORDER BY '+','.join(ident(k) for k in table['primary_key'])
            record['queries'].append(query)
            count=0;digest=hashlib.sha256();non_ascii=0
            with connection.cursor(pymysql.cursors.SSCursor) as cursor, safe_file(SNAPSHOT,original['path']).open('rb') as expected:
                cursor.execute(query)
                for line in expected:
                    actual=cursor.fetchone()
                    if actual is None:raise ValueError('TARGET_ROW_MISSING')
                    expected_row=json.loads(line);cells=expected_row['values']
                    if expected_row['row_sha256']!=hashlib.sha256(canonical(cells)).hexdigest():
                        raise ValueError('SOURCE_ROW_DIGEST_MISMATCH')
                    if len(actual)!=len(cells):raise ValueError('TARGET_ROW_WIDTH_MISMATCH')
                    for cell,value,column in zip(cells,actual,table['columns']):
                        compare_cell(cell,value,column,storage_counts,driver_counts)
                        if cell[0]=='text' and any(ord(char)>127 for char in cell[1]):non_ascii+=1
                    digest.update(bytes.fromhex(expected_row['row_sha256']));count+=1
                if cursor.fetchone() is not None:raise ValueError('TARGET_EXTRA_ROW')
            if count!=original['row_count'] or digest.hexdigest()!=original['rows_sha256']:
                raise ValueError('SOURCE_TABLE_COUNT_OR_DIGEST_MISMATCH')
            record['tables'].append({'name':name,'row_count':count,'source_typed_rows_sha256':digest.hexdigest(),
                                     'non_ascii_text_cells':non_ascii,'all_cells_equal':True})
            total+=count
        if total!=3121 or storage_counts['float']!=111 or storage_counts['blob']!=2:
            raise ValueError('NATIVE_STORAGE_COUNT_MISMATCH')
        record.update(total_rows=total,table_count=len(record['tables']),storage_classes=dict(storage_counts),
                      driver_return_types=dict(driver_counts),non_ascii_text_cells=sum(t['non_ascii_text_cells'] for t in record['tables']))
        record['checks'].append({'name':'All3121 rows match exact source values, including111doublebit patterns and2blobs','passed':True})
        # Demonstrate actual DB-API parameter handling using Unicode and NULL,
        # without creating a temporary table or modifying any row.
        sample='DRAGONHYDRA Équipe \U0001f409'
        values=read('SELECT %s,%s,%s,CAST(%s AS BINARY)',(sample,None,42,b'\x00\xffbinary'))[0]
        if values!=(sample,None,42,b'\x00\xffbinary'):
            raise ValueError('PARAMETER_NATIVE_VALUE_MISMATCH')
        record['checks'].append({'name':'Parameterized Unicode, NULL, integer and raw bytes round-trip without a write','passed':True})
        record['passed']=True
    except Exception as exc:
        # Transport/driver messages can contain credentials or arbitrary returned
        # text. Persist the error class/stage only, plus our fixed invariant codes.
        message=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
        for secret in sensitive:
            if secret:message=message.replace(secret,'[REDACTED]')
        record.update(failed_stage=stage,error=message,error_type=type(exc).__name__)
    finally:
        if connection is not None:
            connection.rollback();connection.close()
        record['finished_at']=datetime.now(timezone.utc).isoformat()
        record['seconds']=(datetime.now(timezone.utc)-started).total_seconds()
        (OUTPUT/'verification.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    summary={key:record.get(key) for key in ('passed','table_count','total_rows','storage_classes','non_ascii_text_cells','seconds','failed_stage','error')}
    print(json.dumps(summary,indent=2))
    return 0 if record['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
