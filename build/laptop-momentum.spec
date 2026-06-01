# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Laptop Momentum.

Build the single exe::

    pyinstaller build/laptop-momentum.spec

Or with the ``--noconsole`` flag already included below.
"""
import sys
from pathlib import Path

block_cipher = None

proj_root = str(Path(SPECPATH).parent)

a = Analysis(
    [proj_root + '/main.py'],
    pathex=[proj_root],
    binaries=[],
    datas=[
        (proj_root + '/favicon.ico', '.'),
        (proj_root + '/favicon.png', '.'),
    ],
    hiddenimports=[
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        'pynput.keyboard._xorg',
        'pynput.mouse._xorg',
        'PySide6.QtMultimedia',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LaptopMomentum',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # no console window in release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=proj_root + '/favicon.ico',
)

# On macOS create a .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='LaptopMomentum.app',
        icon=None,
        bundle_identifier='com.laptopmomentum.app',
    )
