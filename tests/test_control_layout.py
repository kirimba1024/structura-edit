from dataclasses import replace
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QAbstractSpinBox, QLabel, QStyle, QStyleOptionButton, QWidget

from structura_edit.placement import Placement
from structura_edit.destination_rule import DestinationRule
from structura_edit.placement_bar import PlacementBar
from structura_edit.repeat_bar import RepeatBar
from structura_edit.panels import OperationPanel
from structura_edit.selection_panel import SelectionPanel
from structura_edit.theme import apply_theme


@pytest.mark.parametrize("width", [720, 1104])
@pytest.mark.parametrize("expanded", [False, True])
def test_placement_cells_stay_put_for_long_text_numbers_and_state_changes(qt_app, edit, width, expanded):
    host = QWidget()
    apply_theme(host)
    host.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    host.resize(width, 660)
    bar = PlacementBar(host)
    bar.resize(width, bar.sizeHint().height())
    model = Placement(edit.copy(edit.select(((0, 0, 0), (1, 1, 1)))), (0, 0, 0))
    bar.update_state(model, edit, None, busy=False, visible=True)
    host.show()
    try:
        bar.more.setChecked(expanded)
        QTest.qWait(30)
        viewport = host.size()
        widgets = (bar.info, bar.follow, bar.repeat, bar.air, bar.apply, bar.cancel, bar.more, bar.destination,
                   *bar.coordinates, *bar.transforms, bar.hint, bar.content.blocks, bar.content.entities, bar.content.note)
        widgets = [widget for widget in widgets if widget.isVisible()]
        def rectangles():
            return [QRect(widget.mapTo(bar.placement, QPoint()), widget.size()) for widget in widgets]
        fixed = (bar.info, bar.follow, bar.repeat, bar.apply, bar.cancel, bar.more, bar.destination, *bar.transforms[:2])
        fixed_geometry = [widget.geometry() for widget in fixed]
        bar.content.set_clipboard(SimpleNamespace(block_count=500_000, entities=range(500_000), excluded_players=1))
        QTest.qWait(30)
        assert [widget.geometry() for widget in fixed] == fixed_geometry
        for field in (bar.content.blocks, bar.content.entities):
            option = QStyleOptionButton()
            field.initStyleOption(option)
            text = field.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, field)
            assert field.fontMetrics().horizontalAdvance(field.text()) < text.width()
        if expanded:
            assert max(field.width() for field in bar.coordinates) - min(field.width() for field in bar.coordinates) <= 1
        for position, size, busy in (((-30_000_000, 30_000_000, -30_000_000), (30_000_000,) * 3, True),
                                     ((0, 0, 0), (1, 1, 1), False)):
            model.position = position
            model.clipboard = replace(model.clipboard, size=size)
            model.following = not model.following
            model.destination = DestinationRule("air" if busy else "material", "example:machine[active=true]")
            bar.update_state(model, edit, None, busy=busy, visible=True)
            QTest.qWait(30)
            current = rectangles()
            assert [widget.geometry() for widget in fixed] == fixed_geometry
            assert host.size() == viewport
            assert len({widget.height() for widget in widgets if widget not in (bar.hint, bar.content.note)}) == 1
            for field in bar.coordinates:
                if expanded:
                    assert field.fontMetrics().horizontalAdvance(field.text()) < field.lineEdit().contentsRect().width()
            for index, rect in enumerate(current):
                assert bar.placement.rect().contains(rect)
                overlaps = [(widgets[index].objectName() or type(widgets[index]).__name__, rect,
                             type(widgets[other_index]).__name__, other) for other_index, other in enumerate(current)
                            if other_index > index and rect.intersects(other)]
                assert not overlaps, overlaps
            assert bar.hint.wordWrap()
            assert QLabel.text(bar.hint) == bar.hint.text()
            assert bar.hint.height() >= bar.hint.heightForWidth(bar.hint.width())
            for label in (bar.info,):
                shown = QLabel.text(label)
                assert label.fontMetrics().horizontalAdvance(shown) <= label.contentsRect().width()
                assert label.toolTip().startswith(label.text() + "\n")
                assert "Original will stay after Place" in label.toolTip()
                if shown != label.text():
                    assert shown.endswith("…")
        bar.more.setChecked(True)
        QTest.qWait(30)
        assert host.size() == viewport
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
        host.close()
        host.deleteLater()


@pytest.mark.parametrize("width", [1104, 1380])
def test_repeat_panel_fits_long_values_without_overflow(qt_app, width):
    host = QWidget()
    apply_theme(host)
    host.resize(width, 200)
    bar = RepeatBar(host)
    bar.show()
    host.show()
    try:
        QTest.qWait(30)
        bar.reposition()
        widgets = [bar.layout().itemAt(index).widget() for index in range(bar.layout().count())]
        geometry = [widget.geometry() for widget in widgets]
        bar.copies.setValue(500_000)
        bar.gap.setValue(30_000_000)
        bar.direction.setCurrentIndex(5)
        QTest.qWait(30)
        assert [widget.geometry() for widget in widgets] == geometry
        assert bar.width() == host.width() and bar.height() == 100
        for index, rect in enumerate(geometry):
            assert bar.rect().contains(rect)
            overlaps = [(type(widgets[index]).__name__, rect, type(widgets[other_index]).__name__, other)
                        for other_index, other in enumerate(geometry) if other_index > index and rect.intersects(other)]
            assert not overlaps, overlaps
        for field in (bar.copies, bar.gap):
            assert field.fontMetrics().horizontalAdvance(field.text()) < field.lineEdit().contentsRect().width()
    finally:
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
        QTest.qWait(30)
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
