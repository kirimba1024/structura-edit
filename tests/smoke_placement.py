import argparse
import json
from pathlib import Path

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import screen, settle
from structura_edit.ui import EditorWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-placement-smoke"))
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
        window.sources.open_path(path)
        settle(window)
        window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
        window.placement.start("take")
        settle(window)
        placement = window.placement
        assert placement.model is not None and placement.bar.isVisible()
        actors = tuple(placement.view.actors)
        assert actors and window.document.session.state_at((2, 0, 2)) == "minecraft:chest"
        placement.hover(screen(window, (6, 0, 6)))
        QTest.mouseClick(window.plotter, Qt.MouseButton.LeftButton, pos=screen(window, (6, 0, 6)))
        assert not placement.model.following
        placement.set_position((5, 1, 5))
        camera = window.plotter.camera.position
        QTest.keyClick(window.plotter, Qt.Key.Key_Right)
        QTest.keyClick(window.plotter, Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier)
        assert placement.model.position == (6, 2, 5)
        assert window.plotter.camera.position == camera and not window.navigation.keys
        assert tuple(placement.view.actors) == actors and not window.tasks.busy
        placement.set_position((-1, 2, 5))
        camera_before = np.asarray(window.plotter.camera.position) + window.document.session.origin
        assert placement.bar.apply.isEnabled() and "Outside" not in placement.bar.hint.text()
        QTest.keyClick(window.plotter, Qt.Key.Key_Return)
        settle(window)
        assert window.document.session.size == (13, 6, 12) and window.document.session.origin == (-1, 0, 0)
        assert window.document.session.state_at((0, 2, 5)) == "minecraft:chest"
        assert np.allclose(np.asarray(window.plotter.camera.position) + window.document.session.origin, camera_before)
        window.undo()
        settle(window)
        assert window.document.session.size == source.size and window.document.session.origin == (0, 0, 0)
        assert np.allclose(np.asarray(window.plotter.camera.position) + window.document.session.origin, camera_before)
        assert not placement.active and not window.document.session.dirty
        window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
        placement.start("take")
        settle(window)
        placement.set_position((6, 2, 5))
        window.plotter.screenshot(str(output / "ghost.png"))
        placement.bar.grab().save(str(output / "controls.png"))
        QTest.keyClick(window.plotter, Qt.Key.Key_Return)
        settle(window)
        assert not placement.active and len(window.document.session.history.entries) == 1
        assert window.document.session.state_at((2, 0, 2)) == "minecraft:air"
        assert window.document.session.state_at((6, 2, 5)) == "minecraft:chest"
        assert window.document.session.snapshot().block_nbt[(6, 2, 5)]["Items"] == source.block_nbt[(2, 0, 2)]["Items"]
        assert Structure(path).name_at((2, 0, 2)) == "minecraft:chest"
        window.undo()
        settle(window)
        assert window.document.session.state_at((2, 0, 2)) == "minecraft:chest"
        assert not window.document.session.can_undo and not window.document.session.dirty
        window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
        window.show_operation("Move blocks")
        window.operation.set_values({"offset": (-4, 0, 0)})
        camera_before = np.asarray(window.plotter.camera.position) + window.document.session.origin
        window.preview_operation()
        settle(window)
        assert window.document.pending is not None and window.document.pending.resize is not None
        state = window.views.displayed.state
        assert state.origin == (-2, 0, 0) and window.minimap.canvas.origin == state.origin
        assert np.allclose(np.asarray(window.plotter.camera.position) + state.origin, camera_before)
        window.discard_pending()
        settle(window)
        assert window.minimap.canvas.origin == (0, 0, 0)
        assert np.allclose(window.plotter.camera.position, camera_before)
        window.preview_operation()
        settle(window)
        window.cancel_task()
        settle(window)
        assert window.minimap.canvas.origin == (0, 0, 0)
        assert np.allclose(window.plotter.camera.position, camera_before)
        window.preview_operation()
        settle(window)
        window.apply_pending()
        settle(window)
        assert window.document.selection().lower == (0, 0, 2)
        assert window.document.session.state_at((0, 0, 2)) == "minecraft:chest"
        assert np.allclose(np.asarray(window.plotter.camera.position) + window.document.session.origin, camera_before)
        window.undo()
        settle(window)
        assert window.document.session.size == source.size and not window.document.session.dirty
        assert np.allclose(window.plotter.camera.position, camera_before)
        window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
        placement.start("copy")
        settle(window)
        copied = placement.clipboard
        window.sources.open_path(path)
        settle(window)
        assert placement.clipboard is copied
        placement.start("paste")
        settle(window)
        assert placement.model is not None
        window.escape()
        donor = output / "donor.nbt"
        save_structure(source, donor, source.size)
        placement.start("import", path=str(donor))
        settle(window)
        assert placement.model is not None and window.document.session.path == path
        assert placement.model.clipboard.size == source.size
        window.escape()
        report = dict(take="cancel preserves source; Apply is one undo", input="pin, XYZ and arrows; camera unchanged",
                      geometry="actors reused; no jobs while moving", clipboard="survives document open", import_file="same placement path")
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
