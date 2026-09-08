from PySide6.QtCore import QObject, Signal

from .placement import Placement
from .placement_bar import PlacementBar
from .placement_view import PlacementView


class PlacementController(QObject):
    changed = Signal()
    message = Signal(str)
    committed = Signal(object, object, object, int)
    cancel_requested = Signal()

    def __init__(self, scene, navigation, submit):
        super().__init__(navigation)
        self.scene, self.navigation, self.submit = scene, navigation, submit
        self.bar = PlacementBar(scene.plotter)
        self.view = PlacementView(scene.plotter)
        self.clipboard = None
        self.model = None
        self.preparing = False
        self.committing = False
        self.session = self.selection = self.assets = None
        self.busy = False
        self.available = False
        self.visible = False
        self.token = 0
        self.bar.position_changed.connect(self.set_position)
        self.bar.follow_changed.connect(self.set_following)
        self.bar.air_changed.connect(self.set_air)
        self.bar.cancel_requested.connect(self.cancel_requested)
        self.bar.transform_requested.connect(self.transform)
        navigation.nudge_requested.connect(self.nudge)

    @property
    def active(self):
        return self.model is not None or self.preparing

    def set_context(self, session, selection, assets, *, busy, available, visible):
        self.session, self.selection, self.assets = session, selection, assets
        self.busy, self.available, self.visible = busy, available, visible
        self.navigation.placing = self.model is not None
        self.bar.update_state(self.model, session, selection, busy=busy, visible=visible)
        self.bar.cancel.setEnabled(not self.committing)

    def start(self, mode, *, path=None):
        if not self.available or self.active:
            return
        if mode != "copy" and self.session.readonly:
            return
        if mode == "paste" and self.clipboard is None:
            return
        if mode in ("copy", "take", "duplicate") and self.selection is None:
            return
        self.token += 1
        token = self.token
        self.preparing = mode != "copy"
        initial = self.selection.lower if self.selection else (0, 0, 0)
        self.navigation.stop()
        self.scene.plotter.setFocus()
        self.submit("clipboard", lambda result: self._loaded(token, mode, initial, result),
                    session=self.session.fork(), selection=self.selection, assets=self.assets, path=path,
                    clipboard=self.clipboard if mode == "paste" else None,
                    render=mode != "copy", scene_bytes=sum(self.scene.section_bytes.values()))
        self.changed.emit()

    def _loaded(self, token, mode, initial, result):
        if token != self.token:
            return
        clipboard, geometry = result
        self.clipboard = clipboard
        self.preparing = False
        if mode == "copy":
            self.message.emit(f"Copied {'×'.join(map(str, clipboard.size))} · Paste is ready")
        else:
            self.view.load(geometry)
            self.model = Placement(clipboard, initial, take=mode == "take")
            self.navigation.placing = True
            self.refresh()
            self.message.emit("Placement ready · click to pin · Enter applies locally")
        self.changed.emit()

    def refresh(self):
        if self.model is not None:
            self.view.show(self.model, self.model.reason(self.session))
        self.bar.update_state(self.model, self.session, self.selection, busy=self.busy, visible=self.visible)

    def hover(self, point):
        if self.model is not None and not self.busy and point is not None and not self.navigation.looking:
            ray = self.scene.ray_at(point)
            if self.model.follow(*ray, self.scene.hit_at(self.session, point)):
                self.refresh()

    def pin(self, point):
        if self.model is None or self.busy:
            return
        self.hover(point)
        self.set_following(False)

    def set_position(self, position):
        if self.model is not None and not self.busy:
            self.model.set_position(position)
            self.refresh()

    def nudge(self, offset):
        if self.model is not None and not self.busy:
            self.model.nudge(offset)
            self.refresh()

    def set_following(self, following):
        if self.model is not None and not self.busy:
            self.model.following = following
            self.refresh()

    def set_air(self, include_air):
        if self.model is not None and not self.busy:
            self.model.include_air = include_air
            self.refresh()

    def transform(self, turns, flip):
        if self.model is None or self.busy:
            return
        token = self.token
        if self.submit("clipboard", lambda result: self._transformed(token, result), session=None,
                       clipboard=self.model.clipboard, transform=dict(turns=turns, flip=flip), assets=self.assets,
                       scene_bytes=sum(self.scene.section_bytes.values())):
            self.message.emit("Rotating preview…" if turns else "Mirroring preview…")

    def _transformed(self, token, result):
        if token != self.token or self.model is None:
            return
        clipboard, geometry = result
        self.view.load(geometry)
        self.clipboard = clipboard
        self.model.set_clipboard(clipboard)
        self.refresh()
        self.changed.emit()

    def apply(self, *, include_entities):
        if self.model is None or self.busy:
            return
        reason = self.model.reason(self.session)
        if reason:
            self.message.emit(reason)
            return
        self.model.following = False
        token = self.token
        self.submit("placement", lambda result: self._prepared(token, result), session=self.session,
                    placement=self.model, assets=self.assets, include_entities=include_entities,
                    section_bytes=self.scene.section_bytes.copy())

    def _prepared(self, token, result):
        if token != self.token or self.model is None:
            return
        change, data = result
        bounds = self.model.bounds
        self.committing = True
        self.submit("apply", lambda session: self._applied(session, data, bounds, len(change)),
                    session=self.session, change=change)

    def _applied(self, session, data, bounds, count):
        self.committing = False
        self.model = None
        self.view.clear()
        self.navigation.placing = False
        self.committed.emit(session, data, bounds, count)
        self.changed.emit()

    def failed(self):
        self.preparing = self.committing = False

    def cancel(self):
        if self.committing:
            return
        active = self.active
        self.token += 1
        self.model = None
        self.preparing = False
        self.navigation.placing = False
        self.view.clear()
        if active:
            self.message.emit("Placement cancelled")
        self.changed.emit()
