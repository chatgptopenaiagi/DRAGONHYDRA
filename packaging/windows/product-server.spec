from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

root = Path(SPECPATH).resolve().parents[1]
datas = [(str(root/'src/dragonhydra/resources'), 'dragonhydra/resources')]
datas += [(str(root/'src/dragonhydra/research_storage/schema_sqlserver.sql'),
           'dragonhydra/research_storage')]
metadata = os.environ.get('DRAGONHYDRA_BUILD_INFO')
if metadata:
    datas.append((metadata, 'dragonhydra'))
datas += collect_data_files('tzdata')
hidden = collect_submodules('uvicorn') + ['dragonhydra.local_ai_context', 'pyodbc']
analysis = Analysis([str(root/'packaging/windows/server_entry.py')], pathex=[str(root/'src')],
    binaries=[], datas=datas, hiddenimports=hidden, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['playwright','httpx','httpx2','IPython','pytest','numpy','pandas','tkinter'], noarchive=False, optimize=0)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='DRAGONHYDRA-Server',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True,
    version=str(root/'packaging/windows/version_info.txt'))
collection = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='DRAGONHYDRA-Server-x64')
