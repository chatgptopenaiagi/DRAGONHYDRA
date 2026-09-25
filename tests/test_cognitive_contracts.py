"""Adversarial checks on the typed cognitive/evidence boundary."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
import unittest

from dragonhydra.cognitive.contracts import (
    AcquisitionRequest, ActionClass, ActionDecision, ActionProposal, ActionResult,
    ActorIdentity, ActorRole, AgreementState, CalculationRequest, CapabilityDescriptor,
    CalibrationBin, CalibrationMeasurement,
    CognitiveCycleReceipt, CognitiveRequest, CognitiveResponse, EpistemicState,
    EvidenceDelta, EvidenceSummary, Hypothesis, LearningFeedback, Metadata,
    ModelDelta, ModelSummary, ObservedOutcome, Outcome, Position, ReconciliationReport,
    ResearchNeed, ResultStatus, SourceSummary, StateDelta, StatusSummary,
    SystemStateSnapshot, TaskKind, TemporalMode, UncertaintyDelta, UncertaintySummary,
    canonical_hash,
)


NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
DIGEST = "a" * 64
OTHER = "b" * 64


def metadata(role=ActorRole.SYSTEM):
    actor = ActorIdentity(actor_id=role.value.lower(), role=role,
                          model_id="test-model" if role in (ActorRole.QWEN, ActorRole.CODEX) else "NOT_APPLICABLE",
                          runtime_id="deterministic-test" if role is ActorRole.QWEN else "NOT_APPLICABLE")
    return Metadata(created_at=NOW, as_of_at=NOW, temporal_mode=TemporalMode.STRICT_PIT,
                    actor=actor, source_refs=("fixture-1",), input_hashes=(DIGEST,))


def evidence(**changes):
    values = dict(evidence_id="evidence-1", source_id="synthetic-test-fixture",
                  content_hash=DIGEST, available_at=NOW - timedelta(hours=1),
                  observed_at=NOW - timedelta(hours=1), event_at=NOW - timedelta(hours=2),
                  epistemic_state=EpistemicState.OBSERVATION, validation_ref="medusa-test-1",
                  provenance_refs=("capture-test-1",))
    values.update(changes)
    return EvidenceSummary(**values)


def feedback(**changes):
    before = (.2, .3, .5)
    after = (.6, .2, .2)
    values = dict(metadata=metadata(), feedback_id="feedback-1", before_state_hash=DIGEST,
                  after_state_hash=OTHER, action_refs=("action-1",), new_evidence_refs=("evidence-1",),
                  fixture_id="fixture-1", prediction_before_ref="immutable-forecast-1",
                  prediction_after_ref="immutable-forecast-2",
                  prediction_before_at=NOW - timedelta(days=2),
                  prediction_after_at=NOW - timedelta(days=1),
                  prediction_before=before, prediction_after=after,
                  actual_outcome=ObservedOutcome(fixture_id="fixture-1", outcome=Outcome.HOME,
                                                 evidence=evidence()),
                  model_error_before=.98, model_error_after=.24, accuracy_gain=.74,
                  prediction_quality_improved=True, both_wrong=False)
    values.update(changes)
    return LearningFeedback(**values)


class CognitiveContractTests(unittest.TestCase):
    def test_hypothesis_cannot_be_observation(self):
        with self.assertRaises(ValueError):
            Hypothesis(metadata=metadata(ActorRole.QWEN), hypothesis_id="h-1", summary="Unknown lineup",
                       epistemic_state=EpistemicState.OBSERVATION)

    def test_response_identity_and_hypothesis_survive_roundtrip(self):
        actor = metadata(ActorRole.QWEN)
        response = CognitiveResponse(metadata=actor, request_id="r-1", state_hash=DIGEST,
                                     input_hash=OTHER, result_status=ResultStatus.COMPLETE,
                                     conclusions=(Hypothesis(metadata=actor, hypothesis_id="h-1",
                                                             summary="Lineup may matter"),))
        restored = CognitiveResponse.from_json(response.to_json())
        self.assertEqual(restored, response)
        self.assertEqual(restored.conclusions[0].epistemic_state, EpistemicState.HYPOTHESIS)
        self.assertEqual(restored.metadata.actor.model_id, "test-model")
        self.assertEqual(restored.output_hash, response.output_hash)

    def test_qwen_requires_explicit_identity(self):
        with self.assertRaises(ValueError):
            ActorIdentity(actor_id="qwen", role=ActorRole.QWEN)

    def test_hypothesis_confidence_is_not_evidence(self):
        value = Hypothesis(metadata=metadata(ActorRole.CODEX), hypothesis_id="h-1",
                           summary="Uncertain availability", confidence=1)
        self.assertEqual(value.epistemic_state, EpistemicState.HYPOTHESIS)

    def test_contracts_are_frozen(self):
        value = metadata()
        with self.assertRaises(FrozenInstanceError):
            value.schema_version = "2"

    def test_mutable_nested_collections_rejected(self):
        with self.assertRaises(ValueError):
            replace(metadata(), source_refs=["mutable"])

    def test_snapshot_deterministic_and_evidence_change_affects_hash(self):
        first = SystemStateSnapshot(metadata=metadata(), evidence=(evidence(),))
        same = SystemStateSnapshot.from_json(first.to_json())
        changed = replace(first, evidence=(evidence(content_hash=OTHER),))
        self.assertEqual(first.state_hash, same.state_hash)
        self.assertNotEqual(first.state_hash, changed.state_hash)

    def test_canonical_dictionary_order(self):
        self.assertEqual(canonical_hash({"a": 1, "b": 2}), canonical_hash({"b": 2, "a": 1}))

    def test_future_event_cannot_be_observation(self):
        with self.assertRaises(ValueError):
            evidence(event_at=NOW + timedelta(days=1))

    def test_future_prediction_preserves_type(self):
        item = evidence(event_at=NOW + timedelta(days=1), epistemic_state=EpistemicState.PREDICTION)
        value = SystemStateSnapshot(metadata=metadata(), evidence=(item,))
        self.assertEqual(value.evidence[0].epistemic_state, EpistemicState.PREDICTION)

    def test_unknown_event_cannot_be_observation(self):
        with self.assertRaises(ValueError):
            evidence(event_at=None)

    def test_strict_snapshot_rejects_reconstructed_evidence(self):
        item = evidence(temporal_mode=TemporalMode.RECONSTRUCTED_PIT)
        with self.assertRaises(ValueError):
            SystemStateSnapshot(metadata=metadata(), evidence=(item,))

    def test_future_availability_rejected(self):
        item = evidence(available_at=NOW + timedelta(days=1))
        with self.assertRaises(ValueError):
            SystemStateSnapshot(metadata=metadata(), evidence=(item,))

    def test_naive_or_future_cursor_rejected(self):
        for changes in ({"as_of_at": NOW.replace(tzinfo=None)}, {"as_of_at": NOW + timedelta(seconds=1)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(metadata(), **changes)

    def test_snapshot_cannot_be_authored_by_ai(self):
        with self.assertRaises(ValueError):
            SystemStateSnapshot(metadata=metadata(ActorRole.CODEX))

    def test_ai_cannot_author_evidence_or_state_delta_observations(self):
        controlled = EvidenceDelta(metadata=metadata(), before_state_hash=DIGEST,
                                   after_state_hash=OTHER, added=(evidence(),))
        state = StateDelta(metadata=metadata(), before_state_hash=DIGEST,
                           after_state_hash=OTHER, evidence=controlled)
        for role in (ActorRole.QWEN, ActorRole.CODEX):
            for original in (controlled, state):
                with self.subTest(role=role, contract=type(original).__name__), self.assertRaises(ValueError):
                    raw = original.to_dict()
                    raw["metadata"] = metadata(role).to_dict()
                    type(original).from_dict(raw)

    def test_evidence_delta_preserves_cursor_and_temporal_mode(self):
        for item in (evidence(available_at=NOW + timedelta(seconds=1)),
                     evidence(temporal_mode=TemporalMode.RECONSTRUCTED_PIT)):
            with self.subTest(item=item), self.assertRaises(ValueError):
                EvidenceDelta(metadata=metadata(), before_state_hash=DIGEST,
                              after_state_hash=OTHER, added=(item,))

    def test_state_delta_cannot_hide_ai_or_different_clock_components(self):
        controlled = EvidenceDelta(metadata=metadata(), before_state_hash=DIGEST, after_state_hash=OTHER)
        mismatches = (metadata(ActorRole.CODEX),
                      replace(metadata(), created_at=NOW + timedelta(seconds=1)),
                      replace(metadata(), as_of_at=NOW - timedelta(seconds=1)),
                      replace(metadata(), temporal_mode=TemporalMode.RECONSTRUCTED_PIT))
        for child_metadata in mismatches:
            with self.subTest(metadata=child_metadata), self.assertRaises(ValueError):
                StateDelta(metadata=metadata(), before_state_hash=DIGEST, after_state_hash=OTHER,
                           evidence=controlled, uncertainties=(UncertaintyDelta(
                               metadata=child_metadata, uncertainty_id="u", before=.8, after=.2),))

    def test_secret_like_text_rejected_in_every_string_leaf(self):
        for text in ("password" + "=test-value", "Bearer " + "synthetic-token", "https://" + "u:p@" + "example.test"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                replace(metadata(), source_refs=(text,))

    def test_unknown_fields_and_chain_of_thought_rejected(self):
        value = SystemStateSnapshot(metadata=metadata()).to_dict()
        for key in ("chain_of_thought", "reasoning", "shell", "raw_source_text"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                SystemStateSnapshot.from_dict(dict(value, **{key: "untrusted"}))

    def test_nested_unknown_fields_rejected(self):
        value = SystemStateSnapshot(metadata=metadata()).to_dict()
        value["metadata"]["actor"]["chain_of_thought"] = "hidden"
        with self.assertRaises(ValueError):
            SystemStateSnapshot.from_dict(value)

    def test_duplicate_keys_rejected_recursively(self):
        for serialized in ('{"schema_version":"1","schema_version":"2"}',
                           '{"metadata":{"actor":{"role":"SYSTEM","role":"QWEN"}}}'):
            with self.subTest(serialized=serialized), self.assertRaises(ValueError):
                SystemStateSnapshot.from_json(serialized)

    def test_nonfinite_and_bool_numbers_rejected(self):
        for number in (float("nan"), float("inf"), True):
            with self.subTest(number=number), self.assertRaises(ValueError):
                UncertaintySummary(uncertainty_id="u-1", score=number)
        with self.assertRaises(ValueError):
            UncertaintySummary.from_json('{"uncertainty_id":"u-1","score":NaN}')

    def test_huge_finite_json_integer_is_a_structured_validation_failure(self):
        payload = '{"uncertainty_id":"u-1","score":' + "9" * 1000 + "}"
        with self.assertRaises(ValueError):
            UncertaintySummary.from_json(payload)

    def test_bound_strings_collections_and_json(self):
        for changes in ({"source_refs": ("x" * 1025,)}, {"source_refs": ("x",) * 257},
                        {"source_refs": ("two\nlines",)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(metadata(), **changes)
        with self.assertRaises(ValueError):
            SystemStateSnapshot.from_json(" " * 262145)

    def test_wrong_enum_hash_and_reason_code_rejected(self):
        for changes in ({"temporal_mode": "STRICT_PIT"}, {"input_hashes": ("not-a-hash",)},
                        {"reason_codes": ("arbitrary text",)}, {"schema_version": "2"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(metadata(), **changes)

    def test_research_need_retains_provenance(self):
        item = ResearchNeed(metadata=metadata(ActorRole.QWEN), need_id="n-1", state_hash=DIGEST,
                            question="Is player availability known?", hypothesis_refs=("h-1",),
                            provenance_refs=("capture-1", "validation-1"), requested_capability="research")
        self.assertEqual(ResearchNeed.from_json(item.to_json()).provenance_refs, item.provenance_refs)
        with self.assertRaises(ValueError):
            replace(item, provenance_refs=())

    def test_acquisition_cannot_bypass_hydra_medusa(self):
        item = AcquisitionRequest(metadata=metadata(ActorRole.CODEX), request_id="a-1", state_hash=DIGEST,
                                  research_need_id="n-1", requested_capability="research", source_id="source-1",
                                  source_policy_ref="policy-1", provenance_refs=("h-1",))
        for changes in ({"acquisition_actor": ActorRole.CODEX}, {"validation_actor": ActorRole.QWEN},
                        {"epistemic_state": EpistemicState.OBSERVATION}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(item, **changes)

    def test_unsupported_actions_rejected(self):
        value = CapabilityDescriptor(capability_id="none", action=ActionClass.NO_ACTION, enabled=True).to_dict()
        for action in ("UNRESTRICTED_SHELL", "EXECUTE_SQL", "WAGER", "BYPASS_POLICY"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                CapabilityDescriptor.from_dict(dict(value, action=action))

    def test_acquisition_capability_requires_policy_and_validation(self):
        for changes in ({"requires_medusa": False}, {"requires_source_policy": False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                CapabilityDescriptor(capability_id="research", action=ActionClass.REQUEST_RESEARCH,
                                     enabled=True, **changes)

    def test_ai_cannot_authorize_own_action(self):
        with self.assertRaises(ValueError):
            ActionDecision(metadata=metadata(ActorRole.CODEX), proposal_id="p-1", state_hash=DIGEST,
                           action=ActionClass.NO_ACTION, requested_capability="none", permitted=True,
                           result_status=ResultStatus.COMPLETE)

    def test_failed_response_cannot_contain_fabricated_conclusions(self):
        actor = metadata(ActorRole.QWEN)
        with self.assertRaises(ValueError):
            CognitiveResponse(metadata=actor, request_id="r-1", state_hash=DIGEST, input_hash=OTHER,
                              result_status=ResultStatus.FAILED, failure_state="RUNTIME_UNAVAILABLE",
                              conclusions=(Hypothesis(metadata=actor, hypothesis_id="h-1", summary="invented"),))

    def test_failure_requires_structured_reason(self):
        with self.assertRaises(ValueError):
            CognitiveResponse(metadata=metadata(ActorRole.QWEN), request_id="r-1", state_hash=DIGEST,
                              input_hash=OTHER, result_status=ResultStatus.BLOCKED)

    def test_disagreement_preserves_each_position(self):
        first = Position(actor=metadata(ActorRole.QWEN).actor, claim_id="lineup", summary="Lineup uncertainty",
                         epistemic_state=EpistemicState.HYPOTHESIS)
        second = Position(actor=metadata(ActorRole.CODEX).actor, claim_id="market", summary="Market uncertainty",
                          epistemic_state=EpistemicState.HYPOTHESIS)
        value = ReconciliationReport(metadata=metadata(), state_hash=DIGEST,
                                     agreement=AgreementState.DISAGREEMENT, positions=(first, second))
        self.assertEqual(ReconciliationReport.from_json(value.to_json()).positions, (first, second))

    def test_accuracy_gain_requires_observed_outcome(self):
        with self.assertRaises(ValueError):
            feedback(actual_outcome=None)

    def test_synthetic_outcome_cannot_establish_accuracy(self):
        with self.assertRaises(ValueError):
            ObservedOutcome(fixture_id="fixture-1", outcome=Outcome.HOME,
                            evidence=evidence(epistemic_state=EpistemicState.SYNTHETIC))

    def test_measured_score_gain_is_recalculated(self):
        self.assertAlmostEqual(feedback().accuracy_gain, .74)
        for changes in ({"accuracy_gain": .9}, {"model_error_before": .2},
                        {"prediction_quality_improved": False}, {"both_wrong": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                feedback(**changes)

    def test_accuracy_requires_frozen_forecasts_for_same_fixture(self):
        for changes in ({"fixture_id": "different-fixture"}, {"prediction_before_ref": None},
                        {"prediction_after_at": NOW}, {"prediction_before_at": NOW}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                feedback(**changes)

    def test_both_wrong_unknown_for_tied_forecast(self):
        with self.assertRaises(ValueError):
            feedback(prediction_before=(.4, .4, .2), model_error_before=None, accuracy_gain=None)

    def test_usefulness_requires_action_and_measured_benefit(self):
        self.assertTrue(feedback(qwen_proposal_useful=True).qwen_proposal_useful)
        with self.assertRaises(ValueError):
            feedback(qwen_proposal_useful=True, action_refs=())
        with self.assertRaises(ValueError):
            LearningFeedback(metadata=metadata(), feedback_id="f-1", before_state_hash=DIGEST,
                             after_state_hash=OTHER, action_refs=("a-1",), new_evidence_refs=("e-1",),
                             qwen_proposal_useful=True)

    def test_prose_change_is_not_learning(self):
        value = LearningFeedback(metadata=metadata(), feedback_id="f-1", before_state_hash=DIGEST,
                                 after_state_hash=OTHER, action_refs=(), new_evidence_refs=())
        self.assertIsNone(value.accuracy_gain)
        self.assertIsNone(value.prediction_quality_improved)

    def test_source_text_cannot_supply_executable_fields(self):
        payload = ActionProposal(metadata=metadata(ActorRole.CODEX), proposal_id="p-1", state_hash=DIGEST,
                                 action=ActionClass.REQUEST_HUMAN_REVIEW, requested_capability="review",
                                 rationale_summary="Source instruction is untrusted data").to_dict()
        payload["command"] = "untrusted source instruction"
        with self.assertRaises(ValueError):
            ActionProposal.from_dict(payload)

    def test_calibration_is_measured_on_same_multi_outcome_cohort(self):
        before = CalibrationMeasurement(metadata=metadata(), model_id="before", evaluation_ref="evaluation-1",
                                        protocol_ref="protocol-1", outcome_class=Outcome.HOME,
                                        observed_outcome_refs=("outcome-1", "outcome-2"),
                                        bins=(CalibrationBin(mean_probability=.8, observed_count=1, sample_count=2),))
        after = replace(before, model_id="after",
                        bins=(CalibrationBin(mean_probability=.6, observed_count=1, sample_count=2),))
        value = feedback(calibration_before=before, calibration_after=after, calibration_gain=.2)
        self.assertAlmostEqual(value.calibration_gain, .2)
        for changes in ({"calibration_gain": .9}, {"calibration_after": None},
                        {"calibration_after": replace(after, protocol_ref="different")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(value, **changes)

    def test_one_outcome_or_inconsistent_count_cannot_claim_calibration(self):
        for refs in (("outcome-1",), ("outcome-1", "outcome-1"), ("one", "two", "three")):
            with self.subTest(refs=refs), self.assertRaises(ValueError):
                CalibrationMeasurement(metadata=metadata(), model_id="m", evaluation_ref="evaluation-1",
                                       protocol_ref="protocol-1", outcome_class=Outcome.HOME,
                                       observed_outcome_refs=refs,
                                       bins=(CalibrationBin(mean_probability=.5, observed_count=1, sample_count=2),))

    def test_calibration_gain_cannot_relabel_same_cohort_outcomes(self):
        before = CalibrationMeasurement(metadata=metadata(), model_id="before", evaluation_ref="evaluation-1",
                                        protocol_ref="protocol-1", outcome_class=Outcome.HOME,
                                        observed_outcome_refs=("outcome-1", "outcome-2"),
                                        bins=(CalibrationBin(mean_probability=.8, observed_count=0, sample_count=2),))
        after = replace(before, model_id="after",
                        bins=(CalibrationBin(mean_probability=.8, observed_count=2, sample_count=2),))
        with self.assertRaisesRegex(ValueError, "observed outcome totals"):
            feedback(calibration_before=before, calibration_after=after, calibration_gain=.6)

    def test_all_contracts_have_closed_roundtrip(self):
        meta = metadata()
        evidence_delta = EvidenceDelta(metadata=meta, before_state_hash=DIGEST, after_state_hash=OTHER)
        samples = (
            CalculationRequest(metadata=meta, request_id="r", state_hash=DIGEST, requested_capability="math",
                               input_hashes=(OTHER,), provenance_refs=("e",)),
            CognitiveRequest(metadata=meta, request_id="r", state_hash=DIGEST, task=TaskKind.REVIEW_ACTIONS,
                             allowed_actions=(ActionClass.NO_ACTION,)),
            StateDelta(metadata=meta, before_state_hash=DIGEST, after_state_hash=OTHER, evidence=evidence_delta),
            ModelDelta(metadata=meta, model_id="m", before_forecast_hash=None, after_forecast_hash=DIGEST),
            UncertaintyDelta(metadata=meta, uncertainty_id="u", before=None, after=.2),
            SourceSummary(source_id="s", status=ResultStatus.UNKNOWN),
            StatusSummary(component="MODEL", status=ResultStatus.NOT_STARTED),
            ModelSummary(model_id="m", forecast_hash=DIGEST, probabilities=(.3, .3, .4)),
            ActionResult(metadata=meta, proposal_id="p", state_hash=DIGEST, action=ActionClass.NO_ACTION,
                         result_status=ResultStatus.COMPLETE),
            CognitiveCycleReceipt(metadata=meta, cycle_id="c", state_hash=DIGEST),
            feedback(),
        )
        for sample in samples:
            with self.subTest(contract=type(sample).__name__):
                self.assertEqual(type(sample).from_json(sample.to_json()), sample)
                value = sample.to_dict()
                value["unexpected"] = {}
                with self.assertRaises(ValueError):
                    type(sample).from_dict(value)


if __name__ == "__main__":
    unittest.main()
