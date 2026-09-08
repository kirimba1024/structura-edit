import argparse
import json
from pathlib import Path

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
        window.open_path(path)
        settle(window)
        window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
        window.placement.start("take")
        settle(window)
        placement = window.placement
        assert placement.model is not None and placement.bar.isVisible()
        actors = tuple(placement.view.actors)
        assert actors and window.session.state_at((2, 0, 2)) == "minecraft:chest"
        placement.hover(screen(window, (6, 0, 6)))
        QTest.mouseClick(window.plotter, Qt.MouseButton.LeftButton, pos=screen(window, (6, 0, 6)))
        assert not placement.model.following
        placement.set_position((5, 1, 5))
        camera = window.plotter.camera.position
        QTest.keyClick(window.plotter, Qt.Key.Key_Right)
        QTest.keyClick(window.plotter, Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier)
        assert placement.model.position == (6, 2, 5)
        assert window.plotter.camera.position == camera and not window.navigation.keys
        assert tuple(placement.view.actors) == actors and not window.worker.busy
        placement.set_position((-1, 2, 5))
        assert not placement.bar.apply.isEnabled() and "Outside" in placement.bar.hint.text()
        QTest.keyClick(window.plotter, Qt.Key.Key_Return)
        assert not window.worker.busy and not window.session.dirty
        QTest.keyClick(window.plotter, Qt.Key.Key_Escape)
        assert not placement.active and not window.session.dirty
        placement.start("take")
        settle(window)
        placement.set_position((6, 2, 5))
        window.plotter.screenshot(str(output / "ghost.png"))
        placement.bar.grab().save(str(output / "controls.png"))
        QTest.keyClick(window.plotter, Qt.Key.Key_Return)
        settle(window)
        assert not placement.active and len(window.session.history.entries) == 1
        assert window.session.state_at((2, 0, 2)) == "minecraft:air"
        assert window.session.state_at((6, 2, 5)) == "minecraft:chest"
        assert window.session.snapshot().block_nbt[(6, 2, 5)]["Items"] == source.block_nbt[(2, 0, 2)]["Items"]
        assert Structure(path).name_at((2, 0, 2)) == "minecraft:chest"
        window.undo()
        settle(window)
        assert window.session.state_at((2, 0, 2)) == "minecraft:chest"
        assert not window.session.can_undo and not window.session.dirty
        placement.start("copy")
        settle(window)
        copied = placement.clipboard
        window.open_path(path)
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
        assert placement.model is not None and window.session.path == path
        assert placement.model.clipboard.size == source.size
        window.escape()
        report = dict(take="cancel preserves source; Apply is one undo", input="pin, XYZ and arrows; camera unchanged",
                      geometry="actors reused; no jobs while moving", clipboard="survives document open", import_file="same placement path")
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
