"""Bounded Responses-shaped virtual reasoning loop. This module has no network client."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import queue
import re
import threading
import time

VIRTUAL_CREDENTIAL = 'virtual-only-not-a-real-openai-key'
PACKET_SCHEMA = 'dragonhydra.neural-packet/1'
ANALYSIS_SCHEMA = 'dragonhydra.neural-analysis/1'
MODES = ('DEMONSTRATION', 'REPLAY')


def _object(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


def _string(length=128, enum=None):
    result = {'type': 'string', 'minLength': 1, 'maxLength': length}
    if enum is not None:
        result['enum'] = enum
    return result


_NUMBER = {'type': 'number', 'minimum': 0, 'maximum': 1}
_PROBABILITY = _object({name: _NUMBER for name in ('home', 'draw', 'away')})
_IDS = {'type': 'array', 'items': _string(), 'maxItems': 32}
_VIRTUAL_ID = _string()
PACKET_FORMAT = _object({
    'schema_version': _string(enum=[PACKET_SCHEMA]), 'packet_id': _VIRTUAL_ID,
    'match_id': _VIRTUAL_ID, 'event_revision': {'type': 'integer', 'minimum': 0, 'maximum': 1000000},
    'source_mode': _string(enum=list(MODES)), 'forecast_target': _string(),
    'event': _object({'event_id': _VIRTUAL_ID, 'type': _string(64),
                      'minute': {'type': 'number', 'minimum': 0, 'maximum': 150}}),
    'observed_score': _object({side: {'type': 'integer', 'minimum': 0, 'maximum': 100}
                               for side in ('home', 'away')}),
    'probability_before': _PROBABILITY, 'probability_after': _PROBABILITY,
    'change': _object({side: {'type': 'number', 'minimum': -1, 'maximum': 1}
                       for side in ('home', 'draw', 'away')}),
    'data_quality': _object({'status': _string(64), 'flags': {'type': 'array', 'maxItems': 16,
                                                          'items': _string(128)}}),
    'model_id': _string(), 'evidence_ids': _IDS,
    'investigation': _object({'reason': _string(256), 'question': _string(512)}),
})
_FACT = _object({'statement': _string(600), 'evidence_ids': _IDS,
                'classification': _string(enum=['OBSERVED_FACT_IN_SIMULATION'])})
_MATH = _object({'statement': _string(600), 'tool_call_id': _string(), 'evidence_ids': _IDS,
                'classification': _string(enum=['DETERMINISTIC_MATH'])})
_HYPOTHESIS = _object({'statement': _string(600), 'confidence': _string(enum=['low', 'medium']),
                       'evidence_ids': _IDS, 'classification': _string(enum=['AI_HYPOTHESIS'])})
ANALYSIS_FORMAT = _object({'summary': _string(600),
                           'observed_facts': {'type': 'array', 'items': _FACT, 'maxItems': 8},
                           'mathematical_findings': {'type': 'array', 'items': _MATH, 'maxItems': 4},
                           'hypotheses': {'type': 'array', 'items': _HYPOTHESIS, 'maxItems': 4},
                           'evidence_ids': _IDS,
                           'limitations': {'type': 'array', 'items': _string(400), 'minItems': 1, 'maxItems': 8}})


def _json(value, limit=65536):
    try:
        text = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError('NONFINITE_OR_NON_JSON_VALUE') from exc
    if len(text.encode('utf-8')) > limit:
        raise ValueError('JSON_SIZE_LIMIT')
    return text


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_FIELD')
        result[key] = value
    return result


def _parse(value, limit=65536):
    if isinstance(value, (str, bytes)):
        if len(value.encode('utf-8') if isinstance(value, str) else value) > limit:
            raise ValueError('JSON_SIZE_LIMIT')
        try:
            result = json.loads(value, object_pairs_hook=_unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
        except (json.JSONDecodeError, UnicodeError, RecursionError) as exc:
            raise ValueError('INVALID_JSON') from exc
    else:
        result = deepcopy(value)
    _json(result, limit)
    return result


def _validate(value, schema, depth=0):
    if depth > 16:
        raise ValueError('JSON_DEPTH_LIMIT')
    kind = schema['type']
    if kind == 'object':
        if not isinstance(value, dict) or set(value) != set(schema['required']):
            raise ValueError('UNEXPECTED_OR_MISSING_FIELDS')
        for key, child in value.items():
            _validate(child, schema['properties'][key], depth + 1)
    elif kind == 'array':
        if not isinstance(value, list) or not schema.get('minItems', 0) <= len(value) <= schema['maxItems']:
            raise ValueError('ARRAY_SIZE_LIMIT')
        for child in value:
            _validate(child, schema['items'], depth + 1)
    elif kind == 'string':
        if not isinstance(value, str) or not schema.get('minLength', 0) <= len(value) <= schema['maxLength']:
            raise ValueError('STRING_SIZE_LIMIT')
    elif kind in ('number', 'integer'):
        if type(value) not in ((int,) if kind == 'integer' else (int, float)):
            raise ValueError('FINITE_NUMBER_REQUIRED')
        if not schema['minimum'] <= value <= schema['maximum']:
            raise ValueError('NUMBER_RANGE_LIMIT')
        if not math.isfinite(value):
            raise ValueError('FINITE_NUMBER_REQUIRED')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('UNSUPPORTED_ENUM_VALUE')


def validate_packet(packet):
    packet = _parse(packet, 16384)
    _validate(packet, PACKET_FORMAT)
    for value in (packet['packet_id'], packet['match_id'], packet['event']['event_id']):
        if not re.fullmatch(r'virtual-[A-Za-z0-9_.:-]{1,100}', value):
            raise ValueError('VIRTUAL_ID_REQUIRED')
    for key in ('probability_before', 'probability_after'):
        if not math.isclose(math.fsum(packet[key].values()), 1., abs_tol=1e-12, rel_tol=0):
            raise ValueError('PROBABILITIES_NOT_NORMALIZED')
    if any(not math.isclose(packet['change'][side],
                            packet['probability_after'][side] - packet['probability_before'][side],
                            abs_tol=1e-10, rel_tol=0) for side in packet['change']):
        raise ValueError('PACKET_DELTA_MISMATCH')
    if len(set(packet['evidence_ids'])) != len(packet['evidence_ids']):
        raise ValueError('DUPLICATE_EVIDENCE_ID')
    return packet


def _tool(name, properties, description):
    return {'type': 'function', 'name': name, 'description': description,
            'parameters': _object({'match_id': _VIRTUAL_ID} | properties), 'strict': True}


TOOLS = [
    _tool('get_current_match_state', {}, 'Read this synthetic match state.'),
    _tool('get_forecast_distribution', {}, 'Read the persisted deterministic synthetic forecast.'),
    _tool('compare_model_predictions', {}, 'Actually recompute bounded synthetic model variants.'),
    _tool('get_data_quality_report', {}, 'Read quality flags; never acquire new data.'),
    _tool('get_recent_event_history', {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20}},
          'Read a bounded suffix of virtual observations.'),
    _tool('get_historical_analogues', {'limit': {'type': 'integer', 'minimum': 1, 'maximum': 5}},
          'Read explicitly supplied synthetic analogues; no real history lookup.'),
    _tool('run_bounded_counterfactual', {
        'minute_advance': {'type': 'number', 'minimum': 0, 'maximum': 10},
        'score_delta': _object({side: {'type': 'integer', 'minimum': -1, 'maximum': 1}
                                for side in ('home', 'away')}),
        'red_card_delta': _object({side: {'type': 'integer', 'minimum': -1, 'maximum': 1}
                                   for side in ('home', 'away')})},
          'Recompute bounded virtual score, red-card and playing-minute assumptions; never replace the forecast.'),
    _tool('get_calibration_report', {}, 'Read synthetic episode scoring, not real calibration.'),
    _tool('get_prediction_evidence', {'evidence_ids': _IDS}, 'Read only known evidence IDs in this snapshot.'),
]
_TOOL_FORMATS = {tool['name']: tool['parameters'] for tool in TOOLS}


def tool_schemas():
    """Return detached public Responses schemas, not mutable global contracts."""
    return deepcopy(TOOLS)


def _identities(value, result=None):
    result = {} if result is None else result
    if isinstance(value, dict):
        for key in ('event_id', 'evidence_id', 'forecast_id'):
            if isinstance(value.get(key), str):
                result[value[key]] = value
        for child in value.values():
            _identities(child, result)
    elif isinstance(value, list):
        for child in value:
            _identities(child, result)
    return result


class VirtualResponsesTransport:
    """Simulated reasoning model: asks for real local tools, then consumes their outputs."""
    virtual_only = True

    def create(self, request):
        packet = json.loads(next(item['content'] for item in request['input'] if item.get('role') == 'user'))
        results = [json.loads(item['output']) for item in request['input']
                   if item.get('type') == 'function_call_output']
        if not results:
            calls = [('compare_model_predictions', {}), ('run_bounded_counterfactual', {
                'minute_advance': 1., 'score_delta': {'home': 0, 'away': 0},
                'red_card_delta': {'home': 0, 'away': 0}}),
                     ('get_data_quality_report', {}), ('get_prediction_evidence', {'evidence_ids': packet['evidence_ids']})]
            return {'output': [{'type': 'reasoning', 'id': 'virtual-reasoning-local-checks',
                                'summary': [{'type': 'summary_text', 'text': 'Check local math and evidence.'}]}] +
                    [{'type': 'function_call', 'call_id': 'virtual-call-' + str(index), 'name': name,
                      'arguments': _json({'match_id': packet['match_id']} | arguments)}
                     for index, (name, arguments) in enumerate(calls)], 'usage': None}
        by_name = {item['tool']: item for item in results}
        if not {'compare_model_predictions', 'run_bounded_counterfactual', 'get_data_quality_report', 'get_prediction_evidence'} <= by_name.keys():
            raise ValueError('VIRTUAL_MODEL_MISSING_TOOL_RESULTS')
        delta = by_name['run_bounded_counterfactual']['result'].get('full_time_result_delta')
        changed = isinstance(delta, dict) and any(abs(value) > 1e-12 for value in delta.values())
        comparison = by_name['compare_model_predictions']['result']
        if not isinstance(comparison.get('models'), list):
            raise ValueError('VIRTUAL_MODEL_REQUIRES_CALCULATED_MODELS')
        evidence = packet['evidence_ids']
        quality = by_name['get_data_quality_report']['result']
        analysis = {'summary': 'A virtual reasoning model checked deterministic math and supplied simulation evidence.',
                    'observed_facts': [{'statement': 'The supplied event and quality flags are observations within a simulation.',
                                        'evidence_ids': evidence, 'classification': 'OBSERVED_FACT_IN_SIMULATION'}],
                    'mathematical_findings': [
                        {'statement': 'Independent configured model variants were recomputed under shared synthetic assumptions.',
                         'tool_call_id': by_name['compare_model_predictions']['call_id'], 'evidence_ids': evidence,
                         'classification': 'DETERMINISTIC_MATH'},
                        {'statement': ('Advancing simulated time changed the deterministic forecast.' if changed else
                                       'The bounded simulated time change produced no full-time probability delta.'),
                         'tool_call_id': by_name['run_bounded_counterfactual']['call_id'], 'evidence_ids': evidence,
                         'classification': 'DETERMINISTIC_MATH'}],
                    'hypotheses': [{'statement': ('Time remaining may help explain this simulated probability movement; '
                                                  'the counterfactual does not establish a causal effect.'),
                                    'confidence': 'low', 'evidence_ids': evidence,
                                    'classification': 'AI_HYPOTHESIS'}],
                    'evidence_ids': evidence,
                    'limitations': ['All events, outcomes and model assumptions are synthetic.',
                                    'AI hypotheses cannot replace deterministic probabilities.',
                                    'Quality flags require caution.' if quality.get('flags') else
                                    'No synthetic quality flag establishes real-world data quality.']}
        return {'output': [{'type': 'message', 'role': 'assistant',
                            'content': [{'type': 'output_text', 'text': _json(analysis)}]}], 'usage': None}


class NeuralBridge:
    """Read-only local tools plus an injected virtual transport; no retries after uncertainty.

    Exported state supports caller-owned SQLite persistence. The caller should
    retain its permanent packet receipt ledger when the bounded cache is full.
    """
    def __init__(self, context_provider, config=None):
        config = {} if config is None else dict(config)
        allowed = {'credential', 'transport', 'max_rounds', 'max_tool_calls', 'per_match_limit',
                   'per_day_limit', 'max_concurrency', 'timeout_seconds', 'circuit_failure_limit',
                   'circuit_reset_seconds', 'max_cache_entries', 'clock', 'monotonic', 'state', 'enabled'}
        if set(config) - allowed:
            raise ValueError('UNSUPPORTED_BRIDGE_CONFIG')
        if config.get('credential', VIRTUAL_CREDENTIAL) != VIRTUAL_CREDENTIAL:
            raise ValueError('VIRTUAL_CREDENTIAL_ONLY')
        self.transport = config.get('transport', VirtualResponsesTransport())
        if getattr(self.transport, 'virtual_only', False) is not True or not callable(getattr(self.transport, 'create', None)):
            raise ValueError('VIRTUAL_TRANSPORT_ONLY')
        if not callable(context_provider):
            raise ValueError('CONTEXT_PROVIDER_REQUIRED')
        self.context_provider = context_provider
        self.enabled = config.get('enabled', True)
        if type(self.enabled) is not bool:
            raise ValueError('INVALID_BRIDGE_CONFIG')
        self.limits = {}
        for name, default, low, high in (
                ('max_rounds', 3, 1, 3), ('max_tool_calls', 4, 1, 4),
                ('per_match_limit', 8, 1, 100), ('per_day_limit', 24, 1, 1000),
                ('max_concurrency', 1, 1, 4), ('max_cache_entries', 32, 1, 128),
                ('circuit_failure_limit', 2, 1, 5)):
            value = config.get(name, default)
            if type(value) is not int or not low <= value <= high:
                raise ValueError('INVALID_BRIDGE_CONFIG')
            self.limits[name] = value
        self.timeout = config.get('timeout_seconds', 2.)
        self.reset = config.get('circuit_reset_seconds', 60.)
        for value, low, high in ((self.timeout, .001, 30), (self.reset, 1, 3600)):
            if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
                raise ValueError('INVALID_BRIDGE_CONFIG')
        self.clock = config.get('clock', lambda: datetime.now(timezone.utc))
        self.monotonic = config.get('monotonic', time.monotonic)
        self._lock = threading.RLock()
        self._active = 0
        self._transport_active = 0
        self._state = _parse(config.get('state', {'schema_version': 1, 'days': {}, 'cache': {},
                                                 'seen': {}, 'failures': 0, 'circuit_until': 0.}), 4194304)
        if set(self._state) != {'schema_version', 'days', 'cache', 'seen', 'failures', 'circuit_until'} or self._state['schema_version'] != 1:
            raise ValueError('INVALID_BRIDGE_STATE')
        if (not all(isinstance(self._state[key], dict) for key in ('days', 'cache', 'seen')) or
                type(self._state['failures']) is not int or self._state['failures'] < 0 or
                type(self._state['circuit_until']) not in (int, float) or
                not 0 <= self._state['circuit_until'] <= 253402300799 or
                not math.isfinite(self._state['circuit_until'])):
            raise ValueError('INVALID_BRIDGE_STATE')
        if (len(self._state['seen']) > 4096 or len(self._state['days']) > 366 or
                len(self._state['cache']) > self.limits['max_cache_entries'] or
                not self._state['cache'].keys() <= self._state['seen'].keys()):
            raise ValueError('INVALID_BRIDGE_STATE')
        for key, digest in self._state['seen'].items():
            if not isinstance(key, str) or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
                raise ValueError('INVALID_BRIDGE_STATE')
        for day, budget in self._state['days'].items():
            if (not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) or
                    not isinstance(budget, dict) or set(budget) != {'total', 'matches'} or
                    type(budget['total']) is not int or budget['total'] < 0 or
                    not isinstance(budget['matches'], dict) or
                    any(not isinstance(key, str) or type(value) is not int or value < 0
                        for key, value in budget['matches'].items()) or
                    sum(budget['matches'].values()) != budget['total']):
                raise ValueError('INVALID_BRIDGE_STATE')

    def export_state(self):
        with self._lock:
            return deepcopy(self._state)

    def _base(self, packet, status, reason=None):
        return {'schema_version': ANALYSIS_SCHEMA,
                'analysis_id': 'virtual-analysis-' + hashlib.sha256(_json(packet).encode()).hexdigest()[:32],
                'packet_id': packet['packet_id'], 'match_id': packet['match_id'], 'source_mode': packet['source_mode'],
                'synthetic': True, 'status': status, 'reason': reason, 'summary': reason or '',
                'analysis': None, 'hypotheses': [], 'evidence_ids': [], 'tool_results': [],
                'provider': 'virtual-responses', 'model': 'virtual-reasoning-1', 'usage': None, 'cost': None,
                'real_network_call_count': 0, 'virtual_request_count': 0, 'tool_call_count': 0,
                'rounds': 0, 'cache_hit': False, 'probabilities_changed': False}

    def _request(self, request, remaining):
        channel = queue.Queue(maxsize=1)
        def run():
            try:
                channel.put((True, self.transport.create(deepcopy(request))))
            except Exception as exc:
                channel.put((False, exc))
            finally:
                with self._lock:
                    self._transport_active -= 1
        with self._lock:
            self._transport_active += 1
        worker = threading.Thread(target=run, daemon=True, name='virtual-responses-bounded')
        worker.start()
        try:
            ok, value = channel.get(timeout=max(.001, remaining))
        except queue.Empty as exc:
            raise TimeoutError('VIRTUAL_CALL_TIMEOUT_UNCERTAIN_NO_RETRY') from exc
        if not ok:
            raise ValueError('VIRTUAL_TRANSPORT_FAILED') from value
        response = _parse(value, 65536)
        if (not {'output', 'usage'} <= response.keys() or
                set(response) - {'output', 'usage', 'id', 'object', 'status'} or
                response.get('status', 'completed') != 'completed' or
                response['usage'] is not None or not isinstance(response['output'], list)):
            raise ValueError('VIRTUAL_RESPONSE_SHAPE_INVALID')
        return response

    def _context(self, packet):
        snapshot = _parse(self.context_provider(packet['match_id']), 262144)
        required = {'state', 'current_forecast', 'timeline', 'events', 'analyses', 'calibration_report'}
        if not isinstance(snapshot, dict) or not required <= snapshot.keys():
            raise ValueError('CONTEXT_SHAPE_INVALID')
        state = snapshot['state']
        if (not isinstance(state, dict) or state.get('synthetic') is not True or
                state.get('match_id') != packet['match_id'] or state.get('source_mode') != packet['source_mode']):
            raise ValueError('SYNTHETIC_CONTEXT_IDENTITY_MISMATCH')
        forecast = snapshot['current_forecast']
        if (not isinstance(forecast, dict) or not isinstance(forecast.get('forecast'), dict) or
                forecast['forecast'].get('model_id') != packet['model_id'] or
                forecast['forecast'].get('full_time_result') != packet['probability_after'] or
                state.get('score') != packet['observed_score'] or
                state.get('revision') != packet['event_revision']):
            raise ValueError('PACKET_CONTEXT_FORECAST_MISMATCH')
        recorded_config = forecast['forecast'].get('model_configuration')
        if recorded_config is not None and snapshot.get('model_config') != recorded_config:
            raise ValueError('MODEL_CONFIGURATION_BINDING_MISMATCH')
        evidence = _identities({key: snapshot[key] for key in ('state', 'current_forecast', 'timeline', 'events')})
        if not set(packet['evidence_ids']) <= evidence.keys() or packet['event']['event_id'] not in evidence:
            raise ValueError('INVENTED_EVIDENCE_ID')
        for value in set(packet['evidence_ids']) | {packet['event']['event_id']}:
            record = evidence[value]
            if (record.get('match_id', packet['match_id']) != packet['match_id'] or
                    record.get('source_mode', packet['source_mode']) != packet['source_mode']):
                raise ValueError('CROSS_MATCH_EVIDENCE_REJECTED')
        return snapshot, evidence

    def _execute(self, call, packet, snapshot, evidence):
        if (not {'type', 'call_id', 'name', 'arguments'} <= call.keys() or
                set(call) - {'type', 'call_id', 'name', 'arguments', 'id', 'status'} or
                call['type'] != 'function_call' or call.get('status', 'completed') != 'completed'):
            raise ValueError('UNEXPECTED_TOOL_CALL_FIELDS')
        name = call['name']
        if name not in _TOOL_FORMATS:
            raise ValueError('UNSUPPORTED_TOOL')
        if not isinstance(call['call_id'], str) or not 1 <= len(call['call_id']) <= 128:
            raise ValueError('INVALID_CALL_ID')
        arguments = _parse(call['arguments'], 4096)
        _validate(arguments, _TOOL_FORMATS[name])
        if arguments['match_id'] != packet['match_id']:
            raise ValueError('CROSS_MATCH_TOOL_REJECTED')
        state = deepcopy(snapshot['state'])
        classification = 'OBSERVED_FACT_IN_SIMULATION'
        if name == 'get_current_match_state':
            result = state
        elif name == 'get_forecast_distribution':
            result = snapshot['current_forecast']
        elif name == 'get_data_quality_report':
            result = state.get('quality', packet['data_quality'])
        elif name == 'get_recent_event_history':
            result = snapshot['events'][-arguments['limit']:]
        elif name == 'get_historical_analogues':
            result = state.get('virtual_historical_analogues', [])[:arguments['limit']]
            if any(not isinstance(row, dict) or row.get('synthetic') is not True for row in result):
                raise ValueError('SYNTHETIC_ANALOGUES_ONLY')
        elif name == 'get_calibration_report':
            result = snapshot['calibration_report']
        elif name == 'get_prediction_evidence':
            ids = arguments['evidence_ids']
            if not set(ids) <= evidence.keys():
                raise ValueError('INVENTED_EVIDENCE_ID')
            result = [{'evidence_id': value, 'record': evidence[value]} for value in ids]
        else:
            from . import models
            classification = 'DETERMINISTIC_MATH'
            if name == 'compare_model_predictions':
                result = models.compare_models(state, snapshot.get('model_config'))
            else:
                minute = state.get('minute', 0)
                end = state.get('period_end_minute', state.get('duration_minutes', 90))
                changes = {'minute': min(minute + arguments['minute_advance'], end)}
                for target, delta_key in (('score', 'score_delta'), ('red_cards', 'red_card_delta')):
                    changes[target] = {side: state[target][side] + arguments[delta_key][side]
                                       for side in ('home', 'away')}
                result = models.bounded_counterfactual(state, changes, snapshot.get('model_config'))
        return _parse({'tool': name, 'call_id': call['call_id'], 'classification': classification,
                       'synthetic': True, 'evidence_ids': packet['evidence_ids'], 'result': result}, 65536)

    def investigate(self, packet):
        packet = validate_packet(packet)
        digest = hashlib.sha256(_json(packet).encode()).hexdigest()
        key = packet['match_id'] + ':' + packet['packet_id']
        now = self.clock()
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError('BRIDGE_UTC_CLOCK_REQUIRED')
        now = now.astimezone(timezone.utc)
        day = now.date().isoformat()
        with self._lock:
            seen = self._state['seen'].get(key)
            if seen is not None:
                if seen != digest:
                    raise ValueError('PACKET_ID_REUSED_WITH_CHANGED_CONTENTS')
                cached = self._state['cache'].get(key)
                result = deepcopy(cached) if cached is not None else self._base(packet, 'deduplicated', 'CALLER_RECEIPT_REQUIRED')
                result['cache_hit'] = True
                return result
            if not self.enabled:
                return self._base(packet, 'disabled', 'VIRTUAL_BRIDGE_DISABLED')
            if self._active or self._transport_active:
                if max(self._active, self._transport_active) >= self.limits['max_concurrency']:
                    return self._base(packet, 'budget_exhausted', 'CONCURRENCY_BUDGET')
            if self._state['circuit_until'] > now.timestamp():
                return self._base(packet, 'uncertain', 'VIRTUAL_CIRCUIT_OPEN_NO_RETRY')
            budget = self._state['days'].setdefault(day, {'total': 0, 'matches': {}})
            if (budget['total'] >= self.limits['per_day_limit'] or
                    budget['matches'].get(packet['match_id'], 0) >= self.limits['per_match_limit']):
                return self._base(packet, 'budget_exhausted', 'DAILY_OR_MATCH_BUDGET')
            if len(self._state['seen']) >= 4096 or len(self._state['days']) >= 366:
                return self._base(packet, 'budget_exhausted', 'PERSISTED_LEDGER_CAPACITY')
            budget['total'] += 1
            budget['matches'][packet['match_id']] = budget['matches'].get(packet['match_id'], 0) + 1
            self._state['seen'][key] = digest
            self._active += 1
        result = self._base(packet, 'uncertain')
        started = self.monotonic()
        try:
            snapshot, evidence = self._context(packet)
            conversation = [{'role': 'system', 'content': 'Virtual simulation only. Read bounded tools before hypotheses. '
                             'Never alter probabilities or invent evidence. Separate observed simulation facts, math and hypotheses.'},
                            {'role': 'user', 'content': _json(packet, 16384)}]
            calls_seen = set()
            for round_index in range(self.limits['max_rounds']):
                remaining = self.timeout - (self.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('VIRTUAL_CALL_TIMEOUT_UNCERTAIN_NO_RETRY')
                request = {'model': 'virtual-reasoning-1', 'store': False, 'input': deepcopy(conversation),
                           'tools': deepcopy(TOOLS), 'parallel_tool_calls': True,
                           'text': {'format': {'type': 'json_schema', 'name': 'synthetic_hypothesis',
                                               'strict': True, 'schema': deepcopy(ANALYSIS_FORMAT)}}}
                result['virtual_request_count'] += 1
                response = self._request(request, remaining)
                result['rounds'] = round_index + 1
                output = response['output']
                if not output or len(output) > 8 or any(not isinstance(item, dict) or item.get('type') not in
                                                       ('reasoning', 'function_call', 'message') for item in output):
                    raise ValueError('UNSUPPORTED_RESPONSE_ITEM')
                # Preserve every returned item, including reasoning items, BEFORE tool outputs.
                conversation.extend(deepcopy(output))
                calls = [item for item in output if item['type'] == 'function_call']
                messages = [item for item in output if item['type'] == 'message']
                if calls:
                    if messages or result['tool_call_count'] + len(calls) > self.limits['max_tool_calls']:
                        raise ValueError('TOOL_CALL_BUDGET_OR_MIXED_OUTPUT')
                    if round_index + 1 >= self.limits['max_rounds']:
                        raise ValueError('TOOL_ROUND_BUDGET')
                    for call in calls:
                        if call.get('call_id') in calls_seen:
                            raise ValueError('DUPLICATE_TOOL_CALL_ID')
                        calls_seen.add(call.get('call_id'))
                        tool_result = self._execute(call, packet, snapshot, evidence)
                        result['tool_results'].append(tool_result)
                        result['tool_call_count'] += 1
                        conversation.append({'type': 'function_call_output', 'call_id': call['call_id'],
                                             'output': _json(tool_result)})
                    _json(conversation, 262144)
                    continue
                if len(messages) != 1 or result['tool_call_count'] == 0:
                    raise ValueError('EVIDENCE_TOOLS_REQUIRED_BEFORE_ANALYSIS')
                message = messages[0]
                if (not {'type', 'role', 'content'} <= message.keys() or
                        set(message) - {'type', 'role', 'content', 'id', 'status'} or
                        message['role'] != 'assistant' or message.get('status', 'completed') != 'completed'):
                    raise ValueError('UNEXPECTED_MESSAGE_FIELDS')
                content = message['content']
                if (not isinstance(content, list) or len(content) != 1 or
                        set(content[0]) != {'type', 'text'} or content[0]['type'] != 'output_text'):
                    raise ValueError('STRUCTURED_ANALYSIS_REQUIRED')
                analysis = _parse(content[0]['text'], 16384)
                _validate(analysis, ANALYSIS_FORMAT)
                for item in [analysis] + analysis['observed_facts'] + analysis['mathematical_findings'] + analysis['hypotheses']:
                    if not set(item['evidence_ids']) <= set(packet['evidence_ids']):
                        raise ValueError('INVENTED_EVIDENCE_ID')
                math_calls = {item['call_id'] for item in result['tool_results']
                              if item['classification'] == 'DETERMINISTIC_MATH'}
                if not analysis['mathematical_findings'] or not math_calls or any(
                        item['tool_call_id'] not in math_calls for item in analysis['mathematical_findings']):
                    raise ValueError('CALCULATED_MATH_EVIDENCE_REQUIRED')
                result.update(status='completed', analysis=analysis, summary=analysis['summary'],
                              hypotheses=deepcopy(analysis['hypotheses']), evidence_ids=analysis['evidence_ids'])
                result['classification'] = 'AI_HYPOTHESIS'
                with self._lock:
                    self._state['failures'] = 0
                break
            else:
                raise ValueError('TOOL_ROUND_BUDGET')
        except Exception as exc:
            # No retry, guessed answer, fabricated usage, or fallback probability vector.
            code = str(exc) if isinstance(exc, (ValueError, TimeoutError)) else 'VIRTUAL_CONTEXT_OR_TOOL_FAILED'
            if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,159}', code):
                code = 'VIRTUAL_CONTEXT_OR_TOOL_FAILED'
            result.update(status='uncertain', reason=code[:160], summary='Virtual investigation unavailable; no forecast changed.')
            with self._lock:
                self._state['failures'] += 1
                if isinstance(exc, TimeoutError) or self._state['failures'] >= self.limits['circuit_failure_limit']:
                    self._state['circuit_until'] = now.timestamp() + self.reset
        finally:
            with self._lock:
                self._active -= 1
                result['budget'] = deepcopy(self._state['days'][day])
                self._state['cache'][key] = deepcopy(result)
                while len(self._state['cache']) > self.limits['max_cache_entries']:
                    del self._state['cache'][next(iter(self._state['cache']))]
        return result
