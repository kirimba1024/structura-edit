import json
from pathlib import Path
from tempfile import TemporaryDirectory

from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def main():
    app = QApplication([])
    with TemporaryDirectory(prefix="structura-transform-") as temporary:
        path = Path(temporary) / "source.nbt"
        source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[8,4,8],
            palette:[{Name:"minecraft:stone"},{Name:"minecraft:chest",Properties:{facing:"north"}}],
            blocks:[{pos:[0,0,0],state:0},{pos:[1,0,0],state:1,
            nbt:{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}}],entities:[]}'''))
        save_structure(source, path, source.size)
        window = EditorWindow(off_screen=True, cache_dir=Path(temporary) / "cache")
        window.show()
        try:
            window.sources.open_path(path)
            settle(window)
            window.resize(1104, 600)
            window.selection_actions.set_bounds((0, 0, 0), (3, 1, 1))
            window.placement.start("take")
            settle(window)
            placement, bar = window.placement, window.placement.bar
            placement.set_position((4, 0, 2))
            bar.coordinates[0].setFocus()
            bar.coordinates[0].selectAll()
            QTest.keyClicks(bar.coordinates[0], "5")
            assert placement.model.position == (4, 0, 2)
            camera = window.plotter.camera_position
            revision = window.document.session.revision
            for text in ("+90°", "Flip X"):
                button = next(button for button in bar.transforms if button.text() == text)
                QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                assert all(not button.isEnabled() for button in bar.transforms)
                settle(window)
                assert window.plotter.camera_position == camera and window.document.session.revision == revision
                assert not placement.model.following and placement.model.position == (6, 0, 1)
                assert placement.view.source.bounds == ((0, 0, 0), (3, 1, 1))
            assert placement.model.clipboard.size == (1, 1, 3)
            assert placement.model.clipboard.cells[1][1].state == "minecraft:chest[facing=west]"
            window.panels.show("selection")
            app.processEvents()
            for button in bar.transforms:
                assert button.isVisible() and button.geometry().right() < bar.width()
            bar.grab().save("/private/tmp/structura-transform-bar.png")
            window.grab().save("/private/tmp/structura-cell-layout.png")
            pinned = [widget.geometry() for widget in (window.save_button, window.controls)]
            scene_rect = window.plotter.geometry()
            window.progress.set_progress("Preparing a large clipboard", 100_000, 500_000)
            window.progress.show()
            app.processEvents()
            assert [widget.geometry() for widget in (window.save_button, window.controls)] == pinned
            assert window.plotter.geometry() == scene_rect
            window.progress.finish()
            QTest.mouseClick(bar.apply, Qt.MouseButton.LeftButton)
            settle(window)
            assert not placement.active and window.document.session.history.cursor == 1
            assert window.document.session.state_at((0, 0, 0)) == window.document.session.state_at((1, 0, 0)) == "minecraft:air"
            assert window.document.session.state_at((6, 0, 1)) == "minecraft:stone"
            assert window.document.session.state_at((6, 0, 2)) == "minecraft:chest[facing=west]"
            assert str(window.document.session.snapshot().block_nbt[(6, 0, 2)]["Items"][0]["id"]) == "minecraft:diamond"
            window.undo()
            settle(window)
            assert not window.document.session.dirty and window.document.session.state_at((1, 0, 0)) == "minecraft:chest[facing=north]"
            placement.start("paste")
            settle(window)
            assert placement.model.clipboard.size == (1, 1, 3)
            window.escape()
            assert not window.document.session.dirty and not placement.active
            print(json.dumps({"transform": "clockwise rotation and mirror update the ghost and directional state",
                              "placement": "anchor and camera preserved; Take clears source; NBT retained; one Undo",
                              "layout": "controls fit with side panel at minimum window width"}), flush=True)
        finally:
            window.document.load(None)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == "__main__":
    main()
