from time import perf_counter

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QToolButton

from .camera import FreeCamera
from .materials_ui import MaterialController
from .controls import CellLabel
from .appearance import CONTROL_HEIGHT, GRID
from .theme import apply_theme
from .jobs import Worker
from .task_runner import TaskRunner
from .height_slice_ui import HeightSliceController
from .height_slice import HeightSlice
from .object_ui import ObjectController
from .menus import EditorMenus
from .navigation import CONTROLS, Navigation
from .placement_ui import PlacementController
from .placement_review import PlacementReview
from .repeat_ui import RepeatController
from .scene import Scene
from .scene_guides import SceneGuides
from .editor_document import EditorDocument
from .edit_workflow import EditWorkflow
from .selection_actions import SelectionActions
from .source_ui import SourceController
from .task_progress import TaskProgress
from .view_pipeline import ViewPipeline
from .workbench import EditorPanels, Workbench
from .world_ui import WorldController


class EditorWindow(QMainWindow):
    def __init__(self, path=None, *, assets=None, region=None, palette_index=0, source_data_version=None,
                 off_screen=False, cache_dir=None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, off_screen)
        self.setWindowTitle("Structura Edit")
        apply_theme(self)
        self.resize(1380, 880)
        self.setMinimumSize(1104, 600)
        self.document = EditorDocument()
        self.assets = assets
        self.tasks = TaskRunner(Worker(), started=self._task_started, finished=self._sync, failed=self._task_failed,
                                progress=lambda *update: self.progress.set_progress(*update))
        self.edits = EditWorkflow(self.document, self.tasks, previewed=self._previewed, updated=self._document_updated)
        self.workbench = Workbench(cache_dir=cache_dir)
        self.setCentralWidget(self.workbench)
        self.plotter = self.workbench.plotter
        self.minimap = self.workbench.minimap
        self.overlay = self.workbench.overlay
        self.scene = Scene(self.plotter)
        self.guides = SceneGuides(self.plotter)
        self.camera = FreeCamera(self.plotter, self.minimap.set_camera)
        self.navigation = Navigation(self.plotter, self.camera, capture_mouse=not off_screen)
        self.views = ViewPipeline(self.scene, self.camera, self.minimap, self.tasks.submit, self._rendered,
                                  cache_path=self.minimap.cache.path,
                                  map_updates=self.minimap.maps,
                                  retained_geometry=lambda: self.placement.view.geometry_bytes)
        self.panels = EditorPanels(self)
        self.selection_actions = SelectionActions(self.document.selected, self.panels.selection, self.plotter.camera,
                                                  available=lambda: self.document.session is not None and not self.placement.active
                                                  and not self.repeat.active and not self.tasks.busy)
        self.operation = self.panels.operation
        self.placement = PlacementController(self.scene, self.navigation, self.tasks.submit, self.edits.commit)
        self.placement_review = PlacementReview(self.placement, self.document, self.edits, self.tasks, self.views)
        self.repeat = RepeatController(self.plotter, self.document, self.edits, self.tasks)
        self.placement.bar.destination.materials = self.operation.materials
        self.repeat.bar.destination.materials = self.operation.materials
        self.objects = ObjectController(self.document, self.tasks, self.edits, self.scene, self.navigation,
                                        self.selection_actions, available=self._objects_available)
        self.slicing = HeightSliceController(self.document, self.views, self.navigation)
        self.world = WorldController(self.document, self.tasks, self.camera, self.selection_actions,
                                      options=lambda: dict(assets=self.assets, height=self.slicing.value,
                                                           include_entities=self.entities_action.isChecked()),
                                      available=lambda: not self.placement.active and not self.repeat.active, opened=self._opened)
        self.sources = SourceController(self, self.document, self.tasks, self.edits, self.world, self.placement,
                                         opened=self._opened, saved=self._saved)
        self.materials = MaterialController(self.panels, self.navigation, show_operation=self.show_operation,
                                            available=lambda: self.document.session is not None and not self.tasks.busy
                                            and not self.placement.active and not self.repeat.active)
        self._create_menus()
        self._create_status_bar()
        self._connect_ui()
        self._last_tick = perf_counter()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)
        self._sync()
        if path:
            QTimer.singleShot(0, lambda: self.sources.open_path(path, region=region, palette_index=palette_index,
                                                       source_data_version=source_data_version))

    def _objects_available(self):
        return (self.document.session is not None and not self.tasks.busy and self.document.pending is None
                and not self.placement.active and not self.repeat.active)

    def _create_menus(self):
        self.menus = EditorMenus(self, {
            "open": self.sources.open_dialog, "save": self.sources.save_dialog,
            "export": self.sources.export_dialog, "close": self.close, "undo": self.undo, "redo": self.redo,
            "apply": self.apply_pending, "discard": self.discard_pending, "recipe": self.show_recipe,
            "all": self.selection_actions.select_all, "clear": self.selection_actions.clear,
            "coordinates": lambda: self.panels.show("selection"), "materials": lambda: self.materials.show(),
            "fit": self.fit_scene, "map": self.minimap.toggle_large, "goto": self.camera_dialog, "refresh": self.world.refresh,
            "fly": self.fly_camera,
            "height": self.slicing.show,
            "history": lambda: self.panels.show("history"),
            "world_settings": self.world.settings, "entities": self._entities_changed,
            "resources": self.choose_assets, "operation": self.show_operation,
            "copy": lambda: self.placement.start("copy"), "take": lambda: self.placement.start("take"),
            "paste": lambda: self.placement.start("paste"), "duplicate": lambda: self.placement.start("duplicate"),
            "repeat": self.repeat.start,
            "bounds": self._guides_changed, "chunks": self._guides_changed,
            "import": self.sources.import_dialog, "inspect": self.objects.inspect, "entity_all": self.objects.select_region,
            "find_objects": self.objects.finder.show,
            "entity_move": lambda: self.objects.transform("Move"),
            "entity_duplicate": lambda: self.objects.transform("Duplicate"),
            "entity_rotate": lambda: self.objects.transform("Rotate"),
            "entity_delete": lambda: self.objects.transform("Delete"),
        })
        self.placement.bar.bind_actions(self.menus.actions)
        self.entities_action = self.menus.actions["entities"]

    def _create_status_bar(self):
        self.statusBar().addPermanentWidget(self.objects.inspect_button)
        self.statusBar().addPermanentWidget(self.slicing.button)
        self.status = CellLabel("Open a schematic or world")
        self.statusBar().addWidget(self.status, 1)
        self.error_message = ""
        self.error_button = QToolButton()
        self.error_button.setText("Error…")
        self.error_button.setToolTip("View and copy the full error")
        self.error_button.clicked.connect(self.show_error)
        self.statusBar().addWidget(self.error_button)
        self.error_button.hide()
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().setFixedHeight(CONTROL_HEIGHT + GRID)
        self.refresh_button = QToolButton()
        self.refresh_button.setDefaultAction(self.menus.actions["refresh"])
        self.refresh_button.setText("Refresh · F5")
        self.refresh_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_button.setAutoRaise(True)
        self.statusBar().addPermanentWidget(self.refresh_button)
        self.save_button = QToolButton()
        self.save_button.setDefaultAction(self.menus.actions["save"])
        self.save_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.statusBar().addPermanentWidget(self.save_button)
        self.controls = CellLabel("Mouse look · Esc cursor · M map", width=GRID * 72)
        self.controls.setToolTip(CONTROLS)
        self.statusBar().addPermanentWidget(self.controls)
        self.progress = TaskProgress()
        self.progress.cancelled.connect(self.cancel_task)
        self.statusBar().addWidget(self.progress)

    def _connect_ui(self):
        self.sources.opening.connect(self.navigation.stop)
        self.sources.message.connect(self.status.setText)
        self.world.opening.connect(self.navigation.stop)
        self.world.open_requested.connect(self.sources.open_dialog)
        self.world.message.connect(self.status.setText)
        self.objects.message.connect(self.status.setText)
        self.objects.changed.connect(self._sync)
        self.objects.applied.connect(self.render_scene)
        self.objects.reveal_requested.connect(self.slicing.reveal)
        self.objects.finder.opening.connect(self.navigation.stop)
        self.objects.finder.opening.connect(lambda: self.minimap.set_large(False))
        self.objects.finder.opening.connect(self.panels.dismiss)
        self.slicing.changed.connect(lambda: self.overlay.set_hover(None))
        self.slicing.changed.connect(self.render_scene)
        self.workbench.open_requested.connect(self.sources.open_dialog)
        self.workbench.demo_requested.connect(self.sources.open_demo)
        self.navigation.selected.connect(self.scene_click)
        self.navigation.hovered.connect(self.scene_hover)
        self.navigation.sampled.connect(self.sample_material)
        self.navigation.corner_requested.connect(self.selection_actions.at_camera)
        self.navigation.extend_changed.connect(self.extend_selection)
        self.navigation.fit_requested.connect(self.fit_scene)
        self.navigation.apply_requested.connect(self.apply_pending)
        self.navigation.cancel_requested.connect(self.escape)
        self.navigation.speed_changed.connect(lambda speed: self.status.setText(f"Flight speed: {speed:.1f} blocks/s"))
        self.minimap.navigate.connect(self.move_camera)
        self.minimap.maps.failed.connect(self._error)
        self.minimap.large_changed.connect(self._map_changed)
        self.minimap.expanded_changed.connect(lambda expanded: self.views.request_maps() if expanded else None)
        self.selection_actions.changed.connect(self._selection_changed)
        self.selection_actions.preview_changed.connect(lambda: self._show_selection(self.document.selected.preview or self.document.selected.region))
        self.selection_actions.message.connect(self.status.setText)
        self.panels.history.requested.connect(self.seek_history)
        self.panels.recipe.preview_requested.connect(self.preview_recipe)
        self.panels.recipe.code.textChanged.connect(lambda: self.edits.invalidate("recipe"))
        self.panels.recipe.apply_requested.connect(self.apply_pending)
        self.panels.recipe.discard_requested.connect(self.discard_pending)
        self.operation.changed.connect(self._invalidate)
        self.operation.preview_requested.connect(self.preview_operation)
        self.operation.apply_requested.connect(self.apply_pending)
        self.operation.discard_requested.connect(self.discard_pending)
        self.placement.changed.connect(self._sync)
        self.placement.message.connect(self.status.setText)
        self.placement.committed.connect(self._placement_applied)
        self.placement.cancel_requested.connect(self.escape)
        self.placement.bar.apply_requested.connect(self.apply_pending)
        self.repeat.started.connect(self.navigation.stop)
        self.repeat.started.connect(self.panels.dismiss)
        self.repeat.changed.connect(self._sync)
        self.repeat.apply_requested.connect(self.apply_pending)
        self.repeat.cancel_requested.connect(self.cancel_task)

    def _sync(self):
        session, pending = self.document.session, self.document.pending
        selection = self.document.selected.region
        ready = session is not None and not self.tasks.busy
        editable = ready and not session.readonly
        selected = selection is not None
        preview_ready = bool(pending) and self.views.ready
        placing = self.placement.active or self.repeat.active
        self.menus.sync(session, busy=self.tasks.busy, selected=selected,
                        preview=pending is not None, preview_ready=preview_ready, world_active=self.world.active,
                        placing=placing, repeating=self.repeat.active, clipboard=self.placement.clipboard is not None,
                        object_count=len(self.objects.keys), single_block=selected and selection.volume == 1)
        self.placement.set_context(session, selection, self.assets,
                                    busy=self.tasks.busy or (self.placement.active and not self.views.ready and self.placement_review.plan is None),
                                    available=ready and pending is None and self.views.ready and not self.repeat.active,
                                    visible=session is not None and not self.minimap.large and not self.repeat.active
                                    and (pending is None or self.placement_review.plan is not None),
                                    scene_ready=self.views.ready, review=self.placement_review.plan)
        self.placement.bar.stats.set_context(session, selection, self.assets,
                                            visible=not placing and not self.minimap.large and pending is None)
        self._show_selection(selection)
        self.objects.sync()
        self.objects.finder.sync(hidden=self.minimap.large or placing,
                                 bottom=self.placement.bar.height() if self.placement.bar.isVisible() else 0)
        self.slicing.sync(available=session is not None and not self.placement.active
                          and (not self.tasks.busy or self.tasks.kind in ("render", "map")))
        self.menus.actions["height"].setEnabled(self.slicing.button.isEnabled())
        self.repeat.sync(placing=self.placement.active, large=self.minimap.large, scene_ready=self.views.ready)
        self.panels.selection.setEnabled(self.selection_actions.available())
        self.panels.materials.setEnabled(ready and not placing)
        self.operation.setEnabled(session is not None and not session.readonly and not placing)
        self.operation.preview.setEnabled(editable and selected)
        self.operation.apply.setEnabled(editable and preview_ready)
        self.operation.discard.setEnabled(pending is not None)
        self.panels.recipe.preview.setEnabled(editable and selected and not placing)
        self.panels.recipe.apply.setEnabled(editable and preview_ready)
        self.panels.recipe.discard.setEnabled(pending is not None)
        self.refresh_button.setVisible(self.world.active)
        self.save_button.setVisible(self.world.active)
        self.save_button.setText("Save world")
        self.panels.history.set_session(session, busy=self.tasks.busy or placing)
        if session:
            name = session.path.name if session.path else "Untitled"
            self.setWindowTitle(f"{'* ' if session.dirty else ''}{name} — Structura Edit")

    def _map_changed(self, large):
        self.navigation.suspend()
        self.navigation.enabled = self.document.session is not None and not large
        self._sync()

    def fly_camera(self):
        self.minimap.set_large(False)
        self.navigation.start_fly()

    def _task_started(self, kind, task):
        self.error_button.hide()
        self.progress.start(kind.capitalize(), cancellable=not task.protected)
        if task.message:
            self.status.setText(task.message)
        self._sync()

    def _task_failed(self, kind, message):
        if kind == "world" and self.world.queued is None:
            self.world.reset_request()
        self._error(message)

    def _tick(self):
        self.tasks.poll()
        if not self.tasks.busy:
            self.world.flush()
        if not self.tasks.busy:
            self.views.flush()
        if not self.tasks.busy:
            self.progress.finish()
        now = perf_counter()
        self.navigation.tick(now - self._last_tick)
        self.overlay.set_looking(self.navigation.looking)
        self._last_tick = now

    def _error(self, message):
        self.placement.failed()
        self.error_message = message
        self.error_button.show()
        self.status.setText(message.splitlines()[0] if message else "Operation failed")
        self.status.setToolTip(self.status.text())
        self.panels.recipe.output.setPlainText(message)
        self._sync()

    def show_error(self):
        from .error_details import show_error

        self.navigation.stop()
        show_error(self, self.error_message)

    def cancel_task(self):
        if not self.tasks.cancel():
            return
        self.world.reset_request()
        if self.document.session and self.views.displayed is not None:
            offset = tuple(old - new for old, new in zip(self.views.displayed.state.origin, self.document.session.origin))
            if any(offset):
                self.camera.translate(offset)
        self.views.reset()
        self.document.invalidate()
        self.placement.cancel()
        if self.document.session:
            self.render_scene()
        self.status.setText("Task cancelled")
        self._sync()

    def _opened(self, session, *, rendered=None, fit=True, preserve_focus=False):
        self.placement.cancel()
        if not session.readonly:
            session.history.prepare()
        self.document.load(session)
        if not preserve_focus:
            self.slicing.reset(session)
        if rendered is not None and rendered.get("height", HeightSlice()) != self.slicing.value:
            rendered = None
        self.objects.reset()
        self.views.reset()
        self.scene.clear()
        self.panels.selection.set_document(session.size, session.origin)
        if not preserve_focus:
            self.navigation.stop()
            self.panels.dismiss()
        self.workbench.setCurrentIndex(1)
        self.minimap.set_document(session)
        self.navigation.enabled = not self.minimap.large
        self._selection_changed()
        self.materials.set_counts(self.document.session.palette_counts())
        self.views.request(session, None, self.assets, self.entities_action.isChecked(), fit=fit, data=rendered,
                           height=self.slicing.value)
        if rendered is None:
            self.world.queued = None
        if not preserve_focus:
            (self.minimap if self.minimap.large else self.plotter).setFocus()
        self._sync()
        if not preserve_focus:
            self.navigation.start_fly()

    def _selection_changed(self):
        self._invalidate()
        selection = self.document.selected.region
        self._show_selection(selection)
        self.panels.selection.set_selection(selection)
        self.operation.info.setText(self.panels.selection.info.text())
        self.status.setText(self.panels.selection.info.text())
        self._sync()

    def scene_click(self, point, extend=False):
        if self.placement.active:
            self.placement.pin(point)
            return
        if not self.selection_actions.available() or self.document.pending is not None or self.scene.display_revision != self.document.session.revision:
            return
        entity = self.scene.entity_at(self.document.session, point)
        if entity is not None:
            self.objects.select(entity, extend)
            return
        hit = self.scene.hit_at(self.document.session, point)
        if hit is not None:
            self.objects.keys.clear()
            self.objects.refresh()
            self.document.selected.select_block(hit.position, extend=extend)
            self._selection_changed()

    def extend_selection(self, enabled):
        if self.placement.active:
            return
        self.document.selected.set_extending(enabled)
        self._show_selection(self.document.selected.region)

    def scene_hover(self, point):
        if self.placement.active:
            self.overlay.set_hover(None)
            self.placement.hover(point)
            return
        if point is None or not self.document.session or self.document.pending is not None or self.scene.display_revision != self.document.session.revision:
            self.overlay.set_hover(None)
            if self.document.selected.preview is not None:
                self.document.selected.preview = None
                self._show_selection(self.document.selected.region)
            return
        hit = self.scene.hit_at(self.document.session, point)
        self.overlay.set_hover(hit.position if hit is not None else None)
        if self.document.selected.extending:
            previous = self.document.selected.preview
            if hit is None:
                self.document.selected.preview = None
            else:
                self.document.selected.hover_block(hit.position)
            if self.document.selected.preview != previous:
                self._show_selection(self.document.selected.preview or self.document.selected.region)

    def _show_selection(self, selection):
        if self.placement.active:
            self.overlay.set_selection(None)
            return
        display = self.views.displayed.state if self.views.displayed is not None else self.document.session
        offset = tuple(old - new for old, new in zip(self.document.session.origin, display.origin)) if self.document.session and display else (0, 0, 0)
        def shifted(region):
            return region.shifted(offset) if region is not None else None
        corners = tuple(tuple(v + d for v, d in zip(corner, offset)) if corner is not None else None
                        for corner in (self.document.selected.anchor, self.document.selected.opposite))
        self.overlay.set_selection(shifted(self.document.selected.region), shifted(self.document.selected.preview), corners)
        self.overlay.set_hover(None)
        selection = shifted(selection)
        self.minimap.set_selection((selection.lower, selection.upper) if selection else None)

    def show_operation(self, mode):
        if not self.document.session or self.document.session.readonly or self.document.selected.region is None:
            return
        self.navigation.stop()
        self.operation.mode.setCurrentText(mode)
        self.panels.show("operation")
        self._sync()

    def sample_material(self, point):
        if (not self.document.session or self.tasks.busy or self.document.pending is not None or self.placement.active
                or self.scene.display_revision != self.document.session.revision):
            return
        hit = self.scene.hit_at(self.document.session, point)
        if hit is not None:
            state = self.document.session.state_at(hit.position)
            self.operation.fields["target"].setText(state)
            self.operation.fields["target"].setCursorPosition(0)
            self.materials.remember(state)
            self.status.setText(f"Material · {state.removeprefix('minecraft:')}")
            self.status.setToolTip(state)

    def _invalidate(self):
        self.edits.invalidate()
        self._sync()

    def preview_operation(self):
        if not self.placement.active:
            self.edits.prepare("operation", mode=self.operation.current, values=self.operation.values())

    def show_recipe(self):
        self.navigation.stop()
        self.panels.show("recipe")

    def preview_recipe(self):
        if not self.placement.active:
            self.edits.prepare("recipe", code=self.panels.recipe.code.toPlainText())

    def _previewed(self, preview):
        if preview is not None:
            if preview.output is not None:
                self.panels.recipe.output.setPlainText(preview.output)
            if preview.material is not None:
                self.materials.remember(preview.material)
            self.operation.info.setText(f"Preview · {len(preview.change):,} changes")
        self.render_scene()

    def render_scene(self, fit=False):
        if self.document.session:
            self.views.request(self.document.session, self.document.pending, self.assets, self.entities_action.isChecked(), fit=fit,
                               height=self.slicing.value)
            self._sync()

    def _rendered(self, data):
        state = self.views.displayed.state
        canvas = self.minimap.canvas
        if (canvas.size_blocks, canvas.origin) != (state.size, state.origin):
            self.minimap.set_document(state)
        canvas.entities = self.scene.entity_markers
        canvas.update()
        self._guides_changed()
        self.objects.refresh()
        self.status.setText("Preview · Enter to apply · Escape to discard" if self.document.pending is not None else
                            "Minecraft textures" if data["textured"] else "Block colours · View → Minecraft resources for textures")
        for plan in (self.placement_review.plan, self.repeat.plan):
            if plan is not None and self.document.pending is plan.change:
                self.status.setText(plan.summary + " · Preview")
        if data["warnings"]:
            self.panels.recipe.output.setPlainText("\n".join(data["warnings"]))
        if self.document.session.path and self.document.session.path.suffix.lower() == ".schematic" and self.document.pending is None:
            self.status.setText(self.status.text() + " · Legacy converted · Save as NBT")
        self._sync()

    def _guides_changed(self):
        state = self.views.displayed.state if self.views.displayed is not None else self.document.session
        self.guides.update(state, bounds=self.menus.actions["bounds"].isChecked(),
                           chunks=self.menus.actions["chunks"].isChecked())

    def _entities_changed(self):
        if self.world.active:
            self.world.request()
        else:
            self.render_scene()

    def move_camera(self, position):
        self.camera.move_to(position)
        (self.minimap if self.minimap.large else self.plotter).setFocus()

    def camera_dialog(self):
        if self.document.session:
            from .camera_dialog import go_to_coordinates

            self.navigation.stop()
            go_to_coordinates(self, self.plotter.camera.position, self.document.session.origin, self.move_camera)

    def fit_scene(self):
        if self.document.session:
            self.camera.frame(self.document.session.size)

    def apply_pending(self):
        if self.placement.active:
            if self.placement.model is not None and self.placement.model.destination.mode != "all":
                self.placement_review.apply()
            else:
                self.placement.apply(include_entities=self.entities_action.isChecked())
            return
        if not self.document.pending or self.tasks.busy or not self.views.ready:
            return
        preview = self.document.preview
        request = self.views.current
        self.edits.commit(preview.change, lambda session: self._applied(session, preview, request))

    def _applied(self, session, preview, request):
        if not self.views.accept(session, request=request):
            self.render_scene()
        if preview.selection_after is not None:
            self.selection_actions.set_bounds(*preview.selection_after)
        self.panels.dismiss()
        (self.minimap if self.minimap.large else self.plotter).setFocus()
        self.status.setText(f"Applied {len(preview.change):,} cells · Undo is available")
        self._sync()

    def discard_pending(self):
        if self.repeat.active:
            self.repeat.close()
            return
        if self.placement.active:
            self.escape()
            return
        if self.tasks.kind == "apply":
            return
        self._invalidate()
        self.operation.info.setText("Preview discarded")

    def escape(self):
        if self.minimap.large:
            self.minimap.set_large(False)
            return
        if self.repeat.active:
            self.repeat.close()
            return
        if self.placement.active:
            if self.placement.committing:
                return
            if self.tasks.kind in ("clipboard", "placement", "placement_plan"):
                self.cancel_task()
            else:
                self.placement.cancel()
            self.plotter.setFocus()
            return
        if self.document.pending is not None:
            self.discard_pending()
        else:
            self.selection_actions.clear()
            self.objects.reset()
        self.panels.dismiss()
        self.plotter.setFocus()

    def undo(self):
        self._history("undo")

    def redo(self):
        self._history("redo")

    def _history(self, direction):
        if self.tasks.busy or not self.document.session:
            return
        if self.placement.active:
            self.placement.cancel()
            return
        if self.document.pending is not None:
            self.discard_pending()
            return
        self.seek_history(self.document.session.history.cursor + (-1 if direction == "undo" else 1))

    def seek_history(self, index):
        if not self.placement.active:
            self.edits.seek_history(index, lambda session: self.render_scene())

    def choose_assets(self):
        if self.tasks.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose Minecraft client resources", "", "Minecraft client (*.jar)")
        if path:
            self.assets = path
            self.render_scene()

    def _document_updated(self, update):
        if update.resized:
            session = update.session
            self.panels.selection.set_document(session.size, session.origin)
            self.minimap.set_document(session)
            self._show_selection(None)
            self.objects.reset()
        if update.previous.revision != update.session.revision:
            self.materials.set_counts(update.session.palette_counts())

    def _placement_applied(self, session, data, bounds, count):
        clipped = tuple(tuple(max(0, min(p, size)) for p, size in zip(bound, session.size)) for bound in bounds)
        self.document.selected.set_bounds(*clipped)
        self.panels.selection.set_selection(self.document.selected.region)
        if data is None:
            self.views.accept(session)
            self.views.rebase(session)
        else:
            self.views.request(session, None, self.assets, self.entities_action.isChecked(), data=data, height=self.slicing.value)
        self._show_selection(self.document.selected.region)
        self.status.setText(f"Placed · {count:,} changes · Undo is available")
        self._sync()

    def _saved(self, session):
        self.status.setText(f"Saved {session.path.name}")
        if self.world.active:
            backup = getattr(session, "last_backup", None)
            self.status.setToolTip(f"Backup: {backup}" if backup else "No pending changes")
            self.views.rebase(session)
        self._sync()

    def closeEvent(self, event):
        if self.tasks.protected:
            event.ignore()
            return
        if not self.sources.confirm_discard():
            event.ignore()
            return
        self.timer.stop()
        self.navigation.close()
        self.tasks.close()
        self.minimap.cache.close()
        self.minimap.maps.close()
        self.placement.bar.stats.shutdown()
        self.plotter.close()
        event.accept()


def launch(path=None, *, assets=None, region=None, palette_index=0, source_data_version=None, world=None):
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication([])
    app.setApplicationName("Structura Edit")
    window = EditorWindow(path, assets=assets, region=region, palette_index=palette_index, source_data_version=source_data_version)
    window.show()
    if world is not None:
        QTimer.singleShot(0, lambda: window.sources.open_path(world))
    if owns_app:
        return app.exec()
    return window
