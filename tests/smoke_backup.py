import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from amulet_nbt import LongArrayTag, NamedTag, from_snbt
from amulet.level.formats.anvil_world.region import AnvilRegionInterface
from amulet.utils.world_utils import encode_long_array
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from structura_core.nbt import write_root

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def create_world(path):
    write_root(from_snbt('{Data:{DataVersion:3955,LevelName:"Backup test",SpawnX:8,SpawnY:8,SpawnZ:8}}'), path / "level.dat")
    directory = path / "region"
    directory.mkdir()
    region = AnvilRegionInterface(str(directory / "r.0.0.mca"), mcc=True)
    root = from_snbt('''{DataVersion:3955,xPos:0,zPos:0,Status:"minecraft:full",
        sections:[{Y:0b,block_states:{palette:[{Name:"minecraft:air"},{Name:"minecraft:stone"}]},
                   biomes:{palette:["minecraft:plains"]}}],block_entities:[]}''')
    indices = np.zeros(4096, dtype=np.uint16)
    indices[:256] = 1
    root["sections"][0]["block_states"]["data"] = LongArrayTag(encode_long_array(indices, bits_per_entry=4, dense=False))
    region.write_data(0, 0, NamedTag(root))
    region.unload()


def submit_backups(kind, callback, **args):
    from structura_core.world_staging import list_backups, restore_backup
    from structura_core.world_backup import inspect_restore

    if args.get("restore"):
        callback({"restored": restore_backup(args["world"], args["backup"], expected=args.get("expected"))})
    elif args.get("verify"):
        callback(inspect_restore(args["world"], args["backup"]))
    else:
        callback({"backups": list_backups(args["world"])})
    return True


def restore_with_dialog(window, path, original):
    from structura_edit.restore_ui import BackupDialog
    from structura_core.world_staging import list_backups

    messages = []
    dialog = BackupDialog(window, path, submit_backups, messages.append)
    assert dialog.table.rowCount() == 1, dialog.table.rowCount()
    dialog.table.selectRow(0)
    assert not dialog.restore.isEnabled() and dialog.verify.isEnabled()
    dialog.verify_selected()
    assert dialog.restore.isEnabled() and "match" in dialog.note.text()
    dialog.restore_selected()
    assert (path / "region/r.0.0.mca").read_bytes() == original
    assert any("restore" in entry["name"] for entry in list_backups(path))
    assert messages and "Refresh" in messages[0]
    dialog.deleteLater()


def main():
    app = QApplication([])
    with TemporaryDirectory(prefix="structura-backup-") as temporary:
        path = Path(temporary)
        create_world(path)
        original = (path / "region/r.0.0.mca").read_bytes()
        window = EditorWindow(off_screen=True, cache_dir=path / "cache")
        window.world.radius = 0
        window.show()
        try:
            window.sources.open_path(path)
            settle(window)
            session = window.document.session
            position = tuple(-value for value in session.origin)
            session.apply(session.set_block(position, "minecraft:gold_block"))
            settle(window)
            window.menus.actions["changes"].trigger()
            assert window.menus.actions["changes"].isChecked()
            settle(window)
            assert window.scene_changes.actors and "unsaved changes" in window.status.text(), window.status.text()
            QTest.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
            settle(window)
            session = window.document.session
            assert not session.dirty and (path / "region/r.0.0.mca").read_bytes() != original
            window.menus.actions["changes"].trigger()
            settle(window)
            assert not window.scene_changes.actors
            session.apply(session.set_block(position, "minecraft:diamond_block"))
            settle(window)
            window.menus.actions["changes"].trigger()
            settle(window)
            assert window.scene_changes.actors
            QMessageBox.question = staticmethod(lambda *args: QMessageBox.StandardButton.Yes)
            window.revert_all()
            settle(window)
            session = window.document.session
            assert session.state_at(position) == "minecraft:stone" and session.dirty and session.can_redo
            settle(window)
            assert len(window.scene_changes.actors) == 1
            restore_with_dialog(window, path, original)
            print(json.dumps(dict(changes="accent and removal outlines; save and revert clear them",
                                  backup="verify gates restore; original bytes return; safety copy kept")), flush=True)
        finally:
            window.document.load(None)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == "__main__":
    main()
