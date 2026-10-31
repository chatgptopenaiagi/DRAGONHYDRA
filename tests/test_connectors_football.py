"""Synthetic documented-schema fixtures; these tests are not live-account proof."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

from dragonhydra.connectors import football
from dragonhydra.connectors.core import ConnectorError, Document

FIXTURES=Path(__file__).parent/'fixtures'/'connectors'/'football'


def document(value, *, filename=None):
    body=(FIXTURES/filename).read_bytes() if filename else json.dumps(value).encode()
    return Document('https://example.invalid/fixture','https://example.invalid/fixture',body,
                    '2025-08-15T20:00:00Z',hashlib.sha256(body).hexdigest())


class Transport:
    def __init__(self,*responses):
        self.responses=list(responses); self.calls=[]

    def get(self,url,headers=None):
        self.calls.append((url,headers))
        response=self.responses.pop(0)
        if isinstance(response,Exception):
            raise response
        return response


class FootballConnectorTests(unittest.TestCase):
    def fetch(self,provider,transport,config=None,secret='synthetic-test-token'):
        return football.fetch(provider,config or {},secret,transport,lambda:None)

    def assert_code(self,code,function):
        with self.assertRaises(ConnectorError) as caught:
            function()
        self.assertEqual(caught.exception.code,code)
        return caught.exception

    def test_csv_results_statistics_and_bookmaker_phases(self):
        source=document(None,filename='archive.csv'); transport=Transport(source)
        rows=self.fetch('football-data-couk',transport)
        self.assertEqual(len(rows),2)
        first=rows[0]
        self.assertEqual((first['score_home'],first['score_away']),(2,1))
        self.assertEqual(first['statistics']['shots_home'],0)
        self.assertEqual(first['status'],'historical_result')
        self.assertEqual(first['season'],'2025/2026')
        self.assertIsNone(first['kickoff_utc'])
        self.assertEqual(first['source_local_time'],'20:00')
        self.assertTrue(all(o['quote_at'] is None for o in first['odds']))
        self.assertEqual({o['archive_phase'] for o in first['odds']},{'opening','closing'})
        self.assertFalse(any('Max' in o['provider'] or 'Avg' in o['provider'] for o in first['odds']))
        self.assertEqual({o['line'] for o in first['odds'] if o['market']=='total_goals'},{2.5})
        self.assertTrue(first['attributes']['source_warnings'])
        self.assertEqual(first['source_document_sha256'],source.sha256)
        self.assertEqual(rows[1]['status'],'scheduled')
        self.assertIsNone(rows[1]['score_home'])
        self.assertFalse(any(o['selection']=='home' for o in rows[1]['odds']))
        self.assertEqual(transport.calls[0][0],'https://www.football-data.co.uk/mmz4281/2526/E0.csv')

    def test_csv_identity_survives_rescheduling_and_collision_is_rejected(self):
        original=document(None,filename='archive.csv')
        changed=Document(original.url,original.url,original.body.replace(b'15/08/2025',b'17/08/2025'),original.captured_at,'changed')
        before=self.fetch('football-data-couk',Transport(original))[0]
        after=self.fetch('football-data-couk',Transport(changed))[0]
        self.assertEqual(before['source_record_id'],after['source_record_id'])
        lines=original.body.splitlines()
        duplicate=Document(original.url,original.url,b'\n'.join([lines[0],lines[1],lines[1]]),original.captured_at,'duplicate')
        self.assert_code('IDENTITY_COLLISION',lambda:self.fetch('football-data-couk',Transport(duplicate)))

    def test_csv_schema_and_html_fail_closed(self):
        html=document(None); html.body=b'<html>provider unavailable</html>'
        self.assert_code('UNEXPECTED_HTML',lambda:self.fetch('football-data-couk',Transport(html)))
        self.assert_code('SCHEMA_CHANGED',lambda:self.fetch('football-data-couk',Transport(document({'error':'not csv'}))))

    def test_csv_record_cap_is_explicit(self):
        rows=self.fetch('football-data-couk',Transport(document(None,filename='archive.csv')),{'max_records':1})
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]['attributes']['retrieval_truncated'])

    def test_missing_keys_never_call_http(self):
        for provider in set(football.SPECS)-{'football-data-couk'}:
            with self.subTest(provider=provider):
                transport=Transport()
                self.assert_code('NEEDS_KEY',lambda:self.fetch(provider,transport,secret=None))
                self.assertFalse(transport.calls)

    def test_config_rejects_urls_paths_and_unbounded_requests(self):
        for provider,config in [('football-data-couk',{'season':'../../secret'}),('football-data-couk',{'division':[]}),
                ('football-data-org',{'competition':'PL/../../'}),('football-data-org',{'date_from':'2025-01-01','date_to':'2026-01-01'}),
                ('api-football',{'max_pages':100}),('api-football',{'include_odds':'true'}),
                ('sportmonks',{'base_url':'http://127.0.0.1/'}),('the-odds-api',{'sport':'americanfootball_nfl'})]:
            with self.subTest(provider=provider,config=config):
                self.assert_code('INVALID_CONFIG',lambda:football.validate_config(provider,config))

    def test_football_data_org_header_and_normalization(self):
        transport=Transport(document(None,filename='football-data-org.json'))
        row=self.fetch('football-data-org',transport,{'date_from':'2025-08-15','date_to':'2025-08-16'})[0]
        self.assertEqual(row['source_record_id'],'440001')
        self.assertEqual(row['kickoff_utc'],'2025-08-15T19:00:00Z')
        self.assertEqual((row['score_home'],row['score_away']),(0,2))
        self.assertEqual(row['season'],'2025/2026')
        self.assertEqual(transport.calls[0][1],{'X-Auth-Token':'synthetic-test-token'})
        self.assertNotIn('synthetic-test-token',transport.calls[0][0])

    def test_api_football_ids_live_score_and_compatible_odds(self):
        transport=Transport(document(None,filename='api-football.json'),document(None,filename='api-football-odds.json'))
        row=self.fetch('api-football',transport,{'season':2025,'date_from':'2025-08-15','date_to':'2025-08-15','include_odds':True})[0]
        self.assertEqual(row['status'],'live')
        self.assertEqual(row['score_home'],0)
        self.assertEqual(row['kickoff_utc'],'2025-08-15T19:00:00Z')
        self.assertEqual([o['decimal_odds'] for o in row['odds']],[2.5,3.25])
        self.assertTrue(all(o['quote_at'] is None for o in row['odds']))
        query=parse_qs(urlsplit(transport.calls[1][0]).query)
        self.assertEqual(query['date'],['2025-08-15'])
        self.assertNotIn('from',query)
        self.assertEqual(transport.calls[0][1],{'x-apisports-key':'synthetic-test-token'})

    def test_api_football_http200_quota_is_failure(self):
        exc=self.assert_code('RATE_LIMITED',lambda:self.fetch('api-football',Transport(document({'errors':{'rateLimit':'synthetic-test-token exhausted'}}))))
        self.assertNotIn('synthetic-test-token',str(exc))

    def test_api_football_odds_page_bound_is_visible(self):
        odds=json.loads((FIXTURES/'api-football-odds.json').read_text())
        odds['paging']['total']=20
        transport=Transport(document(None,filename='api-football.json'),document(odds))
        row=self.fetch('api-football',transport,{'include_odds':True,'max_pages':1})[0]
        self.assertTrue(row['attributes']['odds_retrieval_truncated'])
        self.assertEqual(len(transport.calls),2)

    def test_odds_api_market_times_and_same_id_scores(self):
        scores=document([{'id':'test-event','completed':False,'scores':[{'name':'Test Home','score':'0'},{'name':'Test Away','score':'1'}]}])
        transport=Transport(document(None,filename='odds-api.json'),scores)
        row=self.fetch('the-odds-api',transport)[0]
        self.assertEqual(row['status'],'live')
        self.assertEqual((row['score_home'],row['score_away']),(0,1))
        self.assertEqual(len(row['odds']),5)
        self.assertEqual(row['odds'][0]['quote_at'],'2025-08-15T18:56:00Z')
        self.assertEqual(row['odds'][0]['state'],'in_play')
        self.assertEqual(row['attributes']['related_source_sha256'],[scores.sha256])
        self.assertNotIn('h2h_lay',{o['market'] for o in row['odds']})

    def test_odds_api_missing_scores_does_not_invent_live(self):
        transport=Transport(document(None,filename='odds-api.json'),ConnectorError('AUTH_REJECTED','Unavailable'))
        row=self.fetch('the-odds-api',transport)[0]
        self.assertEqual(row['status'],'scheduled')
        self.assertTrue(row['attributes']['status_unverified'])
        self.assertIsNone(row['score_home'])
        self.assertTrue(all(o['state']=='unknown' for o in row['odds']))

    def test_sportmonks_participant_roles_current_score_and_utc(self):
        transport=Transport(document(None,filename='sportmonks.json'))
        row=self.fetch('sportmonks',transport,{'include_odds':True})[0]
        self.assertEqual((row['home'],row['away']),('Test Home','Test Away'))
        self.assertEqual((row['score_home'],row['score_away']),(0,2))
        self.assertEqual(row['kickoff_utc'],'2025-08-15T19:00:00Z')
        self.assertEqual(row['status'],'historical_result')
        self.assertEqual(len(row['odds']),1)
        self.assertEqual(transport.calls[0][1],{'Authorization':'synthetic-test-token'})
        self.assertNotIn('synthetic-test-token',transport.calls[0][0])

    def test_sportmonks_bounds_do_not_follow_provider_next_url(self):
        data=json.loads((FIXTURES/'sportmonks.json').read_text())
        data['pagination']={'has_more':True,'next_page':'http://127.0.0.1/private'}
        transport=Transport(document(data))
        row=self.fetch('sportmonks',transport,{'max_pages':1})[0]
        self.assertTrue(row['attributes']['retrieval_truncated'])
        self.assertEqual(len(transport.calls),1)

    def test_transport_errors_are_safe_and_cooldowns_survive(self):
        raw=HTTPError('https://api.example/?apiKey=synthetic-test-token',429,'synthetic-test-token',None,None)
        self.addCleanup(raw.close)
        exc=self.assert_code('RATE_LIMITED',lambda:self.fetch('football-data-org',Transport(raw)))
        self.assertNotIn('synthetic-test-token',str(exc))
        self.assertEqual(exc.http_status,429)
        known=ConnectorError('RATE_LIMITED','Safe quota message',retry_after=17,http_status=429)
        self.assertEqual(self.assert_code('RATE_LIMITED',lambda:self.fetch('sportmonks',Transport(known))).retry_after,17)

    def test_cancellation_check_precedes_network(self):
        transport=Transport()
        def cancel():
            raise ConnectorError('CANCELLED','Cancelled')
        self.assert_code('CANCELLED',lambda:football.fetch('football-data-couk',{},None,transport,cancel))
        self.assertEqual(transport.calls,[])


if __name__=='__main__':
    unittest.main()
