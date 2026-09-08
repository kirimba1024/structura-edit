import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def main():
    app = QApplication([])
    with TemporaryDirectory(prefix="structura-stats-") as temporary:
        path = Path(temporary) / "source.nbt"
        source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[4,2,3],
            palette:[{Name:"minecraft:stone"},{Name:"minecraft:oak_planks"}],
            blocks:[{pos:[0,0,0],state:0},{pos:[1,0,0],state:0},{pos:[2,0,0],state:1}],entities:[]}'''))
        save_structure(source, path, source.size)
        window = EditorWindow(off_screen=True, cache_dir=Path(temporary) / "cache")
        window.show()
        stats = window.placement.bar.stats
        def counts():
            until = monotonic() + 10
            while stats.ready_key != stats.key and monotonic() < until:
                QTest.qWait(20)
            assert stats.ready_key == stats.key, stats.info.text()
            return {stats.model.item(i).data(Qt.ItemDataRole.UserRole): stats.model.item(i).text()
                    for i in range(stats.model.rowCount())}
        try:
            window.open_path(path)
            settle(window)
            window.selection_actions.select_all()
            assert not stats.toggle.isChecked() and stats.future is None
            window.plotter.setFocus()
            QTest.mouseClick(stats.toggle, Qt.MouseButton.LeftButton)
            assert window.focusWidget() is window.plotter
            assert counts() == {"minecraft:stone": "2", "minecraft:oak_planks": "1"}
            window.show_operation("Fill")
            window.operation.fields["target"].setText("minecraft:gold_block")
            window.preview_operation()
            settle(window)
            assert not stats.isVisible()
            window.apply_pending()
            settle(window)
            assert counts() == {"minecraft:gold_block": "24"}
            window.undo()
            settle(window)
            assert counts() == {"minecraft:stone": "2", "minecraft:oak_planks": "1"}
            key = stats.ready_key
            window.plotter.setFocus()
            QTest.keyPress(window.plotter, Qt.Key.Key_W)
            QTest.qWait(180)
            QTest.keyRelease(window.plotter, Qt.Key.Key_W)
            assert stats.key == stats.ready_key == key and stats.future is None
            assert not window.worker.busy and not window.views.render_queued and not window.views.map_queued
            window.minimap.set_large(True)
            assert not stats.isVisible()
            window.minimap.set_large(False)
            assert stats.isVisible() and stats.ready_key == key
            QTest.mouseClick(stats.toggle, Qt.MouseButton.LeftButton)
            assert not stats.isVisible() and window.focusWidget() is window.plotter
            print(json.dumps({"stats": "collapsed by default; textures and counts; Apply/Undo refresh",
                              "interaction": "mouse preserves focus; map hides panel; flight starts no work"}), flush=True)
        finally:
            window.session = None
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == "__main__":
    main()
