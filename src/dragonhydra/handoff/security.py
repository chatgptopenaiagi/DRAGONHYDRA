from pathlib import Path,PureWindowsPath
from urllib.parse import urlsplit,unquote
import re
from ..web.contracts import PipelineError,public_url

SENSITIVE = re.compile(r'(?i)(?:["\s{,]|^)(?:password|passwd|pwd|cookie|set-cookie|authorization|access[_-]?token|refresh[_-]?token|api[_-]?key|session[_-]?(?:id|token))\s*["\']?\s*[:=]|\bBearer\s+\S+|\bBasic\s+[A-Za-z0-9+/=]+|\bsk-(?:proj-)?[A-Za-z0-9_-]{12,}|-----BEGIN .*PRIVATE KEY-----|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.')


class SecurityError(PipelineError):
    pass


def scan_secrets(value):
    if isinstance(value,bytes):
        value=value.decode('utf-8',errors='replace')
    if isinstance(value,str) and SENSITIVE.search(value):
        raise SecurityError('SECRET_LIKE_CONTENT')
    if isinstance(value,dict):
        for k,v in value.items():
            if re.fullmatch(r'(?i)password|passwd|pwd|cookie|cookies|authorization|tokens?|access_token|refresh_token|api_key|session_token|sql|execute|command|browser_profile',k):
                raise SecurityError('FORBIDDEN_FIELD')
            scan_secrets(v)
    elif isinstance(value,list):
        for v in value:scan_secrets(v)


def source_url(url):
    p=urlsplit(url)
    if p.scheme=='http' and p.hostname in ('localhost','127.0.0.1','::1') and not p.username and not p.password and not p.query and not p.fragment:
        if any(ord(c)<33 for c in url) or '\\' in url:raise SecurityError('INVALID_URL')
        return p
    return public_url(url)


def artifact_path(root,relative):
    decoded=unquote(relative).replace('\\','/')
    win=PureWindowsPath(relative)
    if (win.is_absolute() or win.drive or decoded.startswith('/') or ':' in decoded
            or any(p in ('..','.') or p.rstrip(' .')!=p for p in decoded.split('/'))):
        raise SecurityError('UNSAFE_ARTIFACT_PATH')
    path=root/decoded
    allowed=(root/'runtime/handoff/browser_downloads').resolve()
    if not path.resolve().is_relative_to(allowed):raise SecurityError('UNSAFE_ARTIFACT_PATH')
    # Do not follow symlinks/junctions or Windows alternate data streams.
    current=path
    while current != root and current.is_relative_to(root):
        if current.is_symlink() or (hasattr(current,'is_junction') and current.is_junction()):
            raise SecurityError('REPARSE_POINT_REJECTED')
        current=current.parent
    return path


def read_artifact(root, artifact):
    from .contracts import MAX_ARTIFACT_BYTES
    from ..web.provenance import digest
    path=artifact_path(root,artifact['relative_path'])
    media=artifact['media_type']
    extensions={'application/json':{'.json'},'text/plain':{'.txt','.md'},'text/csv':{'.csv'},'image/png':{'.png'},'image/jpeg':{'.jpg','.jpeg'}}
    if path.suffix.lower() not in extensions[media]:raise SecurityError('EXECUTABLE_OR_UNKNOWN_ARTIFACT')
    with path.open('rb') as stream:
        data=stream.read(MAX_ARTIFACT_BYTES+1)
    if len(data)>MAX_ARTIFACT_BYTES:raise SecurityError('OVERSIZED_ARTIFACT')
    if len(data)!=artifact['size_bytes'] or digest(data)!=artifact['sha256']:raise SecurityError('ARTIFACT_HASH_OR_SIZE_MISMATCH')
    if data.startswith((b'MZ',b'\x7fELF',b'#!')):raise SecurityError('EXECUTABLE_ARTIFACT')
    scan_secrets(data)
    if media=='image/png' and not data.startswith(b'\x89PNG\r\n\x1a\n'):raise SecurityError('MEDIA_MISMATCH')
    if media=='image/jpeg' and not data.startswith(b'\xff\xd8\xff'):raise SecurityError('MEDIA_MISMATCH')
    if media in ('application/json','text/plain','text/csv'):
        try:data.decode('utf-8-sig')
        except UnicodeError:raise SecurityError('MEDIA_MISMATCH') from None
    if media=='application/json':
        from ..web.json_api import parse_json
        scan_secrets(parse_json(data))
    return data
