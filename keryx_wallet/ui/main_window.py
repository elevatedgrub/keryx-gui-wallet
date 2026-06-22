"""
main_window.py — Keryx Wallet desktop GUI (PyQt6).

A thin, safe front-end over the audited keryx-cli interactive wallet. The GUI
never handles private keys or constructs transactions; it sends verified
commands to keryx-cli and displays the results.

Screens:
  1. Connection — network + node address, connect (Enter submits).
  2. Wallet Options — a dropdown picks Open / Create / Import; the matching
     form appears. Create and Import auto-open the wallet on success.
  3. Dashboard — Balance (wallet : balance), Receive (address + centered QR)
     beside Send, history. Balance auto-refreshes.
"""

from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QStackedWidget, QListWidget, QTextEdit, QTextBrowser, QFormLayout,
    QMessageBox, QInputDialog, QStatusBar, QGroupBox, QPlainTextEdit,
    QComboBox, QScrollArea, QFileDialog,
)
from PyQt6.QtCore import Qt, QThreadPool, QTimer

from keryx_wallet.core.cli_driver import KeryxCliDriver, CliResult
from keryx_wallet.core.worker import CliRunnable
from keryx_wallet.core.qr import address_qr_pixmap
from keryx_wallet.ui.send_dialog import SendConfirmDialog
from keryx_wallet.ui.theme import ACCENT_LABEL, TOKENS
from keryx_wallet.ui import dialogs
from keryx_wallet.core import i18n
from keryx_wallet.core.i18n import t as _t

import os
import sys


def _dbg(msg: str) -> None:
    """Append a debug line to ~/keryx-debug.log when KERYX_DEBUG is set."""
    if not os.environ.get("KERYX_DEBUG"):
        return
    try:
        import time
        with open(os.path.expanduser("~/keryx-debug.log"), "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass


def _asset_path(name: str) -> str:
    """Locate a bundled asset both from source and from a PyInstaller bundle."""
    candidates = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates.append(os.path.join(base, "assets", name))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(here, "..", "..", "assets", name))
    candidates.append(os.path.join(os.getcwd(), "assets", name))
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""

DEFAULT_PUBLIC_NODE = ""
NETWORK_OPTIONS = ["mainnet", "testnet-10", "testnet-11"]


class MainWindow(QMainWindow):
    def __init__(self, cli_path: str = ""):
        super().__init__()
        self.setWindowTitle("Keryx Wallet")
        # Wide enough that each half (Receive / Send) fits its content; the
        # Receive half must hold the full ~62-char address.
        # Default large enough that the whole dashboard (through the history and
        # its pagination) is visible without scrolling. Cap to the available
        # screen size so it never opens larger than the display (small laptops).
        target_w, target_h = 1140, 900
        try:
            from PyQt6.QtWidgets import QApplication
            screen = QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                target_w = min(target_w, avail.width() - 40)
                target_h = min(target_h, avail.height() - 60)
        except Exception:
            pass
        self.resize(target_w, target_h)
        self.setMinimumSize(880, 600)

        self.driver = KeryxCliDriver(cli_path=cli_path, cli_subcommand="")
        self.pool = QThreadPool.globalInstance()

        self._connected = False
        self._wallet_open = False
        self._wallet_name = ""
        self._selected_account_index = 0  # active account's LIVE keryx select index
        self._selected_account_id = ""  # active account's stable hex id (survives reorder)
        self._wallet_id = ""            # open wallet's id (keys the persisted order)
        self._accounts = []             # parsed accounts from `list` (live keryx order)
        self._account_combo_ids = []    # display-ordered ids in the switcher (rebuild guard)
        self._populating_accounts = False  # guards combo programmatic updates
        self._current_address = ""
        self._krx_price = None          # cached KRX/USDT price
        self._last_list_output = ""     # cached `list` output for re-rendering
        self._tx_min_size = 0.0         # tx filter threshold (0 = show all)
        self._last_history_raw = ""     # cached raw history for re-filtering
        self._explorer_txs = None       # cached explorer txs (address-sourced)
        self._tx_page = 0               # current transactions page (0-based)

        self._balance_timer = QTimer(self)
        self._balance_timer.setInterval(10_000)
        self._balance_timer.timeout.connect(self._auto_refresh_balance)

        self.stack = QStackedWidget()

        # Header bar at the very top, above all screens: logo on the left, a
        # compact language switcher on the right.
        from PyQt6.QtGui import QPixmap
        central = QWidget()
        cv = QVBoxLayout(central)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        header_bar = QWidget()
        header_bar.setObjectName("headerBar")
        # Scope the background to ONLY the header bar by object name, so it does
        # not cascade into child widgets (a bare "QWidget{}" rule would also hit
        # the language button and clobber its green hover fill).
        header_bar.setStyleSheet(
            f"#headerBar {{ background-color:{TOKENS['bg']}; }}")
        hbar = QHBoxLayout(header_bar)
        hbar.setContentsMargins(8, 8, 8, 0)
        header = QLabel()
        header.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hp = _asset_path("keryx-header.png")
        if hp:
            pix = QPixmap(hp)
            if not pix.isNull():
                header.setPixmap(pix.scaledToHeight(
                    48, Qt.TransformationMode.SmoothTransformation))
        # Make the logo a clickable link to the Keryx website.
        header.setToolTip("https://keryx-labs.com/")
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        def _open_site(ev):
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl("https://keryx-labs.com/"))
        header.mousePressEvent = _open_site
        hbar.addWidget(header)
        hbar.addStretch(1)
        # Compact language switcher, top-right. Give it an explicit full button
        # style so it matches the other buttons' green hover exactly, regardless
        # of any header styling.
        self.lang_btn = QPushButton(
            " " + i18n.LANGUAGES_SHORT.get(i18n.get_language(), ""))
        # Custom green globe icon (matches theme) instead of the system emoji.
        _globe = _asset_path("globe-green.png")
        _globe_dark = _asset_path("globe-dark.png")
        if _globe:
            from PyQt6.QtGui import QIcon
            from PyQt6.QtCore import QSize
            self._globe_icon = QIcon(_globe)
            self._globe_icon_dark = QIcon(_globe_dark) if _globe_dark else self._globe_icon
            self.lang_btn.setIcon(self._globe_icon)
            self.lang_btn.setIconSize(QSize(20, 20))
            # Swap to the dark globe on hover (button bg turns green then) so the
            # icon stays visible; swap back on leave.
            _btn = self.lang_btn
            _orig_enter = _btn.enterEvent
            _orig_leave = _btn.leaveEvent
            def _on_enter(ev, b=_btn):
                b.setIcon(self._globe_icon_dark)
                _orig_enter(ev)
            def _on_leave(ev, b=_btn):
                b.setIcon(self._globe_icon)
                _orig_leave(ev)
            _btn.enterEvent = _on_enter
            _btn.leaveEvent = _on_leave
        self.lang_btn.setToolTip(_t("language"))
        self.lang_btn.setMaximumWidth(160)
        self.lang_btn.setStyleSheet(
            f"QPushButton {{ background-color:transparent; "
            f"border:1px solid {TOKENS['green_dim']}; border-radius:5px; "
            f"padding:7px 14px; color:{TOKENS['green']}; font-weight:600; }}"
            f"QPushButton:hover {{ background-color:{TOKENS['green_dim']}; "
            f"color:{TOKENS['bg']}; }}"
            f"QPushButton:pressed {{ background-color:{TOKENS['green']}; "
            f"color:{TOKENS['bg']}; }}")
        self.lang_btn.clicked.connect(self._change_language)
        self.lang_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hbar.addWidget(self.lang_btn, alignment=Qt.AlignmentFlag.AlignTop)
        cv.addWidget(header_bar)
        cv.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Persistent connection indicator in the bottom-left status bar.
        self._status_bar = QStatusBar()
        self._status_bar.setStyleSheet(
            f"QStatusBar {{ background-color:{TOKENS['bg']}; "
            f"color:{TOKENS['text_dim']}; border-top:1px solid {TOKENS['border']}; }}")
        self._conn_label = QLabel()
        self._status_bar.addWidget(self._conn_label)
        self.setStatusBar(self._status_bar)
        self._set_connection_indicator(False)

        self._build_connection_screen()
        self._build_wallet_screen()
        self._build_dashboard_screen()

        self.stack.setCurrentWidget(self.conn_screen)
        self._start_cli()
        self._offer_last_node()

    def _set_connection_indicator(self, connected: bool):
        """Update the bottom-left status indicator (Connected / Disconnected)."""
        self._connected = connected
        if not hasattr(self, "_conn_label"):
            return
        if connected:
            dot = TOKENS["green"]; txt = _t("connected")
        else:
            dot = TOKENS["red"]; txt = _t("disconnected")
        self._conn_label.setText(
            f"<span style='color:{dot};'>●</span> "
            f"<span style='color:{TOKENS['text_dim']};'>{txt}</span>")

    def _back_to_connection(self):
        """Return to the connection screen and mark as disconnected."""
        self._set_connection_indicator(False)
        self.stack.setCurrentWidget(self.conn_screen)

    def _offer_last_node(self):
        """If a previous node address is remembered, pre-fill it and connect
        automatically. The user can hit "Back to connection" to change it."""
        try:
            from keryx_wallet.core.config import get_last_node
            last = get_last_node()
        except Exception:
            last = ""
        if not last:
            return
        self.server_edit.setText(last)
        self._do_connect()

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _heading(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"font-size:18px; font-weight:700; color:{TOKENS['green']};")
        return lbl

    def status(self, msg: str):
        # Status bar is intentionally disabled — no transient messages are shown
        # in the bottom-left. Kept as a no-op so existing call sites are harmless.
        pass

    def _submit(self, fn, on_done, *args, **kwargs):
        task = CliRunnable(fn, *args, **kwargs)
        task.signals.finished.connect(on_done)
        task.signals.error.connect(lambda e: self._on_cli_error(e))
        self.pool.start(task)

    def _on_cli_error(self, msg: str):
        dialogs._error(self, "CLI error", msg)
        self.status(f"Error: {msg}")

    # ── CLI lifecycle ────────────────────────────────────────────────────────

    def _start_cli(self):
        path = self.driver.resolve_binary()
        if not path:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setWindowTitle("keryx-cli not found")
            box.setText(self.driver.binary_help())
            locate = box.addButton("Locate keryx-cli…", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Quit", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is locate:
                chosen, _ = QFileDialog.getOpenFileName(
                    self, "Select the keryx-cli binary", "",
                    "keryx-cli (keryx-cli);;All files (*)")
                if chosen:
                    self.driver._cli_path = chosen
                    path = self.driver.resolve_binary()
            if not path:
                self.status("keryx-cli not found — set PATH, KERYX_CLI, or --cli-path.")
                return
        try:
            self.driver.start()
            self.status(f"keryx-cli ready ({path}). Set a node and connect.")
        except Exception as e:  # noqa
            dialogs._error(self, "Failed to start keryx-cli", str(e))
            self.status("Failed to start keryx-cli")

    # ── Screen 1: Connection ─────────────────────────────────────────────────

    def _build_connection_screen(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(16, 0, 16, 16)
        v.addWidget(self._heading(_t("connect_to_node")))

        form = QFormLayout()
        self.network_combo = QComboBox()
        self.network_combo.addItems(NETWORK_OPTIONS)
        form.addRow(_t("network_label"), self.network_combo)

        self.server_edit = QLineEdit()
        self.server_edit.setPlaceholderText(_t("address_placeholder"))
        if DEFAULT_PUBLIC_NODE:
            self.server_edit.setText(DEFAULT_PUBLIC_NODE)
        self.server_edit.returnPressed.connect(self._do_connect)
        form.addRow(_t("address"), self.server_edit)
        v.addLayout(form)

        row = QHBoxLayout()
        self.connect_btn = QPushButton(_t("connect"))
        self.connect_btn.clicked.connect(self._do_connect)
        row.addStretch(1); row.addWidget(self.connect_btn)
        v.addLayout(row)

        v.addStretch(1)

        self.conn_screen = w
        self.stack.addWidget(w)

    def _do_connect(self):
        address = self.server_edit.text().strip()
        net = self.network_combo.currentText()
        if not address:
            dialogs._warn(self, "Node address",
                                "Enter your node's wRPC address to connect.")
            return
        self.connect_btn.setEnabled(False)
        self.status(f"Selecting {net}…")

        def after_connect(res: CliResult):
            self.connect_btn.setEnabled(True)
            low = (res.output or "").lower() + (res.error or "").lower()
            if res.ok and "error" not in low and "no network" not in low:
                self._set_connection_indicator(True)
                # Remember this node for next launch.
                try:
                    from keryx_wallet.core.config import set_last_node
                    set_last_node(address)
                except Exception:
                    pass
                self._populate_wallet_list()
                self.stack.setCurrentWidget(self.wallet_screen)
            else:
                self._set_connection_indicator(False)
                dialogs.message(self, _t("connection_failed"), "", "warn")

        def after_network(res: CliResult):
            if not res.ok:
                self.connect_btn.setEnabled(True)
                dialogs._warn(self, "Network", res.error or "Network select failed.")
                return
            self.status(f"Connecting to {address}…")
            self._submit(self.driver.connect, after_connect, address)

        self._submit(self.driver.select_network, after_network, net)

    # ── Screen 2: Wallet Options (dropdown -> form) ──────────────────────────

    def _build_wallet_screen(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(16, 0, 16, 12)
        v.setSpacing(8)
        v.addWidget(self._heading(_t("wallet_options")))

        picker = QHBoxLayout()
        picker.addStretch(1)
        picker.addWidget(QLabel(_t("choose")))
        self.wallet_choice = QComboBox()
        self.wallet_choice.addItems([_t("open"), _t("create"), _t("import")])
        self.wallet_choice.currentTextChanged.connect(self._on_wallet_choice)
        picker.addWidget(self.wallet_choice)
        picker.addStretch(1)
        v.addLayout(picker)

        self.wallet_forms = QStackedWidget()

        # Open — dropdown listing existing wallets from ~/.keryx-labs
        openw = QWidget(); ov = QFormLayout(openw)
        ov.setContentsMargins(0, 0, 0, 0)
        self.open_combo = QComboBox()
        # Non-editable so a click ANYWHERE on the widget opens the dropdown
        # (an editable combo only opens via the arrow). All wallets in
        # ~/.keryx-labs are auto-listed, so typing a name isn't needed.
        self.open_combo.setEditable(False)
        ov.addRow(_t("wallet_label"), self.open_combo)
        open_btn = QPushButton(_t("open")); open_btn.clicked.connect(self._do_open_wallet)
        ov.addRow("", open_btn)
        self.wallet_forms.addWidget(openw)

        # Create
        createw = QWidget(); cv = QFormLayout(createw)
        cv.setContentsMargins(0, 0, 0, 0)
        self.create_name = QLineEdit()
        self.create_name.setPlaceholderText(_t("wallet_name_placeholder"))
        self.create_name.returnPressed.connect(self._do_create_wallet)
        cv.addRow(_t("name"), self.create_name)
        create_btn = QPushButton(_t("create")); create_btn.clicked.connect(self._do_create_wallet)
        cv.addRow("", create_btn)
        self.wallet_forms.addWidget(createw)

        # Import
        importw = QWidget(); iv = QFormLayout(importw)
        iv.setContentsMargins(0, 0, 0, 0)
        self.import_name = QLineEdit()
        self.import_name.setPlaceholderText(_t("wallet_name_placeholder"))
        self.import_name.returnPressed.connect(self._do_import_wallet)
        iv.addRow(_t("name"), self.import_name)
        import_btn = QPushButton(_t("import_btn")); import_btn.clicked.connect(self._do_import_wallet)
        iv.addRow("", import_btn)
        self.wallet_forms.addWidget(importw)

        v.addWidget(self.wallet_forms)

        back = QPushButton(_t("back_to_connection"))
        back.clicked.connect(self._back_to_connection)
        v.addWidget(back)
        v.addStretch(1)

        self.wallet_choice.setCurrentIndex(0)
        self.wallet_forms.setCurrentIndex(0)

        self.wallet_screen = w
        self.stack.addWidget(w)

    def _on_wallet_choice(self, choice: str):
        # Use the index (language-independent) since the labels are translated.
        idx = self.wallet_choice.currentIndex()
        self.wallet_forms.setCurrentIndex(idx)
        if idx == 0:  # Open
            self._populate_wallet_list()

    def _wallet_exists(self, name: str) -> bool:
        """True if a wallet file with this name already exists in ~/.keryx-labs."""
        import os
        name = (name or "").strip()
        if not name:
            return False
        path = os.path.expanduser(f"~/.keryx-labs/{name}.wallet")
        return os.path.exists(path)

    def _populate_wallet_list(self):
        """Fill the Open dropdown with wallet names found in ~/.keryx-labs."""
        import os
        import glob
        prev = self.open_combo.currentText().strip()
        self.open_combo.clear()
        wdir = os.path.expanduser("~/.keryx-labs")
        names = []
        try:
            for path in sorted(glob.glob(os.path.join(wdir, "*.wallet"))):
                names.append(os.path.splitext(os.path.basename(path))[0])
        except Exception:
            pass
        self.open_combo.addItems(names)
        if prev:
            self.open_combo.setCurrentText(prev)
        elif names:
            self.open_combo.setCurrentIndex(0)

    def _enter_dashboard(self, wallet_name: str):
        self._wallet_open = True
        self._wallet_name = wallet_name
        self._selected_account_index = 0
        self._selected_account_id = ""   # reconciled to the main account on first list
        self._wallet_id = ""
        # Fresh history state every open — otherwise a load left in flight when a
        # previous wallet was closed leaves _history_loading stuck True (its done
        # bails on the stale-address guard without clearing it), which would block
        # _load_history here ("history not loading after switch + reopen").
        self._history_loading = False
        self._explorer_txs = None
        self._last_history_raw = ""
        self._last_history_html = None   # else the render dedup-skips and the
        self._tx_page = 0                # view stays stuck on "Loading…"
        self.stack.setCurrentWidget(self.dash_screen)
        self.history_view.setHtml(
            f"<div style='color:{TOKENS['text_dim']};'>{_t('loading_transactions')}</div>")
        # keryx-cli will NOT spend (send/estimate) until an account is actively
        # selected. With 2+ accounts `wallet open` selects NONE, so estimate/send
        # fail with "please select an account". We must select an account on open;
        # it should be the FIRST in the user's display order (which respects a
        # manual reorder / the pinned main account), not keryx's list order.
        def after_select(_res: CliResult):
            _dbg(f"after_select: sel_id={self._selected_account_id} "
                 f"live_idx={self._selected_account_index} cur_addr={self._current_address!r}")
            self._refresh_accounts()
            self._show_address()   # resolves address, then loads explorer history
            self._balance_timer.start()
        def after_list(res: CliResult):
            _dbg(f"after_list: ok={getattr(res,'ok',None)} wid={self._wallet_id!r}")
            live_idx = 0
            if res.ok and res.output:
                self._last_list_output = res.output
                self._wallet_id = self._parse_wallet_id(res.output) or self._wallet_id
                accts = self._parse_accounts(res.output)
                if accts:
                    self._accounts = accts
                    if len(accts) == 1 and self._wallet_id:
                        from keryx_wallet.core import config
                        config.set_main_account(self._wallet_id, accts[0]["id"])
                    first = self._display_order(accts)[0]
                    self._selected_account_id = first["id"]
                    live_idx = next((a["index"] for a in accts
                                     if a["id"] == first["id"]), 0)
                    self._selected_account_index = live_idx
            self._submit(self.driver.select_account, after_select, live_idx)
        def after_mute(_res: CliResult):
            # `list` first so we know the display order, THEN select its first
            # account in the CLI so the active account matches what's shown.
            self._submit(self.driver.run, after_list, "list")
        # Mute async notifications FIRST (they desync the REPL).
        self._submit(self.driver.set_muted, after_mute, True)

    def _do_open_wallet(self):
        name = self.open_combo.currentText().strip()
        if not name:
            dialogs._warn(self, _t("name_required"), _t("select_enter_name"))
            return
        pw, ok = dialogs.get_password(
            self, "", _t("enter_password"))
        if not ok:
            return

        def done(res: CliResult):
            if res.ok:
                self.status(f'Wallet "{name}" opened.')
                self._enter_dashboard(name)
            else:
                dialogs._warn(self, "Open failed",
                                    res.error or "Could not open wallet.")
                self.status(f"Open failed: {res.error or 'unknown'}")

        self.status(f'Opening "{name}"…')
        self._submit(self.driver.open_wallet, done, name, pw)

    def _do_create_wallet(self):
        from keryx_wallet.ui.create_dialog import CreateInputDialog, MnemonicBackupDialog

        # Check the name typed on the Wallet Options screen BEFORE opening the
        # input dialog — stop immediately if it already exists.
        typed = self.create_name.text().strip()
        if typed and self._wallet_exists(typed):
            dialogs._warn(self, _t("wallet_name_exists"), "")
            return

        dlg = CreateInputDialog(parent=self)
        if typed:
            dlg.name.setText(typed)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        if not vals:
            return
        # Also catch a name entered/changed inside the dialog.
        if self._wallet_exists(vals["name"]):
            dialogs._warn(self, _t("wallet_name_exists"), "")
            return

        def done(res: CliResult):
            if res.ok:
                parsed = KeryxCliDriver.parse_create_result(res.output)
                MnemonicBackupDialog(parsed.get("mnemonic", ""),
                                     parsed.get("address", ""), parent=self).exec()
                self.status(f'Wallet "{vals["name"]}" created.')
                self._auto_open_after(vals["name"], vals["password"])
            else:
                dialogs.message(self, _t("create_failed"), "", "warn")
                self.status(f"Create failed: {res.error or 'unknown'}")

        self.status(f'Creating "{vals["name"]}"…')
        self._submit(
            self.driver.create_wallet, done,
            vals["name"], vals["password"],
            account_title=vals["account_title"],
            phishing_hint=vals["phishing_hint"],
            bip39_passphrase=vals["bip39_passphrase"],
        )

    def _do_import_wallet(self):
        from keryx_wallet.ui.create_dialog import ImportInputDialog

        typed = self.import_name.text().strip()
        if typed and self._wallet_exists(typed):
            dialogs._warn(self, _t("wallet_name_exists"), "")
            return

        dlg = ImportInputDialog(parent=self)
        if typed:
            dlg.name.setText(typed)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        vals = dlg.values()
        if not vals:
            return
        if self._wallet_exists(vals["name"]):
            dialogs._warn(self, _t("wallet_name_exists"), "")
            return

        def done(res: CliResult):
            if res.ok:
                self.status(f'Wallet "{vals["name"]}" imported.')
                self._auto_open_after(vals["name"], vals["password"])
            else:
                dialogs.message(
                    self, _t("import_failed"), "", "info")
                self.status(f"Import failed: {res.error or 'unknown'}")

        self.status(f'Importing "{vals["name"]}"…')
        self._submit(
            self.driver.import_wallet, done,
            vals["name"], vals["password"], vals["mnemonic"],
            account_title=vals["account_title"],
            phishing_hint=vals["phishing_hint"],
            bip39_passphrase=vals["bip39_passphrase"],
        )

    def _auto_open_after(self, name: str, password: str):
        def done(res: CliResult):
            if res.ok:
                self.status(f'Wallet "{name}" opened.')
                self._enter_dashboard(name)
            else:
                self.wallet_choice.setCurrentIndex(0)
                self._populate_wallet_list()
                self.open_combo.setCurrentText(name)
                dialogs._info(
                    self, "Open your wallet",
                    f'Wallet "{name}" is ready. Enter its password to open.')
        self.status(f'Opening "{name}"…')
        self._submit(self.driver.open_wallet, done, name, password)

    # ── Screen 3: Dashboard ──────────────────────────────────────────────────

    def _build_dashboard_screen(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(16, 0, 16, 12)

        top = QHBoxLayout()
        top.addStretch(1)
        switch_btn = QPushButton(_t("switch_wallet"))
        switch_btn.clicked.connect(self._switch_wallet)
        top.addWidget(switch_btn)
        new_acct_btn = QPushButton(_t("new_account"))
        new_acct_btn.clicked.connect(self._do_new_account)
        top.addWidget(new_acct_btn)
        consolidate_btn = QPushButton(_t("consolidate"))
        consolidate_btn.setToolTip(_t("consolidate_tip"))
        consolidate_btn.clicked.connect(self._do_consolidate)
        top.addWidget(consolidate_btn)
        export_btn = QPushButton(_t("export_phrase"))
        export_btn.clicked.connect(self._do_export)
        top.addWidget(export_btn)
        v.addLayout(top)

        # Account switcher — only shown when the wallet has 2+ accounts. keryx-cli
        # needs an account actively selected to spend; changing this re-selects
        # the account and refreshes balance/address/history for it.
        self.account_row = QWidget()
        ar = QHBoxLayout(self.account_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.addWidget(QLabel(_t("account") + ":"))
        # Custom dropdown whose popup list is drag-reorderable (a QComboBox popup
        # can't be — it intercepts the drag). See account_selector.py.
        from keryx_wallet.ui.account_selector import AccountSelector
        self.account_combo = AccountSelector()
        self.account_combo.setToolTip(_t("reorder_hint"))
        self.account_combo.activated.connect(self._on_account_activated)
        self.account_combo.reordered.connect(self._on_account_reordered)
        ar.addWidget(self.account_combo, 1)
        self.rename_btn = QPushButton(_t("rename"))
        self.rename_btn.clicked.connect(self._do_rename_account)
        ar.addWidget(self.rename_btn)
        self.account_row.setVisible(False)
        v.addWidget(self.account_row)

        # Balance — "wallet : balance", large modern font
        bal_box = QGroupBox(_t("balance"))
        bb = QVBoxLayout(bal_box)
        self.balance_label = QLabel("—")
        self.balance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.balance_label.setWordWrap(True)
        self.balance_label.setStyleSheet(
            "font-family:'Roboto','Noto Sans','DejaVu Sans',sans-serif; "
            f"font-size:24px; font-weight:600; color:{TOKENS['text']};")
        bb.addWidget(self.balance_label)
        v.addWidget(bal_box)

        # Receive + Send side by side
        rs = QHBoxLayout()

        recv_box = QGroupBox(_t("receive"))
        rb = QVBoxLayout(recv_box)
        rb.setContentsMargins(2, 2, 2, 2)
        # Wrapping read-only display so the FULL address is always visible at a
        # fixed, readable font — it wraps onto a second line when the window is
        # too narrow for one line, instead of clipping or shrinking the font.
        from PyQt6.QtWidgets import QSizePolicy
        self.addr_label = QTextEdit(_t("loading_address"))
        self.addr_label.setReadOnly(True)
        self.addr_label.setFrameStyle(0)
        self.addr_label.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.addr_label.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.addr_label.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        # Wrap at any character (an address has no spaces to break on).
        from PyQt6.QtGui import QTextOption
        self.addr_label.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.addr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addr_label.setStyleSheet(
            f"QTextEdit {{ color:{TOKENS['green']}; font-weight:600; "
            "font-size:13px; border:none; background:transparent; padding:0px; }")
        self.addr_label.setFixedHeight(48)  # room for up to ~2 lines
        self.addr_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Fixed)
        rb.addWidget(self.addr_label)
        # Copy button — easier and more reliable than double-clicking a wrapped
        # address (a double-click only selects up to the ':' word boundary).
        copy_btn = QPushButton(_t("copy_address"))
        copy_btn.clicked.connect(self._copy_address)
        rb.addWidget(copy_btn)
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setContentsMargins(0, 25, 0, 0)  # 25px lower
        rb.addWidget(self.qr_label)
        rb.addStretch(1)
        rs.addWidget(recv_box, 1)

        send_box = QGroupBox(_t("send"))
        sb = QFormLayout(send_box)
        self.send_addr = QLineEdit(); self.send_addr.setPlaceholderText(_t("destination_placeholder"))
        # After pasting a long address the view sits at the end; reset it to show
        # the BEGINNING when the field loses focus (not while typing/pasting).
        _orig_focus_out = self.send_addr.focusOutEvent
        def _focus_out(event, w=self.send_addr, orig=_orig_focus_out):
            orig(event)
            w.setCursorPosition(0)
        self.send_addr.focusOutEvent = _focus_out
        self.send_amount = QLineEdit(); self.send_amount.setPlaceholderText(_t("ph_amount"))
        self.send_fee = QLineEdit(); self.send_fee.setPlaceholderText(_t("ph_priority_fee"))
        # Destination row: address field + an address-book button to its right.
        to_row = QWidget()
        to_h = QHBoxLayout(to_row)
        to_h.setContentsMargins(0, 0, 0, 0)
        to_h.setSpacing(6)
        to_h.addWidget(self.send_addr, 1)
        self.addrbook_btn = QPushButton()
        self.addrbook_btn.setToolTip(_t("address_book"))
        self.addrbook_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.addrbook_btn.setFixedWidth(40)
        _abk = _asset_path("addressbook-green.png")
        _abk_dark = _asset_path("addressbook-dark.png")
        if _abk:
            from PyQt6.QtGui import QIcon
            from PyQt6.QtCore import QSize
            self._abk_icon = QIcon(_abk)
            self._abk_icon_dark = QIcon(_abk_dark) if _abk_dark else self._abk_icon
            self.addrbook_btn.setIcon(self._abk_icon)
            self.addrbook_btn.setIconSize(QSize(20, 20))
            _ab = self.addrbook_btn
            _oe, _ol = _ab.enterEvent, _ab.leaveEvent
            def _ab_enter(ev, b=_ab):
                b.setIcon(self._abk_icon_dark); _oe(ev)
            def _ab_leave(ev, b=_ab):
                b.setIcon(self._abk_icon); _ol(ev)
            _ab.enterEvent = _ab_enter
            _ab.leaveEvent = _ab_leave
        self.addrbook_btn.clicked.connect(self._open_address_book)
        to_h.addWidget(self.addrbook_btn)
        sb.addRow(_t("to"), to_row)
        sb.addRow(_t("amount"), self.send_amount)
        sb.addRow(_t("fee"), self.send_fee)
        send_btn = QPushButton(_t("send_btn"))
        send_btn.clicked.connect(self._do_send)
        sb.addRow("", send_btn)
        rs.addWidget(send_box, 1)

        v.addLayout(rs)

        tx_box = QGroupBox(_t("transactions"))
        hb = QVBoxLayout(tx_box)
        # Optional size filter — hide txs whose absolute amount is below this.
        # Empty/0 shows all (default).
        filt = QHBoxLayout()
        filt.addWidget(QLabel(_t("hide_txs_under")))
        self.tx_filter_edit = QLineEdit()
        self.tx_filter_edit.setPlaceholderText(_t("show_all"))
        self.tx_filter_edit.setMaximumWidth(120)
        self.tx_filter_edit.editingFinished.connect(self._apply_tx_filter)
        # Also filter live as the user types, not only on losing focus.
        self.tx_filter_edit.textChanged.connect(lambda _txt: self._apply_tx_filter())
        filt.addWidget(self.tx_filter_edit)
        filt.addWidget(QLabel("KRX"))
        filt.addStretch(1)
        hb.addLayout(filt)
        # QTextBrowser natively handles clickable links (setOpenLinks /
        # anchorClicked). We disable in-widget navigation and open links in the
        # system browser instead.
        self.history_view = QTextBrowser()
        # Show about 4 transaction rows by default (each row ~46px incl. divider,
        # plus the count header). Kept modest so the pagination row below stays
        # visible without scrolling. Expands beyond this if space allows.
        self.history_view.setMinimumHeight(216)
        self.history_view.setReadOnly(True)
        self.history_view.setOpenExternalLinks(True)
        hb.addWidget(self.history_view)
        # Pagination controls (hidden unless there's more than one page).
        pag = QHBoxLayout()
        pag.addStretch(1)
        self.tx_first_btn = QPushButton(_t("first_page"))
        self.tx_first_btn.clicked.connect(self._tx_page_first)
        self.tx_prev_btn = QPushButton(_t("prev"))
        self.tx_prev_btn.clicked.connect(self._tx_page_prev)
        # Editable "current / total" page indicator — type a number + Enter to
        # jump straight to that page.
        self.tx_page_edit = QLineEdit()
        self.tx_page_edit.setMaximumWidth(56)
        self.tx_page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tx_page_edit.returnPressed.connect(self._tx_page_goto)
        self.tx_page_total = QLabel("/ 1")
        self.tx_next_btn = QPushButton(_t("next"))
        self.tx_next_btn.clicked.connect(self._tx_page_next)
        self.tx_last_btn = QPushButton(_t("last_page"))
        self.tx_last_btn.clicked.connect(self._tx_page_last)
        for wdg in (self.tx_first_btn, self.tx_prev_btn, self.tx_page_edit,
                    self.tx_page_total, self.tx_next_btn, self.tx_last_btn):
            wdg.setVisible(False)
        pag.addWidget(self.tx_first_btn)
        pag.addWidget(self.tx_prev_btn)
        pag.addWidget(self.tx_page_edit)
        pag.addWidget(self.tx_page_total)
        pag.addWidget(self.tx_next_btn)
        pag.addWidget(self.tx_last_btn)
        pag.addStretch(1)
        hb.addLayout(pag)
        v.addWidget(tx_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(w)
        self.dash_screen = scroll
        self.stack.addWidget(scroll)

    @staticmethod
    def _parse_accounts(output: str):
        """
        Parse `list` output into ordered account dicts. The position in the list
        IS the keryx-cli select index (verified). Format per account:
            • [<hexid>]: <bal> KRX   <n> UTXOs         (account 0 — no name)
            • <name> [<hexid>]: <bal> KRX   <n> UTXOs  (named accounts)
              keryx:<address>                          (on the next line)
        """
        accounts = []
        lines = (output or "").splitlines()
        for i, line in enumerate(lines):
            s = line.strip().lstrip("•").strip()
            m = re.match(r"^(.*?)\[([0-9a-f]+)\]:\s*(.+?)\s*KRX", s)
            if not m:
                continue
            name = m.group(1).strip()
            acct_id = m.group(2)
            bal = m.group(3).strip()
            addr = ""
            for j in range(i + 1, min(i + 3, len(lines))):
                am = re.search(r"(ker[xy][a-z]*:[0-9a-z]+)", lines[j], re.IGNORECASE)
                if am:
                    addr = am.group(1)
                    break
            accounts.append({
                "index": len(accounts),
                "id": acct_id,
                "name": name,
                "balance": bal,
                "address": addr,
            })
        return accounts

    @staticmethod
    def _parse_wallet_id(output: str) -> str:
        # The wallet id is a bare "• <hex>" line (>=12 hex, no brackets/colon);
        # account ids appear as "[<hex>]:". Used to key the persisted order.
        for line in (output or "").splitlines():
            m = re.match(r"^\s*•\s*([0-9a-f]{12,})\s*$", line.strip())
            if m:
                return m.group(1)
        return ""

    def _display_order(self, accounts):
        """
        Return accounts in a STABLE display order. keryx-cli reorders its own
        list when an account is renamed, so we persist the order per wallet
        (frozen on first sight; new accounts appended) and keep using it. Each
        account keeps its live keryx `index` for selection.
        """
        from keryx_wallet.core import config
        by_id = {a["id"]: a for a in accounts}
        stored = config.get_account_order(self._wallet_id) if self._wallet_id else []
        ordered = [by_id[i] for i in stored if i in by_id]
        seen = {a["id"] for a in ordered}
        ordered.extend(a for a in accounts if a["id"] not in seen)  # new → end
        # Pin the known main account (derivation index 0) to the very front, even
        # if it was renamed (which makes keryx re-append it) — UNLESS the user has
        # manually reordered, in which case their order is respected as-is.
        locked = config.get_order_locked(self._wallet_id) if self._wallet_id else False
        main_id = config.get_main_account(self._wallet_id) if self._wallet_id else ""
        if main_id and main_id in by_id and not locked:
            ordered = [by_id[main_id]] + [a for a in ordered if a["id"] != main_id]
        new_ids = [a["id"] for a in ordered]
        if self._wallet_id and new_ids != stored:
            config.set_account_order(self._wallet_id, new_ids)
        return ordered

    def _account_label(self, acct: dict) -> str:
        # An unnamed account shows just its ID (no placeholder name).
        name = acct.get("name")
        bal = acct.get("balance", "")
        if name:
            return f"{name} [{acct['id']}] — {bal} KRX"
        return f"[{acct['id']}] — {bal} KRX"

    def _populate_account_combo(self, display):
        if not hasattr(self, "account_combo"):
            return
        items = [(a["id"], self._account_label(a)) for a in display]
        # set_accounts does not emit signals, so no re-entrancy guard needed.
        self.account_combo.set_accounts(items, self._selected_account_id)
        self._account_combo_ids = [a["id"] for a in display]
        # The switcher is only useful with more than one account.
        self.account_row.setVisible(len(display) > 1)

    def _on_account_activated(self, sel_id: str):
        if not sel_id or sel_id == self._selected_account_id:
            return
        # Map the chosen account id to its LIVE keryx select index.
        live = next((a["index"] for a in self._accounts if a["id"] == sel_id), None)
        if live is None:
            return
        self._selected_account_id = sel_id
        self._selected_account_index = live

        def done(_res: CliResult):
            # Re-render balance for the now-active account and refresh its
            # address (which in turn reloads explorer history).
            if self._last_list_output:
                self._update_balance_display(self._last_list_output)
            self._show_address()
        self.status(_t("account") + f" → {sel_id}")
        self._submit(self.driver.select_account, done, live)

    def _on_account_reordered(self, ids: list):
        """User drag-reordered the dropdown list. Persist + lock the new order."""
        ids = [i for i in ids if i]
        if not ids or not self._wallet_id:
            return
        from keryx_wallet.core import config
        config.set_account_order(self._wallet_id, ids)
        config.set_order_locked(self._wallet_id, True)
        self._account_combo_ids = ids

    def _do_new_account(self):
        if not self._wallet_open:
            return
        # Show the recovery caveat FIRST (red) — additional bip32 accounts don't
        # auto-restore from the seed; recovery is manual recreation in order.
        if not dialogs.confirm(self, _t("new_account"),
                               _t("account_recovery_warning"), danger=True):
            return
        name, ok = dialogs.get_text(self, _t("new_account"),
                                    _t("account_name_prompt"))
        if not ok:   # cancelled; an empty name is allowed (unnamed account)
            return
        pw, ok = dialogs.get_password(self, "", _t("enter_password"))
        if not ok:
            return

        def done(res: CliResult):
            if res.ok:
                parsed = KeryxCliDriver.parse_created_account(res.output)
                # The CLI auto-selects the new account; track it by id so the
                # refresh reconciles to it (and it appears at the end of the
                # stable display order).
                if parsed and parsed.get("id"):
                    self._selected_account_id = parsed["id"]
                self.status(_t("account_created"))
                self._refresh_accounts()   # repopulate switcher (now includes it)
                self._show_address()       # CLI auto-selected it → its address
                detail = f"{parsed['name']} [{parsed['id']}]" if parsed else ""
                dialogs.message(self, _t("account_created"), detail, "info")
            else:
                dialogs._warn(self, _t("create_account_failed"),
                              res.error or _t("create_account_failed"))
                self.status(_t("create_account_failed"))

        self.status(_t("new_account") + "…")
        self._submit(self.driver.create_account, done, name, pw)

    def _do_rename_account(self):
        idx = self._selected_account_index
        if idx < 0 or idx >= len(self._accounts):
            return
        cur = self._accounts[idx]
        cur_name = cur.get("name") or ""
        new_name, ok = dialogs.get_text(
            self, _t("rename"), _t("rename_prompt"), cur_name)
        # An empty name is allowed — it clears the name. Only bail on cancel or
        # when nothing actually changed.
        if not ok or new_name == cur_name:
            return
        pw, ok = dialogs.get_password(self, "", _t("enter_password"))
        if not ok:
            return

        def done(res: CliResult):
            if res.ok:
                self.status(_t("account_renamed"))
                self._refresh_accounts()   # repopulates the switcher with the new name
                old_label = cur_name or f"[{cur['id']}]"
                dialogs.message(self, _t("account_renamed"),
                                f"{old_label} → {new_name}", "info")
            else:
                dialogs._warn(self, _t("rename_failed"),
                              res.error or _t("rename_failed"))
                self.status(_t("rename_failed"))

        self.status(_t("rename") + "…")
        self._submit(self.driver.rename_account, done, idx, new_name, pw)

    def _update_balance_display(self, output: str):
        # Parse all accounts and (re)populate the switcher.
        self._wallet_id = self._parse_wallet_id(output) or self._wallet_id
        accounts = self._parse_accounts(output)
        bal = ""
        if accounts:
            self._accounts = accounts
            # A wallet seen with exactly one account is showing its main account
            # (derivation index 0) — record it so it can be pinned first later.
            if len(accounts) == 1 and self._wallet_id:
                from keryx_wallet.core import config
                config.set_main_account(self._wallet_id, accounts[0]["id"])
            display = self._display_order(accounts)
            ids = [a["id"] for a in accounts]
            # Reconcile the active account BY ID — keryx reorders its list when an
            # account is renamed, so the live index alone isn't stable. When the
            # selection is unknown, default to the FIRST account in the user's
            # display order (not keryx's list order).
            if self._selected_account_id not in ids:
                self._selected_account_id = display[0]["id"]
            self._selected_account_index = ids.index(self._selected_account_id)
            self._populate_account_combo(display)
            bal = accounts[self._selected_account_index]["balance"]
        else:
            m = re.search(r"\[[0-9a-f]+\]:\s*(.+?)\s*KRX", output or "", re.IGNORECASE)
            if m:
                bal = m.group(1).strip()
        if not bal or bal.upper() == "N/A":
            self.balance_label.setText(f"{bal or '—'} KRX")
            return
        # Cache the numeric balance for the send-time insufficient-funds check.
        try:
            self._balance_krx = float(bal.replace(",", ""))
        except Exception:
            self._balance_krx = None
        # Show "<bal> KRX  ≈ $<usd>" when a price is available; else just KRX.
        krx_text = f"{bal} KRX"
        usd = ""
        try:
            price = self._krx_price  # cached by the price fetch
            if price:
                amount = float(bal.replace(",", ""))
                usd = f"  ≈ ${amount * price:,.8f}"
        except Exception:
            usd = ""
        self.balance_label.setText(krx_text + usd)

    def _refresh_price(self):
        """Fetch KRX/USDT price in the background and refresh the balance text."""
        from keryx_wallet.core.price import get_krx_usdt_price

        def work():
            return get_krx_usdt_price()

        def done(result):
            # result is the price float or None
            if isinstance(result, (int, float)) and result > 0:
                self._krx_price = float(result)
                # Re-render the balance with the latest cached list output.
                if self._last_list_output:
                    self._update_balance_display(self._last_list_output)
        # Use a tiny runnable for the network call.
        from keryx_wallet.core.worker import CliRunnable
        task = CliRunnable(work)
        task.signals.finished.connect(done)
        task.signals.error.connect(lambda e: None)  # price is best-effort
        self.pool.start(task)

    def _refresh_accounts(self):
        def done(res: CliResult):
            if res.ok:
                self._last_list_output = res.output or ""
                self._update_balance_display(res.output or "")
            else:
                pass
        self._submit(self.driver.run, done, "list")
        self._refresh_price()

    def _auto_refresh_balance(self):
        if not self._wallet_open:
            return
        if self.stack.currentWidget() is not self.dash_screen:
            return
        def done(res: CliResult):
            if res.ok and res.output:
                self._last_list_output = res.output
                self._update_balance_display(res.output)
        self._submit(self.driver.run, done, "list")
        self._refresh_price()
        self._load_history()

    def _fit_address_font(self, w):
        # No longer used — the address now wraps in a QTextEdit instead of
        # shrinking to fit. Kept as a harmless no-op for any stray callers.
        pass

    def _change_language(self):
        """Let the user pick a new language, then restart the app to apply it."""
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton, QLabel)
        from keryx_wallet.ui.theme import TOKENS, MONO
        from keryx_wallet.core import config

        codes = list(i18n.LANGUAGES.keys())
        current = i18n.get_language()
        cur_idx = codes.index(current) if current in codes else 0

        dlg = QDialog(self)
        dlg.setWindowTitle("")
        dlg.setModal(True)
        dlg.setMinimumWidth(340)
        dlg.setStyleSheet(
            f"QDialog {{ background:{TOKENS['bg']}; }}"
            f"QLabel {{ color:{TOKENS['green']}; font-family:{MONO}; "
            f"font-size:15px; font-weight:700; }}"
            f"QListWidget {{ background:{TOKENS['surface_2']}; "
            f"color:{TOKENS['text']}; font-family:{MONO}; border:1px solid "
            f"{TOKENS['border']}; }}"
            f"QListWidget::item:selected {{ background:{TOKENS['green_dim']}; "
            f"color:{TOKENS['bg']}; }}"
            f"QPushButton {{ background:{TOKENS['surface_2']}; "
            f"color:{TOKENS['green']}; border:1px solid {TOKENS['green_dim']}; "
            f"border-radius:6px; padding:7px 18px; font-family:{MONO}; }}")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(_t("choose_language")))
        lst = QListWidget()
        for c in codes:
            lst.addItem(i18n.LANGUAGES[c])
        lst.setCurrentRow(cur_idx)
        v.addWidget(lst)
        row = QHBoxLayout(); row.addStretch(1)
        cancel = QPushButton(_t("cancel")); cancel.clicked.connect(dlg.reject)
        okb = QPushButton(_t("ok")); okb.clicked.connect(dlg.accept)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        row.addWidget(cancel); row.addWidget(okb)
        v.addLayout(row)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        chosen = codes[lst.currentRow()]
        if chosen == current:
            return
        config.set_language(chosen)
        i18n.set_language(chosen)
        # Auto-restart so the whole UI rebuilds in the new language.
        self._restart_app()

    def _restart_app(self):
        """Relaunch the application in place."""
        import os
        import sys
        try:
            self.close()
        except Exception:
            pass
        # Re-exec: frozen binary re-runs itself; source re-runs python + argv.
        if getattr(sys, "frozen", False):
            os.execv(sys.executable, [sys.executable] + sys.argv[1:])
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)

    def _copy_address(self):
        """Copy the current receive address to the clipboard."""
        addr = (self._current_address or "").strip()
        if not addr:
            return
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(addr)
        # Brief inline confirmation on the button itself. Always restore the
        # canonical label (NOT the live text) — otherwise a second click while
        # it still says "Copied" captures that as the "original" and it sticks.
        btn = self.sender()
        if btn is not None:
            btn.setText(_t("copied"))
            QTimer.singleShot(1200, lambda b=btn: b.setText(_t("copy_address")))

    def _show_address(self):
        def done(res: CliResult):
            _dbg(f"_show_address.done: ok={getattr(res,'ok',None)} "
                 f"out={(res.output or '')[:80]!r}")
            if not res.ok:
                self.addr_label.setText(_t("loading_address"))
                return
            text = (res.output or "").strip()
            m = re.search(r"(ker[xy][a-z]*:[0-9a-z]+)", text, re.IGNORECASE)
            addr = m.group(1) if m else ""
            prev_addr = self._current_address
            _dbg(f"_show_address: addr={addr!r} prev={prev_addr!r} "
                 f"hist_loading={getattr(self,'_history_loading',None)}")
            self._current_address = addr
            self.addr_label.setText(addr or "(no address)")
            self.addr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if addr:
                if addr != prev_addr:
                    # Account/address changed: discard the previous account's
                    # history so an in-flight load for it can't render here, and
                    # show a fresh loading state. _load_history's stale-address
                    # guard drops any late results for the old account.
                    self._explorer_txs = None
                    self._explorer_total = None
                    self._tx_page = 0
                    self._last_history_raw = ""
                    self._last_history_html = None  # don't dedup-skip the re-render
                    self._history_loading = False
                    self.history_view.setHtml(
                        f"<div style='color:{TOKENS['text_dim']};'>"
                        f"{_t('loading_transactions')}</div>")
                # QR 50% smaller (240 -> 120), centered under the address.
                pix = address_qr_pixmap(addr, size=120)
                if pix:
                    self.qr_label.setPixmap(pix)
                else:
                    self.qr_label.setText("(install qrcode + Pillow for QR)")
                # Now that we have the address, load explorer history.
                self._load_history()
            else:
                self.qr_label.clear()
        self.status("Requesting address…")
        self._submit(self.driver.run, done, "address")

    @staticmethod
    def _parse_history(raw: str):
        """Parse `history list` output into tx dicts: hash, daa, direction, amount."""
        lines = []
        for ln in (raw or "").split("\n"):
            s = ln.strip()
            if not s:
                continue
            if "•" in s and "KRX" in s:          # prompt fragment
                continue
            if re.fullmatch(r"\d+\s+transactions?", s, re.I):  # summary line
                continue
            lines.append(s)
        txs = []
        i = 0
        while i < len(lines):
            m = re.match(
                r"\[[0-9a-f]+\]\s+([0-9a-f]{64})\s+@([\d,]+)\s+DAA\s*-\s*(\w+)\s+(\w+)",
                lines[i], re.I)
            if not m:
                i += 1
                continue
            hash_, daa, direction = m.group(1), m.group(2), m.group(3)
            amount = ""
            if i + 1 < len(lines):
                detail = lines[i + 1]
                mt = re.search(r"Total:\s*([+\-]?[\d.]+)", detail)
                if mt:
                    amount = mt.group(1)
                else:
                    mp = re.search(r"Payment:\s*([\d.]+)", detail)
                    if mp:
                        amount = "-" + mp.group(1)
                i += 2
            else:
                i += 1
            txs.append({"hash": hash_, "daa": daa,
                        "direction": direction, "amount": amount})
        return txs

    def _apply_tx_filter(self):
        """Re-render transactions using the current size threshold."""
        txt = self.tx_filter_edit.text().strip().replace(",", "")
        try:
            self._tx_min_size = float(txt) if txt else 0.0
        except ValueError:
            self._tx_min_size = 0.0
        self._tx_page = 0  # filtering changes the set — go back to first page
        # Prefer explorer data if we have it; else re-render cached CLI history.
        if getattr(self, "_explorer_txs", None):
            self._render_history_explorer(self._explorer_txs)
        elif self._last_history_raw:
            self._render_history(self._last_history_raw)

    def _render_history(self, raw: str):
        """Render parsed transactions as styled HTML into the Transactions box."""
        self._last_history_raw = raw or ""
        low = (raw or "").lower()
        if (not (raw or "").strip()
                or "no such file or directory" in low
                or "notfound" in low
                or "error reading folder" in low):
            self.history_view.setHtml(
                f"<div style='color:{TOKENS['text_dim']};'>{_t('no_transactions')}</div>")
            return
        txs = self._parse_history(raw)
        # Apply the optional size filter (absolute amount >= threshold).
        thresh = getattr(self, "_tx_min_size", 0.0)
        if thresh > 0:
            kept = []
            for tx in txs:
                try:
                    if abs(float(tx["amount"])) >= thresh:
                        kept.append(tx)
                except (ValueError, TypeError):
                    kept.append(tx)  # keep txs we couldn't size
            txs = kept
        if not txs:
            msg = (_t("no_transactions") if thresh <= 0
                   else f"No transactions ≥ {thresh:g} KRX.")
            self.history_view.setHtml(
                f"<div style='color:{TOKENS['text_dim']};'>{msg}</div>")
            return
        green = TOKENS["green"]
        text = TOKENS["text"]
        muted = TOKENS["text_dim"]
        parts = [
            f"<div style='color:{text}; font-weight:600; margin-bottom:6px;'>"
            f"{len(txs)} transaction{'s' if len(txs) != 1 else ''}</div>"
        ]
        import html as _html
        for idx, tx in enumerate(txs):
            amt = tx["amount"]
            pos = amt.startswith("+")
            amt_color = green if pos else TOKENS['red']
            amt_disp = f"{_html.escape(amt)} KRX" if amt else ""
            direction = _html.escape(tx["direction"].capitalize())
            raw_hash = str(tx.get("hash", ""))
            if re.fullmatch(r"[0-9a-fA-F]{64}", raw_hash):
                tx_url = f"https://keryx-labs.com/tx/{raw_hash}"
                hash_html = (
                    f"<a href='{tx_url}' style='color:{green}; "
                    f"text-decoration:none;'>{raw_hash}</a>")
            else:
                hash_html = _html.escape(raw_hash)
            parts.append(
                f"<div style='padding:6px 0;'>"
                f"<div><span style='color:{text}; font-weight:600;'>{direction}</span>"
                f"&nbsp;&nbsp;<span style='color:{amt_color}; font-weight:600;'>{amt_disp}</span>"
                f"</div>"
                f"<div style='font-family:monospace; font-size:11px; "
                f"word-break:break-all;'>{hash_html}</div>"
                f"</div>"
            )
            if idx != len(txs) - 1:
                parts.append(
                    f"<hr style='border:none; border-top:1px solid {green}; "
                    f"opacity:0.4; margin:0;'>")
        self.history_view.setHtml("".join(parts))

    def _load_history(self):
        # Explorer is the sole source of transaction history (queried by address,
        # so it's the true on-chain history regardless of wallet instance).
        addr = self._current_address
        _dbg(f"_load_history: addr={addr!r} hist_loading={getattr(self,'_history_loading',None)}")
        if not addr:
            self.history_view.setHtml(
                f"<div style='color:{TOKENS['text_dim']};'>{_t('loading_address')}</div>")
            return
        # Guard against overlapping loads (auto-refresh racing itself / a manual
        # reload). Without this, two loads render at different stages and the
        # list visibly bounces between counts.
        if getattr(self, "_history_loading", False):
            _dbg("_load_history: BLOCKED by _history_loading guard")
            return
        self._history_loading = True

        # 1. Show cached history instantly — but ONLY on the first load (when the
        # view is still empty). On periodic refreshes the list is already shown,
        # so re-rendering the cache here is what caused the flicker.
        from keryx_wallet.core.explorer import (
            get_address_transactions, get_address_tx_count)
        from keryx_wallet.core.worker import CliRunnable
        from keryx_wallet.core import history_cache

        # view is still empty). On periodic refreshes the list is already shown,
        # so re-rendering the cache here is what caused the flicker.
        cached = history_cache.get_cached(addr)
        first_load = not getattr(self, "_explorer_txs", None)
        if cached and first_load:
            self._render_history_explorer(cached)

        known = history_cache.known_tx_ids(addr)

        def work():
            # Authoritative total from the explorer (matches the website).
            count = get_address_tx_count(addr)
            if known:
                # Incremental: fetch only txs newer than what we have cached.
                new_txs = get_address_transactions(addr, stop_at_ids=known)
                if isinstance(new_txs, list):
                    return ("merge", new_txs, count)
                return ("none", None, count)
            # First time for this address: full fetch.
            full = get_address_transactions(addr)
            return ("full", full, count)

        def done(result):
            _dbg(f"_load_history.done: load_addr={addr!r} cur={self._current_address!r} "
                 f"result={(str(result)[:60])!r}")
            # Stale guard: if the user switched accounts while this load was in
            # flight, the active address changed — discard this result so the
            # previous account's txs never render into the current account.
            if addr != self._current_address:
                _dbg("_load_history.done: STALE — discarded")
                return
            self._history_loading = False
            if isinstance(result, tuple) and len(result) == 3:
                mode, data, count = result
            elif isinstance(result, tuple):
                mode, data = result; count = None
            else:
                mode, data, count = "none", None, None
            if isinstance(count, int) and count > 0:
                self._explorer_total = count
            if mode == "full" and isinstance(data, list):
                history_cache.set_cached(addr, data)
                self._render_history_explorer(data)
            elif mode == "merge" and isinstance(data, list):
                if data:
                    # Only re-render if the merge actually brought in new txs.
                    merged = history_cache.merge_new(addr, data)
                    self._render_history_explorer(merged)
                elif first_load and cached:
                    # First load, no new txs: make sure the cache is shown.
                    self._render_history_explorer(cached)
                elif isinstance(count, int) and getattr(self, "_explorer_txs", None):
                    # No new txs but the authoritative count updated — refresh
                    # just the header by re-rendering the current list.
                    self._render_history_explorer(self._explorer_txs)
            elif not cached:
                self.history_view.setHtml(
                    f"<div style='color:{TOKENS['text_dim']};'>"
                    "Could not reach the explorer. Transactions unavailable.</div>")

        def failed(_e):
            if addr != self._current_address:
                return
            self._history_loading = False
            if not cached:
                self.history_view.setHtml(
                    f"<div style='color:{TOKENS['text_dim']};'>"
                    "Could not reach the explorer. Transactions unavailable.</div>")

        task = CliRunnable(work)
        task.signals.finished.connect(done)
        task.signals.error.connect(failed)
        self.pool.start(task)

    def _render_history_explorer(self, txs: list):
        """Render explorer-sourced transactions with pagination (500/page).
        The size filter applies across ALL transactions before paging."""
        # Defensive de-duplication by tx_id: even if the cache or a merge ever
        # introduced a repeat, never display or count it twice. Preserves order
        # (first occurrence wins, which is the newest).
        if txs:
            _seen = set()
            _deduped = []
            for t in txs:
                tid = t.get("tx_id")
                if tid and tid in _seen:
                    continue
                if tid:
                    _seen.add(tid)
                _deduped.append(t)
            txs = _deduped
        self._explorer_txs = txs
        thresh = getattr(self, "_tx_min_size", 0.0)
        shown = txs
        if thresh > 0:
            shown = [t for t in txs if abs(t.get("amount", 0)) >= thresh]
        if not shown:
            msg = (_t("no_transactions") if thresh <= 0
                   else f"No transactions ≥ {thresh:g} KRX.")
            self.history_view.setHtml(
                f"<div style='color:{TOKENS['text_dim']};'>{msg}</div>")
            self._update_page_controls(0, 1)
            return

        PER_PAGE = 500
        total = len(shown)
        pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        # Clamp current page to valid range (filter may have shrunk the list).
        self._tx_page = max(0, min(getattr(self, "_tx_page", 0), pages - 1))
        start = self._tx_page * PER_PAGE
        page_items = shown[start:start + PER_PAGE]

        import datetime
        import html
        green = TOKENS["green"]; text = TOKENS["text"]; muted = TOKENS["text_dim"]
        # Prefer the explorer's authoritative total (matches the website). Only
        # use it when no size filter is active — with a filter, the meaningful
        # number is how many txs passed the filter, not the chain total.
        auth_total = getattr(self, "_explorer_total", None)
        if thresh <= 0 and isinstance(auth_total, int) and auth_total > 0:
            header = _t("tx_count", n=f"{auth_total:,}")
        else:
            header = _t("tx_count", n=f"{total:,}")
        if pages > 1:
            header += " — " + _t("showing_range",
                                  a=f"{start + 1:,}", b=f"{start + len(page_items):,}")
        parts = [
            f"<div style='color:{text}; font-weight:600; margin-bottom:6px;'>"
            f"{header}</div>"
        ]
        for idx, tx in enumerate(page_items):
            amt = tx.get("amount", 0.0)
            try:
                amt = float(amt)
            except (TypeError, ValueError):
                amt = 0.0
            pos = amt >= 0
            amt_color = green if pos else TOKENS['red']
            amt_disp = f"{'+' if pos else ''}{amt:.8f} KRX"
            raw_dir = (tx.get("direction") or "").lower()
            dir_key = {"incoming": "incoming", "outgoing": "outgoing",
                       "external": "external"}.get(raw_dir)
            direction = html.escape(_t(dir_key) if dir_key else raw_dir.capitalize())
            when = ""
            bt = tx.get("block_time", 0)
            if bt:
                try:
                    when = datetime.datetime.fromtimestamp(
                        int(bt) / 1000).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    when = ""
            # Date/time only — DAA removed from display per design.
            meta = when
            meta = html.escape(meta)
            # tx_id is a 64-char hex hash on-chain. Only treat it as a link if it
            # matches that shape; otherwise show it escaped, never as raw HTML or
            # an href. This blocks any markup/URL injection from a bad API reply.
            raw_id = str(tx.get('tx_id', ''))
            if re.fullmatch(r"[0-9a-fA-F]{64}", raw_id):
                tx_url = f"https://keryx-labs.com/tx/{raw_id}"
                hash_html = (
                    f"<a href='{tx_url}' style='color:{green}; "
                    f"text-decoration:none;'>{raw_id}</a>")
            else:
                hash_html = html.escape(raw_id)
            parts.append(
                f"<div style='padding:6px 0;'>"
                f"<div><span style='color:{text}; font-weight:600;'>{direction}</span>"
                f"&nbsp;&nbsp;<span style='color:{amt_color}; font-weight:600;'>{amt_disp}</span>"
                f"&nbsp;&nbsp;<span style='color:{muted};'>{meta}</span></div>"
                f"<div style='font-family:monospace; font-size:11px; "
                f"word-break:break-all;'>{hash_html}</div>"
                f"</div>"
            )
            if idx != len(page_items) - 1:
                parts.append(
                    f"<hr style='border:none; border-top:1px solid {green}; "
                    f"opacity:0.4; margin:0;'>")
        new_html = "".join(parts)
        # Preserve the scroll position across re-renders (auto-refresh brings in
        # new txs; without this the view would jump back to the top while the
        # user is reading). Skip the update entirely if nothing changed.
        if getattr(self, "_last_history_html", None) == new_html:
            self._update_page_controls(self._tx_page, pages)
            return
        sb = self.history_view.verticalScrollBar()
        prev_scroll = sb.value() if sb else 0
        at_top = prev_scroll == 0
        self._last_history_html = new_html
        self.history_view.setHtml(new_html)
        # Only restore scroll if the user had scrolled down; if they were at the
        # top, leave them at the top (newest items are there).
        if sb and not at_top:
            sb.setValue(min(prev_scroll, sb.maximum()))
        self._update_page_controls(self._tx_page, pages)

    def _update_page_controls(self, page: int, pages: int):
        """Show/enable the page navigation controls and the editable indicator."""
        if not hasattr(self, "tx_prev_btn"):
            return
        self._tx_pages = pages
        multi = pages > 1
        for wdg in (self.tx_first_btn, self.tx_prev_btn, self.tx_page_edit,
                    self.tx_page_total, self.tx_next_btn, self.tx_last_btn):
            wdg.setVisible(multi)
        if multi:
            self.tx_page_edit.setText(str(page + 1))
            self.tx_page_total.setText(f"/ {pages}")
            self.tx_first_btn.setEnabled(page > 0)
            self.tx_prev_btn.setEnabled(page > 0)
            self.tx_next_btn.setEnabled(page < pages - 1)
            self.tx_last_btn.setEnabled(page < pages - 1)

    def _tx_page_goto(self):
        """Jump to the page number typed in the page field."""
        txt = self.tx_page_edit.text().strip()
        try:
            target = int(txt) - 1  # field is 1-based, internal is 0-based
        except ValueError:
            # Restore the current page number on invalid input.
            self.tx_page_edit.setText(str(getattr(self, "_tx_page", 0) + 1))
            return
        pages = getattr(self, "_tx_pages", 1)
        self._tx_page = max(0, min(target, pages - 1))
        if getattr(self, "_explorer_txs", None) is not None:
            self._render_history_explorer(self._explorer_txs)

    def _tx_page_first(self):
        self._tx_page = 0
        if getattr(self, "_explorer_txs", None) is not None:
            self._render_history_explorer(self._explorer_txs)

    def _tx_page_last(self):
        self._tx_page = max(0, getattr(self, "_tx_pages", 1) - 1)
        if getattr(self, "_explorer_txs", None) is not None:
            self._render_history_explorer(self._explorer_txs)

    def _tx_page_prev(self):
        self._tx_page = max(0, getattr(self, "_tx_page", 0) - 1)
        if getattr(self, "_explorer_txs", None) is not None:
            self._render_history_explorer(self._explorer_txs)

    def _tx_page_next(self):
        self._tx_page = getattr(self, "_tx_page", 0) + 1
        if getattr(self, "_explorer_txs", None) is not None:
            self._render_history_explorer(self._explorer_txs)

    def _open_address_book(self):
        from keryx_wallet.ui.address_book import AddressBookDialog
        dlg = AddressBookDialog(self, current_address=self.send_addr.text().strip())
        chosen = dlg.exec_and_get()
        if chosen:
            self.send_addr.setText(chosen)
            self.send_addr.setCursorPosition(0)

    def _do_send(self):
        if not self._connected:
            dialogs._warn(self, _t("not_connected"), _t("connect_before_send"))
            return
        addr = self.send_addr.text().strip()
        amount = self.send_amount.text().strip()
        fee = self.send_fee.text().strip()
        if not addr or not amount or not fee:
            dialogs._warn(self, _t("missing_fields"), _t("fields_required"))
            return
        # Validate the address: must be a Keryx address (keryx:/keryxtest: prefix).
        if not re.match(r"^keryx[a-z]*:[0-9a-z]+$", addr, re.IGNORECASE):
            dialogs._warn(self, _t("invalid_address"), "")
            return
        # Validate the amount: numeric, non-zero, and at least the dust minimum.
        MIN_SEND = 0.069
        try:
            amt_val = float(amount)
        except ValueError:
            dialogs._warn(self, _t("amount_zero"), "")
            return
        if amt_val == 0:
            dialogs._warn(self, _t("amount_zero"), "")
            return
        if amt_val < MIN_SEND:
            dialogs._warn(self, _t("amount_too_small"), "")
            return
        # Insufficient-funds check: amount (plus fee) must not exceed balance.
        bal = getattr(self, "_balance_krx", None)
        if isinstance(bal, (int, float)):
            try:
                fee_val = float(fee)
            except ValueError:
                fee_val = 0.0
            if amt_val + fee_val > bal:
                dialogs._warn(self, _t("insufficient_funds"), "")
                return

        def show_dialog(estimate):
            dlg = SendConfirmDialog(addr, amount, fee, estimate=estimate, parent=self)
            if dlg.exec() != dlg.DialogCode.Accepted:
                self.status("Send cancelled.")
                return
            pw = dlg.password()

            def sent(res: CliResult):
                def show_result():
                    try:
                        if getattr(res, "ok", False):
                            parsed = KeryxCliDriver.parse_send_result(
                                getattr(res, "output", "")) or {}
                            if parsed:
                                dialogs._info(
                                    self, _t("sent"),
                                    f"{_t('amount')} {parsed.get('amount','?')} KRX\n"
                                    f"{_t('fee')} {parsed.get('fees','?')} KRX\n"
                                    f"{_t('total')} {parsed.get('total','?')} KRX")
                            else:
                                dialogs._info(self, _t("sent"),
                                              getattr(res, "output", "") or "")
                            self.send_addr.clear()
                            self.send_amount.clear()
                            self.send_fee.clear()
                            self._refresh_accounts()
                            self._load_history()
                        else:
                            dialogs._error(
                                self, _t("send_uncertain"),
                                (getattr(res, "error", "") or "") + "\n\n" +
                                (getattr(res, "output", "") or ""))
                    except Exception as e:
                        try:
                            dialogs._info(self, _t("sent"), str(e))
                        except Exception:
                            pass
                # Defer to the next event-loop turn so the (now-closing) send
                # confirm dialog is fully torn down before we open another modal
                # — opening a modal from within a closing modal's accept() chain
                # can hard-crash Qt on some platforms.
                QTimer.singleShot(0, show_result)
            self.status("Broadcasting…")
            self._submit(self.driver.send, sent, addr, amount, fee, pw)

        def after_estimate(res):
            est = None
            try:
                if res and getattr(res, "ok", False):
                    est = KeryxCliDriver.parse_estimate_result(res.output)
            except Exception:
                est = None
            show_dialog(est)

        # Fetch a (non-broadcasting) fee estimate so the confirm dialog can show
        # the fee and amount+fee total BEFORE the user signs. If it's
        # unavailable, after_estimate falls back to showing the dialog without it.
        self.status(_t("estimating") + "…")
        self._submit(self.driver.estimate, after_estimate, amount, fee)

    def _switch_wallet(self):
        """Close the open wallet and return to the Wallet Options screen."""
        self._balance_timer.stop()
        self._wallet_open = False
        self._wallet_name = ""
        self._current_address = ""
        self._history_loading = False   # don't leave a load flag stuck for next open
        # Ask the CLI to close the wallet (best-effort; ignore result).
        self._submit(self.driver.run, lambda res: None, "close")
        # Reset dashboard display
        self.balance_label.setText("—")
        self.addr_label.setText("")
        self.qr_label.clear()
        self.history_view.clear()
        self.send_addr.clear(); self.send_amount.clear(); self.send_fee.clear()
        self.status("Wallet closed. Choose a wallet option.")
        self.wallet_choice.setCurrentIndex(0)
        self._populate_wallet_list()
        self.stack.setCurrentWidget(self.wallet_screen)

    def _do_export(self):
        if not self._wallet_open:
            dialogs._warn(self, _t("no_wallet"), _t("open_wallet_first"))
            return
        pw, ok = dialogs.get_password(
            self, _t("export_phrase_title"),
            _t("export_pw_prompt"))
        if not ok or not pw:
            return

        def done(res: CliResult):
            if res.ok:
                from keryx_wallet.ui.create_dialog import ExportRevealDialog
                parsed = KeryxCliDriver.parse_export_result(res.output)
                ExportRevealDialog(parsed.get("mnemonic", ""),
                                   parsed.get("xpub", ""), parent=self).exec()
                self.status("Recovery phrase exported (shown once).")
            else:
                dialogs._warn(self, "Export failed",
                                    res.error or "Could not export.")
                self.status(f"Export failed: {res.error or 'unknown'}")

        self.status("Exporting…")
        self._submit(self.driver.export_mnemonic, done, pw)

    # ── Consolidate (sweep) ──────────────────────────────────────────────────

    UTXOS_PER_BATCH = 80
    BATCH_FEE_KRX = 0.3

    def _do_consolidate(self):
        if not self._wallet_open:
            dialogs._warn(self, _t("no_wallet"), _t("open_wallet_first"))
            return
        addr = (self._current_address or "").strip()
        if not addr:
            dialogs._warn(self, "No address", "Address not loaded yet.")
            return

        # Fetch the live UTXO count from the explorer, then show the breakdown.
        from keryx_wallet.core.explorer import get_utxo_count
        from keryx_wallet.core.worker import CliRunnable
        import math

        def work():
            return get_utxo_count(addr)

        def done(result):
            if not isinstance(result, int):
                dialogs._warn(
                    self, "Could not read UTXOs",
                    "The explorer did not return a UTXO count. Try again shortly.")
                return
            utxos = result
            if utxos <= 1:
                dialogs.message(
                    self, _t("nothing_to_consolidate"),
                    f"This address has {utxos} UTXO"
                    f"{'s' if utxos != 1 else ''} — consolidation isn't needed.",
                    "info")
                return
            batches = max(1, math.ceil(utxos / self.UTXOS_PER_BATCH))
            total_fee = batches * self.BATCH_FEE_KRX
            body = (
                f"{_t('utxos_label')}: {utxos:,}\n"
                f"{_t('batches_label')}: {batches:,}\n"
                f"{_t('batch_fee')}: {self.BATCH_FEE_KRX:g} KRX\n"
                f"{_t('total_fee')}: {total_fee:g} KRX"
            )
            if not dialogs.confirm(
                    self,
                    _t("consolidate_title"),
                    body, yes_text=_t("proceed"), no_text=_t("cancel")):
                return
            # User approved — ask for password, then sweep.
            pw, ok = dialogs.get_password(
                self, "", _t("enter_password"))
            if not ok or not pw:
                return

            def swept(res: CliResult):
                if res.ok:
                    parsed = KeryxCliDriver.parse_sweep_result(res.output) or {}
                    u = parsed.get("utxos", utxos)
                    b = parsed.get("batches", batches)
                    # Use the CLI-reported fee if present; otherwise fall back to
                    # the calculated estimate (batches × per-batch fee) so the
                    # dialog never shows a bare "?".
                    if parsed.get("fees"):
                        fees = parsed["fees"]
                    else:
                        fees = f"{b * self.BATCH_FEE_KRX:g}"
                    dialogs.message(
                        self, _t("consolidation_complete"),
                        _t("swept_result", u=f"{u:,}", b=f"{b:,}", fees=fees),
                        "success")
                    self._refresh_accounts()
                    self._load_history()
                else:
                    dialogs._warn(self, _t("consolidation_failed"),
                                  res.error or "Sweep did not complete.")

            self.status("Consolidating…")
            self._submit(self.driver.sweep, swept, pw)

        self.status("Reading UTXOs…")
        task = CliRunnable(work)
        task.signals.finished.connect(done)
        task.signals.error.connect(
            lambda e: dialogs._warn(self, "Could not read UTXOs", str(e)))
        self.pool.start(task)

    # ── shutdown ─────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Stop periodic work first so no new tasks are queued during teardown.
        try:
            self._balance_timer.stop()
        except Exception:
            pass
        # Give in-flight worker threads a brief moment to finish so they don't
        # emit into a half-destroyed window (the _safe_emit guard catches the
        # rest). 1.5s is enough for quick calls; long ones are abandoned.
        try:
            self.pool.waitForDone(1500)
        except Exception:
            pass
        try:
            self.driver.stop()
        except Exception:
            pass
        super().closeEvent(event)
