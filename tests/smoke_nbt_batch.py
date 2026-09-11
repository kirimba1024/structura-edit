import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from nbt_batch_fixture import batch_structure
from smoke_gui import settle
from smoke_object_search import query, wait_search
from structura_edit.ui import EditorWindow


def main():
    output = Path('/private/tmp/structura-nbt-batch')
    output.mkdir(exist_ok=True)
    app = QApplication([])
    with TemporaryDirectory(prefix='structura-nbt-batch-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
        source = batch_structure()
        path = root / 'source.nbt'
        save_structure(source, path, source.size)
        original = path.read_bytes()
        window = EditorWindow(off_screen=False, cache_dir=root / 'cache')
        window.resize(1104, 720)
        window.show()
        window.drafts.last_attempt = monotonic() + 3600
        try:
            window.sources.open_path(path)
            settle(window)
            window.navigation.stop()
            window.objects.finder.show()
            query(window, 'chest', 'data')
            finder = window.objects.finder
            assert finder.result.total == 150 and len(finder.result.rows) == 64
            finder.panel.next.click()
            wait_search(window)
            assert finder.result.offset == 64
            finder.panel.batch.click()
            settle(window)
            dialog = window.batch_nbt.dialog
            assert dialog is not None and len(window.batch_nbt.targets.rows) == 150
            dialog.path.setText('/id')
            dialog.value.setPlainText('minecraft:stone')
            dialog.preview.click()
            settle(window)
            assert window.document.pending is None and 'Identity and position' in dialog.summary.text()
            dialog.path.setText('/Items/0/count')
            dialog.value.setPlainText('7')
            dialog.preview.click()
            settle(window)
            assert window.document.preview.kind == 'nbt_batch'
            assert len(window.document.pending) == 150 and dialog.apply.isEnabled()
            assert '150 changed' in dialog.summary.text()
            assert not window.document.session.dirty
            dialog.grab().save(str(output / 'preview.png'))
            dialog.value.setPlainText('8')
            assert window.document.pending is None and not dialog.apply.isEnabled()
            settle(window)
            dialog.preview.click()
            settle(window)
            dialog.apply.click()
            settle(window)
            assert window.batch_nbt.dialog is None and window.document.session.history.cursor == 1
            assert all(int(payload['Items'][0]['count']) == 8 for payload in window.document.session.snapshot().block_nbt.values())
            saved = root / 'saved.nbt'
            window.sources.save_path(saved)
            settle(window)
            assert all(int(payload['Items'][0]['count']) == 8 for payload in Structure(saved).block_nbt.values())
            window.undo()
            settle(window)
            assert window.document.session.snapshot().block_nbt == source.block_nbt
            wait_search(window)
            finder.panel.batch.click()
            settle(window)
            dialog = window.batch_nbt.dialog
            dialog.path.setText('/custom')
            dialog.value.setPlainText('100')
            dialog.preview.click()
            assert window.tasks.kind == 'nbt_batch'
            QTest.keyClick(dialog.path, Qt.Key.Key_Escape)
            settle(window)
            assert window.batch_nbt.dialog is None and window.document.pending is None
            assert window.document.session.snapshot().block_nbt == source.block_nbt
            assert path.read_bytes() == original
            result = dict(objects=150, page_size=64, preview='all pages, independent of active page; stale preview invalidated',
                          apply='single Undo; types, metadata and saved NBT retained', cancel='Escape cancels in-flight calculation')
            (output / 'result.json').write_text(json.dumps(result, indent=2))
            print(json.dumps(result), flush=True)
        finally:
            window.document.load(None)
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == '__main__':
    main()
