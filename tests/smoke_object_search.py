import json
from pathlib import Path
from time import monotonic

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QEvent, QItemSelectionModel, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionComboBox
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit.ui import EditorWindow


def wait_search(window):
    finder = window.objects.finder
    until = monotonic() + 20
    while monotonic() < until:
        QTest.qWait(20)
        if not finder.pending and finder.inflight is None and not finder.timer.isActive() and not window.tasks.busy:
            assert finder.result is not None, window.status.text()
            return
    raise AssertionError(f"Search did not settle: {window.status.text()}")


def query(window, text, kind="all"):
    panel = window.objects.finder.panel
    panel.kind.setCurrentIndex(panel.kind.findData(kind))
    panel.search.setText(text)
    panel.find.click()
    wait_search(window)


def main():
    output = Path("/private/tmp/structura-object-search")
    output.mkdir(exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[160,8,8],
      palette:[{Name:"minecraft:stone"},{Name:"mod:storage_crate"}],
      blocks:[{pos:[2,0,2],state:1,nbt:{storage:{items:[{id:"mod:gem",Count:3b}]},custom:42L}}],
      entities:[{pos:[3d,2d,3d],blockPos:[3,2,3],nbt:{id:"minecraft:pig",UUID:[I;1,2,3,4]}},
                {pos:[4d,2d,3d],blockPos:[4,2,3],nbt:{id:"minecraft:pig",UUID:[I;5,6,7,8]}}]}'''))
    source.present.update({(x, 0, 0): 0 for x in range(150)})
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
    window.show()
    try:
        window.sources.open_path(path)
        settle(window)
        window.navigation.stop()
        QApplication.setActiveWindow(window)
        viewport = window.plotter.geometry()
        window.menus.actions["find_objects"].trigger()
        finder, panel = window.objects.finder, window.objects.finder.panel
        wait_search(window)
        assert panel.isVisible() and panel.search.hasFocus() and not window.navigation.looking, (panel.isVisible(), app.focusWidget(), window.navigation.looking)
        assert window.plotter.geometry() == viewport
        assert finder.result.total == 153 and len(finder.result.rows) == 64
        original = finder.result.rows
        panel.next.click()
        wait_search(window)
        assert finder.result.offset == 64 and not set(original).intersection(finder.result.rows)
        query(window, "MOD: storage", "data")
        assert finder.result.total == 1
        assert panel.kind.currentText() == "Block data"
        option = QStyleOptionComboBox()
        panel.kind.initStyleOption(option)
        rect = panel.kind.style().subControlRect(QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, panel.kind)
        assert panel.kind.fontMetrics().horizontalAdvance(panel.kind.currentText()) <= rect.width()
        panel.actions["select"].click()
        assert window.document.selection().lower == (2, 0, 2) and window.document.selection().volume == 1
        assert not window.objects.keys and window.plotter.geometry() == viewport
        panel.actions["show"].click()
        assert np.allclose(window.plotter.camera.focal_point, (2.5, 0.5, 2.5))
        assert panel.search.hasFocus() and not window.navigation.looking
        panel.grab().save(str(output / "find-block.png"))
        panel.actions["inspect"].click()
        settle(window)
        dialog = window.objects.dialog
        assert dialog is not None and dialog.isVisible()
        dialog.tree.replace_value(("data", "storage", "items", 0, "Count"), from_snbt("7b"))
        dialog.apply.click()
        settle(window)
        wait_search(window)
        assert int(window.document.session.snapshot().block_nbt[(2, 0, 2)]["storage"]["items"][0]["Count"]) == 7
        window.undo()
        settle(window)
        wait_search(window)
        assert int(window.document.session.snapshot().block_nbt[(2, 0, 2)]["storage"]["items"][0]["Count"]) == 3
        query(window, "pig", "entities")
        assert finder.result.total == 2
        panel.results.selectAll()
        panel.actions["select"].click()
        assert len(window.objects.keys) == 2
        panel.actions["inspect"].click()
        settle(window)
        assert len(window.objects.dialog.records) == 2
        window.objects.dialog.close()
        panel.in_selection.setChecked(True)
        wait_search(window)
        assert finder.result.total == 0
        window.selection_actions.set_bounds((0, 0, 0), (8, 8, 8))
        wait_search(window)
        assert finder.result.total == 2
        panel.in_selection.setChecked(False)
        query(window, "", "all")
        selection = panel.results.selectionModel()
        selection.select(panel.model.index(2, 0), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        assert not any(button.isEnabled() for button in panel.actions.values())
        old_token, old_result = finder.shown, finder.result
        window.tasks.submit("recipe", lambda result: None, session=window.document.session.fork(), selection=window.document.session.select(), code="import time\ntime.sleep(0.4)")
        panel.search.setText("stone")
        panel.search.setText("pig")
        finder.received(old_token, old_result)
        assert panel.model.rowCount() == 0 and not panel.actions["inspect"].isEnabled()
        wait_search(window)
        assert finder.result.total == 2 and all(row.kind == "entity" for row in finder.result.rows)
        window.document.session._document.readonly = True
        window._sync()
        assert window.menus.actions["find_objects"].isEnabled()
        panel.actions["inspect"].click()
        settle(window)
        assert not window.objects.dialog.apply.isEnabled()
        window.objects.dialog.close()
        QTest.qWait(50)
        assert panel.search.hasFocus(), (app.activeWindow(), app.focusWidget(), panel.isVisible())
        panel.search.setFocus()
        QTest.keyClick(panel.search, Qt.Key.Key_Escape)
        QTest.qWait(20)
        assert not panel.isVisible() and window.plotter.hasFocus()
        assert window.plotter.geometry() == viewport and not window.document.session.dirty
        assert Structure(path).block_nbt == source.block_nbt
        result = dict(search="paged IDs, words, blocks with data, entities and region", actions="Show / Select / Inspect; exact block and entity group",
                      data="mod inventory edit and Undo, readonly inspect", safety="stale results ignored, latest query queued, mixed selection rejected",
                      layout="compact overlay, unchanged viewport, keyboard focus and Escape")
        (output / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
