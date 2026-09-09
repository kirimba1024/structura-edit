from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QCursor, QInputDevice
from PySide6.QtWidgets import QApplication

from .mouse_look import MouseLook
from .navigation_keys import COMMAND_MODIFIERS, MOVEMENT, SPEED_KEYS, HeldKeys, control_key, fly_shortcut


DEFAULT_SPEED = 24.0
MIN_SPEED = 0.5
MAX_SPEED = 256.0
BOOST = 4

CONTROLS = ("Move mouse / one finger: look after opening · Escape: release cursor · Click: select at crosshair\n"
            "Hold WASD / arrows: fly · E / Space: up · Q: down · Shift: faster\n"
            "Shift+`: resume freelook · Hold RMB: temporary look\n"
            "− / +: speed · Mouse wheel while looking: speed · Shift+click: region\n"
            "I / middle click: pick material · 1 / 2: corner A / B at camera\n"
            "F: frame scene · M: map · Ctrl+Shift+P: find command\n"
            "Enter: apply preview · Escape: cancel")


class Navigation(QObject):
    selected = Signal(object, bool)
    hovered = Signal(object)
    sampled = Signal(object)
    corner_requested = Signal(int)
    extend_changed = Signal(bool)
    fit_requested = Signal()
    apply_requested = Signal()
    cancel_requested = Signal()
    speed_changed = Signal(float)
    nudge_requested = Signal(object)

    def __init__(self, view, camera, *, capture_mouse=True):
        super().__init__(view)
        self.view = view
        self.camera = camera
        self.enabled = False
        self.placing = False
        self.held = HeldKeys()
        self.mouse_look = MouseLook(view, capture=capture_mouse)
        self.resume_look = False
        self.press_position = None
        self.hover_position = None
        self.hover_dirty = False
        self.hover_elapsed = 0.0
        self.speed = DEFAULT_SPEED
        QApplication.instance().installEventFilter(self)

    @property
    def keys(self):
        return self.held.keys

    @property
    def looking(self):
        return self.mouse_look.active

    @property
    def flight_speed(self):
        return self.speed * (BOOST if Qt.Key.Key_Shift in self.keys else 1)

    def change_speed(self, factor):
        self.speed = min(MAX_SPEED, max(MIN_SPEED, self.speed * factor))
        self.speed_changed.emit(self.speed)

    def start_fly(self):
        if self.enabled:
            if self.mouse_look.capture and (not self.view.isVisible() or not self.view.window().isActiveWindow()):
                self.suspend()
                self.resume_look = True
                return
            self.stop()
            self.view.setFocus()
            self.mouse_look.start(self.view.mapFromGlobal(QCursor.pos()), latched=True)

    def stop(self, *, restore_cursor=True):
        self.resume_look = False
        extending = Qt.Key.Key_Shift in self.keys
        self.held.clear()
        if extending:
            self.extend_changed.emit(False)
        self.hover_position = None
        self.hover_dirty = False
        self.press_position = None
        self.mouse_look.stop(restore=restore_cursor)
        self.hovered.emit(None)

    def suspend(self):
        resume = self.resume_look or self.mouse_look.latched
        self.stop(restore_cursor=False)
        self.resume_look = resume

    def release_key(self, event):
        extending = Qt.Key.Key_Shift in self.keys
        self.held.release(event)
        if extending and Qt.Key.Key_Shift not in self.keys:
            self.extend_changed.emit(False)

    def keyboard(self, event):
        kind = event.type()
        key = control_key(event)
        if kind == QEvent.Type.KeyRelease:
            self.release_key(event)
            return key in MOVEMENT or key == Qt.Key.Key_Shift
        if event.modifiers() & COMMAND_MODIFIERS:
            if kind == QEvent.Type.KeyPress:
                self.stop()
            return False
        arrows = {Qt.Key.Key_Left: (-1, 0, 0), Qt.Key.Key_Right: (1, 0, 0),
                  Qt.Key.Key_Up: (0, 0, -1), Qt.Key.Key_Down: (0, 0, 1)}
        if self.placing and key in arrows:
            event.accept()
            if kind == QEvent.Type.KeyPress:
                offset = arrows[key]
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and offset[2]:
                    offset = (0, -offset[2], 0)
                self.nudge_requested.emit(offset)
            return True
        handled = key in MOVEMENT or key in SPEED_KEYS or fly_shortcut(event) or key in (Qt.Key.Key_Shift, Qt.Key.Key_F, Qt.Key.Key_I, Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_Escape,
                                            Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if not handled:
            return False
        event.accept()
        if kind == QEvent.Type.ShortcutOverride or event.isAutoRepeat():
            return True
        if fly_shortcut(event):
            if self.looking:
                self.stop()
            else:
                self.start_fly()
        elif key in SPEED_KEYS:
            self.change_speed(2 ** SPEED_KEYS[key])
        elif key in MOVEMENT or key == Qt.Key.Key_Shift:
            extending = Qt.Key.Key_Shift in self.keys
            self.held.press(event)
            if key == Qt.Key.Key_Shift and not extending:
                self.extend_changed.emit(not self.looking and not self.placing)
                self.hover_position = self.view.mapFromGlobal(QCursor.pos())
                self.hover_dirty = True
        elif key == Qt.Key.Key_F:
            self.fit_requested.emit()
        elif key == Qt.Key.Key_I:
            self.sample()
        elif key in (Qt.Key.Key_1, Qt.Key.Key_2):
            if not self.placing:
                self.corner_requested.emit(key - Qt.Key.Key_1)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.apply_requested.emit()
        elif key == Qt.Key.Key_Escape:
            looking = self.looking
            self.stop()
            if not looking:
                self.cancel_requested.emit()
        return True

    def sample(self, point=None):
        if self.placing:
            return
        if self.looking:
            point = self.view.rect().center()
        elif point is None:
            point = self.hover_position
        if point is not None and self.view.rect().contains(point):
            self.sampled.emit(point)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind == QEvent.Type.ApplicationDeactivate or (
                kind in (QEvent.Type.WindowDeactivate, QEvent.Type.WindowBlocked)
                and watched is self.view.window()):
            self.suspend()
        if watched is not self.view:
            if kind == QEvent.Type.KeyRelease:
                self.release_key(event)
            if (kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.RightButton
                    and not self.mouse_look.latched):
                self.mouse_look.stop()
            return False
        if kind in (QEvent.Type.FocusOut, QEvent.Type.Hide):
            self.suspend()
        if kind == QEvent.Type.Leave and not self.looking:
            self.hover_position = None
            self.hovered.emit(None)
        if not self.enabled or QApplication.activePopupWidget() is not None:
            self.suspend()
            return False
        if kind in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return self.keyboard(event)
        if kind == QEvent.Type.ContextMenu:
            return True
        if kind == QEvent.Type.Wheel:
            trackpad = (event.device().type() == QInputDevice.DeviceType.TouchPad
                        or not event.pixelDelta().isNull())
            if self.looking and not trackpad and event.phase() != Qt.ScrollPhase.ScrollMomentum:
                self.change_speed(1.2 ** (event.angleDelta().y() / 120))
            return True
        if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            if event.button() == Qt.MouseButton.MiddleButton:
                self.view.setFocus()
                self.sample(event.position().toPoint())
                return True
            if self.mouse_look.latched:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.selected.emit(self.view.rect().center(), bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                return True
            self.view.setFocus()
            if event.button() == Qt.MouseButton.RightButton:
                self.press_position = None
                self.extend_changed.emit(False)
                self.mouse_look.start(event.position().toPoint())
            elif event.button() == Qt.MouseButton.LeftButton and not self.looking:
                self.press_position = event.position().toPoint()
            return True
        if kind == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.RightButton and not self.mouse_look.latched:
                delta = self.mouse_look.sample()
                if not delta.isNull():
                    self.camera.look(delta.x(), delta.y())
                self.mouse_look.stop()
            elif event.button() == Qt.MouseButton.LeftButton:
                point = event.position().toPoint()
                if self.press_position is not None and (
                        point - self.press_position).manhattanLength() < QApplication.startDragDistance():
                    self.selected.emit(point, bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
                self.press_position = None
            return True
        if kind == QEvent.Type.MouseMove:
            self.hover_position = event.position().toPoint()
            self.hover_dirty = True
            self.mouse_look.move(event.position())
            return True
        return False

    def tick(self, elapsed):
        if not self.enabled or QApplication.activePopupWidget() is not None or QApplication.activeModalWidget() is not None:
            self.suspend()
            return
        if self.resume_look and self.view.hasFocus() and self.view.isVisible() and self.view.window().isActiveWindow():
            self.start_fly()
        was_latched = self.mouse_look.latched
        delta = self.mouse_look.sample()
        if was_latched and not self.looking:
            self.resume_look = True
        if not delta.isNull():
            self.camera.look(delta.x(), delta.y())
        axes = self.held.axes
        self.camera.step(axes, self.flight_speed, min(max(elapsed, 0), 0.1))
        self.hover_dirty = self.hover_dirty or self.camera.needs_render
        self.camera.render()
        self.hover_elapsed += elapsed
        point = self.view.rect().center() if self.looking else self.hover_position
        if self.hover_elapsed >= 1 / 30 and self.hover_dirty and point is not None:
            self.hovered.emit(point)
            self.hover_dirty = False
            self.hover_elapsed = 0.0

    def close(self):
        self.stop()
        self.mouse_look.close()
        QApplication.instance().removeEventFilter(self)
