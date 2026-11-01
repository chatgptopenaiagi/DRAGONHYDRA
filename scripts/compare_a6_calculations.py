"""Compute comparable A6 outputs from an explicitly isolated retained snapshot.

Run this identical helper with the same wheel/snapshot on each platform. It
does not launch a server, call providers, or run a model endpoint. A fixed data
cutoff removes the clock variation in Product responses; actual computation
time guards in the forecasting engine remain active.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import sys


MATCH = '4897236dbf6d5312ff576ee18d6f4c03355e083701b4510543f36c3ad1b101a1'
CONTEXT = 'source_context:ee80300baae09fc55c61a5312abdc7553d072bcdd3c2e3dbf4ce13a2bb7466fe'
CUTOFF = '2026-10-31T23:59:59.000000Z'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def shape(value):
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return {'array_item_shapes': sorted({json.dumps(shape(item), sort_keys=True) for item in value})}
    return type(value).__name__


def differences(left, right, path='', *, tolerance=1e-12):
    """Compare exact structures/integers and platform floats within tolerance."""
    if type(left) in (float, int) and type(right) in (float, int) and (isinstance(left, float) or isinstance(right, float)):
        if math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance):
            return []
        return [{'path': path, 'left': left, 'right': right}]
    if type(left) is not type(right):
        return [{'path': path, 'left_type': type(left).__name__, 'right_type': type(right).__name__}]
    if isinstance(left, dict):
        result = []
        if set(left) != set(right):
            result.append({'path': path, 'left_keys': sorted(left), 'right_keys': sorted(right)})
        for key in sorted(set(left) & set(right)):
            result.extend(differences(left[key], right[key], path+'/'+key, tolerance=tolerance))
        return result
    if isinstance(left, list):
        result = [] if len(left) == len(right) else [{'path': path, 'left_length': len(left), 'right_length': len(right)}]
        for index, (a, b) in enumerate(zip(left, right)):
            result.extend(differences(a, b, path+'/'+str(index), tolerance=tolerance))
        return result
    return [] if left == right else [{'path': path, 'left': left, 'right': right}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, help='Optional installed-wheel target directory (never a source checkout)')
    parser.add_argument('--state', type=Path, required=True, help='Explicitly isolated DB/raw snapshot')
    parser.add_argument('--output', type=Path, required=True, help='Fresh JSON evidence file')
    parser.add_argument('--compare', type=Path, help='Other platform report produced by this exact helper')
    parser.add_argument('--cutoff', default=CUTOFF, help='Fixed data cutoff, identical on both platforms')
    parser.add_argument('--match-id', default=MATCH)
    parser.add_argument('--context-id', default=CONTEXT)
    args = parser.parse_args()
    state, output = args.state.resolve(), args.output.resolve()
    if output.exists() or not state.is_dir() or not (state/'core.sqlite3').is_file():
        parser.error('Existing isolated state and a fresh output file required')
    if datetime.fromisoformat(args.cutoff.replace('Z', '+00:00')) > datetime.now(timezone.utc):
        parser.error('Data cutoff must not be after actual execution time')
    if args.site:
        site = args.site.resolve()
        if not (site/'dragonhydra').is_dir():
            parser.error('--site must contain an installed dragonhydra package')
        sys.path.insert(0, str(site))
    report = {'passed': False,
              'scope': 'Actual installed A6 calculation and serialization comparison on retained data',
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'execution': {'platform': platform.platform(), 'system': platform.system(), 'python': sys.version,
                            'executable': sys.executable, 'state': str(state),
                            'at': datetime.now(timezone.utc).isoformat()},
              'data_cutoff': args.cutoff,
              'providers_contacted': False, 'model_endpoint_called': False,
              'cross_platform_equivalence_claimed': False}
    try:
        import dragonhydra
        from dragonhydra import product as product_module
        from dragonhydra.build_meta import info
        if args.site and not Path(dragonhydra.__file__).resolve().is_relative_to(args.site.resolve()):
            raise AssertionError('Imported package is outside the selected wheel installation')
        report['execution']['module'] = dragonhydra.__file__
        report['build'] = info()
        # Product supplies these response clocks. Leave actual forecast guards
        # untouched: these are current research calculations using a fixed data
        # cutoff, never purported historical predictions.
        product_module.now = lambda: args.cutoff
        from dragonhydra.local_ai import build_context_package
        product = product_module.Product(state)
        rows = product.rows()
        presented = sorted((product.present(row) for row in rows), key=lambda item: item['id'])
        selected = product.present(product.find(args.match_id))
        public_rows = [row for row in rows if row['source_id'] == 'openfootball-2025-26-en1.json']
        if not public_rows:
            raise AssertionError('Required retained OpenFootball league is absent')
        competition = product.competition_id(public_rows[0])
        standings = product.standings(competition)
        if not standings['items'] or sum(item['played'] for item in standings['items']) == 0:
            raise AssertionError('Standings calculation has no real retained results')
        explanation = product.explanation(args.match_id)
        explanation.pop('cutoff', None)
        package = build_context_package(product, args.match_id, args.context_id)
        # Select an actual retained scheduled public fixture deterministically.
        # Latest event date avoids selecting an already elapsed schedule whose
        # missing result must correctly trigger forecast abstention.
        scheduled = sorted((row for row in rows if not row.get('_connector')
                            and row.get('result_state') == 'unavailable'
                            and row.get('outcome') is None),
                           key=lambda row: (row['event_date'], product.match_id(row)), reverse=True)
        prediction = None
        if scheduled:
            target_id = product.match_id(scheduled[0])
            result = product.predictions(target_id)
            result.pop('cutoff', None)
            if result.get('ensemble') is not None and not math.isclose(sum(result['ensemble'].values()), 1.0, abs_tol=1e-12):
                raise AssertionError('Actual ensemble probabilities do not sum to one')
            prediction = {'match_id': target_id, 'event_date': scheduled[0]['event_date'], 'result': result}
        payload = {
            'record_count': len(presented),
            'match_identifiers_sha256': sha([item['id'] for item in presented]),
            'match_presentations_sha256': sha(presented),
            'match_shapes_sha256': sha(sorted({json.dumps(shape(item), sort_keys=True) for item in presented})),
            'selected_match': selected,
            'standings': {'competition_id': competition, 'official': standings['official'],
                          'items': standings['items'], 'items_sha256': sha(standings['items'])},
            'predictions': prediction,
            'deterministic_explanation': explanation,
            'package3': {'schema_version': package['schema_version'],
                         'package_sha256': package['package_sha256'],
                         'canonical_sha256': sha(package),
                         'context_summary': package['context_summary'],
                         'context_id': package['evidence']['C1']['id'],
                         'event_id': package['event']['id']}}
        report['comparison_payload'] = payload
        report['comparison_payload_sha256'] = sha(payload)
        report['forecast_availability'] = ('no_retained_scheduled_public_fixture' if prediction is None else
                                           'available' if prediction['result']['available'] else 'explicit_abstention')
        if args.compare:
            baseline = json.loads(args.compare.read_text(encoding='utf-8-sig'))
            if not baseline.get('passed') or baseline['harness_sha256'] != report['harness_sha256']:
                raise AssertionError('Baseline must be successful and use this exact helper')
            if baseline['data_cutoff'] != report['data_cutoff'] or baseline['build'] != report['build']:
                raise AssertionError('Baseline data cutoff or installed build differs')
            mismatches = differences(baseline['comparison_payload'], payload)
            report['comparison'] = {'baseline': str(args.compare.resolve()),
                                    'canonical_bytes_equal': baseline['comparison_payload_sha256'] == report['comparison_payload_sha256'],
                                    'numeric_relative_and_absolute_tolerance': 1e-12,
                                    'differences': mismatches, 'passed': not mismatches}
            if mismatches:
                raise AssertionError('Platform outputs differ; inspect comparison.differences')
            report['cross_platform_equivalence_claimed'] = baseline['execution'].get('system') != report['execution']['system']
        report['passed'] = True
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name+'.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    os.replace(temporary, output)
    print(json.dumps({'passed': report['passed'], 'report': str(output),
                      'forecast_availability': report.get('forecast_availability'),
                      'payload_sha256': report.get('comparison_payload_sha256'),
                      'comparison': report.get('comparison'), 'error': report.get('error')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
