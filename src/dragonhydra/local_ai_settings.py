"""Server-owned local model settings and Windows-identity DPAPI credentials.

The endpoint file contains no key. Environment settings override stored values;
neither configuration reads nor writes contact or start a model process.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import threading
from uuid import uuid4

from .connectors.core import ConnectorError
from .connectors.vault import Vault
from .local_ai import LocalAIError


_LOCK = threading.RLock()
URL_ENV = 'DRAGONHYDRA_LOCAL_AI_URL'
KEY_ENV = 'DRAGONHYDRA_LOCAL_AI_KEY'


def endpoint(value):
    """Accept only the same explicit loopback HTTP route used by inference."""
    if value == '':
        return ''
    if not isinstance(value, str) or not re.fullmatch(r'http://127\.0\.0\.1:([0-9]{1,5})/?', value):
        raise LocalAIError('AI_ENDPOINT_INVALID', 'Use an explicit HTTP model endpoint at 127.0.0.1 with a valid port.')
    port = int(value.rstrip('/').rsplit(':', 1)[1])
    if not 1 <= port <= 65535:
        raise LocalAIError('AI_ENDPOINT_INVALID', 'Use an explicit HTTP model endpoint at 127.0.0.1 with a valid port.')
    return 'http://127.0.0.1:' + str(port)


def credential(value):
    if not isinstance(value, str) or not 20 <= len(value) <= 4096 or any(not 33 <= ord(char) <= 126 for char in value):
        raise LocalAIError('AI_KEY_INVALID', 'The model key must contain 20 to 4096 printable ASCII characters without spaces.')
    return value


class Settings:
    def __init__(self, state):
        self.state = Path(state)
        self.path = self.state / 'local-ai.json'
        self.vault = Vault(self.state)

    def _stored_endpoint(self):
        try:
            if not self.path.exists():
                return ''
            if self.path.stat().st_size > 2048:
                raise ValueError()
            document = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(document, dict) or set(document) != {'version', 'endpoint'} or document['version'] != 1:
                raise ValueError()
            return endpoint(document['endpoint'])
        except (OSError, UnicodeError, ValueError, LocalAIError):
            raise LocalAIError('AI_SETTINGS_INVALID', 'Saved local model settings could not be read. Save a valid endpoint again.') from None

    def _public(self):
        supplied_url, supplied_key = os.environ.get(URL_ENV, ''), os.environ.get(KEY_ENV, '')
        effective_url = endpoint(supplied_url) if supplied_url else self._stored_endpoint()
        if supplied_key:
            credential(supplied_key)
        key_source = 'environment' if supplied_key else 'vault' if self.vault.path('local-ai').exists() else 'none'
        return {'endpoint': effective_url, 'configured': bool(effective_url and key_source != 'none'),
                'endpoint_source': 'environment' if supplied_url else 'stored' if effective_url else 'none',
                'credential_source': key_source}

    def public(self):
        with _LOCK:
            return self._public()

    def effective(self):
        with _LOCK:
            current = self._public()
            try:
                key = self.vault.get('local-ai')
                if key:
                    credential(key)
                return current['endpoint'], key
            except ConnectorError as error:
                raise LocalAIError(error.code, error.message) from None
            except (OSError, UnicodeError, ValueError):
                raise LocalAIError('AI_CREDENTIAL_UNAVAILABLE', 'The saved model key is unavailable to this server account. Save it again.') from None

    def _private_file(self, path, raw):
        from .server import protect
        with path.open('xb') as output:
            protect(path)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())

    def configure(self, selected_endpoint, selected_credential=None, remove_credential=False):
        # Reject the complete request before creating files or encrypting a key.
        selected_endpoint = endpoint(selected_endpoint)
        if selected_credential is not None:
            credential(selected_credential)
        if selected_credential is not None and remove_credential:
            raise LocalAIError('AI_SETTINGS_INVALID', 'Save or remove a stored key in separate actions.')
        with _LOCK:
            if os.environ.get(URL_ENV):
                endpoint(os.environ[URL_ENV])
            if os.environ.get(KEY_ENV):
                credential(os.environ[KEY_ENV])
            temporary = self.path.with_name('.local-ai-' + uuid4().hex + '.tmp')
            vault_path = self.vault.path('local-ai')
            previous = None
            changed = False
            try:
                previous = vault_path.read_bytes() if vault_path.exists() else None
                self._private_file(temporary, json.dumps({'version': 1, 'endpoint': selected_endpoint}, sort_keys=True).encode('utf-8'))
                if selected_credential is not None:
                    self.vault.put('local-ai', selected_credential)
                    changed = True
                elif remove_credential:
                    self.vault.delete('local-ai')
                    changed = previous is not None
                os.replace(temporary, self.path)
            except Exception as error:
                if changed:
                    if previous is None:
                        self.vault.delete('local-ai')
                    else:
                        rollback = vault_path.with_name('.local-ai-rollback-' + uuid4().hex + '.tmp')
                        try:
                            self._private_file(rollback, previous)
                            os.replace(rollback, vault_path)
                        finally:
                            rollback.unlink(missing_ok=True)
                if isinstance(error, ConnectorError):
                    raise LocalAIError(error.code, error.message) from None
                raise LocalAIError('AI_SETTINGS_WRITE_FAILED', 'Local model settings could not be saved. The previous configuration is retained.') from None
            finally:
                temporary.unlink(missing_ok=True)
            return self._public()
