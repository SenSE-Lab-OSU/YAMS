# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('gradio_client')
datas += collect_data_files('gradio')
datas += collect_data_files('safehttpx')
datas += collect_data_files('groovy')
datas += collect_data_files('scipy')

# liblsl is not bundled in the macOS pylsl wheel — find it from conda or homebrew
_liblsl_candidates = [
    os.path.join(os.environ.get('CONDA_PREFIX', ''), 'lib', 'liblsl.dylib'),
    '/opt/homebrew/lib/liblsl.dylib',
    '/usr/local/lib/liblsl.dylib',
]
_liblsl = next((p for p in _liblsl_candidates if os.path.exists(p)), None)
if _liblsl is None:
    raise FileNotFoundError(
        "liblsl.dylib not found. Install via conda (`conda install -c conda-forge liblsl`) "
        "or homebrew (`brew install labstreaminglayer/tap/lsl`)."
    )

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[(_liblsl, 'pylsl/lib')],
    datas=datas,
    hiddenimports=['pylsl'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
    module_collection_mode={
        'gradio': 'py',  # Collect gradio package as source .py files
    },
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YAMS_MacOS_arm64',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['yams/resources/icons/yams.icns'],
)
