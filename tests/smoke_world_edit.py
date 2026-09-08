import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from amulet_nbt import IntTag, LongArrayTag, NamedTag, from_snbt
from amulet.level.formats.anvil_world.region import AnvilRegionInterface
from amulet.utils.world_utils import encode_long_array
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure
from structura_core.nbt import write_root

from smoke_gui import settle
from structura_edit.source_loading import open_source
from structura_edit.ui import EditorWindow


def create_world(path):
    write_root(from_snbt('{Data:{DataVersion:3955,LevelName:"Placement test",SpawnX:8,SpawnY:8,SpawnZ:8}}'), path / "level.dat")
    directory = path / "region"
    directory.mkdir()
    region = AnvilRegionInterface(str(directory / "r.0.0.mca"), mcc=True)
    for cx in (0, 2):
        root = from_snbt('''{DataVersion:3955,xPos:0,zPos:0,Status:"minecraft:full",
            sections:[{Y:0b,block_states:{palette:[{Name:"minecraft:air"},{Name:"minecraft:stone"}]},
                       biomes:{palette:["minecraft:plains"]}}],block_entities:[]}''')
        root["xPos"] = IntTag(cx)
        indices = np.zeros(4096, dtype=np.uint16)
        indices[:256] = 1
        root["sections"][0]["block_states"]["data"] = LongArrayTag(encode_long_array(indices, bits_per_entry=4, dense=False))
        region.write_data(cx, 0, NamedTag(root))
    region.unload()


def main():
    app = QApplication([])
    with TemporaryDirectory(prefix="structura-world-edit-") as temporary:
        path = Path(temporary)
        create_world(path)
        source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[1,1,1],palette:[{Name:"minecraft:chest"}],
            blocks:[{pos:[0,0,0],state:0,nbt:{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}}],entities:[]}'''))
        donor = path / "donor.nbt"
        save_structure(source, donor, source.size)
        original = (path / "region/r.0.0.mca").read_bytes()
        window = EditorWindow(off_screen=True, cache_dir=path / "cache")
        window.world.radius = 0
        window.show()
        try:
            window.open_path(path)
            settle(window)
            window.placement.start("import", path=str(donor))
            settle(window)
            position = tuple(v - o for v, o in zip((5, 1, 5), window.session.origin))
            window.placement.set_position(position)
            QTest.keyClick(window.plotter, Qt.Key.Key_Return)
            settle(window)
            assert window.session.state_at(position) == "minecraft:chest", window.status.text()
            assert len(window.session.history.entries) == 1 and window.session.dirty
            assert (path / "region/r.0.0.mca").read_bytes() == original
            window.world.center = (40, 8, 8)
            window.world.request(recenter=True)
            settle(window)
            assert window.session.origin[0] == 32 and window.session.dirty
            window.undo()
            settle(window)
            assert not window.session.dirty
            window.redo()
            settle(window)
            actors = tuple(window.scene.actors)
            QTest.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
            settle(window)
            assert not window.session.dirty and window.session.can_undo, window.status.text()
            assert tuple(window.scene.actors) == actors
            assert (window.session.last_backup / "region/r.0.0.mca").read_bytes() == original
            saved = open_source(path, center=(8, 8, 8), radius=0)
            position = tuple(v - o for v, o in zip((5, 1, 5), saved.origin))
            assert saved.state_at(position) == "minecraft:chest"
            assert saved.snapshot().block_nbt[position]["Items"] == source.block_nbt[(0, 0, 0)]["Items"]
            window.undo()
            settle(window)
            assert window.session.dirty
            window.save_dialog()
            settle(window)
            restored = open_source(path, center=(8, 8, 8), radius=0)
            assert restored.state_at(position) in (None, "minecraft:air"), (restored.state_at(position), window.status.text())
            window.session.apply(window.session.set_block((0, -window.session.origin[1], 0), "minecraft:gold_block"))
            window._confirm_discard = lambda: True
            window.world.open(path)
            settle(window)
            assert not window.session.dirty and not window.session.can_undo
            print(json.dumps(dict(import_ghost="one local Apply", refresh="pending blocks and history survive",
                                  save="explicit button; backup and NBT verified", undo_after_save="inverse edit saved")), flush=True)
        finally:
            window.session = None
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == "__main__":
    main()
