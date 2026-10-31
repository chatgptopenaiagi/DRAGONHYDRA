"""Present-time hypothetical calculations over retained archival quoted prices.

This is a scenario, not a historical prediction. User-provided probabilities and
risk parameters become available only at the time this function is run.
"""
import csv
from datetime import datetime, timezone
import io
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import random
import re
import uuid

from .market_signals import convert_odds
from . import football_data

VERSION = 'historical-price-scenario/1'
PRECISION = 34


def _time(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            raise ValueError('INVALID_TIMESTAMP') from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return parsed.astimezone(timezone.utc)


def _iso(value):
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('INVALID_NUMBER')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('INVALID_NUMBER') from None
    if not result.is_finite():
        raise ValueError('INVALID_NUMBER')
    return result


def _count(value, minimum, maximum):
    number = _number(value)
    if number != number.to_integral_value() or not minimum <= number <= maximum:
        raise ValueError('INVALID_INTEGER_BOUND')
    return int(number)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _verify_archival_source(quote, source):
    """Resolve the exact source fixture, column, outcome and provider label."""
    try:
        reader = csv.DictReader(io.StringIO(source.decode('utf-8-sig'), newline=''))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('SOURCE_BINDING_UNPROVED')
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error):
        raise ValueError('SOURCE_BINDING_UNPROVED') from None
    if any(None in row for row in rows):
        raise ValueError('SOURCE_BINDING_UNPROVED')
    outcome = quote['outcome'].lower()
    if outcome not in ('home', 'draw', 'away') or quote['odds_format'].lower() != 'decimal':
        raise ValueError('SOURCE_BINDING_UNPROVED')
    if quote['source_id'] == football_data.SOURCE_ID and quote['adapter_version'] == football_data.TRANSFORM_VERSION:
        event_id = quote['event_id']
        if not event_id.startswith('football-data:'):
            raise ValueError('SOURCE_BINDING_UNPROVED')
        source_event = event_id[len('football-data:'):]
        matches = []
        for row in rows:
            try:
                if football_data._source_event_id(row) == source_event:
                    matches.append(row)
            except ValueError:
                continue
        if len(matches) != 1:
            raise ValueError('SOURCE_BINDING_UNPROVED')
        row = matches[0]
        label = quote.get('source_provider_label')
        phase = quote.get('quote_phase')
        provider = football_data.FIELDS.get(label, {})
        fields = provider.get(phase)
        if not fields:
            raise ValueError('SOURCE_BINDING_UNPROVED')
        field = fields[football_data.OUTCOMES.index(outcome)]
        expected_id = ':'.join((quote['source_hash'], source_event, field))
        checks = [quote.get('source_column') == field, quote['provider_id'] == 'football-data-label:' + label,
                  quote.get('feed_id') == 'football-data-shared-archive', quote.get('provider_mapping_verified') is False, quote['acquisition_id'] == expected_id,
                  quote['competition'] == row.get('Div', '').strip(), quote['home'] == row.get('HomeTeam', '').strip(),
                  quote['away'] == row.get('AwayTeam', '').strip(), quote.get('source_match_date') == row.get('Date'),
                  quote.get('source_match_time') == (row.get('Time') or None),
                  quote['odds_original'] == row.get(field, '').strip()]
    else:
        raise ValueError('SOURCE_BINDING_UNPROVED')
    # The adapters intentionally do not infer these source definitions.
    checks.extend([quote['market_type'] == '1x2', quote['period'] == 'unknown',
                   quote['status'] == 'unknown', quote['settlement'] == 'unknown',
                   quote.get('line') is None, quote.get('quote_time_known') is False,
                   quote.get('synchronization_proven') is False])
    if not all(checks):
        raise ValueError('SOURCE_BINDING_UNPROVED')


def _quote(quote, cutoff, source):
    if not isinstance(quote, dict):
        raise ValueError('QUOTE_REQUIRED')
    if quote.get('data_origin') != 'imported_historical' or quote.get('clock_mode') != 'operational':
        raise ValueError('OPERATIONAL_ARCHIVAL_QUOTE_REQUIRED')
    for field in ('evidence_id', 'source_id', 'source_hash', 'acquisition_id', 'provider_id',
                  'adapter_version', 'event_id', 'competition', 'home', 'away', 'market_type',
                  'period', 'status', 'settlement', 'outcome', 'odds_original', 'odds_format'):
        if not isinstance(quote.get(field), str) or not quote[field].strip():
            raise ValueError('INCOMPLETE_QUOTE_EVIDENCE')
    if not re.fullmatch(r'[0-9a-f]{64}', quote['source_hash']):
        raise ValueError('INVALID_SOURCE_HASH')
    if not isinstance(source, bytes) or hashlib.sha256(source).hexdigest() != quote['source_hash']:
        raise ValueError('SOURCE_HASH_MISMATCH')
    identity = [quote['source_id'], quote['acquisition_id'], quote['outcome']]
    if hashlib.sha256(_bytes(identity)).hexdigest() != quote['evidence_id']:
        raise ValueError('QUOTE_IDENTITY_MISMATCH')
    received = _time(quote.get('received_at'))
    persisted = _time(quote.get('persisted_at'))
    usable = _time(quote.get('usable_at'))
    if not received <= persisted <= usable:
        raise ValueError('INVALID_AVAILABILITY_ORDER')
    if usable > cutoff:
        raise ValueError('QUOTE_NOT_AVAILABLE_AT_CUTOFF')
    published = quote.get('source_published_at')
    if published is not None and _time(published) > received:
        raise ValueError('SOURCE_PUBLICATION_AFTER_RECEIPT')
    if quote['home'].casefold() == quote['away'].casefold():
        raise ValueError('AMBIGUOUS_PARTICIPANTS')
    _verify_archival_source(quote, source)
    return convert_odds(quote['odds_original'], quote['odds_format'])


def _metric(value, units, evidence_ids, formula, **additional):
    return {'value': str(value), 'units': units, 'evidence_ids': sorted(set(evidence_ids)),
            'transformation': {'version': VERSION, 'formula': formula, 'precision': PRECISION}, **additional}


def verify_archived_quote(quote, cutoff, *, raw_source):
    """Verify a stored quote against its retained source before reporting it."""
    return _quote(quote, _time(cutoff), raw_source)


def price_scenario(quote, probability, cutoff, *, raw_source, fraction='0.25', cap='0.02',
                   bankroll='1000', stake_fraction='0.02', trials=1000, steps=20, seed=42,
                   scenario_source='user_supplied'):
    """Evaluate one retained archival quote under current user-supplied assumptions.

    `cutoff` is the time by which the imported quote must have been usable. The
    probability and simulation configuration originate at actual invocation time;
    they are not claimed to have existed at the evidence cutoff. Their canonical
    JSON and hash are included in the result. Quote times remain unknown.
    """
    run_time = datetime.now(timezone.utc)
    decision = _time(cutoff)
    if decision > run_time:
        raise ValueError('EVIDENCE_CUTOFF_IN_FUTURE')
    price = _quote(quote, decision, raw_source)
    if scenario_source not in ('cli_default', 'user_supplied'):
        raise ValueError('INVALID_SCENARIO_SOURCE')
    prob, frac, ceiling = map(_number, (probability, fraction, cap))
    start, stake = map(_number, (bankroll, stake_fraction))
    if not 0 <= prob <= 1:
        raise ValueError('PROBABILITY_OUT_OF_RANGE')
    if not 0 <= frac <= 1 or not 0 <= ceiling <= 1 or not 0 <= stake <= 1 or start <= 0:
        raise ValueError('INVALID_RISK_CONFIGURATION')
    trial_count = _count(trials, 1, 10000)
    horizon = _count(steps, 1, 10000)
    seed_number = _count(seed, 0, 2**63 - 1)
    if trial_count * horizon > 1000000:
        raise ValueError('SIMULATION_BUDGET_EXCEEDED')
    scenario_time = _iso(run_time)
    config = {'scenario_source': scenario_source, 'probability_original': str(probability), 'fraction_original': str(fraction),
              'cap_original': str(cap), 'bankroll_original': str(bankroll),
              'stake_fraction_original': str(stake_fraction), 'trials': trial_count,
              'steps': horizon, 'seed': seed_number,
              'assumptions': ['binary win/loss; no voids or pushes', 'no fees, taxes, limits, correlation or line changes',
                              'scenario probability remains unchanged', 'IID outcomes for simulation']}
    config_raw = _bytes(config)
    config_hash = hashlib.sha256(config_raw).hexdigest()
    config_id = 'user-scenario:' + config_hash
    ids = [quote['evidence_id'], config_id]
    with localcontext() as ctx:
        ctx.prec = PRECISION
        implied = Decimal(1) / price
        expected = prob * price - 1
        raw_kelly = expected / (price - 1)
        capped_kelly = min(ceiling, max(Decimal(0), raw_kelly) * frac)
        rng = random.Random(seed_number)
        outcomes, drawdowns, zero_count = [], [], 0
        for _ in range(trial_count):
            balance = high = start
            worst = Decimal(0)
            for _ in range(horizon):
                wager = balance * stake
                win = Decimal(rng.getrandbits(53)) < prob * Decimal(2**53)
                balance = balance + wager * (price - 1) if win else balance - wager
                high = max(high, balance)
                worst = max(worst, (high - balance) / high)
            outcomes.append(balance)
            drawdowns.append(worst)
            zero_count += int(balance == 0)
        mean = sum(outcomes, Decimal(0)) / trial_count
        variance = (sum(((x - mean) ** 2 for x in outcomes), Decimal(0)) / (trial_count - 1)
                    if trial_count > 1 else None)
        metrics = {
            'decimal_odds': _metric(price, 'decimal odds', [quote['evidence_id']], 'convert(original odds, original format)'),
            'raw_implied_probability': _metric(implied, 'probability fraction', [quote['evidence_id']], '1 / decimal odds'),
            'expected_net_return_per_unit': _metric(expected, 'stake fraction', ids, 'scenario probability * decimal odds - 1'),
            'raw_kelly': _metric(raw_kelly, 'bankroll fraction', ids, '(scenario probability * decimal odds - 1) / (decimal odds - 1)'),
            'fractional_capped_kelly': _metric(capped_kelly, 'bankroll fraction', ids, 'min(cap, max(0, raw Kelly) * fraction)'),
            'mean_final_bankroll': _metric(mean, 'bankroll units', ids, 'mean of seeded IID simulated final balances'),
            'sample_variance_final_bankroll': (_metric(variance, 'bankroll units squared', ids, 'unbiased sample variance of final balances')
                                               if variance is not None else {'value': None, 'reason': 'INSUFFICIENT_TRIALS', 'evidence_ids': sorted(ids), 'transformation': {'version': VERSION}}),
            'mean_max_drawdown': _metric(sum(drawdowns, Decimal(0)) / trial_count, 'fraction', ids, 'mean of maximum peak-to-trough drawdown'),
            'zero_balance_frequency': _metric(Decimal(zero_count) / trial_count, 'fraction', ids, 'zero final balances / trial count'),
        }
    return {
        'run_id': str(uuid.uuid4()), 'replay_mode': 'PRESENT_TIME_SCENARIO',
        'actual_run_time': scenario_time, 'evidence_cutoff': _iso(decision),
        'scenario_assumed_at': scenario_time, 'data_origin': 'imported_historical',
        'quote_evidence': dict(quote),
        'configuration_evidence': {'evidence_id': config_id, 'source_id': ('cli-default-scenario' if scenario_source == 'cli_default' else 'user-supplied-scenario'),
            'source_hash': config_hash, 'canonical_json': config_raw.decode('utf-8'), 'data_origin': ('configuration' if scenario_source == 'cli_default' else 'user_supplied'),
            'received_at': scenario_time, 'persisted_at': None, 'usable_at': scenario_time,
            'transformation': VERSION, 'storage': 'included in report; persist report for later replay'},
        'metrics': metrics,
        'simulation': {'trials': trial_count, 'steps_per_trial': horizon, 'seed': seed_number,
                       'rng': 'Python random.Random.getrandbits(53)',
                       'evidence_ids': sorted(ids), 'version': VERSION},
        'assumptions': config['assumptions'],
        'uncertainty': ['The archived source does not establish the original quote time or current execution availability.',
                        'The supplied probability is a present-time scenario, not a probability known at the evidence cutoff.',
                        'Settlement and market status can be unknown; binary win/loss is an explicit assumption.',
                        'Simulation approximates the supplied probability on a 53-bit grid and assumes IID outcomes.'],
    }





