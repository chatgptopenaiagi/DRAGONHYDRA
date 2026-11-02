"""Build identity supplied by the source-locked release build, never inferred."""
import json
from pathlib import Path

VERSION = '0.5.0-dev.2'
PYTHON_VERSION = '0.5.0.dev2'


def info():
    path = Path(__file__).with_name('build_info.json')
    if path.is_file():
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('version') != VERSION:
            raise RuntimeError('BUILD_VERSION_MISMATCH')
        return data
    return {'version': VERSION, 'python_version': PYTHON_VERSION, 'source_sha': None,
            'api_namespace': '/dragon/api/v1', 'schema_version': 1, 'build_kind': 'source-checkout'}
