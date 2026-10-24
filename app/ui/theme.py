from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

from ..core.config import cfg
from ..resources import asset_path

LIGHT = dict(bg="#f6f7fb", surface="#ffffff", border="#e4e7f0", text="#191d2c", muted="#73798c",
             primary="#6c5ce7", primary_hover="#5b4bd6", primary_bg="#6c5ce7", primary_bg_hover="#5b4bd6",
             danger="#d94149", success="#249563", warning="#a96108", hover="#f0f1f7", input="#ffffff",
             sidebar="#121522", sidebar_text="#c7cbe0", sidebar_active="#24293d", select="#ece9ff",
             check_border="#a7acbd")
DARK = dict(bg="#10121c", surface="#181b29", border="#2a2e40", text="#eceef7", muted="#9ba2b8",
            primary="#9b8cff", primary_hover="#aea3ff", primary_bg="#6554d9", primary_bg_hover="#7665e8",
            danger="#ff7077", success="#48c78e", warning="#d18a2c", hover="#222638", input="#131624",
            sidebar="#0b0d15", sidebar_text="#aab0cc", sidebar_active="#202437", select="#302a68",
            check_border="#5c6280")


def resolve_theme(name: str) -> str:
    """'system' follows the OS light/dark setting (Qt >= 6.5); anything unknown is light."""
    if name == "system":
        try:
            return "dark" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "light"
        except Exception:
            return "light"
    return "dark" if name == "dark" else "light"


def palette(name: str) -> dict:
    return DARK if resolve_theme(name) == "dark" else LIGHT


def qpalette(p: dict) -> QPalette:
    """A real Qt palette, so native-drawn parts (checkboxes, spin arrows, calendar, scrollbars) follow the theme."""
    q = QPalette()
    c = QColor
    pairs = {
        QPalette.Window: p["bg"], QPalette.WindowText: p["text"], QPalette.Base: p["input"],
        QPalette.AlternateBase: p["bg"], QPalette.Text: p["text"], QPalette.Button: p["surface"],
        QPalette.ButtonText: p["text"], QPalette.ToolTipBase: p["surface"], QPalette.ToolTipText: p["text"],
        QPalette.Highlight: p["primary_bg"], QPalette.HighlightedText: "#ffffff", QPalette.Link: p["primary"],
        QPalette.PlaceholderText: p["muted"], QPalette.BrightText: "#ffffff",
    }
    for role, color in pairs.items():
        q.setColor(role, c(color))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        q.setColor(QPalette.Disabled, role, c(p["muted"]))
    return q


def apply_theme(app, family: str, name: str) -> None:
    """Fusion style + palette + stylesheet. Fusion renders identically on every OS and honours the palette."""
    if app.style().objectName().lower() != "fusion":
        app.setStyle("Fusion")
    resolved = resolve_theme(name)
    p = palette(name)
    app.setPalette(qpalette(p))
    app.setStyleSheet(stylesheet(p, family, dark=resolved == "dark", rtl=cfg.language == "fa"))


def preview_css(p: dict) -> str:
    """Default stylesheet for rendered HTML previews (QTextBrowser)."""
    return f"body {{ color: {p['text']}; }} a {{ color: {p['primary']}; }} h2, h3 {{ color: {p['text']}; }}"


def _icon(name: str) -> str:
    # Qt style sheets resolve url(...) as a file path; keep forward slashes for Windows too.
    return asset_path("icons", name).as_posix()


def stylesheet(p: dict, family: str, dark: bool = False, rtl: bool = False) -> str:
    down = _icon(f"chevron-down-{'dark' if dark else 'light'}.svg")
    up = _icon(f"chevron-up-{'dark' if dark else 'light'}.svg")
    check = _icon("check.svg")
    radio = _icon("radio-dot.svg")

    # Combo/spin subcontrols are mirrored automatically in RTL, so right-side positions are the
    # direction-independent way to say "on the trailing edge" (left in Persian).
    spin_up_pos = "top right"
    spin_down_pos = "bottom right"
    spin_pad = "padding: 7px 11px; padding-right: 32px;"
    spin_value_align = "'AlignRight | AlignVCenter'" if rtl else "'AlignLeft | AlignVCenter'"
    arrow_pos = "center right"
    combo_pad = "padding: 7px 11px; padding-right: 34px;"
    group_title_side = "top right" if rtl else "top left"
    # This property is flipped for RTL too: "left" places the tabs on the leading (right) edge.
    tab_align = "left"
    # Qt flips QPushButton text-align for RTL, so "left" is the leading edge in both directions.
    start_align = "left"

    return f"""
* {{ font-family: "{family}", "Segoe UI", "Tahoma", sans-serif; font-size: 13px; }}
QWidget {{ color: {p['text']}; }}
QWidget:disabled {{ color: {p['muted']}; }}
QMainWindow, QDialog, QStackedWidget, #page {{ background: {p['bg']}; }}
#tabPage {{ background: {p['surface']}; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 6px 9px; }}

/* ---------------------------------------------------------------- chrome --- */
#sidebar {{ background: {p['sidebar']}; }}
#brand {{ border-bottom: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 8px; }}
#sidebar QLabel {{ color: {p['sidebar_text']}; }}
#brandName {{ color: #ffffff; font-size: 20px; font-weight: 700; }}
#brandSub {{ color: {p['sidebar_text']}; font-size: 11px; }}
QPushButton#nav {{ background: transparent; color: {p['sidebar_text']}; border: none; border-radius: 9px;
    padding: 11px 13px; text-align: {start_align}; font-size: 14px; font-weight: 500; }}
QPushButton#nav:hover {{ background: {p['sidebar_active']}; color: #ffffff; }}
QPushButton#nav:checked {{ background: {p['primary_bg']}; color: #ffffff; font-weight: 600; }}
#topbar {{ background: {p['surface']}; border-bottom: 1px solid {p['border']}; }}
#topbar QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 7px 9px; font-size: 13px; }}
#topbar QToolButton:hover {{ background: {p['hover']}; border-color: {p['border']}; }}
#topbar QToolButton:pressed {{ background: {p['select']}; }}

/* ----------------------------------------------------------------- cards --- */
QFrame#card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 12px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#muted, QLabel[muted="true"] {{ color: {p['muted']}; }}
QLabel[success="true"] {{ color: {p['success']}; font-weight: 600; }}
QLabel#statValue {{ font-size: 28px; font-weight: 700; color: {p['primary']}; }}
QLabel#chip {{ background: {p['select']}; color: {p['primary']}; border-radius: 7px; padding: 2px 10px; }}

/* ---------------------------------------------------------------- inputs --- */
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox,
QDateTimeEdit, QDateEdit {{
    background: {p['input']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 8px;
    min-height: 22px; padding: 7px 11px;
    selection-background-color: {p['primary_bg']}; selection-color: #ffffff; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateTimeEdit:focus, QDateEdit:focus {{ border: 1px solid {p['primary']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QTextBrowser:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled, QDateTimeEdit:disabled, QDateEdit:disabled {{
    background: {p['bg']}; color: {p['muted']}; border-color: {p['border']}; }}
QLineEdit[readOnly="true"] {{ color: {p['muted']}; }}

QComboBox {{ {combo_pad} }}
QComboBox::drop-down, QDateEdit::drop-down, QDateTimeEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: {arrow_pos}; width: 28px;
    border: none; background: transparent; }}
QComboBox::drop-down:hover, QDateEdit::drop-down:hover, QDateTimeEdit::drop-down:hover {{ background: {p['hover']}; border-radius: 5px; }}
QComboBox::down-arrow, QDateEdit::down-arrow, QDateTimeEdit::down-arrow {{ image: url("{down}"); width: 12px; height: 8px; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 6px;
    padding: 4px; outline: 0; selection-background-color: {p['primary_bg']}; selection-color: #ffffff; }}
QComboBox QAbstractItemView::item {{ min-height: 24px; padding: 2px 6px; border-radius: 4px; }}

QSpinBox, QDoubleSpinBox {{ {spin_pad} qproperty-alignment: {spin_value_align}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin: padding; subcontrol-position: {spin_up_pos};
    width: 26px; border: none; background: transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin: padding; subcontrol-position: {spin_down_pos};
    width: 26px; border: none; background: transparent; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {p['hover']}; border-radius: 4px; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{up}"); width: 10px; height: 7px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{down}"); width: 10px; height: 7px; }}

/* --------------------------------------------------------------- buttons --- */
QPushButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px;
    min-height: 22px; padding: 7px 15px; }}
QPushButton:hover {{ background: {p['hover']}; }}
QPushButton:pressed {{ background: {p['border']}; }}
QPushButton:default {{ background: {p['primary_bg']}; color: #ffffff; border-color: {p['primary_bg']}; font-weight: bold; }}
QPushButton:default:hover {{ background: {p['primary_bg_hover']}; border-color: {p['primary_bg_hover']}; }}
QPushButton:disabled {{ color: {p['muted']}; background: {p['surface']}; border-color: {p['border']}; }}
QPushButton[primary="true"] {{ background: {p['primary_bg']}; color: #ffffff; border: 1px solid {p['primary_bg']}; font-weight: bold; }}
QPushButton[primary="true"]:hover {{ background: {p['primary_bg_hover']}; border-color: {p['primary_bg_hover']}; }}
QPushButton[primary="true"]:disabled {{ background: {p['surface']}; border: 1px solid {p['border']}; color: {p['muted']}; }}
QPushButton[danger="true"] {{ color: {p['danger']}; border: 1px solid {p['danger']}; background: {p['surface']}; }}
QPushButton[danger="true"]:hover {{ background: {p['danger']}; color: #ffffff; }}
QPushButton[danger="true"]:disabled {{ color: {p['muted']}; border-color: {p['border']}; }}
QPushButton[store="true"] {{ padding: 9px 14px; text-align: {start_align}; }}
QToolButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px;
    min-height: 22px; padding: 7px 11px; }}
QToolButton:hover {{ background: {p['hover']}; }}
QToolButton:pressed {{ background: {p['border']}; }}
QToolButton:disabled {{ color: {p['muted']}; background: {p['surface']}; border-color: {p['border']}; }}
QToolButton::menu-indicator {{ image: none; }}
QPushButton[ai="true"] {{ background: {p['select']}; color: {p['primary']}; border: 1px solid {p['primary']}; font-weight: bold; }}
QPushButton[ai="true"]:hover {{ background: {p['primary_bg']}; color: #ffffff; }}
QPushButton[ai="true"]:disabled {{ background: {p['hover']}; color: {p['muted']}; border: 1px solid {p['border']}; }}
QToolButton[ai="true"] {{ background: {p['select']}; color: {p['primary']}; border: 1px solid {p['primary']}; padding: 6px 8px; }}
QToolButton[ai="true"]:hover {{ background: {p['primary_bg']}; color: #ffffff; }}
QToolButton[ai="true"]:disabled {{ background: {p['hover']}; color: {p['muted']}; border: 1px solid {p['border']}; }}

/* ---------------------------------------------------------------- tables --- */
QTableWidget, QListWidget {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px;
    gridline-color: {p['border']}; alternate-background-color: {p['bg']}; outline: 0; }}
QTableWidget::item {{ padding: 6px; border: none; }}
QTableWidget::item:hover {{ background: {p['hover']}; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {p['select']}; color: {p['text']}; }}
QListWidget::item {{ border-radius: 7px; }}
QListWidget::item:hover {{ background: {p['hover']}; }}
QHeaderView::section {{ background: {p['surface']}; color: {p['muted']}; border: none; border-bottom: 1px solid {p['border']};
    padding: 10px 8px; font-weight: 600; }}
QTableCornerButton::section {{ background: {p['surface']}; border: none; }}

/* ---------------------------------------------------------- check / radio --- */
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator, QTableView::indicator, QTableWidget::indicator {{
    width: 16px; height: 16px; background: {p['input']}; border: 1px solid {p['check_border']}; }}
QCheckBox::indicator, QTableView::indicator, QTableWidget::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover, QTableView::indicator:hover, QTableWidget::indicator:hover {{
    border-color: {p['primary']}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked, QTableWidget::indicator:checked {{
    background: {p['primary_bg']}; border-color: {p['primary_bg']}; image: url("{check}"); }}
QRadioButton::indicator:checked {{ background: {p['primary_bg']}; border-color: {p['primary_bg']}; image: url("{radio}"); }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled, QTableView::indicator:disabled, QTableWidget::indicator:disabled {{
    background: {p['bg']}; border-color: {p['border']}; }}
QCheckBox::indicator:checked:disabled, QTableView::indicator:checked:disabled, QTableWidget::indicator:checked:disabled {{
    background: {p['muted']}; border-color: {p['muted']}; }}

/* ------------------------------------------------------------------ tabs --- */
QTabWidget::tab-bar {{ alignment: {tab_align}; }}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 9px; background: {p['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 9px 16px; margin: 0 2px; border-bottom: 2px solid transparent; color: {p['muted']}; }}
QTabBar::tab:hover {{ color: {p['text']}; background: {p['hover']}; border-radius: 6px 6px 0 0; }}
QTabBar::tab:selected {{ color: {p['primary']}; border-bottom: 2px solid {p['primary']}; font-weight: bold; }}
QTabBar::tab:disabled {{ color: {p['muted']}; }}

/* -------------------------------------------------------------- scrollbars --- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {p['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* --------------------------------------------------------------- popups --- */
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 7px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p['primary_bg']}; color: #ffffff; }}
QMenu::item:disabled {{ color: {p['muted']}; }}
QMenu::separator {{ height: 1px; background: {p['border']}; margin: 5px 8px; }}

/* -------------------------------------------------------------- progress --- */
QProgressBar {{ border: 1px solid {p['border']}; border-radius: 6px; text-align: center; background: {p['input']}; min-height: 18px; }}
QProgressBar::chunk {{ background: {p['primary_bg']}; border-radius: 5px; }}

/* ------------------------------------------------------------- groupbox --- */
QGroupBox {{ border: 1px solid {p['border']}; border-radius: 9px; margin-top: 16px; padding: 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: {group_title_side}; padding: 0 7px;
    color: {p['muted']}; font-weight: bold; }}

/* ----------------------------------------------------------------- toast --- */
QFrame#toast {{ border-radius: 10px; }}
QLabel#toastText {{ color: #ffffff; font-weight: 600; background: transparent; }}
"""
