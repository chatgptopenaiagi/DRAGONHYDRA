"""Immutable research publication contract, separate from canonical source memory."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

SCHEMA = 'dragonhydra.research-archive/1'

class StorageError(ValueError):
    def __init__(self, code, *, sqlstate=None, uncertain_write=False):
        super().__init__(code)
        self.code, self.sqlstate, self.uncertain_write = code, sqlstate, uncertain_write

def utc_now():return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def canonical(value):
    try:return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError):raise StorageError('INVALID_RESEARCH_JSON') from None

def fingerprint(value):return hashlib.sha256(canonical(value)).hexdigest()

def validate_bundle(value):
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA:
        raise StorageError('INVALID_RESEARCH_ARCHIVE')
    for key in ('archive_id', 'match_id'):
        if not isinstance(value.get(key), str) or not re.fullmatch('[a-f0-9]{64}', value[key]):
            raise StorageError('INVALID_RESEARCH_ID')
    if not isinstance(value.get('forecast_run_id'), str) or not 1 <= len(value['forecast_run_id']) <= 128:
        raise StorageError('INVALID_FORECAST_RUN_ID')
    if value.get('evaluation_status') not in ('pending', 'available'):
        raise StorageError('INVALID_RESEARCH_EVALUATION_STATUS')
    if not isinstance(value.get('match'), dict) or value['match'].get('id') != value['match_id']:
        raise StorageError('RESEARCH_MATCH_ID_MISMATCH')
    if not isinstance(value.get('source_build'),dict):raise StorageError('RESEARCH_BUILD_IDENTITY_REQUIRED')
    models, predictions, inputs = (value.get(k) for k in ('models', 'predictions', 'input_manifest'))
    if not all(isinstance(x, list) and x for x in (models, predictions, inputs)) or len(predictions) > 32 or len(inputs) > 10000:
        raise StorageError('BOUNDED_COMPLETE_RESEARCH_REQUIRED')
    if any(not isinstance(m,dict) or not isinstance(m.get('record_id'),str) or not m['record_id'] for m in models):
        raise StorageError('INVALID_RESEARCH_MODEL')
    if any(not isinstance(p,dict) or not isinstance(p.get('record_id'),str) or not p['record_id'] for p in predictions):
        raise StorageError('INVALID_RESEARCH_PREDICTION')
    ids = {m['record_id']:m for m in models}
    if len(ids) != len(models) or len(predictions) != len(models):
        raise StorageError('INCOMPLETE_RESEARCH_FORECAST')
    seen = set();bound_models=set()
    for row in predictions:
        model = ids.get(row.get('model_run_id'))
        if model is None or row.get('record_id') in seen or row.get('run_id') != value['forecast_run_id']:
            raise StorageError('RESEARCH_MODEL_BINDING_MISMATCH')
        seen.add(row['record_id'])
        if row['model_run_id'] in bound_models:raise StorageError('RESEARCH_MODEL_BINDING_MISMATCH')
        bound_models.add(row['model_run_id'])
        try:
            if any(not isinstance(row['probabilities'][k],str) for k in ('home','draw','away')):
                raise StorageError('RESEARCH_DECIMAL_TEXT_REQUIRED')
            probabilities = [Decimal(row['probabilities'][k]) for k in ('home', 'draw', 'away')]
            if any(not p.is_finite() or p < 0 or p > 1 or p.as_tuple().exponent < -28 for p in probabilities):
                raise StorageError('INVALID_RESEARCH_PROBABILITY')
            if abs(sum(probabilities)-1) > Decimal('1e-12'):
                raise StorageError('INVALID_RESEARCH_PROBABILITY_SUM')
            for key, p in zip(('home','draw','away'), probabilities):
                original = model['parameters']['result']['probabilities'][key]
                original = original['value'] if isinstance(original, dict) else original
                if p != Decimal(original):raise StorageError('RESEARCH_MODEL_PROBABILITY_MISMATCH')
        except (KeyError, TypeError, InvalidOperation):
            raise StorageError('INVALID_RESEARCH_PROBABILITY') from None
    if len(canonical(value)) > 8*1024*1024:raise StorageError('RESEARCH_ARCHIVE_TOO_LARGE')
    return value
