"""Controlled retained/parser fixtures for reconstructed standings; never live sports proof."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import importlib.util
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[2]
_lab_spec=importlib.util.spec_from_file_location('registered_fixture_release',ROOT/'scripts/core_next/release.py')
_lab_release=importlib.util.module_from_spec(_lab_spec)
_lab_spec.loader.exec_module(_lab_release)
LAB=_lab_release.canonical_lab(ROOT)
sys.path.insert(0,str(ROOT/'src'))
from dragonhydra import public_results
from dragonhydra.kernel.engines import DataEngine
from dragonhydra.connectors import football
from dragonhydra.connectors.core import Document


class FixtureTransport:
    def __init__(self,document): self.document=document
    def get(self,*args,**kwargs): return self.document


class StandingsSemanticsTests(unittest.TestCase):
    def setUp(self):
        lab=LAB/'tests';lab.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='standings-semantics-',dir=lab)
        self.addCleanup(self.temp.cleanup)
        self.database=Path(self.temp.name)/'synthetic.sqlite3'
        self.engine=DataEngine.__new__(DataEngine)
        self.engine.connect=lambda:sqlite3.connect(self.database)
        self.engine.db_path=self.database
        self.engine.clock=lambda:'2099-01-01T00:00:00Z'
        self.engine.connector_store=SimpleNamespace(rows=lambda **kwargs:[])
        with closing(self.engine.connect()) as db: public_results._schema(db);db.commit()
        self.raw=json.dumps({'name':'Synthetic league 2026/27','matches':[
            {'date':'2026-01-01','team1':'A','team2':'B','score':{'ft':[2,1],'et':[8,9],'p':[0,5]}},
            {'date':'2026-01-02','team1':'B','team2':'A','score':{'ft':[0,0],'et':[6,7],'p':[1,4]}},
            {'date':'2026-01-03','team1':'A','team2':'C','score':{'et':[7,0],'p':[4,1]}}]}).encode()
        self.ingest(self.raw,'synthetic-league','capture-1')

    def ingest(self,raw,source_id,acquisition):
        with closing(self.engine.connect()) as db:
            return public_results.ingest_bytes(db,raw,source_id=source_id,source_url='https://example.invalid/synthetic-standings',acquisition_id=acquisition)

    def selected(self):
        row=next(row for row in self.engine.rows() if row['source_id']=='synthetic-league')
        return self.engine.standings(self.engine.competition_id(row))

    def test_competition_and_season_are_scoped_and_duplicate_captures_do_not_double_count(self):
        self.ingest(self.raw,'synthetic-league','capture-1')
        self.ingest(self.raw,'synthetic-league','capture-2')
        for name,source in [('Synthetic league 2027/28','synthetic-next-season'),('Other competition 2026/27','synthetic-other-league')]:
            raw=json.dumps({'name':name,'matches':[{'date':'2026-01-01','team1':'A','team2':'B','score':{'ft':[15,0]}}]}).encode()
            self.ingest(raw,source,'capture-other')
        result=self.selected();teams={r['team']:r for r in result['items']}
        self.assertEqual(result['season'],'2026/27')
        self.assertEqual(result['source_id'],'synthetic-league')
        self.assertEqual(sum(r['played'] for r in teams.values()),4)
        self.assertEqual(teams['A']['points'],4)
        self.assertEqual(teams['A']['goals_for'],2)

    def test_only_finished_full_time_scores_count_missing_is_not_zero_and_real_zero_survives(self):
        rows=self.engine.rows();present=[self.engine.present(r) for r in rows]
        self.assertEqual(sum(row['status']=='finished' for row in present),2)
        self.assertEqual(sum(row['status']=='scheduled' for row in present),1)
        self.assertEqual(next(r for r in present if r['event_date']=='2026-01-02')['score'],{'home':0,'away':0})
        self.assertIsNone(next(r for r in present if r['event_date']=='2026-01-03')['score'])
        result=self.selected();teams={r['team']:r for r in result['items']}
        self.assertEqual(teams['C']['played'],0)
        self.assertEqual(teams['A']['drawn'],1)
        self.assertEqual(sum(r['played'] for r in teams.values()),2*sum(r['status']=='finished' for r in present))
        self.assertEqual(sum(r['goals_for'] for r in teams.values()),3)
        self.assertEqual(sum(r['goals_for'] for r in teams.values()),sum(r['goals_against'] for r in teams.values()))
        for row in teams.values():
            self.assertEqual(row['played'],row['won']+row['drawn']+row['lost'])
            self.assertEqual(row['points'],3*row['won']+row['drawn'])

    def test_public_full_time_score_excludes_extra_time_and_shootout_and_declares_tie_break_limits(self):
        result=self.selected()
        self.assertFalse(result['official'])
        self.assertIn('full-time',result['label'])
        self.assertIn('tie-break',' '.join(result['limitations']))
        self.assertIn('not an official',' '.join(result['limitations']))
        teams={row['team']:row for row in result['items']}
        self.assertEqual((teams['A']['won'],teams['A']['drawn'],teams['A']['goals_for']),(1,1,2))

    def provider_record(self,status,goals,regulation):
        native=json.loads((ROOT/'tests/fixtures/connectors/football/api-football.json').read_text())
        row=native['response'][0]
        row['fixture']['status']['short']=status
        row['goals']={'home':goals[0],'away':goals[1]}
        row['score']['fulltime']={'home':regulation[0],'away':regulation[1]}
        row['league'].update(id=999,name='Synthetic cup',round='Final')
        body=json.dumps(native).encode()
        doc=Document('https://example.invalid/synthetic-api','https://example.invalid/synthetic-api',body,'2026-01-01T00:00:00Z',hashlib.sha256(body).hexdigest())
        record=football.fetch('api-football',{'league_id':999,'season':2025,'date_from':'2025-08-15','date_to':'2025-08-15'},'SYNTHETIC_TEST_ONLY',FixtureTransport(doc),lambda:None)[0]
        return {'provider':'api-football','source_record_id':record['source_record_id'],'record':record,
            'original_url':doc.url,'raw_sha256':doc.sha256,'id':'synthetic-provider-evidence',
            'received_at':doc.captured_at,'usable_at':doc.captured_at,'raw_reference':'synthetic-only'}

    def test_live_provider_score_does_not_become_a_completed_result(self):
        record=self.provider_record('2H',(0,1),(None,None))
        self.engine.connector_store=SimpleNamespace(rows=lambda **kwargs:[record])
        row=next(r for r in self.engine.rows() if r['source_id']=='api-football')
        self.assertIsNone(row['outcome'])
        table=self.engine.standings(self.engine.competition_id(row))
        self.assertEqual(sum(r['played'] for r in table['items']),0)

    def test_finished_provider_regulation_result_keeps_ordinary_points(self):
        record=self.provider_record('FT',(2,1),(2,1))
        self.engine.connector_store=SimpleNamespace(rows=lambda **kwargs:[record])
        row=next(r for r in self.engine.rows() if r['source_id']=='api-football')
        table=self.engine.standings(self.engine.competition_id(row))
        self.assertIsNot(table.get('available'),False)
        home=next(team for team in table['items'] if team['team']==record['record']['home'])
        self.assertEqual((home['played'],home['won'],home['points'],home['goals_for']),(1,1,3,2))

    def test_provider_duration_marked_extra_time_or_shootout_is_explicitly_unavailable(self):
        for duration in ('EXTRA_TIME','PENALTY_SHOOTOUT'):
            with self.subTest(duration=duration):
                native=json.loads((ROOT/'tests/fixtures/connectors/football/football-data-org.json').read_text())
                native['matches'][0]['score']['duration']=duration
                body=json.dumps(native).encode()
                doc=Document('https://example.invalid/synthetic-fdo','https://example.invalid/synthetic-fdo',body,'2026-01-01T00:00:00Z',hashlib.sha256(body).hexdigest())
                record=football.fetch('football-data-org',{'date_from':'2025-08-15','date_to':'2025-08-16'},'SYNTHETIC_TEST_ONLY',FixtureTransport(doc),lambda:None)[0]
                admitted={'provider':'football-data-org','source_record_id':record['source_record_id'],'record':record,
                    'original_url':doc.url,'raw_sha256':doc.sha256,'id':'synthetic-fdo-evidence',
                    'received_at':doc.captured_at,'usable_at':doc.captured_at,'raw_reference':'synthetic-only'}
                self.engine.connector_store=SimpleNamespace(rows=lambda **kwargs:[admitted])
                row=next(r for r in self.engine.rows() if r['source_id']=='football-data-org')
                table=self.engine.standings(self.engine.competition_id(row))
                self.assertIs(table.get('available'),False)
                self.assertTrue(table.get('reason') or table.get('label'))

    def test_provider_extra_time_and_penalty_winners_are_not_silently_full_time_league_wins(self):
        for status in ('AET','PEN'):
            with self.subTest(status=status):
                record=self.provider_record(status,(3,2),(1,1))
                self.engine.connector_store=SimpleNamespace(rows=lambda **kwargs:[record])
                row=next(r for r in self.engine.rows() if r['source_id']=='api-football')
                table=self.engine.standings(self.engine.competition_id(row))
                if table.get('available') is False:
                    self.assertTrue(table.get('reason') or table.get('label'))
                else:
                    self.assertTrue(all(r['drawn']==1 and r['won']==0 and r['goals_for']==1 for r in table['items']),
                        'Admitted provider final scores include ET/PEN while verified regulation is 1-1; refuse the unsupported table or use the regulation score.')


if __name__=='__main__':unittest.main()
