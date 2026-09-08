import json
from pathlib import Path

from amulet_nbt import IntTag, from_snbt
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog
from structura_core import Structure, convert_structure
from structura_core.formats import STRUCTURE_SUFFIXES
from structura_core.nbt_io import load_root, write_root

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def main():
    output = Path("/private/tmp/structura-formats-smoke")
    output.mkdir(exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[3,3,3],
        palette:[{Name:"minecraft:stone"}],blocks:[{pos:[1,1,1],state:0}],entities:[]}'''))
    paths = []
    for suffix in STRUCTURE_SUFFIXES:
        path = output / ("source" + suffix)
        if suffix == ".schematic":
            write_root(from_snbt('''{Width:1s,Height:1s,Length:1s,Materials:"Alpha",Blocks:[B;1b],
                Data:[B;0b],TileEntities:[],Entities:[]}'''), path, name="Schematic")
        else:
            convert_structure(source, path)
        paths.append(path)
    root = load_root(output / "source.schem")
    root["Version"] = IntTag(1)
    root.pop("DataVersion")
    path = output / "sponge-v1.schem"
    write_root(root, path)
    paths.append(path)
    original = {path: path.read_bytes() for path in paths}
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    timer = QTimer(window)
    answered = []
    def answer_version():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QInputDialog):
            answered.append(dialog.labelText())
            dialog.setTextValue(str(source.data_version))
            dialog.accept()
    timer.timeout.connect(answer_version)
    timer.start(20)
    window.show()
    try:
        for path in paths:
            window.open_path(path)
            settle(window)
            assert window.session is not None and window.session.path == path, window.status.text()
            assert window.views.ready and window.scene.actors, window.status.text()
            assert window.views.maps_current is window.views.current
            assert window.session.state_at((0, 0, 0) if path.suffix == ".schematic" else (1, 1, 1)) == "minecraft:stone"
        assert len(answered) == 1, answered
        window.open_path(paths[0])
        settle(window)
        window.placement.start("import", path=str(paths[-1]))
        settle(window)
        assert window.placement.model is not None and len(answered) == 2
        assert window.placement.model.clipboard.size == source.size
        window.placement.set_position((3, 0, 0))
        window.placement.apply(include_entities=True)
        settle(window)
        assert window.session.state_at((4, 1, 1)) == "minecraft:stone"
        window.undo()
        settle(window)
        assert window.session.size == source.size and not window.session.dirty
        assert all(path.read_bytes() == content for path, content in original.items())
        report = dict(opened=[path.name for path in paths], source_version="Sponge v1 Open and Import; Apply and Undo",
                      preview="scene and maps ready", originals="unchanged")
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        timer.stop()
        window.session = None
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
