import argparse
import json
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from smoke_gui import settle
from structura_edit.ui import EditorWindow
from structura_edit.editor_document import EditPreview


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world")
    parser.add_argument("--output", default="/private/tmp/structura-edit-world.json")
    args = parser.parse_args()
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=Path(args.output).with_suffix(".cache"))
    window.show()
    heartbeats = []
    timer = QTimer()
    timer.timeout.connect(lambda: heartbeats.append(time.perf_counter()))
    timer.start(16)
    report = {}
    try:
        start = time.perf_counter()
        window.sources.open_path(args.world)
        settle(window)
        assert window.world.active, window.panels.recipe.output.toPlainText()
        assert window.views.ready and window.scene.actors, window.panels.recipe.output.toPlainText()
        report["open_seconds"] = time.perf_counter() - start
        report["blocks"] = len(window.document.session._document.source.present)
        report["entities"] = [str(e["nbt"]["id"]) for e in window.document.session._document.source.entities]
        print(json.dumps(report), flush=True)
        before = window.world.camera_position()
        direction = tuple(window.plotter.camera.direction)
        QTest.mouseClick(window.refresh_button, Qt.MouseButton.LeftButton)
        settle(window)
        assert np.allclose(window.world.camera_position(), before), (before, window.world.camera_position(), window.document.session.center, window.panels.recipe.output.toPlainText())
        assert np.allclose(window.plotter.camera.direction, direction)
        assert window.document.session.center == before
        camera = tuple(window.plotter.camera.position)
        QTest.keyPress(window.plotter, Qt.Key.Key_W)
        QTest.qWait(120)
        QTest.keyRelease(window.plotter, Qt.Key.Key_W)
        assert not np.allclose(window.plotter.camera.position, camera)
        QTest.keyClick(window.plotter, Qt.Key.Key_Escape)
        assert not window.navigation.keys
        settle(window)
        window.entities_action.setChecked(False)
        window._entities_changed()
        settle(window)
        assert not window.document.session._document.source.entities
        window.entities_action.setChecked(True)
        window._entities_changed()
        settle(window)
        assert window.document.session._document.source.entities
        session, generation = window.document.session, window.world.generation
        window.move_camera(tuple(p + (32 if i == 0 else 0) for i, p in enumerate(window.plotter.camera.position)))
        unexpected_jobs = []
        flight = QTimer(window)
        def fly():
            if window.tasks.busy or window.world.queued is not None:
                unexpected_jobs.append(window.tasks.kind)
            window.move_camera(tuple(p + (2 if i == 0 else 0) for i, p in enumerate(window.plotter.camera.position)))
        flight.timeout.connect(fly)
        flight.start(60)
        QTest.qWait(3000)
        flight.stop()
        assert window.document.session is session and window.world.generation == generation
        assert not unexpected_jobs, "Flight must not schedule background work"
        destination = window.world.camera_position()
        window.menus.actions["refresh"].trigger()
        settle(window)
        assert window.document.session.center == destination
        assert np.allclose(window.world.camera_position(), destination)
        window.world.refresh()
        destination = tuple(p + (16 if i == 0 else 0) for i, p in enumerate(window.world.camera_position()))
        window.world.center = destination
        window.world.radius = 0
        window.world.request(recenter=True)
        settle(window)
        assert window.document.session.center == destination and window.document.session.radius == 0
        assert window.views.ready
        report["latest_location_request"] = "passed"
        report["largest_ui_gap_seconds"] = max(np.diff(heartbeats), default=0)
        report["heartbeat_count"] = len(heartbeats)
        report["refresh_and_camera"] = "passed"
        report["entity_toggle"] = "passed"
        report["flight_without_background_work"] = "passed"
        report["manual_refresh_at_camera"] = "passed"
        window.sources.open_demo()
        settle(window)
        window.document.show_preview(EditPreview(window.document.session.set_block((0, 0, 0), "minecraft:gold_block")))
        window.render_scene()
        settle(window)
        window.apply_pending()
        settle(window)
        session, generation = window.document.session, window.world.generation
        assert session.dirty
        assert not window.menus.actions["refresh"].isEnabled()
        assert not window.menus.actions["world_settings"].isEnabled()
        QTest.keyClick(window.plotter, Qt.Key.Key_F5)
        window.world.refresh()
        QTest.qWait(100)
        assert window.document.session is session and session.dirty
        assert not window.tasks.busy and window.world.queued is None
        assert window.world.generation == generation
        report["refresh_preserves_open_schematic"] = "passed"
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        timer.stop()
        window.document.load(None)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
