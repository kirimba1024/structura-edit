import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from smoke_gui import settle
from smoke_world_edit import create_world
from structura_edit.source_loading import open_source
from structura_edit.ui import EditorWindow


def local(session, position):
    return tuple(p - o for p, o in zip(position, session.origin))


def main():
    app = QApplication([])
    with TemporaryDirectory(prefix="structura-boundary-") as temporary:
        path = Path(temporary)
        os.environ["STRUCTURA_EDIT_DATA"] = str(path / "local")
        create_world(path)
        original = (path / "region/r.0.0.mca").read_bytes()
        window = EditorWindow(off_screen=True, cache_dir=path / "cache")
        window.world.radius = 0
        window.resize(1104, 700)
        window.show()
        try:
            window.sources.open_path(path)
            settle(window)
            session = window.document.session
            window.selection_actions.set_bounds(local(session, (1, 0, 1)), local(session, (3, 1, 2)))
            window.placement.start("take")
            settle(window)
            window.placement.set_position(local(session, (35, 1, 1)))
            assert window.placement.bar.apply.isEnabled()
            for turns in (1, -1):
                before = window.placement.model.clipboard.size
                window.placement.transform(turns, None)
                settle(window)
                after = window.placement.model.clipboard.size
                assert after == (before[2], before[1], before[0])
            camera = window.world.camera_position()
            QTest.mouseClick(window.placement.bar.apply, Qt.MouseButton.LeftButton)
            settle(window)
            session = window.document.session
            assert not window.placement.active and session.dirty, window.status.text()
            assert session.state_at(local(session, (35, 1, 1))) == "minecraft:stone"
            assert session.state_at(local(session, (1, 0, 1))) == "minecraft:air"
            assert window.world.camera_position() == camera
            assert window.views.ready and window.scene.display_revision == session.revision
            assert len(session.history.entries) == 1
            assert (path / "region/r.0.0.mca").read_bytes() == original
            QTest.mouseClick(window.save_button, Qt.MouseButton.LeftButton)
            settle(window)
            assert window.document_status.text() == "Saved", window.status.text()
            saved = open_source(path, center=(40, 8, 8), radius=0)
            assert saved.state_at(local(saved, (35, 1, 1))) == "minecraft:stone"
            window.undo()
            settle(window)
            assert window.document.session.dirty
            window.sources.save_dialog()
            settle(window)
            restored = open_source(path, center=(40, 8, 8), radius=0)
            assert restored.state_at(local(restored, (35, 1, 1))) in (None, "minecraft:air")
            print(json.dumps(dict(place="one click beyond loaded area", rotation="both directions outside area",
                                  camera="world position preserved", save="read back", undo="single step and saved")), flush=True)
        finally:
            window.document.load(None)
            window.close()
            app.processEvents()


if __name__ == "__main__":
    main()
