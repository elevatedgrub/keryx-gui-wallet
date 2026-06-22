"""
create_dialog.py — collect inputs for `wallet create <name>` and safely present
the resulting mnemonic for offline backup.

Two dialogs:

  CreateInputDialog  — gathers name, account title (optional), phishing hint
                       (optional), encryption password (required, confirmed in
                       the GUI before we ever touch the CLI), and an optional
                       bip39 passphrase. Enforces the "name is mandatory" and
                       "password required" rules up front.

  MnemonicBackupDialog — shows the mnemonic and deposit address AFTER creation,
                       behind an explicit "I have written this down" gate. The
                       mnemonic is shown once; the dialog reminds the user it
                       will never be shown again and is not stored by the GUI.
"""

from __future__ import annotations

from keryx_wallet.core.i18n import t as _t
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QPlainTextEdit, QMessageBox, QWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication

from keryx_wallet.ui.theme import WARNING_LABEL, CAUTION_LABEL, ACCENT_LABEL, MONO_BLOCK
from keryx_wallet.ui import dialogs


def _copy_button(text_to_copy: str) -> QPushButton:
    """A 'Copy phrase' button with brief 'Copied' feedback (like copy-address)."""
    btn = QPushButton(_t("copy_phrase"))

    def do_copy():
        QApplication.clipboard().setText(text_to_copy or "")
        btn.setText(_t("copied"))
        QTimer.singleShot(1200, lambda: btn.setText(_t("copy_phrase")))

    btn.clicked.connect(do_copy)
    return btn


class CreateInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("create_wallet"))
        self.setModal(True)
        self.setMinimumWidth(460)

        self._values = None

        v = QVBoxLayout(self)
        intro = QLabel(_t("create_intro"))
        intro.setStyleSheet(ACCENT_LABEL)
        v.addWidget(intro)

        form = QFormLayout()
        self.name = QLineEdit(); self.name.setPlaceholderText(_t("ph_letters_digits"))
        self.title = QLineEdit(); self.title.setPlaceholderText(_t("ph_optional_skip"))
        self.hint = QLineEdit(); self.hint.setPlaceholderText(_t("ph_antiphishing"))
        self.pw1 = QLineEdit(); self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.bip39 = QLineEdit(); self.bip39.setEchoMode(QLineEdit.EchoMode.Password)
        self.bip39.setPlaceholderText(_t("ph_bip39_create"))

        form.addRow(_t("wallet_name"), self.name)
        form.addRow(_t("account_title"), self.title)
        form.addRow(_t("phishing_hint"), self.hint)
        form.addRow(_t("encryption_password"), self.pw1)
        form.addRow(_t("confirm_password"), self.pw2)
        form.addRow(_t("bip39_passphrase"), self.bip39)
        v.addLayout(form)

        note = QLabel(
            _t("create_pw_note")
        )
        note.setWordWrap(True)
        note.setStyleSheet(CAUTION_LABEL)
        v.addWidget(note)

        row = QHBoxLayout()
        cancel = QPushButton(_t("cancel"))
        create = QPushButton(_t("create_wallet"))
        create.setDefault(True)
        cancel.clicked.connect(self.reject)
        create.clicked.connect(self._on_create)
        row.addStretch(1); row.addWidget(cancel); row.addWidget(create)
        v.addLayout(row)

    def _on_create(self):
        import re
        name = self.name.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name or ""):
            dialogs.message(self, "Name is required: 1-64 of letters, digits, _ -.", "", "warn")
            return
        if not self.pw1.text():
            dialogs.message(self, _t("password_required"), "", "warn")
            return
        if self.pw1.text() != self.pw2.text():
            dialogs.message(self, _t("passwords_no_match"), "", "warn")
            return
        # If a BIP39 passphrase was entered, warn (red) BEFORE creating — it
        # can't be recovered and becomes the payment secret for transactions.
        if self.bip39.text():
            if not dialogs.confirm(self, _t("bip39_passphrase"),
                                   _t("create_passphrase_warning"), danger=True):
                return
        self._values = {
            "name": name,
            "account_title": self.title.text(),
            "phishing_hint": self.hint.text(),
            "password": self.pw1.text(),
            "bip39_passphrase": self.bip39.text(),
        }
        self.accept()

    def values(self):
        """Returns the collected dict, or None if cancelled."""
        return self._values


class ImportInputDialog(QDialog):
    """Collect fields to import a wallet from an existing recovery phrase."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("import_wallet"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self._values = None

        v = QVBoxLayout(self)
        intro = QLabel(_t("import_intro"))
        intro.setStyleSheet(ACCENT_LABEL)
        v.addWidget(intro)

        form = QFormLayout()
        self.name = QLineEdit(); self.name.setPlaceholderText(_t("ph_letters_digits"))
        self.title = QLineEdit(); self.title.setPlaceholderText(_t("optional"))
        self.hint = QLineEdit(); self.hint.setPlaceholderText(_t("ph_antiphishing"))
        self.pw1 = QLineEdit(); self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self.bip39 = QLineEdit(); self.bip39.setEchoMode(QLineEdit.EchoMode.Password)
        self.bip39.setPlaceholderText(_t("ph_bip39_import"))
        form.addRow(_t("wallet_name"), self.name)
        form.addRow(_t("account_title"), self.title)
        form.addRow(_t("phishing_hint"), self.hint)
        form.addRow(_t("new_password"), self.pw1)
        form.addRow(_t("confirm_password"), self.pw2)
        form.addRow(_t("bip39_passphrase"), self.bip39)
        v.addLayout(form)

        v.addWidget(QLabel(_t("recovery_phrase_label")))
        self.mnemonic = QPlainTextEdit()
        self.mnemonic.setPlaceholderText(_t("ph_word_list"))
        self.mnemonic.setFixedHeight(70)
        self.mnemonic.setStyleSheet(MONO_BLOCK)
        v.addWidget(self.mnemonic)

        note = QLabel(
            _t("import_pw_note")
        )
        note.setWordWrap(True)
        note.setStyleSheet(CAUTION_LABEL)
        v.addWidget(note)

        row = QHBoxLayout()
        cancel = QPushButton(_t("cancel"))
        imp = QPushButton(_t("import_wallet"))
        imp.setDefault(True)
        cancel.clicked.connect(self.reject)
        imp.clicked.connect(self._on_import)
        row.addStretch(1); row.addWidget(cancel); row.addWidget(imp)
        v.addLayout(row)

    def _on_import(self):
        import re
        name = self.name.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", name or ""):
            dialogs.message(self, "Name is required: 1-64 of letters, digits, _ -.", "", "warn")
            return
        if not self.pw1.text():
            dialogs.message(self, _t("password_required"), "", "warn")
            return
        if self.pw1.text() != self.pw2.text():
            dialogs.message(self, _t("passwords_no_match"), "", "warn")
            return
        words = self.mnemonic.toPlainText().split()
        if len(words) not in (12, 24):
            dialogs.message(
                self, _t("phrase_word_count_error", n=len(words)),
                "", "warn")
            return
        self._values = {
            "name": name,
            "account_title": self.title.text(),
            "phishing_hint": self.hint.text(),
            "password": self.pw1.text(),
            "bip39_passphrase": self.bip39.text(),
            "mnemonic": " ".join(words),
        }
        self.accept()

    def values(self):
        return self._values


class ExportRevealDialog(QDialog):
    """Display an exported recovery phrase + xpub with a sensitive-data warning."""
    def __init__(self, mnemonic: str, xpub: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("exported_phrase_title"))
        self.setModal(True)
        self.setMinimumWidth(640)
        self.resize(680, 380)

        v = QVBoxLayout(self)
        warn = QLabel(_t("export_warning"))
        warn.setWordWrap(True)
        warn.setStyleSheet(WARNING_LABEL)
        v.addWidget(warn)

        v.addWidget(QLabel(_t("mnemonic_label")))
        mbox = QPlainTextEdit(mnemonic)
        mbox.setReadOnly(True)
        mbox.setStyleSheet(MONO_BLOCK)
        mbox.setFixedHeight(80)
        v.addWidget(mbox)
        crow = QHBoxLayout(); crow.addStretch(1); crow.addWidget(_copy_button(mnemonic))
        v.addLayout(crow)

        if xpub:
            v.addWidget(QLabel(_t("xpub_label")))
            xbox = QLineEdit(xpub)
            xbox.setReadOnly(True)
            xbox.setCursorPosition(0)
            xbox.setStyleSheet(MONO_BLOCK)
            v.addWidget(xbox)

        row = QHBoxLayout()
        done = QPushButton(_t("done"))
        done.clicked.connect(self.accept)
        row.addStretch(1); row.addWidget(done)
        v.addLayout(row)


class MnemonicBackupDialog(QDialog):
    def __init__(self, mnemonic: str, address: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("backup_phrase_title"))
        self.setModal(True)
        self.setMinimumWidth(640)
        self.resize(680, 420)

        v = QVBoxLayout(self)

        warn = QLabel(
            _t("backup_warning")
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(WARNING_LABEL)
        v.addWidget(warn)

        v.addWidget(QLabel(_t("mnemonic_label")))
        mbox = QPlainTextEdit(mnemonic)
        mbox.setReadOnly(True)
        mbox.setStyleSheet(MONO_BLOCK)
        mbox.setFixedHeight(80)
        v.addWidget(mbox)
        crow = QHBoxLayout(); crow.addStretch(1); crow.addWidget(_copy_button(mnemonic))
        v.addLayout(crow)

        if address:
            v.addWidget(QLabel(_t("deposit_address")))
            abox = QLineEdit(address)
            abox.setReadOnly(True)
            abox.setMinimumWidth(600)
            abox.setCursorPosition(0)  # show the start, not the end
            abox.setStyleSheet(MONO_BLOCK)
            v.addWidget(abox)

        self.ack = QCheckBox(_t("ack_written"))
        self.ack.stateChanged.connect(self._toggle)
        v.addWidget(self.ack)

        row = QHBoxLayout()
        self.done_btn = QPushButton(_t("continue_btn"))
        self.done_btn.setEnabled(False)
        self.done_btn.clicked.connect(self.accept)
        row.addStretch(1); row.addWidget(self.done_btn)
        v.addLayout(row)

    def _toggle(self):
        self.done_btn.setEnabled(self.ack.isChecked())
