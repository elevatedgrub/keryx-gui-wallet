"""
PyInstaller runtime hook: default the Qt platform to xcb (X11/XWayland).

The bundle ships the Wayland platform plugin, which makes Qt draw its own generic
client-side window decorations (round icon, odd buttons, different frame). The
wallet was designed for the standard X11 decorations, so default to xcb unless
the user explicitly overrides QT_QPA_PLATFORM.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
