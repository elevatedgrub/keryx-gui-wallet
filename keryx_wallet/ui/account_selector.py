"""
account_selector.py — a dropdown-style account picker whose popup list can be
drag-reordered.

This is deliberately NOT a QComboBox. A QComboBox's popup intercepts the mouse
press/release to do "select item + close", which prevents dragging items inside
it. Here the popup is our own QFrame(Qt.Popup) hosting a list, so nothing fights
the drag.

Reordering uses PLAIN mouse handling (move rows on mouse-move) rather than Qt's
drag-and-drop / QDrag machinery. That keeps it client-side and behaves the same
on X11 and Wayland, and it works under the popup's mouse grab.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from keryx_wallet.ui.theme import TOKENS, MONO


class _ClickableField(QFrame):
    """The closed-dropdown field: a name label (left) + arrow pinned far right.
    Emits `clicked` when pressed."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"_ClickableField {{ background:{TOKENS['surface_2']}; "
            f"border:1px solid {TOKENS['border']}; border-radius:6px; }}"
            f"_ClickableField:hover {{ border-color:{TOKENS['green']}; }}")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 6, 8, 6)
        h.setSpacing(6)
        self.name = QLabel("—")
        self.name.setStyleSheet(
            f"QLabel {{ color:{TOKENS['text']}; font-family:{MONO}; border:none; }}")
        self.arrow = QLabel("▾")
        self.arrow.setStyleSheet(
            f"QLabel {{ color:{TOKENS['text_dim']}; border:none; }}")
        h.addWidget(self.name, 1)          # stretches → pushes arrow to far right
        h.addWidget(self.arrow, 0)

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)


class _ReorderList(QListWidget):
    """A list whose rows are reordered by dragging with the mouse — implemented
    by moving rows directly (no QDrag), so it's cross-platform and isn't blocked
    by the popup's mouse grab."""

    rowsReordered = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._press_row = -1
        self._moved = False

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_row = self.indexAt(e.pos()).row()
            self._moved = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press_row >= 0 and (e.buttons() & Qt.MouseButton.LeftButton):
            target = self.indexAt(e.pos()).row()
            if target >= 0 and target != self._press_row:
                it = self.takeItem(self._press_row)
                self.insertItem(target, it)
                self.setCurrentRow(target)
                self._press_row = target
                self._moved = True
            return  # consume — never let the base view start a QDrag
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._moved:
            # A drag, not a click: persist the order and DON'T emit a click
            # (which would switch the active account).
            self._press_row = -1
            self._moved = False
            self.rowsReordered.emit()
            e.accept()
            return
        self._press_row = -1
        super().mouseReleaseEvent(e)


class AccountSelector(QWidget):
    """A dropdown that shows the active account and opens a drag-reorderable list.

    Signals:
      activated(str)  — emitted with an account id when the user picks one
      reordered(list) — emitted with the new list of ids after a drag-reorder
    """

    activated = pyqtSignal(str)
    reordered = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []        # list of (id, label) in display order
        self._current_id = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.field = _ClickableField()
        self.field.clicked.connect(self._toggle)
        lay.addWidget(self.field)

        self._popup = QFrame(self, Qt.WindowType.Popup)
        self._popup.setStyleSheet(
            f"QFrame {{ background:{TOKENS['surface_2']}; "
            f"border:1px solid {TOKENS['border']}; border-radius:6px; }}")
        pl = QVBoxLayout(self._popup)
        pl.setContentsMargins(3, 3, 3, 3)
        self._list = _ReorderList()
        self._list.setStyleSheet(
            f"QListWidget {{ background:{TOKENS['surface_2']}; "
            f"color:{TOKENS['text']}; font-family:{MONO}; border:none; }}"
            f"QListWidget::item {{ padding:6px 4px; }}"
            f"QListWidget::item:selected {{ background:{TOKENS['green_dim']}; "
            f"color:{TOKENS['text']}; }}")
        self._list.itemClicked.connect(self._on_clicked)
        self._list.rowsReordered.connect(self._on_reordered)
        pl.addWidget(self._list)

    # ── public API ───────────────────────────────────────────────────────────

    def set_accounts(self, items, current_id):
        """items: list of (id, label) in display order. Does NOT emit signals."""
        self._items = list(items)
        self._current_id = current_id or ""
        label = dict(self._items).get(self._current_id, "")
        self.field.name.setText(label or "—")

    def current_id(self) -> str:
        return self._current_id

    # ── internals ──────────────────────────────────────────────────────────

    def _toggle(self):
        if self._popup.isVisible():
            self._popup.hide()
            return
        self._list.clear()
        for acc_id, label in self._items:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, acc_id)
            self._list.addItem(it)
            if acc_id == self._current_id:
                self._list.setCurrentItem(it)
        self._popup.setFixedWidth(max(self.field.width(), 260))
        rows = max(1, min(len(self._items), 8))
        self._list.setFixedHeight(rows * 32 + 6)
        self._popup.adjustSize()
        gp = self.field.mapToGlobal(QPoint(0, self.field.height()))
        self._popup.move(gp)
        self._popup.show()

    def _on_clicked(self, it):
        acc_id = it.data(Qt.ItemDataRole.UserRole)
        self._popup.hide()
        if acc_id and acc_id != self._current_id:
            self.set_accounts(self._items, acc_id)
            self.activated.emit(acc_id)

    def _on_reordered(self):
        ids = [self._list.item(r).data(Qt.ItemDataRole.UserRole)
               for r in range(self._list.count())]
        ids = [i for i in ids if i]
        by_id = dict(self._items)
        self._items = [(i, by_id[i]) for i in ids if i in by_id]
        self.reordered.emit(ids)
