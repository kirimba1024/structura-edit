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
    with TemporaryDirectory(prefix="structura-connected-") as temporary:
        path = Path(temporary) / "source.nbt"
        source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[6,3,6],
            palette:[{Name:"minecraft:stone"},{Name:"minecraft:oak_log",Properties:{axis:"y"}}],
            blocks:[{pos:[0,0,0],state:0},{pos:[2,1,2],state:1}],entities:[]}'''))
        present = {(x, y, z): 0 for x in range(1, 4) for y in range(2) for z in range(1, 3)}
        present.update({(x, 0, 5): 0 for x in range(6)})
        present[2, 1, 2] = 1
        source.present = present
        source.block_nbt = {}
        save_structure(source, path, source.size)
        window = EditorWindow(off_screen=True, cache_dir=Path(temporary) / "cache")
        window.show()
        try:
            window.sources.open_path(path)
            settle(window)
            panel = window.panels.selection
            window.connected.set_active(True)
            assert window.connected.active and panel.connected.isChecked() and panel.criterion.isEnabled()
            window.connected.pick(_hit(window, (1, 0, 1)))
            settle(window)
            assert window.document.selected.cells is not None
            assert window.document.selected.cells.volume == 11, window.document.selected.cells.volume
            assert panel.info.text().endswith("· connected"), panel.info.text()
            assert window.menus.actions["connected"].isChecked()
            window.connected.pick(_hit(window, (0, 0, 5)))
            settle(window)
            assert window.document.selected.cells.volume == 17
            panel.subtract.setChecked(True)
            window.connected.pick(_hit(window, (1, 0, 5)))
            settle(window)
            assert window.document.selected.cells.volume == 11
            assert (0, 0, 5) not in window.document.selected.cells
            window.show_operation("Fill")
            window.operation.fields["target"].setText("minecraft:gold_block")
            window.preview_operation()
            settle(window)
            window.apply_pending()
            settle(window)
            assert window.document.session.state_at((1, 0, 1)) == "minecraft:gold_block"
            assert window.document.session.state_at((2, 1, 2)) == "minecraft:oak_log[axis=y]"
            window.undo()
            settle(window)
            assert window.document.session.state_at((1, 0, 1)) == "minecraft:stone"
            QTest.keyPress(window.plotter, Qt.Key.Key_Escape)
            assert not window.connected.active
            assert window.document.selected.cells is not None
            QTest.keyPress(window.plotter, Qt.Key.Key_Escape)
            settle(window)
            assert window.document.selected.current is None
            print(json.dumps({"connected": "add/subtract accumulate; operations use the cell set; Esc chain",
                              "interaction": "menu check, panel info, Fill on cells, one Undo"}), flush=True)
        finally:
            window.document.load(None)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


def _hit(window, position):
    from types import SimpleNamespace

    return SimpleNamespace(position=position)


if __name__ == "__main__":
    main()
