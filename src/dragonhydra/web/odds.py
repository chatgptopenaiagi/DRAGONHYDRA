from dataclasses import dataclass
from datetime import datetime, timezone
import math
from .contracts import PipelineError, timestamp, public_url


def probability(decimal_odds):
    if isinstance(decimal_odds, bool) or not isinstance(decimal_odds, (float, int)) or not math.isfinite(decimal_odds) or decimal_odds <= 1:
        raise PipelineError('INVALID_ODDS')
    return 1 / decimal_odds


def overround(prices):
    if len(prices) < 2:
        raise PipelineError('INCOMPLETE_MARKET')
    return sum(probability(p) for p in prices) - 1


def normalized_probabilities(prices):
    overround(prices)
    probs = [probability(p) for p in prices]
    return [p / sum(probs) for p in probs]


def movement(old, new, old_at, new_at):
    probability(old)
    probability(new)
    seconds = (timestamp(new_at) - timestamp(old_at)).total_seconds()
    if seconds < 0:
        raise PipelineError('INVALID_TIMESTAMP_ORDER')
    return {'odds_delta': new - old, 'percentage_movement': (new - old) / old * 100,
            'seconds_between': seconds}


@dataclass(frozen=True)
class OddsObservation:
    observation_id: str
    fixture_id: str
    source_id: str
    bookmaker: str
    market_type: str
    market_key: str
    selection: str
    line_value: float | None
    decimal_odds: float
    implied_probability: float
    observed_at: str
    available_at: str
    event_at: str | None
    expires_at: str | None
    currency_if_relevant: str | None
    market_status: str
    source_url: str
    source_hash: str
    confidence: float
    verification_state: str
    updated_at: str
    target_as_of_at: str | None = None
    synthetic: bool = False

    def __post_init__(self):
        p = probability(self.decimal_odds)
        if not math.isclose(self.implied_probability, p, rel_tol=1e-12):
            raise PipelineError('INVALID_IMPLIED_PROBABILITY')
        if self.market_type not in ('h2h', 'totals', 'spreads') or not self.market_key:
            raise PipelineError('UNKNOWN_MARKET')
        if self.market_status not in ('OPEN', 'SUSPENDED', 'CLOSED', 'UNKNOWN'):
            raise PipelineError('UNKNOWN_MARKET_STATUS')
        if self.verification_state not in ('CONFIRMED', 'CORROBORATED', 'UNCONFIRMED', 'STALE', 'CONFLICTING', 'REJECTED'):
            raise PipelineError('INVALID_VERIFICATION_STATE')
        if self.line_value is not None and not math.isfinite(self.line_value):
            raise PipelineError('INVALID_LINE')
        if self.market_type in ('totals', 'spreads') and self.line_value is None:
            raise PipelineError('MISSING_LINE')
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise PipelineError('INVALID_CONFIDENCE')
        for name in ('observation_id', 'fixture_id', 'source_id', 'bookmaker', 'selection'):
            if not getattr(self, name):
                raise PipelineError('MISSING_ODDS_FIELD')
        public_url(self.source_url)
        import re
        if not re.fullmatch('[a-f0-9]{64}', self.source_hash):
            raise PipelineError('INVALID_HASH')
        validate_temporal(self.observed_at, self.available_at, self.updated_at, self.target_as_of_at)
        if self.event_at:
            timestamp(self.event_at)
        if self.expires_at and timestamp(self.expires_at) < timestamp(self.observed_at):
            raise PipelineError('INVALID_TIMESTAMP_ORDER')


def validate_temporal(observed_at, available_at, updated_at, target_as_of_at=None):
    observed, available, updated = map(timestamp, (observed_at, available_at, updated_at))
    if not observed <= available <= updated or updated > datetime.now(timezone.utc):
        raise PipelineError('INVALID_TIMESTAMP_ORDER')
    if target_as_of_at is not None and max(observed, available, updated) > timestamp(target_as_of_at):
        raise PipelineError('FUTURE_LEAKAGE')


def quote_identity(o):
    return (o.fixture_id, o.source_id, o.bookmaker, o.market_key, o.selection, o.line_value, o.observed_at)


def compare_quotes(a, b):
    if quote_identity(a) != quote_identity(b):
        return 'DISTINCT'
    return 'DUPLICATE' if (a.decimal_odds, a.market_status) == (b.decimal_odds, b.market_status) else 'CONFLICTING_DATA'
