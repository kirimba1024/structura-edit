import json
from pathlib import Path
from time import monotonic

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDoubleSpinBox
from structura_core import Structure, save_structure

from smoke_gui import screen, settle
from structura_edit.ui import EditorWindow


def wait_inventory(dialog):
    until = monotonic() + 10
    while dialog.items.page is None and monotonic() < until:
        QTest.qWait(25)
    assert dialog.items.page is not None, dialog.errors.text()


def main():
    output = Path("/private/tmp/structura-object-smoke")
    output.mkdir(exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[8,8,8],
        palette:[{Name:"minecraft:chest"}],blocks:[{pos:[2,0,2],state:0,
        nbt:{id:"minecraft:chest",storage:{slots:[{id:"mod:gem",Count:3b}]},custom:{keep:123L}}}],
        entities:[{pos:[3d,2d,3d],blockPos:[3,2,3],nbt:{id:"minecraft:pig",UUID:[I;1,2,3,4],
            Inventory:[{id:"mod:gem",Count:2b}],custom:{keep:42L}}},
            {pos:[5d,2d,3d],blockPos:[5,2,3],nbt:{id:"minecraft:chicken",UUID:[I;5,6,7,8]}}]}'''))
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.show()
    try:
        window.sources.open_path(path)
        settle(window)
        window.navigation.stop()
        QTest.qWait(100)
        completed = []
        observer = window.plotter.render_window.AddObserver("EndEvent", lambda *_: completed.append(True))
        for _ in range(100):
            window.plotter.render()
        assert not completed
        QTest.qWait(50)
        assert 1 <= len(completed) <= 2, len(completed)
        window.plotter.render_window.RemoveObserver(observer)
        key = next(iter(window.document.session._entities))
        lower, upper = window.scene.entity_bounds[key]
        point = screen(window, (np.asarray(lower) + upper) / 2)
        assert window.scene.entity_at(window.document.session, point) == key
        QTest.mouseClick(window.plotter, Qt.MouseButton.LeftButton, pos=point)
        assert window.objects.keys == {key} and window.objects.inspect_button.isEnabled()
        window.objects.inspect_button.click()
        settle(window)
        dialog = window.objects.dialog
        assert dialog is not None and dialog.isVisible()
        dialog.tabs.setCurrentIndex(1)
        wait_inventory(dialog)
        assert dialog.inventory.topLevelItemCount() == 1
        dialog.tree.replace_value(("Inventory", 0, "Count"), from_snbt("7b"))
        dialog.grab().save(str(output / "entity-inspector.png"))
        dialog.apply.click()
        settle(window)
        assert int(window.document.session._entities[key].unpack()["nbt"]["Inventory"][0]["Count"]) == 7
        assert int(window.document.session._entities[key].unpack()["nbt"]["custom"]["keep"]) == 42
        window.undo()
        settle(window)
        assert int(window.document.session._entities[key].unpack()["nbt"]["Inventory"][0]["Count"]) == 2
        window.objects.keys.clear()
        window.selection_actions.set_bounds((2, 0, 2), (3, 1, 3))
        window.objects.inspect()
        settle(window)
        dialog = window.objects.dialog
        dialog.tabs.setCurrentIndex(1)
        wait_inventory(dialog)
        assert dialog.inventory.topLevelItemCount() == 1
        dialog.tree.replace_value(("data", "storage", "slots", 0, "Count"), from_snbt("9b"))
        dialog.apply.click()
        settle(window)
        assert int(window.document.session.snapshot().block_nbt[(2, 0, 2)]["storage"]["slots"][0]["Count"]) == 9
        window.selection_actions.set_bounds((0, 0, 0), (8, 8, 8))
        window.menus.actions["entity_all"].trigger()
        settle(window)
        assert len(window.objects.keys) == 2
        initial = window.document.session.snapshot().entities
        for action, value, count in (("move", 1, 2), ("rotate", 90, 2), ("duplicate", 1, 4), ("delete", 0, 0)):
            def accept(value=value):
                dialog = QApplication.activeModalWidget()
                fields = dialog.findChildren(QDoubleSpinBox)
                if fields:
                    fields[0].setValue(value)
                dialog.accept()
            QTimer.singleShot(0, accept)
            window.menus.actions["entity_" + action].trigger()
            settle(window)
            assert len(window.document.session._entities) == count
            if action == "duplicate":
                assert len(window.objects.keys) == 2 and key not in window.objects.keys
            window.undo()
            settle(window)
            assert window.document.session.snapshot().entities == initial
            window.menus.actions["entity_all"].trigger()
            settle(window)
        saved = output / "edited.nbt"
        window.document.session.save(saved)
        assert Structure(saved).block_nbt == window.document.session.snapshot().block_nbt
        assert Structure(path).block_nbt == source.block_nbt
        window.plotter.screenshot(str(output / "entities.png"))
        print(json.dumps(dict(selection="click and region", actions="move, rotate, duplicate, delete, undo",
                              inspector="entity and block nested inventories", render="100 requests coalesced",
                              saved=str(saved))), flush=True)
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
