"""Single product server/worker coordinator. Run through Start-Dragonhydra.ps1."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import secrets

from .build_meta import VERSION, info as build_info


def protect(path):
    if os.name == 'nt':
        user = subprocess.check_output(['whoami'], text=True).strip()
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', user+':(F)', 'SYSTEM:(F)'], capture_output=True)
        if result.returncode:
            raise RuntimeError('SECRET_FILE_PERMISSION_FAILED')
    else:
        path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description='DRAGONHYDRA authenticated local server')
    parser.add_argument('--host', choices=['127.0.0.1'], default='127.0.0.1')
    parser.add_argument('--port', type=int, default=18743)
    parser.add_argument('--state', type=Path, default=Path('runtime/product'))
    parser.add_argument('--init-bridge', action='store_true', help='Create a protected Joomla bridge secret only if missing')
    parser.add_argument('--build-info', action='store_true', help='Print embedded source/version identity and exit')
    args = parser.parse_args()
    if args.build_info:
        print(json.dumps(build_info(), sort_keys=True))
        return
    args.state = args.state.resolve()
    args.state.mkdir(parents=True, exist_ok=True)
    # OS lock, not a PID file guess: a second launcher cannot create another worker for this state.
    lock = (args.state / 'server.lock').open('a+b')
    lock.seek(0)
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        raise SystemExit('DRAGONHYDRA state already has a running coordinator.') from None
    if args.init_bridge:
        bridge = args.state / 'joomla-bridge.json'
        try:
            with bridge.open('x', encoding='utf-8') as output:
                json.dump({'secret': secrets.token_urlsafe(48)}, output)
            protect(bridge)
        except FileExistsError:
            pass
    from .api import create_app
    import uvicorn
    app = create_app(args.state)
    protect(args.state / 'local-session.json')
    if (args.state / 'joomla-bridge.json').exists():
        protect(args.state / 'joomla-bridge.json')
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name == 'nt':
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        listener.bind((args.host, args.port))
    except OSError:
        raise SystemExit('Configured product port is busy; no unrelated service was stopped. Use --port 0 to allocate a free port.') from None
    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=listener.getsockname()[1], access_log=False, log_level='info', timeout_graceful_shutdown=5))
    app.state.shutdown_callback = lambda: setattr(server, 'should_exit', True)
    endpoint = args.state / 'endpoint.json'
    endpoint.write_text(json.dumps({'url': 'http://127.0.0.1:'+str(listener.getsockname()[1]), 'pid': os.getpid(),
                                    'backend': 'sqlite', 'version': VERSION, 'source_sha': build_info()['source_sha']}), encoding='utf-8')
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()
        lock.close()
        if endpoint.exists() and json.loads(endpoint.read_text()).get('pid') == os.getpid():
            endpoint.unlink()


if __name__ == '__main__':
    main()
