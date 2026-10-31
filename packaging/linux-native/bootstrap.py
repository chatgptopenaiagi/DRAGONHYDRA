"""Relocatable installed entry point; no checkout or user packages are imported."""
from pathlib import Path
import importlib
from importlib import metadata
import json
import os
import runpy
import sys

if sys.version_info[:2] != (3, 14):
    raise SystemExit('DRAGONHYDRA API requires the declared CPython3.14 runtime.')
sys.path.insert(0, str(Path(__file__).resolve().parent/'site-packages'))
# Pin only this process to the bundled IANA database, before any application
# import can populate ZoneInfo's cache. Host timezone packages are unchanged.
os.environ['PYTHONTZPATH'] = ''
if sys.argv[1:] == ['--native-runtime-info']:
    import zoneinfo
    names = ('dragonhydra', 'fastapi', 'uvicorn', 'openpyxl', 'tzdata', 'pydantic_core')
    modules = {name: importlib.import_module(name).__file__ for name in names}
    print(json.dumps({'python': sys.version, 'modules': modules, 'timezone_path': list(zoneinfo.TZPATH),
                      'tzdata_version': metadata.version('tzdata'),
                      'timezone_probe': str(zoneinfo.ZoneInfo('America/New_York'))}, indent=2))
    raise SystemExit(0)
endpoint = runpy.run_path(str(Path(__file__).with_name('managed_endpoint.py')))
sys.argv[1:] = endpoint['managed_arguments'](sys.argv[1:])
runpy.run_module('dragonhydra.server', run_name='__main__')
