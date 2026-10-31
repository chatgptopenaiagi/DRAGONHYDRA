"""Loopback public boundary for the EXISTING Joomla and DRAGONHYDRA API.

Never forward visitor credentials, cookies or write requests. Joomla core and
application source/configuration remain untouched. Both tunnel modes use this
same allowlist. Run with the already verified project Python environment.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import OrderedDict, defaultdict, deque
import hashlib
import hmac
import ipaddress
import json
from pathlib import Path
import re
import secrets
import socket
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
API = '/dragon/api/v1'
RESOURCE = r'[a-f0-9]{64}'
READ_ROUTES = re.compile(rf'^{API}/(?:matches(?:/{RESOURCE}(?:/(?:events|statistics|lineups|odds|odds-history|predictions))?)?|teams(?:/{RESOURCE}(?:/form)?)?|competitions(?:/{RESOURCE}/(?:standings|bracket))?)$')
ASSET = re.compile(r'^/(?:media|templates|images)/[A-Za-z0-9_./-]+\.(?:css|js|mjs|png|jpe?g|gif|svg|ico|webp|woff2?|ttf|otf|map)$', re.I)
PRIVATE = re.compile(r'/(?:administrator|phpmyadmin|installation|configuration\.php|\.git|\.env|vault|debug|llm|logs|cache)(?:/|$)', re.I)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def public_frontend(path, query):
    if ASSET.fullmatch(path):
        if not query.keys() - {'version', 'v', 'ver'}:
            return True
        # Joomla's WebAssetManager appends a bare content hash, e.g. core.js?017f13.
        return len(query)==1 and all(re.fullmatch(r'(?:[a-fA-F0-9]{6,64}|[0-9]{1,3}(?:\.[0-9]{1,3}){1,3})',key) and values==[''] for key,values in query.items())
    if path not in ('/', '/index.php'):
        return False
    if not query:
        return True
    if query.keys() - {'option', 'view', 'id', 'catid', 'Itemid', 'lang'}:
        return False
    if query.get('option', ['com_content']) != ['com_content']:
        return False
    if query.get('view', ['featured'])[0] not in ('featured', 'article', 'category', 'categories'):
        return False
    return all(len(values) == 1 and re.fullmatch(r'[A-Za-z0-9_:-]{1,100}', values[0]) for values in query.values())


def sanitize(value):
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items() if not re.search(r'password|secret|token|credential|vault', k, re.I)}
    if isinstance(value, str) and value.startswith(('http://', 'https://')):
        parsed = urlsplit(value)
        query = [(k, v) for k, values in parse_qs(parsed.query).items() for v in values if not re.search(r'key|token|secret|auth|password', k, re.I)]
        return urlunsplit((parsed.scheme, parsed.netloc.split('@')[-1], parsed.path, urlencode(query), ''))
    return value


def create_gateway(config_path):
    config_path = Path(config_path).resolve()
    config = load(config_path)
    for key in ('api_endpoint_file', 'bridge_secret_file'):
        candidate = Path(config[key]).expanduser()
        config[key] = str(candidate if candidate.is_absolute() else (config_path.parent / candidate).resolve())
    joomla = config['joomla_origin'].rstrip('/')
    origin = urlsplit(joomla)
    if (origin.hostname != '127.0.0.1' or origin.scheme != 'http' or origin.path
            or origin.username or origin.password or origin.query or origin.fragment):
        raise ValueError('Joomla origin must be the verified local loopback HTTP listener')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    concurrency = asyncio.Semaphore(32)
    rates = defaultdict(deque)
    cache = OrderedDict()
    app.state.config = config

    def unavailable(api=False):
        if api:
            return JSONResponse({'error': {'code': 'PUBLIC_SOURCE_UNAVAILABLE', 'message': 'Sports data is temporarily unavailable. Please retry.'}}, status_code=503)
        return HTMLResponse('<!doctype html><html lang="en"><title>DRAGONHYDRA temporarily unavailable</title><h1>DRAGONHYDRA is reconnecting</h1><p>The local website is temporarily unavailable. Please reload shortly.</p></html>',status_code=503)

    @app.api_route('/{path:path}', methods=['GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS','TRACE'])
    async def route(request: Request, path: str):
        path = '/'+path
        raw = request.scope.get('raw_path', b'').decode('ascii', errors='replace').lower()
        headers = {'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin', 'Cache-Control': 'no-store',
                   'X-Frame-Options': 'SAMEORIGIN', 'Permissions-Policy': 'camera=(), microphone=(), geolocation=()'}
        denied = JSONResponse({'error': {'code': 'PUBLIC_ROUTE_DENIED', 'message': 'This route is private or unavailable on the public gateway.'}}, status_code=403, headers=headers)
        if request.method not in ('GET','HEAD'):
            return denied
        if '%' in raw or '..' in path or '\\' in path or '//' in path or PRIVATE.search(path):
            return denied
        query = parse_qs(request.url.query, keep_blank_values=True)
        forward_query = str(request.query_params)
        if len(request.url.query)>1000 or any(len(v)!=1 for v in query.values()):
            return denied
        host = request.headers.get('host','')
        hostname = host.split(':')[0].lower()
        allowed = hostname in ('localhost','127.0.0.1','testserver') or hostname.endswith('.trycloudflare.com') or hostname in config.get('vps_public_ips', [])
        if not allowed or not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}',host):
            return denied
        fallback_ip = request.client.host if request.client else 'unknown'
        if hostname in config.get('vps_public_ips', []):
            client_ip = request.headers.get('x-real-ip', fallback_ip)
        else:
            client_ip = request.headers.get('cf-connecting-ip', fallback_ip)
        try:
            ipaddress.ip_address(client_ip)
        except ValueError:
            client_ip = fallback_ip
        tick = time.monotonic()
        bucket = rates[client_ip]
        while bucket and tick-bucket[0]>60:
            bucket.popleft()
        if len(bucket)>=180:
            return JSONResponse({'error': {'code':'PUBLIC_RATE_LIMIT','message':'Please wait before refreshing again.'}},status_code=429,headers={**headers,'Retry-After':'60'})
        bucket.append(tick)
        if len(rates)>10000:
            rates.clear()
        if path == '/public-health' and not query:
            info_path = BASE/'build-info.json'
            info = load(info_path) if info_path.is_file() else {}
            return JSONResponse({'status':'ready','mode':'read-only-public-gateway',
                                 'version':info.get('version'), 'source_sha':info.get('source_sha')},headers=headers)
        if path == '/public-assets/site.js' and not query:
            return FileResponse(HERE/'site.js',headers=headers)
        if path == '/public-assets/site.css' and not query:
            return FileResponse(HERE/'site.css',headers=headers)
        if re.fullmatch(rf'/sports(?:/(?:matches|teams|competitions)/{RESOURCE})?/?',path) and not query:
            return FileResponse(HERE/'sports.html',headers={**headers,'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"})
        is_api = bool(READ_ROUTES.fullmatch(path))
        if is_api:
            if query.keys()-{'date','timezone','competition','status','search','limit','offset'}:
                return denied
            try:
                if not 1<=int(query.get('limit',['50'])[0])<=50 or not 0<=int(query.get('offset',['0'])[0])<=10000:
                    return denied
            except ValueError:
                return denied
            key = path+'?'+request.url.query
            if key in cache and tick-cache[key][0]<15:
                return JSONResponse(cache[key][1],headers=headers)
            try:
                endpoint = load(config['api_endpoint_file'])['url'].rstrip('/')
                if urlsplit(endpoint).hostname!='127.0.0.1' or urlsplit(endpoint).scheme!='http':
                    return unavailable(True)
                bridge = load(config['bridge_secret_file'])['secret']
                stamp, nonce, user, role = str(int(time.time())), secrets.token_hex(16), 'joomla:public-gateway', 'reader'
                suffix = path+('?' + forward_query if forward_query else '')
                signed = '\n'.join(('GET',suffix,stamp,nonce,user,role,hashlib.sha256(b'').hexdigest()))
                upstream_headers = {'X-Dragon-User':user,'X-Dragon-Roles':role,'X-Dragon-Time':stamp,'X-Dragon-Nonce':nonce,
                                    'X-Dragon-Signature':hmac.new(bridge.encode(),signed.encode(),hashlib.sha256).hexdigest()}
            except (OSError,ValueError,KeyError):
                return unavailable(True)
            origin = endpoint
        else:
            if not public_frontend(path,query):
                return denied
            origin = joomla
            # Upstream trusts only this loopback gateway. No visitor cookies/auth headers pass through.
            scheme = 'https' if hostname.endswith('.trycloudflare.com') else request.headers.get('x-forwarded-proto','http')
            if scheme not in ('http','https'):
                scheme = 'http'
            upstream_headers = {'Host':host,'X-Forwarded-Host':host,'X-Forwarded-Proto':scheme,'Accept-Encoding':'identity'}
        try:
            async with concurrency, httpx.AsyncClient(timeout=httpx.Timeout(12, connect=3), follow_redirects=False, trust_env=False) as client:
                async with client.stream('GET',origin+path+('?' + forward_query if forward_query else ''),headers=upstream_headers) as upstream:
                    body = bytearray()
                    async for chunk in upstream.aiter_bytes():
                        body.extend(chunk)
                        if len(body)>6*1024*1024:
                            return unavailable(is_api)
                    status, content_type = upstream.status_code, upstream.headers.get('content-type','application/octet-stream')
                    location = upstream.headers.get('location')
        except (httpx.HTTPError,OSError):
            return unavailable(is_api)
        if is_api:
            if status>=500 or status in (401,403):
                return unavailable(True)
            try:
                result = sanitize(json.loads(body))
            except ValueError:
                return unavailable(True)
            if status==200:
                cache[key]=(tick,result)
                cache.move_to_end(key)
                while len(cache)>128:
                    cache.popitem(last=False)
            return JSONResponse(result,status_code=status,headers=headers)
        public_origin = ('https' if hostname.endswith('.trycloudflare.com') else upstream_headers['X-Forwarded-Proto'])+'://'+host
        if status>=500:
            return unavailable(False)
        if location:
            parsed = urlsplit(location)
            if parsed.netloc and parsed.netloc not in (urlsplit(joomla).netloc,host):
                return denied
            if not public_frontend(parsed.path or '/',parse_qs(parsed.query)):
                return denied
            return Response(status_code=status,headers={**headers,'Location':public_origin+(parsed.path or '/')+('?' + parsed.query if parsed.query else '')})
        if 'text/html' in content_type:
            text = bytes(body).decode('utf-8',errors='replace')
            text = text.replace(joomla,public_origin).replace('http://'+host,public_origin)
            # This boundary intentionally has no public login/search/write flow.
            # Suppress unsupported form controls in the response; source templates are untouched.
            text = re.sub(r'<form\b[^>]*>.*?</form>', '<p class="public-readonly-note">This public demonstration is read only. Account actions remain private.</p>', text, flags=re.I|re.S)
            nav = '<nav class="dragon-public-nav" aria-label="DRAGONHYDRA public navigation"><a href="/">Joomla home</a> · <a href="/sports">Browse DRAGONHYDRA matches</a></nav><link rel="stylesheet" href="/public-assets/site.css">'
            text = re.sub(r'(<body\b[^>]*>)',lambda m:m.group()+nav,text,count=1,flags=re.I)
            body = text.encode('utf-8')
        return Response(content=bytes(body) if request.method=='GET' else b'',status_code=status,media_type=content_type.split(';')[0],headers=headers)
    return app


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',type=Path,default=BASE/'gateway.json')
    parser.add_argument('--port',type=int,default=18734)
    parser.add_argument('--state',type=Path)
    args=parser.parse_args()
    import uvicorn
    app=create_gateway(args.config)
    listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
    listener.bind(('127.0.0.1',args.port))
    state = args.state.resolve() if args.state else (BASE/'evidence' if (BASE/'evidence').is_dir() else BASE/'state')
    state.mkdir(parents=True, exist_ok=True)
    (state/'gateway-process.json').write_text(json.dumps({'pid':__import__('os').getpid(),'port':listener.getsockname()[1],
        'config':str(args.config.resolve()),'state':str(state)}),encoding='utf-8')
    server=uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='info',timeout_graceful_shutdown=5))
    server.run(sockets=[listener])


if __name__=='__main__':
    main()
