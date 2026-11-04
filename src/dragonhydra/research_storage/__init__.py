"""Explicit per-profile selection; no fallback or passive initialization."""
import json
from pathlib import Path
from .base import StorageError

def configured_repository(state, scope, settings=None):
    path = Path(state)/'research-storage.json'
    if settings is None:
        try:settings = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {'schema_version':1,'provider':'sqlite'}
        except (OSError, ValueError):raise StorageError('INVALID_RESEARCH_STORAGE_CONFIGURATION') from None
    if not isinstance(settings, dict) or set(settings)-{'schema_version','provider','sqlserver'} or type(settings.get('schema_version')) is not int or settings.get('schema_version') != 1:
        raise StorageError('INVALID_RESEARCH_STORAGE_CONFIGURATION')
    if settings.get('provider') == 'sqlite':
        if settings.get('sqlserver'):raise StorageError('UNUSED_SQLSERVER_CONFIGURATION')
        from .sqlite import SQLiteResearchRepository
        return SQLiteResearchRepository(Path(state)/'research.sqlite3', scope)
    if settings.get('provider') == 'sqlserver':
        from .sqlserver import SQLServerConfig, SQLServerResearchRepository
        return SQLServerResearchRepository(SQLServerConfig.from_dict(settings.get('sqlserver',{})), scope)
    raise StorageError('UNSUPPORTED_RESEARCH_STORAGE_PROVIDER')
