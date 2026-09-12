from time import perf_counter

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow, QMessageBox, QToolButton

from .camera import FreeCamera
from .action_log import ActionLog
from .local_store import storage_root
from .changes_ui import ChangesController, SceneChanges
from .connected_actions import ConnectedActions
from .materials_ui import MaterialController
from .planar_ui import PlanarController
from .drafts_ui import DraftController
from .fragments_ui import FragmentController
from .paint_ui import PaintController
from .controls import CellLabel
from .appearance import CONTROL_HEIGHT, GRID
from .theme import apply_theme
from .jobs import Worker
from .task_runner import TaskRunner
from .task_protocol import TaskState
from .height_slice_ui import HeightSliceController
from .height_slice import HeightSlice
from .object_ui import ObjectController
from .inspection_ui import InspectionCard
from .inspection import material_name
from .nbt_batch_ui import BatchNbtController
from .menus import EditorMenus
from .navigation import CONTROLS, Navigation
from .placement_ui import PlacementController
from .placement_review import PlacementReview
from .repeat_ui import RepeatController
from .restore_ui import BackupDialog, ConflictsDialog
from .scene import Scene
from .scene_guides import SceneGuides
from .editor_document import EditorDocument
from .edit_workflow import EditWorkflow
from .exit_ui import ExitController
from .selection_actions import SelectionActions
from .source_ui import SourceController
from .task_progress import TaskProgress, TaskProgressPanel
from .view_pipeline import ViewPipeline
from .workbench import EditorPanels, Workbench
from .world_ui import WorldController
from .overview_ui import OverviewController
from .world_streaming import WorldStreaming
from .action_state import editor_capabilities


class EditorWindow(QMainWindow):
    def __init__(self, path=None, *, assets=None, region=None, palette_index=0, source_data_version=None,
                 off_screen=False, cache_dir=None, world_radius=None):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, off_screen)
        self.setWindowTitle("Structura Edit")
        apply_theme(self)
        self.resize(1380, 880)
        self.setMinimumSize(1104, 600)
        self.document = EditorDocument()
        self.assets = assets
        self.audit = ActionLog(storage_root() / 'logs')
        self.tasks = TaskRunner(Worker(), started=self._task_started, finished=self._sync, failed=self._task_failed,
                                progress=lambda *update: self.progress.set_progress(*update), audit=self.audit)
        self.edits = EditWorkflow(self.document, self.tasks, previewed=self._previewed, updated=self._document_updated)
        self.workbench = Workbench(cache_dir=cache_dir)
        self.setCentralWidget(self.workbench)
        self.plotter = self.workbench.plotter
        self.minimap = self.workbench.minimap
        self.overlay = self.workbench.overlay
        self.scene = Scene(self.plotter)
        self.guides = SceneGuides(self.plotter)
        self.scene_changes = SceneChanges(self.plotter)
        self.changes_ctrl = ChangesController(self.document, self.tasks, self.scene_changes)
        self.camera = FreeCamera(self.plotter, self.minimap.set_camera)
        self.navigation = Navigation(self.plotter, self.camera, capture_mouse=not off_screen)
        self.views = ViewPipeline(self.scene, self.camera, self.minimap, self.tasks.submit, self._rendered,
                                  cache_path=self.minimap.cache.path,
                                  map_updates=self.minimap.maps,
                                  schedule=lambda callback: QTimer.singleShot(8, callback), failed=self._error,
                                  retained_geometry=lambda: self.placement.view.geometry_bytes)
        self.panels = EditorPanels(self)
        self.panels.history.audit = self.audit
        self.selection_actions = SelectionActions(self.document.selected, self.panels.selection, self.plotter.camera,
                                                  available=lambda: self.capabilities.can_select)
        self.connected = ConnectedActions(self.document, self.tasks, self.panels.selection,
                                          available=lambda: self.capabilities.can_keep_selecting)
        self.operation = self.panels.operation
        self.placement = PlacementController(self.scene, self.navigation, self.tasks.submit, self.edits.commit)
        self.placement_review = PlacementReview(self.placement, self.document, self.edits, self.tasks, self.views)
        self.repeat = RepeatController(self.plotter, self.document, self.edits, self.tasks)
        self.placement.bar.destination.materials = self.operation.materials
        self.repeat.bar.destination.materials = self.operation.materials
        self.objects = ObjectController(self.document, self.tasks, self.edits, self.scene, self.navigation,
                                        self.selection_actions, available=self._objects_available,
                                        assets=lambda: self.assets, labels=self.overlay.set_entity_labels)
        self.batch_nbt = BatchNbtController(self)
        self.inspection = InspectionCard(self.plotter, self.minimap, self.objects.inspect)
        self.planar = PlanarController(self)
        self.drafts = DraftController(self)
        self.fragments = FragmentController(self)
        self.paint = PaintController(self)
        self.slicing = HeightSliceController(self.document, self.views, self.navigation)
        self.edits.height = lambda: self.slicing.value
        self.world = WorldController(self.document, self.tasks, self.camera, self.selection_actions,
                                      options=lambda: dict(assets=self.assets, height=self.slicing.value,
                                                           include_entities=self.entities_action.isChecked()),
                                      available=lambda: not self.placement.active and not self.repeat.active, opened=self._opened)
        if world_radius is not None:
            self.world.radius = world_radius
        self.sources = SourceController(self, self.document, self.tasks, self.edits, self.world, self.placement,
                                         opened=self._opened, saved=self._saved, capabilities=lambda: self.capabilities)
        self.exit = ExitController(self)
        self.materials = MaterialController(self.panels, self.navigation, show_operation=self.show_operation,
                                            available=lambda: self.capabilities.can_choose_material)
        self.overview = OverviewController(self)
        self.streaming = WorldStreaming(self.world, lambda: self.overview.auto
                                        and not self.overview.compatible() and not self.overview.worker.busy
                                        and self.overview.blocked_target != self.overview._target() and not self.placement.active
                                        and not self.repeat.active and self.document.pending is None and self.views.ready)
        self.views.prepare_scene = self.overview.prepare_document
        self.views.present_scene = self.overview.present_document
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
        return self.capabilities.can_inspect

    @property
    def capabilities(self):
        model, plan = self.placement.model, self.placement_review.plan
        placement_ready = (self.document.session is not None and model is not None and not model.reason(self.document.session)
                           and (plan is None or bool(plan.change)))
        return editor_capabilities(self.document.session, busy=self.tasks.busy, protected=self.tasks.protected,
                                   selected=self.document.selected.current is not None, preview=self.document.pending,
                                   scene_ready=self.views.ready, placing=self.placement.active,
                                   repeating=self.repeat.active, stroke=self.paint.dragging, world=self.world.active,
                                   placement_ready=placement_ready)

    def _create_menus(self):
        self.menus = EditorMenus(self, {
            "open": self.sources.open_dialog, "save": self.sources.save_dialog,
            "save_as": lambda: self.sources.save_dialog(save_as=True),
            "draft_save": self.drafts.save, "draft_recover": self.drafts.recover,
            "fragment_save": self.fragments.save, "fragments": self.fragments.show,
            "export": self.sources.export_dialog, "close": self.exit.request, "undo": self.undo, "redo": self.redo,
            "revert": self.revert_all, "backups": self.restore_backup, "changes": self.changes_toggled,
            "controls": lambda: self.menus.show_controls(), "about": lambda: self.menus.show_about(),
            "apply": self.apply_pending, "discard": self.discard_pending, "recipe": self.show_recipe,
            "all": self.selection_actions.select_all, "clear": self.selection_actions.clear,
            "select_tool": self.select_tool,
            "connected": self.connected.toggle, "planar": self.planar.toggle, "paint": self.paint.toggle,
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
            "bounds": self._guides_changed, "chunks": self._guides_changed, "sections": self._guides_changed,
            "import": self.sources.import_dialog, "inspect": self.objects.inspect, "entity_all": self.objects.select_region,
            "find_objects": self.objects.finder.show,
            "entity_move": lambda: self.objects.transform("Move"),
            "entity_duplicate": lambda: self.objects.transform("Duplicate"),
            "entity_rotate": lambda: self.objects.transform("Rotate"),
            "entity_delete": lambda: self.objects.transform("Delete"),
        })
        self.panels.materials.catalog_request = self.load_material_catalog
        self.panels.materials.icons = self.objects.icons
        self.placement.bar.bind_actions(self.menus.actions)
        self.entities_action = self.menus.actions["entities"]

    def select_tool(self):
        self.connected.set_active(False)
        if self.planar.active:
            self.planar.toggle()
        if self.paint.active:
            self.paint.toggle()
        self.navigation.freelook = False
        self.navigation.stop()
        self.plotter.setFocus()
        self.status.setText("Click the first corner, then Shift-click the opposite corner. Esc clears and flies.")

    def _create_status_bar(self):
        self.statusBar().addPermanentWidget(self.overview.button)
        self.overview.button.hide()
        self.statusBar().addPermanentWidget(self.slicing.button)
        self.document_status = CellLabel(width=GRID * 24)
        self.statusBar().addPermanentWidget(self.document_status)
        self.status = CellLabel("Open a schematic or world")
        self.statusBar().addWidget(self.status, 1)
        self.error_message = ""
        self.issues = []
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
        self.refresh_button.setText("Load here · F5")
        self.refresh_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refresh_button.setAutoRaise(True)
        self.statusBar().addPermanentWidget(self.refresh_button)
        self.save_button = QToolButton()
        self.save_button.setDefaultAction(self.menus.actions["save"])
        self.save_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.statusBar().addPermanentWidget(self.save_button)
        self.fly_button = QToolButton(text="Look · Tab")
        width = self.fly_button.fontMetrics().horizontalAdvance("Cursor · Tab") + GRID * 6
        self.fly_button.setFixedWidth((width + GRID - 1) // GRID * GRID)
        self.fly_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fly_button.setToolTip(CONTROLS)
        self.fly_button.clicked.connect(self.toggle_fly_camera)
        self.statusBar().addPermanentWidget(self.fly_button)
        self.progress = TaskProgress()
        self.progress.cancelled.connect(self.cancel_task)
        self.progress_panel = TaskProgressPanel(self.workbench, (self.progress, self.overview.progress))

    def _connect_ui(self):
        self.sources.opening.connect(self.navigation.stop)
        self.sources.message.connect(self.status.setText)
        self.world.opening.connect(self.navigation.stop)
        self.world.open_requested.connect(self.sources.open_dialog)
        self.world.message.connect(self.status.setText)
        self.overview.message.connect(self.status.setText)
        self.overview.failed.connect(self._error)
        self.minimap.world_map.failed.connect(self._error)
        self.minimap.world_map.navigate.connect(self.overview.teleport_surface)
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
        self.connected.changed.connect(self._selection_changed)
        self.connected.message.connect(self.status.setText)
        self.changes_ctrl.message.connect(self.status.setText)
        self.navigation.fit_requested.connect(self.fit_scene)
        self.navigation.apply_requested.connect(self.apply_pending)
        self.navigation.cancel_requested.connect(self.escape)
        self.navigation.exit_requested.connect(self.exit.request)
        self.navigation.speed_changed.connect(lambda speed: self.status.setText(f"Flight speed: {speed:.1f} blocks/s"))
        self.minimap.navigate.connect(self.move_camera)
        self.minimap.load_requested.connect(self.world.refresh)
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
        self.operation.changed.connect(self.operation.validate_inputs)
        self.operation.preview_requested.connect(self.preview_operation)
        self.operation.apply_requested.connect(self.apply_pending)
        self.operation.discard_requested.connect(self.discard_pending)
        self.placement.changed.connect(self._sync)
        self.placement.message.connect(self.status.setText)
        self.placement.committed.connect(self._placement_applied)
        self.placement.cancel_requested.connect(self.escape)
        self.placement.bar.apply_requested.connect(self.apply_pending)
        self.repeat.started.connect(self.panels.dismiss)
        self.repeat.changed.connect(self._sync)
        self.repeat.apply_requested.connect(self.apply_pending)
        self.repeat.cancel_requested.connect(self.cancel_task)

    def _sync(self):
        session, pending = self.document.session, self.document.pending
        selection = self.document.selected.current
        caps = self.capabilities
        selected = selection is not None
        placing = self.placement.active or self.repeat.active or self.paint.dragging
        self.connected.sync()
        self.changes_ctrl.refresh()
        self.menus.sync(session, caps, busy=self.tasks.busy, selected=selected,
                        preview=pending is not None, world_active=self.world.active,
                        placing=placing, clipboard=self.placement.clipboard is not None,
                        object_count=len(self.objects.keys), single_block=selected and selection.volume == 1,
                        connected=self.connected.active, changes=self.changes_ctrl.active, stroke=self.paint.dragging)
        self.placement.set_context(session, selection, self.assets,
                                    busy=self.tasks.busy or (self.placement.active and not self.views.ready and self.placement_review.plan is None),
                                    available=caps.can_inspect and self.views.ready,
                                    visible=session is not None and not self.minimap.large and not self.repeat.active
                                    and (pending is None or self.placement_review.plan is not None),
                                    scene_ready=self.views.ready, review=self.placement_review.plan)
        self.placement.bar.apply.setEnabled(caps.can_apply)
        self._show_selection(selection)
        self.inspection.set_context(session, selection, self.objects.keys, self.assets,
                                    visible=not placing and not self.minimap.large and pending is None)
        self.batch_nbt.sync()
        self.objects.finder.sync(hidden=self.minimap.large or placing,
                                 bottom=self.placement.bar.height() if self.placement.bar.isVisible() else 0)
        self.slicing.sync(available=session is not None and not self.placement.active
                          and (not self.tasks.busy or self.tasks.kind in ("render", "render_preview", "map")))
        self.menus.actions["height"].setEnabled(self.slicing.button.isEnabled())
        self.repeat.sync(placing=self.placement.active, large=self.minimap.large, scene_ready=self.views.ready)
        self.repeat.bar.apply.setEnabled(caps.can_apply)
        self.panels.selection.setEnabled(self.selection_actions.available())
        self.panels.materials.setEnabled(caps.can_choose_material)
        self.operation.setEnabled(session is not None and not session.readonly and not placing)
        self.operation.preview.setEnabled(caps.can_operate)
        self.operation.apply.setEnabled(caps.can_apply)
        self.operation.discard.setEnabled(caps.can_discard)
        self.panels.recipe.preview.setEnabled(caps.can_operate)
        self.panels.recipe.apply.setEnabled(caps.can_apply)
        self.panels.recipe.discard.setEnabled(caps.can_discard)
        self.refresh_button.setVisible(self.world.active)
        self.minimap.load_here.setEnabled(self.menus.actions["refresh"].isEnabled())
        self.fly_button.setVisible(session is not None)
        self.save_button.setVisible(session is not None)
        self.save_button.setText("Save world" if self.world.active else "Save")
        self.document_status.setText("" if session is None else "View only" if session.readonly else "Unsaved" if session.dirty else "Saved")
        self.document_status.setToolTip("" if session is None else f"DataVersion {session._document.source.data_version} · {session.path or 'Untitled'}\n{session._document.capabilities.reason}\n{self.drafts.latest}")
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

    def toggle_fly_camera(self):
        self.minimap.set_large(False)
        self.navigation.toggle_fly()

    def _task_started(self, kind, task):
        self.progress.start(kind.capitalize(), cancellable=not task.protected)
        if task.message:
            self.status.setText(task.message)
        self._sync()

    def _task_failed(self, kind, message):
        if kind == "world" and self.world.queued is None:
            self.world.reset_request()
        if kind == "nbt_batch":
            self.batch_nbt.failed(message)
        self._error(message)
        if kind == "save" and "World changed at" in message:
            self.review_conflicts()

    def changes_toggled(self):
        self.changes_ctrl.set_active(self.menus.actions["changes"].isChecked())

    def revert_all(self):
        session = self.document.session
        if not self.capabilities.can_seek_history or not session.can_undo:
            return
        answer = QMessageBox.question(self, "Revert to opened", "Undo every change made in this session?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.seek_history(0)
        self.status.setText("Reverted to the opened document")

    def restore_backup(self):
        session = self.document.session
        if not self.world.active or session is None or self.tasks.busy or self.document.pending is not None:
            return
        dialog = BackupDialog(self, session.path, self.tasks.submit, self.status.setText)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.exec()

    def review_conflicts(self):
        session = self.document.session
        if session is None or not self.world.active or self.tasks.busy or self.document.pending is not None:
            return

        def received(rows):
            if not rows:
                self.status.setText("No conflicts remain; save again")
                return
            dialog = ConflictsDialog(self, rows)
            if dialog.exec():
                self.edits.save(session.path, self.sources.saved, force=True)

        self.tasks.submit("conflicts", received, session=session)

    def _tick(self):
        stopping = self.tasks.state is TaskState.CANCELLING
        self.tasks.poll()
        if stopping and self.tasks.state is TaskState.IDLE:
            self.status.setText("Task cancelled")
        if self.exit.dialog is not None:
            return
        if not self.tasks.busy:
            self.world.flush()
        if not self.tasks.busy:
            self.views.flush()
        if not self.tasks.busy:
            self.progress.finish()
        self.drafts.tick()
        if not self.tasks.busy:
            self.panels.materials.request_icons()
        now = perf_counter()
        self.navigation.tick(now - self._last_tick)
        self.overview.tick()
        self.streaming.tick(now)
        self.overlay.set_looking(self.navigation.looking)
        fly_text = "Cursor · Tab" if self.navigation.looking else "Look · Tab"
        if self.fly_button.text() != fly_text:
            self.fly_button.setText(fly_text)
        self._last_tick = now

    def _error(self, message):
        from .error_details import error_summary

        self.placement.failed()
        self.add_issues((message,))
        self.error_button.show()
        self.status.setText(error_summary(message))
        self.status.setToolTip("Open Issues to read or copy the full details.")
        self.panels.recipe.output.setPlainText(message)
        self._sync()

    def add_issues(self, messages):
        self.issues = list(dict.fromkeys([*self.issues, *messages]))[-32:]
        self.error_message = "\n\n".join(self.issues)
        self.error_button.setText("Issues…")
        self.error_button.setVisible(bool(self.issues))

    def show_error(self):
        from .error_details import show_error

        self.navigation.stop()
        if show_error(self, self.error_message, issues=True):
            self.issues.clear()
            self.error_message = ""
            self.error_button.hide()

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
        self.status.setText("Stopping task…" if self.tasks.busy else "Task cancelled")
        self._sync()

    def _opened(self, session, *, rendered=None, fit=True, preserve_focus=False):
        previous = self.document.session
        self.placement.cancel()
        self.paint.cancel()
        self.paint.active = False
        self.menus.actions["paint"].setChecked(False)
        self.planar.active = False
        self.menus.actions["planar"].setChecked(False)
        self.changes_ctrl.reset()
        if not session.readonly:
            session.history.prepare()
        self.document.load(session)
        self.drafts.opened(session)
        self.issues.clear()
        self.error_button.hide()
        self.add_issues(getattr(session, "notices", ()))
        if not preserve_focus:
            self.slicing.reset(session)
        if rendered is not None and rendered.get("height", HeightSlice()) != self.slicing.value:
            rendered = None
        self.objects.reset()
        self.views.reset()
        if not preserve_focus:
            self.scene.clear()
        elif previous is not None:
            self.scene.shift(tuple(old - new for old, new in zip(previous.origin, session.origin)))
            self.overview.scene.rebase(session.origin)
        self.panels.selection.set_document(session.size, session.origin)
        if not preserve_focus:
            self.navigation.stop()
            self.panels.dismiss()
        self.workbench.setCurrentIndex(1)
        self.minimap.set_document(session)
        if fit and not self.world.active:
            self.camera.frame(session.size)
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
        selection = self.document.selected.current
        self._show_selection(selection)
        self.panels.selection.set_selection(selection)
        self.operation.info.setText(self.panels.selection.info.text())
        if selection is not None and selection.volume == 1:
            name = material_name(self.document.session.state_at(selection.lower))
            world = tuple(p + o for p, o in zip(selection.lower, self.document.session.origin))
            self.status.setText(name + " · X {} · Y {} · Z {}".format(*world))
        else:
            self.status.setText(self.panels.selection.info.text())
        self._sync()

    def scene_click(self, point, extend=False):
        if self.placement.active:
            self.placement.pin(point)
            return
        if not self.selection_actions.available() or self.document.pending is not None or self.scene.display_revision != self.document.session.revision:
            return
        if self.planar.active:
            self.planar.pick(self.scene.hit_at(self.document.session, point))
            return
        hit, entity = self.scene.target_at(self.document.session, point)
        if entity is not None:
            self.objects.select(entity, extend)
            return
        if self.connected.active:
            if hit is not None:
                self.objects.keys.clear()
                self.objects.refresh()
                self.connected.pick(hit)
            return
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
            self.inspection.hover(self.document.session)
            if self.document.selected.preview is not None:
                self.document.selected.preview = None
                self._show_selection(self.document.selected.region)
            return
        session = self.document.session
        if self.planar.active:
            hit, entity = self.scene.hit_at(session, point), None
        else:
            hit, entity = self.scene.target_at(session, point)
        if self.inspection.key is None:
            self.inspection.hover(session, hit.position if hit else None, entity)
        if entity is not None:
            from .object_labels import entity_label

            label = entity_label(session._entities[entity].unpack()["nbt"])
            self.overlay.set_hover(None, bounds=self.scene.entity_bounds[entity], label=label)
        else:
            self.overlay.set_hover(hit.position if hit else None,
                                   label=material_name(session.state_at(hit.position)) if hit else "")
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
        corners = self.document.selected.anchor, self.document.selected.opposite
        self.overlay.set_selection(self.document.selected.region, self.document.selected.preview, corners, offset=offset)
        self.overlay.set_block_label(material_name(self.document.session.state_at(selection.lower))
                                     if selection is not None and selection.volume == 1 else "")
        self.overlay.set_hover(None)
        bounds = tuple(tuple(p + d for p, d in zip(bound, offset)) for bound in (selection.lower, selection.upper)) if selection else None
        self.minimap.set_selection(bounds)

    def show_operation(self, mode):
        if not self.capabilities.can_operate:
            return
        self.navigation.stop()
        self.operation.mode.setCurrentText(mode)
        self.panels.show("operation")
        self._sync()

    def load_material_catalog(self):
        session = self.document.session
        if session is None or self.tasks.busy:
            return
        token, assets = self.document.session_token, self.assets
        def received(result):
            if token == self.document.session_token and assets == self.assets:
                self.panels.materials.set_catalog(result, session._document.source.data_version)
                self.operation.set_materials(self.panels.materials.states)
        self.tasks.submit("catalog", received, assets=assets)

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
        if self.capabilities.can_operate and self.operation.validate_inputs():
            self.edits.prepare("operation", mode=self.operation.current, values=self.operation.values())

    def show_recipe(self):
        if not self.capabilities.can_operate:
            return
        self.navigation.stop()
        self.panels.show("recipe")

    def preview_recipe(self):
        if self.capabilities.can_operate:
            self.edits.prepare("recipe", code=self.panels.recipe.code.toPlainText())

    def _previewed(self, preview):
        self.batch_nbt.previewed(preview)
        if preview is not None:
            if preview.output is not None:
                self.panels.recipe.output.setPlainText(preview.output)
            if preview.material is not None:
                self.materials.remember(preview.material)
            summary = preview.change.report.summary if preview.change.report else f"{len(preview.change):,} changes"
            self.operation.info.setText(summary)
            self.operation.info.setToolTip(summary)
        self.render_scene()

    def render_scene(self, fit=False):
        if self.document.session:
            self.views.request(self.document.session, self.document.pending, self.assets, self.entities_action.isChecked(), fit=fit,
                               height=self.slicing.value)
            self._sync()

    def _rendered(self, data):
        preview = self.document.preview
        if preview is not None and preview.change.report is not None:
            self.operation.info.setText(preview.change.report.for_height(self.slicing.value).summary)
        state = self.views.displayed.state
        canvas = self.minimap.canvas
        if (canvas.size_blocks, canvas.origin) != (state.size, state.origin):
            self.minimap.set_document(state)
        canvas.set_entities(self.scene.entity_markers)
        canvas.update()
        self._guides_changed()
        self.objects.refresh()
        self.status.setText("Preview · Enter to apply · Escape to discard" if self.document.pending is not None else
                            "Minecraft textures" if data["textured"] else "Block colours · View → Minecraft resources for textures")
        for plan in (self.placement_review.plan, self.repeat.plan):
            if plan is not None and self.document.pending is plan.change:
                self.status.setText(plan.summary + " · Preview")
        if data["warnings"]:
            self.add_issues(data["warnings"])
        if self.document.session.path and self.document.session.path.suffix.lower() == ".schematic" and self.document.pending is None:
            self.status.setText(self.status.text() + " · Legacy converted · Save as NBT")
        self._sync()

    def _guides_changed(self):
        state = self.views.displayed.state if self.views.displayed is not None else self.document.session
        self.guides.update(state, bounds=self.menus.actions["bounds"].isChecked(),
                           chunks=self.menus.actions["chunks"].isChecked(), sections=self.menus.actions["sections"].isChecked())

    def _entities_changed(self):
        if self.world.active:
            self.world.request()
        else:
            self.render_scene()

    def move_camera(self, position):
        self.overview.teleport(position)
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
        if not self.capabilities.can_apply:
            return
        if self.placement.active:
            self.placement_review.apply()
            return
        preview = self.document.preview
        request = self.views.current
        self.edits.commit(preview.change, lambda session: self._applied(session, preview, request))

    def _applied(self, session, preview, request):
        if not self.views.accept(session, request=request):
            self.render_scene()
        if preview.selection_after is not None:
            self.selection_actions.set_bounds(*preview.selection_after)
        (self.minimap if self.minimap.large else self.plotter).setFocus()
        self.status.setText(f"Applied {len(preview.change):,} cells · Undo is available")
        self._sync()

    def discard_pending(self):
        if not self.capabilities.can_discard:
            return
        if self.paint.dragging:
            self.paint.cancel()
            self._sync()
            return
        if self.repeat.active:
            self.repeat.close()
            return
        if self.placement.active:
            self.escape()
            return
        self._invalidate()
        self.operation.info.setText("Preview discarded")

    def escape(self):
        if self.overview.intent.destination is not None or self.overview.surface is not None:
            self.overview.cancel()
            return
        if self.paint.active:
            if self.document.preview is not None and self.document.preview.kind == "paint":
                self.discard_pending()
            self.paint.toggle()
            self._sync()
            return
        if self.planar.active:
            self.planar.toggle()
            return
        if self.minimap.large:
            self.minimap.set_large(False)
            return
        if self.repeat.active:
            self.repeat.close()
            return
        if self.placement.active:
            if self.placement.committing:
                return
            if self.tasks.kind in ("clipboard", "placement", "placement_plan", "placement_area"):
                self.cancel_task()
            else:
                self.placement.cancel()
            self.plotter.setFocus()
            return
        if self.connected.active:
            self.connected.set_active(False)
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
        from .action_state import history_action

        state = history_action(self.document.session, direction, busy=self.tasks.busy,
                               placing=self.placement.active or self.repeat.active, preview=self.document.pending is not None,
                               stroke=self.paint.dragging)
        if not state.enabled:
            return
        if state.action == "cancel-stroke":
            self.paint.cancel()
            self._sync()
            return
        if state.action == "cancel-placement":
            self.escape()
            return
        if state.action == "cancel-preview":
            self.discard_pending()
            return
        self.seek_history(self.document.session.history.cursor + (-1 if direction == "undo" else 1))

    def seek_history(self, index):
        if self.capabilities.can_seek_history:
            self.edits.seek_history(index, lambda session: self.render_scene())

    def choose_assets(self):
        if self.tasks.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose Minecraft client resources", "", "Minecraft client (*.jar)")
        if path:
            self.assets = path
            self.objects.icons.forget()
            self.panels.materials.model.icons.clear()
            self.panels.materials.catalog = {}
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
        self.panels.selection.set_selection(self.document.selected.current)
        if data is None:
            if self.views.displayed is not None and self.views.displayed.change is not None and self.views.accept(session):
                self.views.rebase(session)
            else:
                self.render_scene()
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
        if not self.exit.confirm_close():
            event.ignore()
            return
        self.timer.stop()
        self.views.reset()
        self.paint.close()
        self.navigation.close()
        self.tasks.close()
        self.overview.close()
        self.audit.close()
        self.minimap.cache.close()
        self.minimap.maps.close()
        self.inspection.shutdown()
        self.plotter.close()
        event.accept()


def launch(path=None, *, assets=None, region=None, palette_index=0, source_data_version=None, world=None, world_radius=None):
    app = QApplication.instance()
    owns_app = app is None
    if owns_app:
        app = QApplication([])
    app.setApplicationName("Structura Edit")
    window = EditorWindow(path, assets=assets, region=region, palette_index=palette_index, source_data_version=source_data_version, world_radius=world_radius)
    window.show()
    if world is not None:
        QTimer.singleShot(0, lambda: window.sources.open_path(world))
    if owns_app:
        return app.exec()
    return window
