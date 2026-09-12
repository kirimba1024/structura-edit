from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import shutil
from tempfile import TemporaryDirectory

from PySide6 import __version__ as qt_version
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from vtkmodules.vtkCommonCore import vtkVersion

from structura_edit.local_store import storage_root
from structura_edit.overview_cache import open_snapshot
from structura_edit.overview_store import snapshot_directory


@contextmanager
def isolated_data(world, reuse, cache_source=None):
    source = Path(cache_source) if cache_source is not None else storage_root()
    with TemporaryDirectory(prefix="structura-benchmark-") as temporary:
        root = Path(temporary)
        data = root / "data"
        seeded = dict(overview=False, geometry_files=0)
        if reuse:
            directory = snapshot_directory(source, world, "minecraft:overworld")
            filename = json.loads((directory / "current.json").read_text())["file"]
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError("Invalid overview cache filename")
            snapshot = open_snapshot(directory / filename)
            if snapshot["metadata"]["volatile"]:
                raise ValueError("A benchmark requires an overview without unsaved edits")
            destination = snapshot_directory(data, world, "minecraft:overworld")
            destination.mkdir(parents=True)
            shutil.copy2(snapshot["path"], destination / filename)
            (destination / "current.json").write_text(json.dumps({"file": filename}))
            seeded["overview"] = True
            if (source / "geometry").is_dir():
                shutil.copytree(source / "geometry", data / "geometry")
                seeded["geometry_files"] = sum(1 for _ in (data / "geometry").glob("*/*.npz"))
        values = dict(STRUCTURA_EDIT_DATA=str(data), AMULET_LEVEL_CACHE_DIR=str(root / "amulet"))
        previous = {key: os.environ.get(key) for key in values}
        os.environ.update(values)
        try:
            yield root, seeded
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class NativeSession(QObject):
    def __init__(self, window, viewport, *, require_active=True):
        super().__init__(window)
        self.window = window
        self.viewport = tuple(viewport)
        self.interruptions = []
        self.require_active = require_active
        self.viewport_ready = False
        app = QApplication.instance()
        if app.platformName() in ("offscreen", "minimal"):
            raise RuntimeError("Benchmark requires a native display")
        if require_active:
            window.raise_()
            window.activateWindow()
            if not QTest.qWaitForWindowActive(window, 15000):
                raise RuntimeError("Benchmark requires an unlocked session and an active native window")
        self.screen = window.screen()
        self.check()
        app.installEventFilter(self)

    def fit_viewport(self):
        window = self.window
        actual = window.plotter.render_window.GetSize()
        ratio = window.plotter.devicePixelRatioF()
        window.resize(window.width() + round((self.viewport[0] - actual[0]) / ratio),
                      window.height() + round((self.viewport[1] - actual[1]) / ratio))
        QApplication.instance().processEvents()
        self.viewport_ready = True
        self.check()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.ApplicationDeactivate or (
                watched is self.window and event.type() in (QEvent.Type.WindowDeactivate, QEvent.Type.Hide)):
            self.interruptions.append(event.type().name)
        return False

    def check(self):
        app = QApplication.instance()
        if self.require_active and (self.interruptions or not self.window.isActiveWindow() or self.window.isMinimized()
                                   or app.applicationState() != Qt.ApplicationState.ApplicationActive):
            raise RuntimeError("Benchmark lost its active native window; repeat in an unlocked foreground session")
        if self.window.screen() is not self.screen:
            raise RuntimeError("Benchmark display changed during the run")
        actual = tuple(self.window.plotter.render_window.GetSize())
        if self.viewport_ready and actual != self.viewport:
            raise RuntimeError(f"Benchmark viewport changed: expected {self.viewport}, got {actual}")

    def record(self):
        return dict(platform=platform.platform(), python=platform.python_version(), qt=qt_version,
                    vtk=vtkVersion.GetVTKVersion(), display=self.screen.name(), refresh_hz=self.screen.refreshRate(),
                    device_pixel_ratio=self.window.plotter.devicePixelRatioF(), viewport=list(self.viewport),
                    navigation_timer_ms=self.window.timer.interval(), native_platform=QApplication.platformName(),
                    foreground_required=self.require_active, active=self.window.isActiveWindow(),
                    interruptions=list(self.interruptions))

    def close(self):
        QApplication.instance().removeEventFilter(self)


def scene_resources(window):
    scene, overview = window.scene, window.overview.scene
    return dict(exact_actors=len(scene.actors), exact_geometry_bytes=sum(scene.section_bytes.values()),
                overview_actors=sum(len(entry[0]) for entry in overview.entries.values()),
                overview_visible_actors=sum(actor.GetVisibility() for entry in overview.entries.values() for actor in entry[0]),
                overview_geometry_bytes=sum(entry[1] for entry in overview.entries.values()),
                visible_tiles=len(overview.visible))
