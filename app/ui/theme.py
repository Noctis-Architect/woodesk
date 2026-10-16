from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette

LIGHT = dict(bg="#f4f5f9", surface="#ffffff", border="#e3e5ec", text="#1c2033", muted="#6b7185",
             primary="#6c5ce7", primary_hover="#5b4bd6", danger="#e5484d", success="#2fa36b",
             warning="#d9822b", hover="#eef0f7", input="#ffffff", sidebar="#161a2b",
             sidebar_text="#c7cbe0", sidebar_active="#2a2f4a", select="#e9e6ff")
DARK = dict(bg="#12141f", surface="#1b1e2e", border="#2c3047", text="#e8eaf6", muted="#8f95b2",
            primary="#8b7dff", primary_hover="#a095ff", danger="#ff6369", success="#3fc388",
            warning="#f0a050", hover="#242840", input="#15172a", sidebar="#0d0f19",
            sidebar_text="#aab0cc", sidebar_active="#23273d", select="#2b2760")


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
        QPalette.Highlight: p["primary"], QPalette.HighlightedText: "#ffffff", QPalette.Link: p["primary"],
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
    p = palette(name)
    app.setPalette(qpalette(p))
    app.setStyleSheet(stylesheet(p, family))


def preview_css(p: dict) -> str:
    """Default stylesheet for rendered HTML previews (QTextBrowser)."""
    return f"body {{ color: {p['text']}; }} a {{ color: {p['primary']}; }} h2, h3 {{ color: {p['text']}; }}"


def stylesheet(p: dict, family: str) -> str:
    return f"""
* {{ font-family: "{family}", "Segoe UI", "Tahoma", sans-serif; font-size: 13px; }}
QWidget {{ color: {p['text']}; }}
QMainWindow, QDialog, QStackedWidget, #page {{ background: {p['bg']}; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 4px; }}
#sidebar {{ background: {p['sidebar']}; }}
#sidebar QLabel {{ color: {p['sidebar_text']}; }}
#logo {{ color: #ffffff; font-size: 20px; font-weight: bold; padding: 18px 12px 12px 12px; }}
QPushButton#nav {{ background: transparent; color: {p['sidebar_text']}; border: none; border-radius: 8px;
    padding: 10px 14px; text-align: start; font-size: 14px; }}
QPushButton#nav:hover {{ background: {p['sidebar_active']}; color: #fff; }}
QPushButton#nav:checked {{ background: {p['primary']}; color: #fff; font-weight: bold; }}
#topbar {{ background: {p['surface']}; border-bottom: 1px solid {p['border']}; }}
QFrame#card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 12px; }}
QLabel#h1 {{ font-size: 22px; font-weight: bold; }}
QLabel#h2 {{ font-size: 15px; font-weight: bold; }}
QLabel#muted, QLabel[muted="true"] {{ color: {p['muted']}; }}
QLabel#statValue {{ font-size: 26px; font-weight: bold; color: {p['primary']}; }}
QLabel#chip {{ background: {p['select']}; color: {p['primary']}; border-radius: 9px; padding: 2px 10px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit, QDateEdit {{
    background: {p['input']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 6px 8px;
    selection-background-color: {p['primary']}; selection-color: #fff; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {p['primary']}; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; border: 1px solid {p['border']}; selection-background-color: {p['primary']}; selection-color: #fff; }}
QPushButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 7px 14px; }}
QPushButton:hover {{ background: {p['hover']}; }}
QPushButton:disabled {{ color: {p['muted']}; }}
QPushButton[primary="true"] {{ background: {p['primary']}; color: #fff; border: 1px solid {p['primary']}; font-weight: bold; }}
QPushButton[primary="true"]:hover {{ background: {p['primary_hover']}; }}
QPushButton[danger="true"] {{ color: {p['danger']}; border: 1px solid {p['danger']}; }}
QPushButton[danger="true"]:hover {{ background: {p['danger']}; color: #fff; }}
QToolButton {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 6px 10px; }}
QToolButton:hover {{ background: {p['hover']}; }}
QToolButton::menu-indicator {{ image: none; }}
QTableWidget, QListWidget {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px;
    gridline-color: {p['border']}; alternate-background-color: {p['bg']}; outline: 0; }}
QTableWidget::item {{ padding: 4px; border: none; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: {p['select']}; color: {p['text']}; }}
QHeaderView::section {{ background: {p['surface']}; color: {p['muted']}; border: none; border-bottom: 1px solid {p['border']};
    padding: 8px; font-weight: bold; }}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 10px; background: {p['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 9px 16px; margin: 0 2px; border-bottom: 2px solid transparent; color: {p['muted']}; }}
QTabBar::tab:selected {{ color: {p['primary']}; border-bottom: 2px solid {p['primary']}; font-weight: bold; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 6px; }}
QMenu::item:selected {{ background: {p['primary']}; color: #fff; }}
QProgressBar {{ border: 1px solid {p['border']}; border-radius: 6px; text-align: center; background: {p['input']}; }}
QProgressBar::chunk {{ background: {p['primary']}; border-radius: 5px; }}
QGroupBox {{ border: 1px solid {p['border']}; border-radius: 10px; margin-top: 14px; padding: 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {p['muted']}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QPushButton[ai="true"] {{ background: {p['select']}; color: {p['primary']}; border: 1px solid {p['primary']}; font-weight: bold; }}
QPushButton[ai="true"]:hover {{ background: {p['primary']}; color: #fff; }}
QPushButton[ai="true"]:disabled {{ background: {p['hover']}; color: {p['muted']}; border: 1px solid {p['border']}; }}
QToolButton[ai="true"] {{ background: {p['select']}; color: {p['primary']}; border: 1px solid {p['primary']}; padding: 6px 8px; }}
QToolButton[ai="true"]:hover {{ background: {p['primary']}; color: #fff; }}
QToolButton[ai="true"]:disabled {{ background: {p['hover']}; color: {p['muted']}; border: 1px solid {p['border']}; }}
#toast {{ border-radius: 10px; padding: 10px 18px; color: #fff; font-weight: bold; }}
"""
