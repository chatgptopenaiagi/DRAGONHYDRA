import json
from .contracts import PipelineError


def parse_json(content):
    if len(content) > 2_000_000:
        raise PipelineError('MAX_BYTES_EXCEEDED')
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError()
            result[k] = v
        return result
    def invalid(value):
        raise ValueError()
    try:
        value = json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)
        if not isinstance(value, (dict, list)):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise PipelineError('PARSE_FAILED') from None
