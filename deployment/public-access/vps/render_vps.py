"""Render scoped VPS files offline. No remote access, installation or reload."""
from __future__ import annotations
import argparse
import base64
import hashlib
import ipaddress
import json
from pathlib import Path
import struct

PUBLIC_ROOT = Path(__file__).resolve().parents[1]
MARKER = '# DRAGONHYDRA managed public gateway v1; preserve unrelated configuration.\n'


def public_key(path):
    raw = Path(path).read_bytes()
    if len(raw) > 16384 or b'PRIVATE KEY' in raw:
        raise ValueError('Supply one public SSH key, never a private key.')
    lines = [line.strip() for line in raw.decode('ascii').splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError('Supply exactly one public SSH key.')
    fields = lines[0].split()
    allowed = {'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'}
    if len(fields) < 2 or fields[0] not in allowed:
        raise ValueError('Use an Ed25519 or supported ECDSA public key with no preexisting key options.')
    blob = base64.b64decode(fields[1], validate=True)
    if len(blob) < 8:
        raise ValueError('Invalid SSH public key encoding.')
    length = struct.unpack('>I', blob[:4])[0]
    if blob[4:4 + length].decode('ascii') != fields[0]:
        raise ValueError('SSH public key algorithm mismatch.')
    return fields[0] + ' ' + fields[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ip')
    parser.add_argument('--public-key-file', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if not args.ip or args.ip == 'VPS_PUBLIC_IP' or not args.public_key_file:
        print(json.dumps({'status': 'requires_configuration', 'deployed': False,
                          'missing': ['actual authorized public IPv4', 'Windows tunnel identity public-key file']}))
        return
    address = ipaddress.ip_address(args.ip)
    if address.version != 4 or not address.is_global:
        raise ValueError('Supply the actual authorized public IPv4 address.')
    key = public_key(args.public_key_file)
    output = (args.output or PUBLIC_ROOT / 'vps/generated' / str(address)).resolve()
    if not output.is_relative_to(PUBLIC_ROOT):
        raise ValueError('Rendered files must remain inside deployment/public-access.')
    output.mkdir(parents=True, exist_ok=True)
    nginx = (PUBLIC_ROOT / 'reverse-proxy/vps-nginx.conf.example').read_text(encoding='utf-8').replace('VPS_PUBLIC_IP', str(address))
    sshd = (PUBLIC_ROOT / 'tunnel/sshd-dragonhydra.conf.example').read_text(encoding='utf-8')
    authorized = ('restrict,port-forwarding,permitlisten="127.0.0.1:18080" '
                  + key + ' dragonhydra-outbound-tunnel\n')
    payloads = {'dragonhydra-public.conf': MARKER + nginx,
                '99-dragonhydra-tunnel.conf': MARKER + sshd,
                'authorized_keys': MARKER + authorized}
    files = []
    for name, text in payloads.items():
        raw = text.encode('utf-8')
        (output / name).write_bytes(raw)
        files.append({'name': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    receipt = {'status': 'prepared_not_deployed', 'public_ip': str(address),
               'target_url': f'http://{address}/', 'output': str(output), 'files': files,
               'forward': 'VPS127.0.0.1:18080 -> Windows127.0.0.1:18734',
               'domain_required': False, 'certificate_required_for_http': False,
               'remote_execution': False, 'linux_configuration_validation': 'not run by renderer'}
    (output / 'render-manifest.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
