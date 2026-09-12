from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtWidgets import QWidget

from structura_edit.preview_orbit import Orbit, PreviewOrbit


def test_rotation_has_constant_speed_across_frame_rates_and_does_not_jump_after_a_pause():
    for rate in (30, 60, 120):
        orbit = Orbit()
        for _ in range(rate):
            orbit.advance(1 / rate)
        assert orbit.azimuth == pytest.approx(65)
    orbit.advance(10)
    assert orbit.azimuth == pytest.approx(66.5)
    orbit.drag(720, 1000)
    assert 0 <= orbit.azimuth < 360 and orbit.elevation == 80
    orbit.drag(0, -1000)
    assert orbit.elevation == -80


def test_preview_drag_rotates_while_auto_rotation_is_paused(qt_app):
    preview = QWidget()
    updates = []
    controller = PreviewOrbit(preview, lambda: False, lambda: updates.append(controller.orientation.azimuth))
    def event(kind, point):
        return SimpleNamespace(type=lambda: kind, button=lambda: Qt.MouseButton.LeftButton, position=lambda: QPointF(*point))
    try:
        controller.eventFilter(preview, event(QEvent.Type.MouseButtonPress, (50, 50)))
        controller.eventFilter(preview, event(QEvent.Type.MouseMove, (70, 40)))
        assert updates == [25] and controller.orientation.elevation == 24
        controller.eventFilter(preview, event(QEvent.Type.MouseButtonRelease, (70, 40)))
        assert controller.pressed is None
        controller.tick()
        assert updates == [25]
    finally:
        controller.close()
        preview.deleteLater()
