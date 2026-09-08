import json
from pathlib import Path
from time import monotonic

from amulet_nbt import ByteTag, CompoundTag, IntTag, ListTag, LongTag, StringTag, from_snbt
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLineEdit
from structura_core import Structure

from structura_edit.nbt_value_dialog import NbtValueDialog
from structura_edit.object_edits import edit_objects, inspect_objects
from structura_edit.object_inspector import ObjectInspector
from structura_edit.session import EditSession
from structura_edit.theme import apply_theme


def wait_search(dialog):
    until = monotonic() + 10
    while monotonic() < until:
        QTest.qWait(20)
        if not dialog.searcher.timer.isActive():
            assert dialog.results().page is not None, dialog.errors.text()
            return
    raise AssertionError("NBT search did not finish")


def query(dialog, text):
    dialog.search.setText(text)
    QTest.keyClick(dialog.search, Qt.Key.Key_Return)
    wait_search(dialog)


def edit(dialog, button, text, *, invalid=None, cancel=False):
    failures = []
    def enter():
        try:
            value = QApplication.activeModalWidget()
            assert isinstance(value, NbtValueDialog)
            assert isinstance(value.editor, QLineEdit)
            if invalid is not None:
                value.editor.setText(invalid)
                value.buttons.button(QDialogButtonBox.StandardButton.Ok).click()
                assert value.isVisible() and value.error.text()
            value.editor.setText(text)
            value.buttons.button(QDialogButtonBox.StandardButton.Cancel if cancel else QDialogButtonBox.StandardButton.Ok).click()
        except BaseException as error:
            failures.append(error)
            QApplication.activeModalWidget().reject()
    QTimer.singleShot(50, enter)
    button.click()
    if failures:
        raise failures[0]
    if dialog.searcher.timer.isActive():
        wait_search(dialog)


def main():
    output = Path("/private/tmp/structura-inspector")
    output.mkdir(exist_ok=True)
    app = QApplication([])
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[4,4,4],palette:[{Name:"mod:crate"}],
      blocks:[{pos:[1,1,1],state:0,nbt:{id:"mod:crate",storage:{slots:[{id:"mod:rare_gem",Count:3b,
        components:{keep:9007199254740993L}}]},energy:9007199254740993L}}],
      entities:[{pos:[2d,1d,2d],blockPos:[2,1,2],nbt:{id:"mod:mob",Inventory:[{id:"mod:gem",Count:2b}]}}]}'''))
    session = EditSession.from_structure(source)
    records = inspect_objects(session, position=(1, 1, 1)) + inspect_objects(session, keys=tuple(session._entities))
    dialog = ObjectInspector(None, records)
    apply_theme(dialog)
    dialog.resize(800, 580)
    dialog.show()
    QApplication.setActiveWindow(dialog)
    try:
        QTest.qWait(50)
        assert dialog.width() == 800
        original = source.block_nbt[(1, 1, 1)].to_snbt()
        query(dialog, "energy")
        assert dialog.fields.page.total == 1
        dialog.fields.table.setCurrentItem(dialog.fields.table.topLevelItem(0))
        edit(dialog, dialog.open_value, "9223372036854775807", invalid="9223372036854775808")
        assert dialog.tree.value(("data", "energy")) == LongTag(9223372036854775807)
        assert source.block_nbt[(1, 1, 1)].to_snbt() == original
        dialog.search.clear()
        dialog.tabs.setCurrentIndex(1)
        wait_search(dialog)
        query(dialog, "rare gem")
        assert dialog.items.page.total == 1
        dialog.inventory.setCurrentItem(dialog.inventory.topLevelItem(0))
        edit(dialog, dialog.edit_count, "9", cancel=True)
        assert dialog.tree.value(("data", "storage", "slots", 0, "Count")) == ByteTag(3)
        edit(dialog, dialog.edit_count, "9", invalid="128")
        assert dialog.tree.value(("data", "storage", "slots", 0, "Count")) == ByteTag(9)
        dialog.inventory.setCurrentItem(dialog.inventory.topLevelItem(0))
        dialog.grab().save(str(output / "inventory.png"))
        dialog.open_value.click()
        assert dialog.tabs.currentIndex() == 0
        assert dialog.selected_path() == ("data", "storage", "slots", 0)
        assert dialog.tree.hasFocus(), (app.applicationState(), app.activeWindow(), app.focusWidget())
        dialog.objects.setCurrentIndex(1)
        dialog.tabs.setCurrentIndex(1)
        wait_search(dialog)
        assert dialog.items.page.rows[0].columns[1] == "mod:gem"
        dialog.objects.setCurrentIndex(0)
        wait_search(dialog)
        assert dialog.items.page.rows[0].columns[2] == "9"
        received = []
        dialog.requested.connect(received.append)
        dialog.apply.click()
        assert len(received) == 1 and len(received[0]) == 1
        session.apply(edit_objects(session, received[0]))
        data = session.snapshot().block_nbt[(1, 1, 1)]
        assert data["energy"] == LongTag(9223372036854775807)
        assert data["storage"]["slots"][0]["components"]["keep"] == LongTag(9007199254740993)
        saved = output / "edited.nbt"
        session.save(saved)
        assert Structure(saved).block_nbt == session.snapshot().block_nbt
        session.undo()
        assert session.snapshot().block_nbt == source.block_nbt
        dialog.tabs.setCurrentIndex(2)
        dialog.text.setPlainText("{broken")
        dialog.text.document().setModified(True)
        dialog.tabs.setCurrentIndex(0)
        assert dialog.tabs.currentIndex() == 2 and dialog.errors.text()
        dialog.text.setPlainText(dialog.tree.root.to_snbt())
        dialog.text.document().setModified(True)
        dialog.tabs.setCurrentIndex(0)
        huge = CompoundTag({"slots": ListTag([CompoundTag({"id": StringTag(f"mod:item_{i}"), "count": IntTag(3)}) for i in range(300)])})
        dialog.tree.set_root(huge)
        dialog.tabs.setCurrentIndex(1)
        wait_search(dialog)
        assert dialog.items.page.total == 300 and len(dialog.items.page.rows) == 128
        dialog.items.next.click()
        wait_search(dialog)
        assert dialog.items.page.offset == 128
        for text in ("item 2", "missing", "item 299"):
            dialog.search.setText(text)
        wait_search(dialog)
        assert dialog.items.page.total == 1 and dialog.items.page.rows[0].columns[1] == "mod:item_299"
        dialog.open_value.setFocus()
        dialog.search.setText("missing")
        dialog.close()
        QTest.qWait(100)
        readonly = ObjectInspector(None, records, readonly=True)
        readonly.show()
        readonly.tabs.setCurrentIndex(1)
        wait_search(readonly)
        assert not readonly.apply.isEnabled() and not readonly.edit_count.isVisible()
        readonly.close()
        print(json.dumps(dict(search="fields, nested inventories, pagination, latest query", editing="typed values, validation, cancel",
                              preserved="Long precision and unknown mod fields", history="Apply, save, reopen, Undo",
                              screenshot=str(output / "inventory.png"))), flush=True)
    finally:
        app.closeAllWindows()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
