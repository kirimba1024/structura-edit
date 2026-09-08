import argparse
import json
import time
from pathlib import Path

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import mouse_move, settle
from structura_edit.ui import EditorWindow


def point(position):
    return QPoint(*(round(value) for value in position))


def drag_handle(window, axis):
    start, end = window.placement.drag.gizmo.handles()[axis]
    QTest.mousePress(window.plotter, Qt.MouseButton.LeftButton, pos=point(end))
    assert window.placement.drag.drag is not None
    mouse_move(window.plotter, point(end + (end - start)), Qt.MouseButton.LeftButton)
    return point(end + (end - start))


def check_drag(window, output):
    placement, view = window.placement, window.plotter
    window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
    placement.start("take")
    settle(window)
    placement.set_position((5, 1, 5))
    view.camera.position = (22, 18, 25)
    view.camera.focal_point = (5, 1, 5)
    view.camera.up = (0, 1, 0)
    view.reset_camera_clipping_range()
    view.render()
    QApplication.processEvents()
    original = placement.model.position
    camera = tuple(tuple(v) for v in view.camera_position)
    actors = tuple(placement.view.actors)
    size = view.size()
    assert not placement.bar.details.isVisible()
    placement.bar.grab().save(str(output / "placement-compact.png"))
    placement.bar.more.click()
    QApplication.processEvents()
    assert placement.bar.details.isVisible() and view.size() == size
    placement.bar.grab().save(str(output / "placement-coordinates.png"))
    placement.bar.more.click()
    for axis in range(3):
        placement.set_position(original)
        destination = drag_handle(window, axis)
        assert placement.model.position[axis] != original[axis]
        assert all(placement.model.position[i] == original[i] for i in range(3) if i != axis)
        QTest.keyClick(view, Qt.Key.Key_W)
        QTest.keyClick(view, Qt.Key.Key_Return)
        assert tuple(tuple(v) for v in view.camera_position) == camera and not window.worker.busy
        QTest.keyClick(view, Qt.Key.Key_Escape)
        assert placement.model.position == original and placement.drag.drag is None
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=destination)
    destination = drag_handle(window, 1)
    moved = placement.model.position
    QApplication.sendEvent(view, QFocusEvent(QEvent.Type.FocusOut))
    mouse_move(view, destination + QPoint(50, 50), Qt.MouseButton.LeftButton)
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, pos=destination)
    assert placement.drag.drag is None and placement.model.position == moved
    assert tuple(tuple(v) for v in view.camera_position) == camera
    assert tuple(placement.view.actors) == actors and not window.worker.busy
    for zoom in (0.8, 1.25):
        view.camera.zoom(zoom)
        for start, end in placement.drag.gizmo.handles().values():
            assert np.isclose(np.linalg.norm(end - start), 80)
    placement.set_position(original)
    started = time.perf_counter()
    for index in range(200):
        placement.set_position((5 + index % 8, 1, 5))
    elapsed = time.perf_counter() - started
    assert tuple(placement.view.actors) == actors and not window.worker.busy
    placement.set_position(original)
    view.screenshot(str(output / "gizmo.png"))
    return dict(moves=200, update_ms=elapsed * 1000 / 200, rebuilt_meshes=0)


def check_keep_placing(window, source, path, output):
    placement = window.placement
    actors = tuple(placement.view.actors)
    placement.bar.repeat.click()
    assert placement.model.keep_placing
    placement.set_position((-1, 2, 5))
    camera = np.asarray(window.plotter.camera.position) + window.session.origin
    placement.bar.apply.click()
    settle(window)
    assert placement.active and not placement.model.take and placement.model.following
    assert window.session.origin == (-1, 0, 0)
    assert window.session.state_at((3, 0, 2)) == "minecraft:air"
    assert window.session.state_at((0, 2, 5)) == "minecraft:chest"
    assert np.allclose(np.asarray(window.plotter.camera.position) + window.session.origin, camera)
    assert tuple(placement.view.actors) == actors
    placement.set_position((8, 2, 5))
    placement.bar.apply.click()
    settle(window)
    assert len(window.session.history.entries) == 2
    assert tuple(placement.view.actors) == actors
    expected = source.block_nbt[(2, 0, 2)]["Items"]
    assert window.session.snapshot().block_nbt[(8, 2, 5)]["Items"] == expected
    placement.bar.cancel.click()
    assert not placement.active
    saved = output / "placed.nbt"
    window.save_path(saved)
    settle(window)
    assert Structure(saved).block_nbt[(0, 2, 5)]["Items"] == expected
    assert Structure(saved).block_nbt[(8, 2, 5)]["Items"] == expected
    assert Structure(path).name_at((2, 0, 2)) == "minecraft:chest"
    window.undo()
    settle(window)
    assert window.session.state_at((8, 2, 5)) in (None, "minecraft:air")
    window.undo()
    settle(window)
    assert window.session.size == source.size and window.session.origin == (0, 0, 0)
    assert window.session.state_at((2, 0, 2)) == "minecraft:chest"
    window.save_path(output / "restored.nbt")
    settle(window)
    window.open_path(path)
    settle(window)
    window.navigation.stop()


def check_repeat(window, source, path, output):
    window.slicing.y.setValue(2)
    window.slicing.mode.setCurrentIndex(1)
    settle(window)
    window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
    window.menus.actions["repeat"].trigger()
    repeat = window.repeat
    assert repeat.active and repeat.bar.isVisible()
    viewport = window.plotter.geometry()
    repeat.bar.copies.setValue(3)
    repeat.bar.direction.setCurrentIndex(1)
    repeat.bar.gap.setValue(1)
    assert not repeat.bar.apply.isEnabled()
    repeat.bar.preview.click()
    settle(window)
    assert window.pending is not None and not window.session.dirty and repeat.bar.apply.isEnabled()
    assert window.views.displayed.state.origin == (0, -6, 0)
    assert window.scene.height == window.slicing.value
    assert window.plotter.geometry() == viewport
    repeat.bar.grab().save(str(output / "repeat.png"))
    repeat.bar.gap.setValue(0)
    assert window.pending is None and not repeat.bar.apply.isEnabled()
    settle(window)
    repeat.bar.preview.click()
    settle(window)
    camera = np.asarray(window.plotter.camera.position) + window.views.displayed.state.origin
    repeat.bar.apply.click()
    settle(window)
    assert not repeat.active and not repeat.bar.isVisible()
    assert len(window.session.history.entries) == 1 and window.session.origin == (0, -3, 0)
    assert window.session.state_at((2, 3, 2)) == "minecraft:chest"
    for y in range(3):
        assert window.session.state_at((2, y, 2)) == "minecraft:chest"
        assert window.session.snapshot().block_nbt[(2, y, 2)]["Items"] == source.block_nbt[(2, 0, 2)]["Items"]
    assert np.allclose(np.asarray(window.plotter.camera.position) + window.session.origin, camera)
    window.undo()
    settle(window)
    assert window.session.origin == (0, 0, 0) and window.session.size == source.size
    assert not window.session.dirty
    window.redo()
    settle(window)
    assert window.session.origin == (0, -3, 0)
    saved = output / "repeated.nbt"
    window.save_path(saved)
    settle(window)
    assert len(Structure(saved).block_nbt) == 4
    assert Structure(path).size == source.size
    window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
    repeat.start()
    repeat.preview()
    repeat.close()
    settle(window)
    assert not repeat.active and window.pending is None and not window.session.dirty


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-placement-tools"))
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[12,6,12],palette:[{Name:"minecraft:chest"},{Name:"minecraft:stone"}],
        blocks:[{pos:[2,0,2],state:0,nbt:{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}},
                {pos:[6,0,6],state:1}],entities:[]
    }'''))
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.show()
    try:
        window.open_path(path)
        settle(window)
        window.navigation.stop()
        moves = check_drag(window, output)
        print("Axis drag and layout passed", flush=True)
        check_keep_placing(window, source, path, output)
        print("Keep placing passed", flush=True)
        check_repeat(window, source, path, output)
        report = dict(drag="XYZ, snapping, Escape, focus loss, constant handle size, stable camera and viewport",
                      keep_placing="Take clears source once; two placements, two Undo, mesh reuse, NBT save",
                      repeat="slice, negative expansion, preview invalidation, single Undo/Redo, NBT save, cancellation",
                      movement=moves)
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.session = None
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
