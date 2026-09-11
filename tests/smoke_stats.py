import json
from pathlib import Path
from tempfile import TemporaryDirectory

from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import settle
from smoke_feedback import wait_for
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
        def counts():
            window.objects.inspect()
            dialog = window.objects.region_dialog
            wait_for(lambda: not dialog.timer.isActive())
            result = {row[0]: row[2] for row in dialog.models[0].rows}
            dialog.close()
            return result
        try:
            window.sources.open_path(path)
            settle(window)
            window.selection_actions.select_all()
            assert counts() == {"minecraft:stone": "2", "minecraft:oak_planks": "1"}
            window.show_operation("Fill")
            window.operation.fields["target"].setText("minecraft:gold_block")
            window.preview_operation()
            settle(window)
            window.apply_pending()
            settle(window)
            assert counts() == {"minecraft:gold_block": "24"}
            window.undo()
            settle(window)
            assert counts() == {"minecraft:stone": "2", "minecraft:oak_planks": "1"}
            assert not window.tasks.busy and not window.views.render_queued and not window.views.map_queued
            print(json.dumps({"inspect": "region material counts after Apply and Undo; no separate Blocks panel"}), flush=True)
        finally:
            window.tasks.close()
            window.exit.approved = True
            window.document.load(None)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == "__main__":
    main()
