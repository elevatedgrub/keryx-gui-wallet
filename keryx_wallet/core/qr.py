"""
qr.py — generate a QR code pixmap for a Keryx address.

Pure Qt rendering: `qrcode` produces the module matrix in pure Python and we
paint it with QPainter. NO Pillow dependency (so no native-lib bundling issues).
Falls back to None if `qrcode` is missing, so the address text still shows.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
from PyQt6.QtCore import Qt


def address_qr_pixmap(data: str, size: int = 240) -> Optional[QPixmap]:
    """
    Return a QPixmap containing a QR code for `data`, or None if generation
    fails. The caller should always also show the address as selectable text.
    """
    try:
        import qrcode
    except ImportError as e:
        import sys
        print(f"[keryx] QR unavailable: {e}", file=sys.stderr)
        return None

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=1,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        matrix = qr.get_matrix()          # list[list[bool]] — pure Python, no PIL
        n = len(matrix)
        if n == 0:
            return None

        scale = max(1, (size // n)) if size else 8
        img = QImage(n * scale, n * scale, QImage.Format.Format_RGB888)
        img.fill(QColor("white"))
        painter = QPainter(img)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("black"))
        for y, row in enumerate(matrix):
            for x, cell in enumerate(row):
                if cell:
                    painter.drawRect(x * scale, y * scale, scale, scale)
        painter.end()

        pix = QPixmap.fromImage(img)
        if size:
            pix = pix.scaled(size, size,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.FastTransformation)
        return pix
    except Exception as e:
        import sys
        print(f"[keryx] QR generation failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return None
