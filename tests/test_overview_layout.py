from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QLabel

from structura_edit.ui import EditorWindow


def test_both_progress_rows_fit_without_moving_the_viewport(qt_app):
    window = EditorWindow(off_screen=True)
    window.resize(1104, 700)
    window.workbench.setCurrentIndex(1)
    window.show()
    window.timer.stop()
    try:
        for widget in (window.overview.button, window.slicing.button, window.refresh_button, window.save_button):
            widget.show()
        qt_app.processEvents()
        viewport = window.plotter.geometry()
        for progress in (window.progress, window.overview.progress):
            progress.set_progress("Building detail", 12_345, 62_424)
            progress.show()
        qt_app.processEvents()
        assert window.plotter.geometry() == viewport
        assert window.size() == QSize(1104, 700)
        window.grab().save("/private/tmp/structura-overview-progress-layout.png")
        rects = []
        for widget in (window.overview.button, window.refresh_button, window.save_button, window.progress, window.overview.progress):
            rect = QRect(widget.mapTo(window, QPoint()), widget.size())
            assert window.rect().contains(rect), (type(widget).__name__, rect, window.rect())
            assert all(not rect.intersects(other) for other in rects), (type(widget).__name__, rect, rects)
            rects.append(rect)
        for progress in (window.progress, window.overview.progress):
            assert progress.isVisible() and window.progress_panel.isVisible()
            assert QLabel.text(progress.label) == "Building detail"
            assert QLabel.text(progress.count) == "12,345/62,424"
        window.grab().save("/private/tmp/structura-overview-progress-layout.png")
        window.progress.finish()
        assert window.overview.progress.isVisible() and window.progress_panel.isVisible()
        window.overview.progress.finish()
        assert not window.progress_panel.isVisible()
    finally:
        window.document.load(None)
        window.close()
        qt_app.processEvents()
