from collections import deque
from dataclasses import asdict
import json
from pathlib import Path
from time import monotonic, perf_counter

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QInputDialog, QMenu, QToolButton

from .jobs import Worker
from .task_protocol import TaskSuccess
from .local_store import storage_root
from .overview_model import DetailIntent, DetailTarget, SETTLE_MILLISECONDS
from .overview_scene import OverviewScene
from .overview_store import snapshot_directory
from .task_progress import TaskProgress
from .appearance import GRID
from .overview_cache import snapshot_lease
from .overview_batches import BATCH_BYTES


class OverviewController(QObject):
    message = Signal(str)
    failed = Signal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.worker = Worker()
        self.scene = OverviewScene(window.plotter)
        self.intent = DetailIntent()
        self.snapshot = None
        self.leases = {}
        self.identity = None
        self.job = None
        self.open_queued = False
        self.build_queued = False
        self.uploads = deque()
        self.installation = None
        self.selection = {}
        self.pending_selection = None
        self.satisfied = None
        self.last_position = None
        self.last_direction = None
        self.observed_target = None
        self.blocked_target = None
        self.deadline = 0
        self.auto = True
        self.map_below = None
        self.surface = None
        self.document_preparation = None
        self.document_ready = None
        self.progress = TaskProgress()
        self.progress.cancelled.connect(self.cancel)
        self.button = QToolButton(text="Build overview")
        self.button.setFixedWidth(self.button.fontMetrics().horizontalAdvance("Update overview*") + GRID * 6)
        self.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.button.clicked.connect(self.build)
        menu = QMenu(self.button)
        self.auto_action = menu.addAction("Auto detail")
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(True)
        self.auto_action.toggled.connect(self.set_auto)
        menu.addAction("Refine view", self.refine)
        menu.addAction("Fit world", self.fit_world)
        menu.addAction("Fit map", self.window.minimap.world_map.fit)
        menu.addAction("Map below Y…", self.choose_map_height)
        menu.addAction("Map surface", self.map_surface)
        menu.addSeparator()
        menu.addAction("Refresh overview", self.build)
        self.button.setMenu(menu)
        self.button.setToolTip("Prepare all saved chunks in this dimension. The saved world is read only when building or loading an editing area.")

    def _world_identity(self, session=None):
        session = session or self.window.document.session
        return (str(session.path.resolve()), session.dimension) if hasattr(session, "dimension") else None

    def _target(self, position=None, session=None):
        session = session or self.window.document.session
        position = position or self.window.world.camera_position()
        lower = tuple(session.origin)
        upper = tuple(p + s for p, s in zip(lower, session.size))
        return DetailTarget.at(position, self.window.plotter.render_window.GetSize()[1],
                               self.window.plotter.camera.view_angle, (lower, upper))

    def set_auto(self, value):
        self.auto = value
        if value:
            self.refine()

    def compatible(self, height=None):
        assets = str(Path(self.window.assets).expanduser().resolve()) if self.window.assets else None
        return (self.snapshot is not None and self.identity == self._world_identity()
                and self.snapshot["metadata"]["height"] == asdict(height or self.window.slicing.value)
                and self.snapshot["metadata"]["assets_option"] == assets)

    def choose_map_height(self):
        if not self.window.world.active:
            return
        value, accepted = QInputDialog.getInt(self.window, "Overview map height",
                                            "Rebuild the map below Y (exclusive)",
                                            self.map_below or round(self.window.world.camera_position()[1]), -32768, 32767)
        if accepted:
            self.map_below = value
            self.build()

    def map_surface(self):
        self.map_below = None
        self.build()

    def build(self):
        self.build_queued = False
        if not self.window.world.active or (self.job and self.job[0] == "overview_build"):
            return
        identity = self._world_identity()
        directory = snapshot_directory(storage_root(), *identity)
        self.cancel()
        if self.worker.busy:
            self.worker.close()
            self.job = None
        self.progress.start("Preparing overview")
        self._submit("overview_build", dict(path=identity[0], dimension=identity[1], directory=str(directory),
                                           assets=self.window.assets,
                                           below_y=self.map_below,
                                           edits=self.window.document.session.world_changes.patch.copy(),
                                           document_id=self.window.document.session._id,
                                           revision=self.window.document.session.revision, height=self.window.slicing.value),
                     lambda result: self._opened(result, identity))

    def _opened(self, snapshot, identity):
        if identity != self._world_identity():
            return
        metadata = snapshot["metadata"]
        if metadata["volatile"] and metadata["document_id"] != self.window.document.session._id:
            self.progress.finish()
            self.message.emit("Cached overview contains edits from another session · Build overview to refresh it")
            return
        if snapshot["path"] not in self.leases:
            self.leases[snapshot["path"]] = snapshot_lease(snapshot["path"])
        self.snapshot = snapshot
        self.map_below = metadata["below_y"]
        self.identity = identity
        self.button.setText("Update overview")
        self.window.minimap.set_overview(snapshot)
        self.window.add_issues(metadata.get("warnings", ()))
        self.satisfied = None
        self.last_position = self.window.world.camera_position()
        self.last_direction = tuple(self.window.plotter.camera.direction)
        if self.compatible():
            self.progress.start("Preparing view")
            self.refine()
        else:
            self.progress.finish()
            self.message.emit("Overview uses a different height slice · Update overview to match this view")
        if self.compatible():
            self.message.emit(f"Overview ready · {snapshot['metadata']['chunks']:,} saved chunks")

    def _submit(self, kind, args, callback):
        try:
            self.worker.submit(kind, **args)
            self.job = kind, callback, self.intent.generation, self.worker.current_task_id
            self.button.setEnabled(kind != "overview_build")
        except Exception as error:
            self._failed(str(error))

    def _failed(self, message):
        self.blocked_target = self.intent.target
        self.cancel()
        self.failed.emit(message)

    def cancel(self):
        self.build_queued = False
        self.pending_selection = None
        if self.intent.target is not None:
            self.blocked_target = self.intent.target
        self.intent.cancel()
        self.surface = None
        self.uploads.clear()
        self._cancel_installation()
        self.scene.cancel()
        self.selection = {}
        self.progress.finish()
        self.button.setEnabled(True)
        if self.job and self.job[0] in ("overview_build", "overview_open"):
            self.worker.close()
            self.job = None
        pending, self.document_preparation = self.document_preparation, None
        if pending is not None:
            request, ready = pending
            if request is self.window.views.current:
                self.document_ready = request, True
                ready()

    def refine(self, *, position=None, destination=None, session=None):
        if not self.compatible():
            return
        target = self._target(position, session)
        self.blocked_target = None
        generation = self.intent.request(target, destination)
        self.uploads.clear()
        self._cancel_installation()
        self.progress.start("Preparing destination" if destination is not None else "Preparing view")
        self.pending_selection = generation, target
        self._select()

    def _select(self):
        if self.pending_selection is None or self.worker.busy:
            return
        generation, target = self.pending_selection
        self.pending_selection = None
        self._submit('overview_select', dict(path=self.snapshot['path'], target=target),
                     lambda selection: self._selected(generation, selection))

    def _selected(self, generation, selection):
        if not self.intent.accepts(generation):
            return
        self.selection = selection
        self.scene.begin((self.snapshot['path'], key) for key in selection)
        if not self.scene.missing():
            self._publish(generation)

    def teleport(self, position):
        if not self.compatible():
            self.window.camera.move_to(position)
            return
        self.cancel()
        self.last_position = self.window.world.camera_position()
        self.last_direction = tuple(self.window.plotter.camera.direction)
        destination = tuple(p + o for p, o in zip(position, self.window.document.session.origin))
        self.progress.start("Preparing destination")
        self.refine(position=destination, destination=destination)

    def teleport_surface(self, position):
        if not self.compatible():
            self.message.emit("Update overview to match the current height slice and textures")
            return
        self.cancel()
        self.last_position = self.window.world.camera_position()
        self.last_direction = tuple(self.window.plotter.camera.direction)
        self.surface = tuple(position)
        self.progress.start("Preparing destination")

    def _publish(self, generation):
        if not self.intent.accepts(generation):
            return
        if self.intent.destination is not None and (
                self.window.world.camera_position() != self.last_position
                or tuple(self.window.plotter.camera.direction) != self.last_direction):
            self.cancel()
            return
        if self.document_preparation is not None:
            request, ready = self.document_preparation
            self.document_preparation = None
            if request is self.window.views.current:
                self.document_ready = request, False
                ready()
            return
        session = self.window.document.session
        if not self.scene.publish(session.origin):
            return
        self._release_unused_snapshots()
        destination = self.intent.destination
        self.satisfied = self.intent.target
        self.intent.destination = None
        self.progress.finish()
        self.window.camera.needs_render = True
        if destination is not None:
            self.window.camera.move_to(tuple(p - o for p, o in zip(destination, session.origin)))
        else:
            self.window.camera.render()

    def prepare_document(self, request, ready):
        session = request.session
        if self.snapshot is None or self.identity != self._world_identity(session) or not self.compatible(request.height):
            self.document_ready = request, True
            ready()
            return
        if self.satisfied is not None and self.satisfied.excluded == self._target(session=session).excluded:
            self.document_ready = request, False
            ready()
            return
        self.cancel()
        self.document_preparation = request, ready
        QTimer.singleShot(0, lambda: self.refine(session=session) if self.document_preparation else None)

    def present_document(self, request):
        identity = self._world_identity(request.session)
        if self.document_ready != (request, False):
            self.scene.clear()
            self.satisfied = None
            self.intent.cancel()
        elif self.snapshot is not None:
            if self.scene.publish(request.session.origin) and self.intent.target is not None:
                self.satisfied = self.intent.target
        self.document_ready = None
        if identity != self.identity:
            self.cancel()
            self.snapshot = None
            self.build_queued = False
            self.identity = identity
            self.map_below = 120 if identity and identity[1] == "minecraft:the_nether" else None
            self.window.minimap.set_overview(None)
            self.button.setText("Build overview")
            if identity:
                QTimer.singleShot(0, self._open_cached)
        self.button.setVisible(identity is not None)
        self._release_unused_snapshots()

    def _release_unused_snapshots(self):
        retained = {key[0] for key in self.scene.entries}
        if self.snapshot is not None:
            retained.add(self.snapshot["path"])
        for path in self.leases.keys() - retained:
            self.leases.pop(path).release()

    def _open_cached(self):
        if self.worker.busy or not self.identity:
            self.open_queued = bool(self.identity)
            return
        self.open_queued = False
        directory = snapshot_directory(storage_root(), *self.identity)
        pointer = directory / "current.json"
        if not pointer.is_file():
            self.build_queued = self.auto
            return
        try:
            filename = json.loads(pointer.read_text(encoding="utf-8"))["file"]
            if Path(filename).name != filename:
                raise ValueError("Invalid overview path")
            identity = self.identity
            self._submit("overview_open", {"path": str(directory / filename)}, lambda result: self._opened(result, identity))
        except (OSError, ValueError, KeyError) as error:
            self.failed.emit(f"Could not open the overview: {error}")

    def tick(self):
        pending = self.document_preparation or self.document_ready
        if pending is not None and pending[0] is not self.window.views.current:
            self.document_preparation = self.document_ready = None
            self.cancel()
        if self.snapshot is not None and self.window.document.session is not None:
            metadata = self.snapshot["metadata"]
            session = self.window.document.session
            stale = (metadata["document_id"] == session._id and metadata["revision"] != session.revision) or not self.compatible()
            self.button.setText("Update overview*" if stale else "Update overview")
            self.button.setToolTip("The overview contains an earlier snapshot. Update it to include current edits, height and textures."
                                   if stale else "Prepare all saved chunks again, including current edits. Load here (F5) opens an editing area.")
        self.window.minimap.world_map.tick()
        current_job = self.job is not None and (self.job[0] not in ("overview_read", "overview_surface")
                                                or self.job[2] == self.intent.generation)
        update = self.worker.progress()
        if update is not None and current_job and update.task_id == self.job[3]:
            self.progress.set_progress(update.label, update.done, update.total)
        result = self.worker.poll() if self.worker.busy else None
        if result is not None and self.job is not None and result.task_id == self.job[3]:
            job, self.job = self.job, None
            success = isinstance(result, TaskSuccess)
            payload = result.payload if success else result.message
            self.button.setEnabled(True)
            if success and current_job:
                try:
                    job[1](payload)
                except Exception as error:
                    self._failed(str(error))
            elif not success and current_job:
                if job[0] == "overview_open":
                    self.build_queued = self.auto
                    self.message.emit("Preparing a fresh overview…")
                else:
                    self._failed(payload)
        if self.open_queued and not self.worker.busy:
            self._open_cached()
        if self.build_queued and not self.worker.busy and self.window.views.ready and not self.window.tasks.busy:
            self.build()
        if (not self.compatible() or self.document_ready is not None or not self.window.world.active
                or self.identity != self._world_identity()):
            return
        now = monotonic()
        position = self.window.world.camera_position()
        direction = tuple(self.window.plotter.camera.direction)
        moved = position != self.last_position
        rotated = direction != self.last_direction
        if moved:
            self.last_position = position
        self.last_direction = direction
        if moved or rotated:
            if self.intent.destination is not None or self.surface is not None:
                self.cancel()
        current = self._target()
        if current != self.observed_target:
            if self.observed_target is None or self.observed_target == self.satisfied:
                self.deadline = now + SETTLE_MILLISECONDS / 1000
            self.observed_target = current
        if self.document_preparation is None and self.intent.destination is None and self.surface is None:
            if self.intent.superseded_by(current):
                self.intent.cancel()
                self.pending_selection = None
                self.uploads.clear()
                self._cancel_installation()
                self.scene.cancel()
                self.progress.finish()
            if (self.auto and now >= self.deadline and current != self.satisfied
                    and self.intent.target in (None, self.satisfied) and current != self.blocked_target):
                self.refine()
        if self.pending_selection is not None:
            self._select()
            return
        uploading = not self.window.camera.moving and not self.window.plotter.retirement.busy
        deadline = perf_counter() + 0.002
        try:
            while uploading and (self.uploads or self.installation is not None) and perf_counter() < deadline:
                if self.installation is None:
                    generation, key, data = self.uploads.popleft()
                    if not self.intent.accepts(generation):
                        continue
                    self.installation = self.scene.add_steps((self.snapshot["path"], key), data, self.selection[key])
                if not next(self.installation, False):
                    self.installation = None
        except Exception as error:
            self._failed(str(error))
            return
        if self.intent.target is not None and (self.progress.delay.isActive() or self.progress.requested):
            if not self.job or self.job[0] == "overview_read":
                total = len(self.scene.wanted)
                label = "Preparing destination" if self.intent.destination is not None else "Preparing view"
                self.progress.set_progress(label, total - len(self.scene.missing()), total)
        if self.worker.busy or self.installation is not None:
            return
        if self.surface is not None:
            position = self.surface
            token = self.intent.generation
            def arrived(destination):
                if token == self.intent.generation:
                    self.surface = None
                    self.refine(position=destination, destination=destination)
            self._submit("overview_surface", dict(path=self.snapshot["path"], position=position), arrived)
        elif self.intent.target is not None and self.satisfied != self.intent.target:
            missing = sorted(self.scene.missing())
            if not missing:
                self._publish(self.intent.generation)
                return
            if sum(data['geometry_bytes'] for _, _, data in self.uploads) >= 32 * 1024**2:
                return
            queued = {key for _, key, _ in self.uploads}
            missing = [(path, key) for path, key in missing if key not in queued]
            if not missing:
                return
            keys, size = [], 0
            for _, key in missing:
                count = self.selection[key]
                if keys and size + count > BATCH_BYTES:
                    break
                keys.append(key)
                size += count
            generation = self.intent.generation
            self._submit("overview_read", dict(path=self.snapshot["path"], keys=keys),
                         lambda data: self.uploads.extend((generation, key, value) for key, value in data.items())
                         if self.intent.accepts(generation) else None)

    def fit_world(self):
        if not self.compatible():
            return
        lower, upper = self.snapshot["metadata"]["bounds"]
        size = tuple(hi - lo for lo, hi in zip(lower, upper))
        self.window.camera.frame(size, tuple(lo - origin for lo, origin in zip(lower, self.window.document.session.origin)))
        self.refine()

    def close(self):
        self.worker.close()
        self._cancel_installation()
        self.scene.clear()
        for lease in self.leases.values():
            lease.release()
        self.leases.clear()
        self.window.minimap.world_map.shutdown()

    def _cancel_installation(self):
        if self.installation is not None:
            self.installation.close()
            self.installation = None
