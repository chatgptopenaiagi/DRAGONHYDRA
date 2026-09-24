"""Small, dependency-free historical replay harness, never a betting engine.

All probabilities are HOME/DRAW/AWAY. RPS uses that ordered scale and divides
the two nontrivial cumulative squared errors by two (range 0..1). Multiclass
Brier is the unscaled sum over the three classes (range 0..2); per-class terms
are reported separately, not mislabeled as a Murphy decomposition. Log loss
uses natural logarithms. Impossible realized events return an explicit
infinite-loss flag with a JSON-safe null, without undisclosed clipping.

Formula references: https://scikit-learn.org/stable/modules/model_evaluation.html
and https://search.r-project.org/CRAN/refmans/verification/html/rps.html .
These are references only; neither library is a runtime dependency.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
import json
from math import fsum, isclose, isfinite, log

from .temporal import Availability, DecisionHorizon, TemporalMode, TimedRevision, as_of


def _text(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


class Outcome(StrEnum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


CATEGORY_ORDER = (Outcome.HOME, Outcome.DRAW, Outcome.AWAY)


class Metric(StrEnum):
    LOG_LOSS = "LOG_LOSS"
    RPS = "RPS"
    MULTICLASS_BRIER = "MULTICLASS_BRIER"
    ACCURACY_SECONDARY = "ACCURACY_SECONDARY"


@dataclass(frozen=True, slots=True)
class Probabilities:
    home: float
    draw: float
    away: float

    def __post_init__(self) -> None:
        if any(isinstance(p, bool) or not isinstance(p, (int, float))
               or not isfinite(p) or not 0 <= p <= 1 for p in self.values):
            raise ValueError("Probabilities must be finite numbers in [0, 1]")
        if not isclose(fsum(self.values), 1.0, rel_tol=0, abs_tol=1e-12):
            raise ValueError("HOME/DRAW/AWAY probabilities must sum to one")

    @property
    def values(self) -> tuple[float, float, float]:
        return self.home, self.draw, self.away

    def to_dict(self) -> dict:
        return dict(zip(CATEGORY_ORDER, self.values))


@dataclass(frozen=True, slots=True)
class FixtureTarget:
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    kickoff_at: datetime
    schedule_availability: Availability
    schedule_record_id: str

    def __post_init__(self) -> None:
        for field in ("fixture_id", "competition_id", "home_team_id", "away_team_id",
                      "schedule_record_id"):
            _text(getattr(self, field), field)
        _aware(self.kickoff_at, "kickoff_at")
        if self.home_team_id == self.away_team_id:
            raise ValueError("A fixture needs distinct teams")
        if not isinstance(self.schedule_availability, Availability):
            raise ValueError("schedule_availability must use the temporal contract")


@dataclass(frozen=True, slots=True)
class ResultObservation:
    record_id: str
    fixture_id: str
    competition_id: str
    home_team_id: str
    away_team_id: str
    event_completed_at: datetime
    outcome: Outcome
    availability: Availability
    revision: int = 1
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("record_id", "fixture_id", "competition_id", "home_team_id", "away_team_id"):
            _text(getattr(self, field), field)
        _aware(self.event_completed_at, "event_completed_at")
        if not isinstance(self.outcome, Outcome):
            raise ValueError("outcome must be an Outcome")
        if self.home_team_id == self.away_team_id:
            raise ValueError("A result needs distinct teams")
        if not isinstance(self.availability, Availability):
            raise ValueError("availability must use the temporal contract")
        if self.availability.available_at is not None and self.availability.available_at < self.event_completed_at:
            raise ValueError("A final result cannot be available before the event completes")
        self.timed_revision()  # Reuse validation of version and supersession shape.

    def timed_revision(self) -> TimedRevision:
        return TimedRevision(self.record_id, self.fixture_id, self.revision,
                             self.availability, self.supersedes_id)


@dataclass(frozen=True, slots=True)
class EvaluationPeriod:
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        _aware(self.start_at, "start_at")
        _aware(self.end_at, "end_at")
        if self.start_at >= self.end_at:
            raise ValueError("Evaluation period must be a nonempty half-open interval")


class Baseline(StrEnum):
    LEAGUE_EMPIRICAL = "BASELINE_A_LEAGUE_EMPIRICAL"
    HOME_AWAY_EMPIRICAL = "BASELINE_B_HOME_AWAY_EMPIRICAL"
    UNIFORM = "BENCHMARK_UNIFORM"


@dataclass(frozen=True, slots=True)
class ModelIdentity:
    model_id: Baseline
    model_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, Baseline):
            raise ValueError("Unknown baseline model")
        _text(self.model_version, "model_version")


@dataclass(frozen=True, slots=True)
class WalkForwardProtocol:
    protocol_id: str
    version: str
    competition_id: str
    temporal_mode: TemporalMode
    decision_horizon: DecisionHorizon
    evaluation_period: EvaluationPeriod
    min_training_matches: int = 30
    smoothing: float = 1.0
    prior_strength: float = 5.0
    calibration_bins: int = 10

    def __post_init__(self) -> None:
        for field in ("protocol_id", "version", "competition_id"):
            _text(getattr(self, field), field)
        if not isinstance(self.temporal_mode, TemporalMode):
            raise ValueError("temporal_mode must be declared")
        if not isinstance(self.decision_horizon, DecisionHorizon):
            raise ValueError("decision_horizon must be typed")
        if not isinstance(self.evaluation_period, EvaluationPeriod):
            raise ValueError("evaluation_period must be typed")
        if type(self.min_training_matches) is not int or self.min_training_matches < 1:
            raise ValueError("min_training_matches must be a positive integer")
        if type(self.calibration_bins) is not int or not 1 <= self.calibration_bins <= 100:
            raise ValueError("calibration_bins must be an integer in [1, 100]")
        for field in ("smoothing", "prior_strength"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
                raise ValueError(f"{field} must be finite and positive")

    def to_dict(self) -> dict:
        return {
            "protocol_id": self.protocol_id, "version": self.version,
            "competition_id": self.competition_id, "temporal_mode": self.temporal_mode.value,
            "decision_horizon": self.decision_horizon.to_dict(),
            "evaluation_period": {"start_at": self.evaluation_period.start_at.isoformat(),
                                  "end_at": self.evaluation_period.end_at.isoformat()},
            "min_training_matches": self.min_training_matches, "smoothing": self.smoothing,
            "prior_strength": self.prior_strength, "calibration_bins": self.calibration_bins,
            "training_window": "EXPANDING; completed_at < target and available_at <= target",
            "scoring_categories": list(CATEGORY_ORDER), "rps_divisor": 2,
            "benchmark": Baseline.UNIFORM.value,
            "selection": "FIXED_PROTOCOL_NO_RANDOM_SPLIT_NO_PARAMETER_SEARCH",
        }


@dataclass(frozen=True, slots=True)
class InputEvidence:
    record_id: str
    role: str
    availability: Availability

    def __post_init__(self) -> None:
        _text(self.record_id, "record_id")
        if self.role not in ("FIXTURE_SCHEDULE", "TRAINING_RESULT"):
            raise ValueError("Unknown prediction input role")
        if not isinstance(self.availability, Availability):
            raise ValueError("Input evidence needs its availability assumptions")


@dataclass(frozen=True, slots=True)
class Prediction:
    prediction_id: str
    fixture_id: str
    model: ModelIdentity
    probabilities: Probabilities
    prediction_issued_at: datetime
    computed_at: datetime
    decision_horizon: DecisionHorizon
    feature_snapshot_id: str
    evidence_snapshot_id: str
    temporal_mode: TemporalMode
    input_evidence: tuple[InputEvidence, ...]
    issuance_kind: str = "HISTORICAL_REPLAY"

    def __post_init__(self) -> None:
        for field in ("prediction_id", "fixture_id", "feature_snapshot_id", "evidence_snapshot_id"):
            _text(getattr(self, field), field)
        _aware(self.prediction_issued_at, "prediction_issued_at")
        _aware(self.computed_at, "computed_at")
        if self.computed_at < self.prediction_issued_at:
            raise ValueError("A replay cannot be computed before its simulated horizon")
        if self.issuance_kind != "HISTORICAL_REPLAY":
            raise ValueError("This harness produces explicitly labeled historical replays only")
        if not isinstance(self.model, ModelIdentity) or not isinstance(self.probabilities, Probabilities):
            raise ValueError("Prediction requires typed model and probabilities")
        if not isinstance(self.temporal_mode, TemporalMode) or not isinstance(self.decision_horizon, DecisionHorizon):
            raise ValueError("Prediction requires typed temporal mode and decision horizon")
        if not isinstance(self.input_evidence, tuple) or not self.input_evidence:
            raise ValueError("Prediction requires immutable input evidence")
        if any(not isinstance(item, InputEvidence) for item in self.input_evidence):
            raise ValueError("Prediction inputs must be typed evidence references")
        if len({item.record_id for item in self.input_evidence}) != len(self.input_evidence):
            raise ValueError("Prediction input evidence IDs must be unique")
        if any(item.availability.ingested_at > self.computed_at for item in self.input_evidence):
            raise ValueError("Prediction cannot consume evidence acquired after computed_at")
        if (self.decision_horizon.target_at is not None
                and self.decision_horizon.target_at != self.prediction_issued_at):
            raise ValueError("Prediction issue time must equal its absolute decision horizon")
        if any(not item.availability.eligible(self.prediction_issued_at, self.temporal_mode)
               for item in self.input_evidence):
            raise ValueError("Prediction contains unavailable or disallowed temporal input")

    @property
    def model_version(self) -> str:
        return self.model.model_version

    def to_dict(self, *, include_evidence: bool = True) -> dict:
        document = {
            "prediction_id": self.prediction_id, "fixture_id": self.fixture_id,
            "model_id": self.model.model_id.value, "model_version": self.model_version,
            "probabilities": self.probabilities.to_dict(),
            "prediction_issued_at": self.prediction_issued_at.isoformat(),
            "computed_at": self.computed_at.isoformat(), "issuance_kind": self.issuance_kind,
            "decision_horizon": self.decision_horizon.to_dict(),
            "feature_snapshot_id": self.feature_snapshot_id,
            "evidence_snapshot_id": self.evidence_snapshot_id,
            "temporal_mode": self.temporal_mode.value,
            "input_evidence_ids": [item.record_id for item in self.input_evidence],
        }
        if include_evidence:
            document["input_evidence"] = [
                {"record_id": item.record_id, "role": item.role,
                 "availability": item.availability.to_dict()} for item in self.input_evidence]
        return document


@dataclass(frozen=True, slots=True)
class Score:
    log_loss: float | None
    log_loss_infinite: bool
    rps: float
    brier: float
    brier_components: tuple[float, float, float]
    correct: bool


def score_prediction(probabilities: Probabilities, outcome: Outcome) -> Score:
    if not isinstance(probabilities, Probabilities) or not isinstance(outcome, Outcome):
        raise ValueError("Scoring requires typed probabilities and outcome")
    actual_index = CATEGORY_ORDER.index(outcome)
    observed = tuple(float(i == actual_index) for i in range(3))
    components = tuple((p - y) ** 2 for p, y in zip(probabilities.values, observed))
    cumulative = [(fsum(probabilities.values[:i]) - fsum(observed[:i])) ** 2 for i in (1, 2)]
    actual_probability = probabilities.values[actual_index]
    return Score(-log(actual_probability) if actual_probability else None,
                 actual_probability == 0, fsum(cumulative) / 2, fsum(components),
                 components, max(range(3), key=probabilities.values.__getitem__) == actual_index)


def baseline_probabilities(model: Baseline, training: tuple[ResultObservation, ...],
                           target: FixtureTarget, *, smoothing: float = 1,
                           prior_strength: float = 5) -> Probabilities:
    """A: Laplace league rates; B: venue-specific team rates shrunk to A.

    B averages two posterior vectors: the home team's past home outcomes and
    the away team's past away outcomes. Both retain HOME/DRAW/AWAY orientation
    of those historical fixtures. Each receives prior_strength pseudo-matches
    distributed according to A. Unseen teams revert to A. Parameters are fixed
    before replay, never selected using evaluation outcomes.
    """
    if not isinstance(model, Baseline) or not isinstance(target, FixtureTarget):
        raise ValueError("Unknown baseline or invalid fixture target")
    if not isinstance(training, tuple):
        raise ValueError("Training observations must be an immutable tuple")
    for parameter in (smoothing, prior_strength):
        if isinstance(parameter, bool) or not isinstance(parameter, (int, float)) or not isfinite(parameter) or parameter <= 0:
            raise ValueError("Baseline smoothing and prior strength must be positive and finite")
    if any(row.competition_id != target.competition_id or row.fixture_id == target.fixture_id
           for row in training):
        raise ValueError("Training must belong to the target competition and exclude its own outcome")
    if len({row.fixture_id for row in training}) != len(training):
        raise ValueError("Training requires one as-of result per fixture")
    if model is Baseline.UNIFORM:
        return Probabilities(1 / 3, 1 / 3, 1 / 3)
    counts = [sum(row.outcome is outcome for row in training) for outcome in CATEGORY_ORDER]
    league = tuple((count + smoothing) / (len(training) + 3 * smoothing) for count in counts)
    if model is Baseline.LEAGUE_EMPIRICAL:
        return Probabilities(*league)
    home = tuple(row for row in training if row.home_team_id == target.home_team_id)
    away = tuple(row for row in training if row.away_team_id == target.away_team_id)

    def posterior(rows):
        return tuple((sum(row.outcome is category for row in rows) + prior_strength * prior)
                     / (len(rows) + prior_strength) for category, prior in zip(CATEGORY_ORDER, league))

    return Probabilities(*(fsum(pair) / 2 for pair in zip(posterior(home), posterior(away))))


@dataclass(frozen=True, slots=True)
class EvaluatedPrediction:
    prediction: Prediction
    actual: ResultObservation
    score: Score


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    protocol: WalkForwardProtocol
    computed_at: datetime
    predictions: tuple[Prediction, ...]
    evaluations: tuple[EvaluatedPrediction, ...]
    skipped: tuple[tuple[str, str], ...]

    def to_dict(self, *, include_predictions: bool = True) -> dict:
        registry = {}
        for prediction in self.predictions:
            for item in prediction.input_evidence:
                registry[item.record_id] = {"role": item.role, "availability": item.availability.to_dict()}
        for evaluation in self.evaluations:
            row = evaluation.actual
            registry.setdefault(row.record_id, {"role": "SCORING_OUTCOME", "availability": row.availability.to_dict()})
        return {
            "schema_version": "1.0", "protocol": self.protocol.to_dict(),
            "computed_at": self.computed_at.isoformat(), "issuance_kind": "HISTORICAL_REPLAY",
            "temporal_mode": self.protocol.temporal_mode.value,
            "inference_status": ["DEMONSTRATION_ONLY", "INSUFFICIENT_SAMPLE_FOR_STRONG_INFERENCE"],
            "prediction_count": len(self.predictions),
            "evaluation_fixture_count": len({item.actual.fixture_id for item in self.evaluations}),
            "skipped": [{"fixture_id": fixture_id, "reason": reason} for fixture_id, reason in self.skipped],
            "model_results": [_summarize(model, self.evaluations, self.protocol.calibration_bins)
                              for model in Baseline],
            "evidence_registry": registry,
            "predictions": [item.to_dict(include_evidence=False) for item in self.predictions] if include_predictions else [],
            "scoring_pairs": [{"prediction_id": item.prediction.prediction_id,
                               "outcome_record_id": item.actual.record_id, "outcome": item.actual.outcome.value}
                              for item in self.evaluations] if include_predictions else [],
        }


def _summarize(model: Baseline, evaluations: tuple[EvaluatedPrediction, ...], bins: int) -> dict:
    rows = tuple(row for row in evaluations if row.prediction.model.model_id is model)
    count = len(rows)
    infinite = any(row.score.log_loss_infinite for row in rows)
    calibration = []
    for category_index, category in enumerate(CATEGORY_ORDER):
        for bucket in range(bins):
            members = tuple(row for row in rows
                            if min(int(row.prediction.probabilities.values[category_index] * bins), bins - 1) == bucket)
            calibration.append({
                "category": category.value, "bucket": bucket, "lower": bucket / bins,
                "upper": (bucket + 1) / bins, "upper_inclusive": bucket == bins - 1,
                "count": len(members),
                "mean_probability": fsum(row.prediction.probabilities.values[category_index] for row in members) / len(members) if members else None,
                "observed_frequency": sum(row.actual.outcome is category for row in members) / len(members) if members else None,
            })
    return {
        "model_id": model.value, "model_version": "1.0.0", "benchmark": Baseline.UNIFORM.value,
        "evaluation_matches": count,
        "metrics": {
            Metric.LOG_LOSS.value: None if not count or infinite else fsum(row.score.log_loss for row in rows) / count,
            Metric.RPS.value: fsum(row.score.rps for row in rows) / count if count else None,
            Metric.MULTICLASS_BRIER.value: fsum(row.score.brier for row in rows) / count if count else None,
            Metric.ACCURACY_SECONDARY.value: sum(row.score.correct for row in rows) / count if count else None,
        },
        "log_loss_infinite": infinite, "zero_probability_policy": "INFINITE_LOSS_REPORTED_AS_NULL_WITH_FLAG",
        "brier_per_class": {category.value: fsum(row.score.brier_components[i] for row in rows) / count if count else None
                            for i, category in enumerate(CATEGORY_ORDER)},
        "calibration": calibration, "accuracy_tie_policy": "FIRST_IN_HOME_DRAW_AWAY_ORDER",
    }


def run_walk_forward(fixtures: tuple[FixtureTarget, ...], results: tuple[ResultObservation, ...],
                     protocol: WalkForwardProtocol, *, computed_at: datetime) -> EvaluationReport:
    """Replay fixed expanding windows. Scoring labels are joined only afterward.

    Results must be complete strictly before a decision horizon and available
    at or before it. That rule also prevents outcomes at a shared target time
    leaking into another prediction. Revisions resolve at each horizon, not at
    replay execution time. Actual labels use the latest revision available at
    computed_at, retaining their own availability metadata separately.
    """
    _aware(computed_at, "computed_at")
    if not isinstance(fixtures, tuple) or not isinstance(results, tuple):
        raise ValueError("Replay inputs must be immutable tuples")
    if not isinstance(protocol, WalkForwardProtocol):
        raise ValueError("Replay needs a declared protocol")
    if len({fixture.fixture_id for fixture in fixtures}) != len(fixtures):
        raise ValueError("One target schedule per fixture is required; resolve schedule revisions first")
    if len({row.record_id for row in results}) != len(results):
        raise ValueError("Outcome record IDs must be unique")
    if len({fixture.schedule_record_id for fixture in fixtures}) != len(fixtures):
        raise ValueError("Schedule evidence IDs must be unique")
    if {fixture.schedule_record_id for fixture in fixtures} & {row.record_id for row in results}:
        raise ValueError("Schedule and result evidence IDs must not collide")
    if any(item.competition_id != protocol.competition_id for item in (*fixtures, *results)):
        raise ValueError("A phase-A protocol evaluates exactly one competition")
    if any(item.schedule_availability.ingested_at > computed_at for item in fixtures) or any(
            row.availability.ingested_at > computed_at for row in results):
        raise ValueError("Replay cannot consume evidence acquired after its actual computed_at")
    by_record = {row.record_id: row for row in results}
    revisions = tuple(row.timed_revision() for row in results)
    # Validate the complete revision graph even if all candidates are skipped.
    final_revisions = as_of(revisions, computed_at, TemporalMode.RECONSTRUCTED_PIT)
    final_results = {revision.entity_key: by_record[revision.record_id] for revision in final_revisions}
    predictions, skipped = [], []
    ordered = sorted(fixtures, key=lambda fixture: (protocol.decision_horizon.target(fixture.kickoff_at), fixture.fixture_id))
    for fixture in ordered:
        target = protocol.decision_horizon.target(fixture.kickoff_at)
        if not protocol.evaluation_period.start_at <= target < protocol.evaluation_period.end_at:
            skipped.append((fixture.fixture_id, "OUTSIDE_EVALUATION_PERIOD"))
            continue
        if target > computed_at:
            raise ValueError("Historical replay cannot contain future decision horizons")
        if target > fixture.kickoff_at:
            raise ValueError("A pre-match decision horizon cannot occur after kickoff")
        if not fixture.schedule_availability.eligible(target, protocol.temporal_mode):
            skipped.append((fixture.fixture_id, "SCHEDULE_UNAVAILABLE_AT_HORIZON"))
            continue
        training = tuple(sorted((by_record[revision.record_id] for revision in
                                as_of(revisions, target, protocol.temporal_mode)
                                if by_record[revision.record_id].event_completed_at < target
                                and revision.entity_key != fixture.fixture_id), key=lambda row: row.record_id))
        if len(training) < protocol.min_training_matches:
            skipped.append((fixture.fixture_id, "INSUFFICIENT_TRAINING_HISTORY"))
            continue
        evidence = (InputEvidence(fixture.schedule_record_id, "FIXTURE_SCHEDULE", fixture.schedule_availability),
                    *(InputEvidence(row.record_id, "TRAINING_RESULT", row.availability) for row in training))
        evidence_hash = _hash([{"record_id": row.record_id, "availability": row.availability.to_dict()} for row in evidence])
        for model in Baseline:
            probabilities = baseline_probabilities(model, training, fixture, smoothing=protocol.smoothing,
                                                   prior_strength=protocol.prior_strength)
            feature_hash = _hash({"protocol": protocol.to_dict(), "model": model.value,
                                  "fixture": {"fixture_id": fixture.fixture_id, "home": fixture.home_team_id,
                                              "away": fixture.away_team_id},
                                  "training": [{"record_id": row.record_id, "fixture_id": row.fixture_id,
                                                "home": row.home_team_id, "away": row.away_team_id,
                                                "outcome": row.outcome.value} for row in training],
                                  "evidence_snapshot_id": evidence_hash})
            prediction_id = _hash({"fixture_id": fixture.fixture_id, "model": model.value,
                                   "model_version": "1.0.0", "target": target.isoformat(),
                                   "feature_snapshot_id": feature_hash})
            predictions.append(Prediction(prediction_id, fixture.fixture_id, ModelIdentity(model), probabilities,
                                          target, computed_at, protocol.decision_horizon, feature_hash,
                                          evidence_hash, protocol.temporal_mode, evidence))
    # Only after all predictions are frozen do labels enter the scoring stage.
    evaluations = []
    target_by_id = {fixture.fixture_id: fixture for fixture in fixtures}
    for prediction in predictions:
        actual = final_results.get(prediction.fixture_id)
        if actual is None or actual.event_completed_at > computed_at:
            continue
        fixture = target_by_id[prediction.fixture_id]
        if (actual.home_team_id, actual.away_team_id) != (fixture.home_team_id, fixture.away_team_id):
            raise ValueError("Scoring outcome teams disagree with canonical fixture teams")
        if actual.event_completed_at <= prediction.prediction_issued_at:
            raise ValueError("Evaluation outcome must complete after its prediction horizon")
        evaluations.append(EvaluatedPrediction(prediction, actual, score_prediction(prediction.probabilities, actual.outcome)))
    return EvaluationReport(protocol, computed_at, tuple(predictions), tuple(evaluations), tuple(skipped))
