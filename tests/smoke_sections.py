import argparse
import json
from pathlib import Path
from time import perf_counter

from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-section-smoke"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "source.nbt"
    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[48,4,4],palette:[{Name:"minecraft:stone"}],
        blocks:[{pos:[15,1,1],state:0},{pos:[16,1,1],state:0},{pos:[34,1,1],state:0}],
        entities:[{pos:[34.5d,2d,1.5d],blockPos:[34,2,1],nbt:{id:"minecraft:chicken"}}]
    }'''))
    save_structure(source, path, source.size)
    app = QApplication([])
    window = EditorWindow(off_screen=True)
    window.show()
    try:
        window.open_path(path)
        settle(window)
        distant = tuple(window.scene.sections[(2, 0, 0)])
        entities = tuple(window.scene.sections["entities"])
        original = tuple(window.scene.sections[(0, 0, 0)])
        window.pending = window.session.set_block((15, 1, 1), "minecraft:glass")
        start = perf_counter()
        window.render_scene()
        settle(window)
        elapsed = perf_counter() - start
        preview = tuple(window.scene.sections[(0, 0, 0)])
        assert original != preview
        assert tuple(window.scene.sections[(2, 0, 0)]) == distant
        assert tuple(window.scene.sections["entities"]) == entities
        window.apply_pending()
        settle(window)
        assert tuple(window.scene.sections[(0, 0, 0)]) == preview
        assert window.session.state_at((15, 1, 1)) == "minecraft:glass"
        window.undo()
        settle(window)
        assert window.session.state_at((15, 1, 1)) == "minecraft:stone"
        window.redo()
        settle(window)
        assert window.session.state_at((15, 1, 1)) == "minecraft:glass"
        window.pending = window.session.set_block((16, 1, 1), "minecraft:air")
        window.render_scene()
        window.views.flush()
        window.discard_pending()
        settle(window)
        assert window.session.state_at((16, 1, 1)) == "minecraft:stone"
        assert tuple(window.scene.sections[(2, 0, 0)]) == distant
        assert tuple(window.scene.sections["entities"]) == entities
        window.plotter.screenshot(str(args.output / "scene.png"))
        report = dict(preview_with_maps_seconds=elapsed, unchanged_actors="reused",
                      apply="reuses preview", undo_redo="passed", discard_inflight="passed",
                      section_count=len(window.scene.sections), actor_count=len(window.scene.actors))
        (args.output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.session = None
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
