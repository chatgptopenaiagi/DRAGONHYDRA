"""Server identity guards use temporary profiles and never touch a service."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from dragonhydra.installation_profile import load_binding, isolated_environment


class ServerProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.lab=Path(self.tmp.name)
        identifier='core-next-'+'a'*32
        self.root=self.lab/'profiles'/identifier;self.root.mkdir(parents=True)
        self.path=self.root/'installation-profile.json'
        self.profile=dict(schema_version=1,product='DRAGONHYDRA CORE NEXT',edition='CORE NEXT',installation_id=identifier,
            environment_id='candidate',lab_root=str(self.lab),install_root=str(self.root/'application'),state_root=str(self.root/'state'),
            browser_user_data=str(self.root/'browser'),ports=dict(api=18810,web=18811,database=18812),copy_credentials=False,
            provider_schedules='disabled',service_name='DragonhydraCoreNextcandidate'+'a'*12,source_commit='1'*40)
        self.save()

    def save(self):self.path.write_text(json.dumps(self.profile))

    def test_explicit_bound_profile(self):
        profile,state=load_binding(profile_path=self.path,lab_root=self.lab)
        self.assertEqual(state,(self.root/'state'/'kernel').resolve())
        self.assertEqual(profile['installation_id'],self.profile['installation_id'])

    def test_missing_profile_does_not_fall_back(self):
        with self.assertRaisesRegex(ValueError,'PROFILE_REQUIRED'):load_binding(lab_root=self.lab)

    def test_original_credential_environment_is_not_inherited(self):
        original={'PATH':'unchanged','DRAGONHYDRA_LOCAL_AI_URL':'old-instance',
            'DRAGONHYDRA_LOCAL_AI_KEY':'old-fixture','DRAGONHYDRA_EXAMPLE_KEY':'old-provider-fixture'}
        self.assertEqual(isolated_environment(original),{'PATH':'unchanged'})
        self.assertEqual(original['DRAGONHYDRA_LOCAL_AI_KEY'],'old-fixture')

    def test_only_explicit_candidate_namespace_binds_existing_adapters(self):
        original={'PATH':'unchanged','DRAGONHYDRA_LOCAL_AI_KEY':'old-fixture',
            'DRAGONHYDRA_CORE_NEXT_LOCAL_AI_KEY':'candidate-fixture'}
        self.assertEqual(isolated_environment(original),{'PATH':'unchanged','DRAGONHYDRA_LOCAL_AI_KEY':'candidate-fixture'})

    def test_state_and_path_escape_rejected(self):
        for state in [self.lab.parent/'original',self.root/'different-state']:
            with self.subTest(state=state),self.assertRaises(ValueError):load_binding(state,self.path,lab_root=self.lab)
        self.profile['install_root']=str(self.lab.parent/'original');self.save()
        with self.assertRaises(ValueError):load_binding(profile_path=self.path,lab_root=self.lab)

    def test_port_and_service_identities_rejected(self):
        original=copy.deepcopy(self.profile)
        for field,value in [('ports',dict(api=18744,web=18811,database=18812)),('service_name','DragonhydraWorkstation')]:
            self.profile=copy.deepcopy(original);self.profile[field]=value;self.save()
            with self.subTest(field=field),self.assertRaises(ValueError):load_binding(profile_path=self.path,lab_root=self.lab)

    def test_persisted_identity_mismatch_rejected(self):
        state=self.root/'state'/'kernel';state.mkdir(parents=True)
        identity={k:self.profile[k] for k in ['installation_id','environment_id','product','edition']}
        identity['profile_path']=str(self.path);identity['installation_id']='other'
        (state/'product.json').write_text(json.dumps(identity))
        with self.assertRaisesRegex(ValueError,'PERSISTED_IDENTITY'):load_binding(state,lab_root=self.lab)

    def test_linked_state_path_rejected(self):
        destination=self.lab/'outside';destination.mkdir()
        link=self.root/'state'
        try:link.symlink_to(destination,target_is_directory=True)
        except OSError as e:self.skipTest(str(e))
        with self.assertRaisesRegex(ValueError,'REPARSE'):load_binding(profile_path=self.path,lab_root=self.lab)


if __name__=='__main__':unittest.main()
