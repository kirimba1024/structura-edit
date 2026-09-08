from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from structura_edit.mouse_look import MouseLook


def test_native_relative_events_keep_subpixel_motion_and_ignore_old_or_inactive_events():
    from PySide6.QtCore import QPointF
    from structura_edit.cocoa_mouse import CocoaMouse

    event = {"type": 5, "deltaX": 0.25, "deltaY": -0.5, "timestamp": 12.1}
    view = SimpleNamespace(hasFocus=lambda: True, window=lambda: SimpleNamespace(isActiveWindow=lambda: True))
    capture = SimpleNamespace(active=True, pending=QPointF(), started=12.0, view=view,
                              selectors={key: key for key in event},
                              send_integer=lambda ptr, key: event[key], send_double=lambda ptr, key: event[key])
    for _ in range(4):
        assert CocoaMouse.nativeEventFilter(capture, b"mac_generic_NSEvent", 1) is False
    assert CocoaMouse.sample(capture) == QPointF(1, -2)
    assert CocoaMouse.sample(capture).isNull()
    event["timestamp"] = 11.9
    CocoaMouse.nativeEventFilter(capture, b"mac_generic_NSEvent", 1)
    event["timestamp"], event["type"] = 12.2, 10
    CocoaMouse.nativeEventFilter(capture, b"mac_generic_NSEvent", 1)
    event["type"], capture.active = 5, False
    CocoaMouse.nativeEventFilter(capture, b"mac_generic_NSEvent", 1)
    assert CocoaMouse.sample(capture).isNull()


@pytest.mark.parametrize("warp_works", [False, True])
def test_captured_trackpad_motion_is_consumed_once_and_cursor_warps_are_ignored(qt_app, monkeypatch, warp_works):
    view = QWidget()
    view.resize(800, 600)
    cursor = SimpleNamespace(position=view.mapToGlobal(QPoint(100, 100)))
    def warp(point):
        if warp_works:
            cursor.position = point
    monkeypatch.setattr("structura_edit.mouse_look.QCursor.pos", lambda: cursor.position)
    monkeypatch.setattr("structura_edit.mouse_look.QCursor.setPos", warp)
    monkeypatch.setattr(view, "grabMouse", lambda: None)
    monkeypatch.setattr(view, "releaseMouse", lambda: None)
    monkeypatch.setattr("structura_edit.mouse_look.QWidget.mouseGrabber", lambda: view)
    monkeypatch.setattr("structura_edit.mouse_look.relative_mouse", lambda view: None)
    look = MouseLook(view)
    try:
        look.start(QPoint(100, 100), latched=True)
        if warp_works:
            look.move(view.rect().center())
        assert look.sample().isNull()
        look.move(look.anchor + QPoint(60, -20))
        assert look.sample() == QPoint(60, -20)
        for _ in range(60):
            assert look.sample().isNull()
        look.move(QPoint(1, 1))
        look.sample()
        if warp_works:
            look.move(view.rect().center())
        for _ in range(60):
            assert look.sample().isNull()
        look.move(look.anchor + QPoint(-20, 30))
        assert look.sample() == QPoint(-20, 30)
        look.stop()
        assert look.sample().isNull()
    finally:
        look.stop()
        view.deleteLater()
