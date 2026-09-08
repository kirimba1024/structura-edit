from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from structura_edit import Selection
from structura_edit.selection import RegionSelection
from structura_edit.selection_actions import SelectionActions
from structura_edit.selection_panel import SelectionPanel


def test_world_coordinates_commit_inclusively_and_invalid_input_restores_fields(qt_app):
    model, panel = RegionSelection(), SelectionPanel()
    model.reset((16, 16, 16))
    model.set_bounds((4, 2, 4), (8, 6, 8))
    panel.set_document(model.size, (-32, -64, 48))
    panel.set_selection(model.region)
    available = [True]
    camera = SimpleNamespace(position=(2.8, 10.1, 12.5))
    actions = SelectionActions(model, panel, camera, available=lambda: available[0])
    actions.changed.connect(lambda: panel.set_selection(model.region))
    errors = []
    actions.message.connect(errors.append)
    assert tuple(field.value() for field in panel.fields[0]) == (-28, -62, 52)
    assert tuple(field.value() for field in panel.fields[1]) == (-25, -59, 55)
    field = panel.fields[1][0]
    field.selectAll()
    QTest.keyClicks(field, "-24")
    assert model.region.upper[0] == 8
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert model.region.upper[0] == 9
    field.selectAll()
    QTest.keyClicks(field, "-32")
    QTest.keyClick(field, Qt.Key.Key_Return)
    assert errors and model.region.upper[0] == 9 and field.value() == -24
    available[0] = False
    actions.at_camera(0)
    assert model.anchor == (4, 2, 4)
    available[0] = True
    actions.at_camera(0)
    assert model.anchor == (2, 10, 12) and model.opposite == (8, 5, 7)
    assert model.region == Selection((2, 5, 7), (9, 11, 13))
    panel.close()
    panel.deleteLater()
