"""Entry point: python -m keryx_wallet [--cli-path /path/to/keryx-cli]"""
import os
import sys
import argparse
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from keryx_wallet.ui.main_window import MainWindow
from keryx_wallet.ui.theme import stylesheet


def _icon_path():
    """Locate the bundled icon both when run from source and from a PyInstaller
    bundle (which unpacks data to sys._MEIPASS)."""
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(os.path.join(base, "assets", "keryx.png"))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "..", "assets", "keryx.png"))
    candidates.append(os.path.join(os.getcwd(), "assets", "keryx.png"))
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""


def _ensure_desktop_integration():
    """
    On first run, install a user-level .desktop entry + icon into
    ~/.local/share so the app menu and taskbar show the Keryx icon (instead of a
    generic gear) — without requiring a separate install step or sudo.

    Silent and best-effort: any failure is ignored and the app still runs.
    Skips entirely when running from source (only does this for the built
    executable, where sys.frozen is set), so dev runs don't litter the system.
    """
    try:
        if not getattr(sys, "frozen", False):
            return  # only auto-install for the built binary, not source runs
        exe = os.path.abspath(sys.executable)
        home = os.path.expanduser("~")
        apps = os.path.join(home, ".local", "share", "applications")
        icons = os.path.join(home, ".local", "share", "icons", "hicolor")
        desktop_file = os.path.join(apps, "keryx-wallet.desktop")

        # Copy icons into the user icon theme (best-effort, multiple sizes).
        import shutil
        base = getattr(sys, "_MEIPASS", "")
        for s in (48, 128, 256):
            src = os.path.join(base, "assets", f"keryx-{s}.png") if base else ""
            if src and os.path.exists(src):
                dst_dir = os.path.join(icons, f"{s}x{s}", "apps")
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copyfile(src, os.path.join(dst_dir, "keryx-emblem.png"))

        # Write/refresh the .desktop entry pointing at THIS binary.
        os.makedirs(apps, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Keryx Wallet\n"
            "Comment=Desktop wallet for the Keryx network\n"
            f"Exec={exe}\n"
            "Icon=keryx-emblem\n"
            "Terminal=false\n"
            "Categories=Finance;Network;\n"
            "StartupWMClass=keryx-wallet\n"
        )
        # Rewrite if missing, if the binary moved, OR if the entry is stale
        # (e.g. an older install that referenced a different icon name).
        existing = ""
        if os.path.exists(desktop_file):
            try:
                with open(desktop_file, "r", encoding="utf-8") as f:
                    existing = f.read()
            except Exception:
                existing = ""
        needs_write = (
            f"Exec={exe}" not in existing
            or "Icon=keryx-emblem" not in existing
        )
        if needs_write:
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
        # Always refresh the icon cache + desktop database (the icon files above
        # are copied every launch, so the cache must be refreshed every launch
        # too — otherwise GTK keeps showing a stale cached icon even though the
        # new icon is already on disk).
        import subprocess
        for cmd in (
            ["gtk-update-icon-cache", "-f", icons],
            ["update-desktop-database", apps],
        ):
            try:
                subprocess.run(cmd, check=False,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10)
            except Exception:
                pass
    except Exception:
        pass  # never block startup on desktop integration


def _ask_language(parent=None):
    """First-run language picker. Returns the chosen language code or None."""
    try:
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QListWidget, QPushButton, QLabel)
        from PyQt6.QtCore import Qt
        from keryx_wallet.core import i18n
        from keryx_wallet.ui.theme import TOKENS, MONO

        dlg = QDialog(parent)
        dlg.setWindowTitle("")
        dlg.setModal(True)
        dlg.setMinimumWidth(360)
        dlg.setStyleSheet(
            f"QDialog {{ background:{TOKENS['bg']}; }}"
            f"QLabel {{ color:{TOKENS['green']}; font-family:{MONO}; "
            f"font-size:15px; font-weight:700; }}"
            f"QListWidget {{ background:{TOKENS['surface_2']}; "
            f"color:{TOKENS['text']}; font-family:{MONO}; border:1px solid "
            f"{TOKENS['border']}; }}"
            f"QListWidget::item:selected {{ background:{TOKENS['green_dim']}; "
            f"color:{TOKENS['bg']}; }}"
            f"QPushButton {{ background:{TOKENS['green']}; color:{TOKENS['bg']}; "
            f"border:none; border-radius:6px; padding:7px 20px; "
            f"font-family:{MONO}; font-weight:700; }}")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Choose your language / Выберите язык / 选择语言"))
        lst = QListWidget()
        codes = list(i18n.LANGUAGES.keys())
        for code in codes:
            lst.addItem(i18n.LANGUAGES[code])
        lst.setCurrentRow(0)
        v.addWidget(lst)
        btn = QPushButton("OK")
        btn.clicked.connect(dlg.accept)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        v.addWidget(btn)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return codes[lst.currentRow()]
    except Exception:
        pass
    return None


def main():
    # Log any uncaught exception to a file so hard-to-see crashes (e.g. a send
    # that closes the window) leave a traceback we can inspect.
    import traceback as _tb
    _log_path = os.path.expanduser("~/.keryx-wallet-gui.log")

    def _excepthook(exc_type, exc_value, exc_tb):
        try:
            with open(_log_path, "a", encoding="utf-8") as f:
                f.write("\n=== Uncaught exception ===\n")
                _tb.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass
        _tb.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    parser = argparse.ArgumentParser(
        prog="keryx-wallet",
        description="Desktop GUI for the Keryx wallet (front-end for keryx-cli).",
    )
    parser.add_argument(
        "--cli-path", default="",
        help="Full path to the keryx-cli binary. If omitted, the KERYX_CLI "
             "environment variable and then the system PATH are checked.",
    )
    args, qt_args = parser.parse_known_args()

    _ensure_desktop_integration()

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("Keryx Wallet")

    # Show tooltips quickly (200 ms instead of Qt's ~700 ms default) via a proxy
    # style that overrides the wake-up delay style hint.
    try:
        from PyQt6.QtWidgets import QProxyStyle, QStyle

        class _FastTooltipStyle(QProxyStyle):
            def styleHint(self, hint, option=None, widget=None, returnData=None):
                if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
                    return 200
                return super().styleHint(hint, option, widget, returnData)

        app.setStyle(_FastTooltipStyle(app.style()))
    except Exception:
        pass
    # Tell GNOME/Wayland which .desktop entry this app maps to, so the taskbar
    # uses our icon instead of a generic gear. The name must match the installed
    # .desktop filename (without the .desktop extension): keryx-wallet.desktop.
    try:
        app.setDesktopFileName("keryx-wallet")
    except Exception:
        pass
    icon = _icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))
    app.setStyleSheet(stylesheet())

    # Resolve language BEFORE building the window, so all labels are translated.
    from keryx_wallet.core import i18n, config as _cfg
    need_picker = False
    try:
        saved_lang = _cfg.get_language()
        if saved_lang and saved_lang in i18n.LANGUAGES:
            i18n.set_language(saved_lang)
        else:
            need_picker = True
    except Exception:
        need_picker = True

    # First run (no saved language): show the picker now, before the window, so
    # the very first session is already in the chosen language. We guard against
    # the app quitting while no main window exists.
    if need_picker:
        try:
            app.setQuitOnLastWindowClosed(False)
            chosen = _ask_language(None)
            app.setQuitOnLastWindowClosed(True)
            if chosen:
                i18n.set_language(chosen)
                _cfg.set_language(chosen)
        except Exception:
            pass

    win = MainWindow(cli_path=args.cli_path)
    if icon:
        win.setWindowIcon(QIcon(icon))

    # Give clickable controls a pointing-hand cursor.
    try:
        from PyQt6.QtWidgets import QPushButton, QComboBox, QCheckBox, QRadioButton
        from PyQt6.QtCore import Qt as _Qt
        for _w in win.findChildren((QPushButton, QComboBox, QCheckBox, QRadioButton)):
            _w.setCursor(_Qt.CursorShape.PointingHandCursor)
    except Exception:
        pass

    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
