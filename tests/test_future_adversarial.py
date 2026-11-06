"""Adversarial acquisition checks over invented worlds; no original state or network."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import timedelta
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from dragonhydra.future_relevance.environment import OUTCOME_DELAY_MINUTES, VirtualEpisode
from dragonhydra.future_relevance.forecast import forecast
from dragonhydra.future_relevance import service as runtime
from dragonhydra.future_relevance.service import FutureService, execute_policy, evaluate_decision
from dragonhydra.future_relevance.learning import estimate, feature_vector, select_model
from dragonhydra.future_relevance.policies import POLICIES, choose_action


@lru_cache(maxsize=1)
def trained():
    from dragonhydra.future_relevance.experiments import train_model
    return train_model(seed=42, cases=10)['model']


def settle(episode):
    view = episode.public()
    episode.advance(max(0, view['target_maturity_minute'] + OUTCOME_DELAY_MINUTES - view['now_minute']) + 1e-9)
    return episode.matured_outcome()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class FutureAdversarialTests(unittest.TestCase):
    def setUp(self):
        network = patch('socket.socket', side_effect=AssertionError('All network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def store(self, **config):
        temporary = tempfile.TemporaryDirectory(prefix='genesis61-future-adversarial-')
        self.addCleanup(temporary.cleanup)
        service = FutureService(Path(temporary.name) / 'owned-virtual-journal', config)
        self.addCleanup(service.close)
        return service

    def test_b_shared_prefix_groups_cannot_cross_training_validation(self):
        from dragonhydra.future_relevance.experiments import make_rows
        train = make_rows(seed=42, cases=6, split='TRAIN')
        validation = make_rows(seed=42, cases=6, split='VALIDATION')
        parent = VirtualEpisode('constant', 1001)
        child = parent.fork(55)
        self.assertEqual(parent.public()['group_id'], child.public()['group_id'])
        self.assertNotEqual(parent.public()['episode_id'], child.public()['episode_id'])
        validation[0]['group_id'] = train[0]['group_id']
        validation[0]['episode_id'] = 'virtual-cross-split-prefix-branch'
        with self.assertRaisesRegex(ValueError, 'GROUP_LEAKAGE'):
            select_model(train, validation)

    def test_a_outcomes_do_not_cross_the_pre_maturity_boundary(self):
        episode = VirtualEpisode('tempo_signal', 1001)
        public = episode.public()
        with self.assertRaisesRegex(ValueError, 'OUTCOME_NOT_AVAILABLE'):
            episode.matured_outcome()
        episode.advance(10)
        with self.assertRaisesRegex(ValueError, 'OUTCOME_NOT_AVAILABLE'):
            episode.matured_outcome()
        episode.advance(OUTCOME_DELAY_MINUTES)
        outcome = episode.matured_outcome()
        self.assertIn(outcome['label'], ('goal', 'no_goal'))
        self.assertNotIn('label', public)
        self.assertNotIn('outcome', public)
        self.assertEqual(public['observed_goal_count_since_origin'], 0)

    def test_c_early_acquisition_has_no_cost_or_visibility_side_effect(self):
        episode = VirtualEpisode('noisy_signal', 400001)
        before = encoded(episode.descriptor())
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_NOT_AVAILABLE'):
            episode.acquire('fatigue', 'virtual-decision-too-early')
        self.assertEqual(encoded(episode.descriptor()), before)

    def test_d_exhausted_budget_cannot_create_an_acquisition_receipt(self):
        episode = VirtualEpisode('constant', 1002, budget=0)
        before = encoded(episode.descriptor())
        with self.assertRaisesRegex(ValueError, 'ACQUISITION_BUDGET_EXHAUSTED'):
            episode.acquire('possession', 'virtual-decision-no-budget')
        self.assertEqual(encoded(episode.descriptor()), before)
        self.assertEqual(episode.public()['budget_remaining'], 0)
        service = self.store(experiment_acquisition_budget=0)
        key = service.create_episode()['episode_id']
        receipt = service.decide(key, 'acquire_all', 'virtual-global-zero-budget', 0)
        self.assertEqual(receipt['acquisition_cost'], 0)
        self.assertEqual(receipt['acquisitions'], [])
        self.assertEqual(service.status()['acquisition_budget_spent'], 0)

    def test_e_redundant_information_is_not_charged_twice(self):
        episode = VirtualEpisode('card_sensitive', 1003)
        receipt = episode.acquire('red_cards', 'virtual-decision-first-card-read')
        before = encoded(episode.descriptor())
        with self.assertRaisesRegex(ValueError, 'REDUNDANT_ACQUISITION'):
            episode.acquire('red_cards', 'virtual-decision-repeat-card-read')
        self.assertEqual(encoded(episode.descriptor()), before)
        self.assertAlmostEqual(episode.public()['budget_total'] - episode.public()['budget_remaining'],
                               receipt['actual_cost'])

    def test_f_a_wrong_relevance_claim_is_not_reported_as_observed_benefit(self):
        found = None
        for seed in range(401000, 401040):
            episode = VirtualEpisode('constant', seed, minute=70)
            def wrong_claim(view, *args, **kwargs):
                candidate = next(row for row in view['candidates'] if row['category'] == 'possession')
                acquire = 'possession' not in view['acquired']
                return {'action': 'ACQUIRE_NOW' if acquire else 'IGNORE', 'category': 'possession' if acquire else None,
                        'estimated_value': 100. if acquire else 0., 'estimated_cost': candidate['cost'] if acquire else 0.,
                        'reason': 'TRUSTED_ADVERSARIAL_WRONG_ESTIMATE', 'scores': []}
            with patch.object(runtime, 'choose_action', side_effect=wrong_claim):
                receipt = execute_policy(episode, 'handcrafted', request_id='virtual-wrong-relevance-' + str(seed))
            evaluation = evaluate_decision(receipt, settle(episode))
            if evaluation['observed_predictive_improvement'] < 0:
                found = receipt, evaluation
                break
        self.assertIsNotNone(found, 'Negative oracle-selected adversarial fixture not found')
        receipt, evaluation = found
        self.assertEqual(receipt['actions'][0]['estimated_value'], 100.)
        self.assertLess(evaluation['observed_predictive_improvement'], 0)
        self.assertLess(evaluation['net_usefulness'], 0)
        self.assertEqual(receipt['expected_value_state'], 'EXPERIMENTAL_NOT_CALIBRATED')

    def test_g_final_rule_families_are_not_constructed_during_training_selection(self):
        from dragonhydra.future_relevance import experiments, environment
        seen = []
        actual = environment.VirtualEpisode
        def construct(*args, **kwargs):
            seen.append(args[0] if args else kwargs['family'])
            return actual(*args, **kwargs)
        with patch.object(environment, 'VirtualEpisode', side_effect=construct):
            result = experiments.train_model(seed=43, cases=6)
        self.assertFalse(set(seen) & set(environment.TEST_FAMILIES))
        self.assertEqual(set(seen), set(environment.TRAIN_FAMILIES) | set(environment.VALIDATION_FAMILIES))
        self.assertFalse(result['training_summary']['final_test_constructed'])
        self.assertFalse(result['model']['selection']['final_test_used'])

    def test_h_time_can_make_previously_valued_information_unusable(self):
        episode = None
        for seed in range(401000, 401020):
            candidate = VirtualEpisode('constant', seed, minute=70)
            early = choose_action(candidate.public(), 'handcrafted')
            candidate.advance(9)
            if not candidate.public()['observed_goal_count_since_origin']:
                episode = candidate
                break
        self.assertIsNotNone(episode, 'Continuous-window no-observed-goal fixture not found')
        early_value = next(row['estimated_value'] for row in early['scores'] if row['category'] == 'possession')
        late = choose_action(episode.public(), 'handcrafted')
        late_value = next(row['estimated_value'] for row in late['scores'] if row['category'] == 'possession')
        self.assertLess(late_value, early_value)
        self.assertEqual(late['action'], 'IGNORE')
        episode.advance(1)
        self.assertEqual(choose_action(episode.public(), 'handcrafted')['action'], 'NO_ADDITIONAL_INFORMATION')

    def test_i_conditional_estimate_changes_after_another_observation_without_causal_claim(self):
        episode = VirtualEpisode('late_card_interaction', 401000, minute=70)
        model = trained()
        before_features = feature_vector(episode.public(), 'shots')
        before = estimate(episode.public(), 'shots', model)['estimated_value']
        episode.acquire('red_cards', 'virtual-conditioned-context')
        after_features = feature_vector(episode.public(), 'shots')
        after = estimate(episode.public(), 'shots', model)['estimated_value']
        self.assertEqual(before_features['acquired_red_cards'], 0)
        self.assertEqual(after_features['acquired_red_cards'], 1)
        self.assertNotEqual(before, after)
        self.assertEqual(model['calibration_state'], 'UNVERIFIED')

    def test_j_missing_observation_stays_hidden_until_actual_availability(self):
        episode = VirtualEpisode('noisy_signal', 400002)
        candidate = next(row for row in episode.public()['candidates'] if row['category'] == 'fatigue')
        self.assertEqual(candidate['availability'], 'PENDING')
        self.assertNotIn('value', candidate)
        episode.advance(1)
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_NOT_AVAILABLE'):
            episode.acquire('fatigue', 'virtual-decision-still-early')
        episode.advance(1)
        receipt = episode.acquire('fatigue', 'virtual-decision-now-available')
        observation = receipt['information_revealed']
        self.assertLessEqual(observation['available_at'], observation['received_at'])
        self.assertEqual(episode.public()['acquired']['fatigue'], observation)
        self.assertTrue(forecast(episode.public())['availability'])

    def test_j_durable_defer_resumes_original_frozen_model_and_keeps_history(self):
        from dragonhydra.future_relevance.experiments import train_model
        service = self.store()
        trained_report = service.train(seed=42, cases_per_family=10)
        key = service.create_episode('noisy_signal', 401000, minute=60)['episode_id']
        original = service.decide(key, 'learned', 'virtual-durable-original-defer', 0)
        self.assertEqual(original['actions'][-1]['action'], 'DEFER')
        self.assertEqual(original['actions'][-1]['category'], 'fatigue')
        self.assertEqual(original['acquisitions'], [])
        original_bytes = encoded(original)
        directory = service.journal.directory
        service.close()
        restarted = FutureService(directory)
        self.addCleanup(restarted.close)
        self.assertEqual(len(restarted.episode(key)['decisions']), 1)
        self.assertEqual(restarted.decide(key, 'learned', 'virtual-durable-original-defer', 0), original)
        # A genuinely fitted alternate active model cannot replace the model
        # named by the immutable earlier DEFER receipt.
        alternate = train_model(seed=43, cases=6)['model']
        self.assertNotEqual(alternate['model_id'], original['model_id'])
        with restarted.journal.connect() as db:
            db.execute('INSERT OR IGNORE INTO models VALUES(?,?)', (alternate['model_id'], encoded(alternate)))
            restarted.journal.put_meta(db, 'active_model', alternate['model_id'])
            db.commit()
        after = restarted.advance(key, 2, original['final_state_revision'])
        resumed = next(row for row in after['decisions'] if row.get('resumes_decision_id') == original['decision_id'])
        self.assertEqual(resumed['model_id'], original['model_id'])
        self.assertNotEqual(resumed['model_id'], alternate['model_id'])
        acquired = next(row for row in resumed['acquisitions'] if row['category'] == 'fatigue')
        self.assertEqual(resumed['before']['cutoff'], resumed['after']['cutoff'])
        self.assertEqual(acquired['decision_at'], resumed['decision_at'])
        self.assertLess(original['decision_at'], resumed['decision_at'])
        self.assertEqual(encoded(after['decisions'][0]), original_bytes)
        spent = restarted.status()['acquisition_budget_spent']
        self.assertEqual(restarted.episode(key)['decisions'], after['decisions'])
        self.assertEqual(restarted.status()['acquisition_budget_spent'], spent)
        self.assertAlmostEqual(spent, sum(row['acquisition_cost'] for row in after['decisions']))
        revision = after['snapshot']['revision']
        matured = restarted.advance(key, 8 + OUTCOME_DELAY_MINUTES + 1e-9, revision)
        evaluation = next(row for row in matured['evaluations'] if row['decision_id'] == original['decision_id'])
        linked = next(row for row in evaluation['deferred_future_relevance'] if row['category'] == 'fatigue')
        self.assertEqual(linked['original_model_id'], original['model_id'])
        self.assertEqual(linked['resumed_decision_id'], resumed['decision_id'])
        self.assertEqual(linked['predicted_at'], original['decision_at'])
        self.assertEqual(linked['acquired_at'], resumed['decision_at'])
        self.assertTrue(math.isfinite(linked['observed_local_improvement']))
        stable = encoded(matured['evaluations'])
        again = restarted.advance(key, 0, matured['snapshot']['revision'])
        self.assertEqual(encoded(again['evaluations']), stable)
        self.assertEqual(encoded(again['decisions'][0]), original_bytes)

    def test_k_wrong_horizon_is_not_silently_replaced(self):
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED'):
            VirtualEpisode('constant', 1004, horizon='7')
        snapshot = VirtualEpisode('constant', 1004).public()
        snapshot['horizon'] = '7'
        result = forecast(snapshot)
        self.assertFalse(result['availability'])
        self.assertEqual(result['reason'], 'UNSUPPORTED_TARGET_OR_HORIZON')
        self.assertEqual(result['probabilities'], {})
        snapshot['target'], snapshot['horizon'] = 'FULL_TIME_RESULT', '10'
        self.assertFalse(forecast(snapshot)['availability'])

    def test_l_stale_forecast_or_revision_rolls_back_all_visibility_and_cost(self):
        episode = VirtualEpisode('constant', 401002)
        before = encoded(episode.descriptor())
        with self.assertRaisesRegex(ValueError, 'STALE_DECISION'):
            execute_policy(episode, 'acquire_all', expected_revision=9)
        self.assertEqual(encoded(episode.descriptor()), before)
        actual = runtime.forecast
        calls = 0
        def stale(snapshot):
            nonlocal calls
            calls += 1
            value = actual(snapshot)
            if calls > 1:
                value['cutoff'] = '2035-01-01T00:00:00Z'
            return value
        with patch.object(runtime, 'forecast', side_effect=stale):
            with self.assertRaisesRegex(ValueError, 'STALE_FORECAST'):
                execute_policy(episode, 'acquire_all')
        self.assertGreater(calls, 1)
        self.assertEqual(encoded(episode.descriptor()), before)

    def test_m_concurrent_decisions_with_one_revision_commit_once(self):
        service = self.store()
        key = service.create_episode()['episode_id']
        ready = threading.Barrier(3)
        def decide(number):
            ready.wait(timeout=3)
            try:
                return 'ok', service.decide(key, 'acquire_all', 'virtual-concurrent-' + str(number), 0)
            except ValueError as error:
                return 'error', str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(decide, number) for number in (1, 2)]
            ready.wait(timeout=3)
            results = [future.result(timeout=5) for future in futures]
        self.assertEqual(sum(kind == 'ok' for kind, _ in results), 1)
        self.assertIn('FUTURE_STALE_DECISION_REJECTED', [row for kind, row in results if kind == 'error'])
        self.assertEqual(len(service.episode(key)['decisions']), 1)
        receipt = next(row for kind, row in results if kind == 'ok')
        self.assertAlmostEqual(service.status()['acquisition_budget_spent'], receipt['acquisition_cost'])

    def test_n_actual_process_crash_preserves_receipt_without_recharging(self):
        with tempfile.TemporaryDirectory(prefix='genesis61-actual-crash-') as temporary:
            state = Path(temporary) / 'owned-virtual-journal'
            program = r'''
import os,socket,sys
socket.socket=lambda *a,**k:(_ for _ in ()).throw(AssertionError('NETWORK_FORBIDDEN'))
from dragonhydra.future_relevance.service import FutureService
service=FutureService(sys.argv[1])
key=service.create_episode()['episode_id']
receipt=service.decide(key,'acquire_all','virtual-crash-committed-request',0)
assert receipt['acquisition_cost']>0
os._exit(37)
'''
            environment = dict(os.environ, PYTHONPATH=str(Path(__file__).parents[1] / 'src'), PYTHONDONTWRITEBYTECODE='1')
            child = subprocess.run([sys.executable, '-B', '-c', program, str(state)], env=environment,
                                   capture_output=True, text=True, timeout=15)
            self.assertEqual(child.returncode, 37, child.stderr)
            service = FutureService(state)
            try:
                key = service.episodes()['items'][0]['episode_id']
                before = service.episode(key)['decisions'][0]
                spent = service.status()['acquisition_budget_spent']
                repeated = service.decide(key, 'acquire_all', 'virtual-crash-committed-request', 0)
                self.assertEqual(repeated, before)
                self.assertEqual(service.status()['acquisition_budget_spent'], spent)
                self.assertEqual(len(service.episode(key)['decisions']), 1)
            finally:
                service.close()

    def test_o_duplicate_receipt_is_exact_and_changed_request_identity_rejected(self):
        service = self.store()
        key = service.create_episode()['episode_id']
        first = service.decide(key, 'acquire_all', 'virtual-repeat-request', 0)
        self.assertEqual(service.decide(key, 'acquire_all', 'virtual-repeat-request', 0), first)
        with self.assertRaisesRegex(ValueError, 'IDEMPOTENCY_CONFLICT'):
            service.decide(key, 'acquire_none', 'virtual-repeat-request', 0)
        self.assertEqual(len(service.episode(key)['decisions']), 1)

    def test_p_nonfinite_world_and_revealed_values_fail_closed(self):
        for field in ('minute', 'budget'):
            for value in (math.nan, math.inf, -math.inf, 10 ** 999):
                with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(ValueError):
                    VirtualEpisode('constant', 1005, **{field: value})
        episode = VirtualEpisode('tempo_signal', 1006)
        episode.acquire('possession', 'virtual-decision-valid-read')
        for value in (math.nan, math.inf, -math.inf, 10 ** 999):
            snapshot = episode.public()
            snapshot['acquired']['possession']['value'] = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                forecast(snapshot)
        actual = runtime.forecast
        for value in (math.nan, math.inf, 10 ** 999):
            episode = VirtualEpisode('constant', 401006)
            before = encoded(episode.descriptor())
            def corrupt(snapshot):
                result = actual(snapshot)
                result['probabilities']['goal'] = value
                return result
            with self.subTest(forecast_value=str(value)[:20]), patch.object(runtime, 'forecast', side_effect=corrupt):
                with self.assertRaises(ValueError):
                    execute_policy(episode, 'acquire_none')
            self.assertEqual(encoded(episode.descriptor()), before)

    def test_q_actual_quotes_and_kernel_work_determine_cost(self):
        episode = VirtualEpisode('constant', 401003)
        actual = runtime.forecast
        with patch.object(runtime, 'forecast', wraps=actual) as counted:
            receipt = execute_policy(episode, 'acquire_all')
        self.assertEqual(receipt['kernel_calls'], counted.call_count)
        self.assertEqual(receipt['computation_cost'], .001 * counted.call_count)
        self.assertAlmostEqual(receipt['acquisition_cost'], sum(row['actual_cost'] for row in receipt['acquisitions']))
        self.assertAlmostEqual(receipt['budget_before'] - receipt['budget_remaining'], receipt['acquisition_cost'])

    def test_r_every_policy_gets_the_same_initial_hidden_information_boundary(self):
        base = VirtualEpisode('possession_inverse', 401004)
        initial = encoded(base.public())
        captured = {}
        actual = runtime.choose_action
        def choose(snapshot, policy, *args, **kwargs):
            captured.setdefault(policy, encoded(snapshot))
            return actual(snapshot, policy, *args, **kwargs)
        pending = []
        with patch.object(runtime, 'choose_action', side_effect=choose):
            for policy in POLICIES:
                arm = base.clone()
                execute_policy(arm, policy, trained() if policy == 'learned' else None)
                pending.append(arm)
        self.assertEqual(set(captured), set(POLICIES))
        self.assertTrue(all(value == initial for value in captured.values()))
        outcomes = [settle(arm) for arm in pending]
        self.assertTrue(all(row == outcomes[0] for row in outcomes))

    def test_s_a_learned_policy_is_allowed_to_be_worse_than_acquire_none(self):
        model, found = trained(), None
        for seed in range(401000, 401040):
            base = VirtualEpisode('possession_inverse', seed, minute=70)
            results = []
            for policy in ('acquire_none', 'learned'):
                arm = base.clone()
                receipt = execute_policy(arm, policy, model if policy == 'learned' else None)
                results.append(evaluate_decision(receipt, settle(arm)))
            if results[1]['net_usefulness'] < results[0]['net_usefulness']:
                found = results
                break
        self.assertIsNotNone(found, 'Expected finite synthetic counterexample not found; never force a positive result')
        self.assertLess(found[1]['net_usefulness'] - found[0]['net_usefulness'], 0)

    def test_t_positive_pre_cost_improvement_can_be_negative_after_cost(self):
        found = None
        for seed in range(401000, 401040):
            episode = VirtualEpisode('constant', seed, minute=70)
            receipt = execute_policy(episode, 'acquire_all', cost_weight=100.)
            result = evaluate_decision(receipt, settle(episode))
            if result['observed_predictive_improvement'] > 0 and result['net_usefulness'] < 0:
                found = receipt, result
                break
        self.assertIsNotNone(found, 'Actual cost-reversal adversarial fixture not found')
        receipt, result = found
        self.assertAlmostEqual(result['net_usefulness'], result['observed_predictive_improvement'] - 100 *
                               (receipt['acquisition_cost'] + receipt['computation_cost']))

    def test_u_public_snapshot_has_no_private_rule_or_unobserved_value_fields(self):
        forbidden = {'family', 'seed', 'branch_seed', 'rates', 'home_hazard', 'away_hazard',
                     'outcomes', 'labels', 'truth', 'future_goals', 'hidden_tempo'}
        def check(value):
            if isinstance(value, dict):
                self.assertFalse(forbidden & value.keys())
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        for family in ('constant', 'card_sensitive', 'tempo_signal', 'clock_sensitive',
                       'noisy_signal', 'possession_inverse', 'late_card_interaction'):
            snapshot = VirtualEpisode(family, 400003).public()
            check(snapshot)
            self.assertEqual(snapshot['acquired'], {})
            self.assertTrue(all('value' not in row for row in snapshot['candidates']))
        snapshot = VirtualEpisode('constant', 401005).public()
        before = feature_vector(snapshot, 'possession')
        snapshot.update(family='leaked-rule-must-be-ignored', seed=12345, episode_id='virtual-unrelated-id', group_id='virtual-unrelated-group')
        from dragonhydra.future_relevance.forecast import instant
        def move(value):
            if isinstance(value, dict):
                return {key: ((instant(child) + timedelta(days=365)).isoformat().replace('+00:00', 'Z')
                              if key in ('now', 'decision_at', 'available_at', 'received_at', 'last_event_time', 'observed_at') and isinstance(child, str)
                              else move(child)) for key, child in value.items()}
            if isinstance(value, list): return [move(child) for child in value]
            return value
        self.assertEqual(feature_vector(move(snapshot), 'possession'), before)

    def test_v_unsupported_category_does_not_mutate_the_world(self):
        episode = VirtualEpisode('constant', 1007)
        before = encoded(episode.descriptor())
        for category in ('unknown', 'outcomes', 'family', 'live_provider'):
            with self.subTest(category=category), self.assertRaisesRegex(ValueError, 'CATEGORY_UNSUPPORTED'):
                episode.acquire(category, 'virtual-decision-forbidden-category')
            self.assertEqual(encoded(episode.descriptor()), before)

    def test_w_mutating_a_public_copy_cannot_rewrite_retained_episode_state(self):
        episode = VirtualEpisode('constant', 1008)
        episode.acquire('possession', 'virtual-decision-retained-observation')
        before = encoded(episode.public())
        exposed = episode.public()
        exposed['observed_state']['score']['home'] = 99
        exposed['acquired']['possession']['value'] = .999
        exposed['candidates'][0]['cost'] = 0
        self.assertEqual(encoded(episode.public()), before)
        service = self.store()
        key = service.create_episode()['episode_id']
        decision = service.decide(key, 'acquire_all', 'virtual-immutable-history', 0)
        service.advance(key, 10 + OUTCOME_DELAY_MINUTES + 1e-9, decision['final_state_revision'])
        service.train(seed=42, cases_per_family=10)
        for table in ('decisions', 'acquisitions', 'predictions', 'evaluations', 'models', 'experiments'):
            for action in ('UPDATE', 'DELETE'):
                with self.subTest(table=table, action=action), service.journal.connect() as db:
                    self.assertGreater(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0)
                    prior = [row[0] for row in db.execute('SELECT payload FROM ' + table + ' ORDER BY rowid')]
                    sql = 'UPDATE ' + table + ' SET payload=payload' if action == 'UPDATE' else 'DELETE FROM ' + table
                    with self.assertRaisesRegex(sqlite3.DatabaseError, 'IMMUTABLE_FUTURE_EVIDENCE'):
                        db.execute(sql)
                    self.assertEqual([row[0] for row in db.execute('SELECT payload FROM ' + table + ' ORDER BY rowid')], prior)


if __name__ == '__main__':
    unittest.main()
