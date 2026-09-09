from pathlib import Path
from string import Template

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication, QProxyStyle, QStyle

from . import appearance


DATA = Path(__file__).parent / "data"


class PixelStyle(QProxyStyle):
    def __init__(self):
        super().__init__("Fusion")

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (QStyle.PixelMetric.PM_LayoutLeftMargin, QStyle.PixelMetric.PM_LayoutTopMargin,
                      QStyle.PixelMetric.PM_LayoutRightMargin, QStyle.PixelMetric.PM_LayoutBottomMargin,
                      QStyle.PixelMetric.PM_LayoutHorizontalSpacing, QStyle.PixelMetric.PM_LayoutVerticalSpacing):
            return appearance.GRID
        if metric in (QStyle.PixelMetric.PM_DefaultFrameWidth, QStyle.PixelMetric.PM_DockWidgetSeparatorExtent):
            return 1
        return super().pixelMetric(metric, option, widget)

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_Widget_Animate:
            return 0
        return super().styleHint(hint, option, widget, returnData)


def pixel_font(size=appearance.FONT_SIZE):
    font = QFont("Monocraft")
    font.setPixelSize(size)
    font.setStyleStrategy(QFont.StyleStrategy.NoAntialias)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


def apply_theme(widget):
    app = QApplication.instance()
    if not app.property("structuraTheme"):
        if QFontDatabase.addApplicationFont(str(DATA / "fonts/Monocraft.ttf")) < 0:
            raise RuntimeError("Bundled Monocraft font could not be loaded")
        app.setStyle(PixelStyle())
        app.setFont(pixel_font())
        app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        palette = app.palette()
        colors = {"Window": appearance.PANEL_BACKGROUND, "WindowText": appearance.TEXT, "Base": appearance.INPUT_BASE,
                  "Text": appearance.TEXT, "Button": appearance.PANEL_BACKGROUND, "ButtonText": appearance.TEXT,
                  "Highlight": appearance.ACCENT, "HighlightedText": "#ffffff", "ToolTipBase": appearance.PANEL_BACKGROUND,
                  "ToolTipText": appearance.TEXT, "AlternateBase": appearance.PANEL_PRESSED}
        for name, color in colors.items():
            palette.setColor(getattr(QPalette.ColorRole, name), QColor(color))
        for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(appearance.BORDER))
        app.setPalette(palette)
        values = vars(appearance) | {"ASSETS": DATA.as_posix(), "CONTROL_CONTENT": appearance.CONTROL_HEIGHT - 4,
                                     "TITLE_FONT_SIZE": appearance.FONT_SIZE * 2}
        app.setStyleSheet(Template((DATA / "editor.qss").read_text()).substitute(values))
        app.setProperty("structuraTheme", True)
    widget.setFont(app.font())
