"""Bounded source-native parsing and exact bound projection reconstruction."""
from contextlib import closing
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from uuid import UUID

from dragonhydra import source_context
from dragonhydra.connectors import statsbomb_context as binding, statsbomb_context_parser as parser
import test_statsbomb_context as fixtures


PARENT = {'native_identity':{'match_id':3869685,'competition_id':43,'season_id':106,
    'home_team_id':779,'away_team_id':771,'event_date':'2022-12-18'},
    'normalized_record':{'home':'Argentina','away':'France'}}
LINEUPS = [{'team_id':779,'team_name':'Argentina','lineup':[
    {'player_id':1001,'player_name':'Argentina Player','player_nickname':None,'jersey_number':10,
     'country':{'id':11,'name':'Argentina'},'positions':[{'position':'uninterpreted'}]}]},
    {'team_id':771,'team_name':'France','lineup':[{'player_id':2001,'player_name':'France Player'}]}]


def event(ordinal=1,**values):
    return {'id':str(UUID(int=ordinal)), 'index':ordinal,'type':{'id':18,'name':'Half Start'},**values}


EVENTS = [event(1),event(3,team={'id':779,'name':'Argentina'},player={'id':1001,'name':'Argentina Player'},
    period=1,timestamp='00:00:01.000',minute=0,second=1,type={'id':30,'name':'Pass'}),
    event(4,team={'id':771,'name':'France'},player={'id':2001,'name':'France Player'},period=2,
          type={'id':30,'name':'Pass'}),
    event(8,team={'id':779,'name':'Argentina'},period=1,type={'id':30,'name':'Pass'})]


def raw(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()


class NativeParserTests(unittest.TestCase):
    def parse(self,events=EVENTS,lineups=LINEUPS,parent=PARENT):
        return parser.parse(raw(events),raw(lineups),parent=parent)

    def test_optional_fields_absence_and_explicit_zero_preserved_without_inference(self):
        projection = self.parse()
        summary = projection['event_summary']
        self.assertEqual(summary['row_count'],4)
        self.assertEqual(summary['missing_fields'],{'team':1,'player':2,'period':1,'timestamp':3,'minute':3,'second':3})
        self.assertEqual(summary['counts_by_team_period_type'],[
            {'team_id':None,'period':None,'type_id':18,'count':1},
            {'team_id':771,'period':2,'type_id':30,'count':1},
            {'team_id':779,'period':1,'type_id':30,'count':2}])
        page = parser.event_page(raw(EVENTS),raw(LINEUPS),parent=PARENT)
        self.assertEqual(page['items'][0],EVENTS[0])
        self.assertEqual(page['items'][1]['minute'],0)
        self.assertNotIn('minute',page['items'][2])
        self.assertNotIn('player',page['items'][3])
        self.assertNotIn('team',page['items'][0])

    def test_native_array_order_indexes_with_gaps_and_relative_clocks_not_rewritten(self):
        rows = [EVENTS[3],EVENTS[0],EVENTS[1]]
        page = parser.event_page(raw(rows),raw(LINEUPS),parent=PARENT,offset=1,limit=1)
        self.assertEqual(page['items'],[EVENTS[0]])
        self.assertEqual(page['total'],3)
        self.assertEqual(page['offset'],1)
        self.assertEqual(page['parser_version'],parser.VERSION)

    def test_team_absent_with_rostered_player_stays_absent(self):
        rows = [event(player={'id':1001,'name':'Argentina Player'})]
        page = parser.event_page(raw(rows),raw(LINEUPS),parent=PARENT)
        self.assertNotIn('team',page['items'][0])
        self.assertEqual(self.parse(rows)['event_summary']['missing_fields']['team'],1)

    def test_source_squad_fields_only_no_starting_roles_or_sports_metrics(self):
        rows = [event(possession=999,shot={'statsbomb_xg':0.8},tactics={'formation':433})]
        projection = self.parse(rows)
        player = projection['squads'][0]['lineup'][0]
        self.assertEqual(player['country'],{'id':11,'name':'Argentina'})
        self.assertIsNone(player['player_nickname'])
        self.assertNotIn('positions',player)
        page = parser.event_page(raw(rows),raw(LINEUPS),parent=PARENT)
        self.assertEqual(page['items'],[event()])
        for key in ('score','winner','possession','xg','starting_roles','settlement'):
            self.assertNotIn(key,projection)

    def test_uuid_and_index_duplicates_and_noncanonical_case_rejected(self):
        for rows,code in (([event(),event()],'DUPLICATE_EVENT_IDENTITY'),
                          ([event(),event(2,index=1)],'DUPLICATE_EVENT_IDENTITY'),
                          ([event(id='ABCDEFAB-0000-0000-0000-000000000001')],'INVALID_EVENT_UUID'),
                          ([event(id='not-a-uuid')],'INVALID_EVENT_UUID')):
            with self.subTest(code=code),self.assertRaisesRegex(ValueError,code):
                self.parse(rows)

    def test_required_fields_and_present_optional_fields_use_exact_types(self):
        cases = [{'id':None},{'index':True},{'index':1.0},{'type':None},
                 {'period':None},{'period':0},{'period':True},{'period':6},
                 {'minute':True},{'minute':-1},{'second':60},{'second':None},
                 {'timestamp':None},{'timestamp':'2022-12-18T10:00:00Z'},
                 {'team':None},{'player':None},{'type':{'id':True,'name':'Pass'}}]
        for values in cases:
            with self.subTest(values=values),self.assertRaises(ValueError):
                self.parse([event(**values)])

    def test_native_team_player_roster_and_type_name_identity_consistency(self):
        cases = [[event(team={'id':999,'name':'Other'})],
                 [event(team={'id':779,'name':'France'})],
                 [event(player={'id':999,'name':'Unknown'})],
                 [event(player={'id':1001,'name':'Changed Name'})],
                 [event(team={'id':771,'name':'France'},player={'id':1001,'name':'Argentina Player'})],
                 [event(),event(2,type={'id':18,'name':'Changed Type'})]]
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                self.parse(rows)

    def test_squad_identity_duplicate_players_and_present_optional_types(self):
        cases = []
        wrong = deepcopy(LINEUPS); wrong[1]['team_id'] = 779; cases.append(wrong)
        wrong = deepcopy(LINEUPS); wrong[0]['team_name'] = 'Other'; cases.append(wrong)
        wrong = deepcopy(LINEUPS); wrong[1]['lineup'][0] = wrong[0]['lineup'][0]; cases.append(wrong)
        for values in ({'player_id':True},{'player_name':123},{'jersey_number':None},{'country':None},{'player_nickname':7}):
            wrong = deepcopy(LINEUPS); wrong[0]['lineup'][0].update(values); cases.append(wrong)
        for squads in cases:
            with self.subTest(squads=squads),self.assertRaises(ValueError):
                self.parse([],squads)
        for squads in ([],LINEUPS[:1],LINEUPS+[LINEUPS[0]]):
            with self.assertRaisesRegex(ValueError,'TWO_SQUADS_REQUIRED'):
                self.parse([],squads)

    def test_twenty_thousand_events_stay_compact_and_page_at_most_two_hundred(self):
        rows = [event(index) for index in range(1,20_001)]
        projection = self.parse(rows)
        self.assertEqual(projection['event_summary']['row_count'],20_000)
        self.assertLess(len(raw(projection)),4096)
        page = parser.event_page(raw(rows),raw(LINEUPS),parent=PARENT,offset=19_900)
        self.assertEqual(len(page['items']),100)
        self.assertEqual(page['items'][0]['index'],19_901)
        with self.assertRaisesRegex(ValueError,'EVENT_LIMIT'):
            self.parse(rows+[event(20_001)])
        with self.assertRaisesRegex(ValueError,'INVALID_PAGE'):
            parser.event_page(raw(rows),raw(LINEUPS),parent=PARENT,limit=201)

    def test_hundred_squad_entries_and_hard_resource_bounds(self):
        squads = deepcopy(LINEUPS)
        squads[0]['lineup'] = [{'player_id':index,'player_name':'Player '+str(index)} for index in range(1,101)]
        self.assertEqual(len(self.parse([],squads)['squads'][0]['lineup']),100)
        squads[0]['lineup'].append({'player_id':101,'player_name':'Extra'})
        with self.assertRaisesRegex(ValueError,'SQUAD_LIMIT'):
            self.parse([],squads)
        with patch.object(parser,'MAX_TYPES',1),self.assertRaisesRegex(ValueError,'EVENT_TYPE_LIMIT'):
            self.parse()
        with patch.object(parser,'MAX_PROJECTION_BYTES',10),self.assertRaisesRegex(ValueError,'PROJECTION_LIMIT'):
            self.parse()

    def test_invalid_finite_json_duplicate_keys_unicode_depth_and_huge_integer_fail_closed(self):
        bodies = [b'[{"id":1,"id":2}]',b'[NaN]',b'[1e999]',b'[Infinity]',b'["\xff"]',
                  b'["\\ud800"]',b'['*1000+b']'*1000,b'['+b'9'*5000+b']']
        for body in bodies:
            with self.subTest(prefix=body[:30]),self.assertRaisesRegex(ValueError,'STATSBOMB_PARSER_'):
                parser.parse(body,raw(LINEUPS),parent=PARENT)
        nested = {'ignored':[]}
        node = nested['ignored']
        for _ in range(70):
            node.append([]); node = node[0]
        with self.assertRaisesRegex(ValueError,'JSON_DEPTH_LIMIT'):
            self.parse([event(**nested)])

    def test_page_parameters_and_parent_selection_checked(self):
        for values in ({'offset':-1},{'offset':True},{'limit':0},{'limit':True},{'limit':201}):
            with self.subTest(values=values),self.assertRaisesRegex(ValueError,'INVALID_PAGE'):
                parser.event_page(raw(EVENTS),raw(LINEUPS),parent=PARENT,**values)
        wrong = deepcopy(PARENT); wrong['native_identity']['match_id'] = 3869686
        with self.assertRaisesRegex(ValueError,'PARENT_SELECTION_MISMATCH'):
            self.parse(parent=wrong)
        wrong['native_identity']['match_id'] = 3869685.0
        with self.assertRaisesRegex(ValueError,'PARENT_SELECTION_MISMATCH'):
            self.parse(parent=wrong)


class BoundParserTests(unittest.TestCase):
    readonly = fixtures.StatsBombContextTests.readonly
    document = fixtures.StatsBombContextTests.document
    update = fixtures.StatsBombContextTests.update

    def setUp(self):
        fixtures.StatsBombContextTests.setUp(self)
        documents = {'events':self.document(raw(EVENTS),binding.ROLE_URLS['events']),
                     'lineups':self.document(raw(LINEUPS),binding.ROLE_URLS['lineups'])}
        with closing(self.readonly()) as db:
            self.payload['documents'] = {role:binding.document_binding(db,self.raw,role,doc.acquisition_id)
                                         for role,doc in documents.items()}
        self.payload['parser_version'] = parser.VERSION
        self.payload['projection'] = parser.parse(raw(EVENTS),raw(LINEUPS),parent=self.parent)

    def test_full_callback_composes_exact_bindings_and_projection_with_once_verified_role_bodies(self):
        calls = []
        body = binding._body
        def counted(raw_dir,receipt,maximum):
            calls.append(receipt['id'])
            return body(raw_dir,receipt,maximum)
        statements = []
        with patch.object(binding,'_body',side_effect=counted),closing(self.readonly()) as db:
            db.set_trace_callback(statements.append)
            parser.make_validator(self.raw)(db,self.payload)
        for role in binding.ROLE_URLS:
            self.assertEqual(calls.count(self.payload['documents'][role]['id']),1)
        self.assertEqual(len(calls),4)
        self.assertTrue(all(sql.lstrip().upper().startswith('SELECT') for sql in statements))

    def test_projection_tamper_and_unexpected_parser_version_cannot_be_accepted(self):
        for values,code in (({'parser_version':'other/1'},'PARSER_VERSION_MISMATCH'),
                            ({'projection':{'invented':True}},'PROJECTION_RECONSTRUCTION_MISMATCH')):
            wrong = deepcopy(self.payload); wrong.update(values)
            with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,code):
                parser.make_validator(self.raw)(db,wrong)
        wrong = deepcopy(self.payload)
        wrong['projection']['event_summary']['row_count'] = 4.0
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PROJECTION_RECONSTRUCTION_MISMATCH'):
            parser.make_validator(self.raw)(db,wrong)

    def test_exact_parent_snapshot_numeric_types_cannot_silently_change(self):
        wrong = deepcopy(self.payload)
        wrong['parent']['native_identity']['match_id'] = 3869685.0
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PARENT_BINDING_MISMATCH'):
            parser.make_validator(self.raw)(db,wrong)

    def test_bound_read_page_reconstructs_projection_and_preserves_source_fields(self):
        with closing(self.readonly()) as db:
            page = parser.read_event_page(db,self.raw,self.payload,offset=1,limit=2)
        self.assertEqual(page['items'],EVENTS[1:3])
        wrong = deepcopy(self.payload)
        wrong['projection']['event_summary']['row_count'] = 0
        with closing(self.readonly()) as db,self.assertRaisesRegex(ValueError,'PROJECTION_RECONSTRUCTION_MISMATCH'):
            parser.read_event_page(db,self.raw,wrong)

    def test_immutable_context_uses_full_validator_and_same_payload_duplicate(self):
        validate = parser.make_validator(self.raw)
        first = source_context.append(self.path,self.payload,validate_dependencies=validate)
        second = source_context.append(self.path,self.payload,validate_dependencies=validate)
        self.assertEqual(first['record_id'],second['record_id'])
        self.assertTrue(second['duplicate'])
        result = source_context.latest(self.path,'statsbomb','3869685',validate_dependencies=validate)
        self.assertEqual(result['availability'],'available')
        self.assertEqual(result['item']['projection'],self.payload['projection'])


if __name__ == '__main__':
    unittest.main()
