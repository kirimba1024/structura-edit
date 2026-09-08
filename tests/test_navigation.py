from types import SimpleNamespace

import numpy as np
import pytest

try:
    import pyvista as pv
    from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QFocusEvent, QKeyEvent, QWheelEvent
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

    from structura_edit.camera import FreeCamera
    from structura_edit.navigation import Navigation
except ImportError:
    pytest.skip("Navigation requires the GUI extra", allow_module_level=True)


@pytest.fixture
def navigation(qt_app):
    view = QWidget()
    view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    plotter = SimpleNamespace(camera=pv.Camera(), bounds=(0, 10, 0, 10, 0, 10), render=lambda: None)
    plotter.camera.position, plotter.camera.focal_point = (0, 0, 10), (0, 0, 0)
    camera = FreeCamera(plotter, lambda position, direction: None)
    navigation = Navigation(view, camera, capture_mouse=False)
    navigation.enabled = True
    navigation.speed = 8.0
    yield navigation
    navigation.close()
    view.close()
    view.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def key(view, kind, code, *, text="", repeat=False, scan=0, modifiers=Qt.KeyboardModifier.NoModifier):
    QApplication.sendEvent(view, QKeyEvent(kind, code, modifiers, scan, 0, 0, text, repeat))


def test_single_press_flies_every_frame_until_release(navigation):
    camera = navigation.camera.plotter.camera
    start = np.array(camera.position)
    QTest.keyPress(navigation.view, Qt.Key.Key_W)
    for _ in range(60):
        navigation.tick(1 / 60)
    assert np.allclose(np.array(camera.position) - start, (0, 0, -8))
    QTest.keyRelease(navigation.view, Qt.Key.Key_W)
    stopped = camera.position
    for _ in range(60):
        navigation.tick(1 / 60)
    assert camera.position == stopped


def test_repeat_events_do_not_move_or_release_camera(navigation):
    view, camera = navigation.view, navigation.camera.plotter.camera
    start = camera.position
    QTest.keyPress(view, Qt.Key.Key_W)
    for _ in range(4):
        key(view, QEvent.Type.KeyRelease, Qt.Key.Key_W, repeat=True)
        key(view, QEvent.Type.KeyPress, Qt.Key.Key_W, repeat=True)
    assert camera.position == start
    navigation.tick(0.1)
    assert np.allclose(camera.position, (0, 0, 9.2))
    QTest.keyRelease(view, Qt.Key.Key_W)
    key(view, QEvent.Type.KeyPress, Qt.Key.Key_W, repeat=True)
    assert not navigation.keys


def test_aliases_cancel_opposing_directions_without_double_speed(navigation):
    view, camera = navigation.view, navigation.camera.plotter.camera
    for code in (Qt.Key.Key_W, Qt.Key.Key_Up, Qt.Key.Key_S):
        QTest.keyPress(view, code)
    navigation.tick(0.1)
    assert camera.position == (0, 0, 10)
    QTest.keyRelease(view, Qt.Key.Key_S)
    navigation.tick(0.1)
    assert np.allclose(camera.position, (0, 0, 9.2))
    QTest.keyRelease(view, Qt.Key.Key_W)
    navigation.tick(0.1)
    assert np.allclose(camera.position, (0, 0, 8.4))


def test_native_release_survives_layout_change_and_empty_text(navigation):
    view = navigation.view
    key(view, QEvent.Type.KeyPress, Qt.Key.Key_W, text="w", scan=17)
    key(view, QEvent.Type.KeyRelease, ord("Ц"), scan=17)
    assert not navigation.keys
    key(view, QEvent.Type.KeyPress, ord("Ц"), text="ц")
    key(view, QEvent.Type.KeyRelease, ord("Ц"))
    assert not navigation.keys


def test_two_shift_keys_keep_boost_until_both_are_released(navigation):
    view, camera = navigation.view, navigation.camera.plotter.camera
    key(view, QEvent.Type.KeyPress, Qt.Key.Key_Shift, scan=42)
    key(view, QEvent.Type.KeyPress, Qt.Key.Key_Shift, scan=54)
    key(view, QEvent.Type.KeyRelease, Qt.Key.Key_Shift, scan=42)
    QTest.keyPress(view, Qt.Key.Key_W)
    navigation.tick(0.1)
    assert np.allclose(camera.position, (0, 0, 6.8))
    key(view, QEvent.Type.KeyRelease, Qt.Key.Key_Shift, scan=54)
    navigation.tick(0.1)
    assert np.allclose(camera.position, (0, 0, 6))


@pytest.mark.parametrize("event", [QEvent.Type.FocusOut, QEvent.Type.Hide,
                                     QEvent.Type.WindowDeactivate, QEvent.Type.WindowBlocked,
                                     QEvent.Type.ApplicationDeactivate])
def test_interruption_stops_flight_and_look(navigation, event):
    QTest.keyPress(navigation.view, Qt.Key.Key_W)
    navigation.mouse_look.start(QPoint(100, 100))
    target = QApplication.instance() if event == QEvent.Type.ApplicationDeactivate else navigation.view
    QApplication.sendEvent(target, QFocusEvent(event) if event == QEvent.Type.FocusOut else QEvent(event))
    navigation.tick(0.1)
    assert not navigation.keys and not navigation.looking
    assert navigation.camera.plotter.camera.position == (0, 0, 10)


def test_release_in_other_widget_cancels_temporary_selection(navigation):
    changes = []
    navigation.extend_changed.connect(changes.append)
    QTest.keyPress(navigation.view, Qt.Key.Key_Shift)
    field = QLineEdit(navigation.view)
    QTest.keyRelease(field, Qt.Key.Key_Shift)
    QTest.keyClicks(field, "wasd")
    navigation.tick(0.1)
    assert changes == [True, False]
    assert field.text() == "wasd" and not navigation.keys


def test_escape_discards_pending_mouse_delta(navigation):
    look = navigation.mouse_look
    look.start(QPoint(100, 100))
    look.move(QPoint(200, 130))
    QTest.keyPress(navigation.view, Qt.Key.Key_Escape)
    navigation.tick(0.1)
    assert not navigation.looking
    assert np.allclose(navigation.camera.plotter.camera.direction, (0, 0, -1))


def test_freelook_click_selects_without_losing_camera_and_escape_releases(navigation):
    view = navigation.view
    selected, extended = [], []
    navigation.selected.connect(lambda *args: selected.append(args))
    navigation.extend_changed.connect(extended.append)
    QTest.keyClick(view, Qt.Key.Key_QuoteLeft, Qt.KeyboardModifier.ShiftModifier)
    assert navigation.looking and not navigation.keys
    navigation.mouse_look.move(navigation.mouse_look.anchor + QPoint(60, -20))
    navigation.tick(0.1)
    assert navigation.camera.plotter.camera.direction[0] > 0
    QTest.keyPress(view, Qt.Key.Key_Shift)
    QTest.keyPress(view, Qt.Key.Key_W)
    navigation.tick(0.1)
    assert extended[-1] is False
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    assert navigation.looking and navigation.keys and selected == [(view.rect().center(), False)]
    QTest.keyClick(view, Qt.Key.Key_Escape)
    stopped = navigation.camera.plotter.camera.position
    navigation.tick(0.1)
    assert not navigation.looking and not navigation.keys
    assert navigation.camera.plotter.camera.position == stopped
    navigation.start_fly()
    QApplication.sendEvent(view, QFocusEvent(QEvent.Type.FocusOut))
    assert not navigation.looking


def test_speed_keys_replace_scroll_and_trackpad_cannot_change_speed(navigation):
    view, speed = navigation.view, navigation.speed
    QTest.keyClick(view, Qt.Key.Key_Equal)
    assert navigation.speed > speed
    QTest.keyClick(view, Qt.Key.Key_Minus)
    assert navigation.speed == speed
    def scroll(pixels=QPoint(), phase=Qt.ScrollPhase.NoScrollPhase):
        QApplication.sendEvent(view, QWheelEvent(QPointF(30, 30), QPointF(30, 30), pixels, QPoint(0, 120),
                              Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, phase, False))
    scroll()
    assert navigation.speed == speed
    navigation.start_fly()
    scroll(QPoint(0, 80), Qt.ScrollPhase.ScrollUpdate)
    scroll(QPoint(0, 40), Qt.ScrollPhase.ScrollMomentum)
    assert navigation.speed == speed
    scroll()
    assert navigation.speed > speed
    field = QLineEdit(view)
    changed = navigation.speed
    QTest.keyClicks(field, "-+=")
    assert field.text() == "-+=" and navigation.speed == changed


def test_shortcut_override_does_not_change_input(navigation):
    QTest.keyPress(navigation.view, Qt.Key.Key_W)
    key(navigation.view, QEvent.Type.ShortcutOverride, Qt.Key.Key_S,
        modifiers=Qt.KeyboardModifier.ControlModifier)
    assert Qt.Key.Key_W in navigation.keys
    key(navigation.view, QEvent.Type.KeyPress, Qt.Key.Key_S,
        modifiers=Qt.KeyboardModifier.ControlModifier)
    assert not navigation.keys


def test_pick_uses_pointer_or_crosshair_without_exiting_flight_or_typing(navigation):
    view, samples = navigation.view, []
    navigation.sampled.connect(samples.append)
    navigation.hover_position = QPoint(40, 60)
    QTest.keyClick(view, Qt.Key.Key_I)
    assert samples == [QPoint(40, 60)]
    key(view, QEvent.Type.KeyPress, Qt.Key.Key_I, repeat=True)
    field = QLineEdit(view)
    QTest.keyClicks(field, "ii")
    assert field.text() == "ii" and len(samples) == 1
    navigation.start_fly()
    QTest.keyPress(view, Qt.Key.Key_W)
    QTest.mouseClick(view, Qt.MouseButton.MiddleButton, pos=QPoint(20, 20))
    key(view, QEvent.Type.KeyPress, ord("Ш"), text="ш")
    assert samples[-2:] == [view.rect().center()] * 2
    assert navigation.looking and Qt.Key.Key_W in navigation.keys
    navigation.placing = True
    QTest.keyClick(view, Qt.Key.Key_I)
    assert len(samples) == 3


def test_camera_corner_keys_preserve_flight_and_stay_local_to_viewport(navigation):
    corners = []
    navigation.corner_requested.connect(corners.append)
    navigation.start_fly()
    QTest.keyPress(navigation.view, Qt.Key.Key_W)
    QTest.keyClick(navigation.view, Qt.Key.Key_1)
    QTest.keyClick(navigation.view, Qt.Key.Key_2)
    key(navigation.view, QEvent.Type.KeyPress, Qt.Key.Key_2, repeat=True)
    assert corners == [0, 1] and navigation.looking and Qt.Key.Key_W in navigation.keys
    field = QLineEdit(navigation.view)
    QTest.keyClicks(field, "12")
    navigation.placing = True
    QTest.keyClick(navigation.view, Qt.Key.Key_1)
    assert field.text() == "12" and corners == [0, 1]


def test_captured_mouse_does_not_repeat_rotation_and_restores_cursor(navigation, monkeypatch):
    from structura_edit import mouse_look

    view = navigation.view
    pointer = {"position": QPoint(40, 60), "grabbed": False}
    monkeypatch.setattr(mouse_look, "QCursor", SimpleNamespace(
        pos=lambda: QPoint(pointer["position"]),
        setPos=lambda point: pointer.update(position=QPoint(point)),
    ))
    monkeypatch.setattr(view, "grabMouse", lambda: pointer.update(grabbed=True))
    monkeypatch.setattr(view, "releaseMouse", lambda: pointer.update(grabbed=False))
    monkeypatch.setattr(QWidget, "mouseGrabber", lambda: view if pointer["grabbed"] else None)
    monkeypatch.setattr(mouse_look, "relative_mouse", lambda view: None)
    navigation.mouse_look = mouse_look.MouseLook(view)
    QTest.mousePress(view, Qt.MouseButton.RightButton, pos=QPoint(40, 60))
    pointer["position"] += QPoint(30, -15)
    navigation.mouse_look.move(view.mapFromGlobal(pointer["position"]))
    navigation.tick(1 / 60)
    camera = navigation.camera.plotter.camera
    assert camera.direction[0] > 0 and camera.direction[1] > 0
    direction = camera.direction
    for _ in range(10):
        navigation.tick(1 / 60)
    assert camera.direction == direction
    QTest.mouseRelease(view, Qt.MouseButton.RightButton)
    assert pointer == {"position": QPoint(40, 60), "grabbed": False}
    assert not navigation.looking


def test_freelook_resumes_after_focus_returns_but_not_after_escape(navigation, monkeypatch):
    view = navigation.view
    focused = {"value": True}
    monkeypatch.setattr(view, "hasFocus", lambda: focused["value"])
    monkeypatch.setattr(view, "isVisible", lambda: True)
    monkeypatch.setattr(view, "isActiveWindow", lambda: focused["value"])
    navigation.start_fly()
    navigation.mouse_look.move(navigation.mouse_look.anchor + QPoint(60, -20))
    QTest.keyPress(view, Qt.Key.Key_W)
    focused["value"] = False
    QApplication.sendEvent(view, QFocusEvent(QEvent.Type.FocusOut))
    camera = navigation.camera.plotter.camera
    position, direction = camera.position, camera.direction
    for _ in range(10):
        navigation.tick(1 / 60)
    assert not navigation.looking and navigation.resume_look and not navigation.keys
    assert camera.position == position and camera.direction == direction
    focused["value"] = True
    navigation.tick(1 / 60)
    assert navigation.looking and not navigation.resume_look
    assert camera.position == position and camera.direction == direction
    navigation.mouse_look.move(navigation.mouse_look.anchor + QPoint(20, 10))
    navigation.tick(1 / 60)
    assert camera.position == position and camera.direction != direction
    QTest.keyClick(view, Qt.Key.Key_Escape)
    navigation.tick(1 / 60)
    assert not navigation.looking and not navigation.resume_look


def test_disabled_map_view_preserves_freelook_until_return(navigation, monkeypatch):
    view = navigation.view
    monkeypatch.setattr(view, "hasFocus", lambda: True)
    monkeypatch.setattr(view, "isVisible", lambda: True)
    monkeypatch.setattr(view, "isActiveWindow", lambda: True)
    navigation.start_fly()
    navigation.suspend()
    navigation.enabled = False
    for _ in range(10):
        navigation.tick(1 / 60)
    assert not navigation.looking and navigation.resume_look
    navigation.enabled = True
    navigation.tick(1 / 60)
    assert navigation.looking and not navigation.resume_look
