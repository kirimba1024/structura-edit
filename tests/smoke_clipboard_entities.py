import json
from pathlib import Path
from time import perf_counter

from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit import DestinationRule
from structura_edit.entity_transform import payloads
from structura_edit.ui import EditorWindow


def unique_ids(session):
    values = [payload["UUID"].to_snbt() for record in session.snapshot().entities for payload in payloads(record["nbt"])]
    assert len(values) == len(set(values))


def click(field):
    QTest.mouseClick(field, Qt.MouseButton.LeftButton, pos=QPoint(field.width() - 2, field.height() // 2))
    QApplication.processEvents()


def check_placement(window, output):
    window.selection_actions.set_bounds((1, 0, 1), (4, 4, 4))
    placement = window.placement
    placement.start("take")
    settle(window)
    placement.set_position((6, 0, 5))
    original = window.document.session.snapshot()
    actors = tuple(placement.view.actors)
    camera = tuple(tuple(v) for v in window.plotter.camera_position)
    viewport = window.plotter.geometry()
    content = placement.bar.content
    assert content.blocks.text() == "Blocks · 2" and content.entities.text() == "Entities · 2"
    assert placement.view.block_actors and placement.view.entity_actors
    click(content.entities)
    assert all(not actor.GetVisibility() for actor in placement.view.entity_actors)
    click(content.blocks)
    assert not placement.bar.apply.isEnabled()
    click(content.entities)
    assert placement.bar.apply.isEnabled() and not placement.bar.air.isEnabled()
    assert all(actor.GetVisibility() for actor in placement.view.entity_actors)
    assert all(not actor.GetVisibility() for actor in placement.view.block_actors)
    click(content.blocks)
    start = perf_counter()
    for _ in range(100):
        content.entities.click()
    elapsed = (perf_counter() - start) * 10
    assert not window.tasks.busy and tuple(placement.view.actors) == actors
    assert window.plotter.geometry() == viewport
    assert tuple(tuple(v) for v in window.plotter.camera_position) == camera
    placement.bar.grab().save(str(output / "placement.png"))
    placement.bar.transforms[1].click()
    settle(window)
    assert len(placement.model.clipboard.entities) == 2
    placement.bar.repeat.click()
    placement.set_destination(DestinationRule("air"))
    placement.bar.apply.click()
    settle(window)
    assert window.document.pending and len(window.document.pending.entities) == 2 and not window.document.session.dirty
    assert not content.isEnabled()
    assert all(not actor.GetVisibility() for actor in placement.view.actors)
    window.plotter.screenshot(str(output / "preview.png"))
    placement.bar.grab().save(str(output / "review.png"))
    placement.bar.apply.click()
    settle(window)
    assert placement.active and not placement.model.take and len(window.document.session.history.entries) == 1
    assert len(window.document.session._entities) == 2
    unique_ids(window.document.session)
    placement.set_position((6, 0, 1))
    placement.bar.apply.click()
    settle(window)
    placement.bar.apply.click()
    settle(window)
    assert len(window.document.session.history.entries) == 2 and len(window.document.session._entities) == 4
    unique_ids(window.document.session)
    placement.bar.cancel.click()
    window.undo()
    settle(window)
    window.undo()
    settle(window)
    assert window.document.session.snapshot().entities == original.entities
    assert window.document.session.snapshot().block_nbt == original.block_nbt and not window.document.session.dirty
    return dict(toggle_ms=round(elapsed, 3), toggles=100, rebuilt_meshes=0)


def check_repeat(window, output):
    original = window.document.session.snapshot()
    window.selection_actions.set_bounds((1, 0, 1), (4, 4, 4))
    window.repeat.start()
    bar = window.repeat.bar
    bar.copies.setValue(2)
    click(bar.content.blocks)
    assert not bar.air.isEnabled() and not bar.destination.isEnabled()
    bar.preview.click()
    settle(window)
    assert window.document.pending and not window.document.pending.changes and len(window.document.pending.entities) == 4
    assert "4 entities" in bar.info.text()
    click(bar.content.entities)
    assert window.document.pending is None and not bar.preview.isEnabled() and not bar.apply.isEnabled()
    settle(window)
    click(bar.content.entities)
    bar.preview.click()
    settle(window)
    bar.grab().save(str(output / "repeat.png"))
    bar.apply.click()
    settle(window)
    assert len(window.document.session._entities) == 6 and len(window.document.session.history.entries) == 1
    assert window.document.session.snapshot().block_nbt == original.block_nbt
    unique_ids(window.document.session)
    path = output / "entities.nbt"
    window.sources.save_path(path)
    settle(window)
    assert Structure(path).entities == window.document.session.snapshot().entities
    window.undo()
    settle(window)
    assert window.document.session.snapshot().entities == original.entities


def main():
    output = Path("/private/tmp/structura-clipboard-entities")
    output.mkdir(parents=True, exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[12,8,12],
        palette:[{Name:"minecraft:chest",Properties:{facing:"north"}},{Name:"minecraft:stone"}],
        blocks:[{pos:[1,0,1],state:0,nbt:{id:"minecraft:chest",Items:[{id:"minecraft:diamond",count:3}]}},
                {pos:[2,0,2],state:1}],entities:[
          {pos:[1.5d,1d,1.5d],blockPos:[1,1,1],nbt:{id:"minecraft:pig",UUID:[I;1,2,3,4],
              Pos:[1.5d,1d,1.5d],Rotation:[0f,0f],custom:{keep:7L}}},
          {pos:[2.5d,1d,2.5d],blockPos:[2,1,2],nbt:{id:"minecraft:armor_stand",UUID:[I;5,6,7,8],Rotation:[0f,0f]}}]}'''))
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    original = path.read_bytes()
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.resize(1104, 720)
    window.show()
    try:
        window.sources.open_path(path)
        settle(window)
        window.navigation.stop()
        performance = check_placement(window, output)
        print("Combined Take, masks, Keep placing, actor reuse and Undo passed", flush=True)
        check_repeat(window, output)
        assert original == path.read_bytes()
        report = dict(placement="blocks and entities, toggles, rotation, conditional preview, Take and repeated copies",
                      repeat="entities only, preview invalidation, one Undo, NBT save", performance=performance)
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
