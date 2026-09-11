import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import qVersion
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from smoke_gui import settle
from smoke_navigation import wait_for
from smoke_world_edit import create_world
from structura_edit.ui import EditorWindow


class InspectionWindow(EditorWindow):
    def _saved(self, session):
        super()._saved(session)
        print(json.dumps(dict(stage='saved', dirty=session.dirty, qt=qVersion())), flush=True)


def main():
    app = QApplication([])
    with TemporaryDirectory(prefix='structura-accessibility-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
        world = root / 'world'
        world.mkdir()
        create_world(world)
        window = InspectionWindow(cache_dir=root / 'cache')
        window.world.radius = 0
        window.show()
        window.raise_()
        window.activateWindow()
        try:
            window.sources.open_path(world)
            settle(window)
            window.navigation.stop()
            y = -window.document.session.origin[1]
            window.selection_actions.set_bounds((1, y, 1), (4, y + 1, 4))
            window.show_operation('Fill')
            window.operation.fields['target'].setText('minecraft:gold_block')
            window.preview_operation()
            settle(window)
            window.apply_pending()
            settle(window)
            window.navigation.stop()
            window.panels.dismiss()
            window.objects.inspect()
            wait_for(lambda: not window.objects.region_dialog.timer.isActive())
            QTest.qWait(100)
            print(json.dumps(dict(stage='ready', qt=qVersion(), world=str(world))), flush=True)
            app.exec()
        finally:
            window.document.load(None)
            window.close()


if __name__ == '__main__':
    main()
