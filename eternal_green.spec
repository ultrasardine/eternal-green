# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Eternal Green macOS .app bundle.

Build with:
    pyinstaller eternal_green.spec

The resulting .app lives in dist/Eternal Green.app and runs as a
menu-bar-only application (no Dock icon).
"""

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ["eternal_green/tray.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # pystray macOS backend
        "pystray._darwin",
        # Settings window launched as subprocess via -m
        "eternal_green.settings_window",
        # Pillow image plugins used at runtime
        "PIL._tkinter_finder",
        # tkinter for the settings window subprocess
        "tkinter",
        "tkinter.ttk",
        "tkinter.filedialog",
        "tkinter.messagebox",
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
    [],
    exclude_binaries=True,
    name="Eternal Green",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No terminal window
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Eternal Green",
)

# --- macOS .app bundle ---
icon_path = Path("assets/icon.icns")
app = BUNDLE(
    coll,
    name="Eternal Green.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="com.eternalgreen.app",
    info_plist={
        "CFBundleName": "Eternal Green",
        "CFBundleDisplayName": "Eternal Green",
        "CFBundleVersion": "0.2.0",
        "CFBundleShortVersionString": "0.2.0",
        "LSMinimumSystemVersion": "10.15",
        # Hide from Dock — menu-bar only
        "LSUIElement": True,
        # Accessibility usage description (required for pyautogui)
        "NSAppleEventsUsageDescription": (
            "Eternal Green needs Accessibility access to simulate "
            "mouse movements and keystrokes."
        ),
    },
)
