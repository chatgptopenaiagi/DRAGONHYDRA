"""Windows service-identity DPAPI vault; headless environment credentials elsewhere."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re

from .core import ConnectorError


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect_bytes(raw, decrypt=False):
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt32, kernel32 = ctypes.WinDLL('crypt32', use_last_error=True), ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ConnectorError('VAULT_IDENTITY_MISMATCH', 'Vault decryption requires the same Windows service identity. Reauthorize this connection after an identity change.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel32.LocalFree(target.data)


class Vault:
    def __init__(self, state):
        self.directory = Path(state) / 'vault'

    def path(self, provider):
        if not re.fullmatch(r'[a-z0-9-]{1,60}', provider):
            raise LookupError('CONNECTION_NOT_FOUND')
        return self.directory / (provider+'.dpapi')

    def get(self, provider):
        env = os.environ.get('DRAGONHYDRA_'+provider.upper().replace('-', '_')+'_KEY')
        if env:
            return env
        path = self.path(provider)
        if not path.exists():
            return None
        if os.name != 'nt':
            raise ConnectorError('VAULT_PLATFORM', 'Configure a protected service environment credential on this platform.')
        return protect_bytes(base64.b64decode(path.read_bytes()), decrypt=True).decode('utf-8')

    def configured(self, provider):
        return bool(os.environ.get('DRAGONHYDRA_'+provider.upper().replace('-', '_')+'_KEY') or self.path(provider).exists())

    def put(self, provider, secret):
        if os.name != 'nt':
            raise ConnectorError('VAULT_PLATFORM', 'Use the protected headless service environment DRAGONHYDRA_'+provider.upper().replace('-', '_')+'_KEY.')
        from ..server import protect
        self.directory.mkdir(exist_ok=True)
        path = self.path(provider)
        temp = path.with_suffix('.tmp')
        try:
            with temp.open('wb') as out:
                out.write(base64.b64encode(protect_bytes(secret.encode('utf-8'))))
            protect(temp)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def delete(self, provider):
        self.path(provider).unlink(missing_ok=True)
