import unittest
from dragonhydra.cognition import research


class CognitiveResearchTests(unittest.TestCase):
    def forecast(self):
        def model(home,draw,away):
            return {'available':True,'probabilities':{k:{'value':v} for k,v in
                    zip(('home','draw','away'),(home,draw,away))}}
        return {'decision_cutoff':'2026-01-01T00:00:00Z','target':{'evidence_id':'target'},
                'training_manifest':[{'evidence_id':'training','event_date':'2025-12-01'}],
                'configuration':{'evidence_id':'config'},'abstained':False,'research_tasks':[],
                'models':{'one':model(.5,.3,.2),'two':model(.3,.3,.4)}}

    def test_unknown_mapping_never_becomes_a_market_comparison(self):
        fictitious={'fixture_evidence_id':'target','mapping_verified':True,'evidence_id':'made-up'}
        result=research.assess(self.forecast(),[fictitious])
        self.assertEqual(result['matched_quote_evidence_ids'],[])
        self.assertIn('MATCHING_MARKET_QUOTES_UNAVAILABLE',{t['gap'] for t in result['research_tasks']})
        self.assertIn('NO_SCORED_OPERATIONAL_PREDICTIONS',{t['gap'] for t in result['research_tasks']})

    def test_model_disagreement_is_computed_and_linked(self):
        result=research.assess(self.forecast(),[],evaluated_predictions=1)
        self.assertAlmostEqual(result['model_disagreement']['home']['value'],.2)
        self.assertIn('training',result['model_disagreement']['home']['evidence_ids'])
        self.assertIn('HIGH_MODEL_DISAGREEMENT',{t['gap'] for t in result['research_tasks']})
        self.assertIn('STALE_RESULTS_COVERAGE',{t['gap'] for t in result['research_tasks']})
        self.assertNotIn('NO_SCORED_OPERATIONAL_PREDICTIONS',{t['gap'] for t in result['research_tasks']})

    def test_competing_hypotheses_link_only_to_eligible_evidence(self):
        forecast=self.forecast()
        forecast['models']={'frequency':forecast['models']['one'],'poisson_goals':forecast['models']['two']}
        result=research.assess(forecast,[])
        self.assertEqual(len(result['hypotheses']),2)
        for hypothesis in result['hypotheses']:
            self.assertTrue(set(hypothesis['supporting_evidence_ids']) <= {'target','training','config'})
            self.assertTrue(hypothesis['assumptions'] and hypothesis['missing_information'] and hypothesis['next_question'])


if __name__=='__main__':
    unittest.main()
