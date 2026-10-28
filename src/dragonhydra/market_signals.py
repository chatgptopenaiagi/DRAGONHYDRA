"""Deterministic, provenance-linked point-in-time quoted-price signals.

Raw implied probabilities are price transforms, not estimates of true chances.
The default margin removal is proportional and makes no calibration claim.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from itertools import combinations
from fractions import Fraction
import re

VERSION = 'market-signals/1'
PRECISION = 34
SCOPE = ('event_id', 'competition', 'home', 'away', 'market_type', 'period',
         'status', 'settlement', 'line')
ONE_X_TWO = frozenset(('home', 'draw', 'away'))
TOTAL_MARKETS = frozenset(('totals', 'total', 'over_under'))
TOTAL_OUTCOMES = frozenset(('over', 'under'))


def _decimal(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('INVALID_ODDS')
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('INVALID_ODDS') from None
    if not number.is_finite():
        raise ValueError('INVALID_ODDS')
    return number


def convert_odds(original, odds_format):
    """Convert a decimal, American, or fractional quotation to decimal odds."""
    if not isinstance(odds_format, str):
        raise ValueError('UNKNOWN_ODDS_FORMAT')
    fmt = odds_format.strip().lower()
    with localcontext() as ctx:
        ctx.prec = PRECISION
        if fmt == 'decimal':
            result = _decimal(original)
        elif fmt == 'american':
            amount = _decimal(original)
            if amount != amount.to_integral_value() or abs(amount) < 100:
                raise ValueError('INVALID_ODDS')
            result = 1 + (amount / 100 if amount > 0 else Decimal(100) / -amount)
        elif fmt == 'fractional':
            match = re.fullmatch(r'\s*(\d+)\s*/\s*(\d+)\s*', str(original))
            if not match:
                raise ValueError('INVALID_ODDS')
            numerator, denominator = map(int, match.groups())
            if numerator <= 0 or denominator <= 0:
                raise ValueError('INVALID_ODDS')
            result = 1 + Decimal(numerator) / Decimal(denominator)
        else:
            raise ValueError('UNKNOWN_ODDS_FORMAT')
        if not result.is_finite() or result <= 1:
            raise ValueError('INVALID_ODDS')
        return +result


def implied_probability(decimal_odds):
    with localcontext() as ctx:
        ctx.prec = PRECISION
        value = _decimal(decimal_odds)
        if value <= 1:
            raise ValueError('INVALID_ODDS')
        return +(Decimal(1) / value)


def _at(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (ValueError, TypeError):
        raise ValueError('INVALID_TIMESTAMP') from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return stamp.astimezone(timezone.utc)


def _line(value):
    if value is None or value == '':
        return None
    n = _decimal(value)
    # Preserve exact line identity without Decimal.normalize() context rounding.
    if len(n.as_tuple().digits) > 100 or abs(n.as_tuple().exponent) > 100:
        raise ValueError('INVALID_LINE')
    text = format(n, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return '0' if n == 0 else text


def _scope(row):
    result = []
    for key in SCOPE:
        item = row.get(key)
        if key == 'line':
            item = _line(item)
        elif not isinstance(item, str) or not item.strip():
            raise ValueError('INCOMPLETE_MARKET_IDENTITY')
        else:
            item = item.strip()
        result.append(item)
    if result[2].casefold() == result[3].casefold():
        raise ValueError('AMBIGUOUS_PARTICIPANTS')
    if result[6] not in ('pregame', 'live', 'unknown'):
        raise ValueError('INVALID_STATUS')
    if result[4].lower() in TOTAL_MARKETS.union(('spreads', 'handicap')) and result[-1] is None:
        raise ValueError('MISSING_LINE')
    return tuple(result)


def _metric(value, units, ids, formula, **more):
    return {'value': str(value), 'units': units, 'evidence_ids': sorted(set(ids)),
            'transformation': {'version': VERSION, 'formula': formula}, **more}


def _unavailable(reason, ids=()):
    return {'value': None, 'reason': reason, 'evidence_ids': sorted(set(ids)),
            'transformation': {'version': VERSION}}


def _scope_dict(scope):
    return dict(zip(SCOPE, scope))


def _unverified_scope(scope):
    return any(str(scope[index]).lower() in ('unknown', 'unverified') for index in (1, 4, 5, 6, 7))


def _seconds(delta):
    return (Decimal(delta.days) * 86400 + Decimal(delta.seconds) +
            Decimal(delta.microseconds) / Decimal(1000000))


def compute_signals(observations, cutoff, *, max_age_seconds=600,
                    alignment_seconds=120, lookback_seconds=86400):
    """Calculate latest known streams; never combine unrelated upstream feeds.

    Clocks use original system quote receipt for age and movement; receipt and
    availability of a later correction only gate when that revision may be seen.
    Margin math requires a complete 1X2 or half-unit over/under outcome set.
    """
    decision = _at(cutoff)
    for value in (max_age_seconds, alignment_seconds, lookback_seconds):
        if type(value) is not int or value < 0:
            raise ValueError('INVALID_WINDOW')
    rows, flags = [], []
    for original in observations:
        if not isinstance(original, dict):
            continue
        row = dict(original)
        # Unknown or future usability is never used, even for a quality flag.
        try:
            usable = _at(row.get('usable_at'))
        except ValueError:
            continue
        if usable > decision:
            continue
        eid = row.get('evidence_id')
        if not isinstance(eid, str) or not eid:
            raise ValueError('MISSING_EVIDENCE_ID')
        try:
            received, persisted = _at(row['received_at']), _at(row['persisted_at'])
            if received > persisted or persisted > usable:
                raise ValueError('INVALID_AVAILABILITY_ORDER')
            if row.get('supersedes_acquisition_id') and not row.get('effective_market_received_at'):
                raise ValueError('CORRECTION_ORIGINAL_TIME_UNAVAILABLE')
            effective = _at(row.get('effective_market_received_at') or row['received_at'])
            if effective > received:
                raise ValueError('INVALID_MARKET_TIME')
            scope = _scope(row)
            for key in ('source_id', 'provider_id', 'snapshot_id', 'outcome', 'data_origin'):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError('INCOMPLETE_MARKET_IDENTITY')
            if row['data_origin'] not in ('synthetic', 'captured_real', 'imported_historical'):
                raise ValueError('INVALID_DATA_ORIGIN')
            price = convert_odds(row.get('odds_original'), row.get('odds_format'))
        except (KeyError, ValueError) as exc:
            flags.append({'code': str(exc).strip("'"), 'evidence_ids': [eid]})
            continue
        row.update(_receipt=received, _effective=effective, _usable=usable, _scope=scope,
                   _price=price, _probability=implied_probability(price))
        rows.append(row)
    rows.sort(key=lambda r: (r['_effective'], r['_usable'], r['source_id'], r['snapshot_id'], r['evidence_id']))
    streams, snapshots = defaultdict(list), defaultdict(list)
    for row in rows:
        feed = row.get('feed_id') or None
        phase = row.get('quote_phase') if row['data_origin'] == 'imported_historical' else None
        key = (row['_scope'], row['provider_id'], row['source_id'], feed, row['data_origin'], phase, row['outcome'].lower())
        streams[key].append(row)
        snapshots[(row['_scope'], row['provider_id'], row['source_id'], feed, row['data_origin'], row['snapshot_id'])].append(row)
    quotes, moves, margins, divergences, best, coverage = [], [], [], [], [], []
    latest = defaultdict(list)
    conflicting_markets = set()
    with localcontext() as ctx:
        ctx.prec = PRECISION
        for (scope, provider, source, feed, origin, phase, outcome), stream in sorted(streams.items(), key=lambda v: repr(v[0])):
            current_time = stream[-1]['_effective']
            tied = [r for r in stream if r['_effective'] == current_time]
            base = {'scope': _scope_dict(scope), 'provider_id': provider, 'source_id': source,
                    'feed_id': feed, 'data_origin': origin, 'outcome': outcome}
            if len({r['_price'] for r in tied}) > 1:
                ids = [r['evidence_id'] for r in tied]
                conflicting_markets.add((scope, provider, source, feed, origin))
                flags.append({'code': 'CONFLICTING_SOURCE_QUOTES', 'evidence_ids': sorted(ids)})
                quotes.append(dict(base, decimal_odds=_unavailable('CONFLICTING_SOURCE_QUOTES', ids),
                                   raw_implied_probability=_unavailable('CONFLICTING_SOURCE_QUOTES', ids),
                                   quote_age=_unavailable('CONFLICTING_SOURCE_QUOTES', ids)))
                moves.append(dict(base, available=False, change=_unavailable('CONFLICTING_SOURCE_QUOTES', ids)))
                continue
            current = tied[-1]
            latest[(scope, outcome, provider)].append(current)
            eid = current['evidence_id']
            age = _seconds(decision - current['_effective'])
            base['snapshot_id'] = current['snapshot_id']
            if current.get('quote_phase'):
                base['quote_phase'] = current['quote_phase']
            historical = origin == 'imported_historical'
            quote_age = (_unavailable('HISTORICAL_QUOTE_TIME_UNAVAILABLE', [eid]) if historical else
                         _metric(age, 'seconds since system capture', [eid], 'cutoff - original_system_receipt',
                                 interpretation='Time since capture; the source quote may be older.'))
            quotes.append(dict(base,
                decimal_odds=_metric(current['_price'], 'decimal odds', [eid], 'convert(original, format)'),
                raw_implied_probability=_metric(current['_probability'], 'probability fraction', [eid], '1 / decimal_odds'),
                quote_age=quote_age))
            if historical:
                flags.append({'code': 'HISTORICAL_QUOTE_TIME_UNAVAILABLE', 'evidence_ids': [eid]})
            if _unverified_scope(scope):
                flags.append({'code': 'MARKET_SCOPE_UNVERIFIED', 'evidence_ids': [eid]})
            if historical or _unverified_scope(scope):
                reason = 'HISTORICAL_QUOTE_TIME_UNAVAILABLE' if historical else 'MARKET_SCOPE_UNVERIFIED'
                moves.append(dict(base, available=False, change=_unavailable(reason, [eid])))
                continue
            if age > max_age_seconds:
                flags.append({'code': 'STALE_QUOTE', 'evidence_ids': [eid]})
            prior = [r for r in stream if r['_effective'] < current_time and
                     _seconds(current_time - r['_effective']) <= lookback_seconds]
            if not prior:
                moves.append(dict(base, available=False, change=_unavailable('NO_PREVIOUS_QUOTE_IN_WINDOW', [eid])))
                continue
            previous_time = prior[-1]['_effective']
            old_tied = [r for r in prior if r['_effective'] == previous_time]
            if len({r['_price'] for r in old_tied}) > 1:
                ids = [r['evidence_id'] for r in old_tied] + [eid]
                flags.append({'code': 'CONFLICTING_SOURCE_QUOTES', 'evidence_ids': sorted(ids)})
                moves.append(dict(base, available=False, change=_unavailable('CONFLICTING_PREVIOUS_QUOTES', ids)))
                continue
            old = old_tied[-1]
            ids = [old['evidence_id'], eid]
            elapsed = _seconds(current['_effective'] - old['_effective'])
            odds_change = current['_price'] - old['_price']
            prob_change = current['_probability'] - old['_probability']
            moves.append(dict(base, available=True,
                decimal_odds_change=_metric(odds_change, 'decimal odds', ids, 'latest_decimal - previous_decimal'),
                raw_probability_change=_metric(prob_change, 'probability fraction', ids, 'latest_implied - previous_implied'),
                elapsed=_metric(elapsed, 'seconds', ids, 'latest_original_receipt - previous_original_receipt'),
                odds_change_per_hour=_metric(odds_change * 3600 / elapsed, 'decimal odds/hour', ids, 'odds_change * 3600 / elapsed'),
                probability_change_per_hour=_metric(prob_change * 3600 / elapsed, 'probability fraction/hour', ids, 'probability_change * 3600 / elapsed')))
        # Only the latest entire acquisition for each provider/source/feed qualifies.
        latest_snapshots = {}
        for (scope, provider, source, feed, origin, sid), group in snapshots.items():
            key = (scope, provider, source, feed, origin)
            order = (max((r['_effective'], r['_usable']) for r in group), sid)
            if key not in latest_snapshots or order > latest_snapshots[key][0]:
                latest_snapshots[key] = (order, sid, group)
        for (scope, provider, source, feed, origin), (_, sid, group) in sorted(latest_snapshots.items(), key=lambda v: repr(v[0])):
            ids = [r['evidence_id'] for r in group]
            base = {'scope': _scope_dict(scope), 'provider_id': provider, 'source_id': source,
                    'feed_id': feed, 'data_origin': origin, 'snapshot_id': sid}
            outcomes = [r['outcome'].lower() for r in group]
            if (scope, provider, source, feed, origin) in conflicting_markets:
                reason = 'CONFLICTING_SOURCE_QUOTES'
            elif _unverified_scope(scope):
                reason = 'MARKET_SCOPE_UNVERIFIED'
            elif origin == 'imported_historical' and not all(r.get('synchronization_proven') is True for r in group):
                reason = 'HISTORICAL_SNAPSHOT_SYNCHRONIZATION_UNPROVED'
            elif scope[4].lower() in ('1x2', 'h2h_3way', 'match_result_1x2'):
                reason = None if len(outcomes) == 3 and set(outcomes) == ONE_X_TWO else 'INCOMPLETE_OR_DUPLICATE_1X2_SET'
            elif scope[4].lower() in TOTAL_MARKETS:
                line = Decimal(scope[-1])
                if line < 0 or line % 1 != Decimal('0.5'):
                    reason = 'TOTAL_LINE_REQUIRES_PUSH_OR_SPLIT_HANDLING'
                else:
                    reason = None if len(outcomes) == 2 and set(outcomes) == TOTAL_OUTCOMES else 'INCOMPLETE_OR_DUPLICATE_TOTAL_SET'
            else:
                reason = 'UNSUPPORTED_OUTCOME_SET'
            if reason is None and len({r['_effective'] for r in group}) != 1:
                reason = 'SNAPSHOT_TIME_MISMATCH'
            if reason is None and _seconds(decision - min(r['_effective'] for r in group)) > max_age_seconds:
                reason = 'STALE_QUOTE'
            if reason:
                margins.append(dict(base, overround=_unavailable(reason, ids)))
                if reason in ('INCOMPLETE_OR_DUPLICATE_1X2_SET', 'INCOMPLETE_OR_DUPLICATE_TOTAL_SET'):
                    flags.append({'code': 'INCOMPLETE_MARKET', 'evidence_ids': sorted(ids)})
            else:
                # Rational arithmetic prevents intermediate rounding from distorting
                # equal-price margins or proportional estimates; round once at output.
                probabilities = {r['outcome'].lower(): Fraction(1, 1) / Fraction(r['_price']) for r in group}
                total = sum(probabilities.values(), Fraction(0, 1))
                def to_decimal(value):
                    return Decimal(value.numerator) / Decimal(value.denominator)
                margins.append(dict(base, overround=_metric(to_decimal(total - 1), 'probability fraction', ids,
                    'sum(exact reciprocal decimal odds) - 1; rounded once'),
                    proportional_margin_removed_estimates={outcome: _metric(to_decimal(prob / total),
                        'probability fraction', ids, 'exact reciprocal odds / sum(exact reciprocal odds); rounded once',
                        interpretation='proportional margin-removal estimate; not true probability')
                        for outcome, prob in probabilities.items()}))
        groups = defaultdict(list)
        for (scope, outcome, provider), items in latest.items():
            if len(items) > 1:
                ids = sorted(r['evidence_id'] for r in items)
                archival_labels = all(r['data_origin'] == 'imported_historical' for r in items)
                phases = {r.get('quote_phase') for r in items}
                if not (archival_labels and len(phases - {None}) > 1):
                    known_simultaneous = not archival_labels
                    latest_time = max(r['_effective'] for r in items)
                    differing = len({r['_price'] for r in items if r['_effective'] == latest_time}) > 1
                    code = 'CONFLICTING_SOURCE_QUOTES' if known_simultaneous and differing else 'AMBIGUOUS_PROVIDER_SOURCES'
                    flags.append({'code': code, 'provider_id': provider, 'evidence_ids': ids})
                groups[(scope, outcome)].append((provider, None, ids))
            else:
                groups[(scope, outcome)].append((provider, items[0], [items[0]['evidence_id']]))
        for (scope, outcome), members in sorted(groups.items(), key=lambda v: repr(v[0])):
            valid = [m for m in members if m[1] is not None]
            ids = [eid for _, _, evidence in members for eid in evidence]
            fresh = [m for m in valid if not _unverified_scope(scope) and m[1]['data_origin'] != 'imported_historical' and _seconds(decision - m[1]['_effective']) <= max_age_seconds]
            coverage.append({'scope': _scope_dict(scope), 'outcome': outcome,
                'provider_count': _metric(len(members), 'providers', ids, 'count eligible provider identities'),
                'fresh_comparable_provider_count': _metric(len(fresh), 'providers', [m[1]['evidence_id'] for m in fresh], 'count unambiguous fresh providers')})
            for a, b in combinations(sorted(members, key=lambda m: m[0]), 2):
                pair_ids = a[2] + b[2]
                item = {'scope': _scope_dict(scope), 'outcome': outcome, 'providers': [a[0], b[0]],
                        'independent_corroboration': False}
                if a[1] is None or b[1] is None:
                    reason = 'AMBIGUOUS_PROVIDER_SOURCES'
                elif _unverified_scope(scope):
                    reason = 'MARKET_SCOPE_UNVERIFIED'
                elif a[1]['data_origin'] == 'imported_historical' or b[1]['data_origin'] == 'imported_historical':
                    reason = 'HISTORICAL_QUOTE_TIME_UNAVAILABLE'
                elif scope[6] == 'live':
                    reason = 'LIVE_GAME_STATE_UNAVAILABLE'
                elif max(_seconds(decision - a[1]['_effective']), _seconds(decision - b[1]['_effective'])) > max_age_seconds:
                    reason = 'STALE_QUOTE'
                elif abs(_seconds(a[1]['_effective'] - b[1]['_effective'])) > alignment_seconds:
                    reason = 'EXCESSIVE_TIME_SEPARATION'
                else:
                    reason = None
                if reason:
                    item['decimal_odds_difference'] = _unavailable(reason, pair_ids)
                else:
                    x, y = a[1], b[1]
                    item['shared_feed'] = bool(x.get('feed_id') and x.get('feed_id') == y.get('feed_id'))
                    item['decimal_odds_difference'] = _metric(abs(x['_price'] - y['_price']), 'decimal odds', pair_ids, 'absolute provider decimal odds difference')
                    item['raw_probability_difference'] = _metric(abs(x['_probability'] - y['_probability']), 'probability fraction', pair_ids, 'absolute raw implied probability difference')
                    better, other = sorted((x, y), key=lambda r: (r['_price'], r['provider_id']), reverse=True)
                    best.append({'scope': _scope_dict(scope), 'outcome': outcome,
                        'higher_price_provider': better['provider_id'], 'other_provider': other['provider_id'],
                        'price_advantage': _metric(better['_price'] - other['_price'], 'decimal odds', pair_ids, 'higher decimal - other decimal'),
                        'interpretation': 'quoted-price discrepancy; not an estimate of expected value'})
                divergences.append(item)
    # Report scope mismatch as unavailable rather than silently comparing prices.
    grouped_scopes = defaultdict(list)
    for (scope, outcome, provider), items in latest.items():
        grouped_scopes[(scope[0], outcome)].append((scope, provider, items))
    for (_, outcome), entries in grouped_scopes.items():
        for a, b in combinations(sorted(entries, key=repr), 2):
            scope_a, provider_a, rows_a = a
            scope_b, provider_b, rows_b = b
            if provider_a == provider_b or scope_a == scope_b:
                continue
            ids = [r['evidence_id'] for r in rows_a + rows_b]
            divergences.append({'scope': _scope_dict(scope_a), 'other_scope': _scope_dict(scope_b),
                                'outcome': outcome, 'providers': [provider_a, provider_b],
                                'independent_corroboration': False,
                                'decimal_odds_difference': _unavailable('INCOMPATIBLE_MARKET_DEFINITIONS', ids)})
            flags.append({'code': 'INCOMPATIBLE_MARKET_DEFINITIONS', 'evidence_ids': sorted(ids)})
    flags.sort(key=lambda item: (item['code'], repr(item)))
    return {'quote_metrics': quotes, 'movements': moves, 'overrounds': margins,
            'provider_divergences': divergences, 'best_price_discrepancies': best,
            'source_coverage': coverage, 'quality_flags': flags,
            'configuration': {'max_age_seconds': max_age_seconds, 'alignment_seconds': alignment_seconds,
                              'lookback_seconds': lookback_seconds, 'time_basis': 'original system receipt',
                              'precision': PRECISION, 'version': VERSION}}







