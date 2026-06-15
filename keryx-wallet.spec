# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the Keryx Wallet desktop GUI.
#
# Produces a SINGLE self-contained executable (the Python wallet + PyQt6 +
# pexpect + qrcode bundled in). It does NOT bundle keryx-cli — that remains a
# user-supplied binary located at runtime via PATH, $KERYX_CLI, or --cli-path
# (Option A). The wallet calls keryx-cli; it does not contain it.
#
# Build:  pyinstaller keryx-wallet.spec
# Output: dist/keryx-wallet   (a single executable)

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[('assets/keryx.png', 'assets'),
           ('assets/keryx-256.png', 'assets'),
           ('assets/keryx-128.png', 'assets'),
           ('assets/keryx-48.png', 'assets'),
           ('assets/globe-green.png', 'assets'),
           ('assets/globe-dark.png', 'assets'),
           ('assets/keryx-header.png', 'assets')],
    hiddenimports=[
        # pexpect imports submodules dynamically on Linux
        'pexpect',
        'ptyprocess',
        # qrcode image backend
        'qrcode',
        'qrcode.image.pil',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # trim large unused stacks to keep the binary smaller
        'tkinter',
        'matplotlib',
        'numpy',
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
    upx=True,                 # compress if upx is installed; harmless if not
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
