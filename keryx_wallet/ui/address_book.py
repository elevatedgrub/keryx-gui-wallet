"""
address_book.py — a themed dialog to save, select, and delete labeled Keryx
addresses. Opened from the book icon beside the Send destination field.

Selecting an entry returns its address to the caller (to fill the Send field).
Entries persist via keryx_wallet.core.config (address_book list).
"""

from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QWidget,
)
from PyQt6.QtCore import Qt

from keryx_wallet.core.i18n import t as _t
from keryx_wallet.core import config
from keryx_wallet.ui.theme import TOKENS, MONO

_ADDR_RE = re.compile(r"^keryx[a-z]*:[0-9a-z]+$", re.IGNORECASE)


class AddressBookDialog(QDialog):
    def __init__(self, parent=None, current_address: str = ""):
        super().__init__(parent)
        self._chosen = ""
        self.setWindowTitle("")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlags(
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(
            f"QDialog {{ background-color:{TOKENS['bg']}; "
            f"border:1px solid {TOKENS['green_dim']}; }}")

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(10)

        title = QLabel(_t("address_book"))
        title.setStyleSheet(
            f"color:{TOKENS['green']}; font-weight:700; font-size:15px;")
        v.addWidget(title)

        # Saved entries list.
        self.list = QListWidget()
        self.list.setStyleSheet(
            f"QListWidget {{ background-color:{TOKENS['surface']}; "
            f"color:{TOKENS['text']}; border:1px solid {TOKENS['green_dim']}; "
            f"border-radius:5px; }}"
            f"QListWidget::item {{ padding:6px; }}"
            f"QListWidget::item:selected {{ background-color:{TOKENS['green_dim']}; "
            f"color:{TOKENS['bg']}; }}")
        self.list.itemDoubleClicked.connect(lambda _i: self._use_selected())
        v.addWidget(self.list)

        # Add-new row: label + address + Save.
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText(_t("ab_label"))
        self.label_edit.setMaximumWidth(140)
        self.addr_edit = QLineEdit()
        self.addr_edit.setPlaceholderText(_t("ab_address"))
        if current_address:
            self.addr_edit.setText(current_address)
        save_btn = QPushButton(_t("ab_save"))
        save_btn.clicked.connect(self._save_new)
        for w in (self.label_edit, self.addr_edit):
            w.setStyleSheet(
                f"QLineEdit {{ background-color:{TOKENS['surface']}; "
                f"color:{TOKENS['text']}; border:1px solid {TOKENS['green_dim']}; "
                f"border-radius:4px; padding:5px; }}")
        add_row.addWidget(self.label_edit)
        add_row.addWidget(self.addr_edit, 1)
        add_row.addWidget(save_btn)
        v.addLayout(add_row)

        self.err = QLabel("")
        self.err.setStyleSheet(f"color:{TOKENS['red']}; font-size:12px;")
        self.err.setVisible(False)
        v.addWidget(self.err)

        # Action buttons.
        btns = QHBoxLayout()
        del_btn = QPushButton(_t("ab_delete"))
        del_btn.clicked.connect(self._delete_selected)
        use_btn = QPushButton(_t("ab_use"))
        use_btn.clicked.connect(self._use_selected)
        close_btn = QPushButton(_t("cancel"))
        close_btn.clicked.connect(self.reject)
        for b in (del_btn, use_btn, close_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        btns.addWidget(close_btn)
        btns.addWidget(use_btn)
        v.addLayout(btns)

        # Themed buttons (green hover) for all the buttons in this dialog.
        for b in (save_btn, del_btn, use_btn, close_btn):
            b.setStyleSheet(
                f"QPushButton {{ background-color:transparent; "
                f"border:1px solid {TOKENS['green_dim']}; border-radius:5px; "
                f"padding:6px 12px; color:{TOKENS['green']}; font-weight:600; }}"
                f"QPushButton:hover {{ background-color:{TOKENS['green_dim']}; "
                f"color:{TOKENS['bg']}; }}")

        self._reload()

    def _reload(self):
        self.list.clear()
        for e in config.get_address_book():
            label = e.get("label") or "(no label)"
            addr = e.get("address", "")
            short = addr if len(addr) <= 28 else addr[:14] + "…" + addr[-10:]
            item = QListWidgetItem(f"{label}\n{short}")
            item.setData(Qt.ItemDataRole.UserRole, addr)
            self.list.addItem(item)

    def _show_err(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)

    def _save_new(self):
        addr = self.addr_edit.text().strip()
        label = self.label_edit.text().strip()
        if not _ADDR_RE.match(addr):
            self._show_err(_t("invalid_address"))
            return
        config.add_address(label, addr)
        self.label_edit.clear()
        self.addr_edit.clear()
        self.err.setVisible(False)
        self._reload()

    def _delete_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        addr = item.data(Qt.ItemDataRole.UserRole)
        config.remove_address(addr)
        self._reload()

    def _use_selected(self):
        item = self.list.currentItem()
        if not item:
            return
        self._chosen = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def exec_and_get(self) -> str:
        """Show modally; return the chosen address, or '' if cancelled."""
        self.exec()
        return self._chosen
