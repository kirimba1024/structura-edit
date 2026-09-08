from pathlib import Path
from time import perf_counter

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMainWindow, QMessageBox, QSizePolicy, QToolButton

from .camera import FreeCamera
from .appearance import apply_theme
from .jobs import PROTECTED_JOBS, Worker
from .menus import EditorMenus
from .navigation import CONTROLS, Navigation
from .scene import Scene
from .selection import RegionSelection
from .task_progress import TaskProgress
from .view_pipeline import ViewPipeline
from .workbench import EditorPanels, Workbench
from .world_ui import WorldController


class EditorWindow(QMainWindow):
    def __init__(self, path=None, *, assets=None, region=None, off_screen=False, cache_dir=None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, off_screen)
        self.setWindowTitle("Structura Edit")
        apply_theme(self)
        self.resize(1380, 880)
        self.setMinimumSize(850, 600)
        self.session = None
        self.pending = None
        self.assets = assets
        self._input_revision = 0
        self._job = None
        self.worker = Worker()
        self.selected = RegionSelection()
        self.workbench = Workbench(cache_dir=cache_dir)
        self.setCentralWidget(self.workbench)
        self.plotter = self.workbench.plotter
        self.minimap = self.workbench.minimap
        self.overlay = self.workbench.overlay
        self.scene = Scene(self.plotter)
        self.camera = FreeCamera(self.plotter, self.minimap.set_camera)
        self.navigation = Navigation(self.plotter, self.camera, capture_mouse=not off_screen)
        self.views = ViewPipeline(self.scene, self.camera, self.minimap, self._run, self._rendered,
                                  cache_path=self.minimap.cache.path)
        self.panels = EditorPanels(self)
        self.operation = self.panels.operation
        self.world = WorldController(self)
        self.menus = EditorMenus(self, {
            "open": self.open_dialog, "world": self.world.open_dialog, "save": self.save_dialog,
            "export": self.export_dialog, "close": self.close, "undo": self.undo, "redo": self.redo,
            "apply": self.apply_pending, "discard": self.discard_pending, "recipe": self.show_recipe,
            "all": self.select_all, "clear": self.clear_selection,
            "coordinates": lambda: self.panels.show("selection"), "materials": self.show_materials,
            "fit": self.fit_scene, "map": self.minimap.toggle_large, "goto": self.camera_dialog, "refresh": self.world.refresh,
            "fly": self.fly_camera,
            "history": lambda: self.panels.show("history"),
            "world_settings": self.world.settings, "entities": self._entities_changed,
            "resources": self.choose_assets, "operation": self.show_operation,
        })
        self.entities_action = self.menus.actions["entities"]
        self.status = QLabel("Open a schematic or world")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.statusBar().addWidget(self.status, 1)
        self.statusBar().setSizeGripEnabled(False)
        self.refresh_button = QToolButton()
        self.refresh_button.setDefaultAction(self.menus.actions["refresh"])
        self.refresh_button.setText("↻ Refresh · F5")
        self.refresh_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_button.setAutoRaise(True)
        self.statusBar().addPermanentWidget(self.refresh_button)
        self.controls = QLabel("WASD fly · RMB / Shift+` look · −/+ speed · M map")
        self.controls.setToolTip(CONTROLS)
        self.statusBar().addPermanentWidget(self.controls)
        self.progress = TaskProgress()
        self.progress.cancelled.connect(self.cancel_task)
        self.statusBar().addPermanentWidget(self.progress)
        self._connect_ui()
        self._last_tick = perf_counter()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self._sync()
        if path:
            QTimer.singleShot(0, lambda: self.open_path(path, region=region))

    def _connect_ui(self):
        self.workbench.open_requested.connect(self.open_dialog)
        self.workbench.world_requested.connect(self.world.open_dialog)
        self.workbench.demo_requested.connect(self.open_demo)
        self.navigation.selected.connect(self.scene_click)
        self.navigation.hovered.connect(self.scene_hover)
        self.navigation.extend_changed.connect(self.extend_selection)
        self.navigation.fit_requested.connect(self.fit_scene)
        self.navigation.apply_requested.connect(self.apply_pending)
        self.navigation.cancel_requested.connect(self.escape)
        self.navigation.speed_changed.connect(lambda speed: self.status.setText(f"Flight speed: {speed:.1f} blocks/s"))
        self.minimap.navigate.connect(self.move_camera)
        self.minimap.large_changed.connect(self._map_changed)
        self.minimap.expanded_changed.connect(lambda expanded: self.views.request_maps() if expanded else None)
        self.panels.selection.bounds_requested.connect(self.set_selection_bounds)
        self.panels.selection.all_requested.connect(self.select_all)
        self.panels.selection.clear_requested.connect(self.clear_selection)
        self.panels.materials.chosen.connect(self.fill_material)
        self.panels.history.requested.connect(self.seek_history)
        self.panels.recipe.preview_requested.connect(self.preview_recipe)
        self.panels.recipe.apply_requested.connect(self.apply_pending)
        self.panels.recipe.discard_requested.connect(self.discard_pending)
        self.operation.changed.connect(self._invalidate)
        self.operation.preview_requested.connect(self.preview_operation)
        self.operation.apply_requested.connect(self.apply_pending)
        self.operation.discard_requested.connect(self.discard_pending)

    def _sync(self):
        ready = self.session is not None and not self.worker.busy
        editable = ready and not self.session.readonly
        selected = self.selected.region is not None
        preview_ready = bool(self.pending) and self.views.ready
        self.menus.sync(self.session, busy=self.worker.busy, selected=selected,
                        preview=self.pending is not None, preview_ready=preview_ready, world_active=self.world.active)
        self.panels.selection.setEnabled(self.session is not None)
        self.operation.setEnabled(self.session is not None and not self.session.readonly)
        self.operation.preview.setEnabled(editable and selected)
        self.operation.apply.setEnabled(editable and preview_ready)
        self.operation.discard.setEnabled(self.pending is not None)
        self.panels.recipe.preview.setEnabled(editable and selected)
        self.panels.recipe.apply.setEnabled(editable and preview_ready)
        self.panels.recipe.discard.setEnabled(self.pending is not None)
        self.refresh_button.setVisible(self.world.active)
        self.panels.history.set_session(self.session, busy=self.worker.busy)
        if self.session:
            name = self.session.path.name if self.session.path else "Untitled"
            self.setWindowTitle(f"{'● ' if self.session.dirty else ''}{name} — Structura Edit")

    def _map_changed(self, large):
        self.navigation.stop()
        self.navigation.enabled = self.session is not None and not large

    def fly_camera(self):
        self.minimap.set_large(False)
        self.navigation.start_fly()

    def _run(self, kind, callback, **args):
        if self.worker.busy:
            return False
        self._job = kind, callback
        self.worker.submit(kind, **args)
        self.progress.start(kind.capitalize(), cancellable=kind not in PROTECTED_JOBS)
        if kind != "map":
            messages = {"open": "Opening…", "world": "Loading world…", "render": "Building preview…",
                        "save": "Saving…", "recipe": "Running recipe…", "operation": "Preparing change…", "export": "Exporting…",
                        "apply": "Applying…", "history": "Restoring history…"}
            self.status.setText(messages[kind])
        self._sync()
        return True

    def _tick(self):
        progress = self.worker.progress()
        if progress:
            self.progress.set_progress(*progress)
        result = self.worker.poll() if self.worker.busy else None
        if result is not None:
            kind, callback = self._job
            self._job = None
            if result[0]:
                try:
                    callback(result[1])
                except Exception as error:
                    self._error(str(error))
            else:
                self._error(result[1])
            self._sync()
        if not self.worker.busy:
            self.world.flush()
        if not self.worker.busy:
            self.views.flush()
        if not self.worker.busy:
            self.progress.finish()
        now = perf_counter()
        self.navigation.tick(now - self._last_tick)
        self.overlay.set_looking(self.navigation.looking)
        self._last_tick = now

    def _error(self, message):
        self.status.setText(message.splitlines()[0] if message else "Operation failed")
        self.panels.recipe.output.setPlainText(message)
        self._sync()

    def cancel_task(self):
        if self._job and self._job[0] in PROTECTED_JOBS:
            return
        self.worker.close()
        self._job = None
        self.world.queued = None
        self.views.reset()
        self.pending = None
        self._input_revision += 1
        if self.session:
            self.render_scene()
        self.status.setText("Task cancelled")
        self._sync()

    def _confirm_discard(self):
        if not self.session or not self.session.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved changes", "Discard unsaved changes?",
                                      QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open structure or level.dat", "", "Minecraft (*.nbt *.snbt *.schem *.litematic *.mcstructure level.dat)")
        if path:
            self.open_path(path)

    def open_demo(self):
        from importlib.resources import files

        self.open_path(str(files("structura_render").joinpath("data/examples/demo.nbt")))

    def open_path(self, path, region=None):
        path = Path(path).expanduser()
        if path.is_dir() or path.name == "level.dat":
            self.world.open(path if path.is_dir() else path.parent)
            return
        if not self.worker.busy and self._confirm_discard():
            self.navigation.stop()
            self._run("open", self._opened, path=str(path), region=region)

    def _opened(self, session, *, rendered=None, fit=True, preserve_focus=False):
        if not session.readonly:
            session.history.prepare()
        self.session = session
        self.pending = None
        self._input_revision += 1
        self.views.reset()
        self.scene.clear()
        self.selected.reset(session.size)
        self.panels.selection.set_document(session.size)
        if not preserve_focus:
            self.navigation.stop()
            self.panels.dismiss()
        self.workbench.setCurrentIndex(1)
        self.minimap.set_document(session)
        self.navigation.enabled = not self.minimap.large
        self._selection_changed()
        self._refresh_palette()
        self.views.request(session, None, self.assets, self.entities_action.isChecked(), fit=fit, data=rendered)
        if rendered is None:
            self.world.queued = None
        if not preserve_focus:
            (self.minimap if self.minimap.large else self.plotter).setFocus()
        self._sync()

    def selection(self):
        if self.selected.region is None:
            raise ValueError("Click a block to select it; Shift+click another block to extend the region")
        return self.selected.region

    def set_selection_bounds(self, lower, upper):
        if self.session is None:
            return
        try:
            self.selected.set_bounds(lower, upper)
            self._selection_changed()
        except ValueError as error:
            self.status.setText(str(error))

    def select_all(self):
        if self.session:
            self.selected.select_all()
            self._selection_changed()

    def clear_selection(self):
        self.selected.clear()
        self._selection_changed()

    def _selection_changed(self):
        self._invalidate()
        selection = self.selected.region
        self._show_selection(selection)
        self.panels.selection.set_selection(selection)
        self.operation.info.setText(self.panels.selection.info.text())
        self.status.setText(self.panels.selection.info.text())
        self._sync()

    def scene_click(self, point, extend=False):
        if not self.session or self.pending is not None or self.scene.display_revision != self.session.revision:
            return
        hit = self.scene.hit_at(self.session, point)
        if hit is not None:
            self.selected.select_block(hit.position, extend=extend)
            self._selection_changed()

    def extend_selection(self, enabled):
        self.selected.set_extending(enabled)
        self._show_selection(self.selected.region)

    def scene_hover(self, point):
        if point is None or not self.session or self.pending is not None or self.scene.display_revision != self.session.revision:
            self.overlay.set_hover(None)
            if self.selected.preview is not None:
                self.selected.preview = None
                self._show_selection(self.selected.region)
            return
        hit = self.scene.hit_at(self.session, point)
        self.overlay.set_hover(hit.position if hit is not None else None)
        if self.selected.extending:
            previous = self.selected.preview
            if hit is None:
                self.selected.preview = None
            else:
                self.selected.hover_block(hit.position)
            if self.selected.preview != previous:
                self._show_selection(self.selected.preview or self.selected.region)

    def _show_selection(self, selection):
        self.overlay.set_selection(self.selected.region, self.selected.preview)
        self.overlay.set_hover(None)
        self.minimap.set_selection((selection.lower, selection.upper) if selection else None)

    def show_operation(self, mode):
        if not self.session or self.session.readonly or self.selected.region is None:
            return
        self.navigation.stop()
        self.operation.mode.setCurrentText(mode)
        self.panels.show("operation")
        self._sync()

    def show_materials(self):
        if self.session:
            self.panels.materials.set_counts(self.session.palette_counts(self.selected.region))
            self.panels.show("materials")

    def fill_material(self, state):
        self.panels.docks["materials"].hide()
        self.show_operation("Fill")
        self.operation.fields["target"].setText(state)

    def _refresh_palette(self):
        self.operation.set_materials(self.session.palette_counts())

    def _invalidate(self):
        if self._job and self._job[0] == "apply":
            return
        self._input_revision += 1
        if self.pending is not None:
            self.pending = None
            self.render_scene()
        self._sync()

    def preview_operation(self):
        self._prepare_change("operation", mode=self.operation.current, values=self.operation.values())

    def show_recipe(self):
        self.navigation.stop()
        self.panels.show("recipe")

    def preview_recipe(self):
        self._prepare_change("recipe", code=self.panels.recipe.code.toPlainText())

    def _prepare_change(self, kind, **args):
        if not self.session or self.session.readonly or self.worker.busy:
            return
        try:
            selection = self.selection()
        except ValueError as error:
            self.status.setText(str(error))
            return
        revision = self._input_revision
        def received(result):
            if revision != self._input_revision:
                return
            if kind == "recipe":
                change, output = result
                self.panels.recipe.output.setPlainText(output)
            else:
                change = result
            self.session._check_change(change)
            self.pending = change
            self.operation.info.setText(f"Preview · {len(change):,} changed cells")
            self.render_scene()
        self._run(kind, received, session=self.session.fork(), selection=selection, **args)

    def render_scene(self, fit=False):
        if self.session:
            self.views.request(self.session, self.pending, self.assets, self.entities_action.isChecked(), fit=fit)
            self._sync()

    def _rendered(self, data):
        self.status.setText("Preview · Enter to apply · Escape to discard" if self.pending is not None else
                            "Minecraft textures" if data["textured"] else "Block colours · View → Minecraft resources for textures")
        if data["warnings"]:
            self.panels.recipe.output.setPlainText("\n".join(data["warnings"]))
        self._sync()

    def _entities_changed(self):
        if self.world.active:
            self.world.request()
        else:
            self.render_scene()

    def move_camera(self, position):
        self.camera.move_to(position)
        (self.minimap if self.minimap.large else self.plotter).setFocus()

    def camera_dialog(self):
        if self.session:
            from .camera_dialog import go_to_coordinates

            self.navigation.stop()
            go_to_coordinates(self, self.plotter.camera.position, self.session.origin, self.move_camera)

    def fit_scene(self):
        if self.session:
            self.camera.frame(self.session.size)

    def apply_pending(self):
        if not self.pending or self.worker.busy or not self.views.ready:
            return
        destination = None
        if self.pending.label == "Move blocks" and self.operation.current == "Move blocks":
            offset = self.operation.values()["offset"]
            destination = tuple(tuple(p + d for p, d in zip(bound, offset))
                                for bound in (self.selection().lower, self.selection().upper))
        count = len(self.pending)
        request = self.views.current
        self._run("apply", lambda session: self._applied(session, count, destination, request),
                  session=self.session, change=self.pending)

    def _applied(self, session, count, destination, request):
        self.session = session
        self.pending = None
        if self.views.current is request:
            self.views.accept(self.session)
        else:
            self.render_scene()
        self.scene.display_revision = self.session.revision
        if destination is not None:
            self.set_selection_bounds(*destination)
        self.panels.dismiss()
        self._refresh_palette()
        (self.minimap if self.minimap.large else self.plotter).setFocus()
        self.status.setText(f"Applied {count:,} cells · Undo is available")
        self._sync()

    def discard_pending(self):
        if self._job and self._job[0] == "apply":
            return
        self._invalidate()
        self.operation.info.setText("Preview discarded")

    def escape(self):
        if self.minimap.large:
            self.minimap.set_large(False)
            return
        if self.pending is not None:
            self.discard_pending()
        else:
            self.clear_selection()
        self.panels.dismiss()
        self.plotter.setFocus()

    def undo(self):
        self._history("undo")

    def redo(self):
        self._history("redo")

    def _history(self, direction):
        if self.worker.busy or not self.session:
            return
        if self.pending is not None:
            self.discard_pending()
            return
        self.seek_history(self.session.history.cursor + (-1 if direction == "undo" else 1))

    def seek_history(self, index):
        if self.worker.busy or not self.session or self.pending is not None:
            return
        if not 0 <= index <= len(self.session.history.entries) or index == self.session.history.cursor:
            return
        self._input_revision += 1
        self._run("history", self._history_changed, session=self.session, index=index)

    def _history_changed(self, session):
        self.session = session
        self._refresh_palette()
        self.render_scene()

    def choose_assets(self):
        if self.worker.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose Minecraft client resources", "", "Minecraft client (*.jar)")
        if path:
            self.assets = path
            self.render_scene()

    def export_dialog(self):
        if not self.session or self.worker.busy or self.pending is not None or self.selected.region is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export selection as Structure NBT", "selection.nbt",
                                             "Structure NBT (*.nbt);;Text NBT (*.snbt)")
        if path:
            self._run("export", lambda result: self.status.setText(f"Exported {result}"),
                      session=self.session.fork(), selection=self.selection(), path=path)

    def save_dialog(self):
        if not self.session or self.worker.busy or self.pending is not None:
            return
        current = self.session.path or Path("structure.nbt")
        proposal = str(current.with_name(f"{current.stem}-edited{current.suffix}"))
        filters = "Sponge (*.schem)" if current.suffix == ".schem" else "Structure NBT (*.nbt);;Text NBT (*.snbt)"
        path, _ = QFileDialog.getSaveFileName(self, "Save edited schematic", proposal, filters)
        if path:
            self.save_path(path)

    def save_path(self, path):
        if self.session and not self.session.readonly and self.pending is None:
            self._run("save", self._saved, session=self.session, path=str(path))

    def _saved(self, session):
        self.session = session
        self.status.setText(f"Saved {session.path.name}")
        self._sync()

    def closeEvent(self, event):
        if self._job and self._job[0] in PROTECTED_JOBS:
            event.ignore()
            return
        if not self._confirm_discard():
            event.ignore()
            return
        self.timer.stop()
        self.navigation.close()
        self.worker.close()
        self.minimap.cache.close()
        self.plotter.close()
        event.accept()


def launch(path=None, *, assets=None, region=None, world=None):
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication([])
    app.setApplicationName("Structura Edit")
    window = EditorWindow(path, assets=assets, region=region)
    window.show()
    if world is not None:
        QTimer.singleShot(0, lambda: window.world.open(world))
    if owns_app:
        return app.exec()
    return window
