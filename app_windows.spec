# -*- mode: python ; coding: utf-8 -*-
import os, pylsl
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('gradio_client')
datas += collect_data_files('gradio')
datas += collect_data_files('safehttpx')
datas += collect_data_files('groovy')
datas += collect_data_files('scipy')
# App artwork: the favicon is read at runtime via yams.config.favicon_path(),
# so it has to exist inside the bundle, not just next to the source tree.
datas += [('yams/resources/icons', 'yams/resources/icons')]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[(os.path.join(os.path.dirname(pylsl.__file__), 'lib'), 'pylsl/lib')],
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
    name='YAMS_Windows_x64',
    icon='yams/resources/icons/yams.ico',
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
)
