"""Synthetic registry privacy/clock contracts; no providers, stores or services."""
from datetime import datetime,timedelta,timezone
import json
import unittest

from dragonhydra.kernel.contracts import ModuleDefinition
from dragonhydra.kernel.registry import ModuleRegistry


class Probe:
    contract_version='core-next.engine/1'
    def read(self):return []
    def write(self):return None
    def observe(self):return {'state':'READY','reason':'LOCAL_FIXTURE_OBSERVED','metrics':{}}
    def stop(self):pass


class RegistrySafetyTests(unittest.TestCase):
    def make(self):
        self.at=datetime(2026,11,2,tzinfo=timezone.utc)
        return ModuleRegistry((ModuleDefinition('sample','Sample','Fixture','Fixture'),),
            {'sample':Probe()},clock=lambda:self.at,installation_id='fixture-profile')

    def test_secret_or_unknown_metrics_never_escape_any_projection(self):
        r=self.make();r.record('sample','READY','LOCAL_FIXTURE_OBSERVED',metrics={
            'service_token':'SYNTHETIC_CANARY_NOT_A_CREDENTIAL','arbitrary_name':'SYNTHETIC_CANARY_NOT_A_CREDENTIAL',
            'configured':True,'cognitive_records':5})
        value=r.item('sample');text=json.dumps(value,allow_nan=False)
        self.assertNotIn('SYNTHETIC_CANARY',text)
        self.assertEqual(value['observation']['metrics'],{'configured':True,'cognitive_records':5})
        self.assertEqual(value['sanitized_metrics'],value['observation']['metrics'])

    def test_nonfinite_and_wrong_scalar_types_rejected_before_publish(self):
        r=self.make()
        for value in (float('nan'),float('inf'),float('-inf'),'pretend count',{},[]):
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):
                r.record('sample','READY','LOCAL_FIXTURE_OBSERVED',metrics={'cognitive_records':value})
        self.assertNotIn('sample',r.observations)

    def test_future_observation_cannot_stay_ready_when_clock_moves_back(self):
        r=self.make();r.start();self.at-=timedelta(seconds=1)
        self.assertNotEqual(r.item('sample')['state'],'READY')

    def test_failed_refresh_retains_actual_historical_success(self):
        r=self.make();r.start();success=r.item('sample')['last_success_at'];self.at+=timedelta(seconds=5)
        def failed():raise RuntimeError('SYNTHETIC private exception must not escape')
        r.engines['sample'].observe=failed;r.refresh('sample');value=r.item('sample')
        self.assertEqual(value['last_success_at'],success);self.assertEqual(value['state'],'DEGRADED')
        self.assertNotIn('private exception',json.dumps(value))

    def test_failed_or_empty_sample_does_not_renew_retained_count(self):
        r=self.make();r.record('sample','READY','LOCAL_FIXTURE_OBSERVED',metrics={'cognitive_records':5})
        self.at+=timedelta(seconds=10)
        r.record('sample','UNAVAILABLE','STORE_UNREADABLE',metrics={})
        current=r.item('sample')['observation']
        self.assertEqual(current['metrics'],{})
        self.assertIsNone(current['metrics_sampled_at'])

    def test_invalid_identifiers_and_configuration_references_rejected(self):
        for definition in (ModuleDefinition('../bad','Name','Fixture','Fixture'),
                           ModuleDefinition('sample','Name','Fixture','Fixture',configuration_requirements=('unknown-secret-reference',))):
            with self.subTest(identifier=definition.id),self.assertRaises(ValueError):
                ModuleRegistry((definition,),{definition.id:Probe()})

    def test_observation_has_bound_identity_scope_and_unique_ids(self):
        r=self.make();r.start();first=r.item('sample')['observation'];self.at+=timedelta(seconds=1);r.refresh('sample');second=r.item('sample')['observation']
        for value in (first,second):
            self.assertEqual(value['installation_id'],'fixture-profile')
            self.assertTrue(value.get('observation_id'))
            self.assertTrue(value.get('observer_identity'))
            self.assertTrue(value.get('verification_scope'))
        self.assertNotEqual(first['observation_id'],second['observation_id'])

    def test_operation_proof_does_not_verify_other_capabilities_or_renew_expired_evidence(self):
        self.at=datetime(2026,11,2,tzinfo=timezone.utc)
        definition=ModuleDefinition('sample','Sample','Fixture','Fixture',capabilities=('read','write'),
            supported_operations=('read','write'),capability_operations=(('read',('read',)),('write',('write',))))
        r=ModuleRegistry((definition,),{'sample':Probe()},clock=lambda:self.at,ttl_seconds=5)
        r.start();self.assertFalse(any(v['available'] for v in r.item('sample')['capability_status']))
        r.record_operation('sample','read','READY','EXPLICIT_READ')
        caps={v['id']:v for v in r.item('sample')['capability_status']}
        self.assertTrue(caps['read']['available']);self.assertFalse(caps['write']['available'])
        self.assertEqual(caps['read']['verified_operations'],['read'])
        self.at+=timedelta(seconds=6);r.refresh('sample')
        self.assertEqual(r.item('sample')['state'],'READY')
        self.assertFalse(any(v['available'] for v in r.item('sample')['capability_status']))
        r.record_operation('sample','read','UNAVAILABLE','EXPLICIT_READ_FAILED')
        self.assertFalse(r.item('sample')['capability_status'][0]['available'])

    def test_scoped_read_success_does_not_promote_absent_store_or_optional_model(self):
        self.at=datetime(2026,11,2,tzinfo=timezone.utc)
        definition=ModuleDefinition('sample','Sample','Fixture','Fixture',capabilities=('read','write'),
            supported_operations=('read','write'),capability_operations=(('read',('read',)),('write',('write',))))
        r=ModuleRegistry((definition,),{'sample':Probe()},clock=lambda:self.at)
        r.record('sample','NOT_CONFIGURED','STORE_ABSENT',metrics={'configured':False,'schema_complete':False})
        initial=r.item('sample')['observation']['observation_id']
        r.record_operation('sample','read','READY','EMPTY_READ_SUCCEEDED',update_module=False)
        value=r.item('sample');self.assertEqual(value['state'],'NOT_CONFIGURED')
        self.assertEqual(value['configuration_state'],'NOT_CONFIGURED')
        self.assertEqual(value['observation']['observation_id'],initial)
        self.assertTrue(value['capability_status'][0]['available'])
        self.assertFalse(value['capability_status'][1]['available'])
