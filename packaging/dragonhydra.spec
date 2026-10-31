# PyInstaller one-directory build; all paths derive from the checkout.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).resolve().parent
analysis = Analysis(
    [str(root / 'packaging' / 'windows_entry.py')],
    pathex=[str(root / 'src')],
    binaries=[], datas=[],
    hiddenimports=collect_submodules('dragonhydra'),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True,
    name='dragonhydra', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True,
)
collection = COLLECT(exe, analysis.binaries, analysis.datas,
                     strip=False, upx=False, name='dragonhydra')
