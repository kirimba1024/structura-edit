import json
from pathlib import Path

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QDialogButtonBox, QLabel
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit import DestinationRule
from structura_edit.ui import EditorWindow


def choose_rule(button, mode, material="", *, output=None, cancel=False):
    failures = []
    def interact():
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog is not None
            modes, field = dialog.findChildren(QComboBox)
            modes.setCurrentIndex(modes.findData(mode))
            buttons = dialog.findChild(QDialogButtonBox)
            if mode == "material":
                field.setEditText("bad id")
                buttons.button(QDialogButtonBox.StandardButton.Ok).click()
                assert dialog.isVisible() and any("Enter a block ID" in label.text() for label in dialog.findChildren(QLabel))
                field.setEditText(material)
            QApplication.processEvents()
            assert dialog.height() <= 192
            if output:
                dialog.grab().save(str(output / "rule-dialog.png"))
            buttons.button(QDialogButtonBox.StandardButton.Cancel if cancel else QDialogButtonBox.StandardButton.Ok).click()
        except Exception as error:
            failures.append(error)
            if dialog is not None:
                dialog.reject()
    QTimer.singleShot(60, interact)
    button.click()
    assert not failures, failures


def review(window):
    placement = window.placement
    assert placement.bar.apply.text() == "Preview"
    placement.bar.apply.click()
    settle(window)
    assert window.placement_review.plan is not None
    assert not window.session.dirty
    assert placement.bar.apply.text() == "Place" and placement.bar.isVisible()
    assert all(not actor.GetVisibility() for actor in placement.view.actors)
    assert not placement.drag.gizmo.handles()
    return window.placement_review.plan


def check_placement(window, path, output):
    placement = window.placement
    window.selection_actions.set_bounds((2, 0, 2), (4, 1, 3))
    placement.start("take")
    settle(window)
    placement.set_position((6, 0, 2))
    placement.bar.repeat.click()
    viewport = window.plotter.geometry()
    camera = tuple(tuple(v) for v in window.plotter.camera_position)
    actors = tuple(placement.view.actors)
    choose_rule(placement.bar.destination, "air")
    assert placement.model.destination == DestinationRule("air")
    plan = review(window)
    assert (plan.matched, plan.skipped) == (1, 1) and len(plan.change.changes) == 2
    state = window.views.displayed.state
    assert state.state_at((6, 0, 2)) == "minecraft:gold_block"
    assert state.state_at((2, 0, 2)) == "minecraft:stone"
    assert state.state_at((3, 0, 2)) == "minecraft:air"
    assert state.state_at((7, 0, 2)) == "minecraft:chest"
    assert window.scene.ghost_actors and "1 skipped" in window.status.text()
    assert window.plotter.geometry() == viewport and tuple(tuple(v) for v in window.plotter.camera_position) == camera
    placement.bar.grab().save(str(output / "filtered-preview.png"))
    placement.bar.adjust.click()
    settle(window)
    assert window.pending is None and window.placement_review.plan is None and placement.active
    assert all(actor.GetVisibility() for actor in placement.view.actors)
    choose_rule(placement.bar.destination, "material", "minecraft:obsidian", output=output)
    plan = review(window)
    assert not plan.change and not placement.bar.apply.isEnabled()
    placement.bar.adjust.click()
    settle(window)
    choose_rule(placement.bar.destination, "all", cancel=True)
    assert placement.model.destination.mode == "material"
    choose_rule(placement.bar.destination, "air")
    review(window)
    preview_actors = tuple(window.scene.actors)
    placement.bar.apply.click()
    settle(window)
    assert placement.active and placement.model.following and not placement.model.take
    assert tuple(placement.view.actors) == actors
    assert all(actor in preview_actors for actor in window.scene.actors)
    assert window.session.state_at((2, 0, 2)) == "minecraft:stone"
    assert window.session.state_at((3, 0, 2)) == "minecraft:air"
    assert window.session.state_at((7, 0, 2)) == "minecraft:chest"
    assert len(window.session.history.entries) == 1 and window.pending is None
    placement.bar.cancel.click()
    window.undo()
    settle(window)
    assert not window.session.dirty and window.session.state_at((3, 0, 2)) == "minecraft:chest"
    window.redo()
    settle(window)
    saved = output / "filtered.nbt"
    window.save_path(saved)
    settle(window)
    assert Structure(saved).block_nbt[(7, 0, 2)]["Items"] == Structure(path).block_nbt[(3, 0, 2)]["Items"]
    window.open_path(path)
    settle(window)
    window.navigation.stop()


def check_repeat(window, output):
    window.selection_actions.set_bounds((2, 0, 2), (4, 1, 3))
    window.repeat.start()
    bar = window.repeat.bar
    bar.copies.setValue(3)
    bar.direction.setCurrentIndex(2)
    choose_rule(bar.destination, "air")
    bar.preview.click()
    settle(window)
    assert window.pending and window.repeat.plan.skipped == 1 and bar.apply.isEnabled()
    assert window.views.displayed.state.state_at((6, 0, 2)) == "minecraft:gold_block"
    bar.grab().save(str(output / "repeat-rule.png"))
    bar.apply.click()
    settle(window)
    assert len(window.session.history.entries) == 1 and window.session.state_at((6, 0, 2)) == "minecraft:gold_block"
    window.undo()
    settle(window)
    assert not window.session.dirty
    window.repeat.start()
    window.repeat.preview()
    window.repeat.close()
    settle(window)
    assert not window.session.dirty and window.pending is None


def check_negative_review(window):
    window.selection_actions.set_bounds((3, 0, 2), (4, 1, 3))
    window.placement.start("duplicate")
    settle(window)
    placement = window.placement
    placement.set_position((-2, -1, -3))
    choose_rule(placement.bar.destination, "air")
    camera = np.asarray(window.plotter.camera.position) + window.session.origin
    review(window)
    assert np.allclose(np.asarray(window.plotter.camera.position) + window.views.displayed.state.origin, camera)
    placement.bar.adjust.click()
    settle(window)
    assert np.allclose(np.asarray(window.plotter.camera.position) + window.session.origin, camera)
    review(window)
    placement.bar.apply.click()
    settle(window)
    assert window.session.origin == (-2, -1, -3) and not placement.active
    assert np.allclose(np.asarray(window.plotter.camera.position) + window.session.origin, camera)
    window.undo()
    settle(window)
    assert not window.session.dirty and window.session.origin == (0, 0, 0)


def main():
    output = Path("/private/tmp/structura-destination-rules")
    output.mkdir(exist_ok=True)
    source = Structure.from_root(from_snbt('''{
        DataVersion:3955,size:[12,6,12],palette:[{Name:"minecraft:stone"},{Name:"minecraft:chest"},{Name:"minecraft:gold_block"}],
        blocks:[{pos:[2,0,2],state:0},{pos:[3,0,2],state:1,nbt:{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}},
                {pos:[6,0,2],state:2}],entities:[]
    }'''))
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    original = path.read_bytes()
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.resize(1104, 700)
    window.show()
    try:
        window.open_path(path)
        settle(window)
        window.navigation.stop()
        check_placement(window, path, output)
        print("Conditional placement passed", flush=True)
        check_repeat(window, output)
        check_negative_review(window)
        assert path.read_bytes() == original
        report = dict(placement="accurate filtered preview, no-match, adjust, partial Take, repeated clipboard, Undo/Redo and NBT save",
                      dialog="validation, loaded material list, Cancel preserves rule", repeat="same rule, kept destinations, one Undo",
                      bounds="negative expansion, Adjust and Apply preserve world camera", source="unchanged")
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.session = None
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
