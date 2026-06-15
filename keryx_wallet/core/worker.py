"""
worker.py — runs KeryxCliDriver commands on a background thread.

The CLI subprocess calls (connect, list, send, ...) can block for seconds.
They must never run on the Qt UI thread or the window freezes. This module
wraps a single callable in a QThread-friendly worker that emits the CliResult
back to the UI thread via a signal.

Pattern: build a CliTask with a function + args, move it to a QThread (or use
QThreadPool via CliRunnable), connect `finished`/`error`, start it.
"""

from __future__ import annotations

from typing import Callable, Any

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable, pyqtSlot


class CliSignals(QObject):
    finished = pyqtSignal(object)   # emits CliResult (or any return value)
    error = pyqtSignal(str)


class CliRunnable(QRunnable):
    """
    Runs `fn(*args, **kwargs)` on a QThreadPool thread and emits the result.

    Use for one-shot CLI operations triggered from the UI. The driver itself is
    internally locked, so concurrent runnables serialise safely on the REPL.
    """

    def __init__(self, fn: Callable[..., Any], *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.signals = CliSignals()

    @pyqtSlot()
    def run(self):
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as e:  # noqa — surface any driver exception to the UI
            self.signals.error.emit(str(e))
            return
        self.signals.finished.emit(result)
