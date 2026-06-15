"""
send_dialog.py — the two-step safe send flow.

SAFETY MODEL (critical):
`keryx-cli send` broadcasts IMMEDIATELY after the wallet password is entered —
there is no CLI-side confirmation. The password is the point of no return.

Therefore this dialog enforces a strict order:
  Step 1 — REVIEW: the user sees destination, amount, priority fee, and (after an
           `estimate`) the fee/total. They must explicitly click "Confirm & Sign".
  Step 2 — PASSWORD: only after confirming do we collect the password. Submitting
           the password triggers the broadcast.

The user can cancel freely in step 1. Once the password is submitted in step 2,
the transaction is sent. The dialog never pre-fills or remembers the password.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFormLayout, QFrame, QWidget, QMessageBox,
)
from PyQt6.QtCore import Qt
from keryx_wallet.core.i18n import t as _t
from keryx_wallet.ui.theme import WARNING_LABEL


class SendConfirmDialog(QDialog):
    """
    Modal dialog returning the password via .password() only if the user
    completed both review and password entry. Returns QDialog.Accepted only
    when the user has explicitly confirmed and entered a password.
    """

    def __init__(self, address: str, amount: str, priority_fee: str,
                 estimate: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("confirm_send"))
        self.setModal(True)
        self.setMinimumWidth(440)

        self._address = address
        self._amount = amount
        self._priority_fee = priority_fee
        self._password_value = ""

        root = QVBoxLayout(self)

        warn = QLabel(
            _t("send_warning")
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(WARNING_LABEL)
        root.addWidget(warn)

        # ── Review section ───────────────────────────────────────────────────
        review = QFormLayout()
        addr_lbl = QLabel(address)
        addr_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        addr_lbl.setWordWrap(True)
        review.addRow(_t("to"), addr_lbl)
        review.addRow(_t("amount"), QLabel(f"{amount} KRX"))
        review.addRow(_t("priority_fee"), QLabel(f"{priority_fee} KRX"))
        if estimate:
            review.addRow(_t("estimated_fee"), QLabel(f"{estimate.get('fees','?')} KRX"))
            review.addRow(_t("estimated_total"), QLabel(f"{estimate.get('total','?')} KRX"))
        root.addLayout(review)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        # ── Step 1 buttons ───────────────────────────────────────────────────
        self._review_row = QWidget()
        rrl = QHBoxLayout(self._review_row); rrl.setContentsMargins(0, 0, 0, 0)
        cancel1 = QPushButton(_t("cancel"))
        confirm = QPushButton(_t("confirm_sign"))
        confirm.setDefault(True)
        cancel1.clicked.connect(self.reject)
        confirm.clicked.connect(self._show_password_step)
        rrl.addStretch(1); rrl.addWidget(cancel1); rrl.addWidget(confirm)
        root.addWidget(self._review_row)

        # ── Step 2 (hidden until confirmed) ──────────────────────────────────
        self._pw_row = QWidget()
        pwl = QVBoxLayout(self._pw_row); pwl.setContentsMargins(0, 0, 0, 0)
        pwl.addWidget(QLabel(_t("enter_pw_broadcast")))
        self._pw_edit = QLineEdit()
        self._pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_edit.returnPressed.connect(self._submit_password)
        pwl.addWidget(self._pw_edit)
        btns = QHBoxLayout()
        cancel2 = QPushButton(_t("cancel"))
        broadcast = QPushButton(_t("broadcast_tx"))
        broadcast.setStyleSheet("font-weight:600;")
        cancel2.clicked.connect(self.reject)
        broadcast.clicked.connect(self._submit_password)
        btns.addStretch(1); btns.addWidget(cancel2); btns.addWidget(broadcast)
        pwl.addLayout(btns)
        self._pw_row.setVisible(False)
        root.addWidget(self._pw_row)

    def _show_password_step(self):
        self._review_row.setVisible(False)
        self._pw_row.setVisible(True)
        self._pw_edit.setFocus()

    def _submit_password(self):
        pw = self._pw_edit.text()
        if not pw:
            QMessageBox.warning(self, "Password required",
                                "Enter your wallet password to broadcast.")
            return
        self._password_value = pw
        self.accept()

    def password(self) -> str:
        """The entered password — only valid if the dialog was Accepted."""
        return self._password_value
