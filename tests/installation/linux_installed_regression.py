"""Run an explicit existing core cohort against the installed R7 Python package.

Byte-identical test copies give their __file__-relative fixture writers an owned
scratch root. No checkout application directory is added to sys.path. This is a
bounded core portability cohort, not discovery of the full application suite.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import unittest
from unittest.mock import patch
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
PREFIX=Path('/opt/dragonhydra/api')
BOUNDARY=ROOT/'build/linux/native-kernel-20261031/installed-regression-7'
SCRATCH=ROOT/'runtime/scratch/linux-installed-regression-7'
VERSION='0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1'
SOURCE='4a2b97baec4fc278bc405a99a1d970f66e030be77b63d5f043f0faf295b39bc0'
ARTIFACT=ROOT/'dist/linux/native-kernel-20261031/r7/dragonhydra-api_0.4.0~alpha.1+dev20261031.r7.c77ddb3667f2-1_amd64.deb'
COHORT={
    'test_research.py':None,
    'test_public_results.py':None,
    'test_current_prior.py':None,
    'test_cognition_models.py':None,
    'test_cognition_adaptation.py':None,
    'test_cognition_evaluation.py':None,
    'test_cognition_memory.py':None,
    'test_cognition_research.py':None,
    'test_market_store.py':None,
    'test_football_data.py':None,
    'test_connector_provenance.py':('AcquisitionBindingTests',),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,default=BOUNDARY/'run-r1')
    args=parser.parse_args();work=args.work.resolve()
    if (platform.system()!='Linux' or sys.version_info[:2]!=(3,14) or not sys.flags.isolated
            or not sys.flags.no_site or not work.is_relative_to(BOUNDARY) or work==BOUNDARY or work.exists()):
        parser.error('Use Linux Python3.14 -I -S -B and a fresh owned evidence directory.')
    scratch=SCRATCH/work.name
    if scratch.exists():parser.error('Scratch run exists; retain it and choose another work directory.')
    work.mkdir(parents=True);scratch.mkdir(parents=True)
    temporary=scratch/'tmp';temporary.mkdir()
    os.environ['TMPDIR']=str(temporary);os.environ['TMP']=str(temporary);os.environ['TEMP']=str(temporary)
    tempfile.tempdir=str(temporary)
    for name in tuple(os.environ):
        if name.startswith('DRAGONHYDRA_') or name in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV','CONDA_PREFIX'):
            os.environ.pop(name,None)
    os.environ['PYTHONTZPATH']=''
    started=time.monotonic()
    report={'schema_version':1,'started_at':datetime.now(timezone.utc).isoformat(),'passed':False,
            'scope':'Explicit installed R7 core calculation, storage, provenance and bounded statistical-model unittest cohort; not the full suite or service/UI/provider-network test.',
            'command':[sys.executable,'-I','-S','-B','tests/installation/linux_installed_regression.py'],
            'environment':{'platform':platform.platform(),'python':sys.version,'isolated':bool(sys.flags.isolated),'no_site':bool(sys.flags.no_site),'timezone_override':''},
            'harness_sha256':digest(__file__),'checks':[],'source_tests':[],'network_calls_attempted':0,
            'subprocess_calls_attempted':0,'operational_database_modified':False,'service_operations':False,
            'excluded':[{'target':'CLI/forecast/cognition-command subprocess suites','reason':'Their launchers address checkout dragon.py and would not prove installed package isolation.'},
                        {'target':'test_market_signals.py and test_scenario.py','reason':'Original modules insert checkout src on sys.path; no test source is rewritten. Known negative-EV/Kelly case added explicitly in this harness.'},
                        {'target':'API/Joomla/Android/migration/release/network suites and AcquisitionAPITests','reason':'Outside bounded core scope, some require verification-only dependencies or external services.'},
                        {'target':'Newer StatsBomb context tests','reason':'Newer than frozen A4 application; unavailable contract is not advertised by R7.'},
                        {'target':'Provider vault write and model runtime/training suites','reason':'No vault mutation, model execution or large training in this cohort.'}]}
    installed_hashes={};original_hashes={};loaded={};result=None
    def check(name,**details):
        report['checks'].append({'name':name,'passed':True,**details})
        print(json.dumps({'passed':name,**details}),flush=True)
    def no_network(*args,**kwargs):
        report['network_calls_attempted']+=1;raise AssertionError('NETWORK_NOT_ALLOWED_IN_INSTALLED_CORE_COHORT')
    def no_subprocess(*args,**kwargs):
        report['subprocess_calls_attempted']+=1;raise AssertionError('SUBPROCESS_NOT_ALLOWED_IN_INSTALLED_CORE_COHORT')
    try:
        identity=json.loads((PREFIX/'BUILD-IDENTITY.json').read_text())
        assert identity['debian_version']==VERSION and identity['source_content_sha256']==SOURCE
        assert digest(ARTIFACT)=='02229cd57f01c36391df2a966f11f9275feed9f8aacdc8dc5640766439882605'
        manifest=json.loads((ROOT/'build/linux/native-kernel-20261031/build-7/PAYLOAD-MANIFEST.json').read_text())['files']
        for item in manifest:
            if item['path'].startswith('opt/dragonhydra/api/'):
                path=Path('/')/item['path']
                assert path.is_file() and not path.is_symlink() and path.stat().st_size==item['bytes'] and digest(path)==item['sha256'],'INSTALLED_PACKAGE_INPUT_DRIFT'
                installed_hashes[path]=item['sha256']
        site=PREFIX/'site-packages';sys.path.insert(0,str(site))
        import dragonhydra
        from dragonhydra.build_meta import info
        assert info()['source_content_sha256']==SOURCE and Path(dragonhydra.__file__).resolve().is_relative_to(site)
        check('Actual installed R7 identity and immutable private payload verified',files=len(installed_hashes),effective_source=SOURCE)
        mirror=scratch/'test-root'; testdir=mirror/'tests';testdir.mkdir(parents=True)
        (mirror/'runtime/scratch').mkdir(parents=True);(mirror/'examples').mkdir()
        fixture=ROOT/'examples/synthetic-market.json';original_hashes[fixture]=digest(fixture)
        (mirror/'examples/synthetic-market.json').write_bytes(fixture.read_bytes())
        sys.path.insert(0,str(testdir))
        suite=unittest.TestSuite();loader=unittest.TestLoader()
        for name,classes in COHORT.items():
            path=ROOT/'tests'/name;body=path.read_bytes();original_hashes[path]=hashlib.sha256(body).hexdigest()
            assert b'sys.path' not in body,'COHORT_MODULE_MODIFIES_IMPORT_PATH'
            copied=testdir/name;copied.write_bytes(body)
            assert digest(copied)==original_hashes[path]
            spec=importlib.util.spec_from_file_location(path.stem,copied);module=importlib.util.module_from_spec(spec)
            sys.modules[path.stem]=module;spec.loader.exec_module(module);loaded[path.stem]=module
            selected=loader.loadTestsFromModule(module) if classes is None else unittest.TestSuite(loader.loadTestsFromTestCase(getattr(module,c)) for c in classes)
            suite.addTests(selected)
            report['source_tests'].append({'path':path.relative_to(ROOT).as_posix(),'sha256':original_hashes[path],
                                           'classes':list(classes) if classes else 'all','cases':selected.countTestCases(),
                                           'execution_copy':copied.relative_to(ROOT).as_posix(),'byte_identical_copy':True})
        research_fixture=loaded['test_research'].ResearchTests
        class OfferedPriceRegression(unittest.TestCase):
            def test_probability_055_price_130_ev_minus0285_zero_long_only_kelly(self):
                fixture=research_fixture();fixture.setUp();fixture.quote['odds_original']='1.30'
                assessed=fixture.assess()
                self.assertEqual(Decimal(assessed['expected_net_return_per_unit']['value']),Decimal('-0.285'))
                self.assertEqual(Decimal(assessed['raw_kelly']['value']),Decimal('-0.95'))
                self.assertEqual(Decimal(assessed['fractional_capped_kelly']['value']),Decimal('0'))
        suite.addTests(loader.loadTestsFromTestCase(OfferedPriceRegression))
        def flatten(node):
            for entry in node:
                if isinstance(entry,unittest.TestSuite):yield from flatten(entry)
                else:yield entry
        cases=list(flatten(suite));case_ids=[case.id() for case in cases]
        assert len(case_ids)==len(set(case_ids))
        report['case_ids']=case_ids;report['unique_cases']=len(case_ids);report['existing_cases']=len(case_ids)-1
        report['additional_known_answer_cases']=1
        # Builtin file writes and SQLite connections must remain within these
        # owned scratch/evidence directories. Original tests/fixtures stay read-only.
        def ownership_guard(event,args):
            if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
                path,mode,flags=args
                writing=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and bool(flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_APPEND|os.O_TRUNC)))
                if writing:
                    resolved=Path(os.fsdecode(path)).resolve()
                    if not (resolved.is_relative_to(scratch) or resolved.is_relative_to(work)):
                        raise AssertionError('FILE_WRITE_OUTSIDE_OWNED_CORE_TEST_ROOT')
            elif event=='sqlite3.connect':
                name=str(args[0])
                if name!=':memory:' and not Path(name).resolve().is_relative_to(scratch):
                    raise AssertionError('DATABASE_OUTSIDE_OWNED_CORE_TEST_ROOT')
        sys.addaudithook(ownership_guard)
        class RecordedResult(unittest.TextTestResult):
            subtests=0
            def addSubTest(self,test,subtest,error):
                self.subtests+=1;super().addSubTest(test,subtest,error)
        with (work/'unittest.log').open('w') as log,ExitStack() as guards:
            for owner,name in ((urllib.request,'urlopen'),(urllib.request.OpenerDirector,'open'),
                               (socket,'create_connection'),(socket.socket,'connect'),(socket.socket,'connect_ex')):
                guards.enter_context(patch.object(owner,name,no_network))
            guards.enter_context(patch.object(subprocess,'run',no_subprocess))
            guards.enter_context(patch.object(subprocess,'Popen',no_subprocess))
            result=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=RecordedResult).run(suite)
        print((work/'unittest.log').read_text(),end='',flush=True)
        origins={}
        for name,module in tuple(sys.modules.items()):
            if name=='dragonhydra' or name.startswith('dragonhydra.'):
                path=Path(module.__file__).resolve();assert path.is_relative_to(site),'CHECKOUT_MODULE_LEAK'
                origins[name]=str(path)
        report['module_origins']=origins
        report['test_result']={'tests_run':result.testsRun,'passed':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                               'failures':[case.id() for case,_ in result.failures],'errors':[case.id() for case,_ in result.errors],
                               'skips':[{'case':case.id(),'reason':reason} for case,reason in result.skipped],
                               'subtest_outcomes_separate_not_added_to_case_count':result.subtests}
        assert result.testsRun==len(case_ids)
        originals_unchanged=all(digest(path)==expected for path,expected in original_hashes.items())
        installed_unchanged=all(digest(path)==expected for path,expected in installed_hashes.items())
        report['source_fingerprints_unchanged']=originals_unchanged
        report['installed_fingerprints_unchanged']=installed_unchanged
        assert originals_unchanged,'TEST_OR_FIXTURE_SOURCE_CHANGED_DURING_COHORT'
        assert installed_unchanged,'INSTALLED_PACKAGE_CHANGED_DURING_COHORT'
        assert report['network_calls_attempted']==report['subprocess_calls_attempted']==0
        check('All loaded application modules resolve inside actual installed prefix',modules=len(origins))
        check('Selected original tests/fixtures and installed bytes remain unchanged; no network/subprocess escaped')
        report['passed']=result.wasSuccessful()
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error),'line':traceback.extract_tb(error.__traceback__)[-1].lineno}
        (work/'traceback.log').write_text(traceback.format_exc())
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-started,3))
        report['exit_code']=0 if report['passed'] else 1
        (work/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'passed':report['passed'],'unique_cases':report.get('unique_cases'),
                          'result':report.get('test_result'),'seconds':report['elapsed_seconds'],
                          'error':report.get('error'),'evidence':(work/'verification.json').relative_to(ROOT).as_posix()}),flush=True)
    return report['exit_code']


if __name__=='__main__':
    raise SystemExit(main())
