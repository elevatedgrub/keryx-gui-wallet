"""
dialogs.py — themed message/input dialogs matching the Keryx wallet theme.

The native QMessageBox/QInputDialog title bars can truncate ("Open failed" ->
"Op") when the dialog is narrow, and they don't fully pick up our dark theme.
These helpers build QDialogs we fully control: phosphor-green on near-black,
monospace, and wide enough that titles never truncate.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
)
from PyQt6.QtCore import Qt

from keryx_wallet.core.i18n import t as _t
from keryx_wallet.ui.theme import TOKENS, MONO

_MIN_W = 420


def _frame(dlg: QDialog, title: str):
    # Frameless: no OS title bar (which would otherwise show the app name
    # "Keryx Wallet"). The green heading inside is the only title. A subtle
    # border keeps it visually contained against the dark background.
    # Note: on Wayland, frameless windows cannot be positioned by the client and
    # are not auto-centered by the compositor, so they appear where the
    # compositor places them. We accept that to keep the clean frameless look.
    dlg.setWindowTitle("")
    dlg.setModal(True)
    dlg.setMinimumWidth(_MIN_W)
    dlg.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
    dlg.setStyleSheet(
        f"QDialog {{ background-color: {TOKENS['bg']}; "
        f"border: 1px solid {TOKENS['green_dim']}; border-radius: 8px; }}"
        f"QLabel {{ color: {TOKENS['text']}; font-family: {MONO}; font-size: 13px; }}"
    )
    _center_on_parent(dlg)


def _center_on_parent(dlg: QDialog):
    """Best-effort centering of the dialog over its parent. This works on X11
    but is a no-op on Wayland, where clients cannot position their own windows;
    there the dialog appears wherever the compositor places it."""
    parent = dlg.parent()

    def _do_center():
        try:
            if parent is not None and hasattr(parent, "frameGeometry"):
                pg = parent.frameGeometry()
                dg = dlg.frameGeometry()
                dlg.move(pg.center().x() - dg.width() // 2,
                         pg.center().y() - dg.height() // 2)
        except Exception:
            pass

    _orig_show = dlg.showEvent

    def _show(ev):
        _orig_show(ev)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, _do_center)

    dlg.showEvent = _show


def _title_label(text: str, color: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-family: {MONO}; font-size: 15px; font-weight: 700;")
    lbl.setWordWrap(True)
    return lbl


def _btn(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    from PyQt6.QtCore import Qt as _Qt
    b.setCursor(_Qt.CursorShape.PointingHandCursor)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ background:{TOKENS['green']}; color:{TOKENS['bg']}; "
            f"border:none; border-radius:6px; padding:7px 20px; font-family:{MONO}; "
            f"font-weight:700; min-width:80px; }}"
            f"QPushButton:hover {{ background:{TOKENS['green_dim']}; color:{TOKENS['text']}; }}")
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{TOKENS['surface_2']}; color:{TOKENS['text']}; "
            f"border:1px solid {TOKENS['border']}; border-radius:6px; padding:7px 20px; "
            f"font-family:{MONO}; min-width:80px; }}"
            f"QPushButton:hover {{ border-color:{TOKENS['green_dim']}; }}")
    return b


def message(parent, title: str, text: str, kind: str = "info"):
    """Themed message dialog. Shows the green heading; body only if it adds info
    beyond the heading (no duplicate of the title)."""
    color = {
        "info": TOKENS["green"],
        "success": TOKENS["green"],
        "warn": TOKENS["amber"],
        "error": TOKENS["red"],
    }.get(kind, TOKENS["green"])

    dlg = QDialog(parent)
    _frame(dlg, title)
    v = QVBoxLayout(dlg)
    v.addWidget(_title_label(title, color))
    # Only add a body line if it's meaningfully different from the title.
    if text and text.strip() and text.strip() != title.strip():
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(body)
    row = QHBoxLayout(); row.addStretch(1)
    ok = _btn(_t("ok"), primary=True)
    ok.clicked.connect(dlg.accept)
    row.addWidget(ok)
    v.addLayout(row)
    dlg.exec()


def confirm(parent, title: str, text: str,
            yes_text: str = None, no_text: str = None,
            danger: bool = False) -> bool:
    """Themed yes/no confirm. Green heading only; body shown if it adds info."""
    color = TOKENS["red"] if danger else TOKENS["green"]
    if yes_text is None:
        yes_text = _t("ok")
    if no_text is None:
        no_text = _t("cancel")
    dlg = QDialog(parent)
    _frame(dlg, title)
    v = QVBoxLayout(dlg)
    v.addWidget(_title_label(title, color))
    if text and text.strip() and text.strip() != title.strip():
        body = QLabel(text); body.setWordWrap(True)
        v.addWidget(body)
    row = QHBoxLayout(); row.addStretch(1)
    no = _btn(no_text, primary=False)
    yes = _btn(yes_text, primary=True)
    no.clicked.connect(dlg.reject)
    yes.clicked.connect(dlg.accept)
    row.addWidget(no); row.addWidget(yes)
    v.addLayout(row)
    return dlg.exec() == QDialog.DialogCode.Accepted


def get_password(parent, title: str, prompt: str):
    """Themed password input. The prompt is the single green heading — no
    separate window title or duplicate label. Returns (text, ok)."""
    dlg = QDialog(parent)
    _frame(dlg, title)
    v = QVBoxLayout(dlg)
    # The prompt itself is the green heading; don't also show `title`.
    v.addWidget(_title_label(prompt, TOKENS["green"]))
    field = QLineEdit()
    field.setEchoMode(QLineEdit.EchoMode.Password)
    field.setStyleSheet(
        f"QLineEdit {{ background:{TOKENS['surface_2']}; color:{TOKENS['text']}; "
        f"border:1px solid {TOKENS['border']}; border-radius:6px; padding:7px 9px; "
        f"font-family:{MONO}; }}"
        f"QLineEdit:focus {{ border-color:{TOKENS['green']}; }}")
    v.addWidget(field)
    row = QHBoxLayout(); row.addStretch(1)
    cancel = _btn(_t("cancel"), primary=False)
    okb = _btn(_t("ok"), primary=True)
    cancel.clicked.connect(dlg.reject)
    okb.clicked.connect(dlg.accept)
    field.returnPressed.connect(dlg.accept)
    row.addWidget(cancel); row.addWidget(okb)
    v.addLayout(row)
    field.setFocus()
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return field.text(), True
    return "", False


def get_text(parent, title: str, prompt: str, initial: str = ""):
    """Themed single-line text input (visible echo). The prompt is the green
    heading. Pre-fills `initial` and selects it. Returns (text, ok)."""
    dlg = QDialog(parent)
    _frame(dlg, title)
    v = QVBoxLayout(dlg)
    v.addWidget(_title_label(prompt, TOKENS["green"]))
    field = QLineEdit()
    field.setText(initial)
    field.setStyleSheet(
        f"QLineEdit {{ background:{TOKENS['surface_2']}; color:{TOKENS['text']}; "
        f"border:1px solid {TOKENS['border']}; border-radius:6px; padding:7px 9px; "
        f"font-family:{MONO}; }}"
        f"QLineEdit:focus {{ border-color:{TOKENS['green']}; }}")
    v.addWidget(field)
    row = QHBoxLayout(); row.addStretch(1)
    cancel = _btn(_t("cancel"), primary=False)
    okb = _btn(_t("ok"), primary=True)
    cancel.clicked.connect(dlg.reject)
    okb.clicked.connect(dlg.accept)
    field.returnPressed.connect(dlg.accept)
    row.addWidget(cancel); row.addWidget(okb)
    v.addLayout(row)
    field.setFocus()
    field.selectAll()
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return field.text().strip(), True
    return "", False


# ── Drop-in wrappers matching QMessageBox.<level>(parent, title, text) ────────
def _warn(parent, title, text, *args, **kwargs):
    message(parent, title, str(text), "warn")


def _error(parent, title, text, *args, **kwargs):
    message(parent, title, str(text), "error")


def _info(parent, title, text, *args, **kwargs):
    message(parent, title, str(text), "info")
