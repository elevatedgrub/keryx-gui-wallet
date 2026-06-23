# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Keryx Wallet desktop GUI — fully self-contained.
#
# collect_all('PyQt6') is used because PyInstaller's automatic PyQt6 hook does
# NOT bundle Qt on some Python builds (e.g. 3.14), producing a tiny binary that
# fails at launch with "Could not find the Qt platform plugin". Forcing the
# collection bundles Qt's libs + plugins so the binary is self-contained and
# needs no system Qt. keryx-cli is NOT bundled.
#
# Build:  pyinstaller keryx-wallet.spec   ->   dist/keryx-wallet

block_cipher = None

from PyInstaller.utils.hooks import collect_all
import os as _os

_qt_datas, _qt_bins, _qt_hidden = collect_all('PyQt6')

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=_qt_bins,
    datas=_qt_datas + [('assets/keryx.png', 'assets'),
           ('assets/keryx-256.png', 'assets'),
           ('assets/keryx-128.png', 'assets'),
           ('assets/keryx-48.png', 'assets'),
           ('assets/globe-green.png', 'assets'),
           ('assets/globe-dark.png', 'assets'),
           ('assets/addressbook-green.png', 'assets'),
           ('assets/addressbook-dark.png', 'assets'),
           ('assets/keryx-header.png', 'assets')],
    hiddenimports=[
        'pexpect',
        'ptyprocess',
        'qrcode',          # pure Python; QR rendered with QPainter (no Pillow)
    ] + _qt_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthook_xcb.py'],   # default to X11/xcb for normal window decorations
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'PIL',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Drop the SYSTEM Qt/ICU libs PyInstaller's dependency scan put at the bundle
# ROOT (your distro's newer Qt). They'd be loaded first via LD_LIBRARY_PATH and
# mix with the wheel's 6.4.2 libs (kept under PyQt6/Qt6/lib) → "undefined symbol
# ... Qt_6_PRIVATE_API". Removing them leaves only the consistent 6.4.2 set,
# which the PyQt6 bindings find via their RUNPATH ($ORIGIN/Qt6/lib).
a.binaries = [
    b for b in a.binaries
    if not (_os.path.basename(b[0]).startswith(('libQt6', 'libicu'))
            and _os.path.dirname(b[0]) in ('', '.'))
]
# Guard: drop any "binary" whose source isn't a real file (PyInstaller's scan can
# mis-resolve a name to a directory and crash the archive writer otherwise).
a.binaries = [b for b in a.binaries if _os.path.isfile(b[1])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='keryx-wallet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
