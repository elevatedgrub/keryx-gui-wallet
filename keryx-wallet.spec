# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Keryx Wallet desktop GUI.
#
# Produces a SINGLE self-contained executable (the Python wallet + PyQt6 +
# pexpect + qrcode bundled in). It does NOT bundle keryx-cli — that stays a
# user-supplied binary located at runtime via PATH, $KERYX_CLI, or --cli-path.
#
# Build:  pyinstaller keryx-wallet.spec
# Output: dist/keryx-wallet   (a single executable)

block_cipher = None

from PyInstaller.utils.hooks import collect_all, collect_data_files
import os as _os, glob as _glob
import PyQt6 as _pyqt6mod

# qrcode is pure Python (QR is rendered with QPainter, no Pillow). Bundle it whole.
_qr_datas, _qr_bins, _qr_hidden = collect_all('qrcode')

# --- Qt: bundle ONLY the libraries the app actually loads --------------------
# The wallet imports only QtCore/QtGui/QtWidgets. Ship just those Qt libs (+
# libQt6DBus and libQt6XcbQpa that the xcb platform plugin needs, + the ICU libs
# Core needs) AT ROOT, where the bootloader's LD_LIBRARY_PATH finds them first —
# so an older *system* Qt can't shadow them ("version `Qt_6.11' not found"). This
# also avoids bundling the full ~170 MB Qt6/lib (Quick3D, Multimedia, FFmpeg, all
# of QML) that we never touch.
_qt_lib_dir = _os.path.join(_os.path.dirname(_pyqt6mod.__file__), 'Qt6', 'lib')
_QT_KEEP = ('libQt6Core', 'libQt6Gui', 'libQt6Widgets', 'libQt6DBus',
            'libQt6XcbQpa', 'libicudata', 'libicui18n', 'libicuuc')
_qt_root_libs = [
    (_os.path.basename(_so), _so, 'BINARY')
    for _so in _glob.glob(_os.path.join(_qt_lib_dir, '*.so*'))
    if _os.path.basename(_so).startswith(_QT_KEEP)
]
# Only the small Qt plugin groups we need; skips translations and the big unused
# groups (multimedia, sqldrivers, qml/quick, …). 'platforms' (xcb) is essential.
_pyqt6_datas = collect_data_files('PyQt6', includes=[
    'Qt6/plugins/platforms/*',
    'Qt6/plugins/platforminputcontexts/*',
    'Qt6/plugins/imageformats/*',
    'Qt6/plugins/iconengines/*',
])

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=_qr_bins,
    datas=_pyqt6_datas + _qr_datas + [
           ('assets/keryx.png', 'assets'),
           ('assets/keryx-256.png', 'assets'),
           ('assets/keryx-128.png', 'assets'),
           ('assets/keryx-48.png', 'assets'),
           ('assets/globe-green.png', 'assets'),
           ('assets/globe-dark.png', 'assets'),
           ('assets/addressbook-green.png', 'assets'),
           ('assets/addressbook-dark.png', 'assets'),
           ('assets/keryx-header.png', 'assets')],
    hiddenimports=[
        # pexpect imports submodules dynamically on Linux
        'pexpect',
        'ptyprocess',
        'qrcode',
    ] + _qr_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # trim large unused stacks to keep the binary smaller
        'tkinter',
        'matplotlib',
        'numpy',
        'PIL',
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.Qt3DCore',
        'PyQt6.QtMultimedia',
        'PyQt6.QtBluetooth',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# --- Qt lib placement: slim + conflict-free ---------------------------------
# 1) Drop ROOT-level Qt/ICU libs PyInstaller's dep-scan pulled from an older
#    *system* Qt (these shadow the wheel's 6.11 via LD_LIBRARY_PATH).
# 2) Drop any full Qt6/lib subdir copy a hook may have added.
# 3) Add only our slim wheel keep-list at root.
a.binaries = [
    (n, p, t) for (n, p, t) in a.binaries
    if not (_os.path.basename(n).startswith(('libQt6', 'libicu'))
            and _os.path.dirname(n) in ('', '.'))
    and '/Qt6/lib/' not in n.replace('\\', '/')
]
a.binaries += _qt_root_libs

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
    upx=False,                # UPX can corrupt Qt .so libs → load failures; keep off
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # GUI app — no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/keryx.ico',  # add an icon here if you have one
)
