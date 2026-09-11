import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from amulet_nbt import from_snbt
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QFocusEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from structura_core import Structure, save_structure

from smoke_gui import screen, settle
from structura_edit import Condition, EditSession, Mix
from structura_edit.condition_ui import ConditionDialog
from structura_edit.drafts import list_drafts, restore_draft
from structura_edit.mix_ui import MixDialog
from structura_edit.picking import Hit
from structura_edit.ui import EditorWindow


def main():
    app = QApplication([])
    output = Path('/private/tmp/structura-improvements-smoke')
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='structura-new-features-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
        source = Structure.from_root(from_snbt('{DataVersion:3955,size:[9,4,11],palette:[{Name:"minecraft:air"}],blocks:[],entities:[]}'))
        edit = EditSession.from_structure(source)
        edit.apply(edit.fill(edit.select(((2, 0, 2), (7, 1, 9))), 'minecraft:stone'))
        path = root / 'plane.nbt'
        save_structure(edit.snapshot(), path, edit.size)
        window = EditorWindow(off_screen=os.environ.get("STRUCTURA_SMOKE_VISIBLE") != "1", cache_dir=root / 'cache')
        window.resize(960, 720)
        window.show()
        if os.environ.get("STRUCTURA_SMOKE_VISIBLE") == "1":
            window.raise_()
            window.activateWindow()
        try:
            window.drafts.last_attempt = monotonic() + 3600
            window.sources.open_path(path)
            settle(window)
            window.navigation.stop()
            window.planar.active = True
            window.planar.pick(Hit((2, 0, 2), (0, 1, 0)))
            settle(window)
            assert window.document.selected.current.volume == 35
            assert window.operation.current == 'Extrude'
            window.operation.fields['depth'].setValue(2)
            window.preview_operation()
            settle(window)
            assert window.document.pending.report.added == 70
            window.apply_pending()
            settle(window)
            assert window.document.session.can_undo
            window.undo()
            settle(window)
            window.selection_actions.set_bounds((2, 0, 2), (7, 1, 9))
            window.show_operation('Frame')
            window.operation.fields['target'].setText('minecraft:gold_block')
            window.preview_operation()
            settle(window)
            assert len(window.document.pending.changes) == 28
            window.grab().save(str(output / 'frame-review.png'))
            window.plotter.screenshot(str(output / 'frame-scene.png'))
            window.discard_pending()
            settle(window)
            window.panels.dismiss()
            window.placement.start('copy')
            settle(window)
            window.placement.start('paste')
            settle(window)
            window.placement.set_position((2, 1, 2))
            assert window.placement.bar.apply.text() == 'Place'
            window.placement_review.preview()
            settle(window)
            assert window.document.pending and not window.document.session.dirty
            assert window.placement_review.plan.change.report.added == 35
            window.placement.bar.grab().save(str(output / 'paste-review.png'))
            window.placement.bar.apply.click()
            settle(window)
            assert window.document.session.dirty
            window.undo()
            settle(window)
            window.selection_actions.set_bounds((2, 0, 2), (7, 1, 9))
            window.show_operation('Fill')
            window.operation.fields['target'].setText('minecraft:gold_block')
            window.panels.dismiss()
            window.plotter.camera.position = (4.5, 25, 5.5)
            window.plotter.camera.focal_point = (4.5, 0, 5.5)
            window.plotter.camera.up = (0, 0, -1)
            window.camera.needs_render = True
            window.camera.render()
            window.plotter.setFocus()
            window.paint.active = True
            window.menus.actions['paint'].setChecked(True)
            a, b = screen(window, (2, 0, 2)), screen(window, (6, 0, 8))
            QTest.mousePress(window.plotter, Qt.MouseButton.LeftButton, pos=a)
            assert window.paint.dragging
            QApplication.sendEvent(window.plotter, QFocusEvent(QEvent.Type.FocusOut))
            assert not window.paint.dragging and not window.document.session.dirty
            assert window.menus.actions['undo'].text() != 'Cancel stroke'
            window.plotter.setFocus()
            QTest.mousePress(window.plotter, Qt.MouseButton.LeftButton, pos=a)
            QTest.keyClick(window.plotter, Qt.Key.Key_Escape)
            assert not window.paint.dragging and not window.document.session.dirty
            QTest.mousePress(window.plotter, Qt.MouseButton.LeftButton, pos=a)
            QTest.mouseRelease(window.status, Qt.MouseButton.LeftButton)
            assert not window.paint.dragging and window.document.pending is None
            window.plotter.setFocus()
            QTest.mousePress(window.plotter, Qt.MouseButton.LeftButton, pos=a)
            event = QMouseEvent(QEvent.Type.MouseMove, QPointF(b), QPointF(window.plotter.mapToGlobal(b)),
                                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(window.plotter, event)
            QTest.mouseRelease(window.plotter, Qt.MouseButton.LeftButton, pos=b)
            settle(window)
            assert window.document.pending and window.document.pending.label == 'Paint stroke'
            window.apply_pending()
            settle(window)
            assert len(window.document.session.history.entries) == 1
            window.paint.toggle()
            window.drafts.save()
            settle(window)
            draft = list_drafts()[0]
            recovered = restore_draft(draft['path'])
            assert recovered.dirty and not recovered.can_undo
            assert recovered.state_at((2, 0, 2)) == 'minecraft:gold_block'
            window.tasks.submit('fragment_save', lambda _: None, session=window.document.session.fork(),
                                selection=window.document.selected.current, name='Wall module', tags=('test',), anchor=(0, 0, 0))
            settle(window)
            def choose_fragment():
                dialog = QApplication.activeModalWidget()
                if dialog is None:
                    QTimer.singleShot(50, choose_fragment)
                    return
                dialog.grab().save(str(output / 'fragment-library.png'))
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Open).click()
            QTimer.singleShot(100, choose_fragment)
            window.fragments.show()
            settle(window)
            assert window.placement.active and window.placement.clipboard.anchor == (0, 0, 0)
            window.placement.cancel()
            window.materials.show()
            settle(window)
            assert window.panels.materials.catalog
            window.panels.materials.search.setText('diamond')
            settle(window)
            window.grab().save(str(output / 'materials.png'))
            window.panels.dismiss()
            for name, dialog in (
                ('condition', ConditionDialog(window, Condition('all', (Condition('height', ('0', '80')), Condition('block-entities', negate=True))))),
                ('mix', MixDialog(window, Mix((('minecraft:stone', 1), ('minecraft:gold_block', 1)), anchor='world', gradient=(0, 80)))),
            ):
                dialog.show()
                app.processEvents()
                dialog.grab().save(str(output / (name + '.png')))
                dialog.close()
            report = {'planar': 35, 'extrude': 70, 'frame': 28, 'paste': 'optional Preview → Place',
                      'paint': 'Focus loss cancels; one stroke, one Undo', 'draft': 'Recovered without writing source',
                      'library': 'Named fragment with tags, thumbnail and anchor placed', 'catalog': len(window.panels.materials.catalog)}
            (output / 'result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
        finally:
            window.document.load(None)
            window.close()
            app.processEvents()


if __name__ == '__main__':
    main()
