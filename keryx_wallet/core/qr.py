"""
qr.py — generate a QR code pixmap for a Keryx address.

Used by the Receive screen. Falls back gracefully if the qrcode library is
missing so the address text is still shown.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtGui import QPixmap, QImage


def address_qr_pixmap(data: str, size: int = 240) -> Optional[QPixmap]:
    """
    Return a QPixmap containing a QR code for `data`, or None if generation
    fails (e.g. qrcode/Pillow not installed). The caller should always also
    display the address as selectable text so funds can be received regardless.
    """
    try:
        import qrcode
    except ImportError:
        return None

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

        w, h = img.size
        qimg = QImage(img.tobytes("raw", "RGB"), w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        if size:
            from PyQt6.QtCore import Qt
            pix = pix.scaled(size, size,
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return pix
    except Exception:
        return None
