"""Explicit reconstructed historical demonstration from already retained bytes.

Default acquisition is a bounded read-only SQL query plus local hash lookup.
There is no fetch, DB write, source expansion, or genuine historical-clock claim.
"""

import argparse
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re

from ..config import PROJECT_ROOT
from ..web.json_api import parse_json
from .entities import (Competition, CrosswalkRecord, EntityRegistry, EntityType, Fixture,
                       ResolutionMethod, ReviewState, Team, competition_id, fixture_id, team_id)
from .evaluation import (EvaluationPeriod, FixtureTarget, Outcome, ResultObservation,
                         WalkForwardProtocol, run_walk_forward)
from .temporal import Availability, DecisionHorizon, TemporalMode, aware_utc


_MAX_BYTES = 2_000_000
_EXPECTED_URL = "https://raw.githubusercontent.com/openfootball/football.json/master/2023-24/en.1.json"
_ASSUMPTIONS = (
    "Historical import was genuinely captured in 2026, not at the historical decision horizons.",
    "Source local kickoff timezone is unverified. UTC day start is only a calendar-date decision proxy.",
    "Fixture schedule is assumed available one day before the reported match date; no publication proof exists.",
    "Event completion is conservatively represented by next UTC day start, not an observed final whistle.",
    "Final result is assumed available two days after reported match-date UTC midnight; not a measured delay.",
    "Declared source-name and round/team identity mappings are reconstructed now, not historically known IDs.",
    "One season and fixed illustrative assumptions are insufficient for strong inference or profitability claims.",
)


@dataclass(frozen=True)
class CaptureMetadata:
    source_id: str
    source_url: str
    content_hash: str
    observed_at: datetime
    retrieved_at: datetime
    ingested_at: datetime
    capture_basis: str

    def __post_init__(self):
        for field in ("source_id", "source_url", "capture_basis"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise ValueError(f"{field} must be nonempty text")
        if not isinstance(self.content_hash, str) or not re.fullmatch("[a-f0-9]{64}", self.content_hash):
            raise ValueError("content_hash must be SHA-256")
        for field in ("observed_at", "retrieved_at", "ingested_at"):
            object.__setattr__(self, field, aware_utc(getattr(self, field), field))
        if not self.observed_at <= self.retrieved_at <= self.ingested_at:
            raise ValueError("Capture chronology must remain observed <= retrieved <= ingested")

    def to_dict(self):
        return {"source_id": self.source_id, "source_url": self.source_url,
                "content_hash": self.content_hash, "observed_at": self.observed_at.isoformat(),
                "retrieved_at": self.retrieved_at.isoformat(), "ingested_at": self.ingested_at.isoformat(),
                "capture_basis": self.capture_basis}

    @classmethod
    def from_dict(cls, payload):
        fields = dict(payload)
        for name in ("observed_at", "retrieved_at", "ingested_at"):
            fields[name] = datetime.fromisoformat(fields[name])
        return cls(**fields)


@dataclass(frozen=True)
class HistoricalInputs:
    registry: EntityRegistry
    fixtures: tuple[FixtureTarget, ...]
    results: tuple[ResultObservation, ...]
    protocol: WalkForwardProtocol


def parse_historical_rows(raw: bytes) -> tuple[dict, ...]:
    """Bounded schema validation; source dates and final scores remain distinct."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= _MAX_BYTES:
        raise ValueError("Expected bounded retained raw bytes")
    document = parse_json(raw)
    if (not isinstance(document, dict) or document.get("name") != "English Premier League 2023/24"
            or not isinstance(document.get("matches"), list) or not 1 <= len(document["matches"]) <= 500):
        raise ValueError("This demonstration is bounded to OpenFootball English Premier League 2023/24")
    normalized = []
    identities = set()
    for row in document["matches"]:
        if not isinstance(row, dict):
            raise ValueError("Match must be an object")
        for key in ("round", "team1", "team2", "date"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError("Match needs explicit round, teams and calendar date")
        day = date.fromisoformat(row["date"])
        if not date(2023, 7, 1) <= day < date(2024, 7, 1):
            raise ValueError("Match date is outside the declared season")
        score = row.get("score", {}).get("ft") if isinstance(row.get("score"), dict) else None
        if not isinstance(score, list) or len(score) != 2 or any(type(value) is not int or value < 0 for value in score):
            raise ValueError("Historical evaluation requires an explicit valid final score")
        key = (row["round"], row["team1"], row["team2"])
        if key in identities or row["team1"] == row["team2"]:
            raise ValueError("Duplicate or ambiguous fixture identity requires review")
        identities.add(key)
        normalized.append({"round": row["round"], "home": row["team1"], "away": row["team2"],
                           "date": day.isoformat(), "home_score": score[0], "away_score": score[1]})
    return tuple(sorted(normalized, key=lambda row: (row["date"], row["round"], row["home"], row["away"])))


def build_historical_inputs(raw: bytes, capture: CaptureMetadata, *, computed_at: datetime,
                            min_training_matches: int = 50) -> HistoricalInputs:
    computed = aware_utc(computed_at, "computed_at")
    if computed < capture.ingested_at:
        raise ValueError("Computation cannot precede actual source ingestion")
    if sha256(raw).hexdigest() != capture.content_hash:
        raise ValueError("Retained raw content hash differs from capture metadata")
    rows = parse_historical_rows(raw)
    registry = EntityRegistry()
    competition = competition_id("openfootball", "en.1")
    registry.register(Competition(competition, "English Premier League"))
    mapping_valid_from = datetime(2023, 7, 1, tzinfo=timezone.utc)

    def crosswalk(key, name, kind, canonical):
        registry.append_crosswalk(CrosswalkRecord(
            "openfootball", key, name, kind, canonical, mapping_valid_from, None, computed,
            ResolutionMethod.DECLARED_ALIAS, 0.8, ReviewState.CONFIRMED))

    crosswalk("declared:en.1", "English Premier League", EntityType.COMPETITION, competition)
    teams = {}
    for name in sorted({row[key] for row in rows for key in ("home", "away")}):
        teams[name] = team_id("openfootball:en.1", name)
        registry.register(Team(teams[name], name))
        crosswalk("declared-name:" + name, name, EntityType.TEAM, teams[name])

    def availability(available_at, policy, reason):
        return Availability(TemporalMode.RECONSTRUCTED_PIT, available_at,
                            capture.observed_at, capture.retrieved_at, capture.ingested_at,
                            policy, "1.0.0", reason, 0.2, capture.source_url)

    fixtures, results = [], []
    for row in rows:
        explicit_key = json.dumps([row["round"], str(teams[row["home"]]), str(teams[row["away"]])],
                                  ensure_ascii=False, separators=(",", ":"))
        identity = fixture_id("openfootball", competition, "2023-24", explicit_key)
        registry.register(Fixture(identity, competition, "2023-24", teams[row["home"]], teams[row["away"]]))
        crosswalk("declared-round-teams:" + explicit_key,
                  f'{row["round"]}: {row["home"]} / {row["away"]}', EntityType.FIXTURE, identity)
        day_proxy = datetime.combine(date.fromisoformat(row["date"]), time(), timezone.utc)
        schedule = availability(day_proxy - timedelta(days=1), "FIXTURE_DATE_MINUS_1D_UTC_PROXY",
                                _ASSUMPTIONS[1] + " " + _ASSUMPTIONS[2] + " " + _ASSUMPTIONS[5])
        result = availability(day_proxy + timedelta(days=2), "RESULT_DATE_PLUS_2D_UTC_PROXY",
                              _ASSUMPTIONS[1] + " " + _ASSUMPTIONS[3] + " " + _ASSUMPTIONS[4]
                              + " " + _ASSUMPTIONS[5])
        fixtures.append(FixtureTarget(str(identity), str(competition), str(teams[row["home"]]),
                                      str(teams[row["away"]]), day_proxy, schedule,
                                      "schedule:" + str(identity) + ":" + capture.content_hash))
        outcome = Outcome.HOME if row["home_score"] > row["away_score"] else (
            Outcome.AWAY if row["away_score"] > row["home_score"] else Outcome.DRAW)
        results.append(ResultObservation("result:" + str(identity) + ":" + capture.content_hash,
                                         str(identity), str(competition), str(teams[row["home"]]),
                                         str(teams[row["away"]]), day_proxy + timedelta(days=1), outcome, result))
    horizon = DecisionHorizon("DAY_START_UTC_PROXY", offset_before_kickoff=timedelta(0))
    protocol = WalkForwardProtocol(
        "openfootball-en.1-2023-24-calendar-proxy-demonstration", "1.0.0", str(competition),
        TemporalMode.RECONSTRUCTED_PIT, horizon,
        EvaluationPeriod(min(row.kickoff_at for row in fixtures), max(row.kickoff_at for row in fixtures) + timedelta(days=1)),
        min_training_matches=min_training_matches, smoothing=1.0, prior_strength=5.0, calibration_bins=10)
    return HistoricalInputs(registry, tuple(fixtures), tuple(results), protocol)


def evaluate_historical(raw: bytes, capture: CaptureMetadata, *, computed_at: datetime,
                        min_training_matches: int = 50) -> dict:
    inputs = build_historical_inputs(raw, capture, computed_at=computed_at,
                                     min_training_matches=min_training_matches)
    report = run_walk_forward(inputs.fixtures, inputs.results, inputs.protocol, computed_at=computed_at).to_dict()
    summary = {
        "schema_version": "1.0", "source": capture.to_dict(), "raw_byte_count": len(raw),
        "temporal_mode": "RECONSTRUCTED_PIT", "capture_timestamps_backdated": False,
        "historical_strict_pit_eligible_records": 0,
        "inference_status": ["DEMONSTRATION_ONLY", "INSUFFICIENT_SAMPLE_FOR_STRONG_INFERENCE"],
        "canonical_competitions": 1,
        "canonical_teams": sum(isinstance(entity, Team) for entity in inputs.registry.entities),
        "canonical_fixtures": len(inputs.fixtures), "crosswalk_records": len(inputs.registry.crosswalks),
        "crosswalk_recorded_at": computed_at.isoformat(), "crosswalk_policy": "DECLARED_SOURCE_NAMES_AND_ROUND_TEAM_KEYS",
        "decision_horizon": "DAY_START_UTC_PROXY", "evaluation_fixture_count": report["evaluation_fixture_count"],
        "prediction_count": report["prediction_count"], "skipped_fixture_count": len(report["skipped"]),
        "min_training_matches": min_training_matches, "model_results": report["model_results"],
        "assumptions": list(_ASSUMPTIONS), "computed_at": computed_at.isoformat(),
        "issuance_kind": "HISTORICAL_REPLAY", "external_source_changes": "NONE; retained bytes only",
        "packages_added": [],
    }
    protocol = {**inputs.protocol.to_dict(), "assumptions": list(_ASSUMPTIONS),
                "source": capture.to_dict(), "event_time_semantics": "UNVERIFIED_CALENDAR_DAY_UTC_PROXY",
                "outcome_usage": "TRAINING_ONLY_AFTER_ASSUMED_AVAILABILITY; TARGET_LABEL_JOINED_AFTER_PREDICTION",
                "identity_mode": "RECONSTRUCTED_DECLARED_MAPPING_CREATED_AT_COMPUTED_AT"}
    return {"registry": inputs.registry.to_dict(), "report": report, "protocol": protocol, "summary": summary}


def _retained_source(computed_at: datetime) -> tuple[bytes, CaptureMetadata]:
    from ..storage.intelligence import IntelligenceStore
    records = IntelligenceStore().fixtures_as_of(computed_at.isoformat(), limit=500)
    rows = [row for row in records if row.get("source_id") == "openfootball" and row.get("source_url") == _EXPECTED_URL]
    if len(rows) != 380 or any(row.get("synthetic") is not False for row in rows):
        raise ValueError("Expected exactly the existing 380 nonsynthetic 2023-24 OpenFootball SQL fixtures")
    hashes = {row["content_hash"] for row in rows}
    if len(hashes) != 1:
        raise ValueError("Mixed raw versions require explicit reconciliation before evaluation")
    expected = next(iter(hashes))
    raw = None
    for folder in (PROJECT_ROOT / "runtime/handoff/browser_downloads", PROJECT_ROOT / "runtime/checkpoints"):
        for path in sorted(folder.rglob("*")):
            if path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= _MAX_BYTES:
                content = path.read_bytes()
                if sha256(content).hexdigest() == expected:
                    raw = content
                    break
        if raw is not None:
            break
    if raw is None:
        raise ValueError("Original raw bytes are unavailable; this runner will not recreate historical evidence by fetching")
    normalized = parse_historical_rows(raw)
    sql_facts = {(row["round"], row["match_date"], row["home_team"], row["away_team"],
                  row["home_score"], row["away_score"]) for row in rows}
    raw_facts = {(row["round"], row["date"], row["home"], row["away"],
                  row["home_score"], row["away_score"]) for row in normalized}
    if len(sql_facts) != 380 or sql_facts != raw_facts:
        raise ValueError("Retained source facts differ from read-only SQL historical records")
    capture = CaptureMetadata("openfootball", _EXPECTED_URL, expected,
                              max(datetime.fromisoformat(row["observed_at"]) for row in rows),
                              max(datetime.fromisoformat(row["retrieved_at"]) for row in rows),
                              datetime.now(timezone.utc),
                              "ORIGINAL_SQL_CAPTURE_CLOCKS_AND_HASH_VERIFIED_RETAINED_BYTES; "
                              "INGESTED_AT_IS_CURRENT_DERIVED_SCIENTIFIC_INPUT_CONSTRUCTION_NOT_ORIGINAL_DB_COMMIT")
    return raw, capture


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory within runtime/checkpoints")
    parser.add_argument("--raw-file", type=Path, help="Retained bytes for portable replay, never an acquisition URL")
    parser.add_argument("--capture-metadata", type=Path, help="Saved CaptureMetadata JSON matching --raw-file")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to((PROJECT_ROOT / "runtime/checkpoints").resolve()) or output.exists():
        raise ValueError("Output must be a new checkpoint directory; historical evidence will not be overwritten")
    if bool(args.raw_file) != bool(args.capture_metadata):
        raise ValueError("Portable replay requires both --raw-file and --capture-metadata")
    query_at = datetime.now(timezone.utc)
    if args.raw_file:
        if args.raw_file.stat().st_size > _MAX_BYTES:
            raise ValueError("Raw file exceeds bounded input size")
        raw = args.raw_file.read_bytes()
        capture = CaptureMetadata.from_dict(json.loads(args.capture_metadata.read_text(encoding="utf-8")))
    else:
        raw, capture = _retained_source(query_at)
    computed = datetime.now(timezone.utc)
    artifacts = evaluate_historical(raw, capture, computed_at=computed)
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, payload in {**artifacts, "capture-metadata": capture.to_dict()}.items():
        content = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        path = output / f"{name}.json"
        with path.open("xb") as stream:
            stream.write(content)
        hashes[path.name] = {"sha256": sha256(content).hexdigest(), "byte_count": len(content)}
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"computed_at": computed.isoformat(), "files": hashes, "raw_hash": capture.content_hash}, stream, indent=2)
    compact = {key: value for key, value in artifacts["summary"].items() if key != "model_results"}
    compact["model_results"] = [{key: value for key, value in model.items() if key != "calibration"}
                                for model in artifacts["summary"]["model_results"]]
    print(json.dumps(compact, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
