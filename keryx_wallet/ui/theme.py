"""
theme.py — Keryx terminal aesthetic for the wallet GUI.

Derived from keryx-labs.com: a dark "sovereign terminal" look — near-black
background, phosphor-green primary accent, monospace type, and the command-line
motifs ($ prompts, // comments, > markers) that run through the Keryx brand.

The palette is expressed as named tokens so every screen pulls from one source.

  bg          #0A0E0C   near-black with a faint green cast (terminal black)
  surface     #11161300 -> #121A16  raised panels / group boxes
  surface_2   #0D1310   insets (text areas, lists)
  border      #1F2A24   hairline dividers
  green       #36F5A0   primary phosphor-green accent (CTAs, focus, success)
  green_dim   #1C7F55   pressed / muted accent
  text        #C9D6CF   primary body text (soft green-grey, not pure white)
  text_dim    #6E8278   secondary / labels
  amber       #F5C542   warnings (review/caution)
  red         #FF5C6C   destructive / irreversible (the send warning)

Type: a monospace family for the whole UI (the brand is a terminal). We request
a stack that resolves on Ubuntu 26.04 to a good mono.
"""

MONO = '"JetBrains Mono", "DejaVu Sans Mono", "Ubuntu Mono", monospace'

TOKENS = {
    "bg":        "#0A0E0C",
    "surface":   "#121A16",
    "surface_2": "#0D1310",
    "border":    "#1F2A24",
    "green":     "#36F5A0",
    "green_dim": "#1C7F55",
    "text":      "#C9D6CF",
    "text_dim":  "#6E8278",
    "amber":     "#F5C542",
    "red":       "#FF5C6C",
}


def stylesheet() -> str:
    t = TOKENS
    return f"""
    * {{
        font-family: {MONO};
        font-size: 13px;
        color: {t['text']};
    }}
    QMainWindow, QDialog, QWidget {{
        background-color: {t['bg']};
    }}

    /* Headings rendered via rich text <h2> pick this up loosely; we also style
       QLabel headings through the green accent on group titles. */
    QLabel {{
        color: {t['text']};
        background: transparent;
    }}

    QGroupBox {{
        background-color: {t['surface']};
        border: 1px solid {t['border']};
        border-radius: 6px;
        margin-top: 14px;
        padding: 12px 12px 12px 12px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 2px 8px;
        color: {t['green']};
        background-color: {t['bg']};
        /* prefix group titles with a terminal marker */
    }}

    QLineEdit, QPlainTextEdit, QTextEdit, QListWidget {{
        background-color: {t['surface_2']};
        border: 1px solid {t['border']};
        border-radius: 5px;
        padding: 6px 8px;
        color: {t['text']};
        selection-background-color: {t['green_dim']};
        selection-color: {t['bg']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 1px solid {t['green']};
    }}
    QLineEdit::placeholder {{
        color: {t['text_dim']};
    }}

    QPushButton {{
        background-color: transparent;
        border: 1px solid {t['green_dim']};
        border-radius: 5px;
        padding: 7px 16px;
        color: {t['green']};
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {t['green_dim']};
        color: {t['bg']};
    }}
    QPushButton:pressed {{
        background-color: {t['green']};
        color: {t['bg']};
    }}
    QPushButton:disabled {{
        border: 1px solid {t['border']};
        color: {t['text_dim']};
    }}

    QListWidget::item {{
        padding: 4px 2px;
    }}
    QListWidget::item:selected {{
        background-color: {t['green_dim']};
        color: {t['bg']};
    }}

    QStatusBar {{
        background-color: {t['surface_2']};
        color: {t['text_dim']};
        border-top: 1px solid {t['border']};
    }}
    QStatusBar::item {{ border: none; }}

    QScrollBar:vertical {{
        background: {t['surface_2']};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t['border']};
        border-radius: 5px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {t['green_dim']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

    QMessageBox, QInputDialog {{
        background-color: {t['surface']};
        color: {t['text']};
        font-family: {MONO};
        min-width: 360px;
    }}
    QMessageBox QLabel, QInputDialog QLabel {{
        color: {t['text']};
        font-family: {MONO};
        font-size: 13px;
        min-width: 320px;
    }}
    QMessageBox QPushButton, QInputDialog QPushButton {{
        background-color: {t['surface_2']};
        color: {t['green']};
        border: 1px solid {t['green_dim']};
        border-radius: 6px;
        padding: 6px 18px;
        font-family: {MONO};
        min-width: 70px;
    }}
    QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {{
        background-color: {t['green_dim']};
        color: {t['bg']};
    }}
    QInputDialog QLineEdit {{
        background-color: {t['surface_2']};
        color: {t['text']};
        border: 1px solid {t['border']};
        border-radius: 6px;
        padding: 6px 8px;
        font-family: {MONO};
    }}
    QToolTip {{
        background-color: {t['surface']};
        color: {t['green']};
        border: 1px solid {t['green_dim']};
        border-radius: 4px;
        padding: 5px 8px;
        font-family: {MONO};
        font-size: 12px;
    }}
    /* Pointer cursor on clickable controls. */
    QPushButton, QComboBox, QCheckBox, QRadioButton {{
        /* cursor set in code via setCursor for reliability across styles */
    }}
    /* Highlight the selected/hovered item in dropdown lists (Open wallet etc). */
    QComboBox QAbstractItemView {{
        background-color: {t['surface']};
        color: {t['text']};
        selection-background-color: {t['green_dim']};
        selection-color: {t['bg']};
        border: 1px solid {t['border']};
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 4px 8px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {t['green_dim']};
        color: {t['bg']};
    }}
    """


# Convenience inline styles for specific semantic widgets.
WARNING_LABEL = f"color:{TOKENS['red']}; font-weight:700;"
CAUTION_LABEL = f"color:{TOKENS['amber']}; font-weight:600;"
ACCENT_LABEL  = f"color:{TOKENS['green']}; font-weight:600;"
DIM_LABEL     = f"color:{TOKENS['text_dim']};"
MONO_BLOCK    = (f"font-family:{MONO}; background:{TOKENS['surface_2']}; "
                 f"border:1px solid {TOKENS['border']}; border-radius:5px; "
                 f"padding:8px; color:{TOKENS['text']};")
