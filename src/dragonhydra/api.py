"""Authenticated API shared by the dashboard, desktop and Joomla bridge."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, closing
from datetime import date as Date
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from .api_contracts import EmptyInput, ExportInput, Health, Job, JobInput, Match, MatchPage, SessionInput, SyncInput
from .jobs import Jobs, PUBLIC_URLS, fetch_public
from .product import API, ROOT, VERSION, Product, now
from .build_meta import info as build_info


def failure(code, message, status=400):
    return JSONResponse({'error': {'code': code, 'message': message}}, status_code=status)


def secure_equal(value: str, expected: str):
    # compare_digest(str, str) raises for non-ASCII user input. Byte comparison
    # preserves constant-time comparison and returns an ordinary mismatch.
    return hmac.compare_digest(value.encode('utf-8'), expected.encode('utf-8'))


def create_app(state: Path, *, local_token: str | None = None, bridge_secret: str | None = None,
               start_worker=True, source_root=ROOT):
    product = Product(state, source_root)
    jobs = Jobs(product)
    token_path = product.state / 'local-session.json'
    if local_token is None:
        local_token = json.loads(token_path.read_text())['token'] if token_path.exists() else secrets.token_urlsafe(48)
    if not token_path.exists():
        token_path.write_text(json.dumps({'token': local_token, 'user': 'local:owner'}), encoding='utf-8')
    bridge_path = product.state / 'joomla-bridge.json'
    if bridge_secret is None and bridge_path.exists():
        bridge_secret = json.loads(bridge_path.read_text())['secret']

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            jobs.start()
        yield
        jobs.close()

    app = FastAPI(title='DRAGONHYDRA Application API', version=VERSION, lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.product, app.state.jobs = product, jobs
    app.state.shutdown_callback = None
    app.state.stopping = False

    @app.exception_handler(LookupError)
    async def missing(request, exc):
        return failure(str(exc), 'The requested retained resource was not found.', 404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        code = str(exc) if str(exc).isupper() and len(str(exc)) < 80 else 'INVALID_REQUEST'
        return failure(code, 'The request is invalid or conflicts with retained state.', 409 if code == 'IDEMPOTENCY_CONFLICT' else 400)

    @app.exception_handler(RequestValidationError)
    async def validation(request, exc):
        return failure('VALIDATION_ERROR', 'Check the requested filters, resource IDs, and field types.', 422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return failure(str(exc.detail), 'Authentication or permission check failed.' if exc.status_code in (401,403) else 'Request unavailable.', exc.status_code)

    @app.middleware('http')
    async def browser_security(request, call_next):
        host = request.headers.get('host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost', 'testserver'):
            return failure('HOST_NOT_ALLOWED', 'Use the configured loopback product endpoint.', 400)
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = request.headers.get('origin')
            if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
                return failure('ORIGIN_NOT_ALLOWED', 'Open this action in the configured product application.', 403)
            try:
                content_length = int(request.headers.get('content-length', '0'))
            except ValueError:
                return failure('INVALID_CONTENT_LENGTH', 'Content-Length must be a nonnegative integer.', 400)
            if content_length < 0:
                return failure('INVALID_CONTENT_LENGTH', 'Content-Length must be a nonnegative integer.', 400)
            if content_length > 32*1024:
                return failure('REQUEST_TOO_LARGE', 'Request body exceeds the product limit.', 413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    async def principal(request: Request):
        auth = request.headers.get('authorization', '')
        if auth.startswith('Bearer ') and secure_equal(auth[7:], local_token):
            return {'user': 'local:owner', 'roles': ['admin']}
        cookie = request.cookies.get('dragon_session')
        if cookie:
            with closing(product.connect()) as db:
                row = db.execute('SELECT user,roles FROM product_sessions WHERE token_hash=? AND expires>?', (hashlib.sha256(cookie.encode()).hexdigest(), time.time())).fetchone()
            if row:
                return {'user': row[0], 'roles': json.loads(row[1])}
        if bridge_secret and request.headers.get('x-dragon-signature'):
            headers = request.headers
            user, roles, stamp, nonce = (headers.get(k, '') for k in ('x-dragon-user','x-dragon-roles','x-dragon-time','x-dragon-nonce'))
            try:
                valid_time = abs(time.time()-int(stamp)) <= 60
            except ValueError:
                valid_time = False
            if not valid_time or not user.startswith('joomla:') or len(nonce) < 16 or len(nonce) > 100 or roles not in ('admin', 'reader'):
                raise HTTPException(401, 'BRIDGE_IDENTITY_INVALID')
            body_hash = hashlib.sha256(await request.body()).hexdigest()
            path = request.url.path + ('?'+request.url.query if request.url.query else '')
            signed = '\n'.join((request.method, path, stamp, nonce, user, roles, body_hash))
            signature = hmac.new(bridge_secret.encode(), signed.encode(), hashlib.sha256).hexdigest()
            if not secure_equal(signature, headers['x-dragon-signature']):
                raise HTTPException(401, 'BRIDGE_SIGNATURE_INVALID')
            with closing(product.connect()) as db:
                try:
                    db.execute('DELETE FROM product_bridge_nonces WHERE expires<?', (time.time(),))
                    db.execute('INSERT INTO product_bridge_nonces VALUES(?,?)', (nonce, time.time()+120))
                    db.commit()
                except sqlite3.IntegrityError:
                    raise HTTPException(401, 'BRIDGE_REPLAY') from None
            return {'user': user, 'roles': [roles]}
        raise HTTPException(401, 'AUTHENTICATION_REQUIRED')

    def admin(user=Depends(principal)):
        if 'admin' not in user['roles']:
            raise HTTPException(403, 'ADMIN_PERMISSION_REQUIRED')
        return user

    def owned_job(job_id, user):
        job = jobs.get(job_id)
        if user['user'] != job['owner'] and 'admin' not in user['roles']:
            raise HTTPException(403, 'JOB_OWNER_REQUIRED')
        return job

    router = APIRouter(prefix=API, dependencies=[Depends(principal)])

    @app.get(API+'/health/live')
    def live():
        return {'status': 'alive', 'product': 'DRAGONHYDRA'}

    @app.post(API+'/session')
    def session(body: SessionInput, response: Response):
        if not secure_equal(body.token, local_token):
            raise HTTPException(401, 'INVALID_PAIRING_TOKEN')
        session_token = secrets.token_urlsafe(48)
        with closing(product.connect()) as db:
            db.execute('DELETE FROM product_sessions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO product_sessions VALUES(?,?,?,?)', (hashlib.sha256(session_token.encode()).hexdigest(), 'local:owner', '["admin"]', time.time()+12*3600))
            db.commit()
        response.set_cookie('dragon_session', session_token, httponly=True, samesite='strict', max_age=12*3600, path='/')
        return {'user': 'local:owner', 'roles': ['admin'], 'expires_in': 12*3600, 'network_mode': 'loopback-only'}

    @router.get('/health/ready', response_model=Health)
    def ready():
        with closing(product.connect()) as db:
            db.execute('SELECT version FROM product_schema').fetchone()
        return {'status': 'ready', 'backend': 'sqlite', 'version': VERSION, 'schema_version': 1, 'optional_ai': 'not_configured', 'source_sha': build_info()['source_sha']}

    @router.get('/openapi.json')
    def schema():
        return app.openapi()

    @router.get('/matches', response_model=MatchPage)
    def matches(date: str | None = None, timezone: str = 'UTC', competition: str | None = None,
                status: str | None = Query(default=None, pattern='^(finished|scheduled|live)$'),
                search: str = Query(default='', max_length=120), limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
        if date:
            Date.fromisoformat(date)
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            # Windows has no system IANA DB; UTC is always accepted. Other zones need tzdata.
            if timezone != 'UTC':
                raise ValueError('INVALID_TIMEZONE') from None
        return product.matches(date=date, status=status, competition=competition, search=search, limit=limit, offset=offset)

    @router.get('/matches/{match_id}', response_model=Match)
    def match(match_id: str):
        return product.present(product.find(match_id))

    @router.get('/matches/{match_id}/predictions')
    def predictions(match_id: str):
        return product.predictions(match_id)

    @router.get('/matches/{match_id}/odds')
    @router.get('/matches/{match_id}/odds-history')
    def odds(match_id: str):
        product.find(match_id)
        return {'items': [], 'axis': 'capture_time', 'reason': 'No approved cross-source market mapping for this canonical event. Archive prices are kept separate.'}

    @router.get('/matches/{match_id}/events')
    @router.get('/matches/{match_id}/statistics')
    @router.get('/matches/{match_id}/lineups')
    def context(match_id: str):
        product.find(match_id)
        return {'items': [], 'reason': 'This source does not provide this match context. Missing data does not mean zero.'}

    @router.get('/teams/{team_id}')
    def team(team_id: str):
        return product.team(team_id)

    @router.get('/teams/{team_id}/form')
    def form(team_id: str):
        return {'items': product.team(team_id)['form']}

    @router.get('/teams')
    def teams():
        result = {}
        for row in product.rows():
            for side in ('home', 'away'):
                key = product.team_id(row, row[side])
                result[key] = {'id': key, 'name': row[side], 'competition': row['competition']}
        return {'items': sorted(result.values(), key=lambda r: (r['name'],r['competition']))}

    @router.get('/competitions')
    def competitions():
        return product.competitions()

    @router.get('/competitions/{competition_id}/standings')
    def standings(competition_id: str):
        return product.standings(competition_id)

    @router.get('/competitions/{competition_id}/bracket')
    def bracket(competition_id: str):
        product.standings(competition_id)
        return {'items': [], 'reason': 'This competition is a league; no knockout bracket is supplied.'}

    @router.get('/connections')
    def connections():
        return jobs.connections()

    @router.post('/connections/{connection_id}/test', dependencies=[Depends(admin)])
    def test_connection(connection_id: str, body: EmptyInput):
        if connection_id != 'openfootball':
            raise HTTPException(409, 'CONNECTOR_NOT_IMPLEMENTED')
        try:
            raw = fetch_public(PUBLIC_URLS[0])
            doc = json.loads(raw)
            count = len(doc['matches'])
        except Exception:
            return {'status': 'unavailable', 'authentication': 'not_required', 'retrieved': False,
                    'record_count': 0, 'normalized_rows': 0, 'capabilities': [], 'reason': 'Public retrieval failed; retained imports remain available.'}
        return {'status': 'payload_retrieved', 'authentication': 'not_required', 'retrieved': True,
                'record_count': count, 'normalized_rows': 0, 'display_verified': False,
                'capabilities': ['historical_fixtures', 'results'], 'live': False,
                'reason': 'Payload retrieval verified; import and visible display are separate steps.'}

    @router.post('/connections/{connection_id}/sync', status_code=202, response_model=Job)
    def sync(connection_id: str, body: SyncInput, request: Request, user=Depends(admin)):
        if connection_id != 'openfootball':
            raise HTTPException(409, 'CONNECTOR_NOT_IMPLEMENTED')
        return jobs.submit('import_public', body.model_dump(), user['user'], request.headers.get('idempotency-key'))

    @router.post('/matches/{match_id}/explanations', status_code=202, response_model=Job)
    def explain(match_id: str, body: EmptyInput, request: Request, user=Depends(principal)):
        product.find(match_id)
        return jobs.submit('explanation', {'match_id': match_id}, user['user'], request.headers.get('idempotency-key'))

    @router.post('/exports', status_code=202, response_model=Job)
    def export(body: ExportInput, request: Request, user=Depends(principal)):
        product.find(body.match_id)
        return jobs.submit('export', body.model_dump(), user['user'], request.headers.get('idempotency-key'))

    @router.get('/exports/{job_id}/download')
    def download(job_id: str, user=Depends(principal)):
        job = owned_job(job_id, user)
        if job['kind'] != 'export' or job['status'] != 'succeeded':
            raise HTTPException(409, 'EXPORT_NOT_READY')
        name = job['result']['filename']
        return FileResponse(product.exports/name, filename=name)

    @router.post('/jobs', status_code=202, response_model=Job)
    def submit(body: JobInput, request: Request, user=Depends(principal)):
        if body.kind == 'import_public':
            if 'admin' not in user['roles']:
                raise HTTPException(403, 'ADMIN_PERMISSION_REQUIRED')
            payload = {'mode': body.mode}
        else:
            if not body.match_id:
                raise ValueError('MATCH_ID_REQUIRED')
            product.find(body.match_id)
            payload = {'match_id': body.match_id}
            if body.kind == 'export':
                payload['format'] = body.format
        return jobs.submit(body.kind, payload, user['user'], request.headers.get('idempotency-key'))

    @router.get('/jobs/{job_id}', response_model=Job)
    def job(job_id: str, user=Depends(principal)):
        return owned_job(job_id, user)

    @router.post('/jobs/{job_id}/cancel', response_model=Job)
    def cancel(job_id: str, body: EmptyInput, user=Depends(principal)):
        owned_job(job_id, user)
        return jobs.cancel(job_id)

    @router.get('/evidence/{evidence_id}')
    def evidence(evidence_id: str):
        return product.evidence(evidence_id)

    @router.get('/system')
    def system():
        config = product.state / 'product.json'
        settings = json.loads(config.read_text()) if config.exists() else {}
        return {'status': 'ready', 'backend': 'sqlite', 'version': VERSION, 'build': build_info(),
                'administration_url': settings.get('administration_url'),
                'ai': 'not_configured', 'network_mode': 'loopback-only',
                'capabilities': {'public_import': True, 'xlsx_export': True, 'joomla_bridge': bool(bridge_secret),
                                 'live_provider': False, 'mariadb': False, 'local_llm': False}}

    @router.post('/system/shutdown', dependencies=[Depends(admin)])
    def shutdown(body: EmptyInput):
        app.state.stopping = True
        if app.state.shutdown_callback:
            app.state.shutdown_callback()
        return {'status': 'stopping'}

    @router.get('/updates')
    async def updates(request: Request, cursor: int = Query(default=0, ge=0), user=Depends(principal)):
        try:
            after = max(cursor, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            raise ValueError('INVALID_EVENT_CURSOR') from None
        async def stream():
            nonlocal after
            # Bounded stream; EventSource reconnects using Last-Event-ID. Retention is durable and unpruned in v1.
            for _ in range(120):
                if app.state.stopping or await request.is_disconnected():
                    break
                for event in jobs.updates(after):
                    after = event['id']
                    # Readers receive only their job updates; data changes have no secret content.
                    job_id = event['data'].get('id') if event['topic'] == 'job' else event['data'].get('job_id')
                    if job_id and 'admin' not in user['roles'] and jobs.get(job_id)['owner'] != user['user']:
                        continue
                    yield f"id: {after}\nevent: {event['topic']}\ndata: {json.dumps(event['data'])}\n\n"
                yield ': heartbeat\n\n'
                await asyncio.sleep(0.5)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})

    app.include_router(router)
    web = Path(__file__).parent / 'resources' / 'web'
    if not web.is_dir():
        web = ROOT / 'client' / 'desktop' / 'web'
    if web.exists():
        app.mount('/', StaticFiles(directory=web, html=True), name='dashboard')
    return app
