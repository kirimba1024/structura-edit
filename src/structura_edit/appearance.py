ACCENT = "#26a888"
HOVER = "#eee9d7"
REMOVAL = "#ef6652"
MAP_BACKGROUND = "#d8e6cc"
SCENE_BACKGROUND = "#cfe6ed"
PANEL_BACKGROUND = "#f1eedc"
PANEL_HOVER = "#fff9df"
PANEL_PRESSED = "#dedfc5"
BORDER = "#7d8c74"
TEXT = "#263b30"
SELECTION_FILL = 0.045
TEMPORARY_FILL = 0.025
GHOST_OPACITY = 0.42
REMOVAL_OPACITY = 0.35
MAP_HEADER_HEIGHT = 20
MAP_ICON_SIZE = 48
PROGRESS_DELAY_MS = 300

EDITOR_STYLE = (
    f"QMainWindow, QStatusBar {{ background: {PANEL_BACKGROUND}; color: {TEXT}; }}"
    f"QLabel, QDockWidget {{ color: {TEXT}; }}"
    f"QDockWidget::title {{ background: {PANEL_BACKGROUND}; padding: 3px; }}"
    f"QPushButton, QToolButton {{ border: 1px solid {BORDER}; border-top-color: #fffdf0; "
    f"border-left-color: #fffdf0; border-radius: 0; padding: 3px 7px; background: {PANEL_BACKGROUND}; color: {TEXT}; }}"
    f"QPushButton:hover, QToolButton:hover {{ background: {PANEL_HOVER}; }}"
    f"QPushButton:pressed, QToolButton:pressed {{ background: {PANEL_PRESSED}; }}"
    f"QPushButton:disabled, QToolButton:disabled {{ color: {BORDER}; }}"
    f"QPushButton:focus, QToolButton:focus {{ border-color: {ACCENT}; }}"
    f"QLineEdit, QPlainTextEdit, QSpinBox {{ border: 1px solid {BORDER}; border-radius: 0; "
    f"background: #fffdf0; color: {TEXT}; selection-background-color: {ACCENT}; }}"
    f"QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}"
)


def apply_theme(widget):
    from PySide6.QtGui import QColor, QPalette

    palette = widget.palette()
    for role, color in ((QPalette.ColorRole.Window, PANEL_BACKGROUND),
                        (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Base, "#fffdf0"),
                        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, PANEL_BACKGROUND),
                        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                        (QPalette.ColorRole.HighlightedText, "#ffffff")):
        palette.setColor(role, QColor(color))
    widget.setPalette(palette)
    widget.setStyleSheet(EDITOR_STYLE)
