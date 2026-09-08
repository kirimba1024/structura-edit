from dataclasses import replace

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QAbstractSpinBox, QLabel, QStyle, QStyleOptionButton, QWidget

from structura_edit.placement import Placement
from structura_edit.placement_bar import PlacementBar
from structura_edit.panels import OperationPanel
from structura_edit.selection_panel import SelectionPanel
from structura_edit.theme import apply_theme


@pytest.mark.parametrize("width", [720, 1104])
def test_placement_cells_stay_put_for_long_text_numbers_and_state_changes(qt_app, edit, width):
    host = QWidget()
    apply_theme(host)
    host.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    host.resize(width, 200)
    bar = PlacementBar(host)
    bar.resize(width, bar.sizeHint().height())
    model = Placement(edit.copy(edit.select(((0, 0, 0), (1, 1, 1)))), (0, 0, 0))
    bar.update_state(model, edit, None, busy=False, visible=True)
    host.show()
    try:
        qt_app.processEvents()
        widgets = (bar.info, bar.follow, bar.air, bar.apply, bar.cancel, *bar.coordinates, *bar.transforms, bar.hint)
        geometry = [widget.geometry() for widget in widgets]
        for position, size, busy in (((-30_000_000, 30_000_000, -30_000_000), (30_000_000,) * 3, True),
                                     ((0, 0, 0), (1, 1, 1), False)):
            model.position = position
            model.clipboard = replace(model.clipboard, size=size)
            model.following = not model.following
            bar.update_state(model, edit, None, busy=busy, visible=True)
            qt_app.processEvents()
            assert [widget.geometry() for widget in widgets] == geometry
            assert len({widget.height() for widget in widgets}) == 1
            for field in bar.coordinates:
                assert field.fontMetrics().horizontalAdvance(field.text()) < field.lineEdit().contentsRect().width()
            for index, rect in enumerate(geometry):
                assert bar.placement.rect().contains(rect)
                assert not any(rect.intersects(other) for other in geometry[index + 1:])
            for label in (bar.info, bar.hint):
                shown = QLabel.text(label)
                assert label.fontMetrics().horizontalAdvance(shown) <= label.contentsRect().width()
                assert label.toolTip() == label.text()
                if shown != label.text():
                    assert shown.endswith("…")
        host.setFocus()
        focus = qt_app.focusWidget()
        values = []
        bar.air_changed.connect(values.append)
        QTest.mouseClick(bar.air, Qt.MouseButton.LeftButton, pos=QPoint(bar.air.width() - 2, 2))
        assert values == [True] and qt_app.focusWidget() is focus
        option = QStyleOptionButton()
        bar.air.initStyleOption(option)
        indicator = bar.air.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, bar.air)
        text = bar.air.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, bar.air)
        assert indicator.right() < text.left() and bar.air.rect().contains(indicator)
    finally:
        bar.stats.shutdown()
        host.close()
        host.deleteLater()


@pytest.mark.parametrize("panel_type", [SelectionPanel, OperationPanel])
def test_panel_cells_reserve_space_for_labels_and_large_numbers(qt_app, panel_type):
    apply_theme(QWidget())
    panel = panel_type()
    panel.setFixedWidth(384)
    panel.show()
    try:
        if isinstance(panel, SelectionPanel):
            panel.set_document((60_000_000,) * 3, (-30_000_000,) * 3)
            panel.step.setValue(60_000_000)
        else:
            panel.mode.setCurrentText("Move blocks")
            panel.set_values({"offset": (-30_000_000, 30_000_000, -30_000_000)})
        qt_app.processEvents()
        widgets = [widget for widget in panel.findChildren(QWidget)
                   if isinstance(widget, (QLabel, QAbstractSpinBox, QAbstractButton)) and widget.isVisible()]
        for index, widget in enumerate(widgets):
            assert widget.parentWidget().rect().contains(widget.geometry())
            siblings = [other for other in widgets[index + 1:] if other.parentWidget() is widget.parentWidget()]
            assert not any(widget.geometry().intersects(other.geometry()) for other in siblings)
            if isinstance(widget, QAbstractSpinBox):
                assert widget.fontMetrics().horizontalAdvance(widget.text()) < widget.lineEdit().contentsRect().width()
            if isinstance(widget, QLabel) and widget.minimumWidth() == widget.maximumWidth():
                assert QLabel.text(widget) == widget.text()
    finally:
        panel.close()
        panel.deleteLater()
