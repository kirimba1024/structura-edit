import argparse
import json
from pathlib import Path
import tempfile
from time import perf_counter

import numpy as np
from PySide6.QtCore import QEventLoop, QPointF, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from overview_fixture import create_overview_world
from structura_edit.ui import EditorWindow


def wait_until(condition, timeout=30):
    if condition():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.timeout.connect(lambda: loop.quit() if condition() else None)
    poll.start(10)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(timeout * 1000)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert condition(), "Overview operation timed out"


def run(output, visible, *, assets=None):
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="structura-overview-world-") as temporary:
        world = create_overview_world(Path(temporary) / "world")
        window = EditorWindow(off_screen=not visible, world_radius=0, assets=assets,
                              cache_dir=Path(temporary) / "maps")
        window.show()
        overview = window.overview
        report = {}
        try:
            window.sources.open_path(world)
            wait_until(lambda: window.world.active and window.views.ready and not window.tasks.busy)
            window.navigation.stop()
            window.navigation.freelook = False
            start = perf_counter()
            QTest.mouseClick(overview.button, Qt.MouseButton.LeftButton)
            wait_until(lambda: overview.snapshot is not None and overview.satisfied == overview._target()
                       and not overview.worker.busy and not overview.uploads)
            report["build_seconds"] = perf_counter() - start
            report["chunks"] = overview.snapshot["metadata"]["chunks"]
            assert report["chunks"] == 6
            overview.fit_world()
            wait_until(lambda: overview.satisfied == overview._target() and not overview.worker.busy)
            window.minimap.world_map.fit()
            window.plotter._render()
            window.grab().save(str(output.with_suffix(".png")))
            window.plotter.screenshot(str(output.with_name(output.stem + "-3d.png")))
            selected = overview.scene.visible.copy()
            generation = overview.intent.generation
            for turn in range(24):
                window.camera.look(50, 0)
                window.camera.render()
                overview.tick()
            assert overview.scene.visible == selected and overview.intent.generation == generation
            report["rotation_without_loading"] = True
            original_session = window.document.session
            original_origin = original_session.origin
            destinations = [(4, 14, 4), (20, 14, 4), (36, 14, 4)]
            for destination in destinations:
                window.move_camera(tuple(p - o for p, o in zip(destination, original_origin)))
            wait_until(lambda: overview.intent.destination is None and not overview.worker.busy and not overview.uploads)
            assert np.allclose(window.world.camera_position(), destinations[-1]), window.world.camera_position()
            assert window.document.session is original_session
            report["latest_teleport_preserves_document"] = True
            window.move_camera(tuple(p - o for p, o in zip((2000, 300, 0), original_origin)))
            overview.tick()
            window.camera.translate((1, 0, 0))
            window.camera.render()
            expected = window.world.camera_position()
            overview.tick()
            wait_until(lambda: not overview.worker.busy and not overview.uploads)
            assert np.allclose(window.world.camera_position(), expected)
            report["manual_flight_cancels_teleport"] = True
            window.world.refresh()
            wait_until(lambda: not window.tasks.busy and window.views.ready and overview.document_preparation is None
                       and overview.document_ready is None and overview.satisfied == overview._target())
            assert window.document.session is not original_session
            assert np.allclose(window.world.camera_position(), expected)
            report["load_here_preserves_camera"] = True
            window.slicing.y.setValue(3)
            window.slicing.mode.setCurrentIndex(1)
            window.slicing.mode.setCurrentIndex(2)
            window.slicing.mode.setCurrentIndex(0)
            wait_until(lambda: window.views.ready and not window.tasks.busy and overview.document_preparation is None
                       and overview.document_ready is None and overview.satisfied == overview._target())
            report["rapid_height_changes_keep_the_latest_view"] = True
            window.camera.move_to(tuple(p - o for p, o in zip((8, 20, 8), window.document.session.origin)))
            overview.refine()
            overview.tick()
            overview.cancel()
            cancelled = overview.intent.generation
            loop = QEventLoop()
            QTimer.singleShot(700, loop.quit)
            loop.exec()
            assert overview.intent.generation == cancelled and overview.intent.target is None
            report["cancel_does_not_restart_auto_detail"] = True
            overview.refine()
            wait_until(lambda: overview.satisfied == overview._target() and not overview.worker.busy)
            canvas = window.minimap.world_map
            cursor = QPointF(91, 52)
            before = canvas.world_at(cursor)
            for factor in (1.2, 1.2, 0.5, 2, 0.75):
                canvas.zoom_at(cursor, factor)
                assert np.allclose(canvas.world_at(cursor), before)
            report["zoom_anchor"] = True
            window.minimap.set_large(True)
            canvas.fit()
            wait_until(lambda: canvas.loaded == canvas.target and canvas.future is None)
            window.resize(1104, 700)
            app.processEvents()
            window.grab().save(str(output.with_name(output.stem + "-map.png")))
            assert not window.issues, window.issues
            report["visible_tiles"] = len(overview.scene.visible)
            report["geometry_bytes"] = sum(entry[2] for entry in overview.scene.entries.values())
            output.write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
            return report
        finally:
            window.document.load(None)
            window.close()
            window.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-overview-smoke.json"))
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()
    run(args.output, args.visible)
