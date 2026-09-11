import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from structura_core import save_structure

from building_fixture import building_source
from smoke_gui import settle
from structura_edit.ui import EditorWindow


def wait_for(predicate):
    deadline = monotonic() + 15
    while not predicate() and monotonic() < deadline:
        QTest.qWait(20)
    assert predicate()


def check_navigation(app):
    output = Path('/private/tmp/structura-navigation-smoke')
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='structura-navigation-') as temporary:
        root = Path(temporary)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
        path = root / 'building.nbt'
        source = building_source()
        save_structure(source, path, source.size)
        window = EditorWindow(cache_dir=root / 'cache')
        other = QWidget()
        other.setWindowTitle('Navigation focus check')
        window.resize(1104, 660)
        window.show()
        window.raise_()
        window.activateWindow()
        try:
            assert QTest.qWaitForWindowActive(window, 15000), 'Navigation requires an unlocked session and an active native window'
            window.sources.open_path(path)
            settle(window)
            view, navigation = window.plotter, window.navigation
            window.raise_()
            window.activateWindow()
            view.setFocus()
            wait_for(lambda: navigation.looking)
            QTest.keyClick(view, Qt.Key.Key_Escape)
            QTest.qWait(100)
            assert navigation.looking
            QTest.keyClick(view, Qt.Key.Key_QuoteLeft, Qt.KeyboardModifier.ShiftModifier)
            assert navigation.looking
            QTest.keyClick(view, Qt.Key.Key_Tab)
            QTest.qWait(100)
            assert not navigation.looking and not navigation.freelook
            wait_for(lambda: window.fly_button.text() == 'Look · Tab')
            window.statusBar().grab().save(str(output / 'cursor.png'))
            QTest.keyClick(view, Qt.Key.Key_Tab)
            wait_for(lambda: navigation.looking)
            wait_for(lambda: window.fly_button.text() == 'Cursor · Tab')
            window.statusBar().grab().save(str(output / 'freelook.png'))
            for point in ((8, 0, 8), (12, 0, 12)):
                view.camera.position = (point[0] + 0.5, 20, point[2] + 0.5)
                view.camera.focal_point = (point[0] + 0.5, 0, point[2] + 0.5)
                view.camera.up = (0, 0, -1)
                window.camera.needs_render = True
                if window.document.selected.anchor is not None:
                    QTest.keyPress(view, Qt.Key.Key_Shift)
                    navigation.tick(0.05)
                    preview = window.document.selected.preview
                    assert preview is not None and preview.volume == 25
                    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
                    QTest.keyRelease(view, Qt.Key.Key_Shift)
                    assert window.document.selection() == preview
                else:
                    navigation.tick(0.05)
                    QTest.mouseClick(view, Qt.MouseButton.LeftButton)
                    assert window.document.selected.anchor == point
                assert navigation.looking
            position = view.camera.position
            QTest.keyPress(view, Qt.Key.Key_W)
            QApplication.sendEvent(view, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab,
                                                   Qt.KeyboardModifier.ControlModifier))
            other.show()
            other.raise_()
            other.activateWindow()
            wait_for(lambda: other.isActiveWindow())
            QTest.qWait(100)
            assert not navigation.looking and not navigation.keys
            window.raise_()
            window.activateWindow()
            wait_for(lambda: navigation.looking)
            assert view.camera.position == position
            bar = window.menuBar()
            action = next(action for action in bar.actions() if action.text() == '&View')
            navigation.suspend()
            QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=bar.actionGeometry(action).center())
            wait_for(lambda: not navigation.looking)
            popup = QApplication.activePopupWidget()
            assert popup is not None
            popup.close()
            view.setFocus()
            wait_for(lambda: navigation.looking)
            window.minimap.set_large(True)
            assert not navigation.looking
            window.minimap.set_large(False)
            view.setFocus()
            wait_for(lambda: navigation.looking)
            window.show_operation('Fill')
            field = window.operation.fields['target']
            field.setFocus()
            field.selectAll()
            QTest.keyClicks(field, 'minecraft:stone')
            assert field.text() == 'minecraft:stone' and not navigation.looking
            popup = app.activePopupWidget()
            if popup is not None:
                popup.close()
            window.panels.close('operation')
            wait_for(lambda: navigation.looking)
            window.placement.start('take')
            settle(window)
            assert navigation.looking and window.placement.active
            QTest.keyClick(view, Qt.Key.Key_Escape)
            assert navigation.looking and not window.placement.active
            assert window.fly_button.isVisible()
            assert window.fly_button.fontMetrics().horizontalAdvance('Cursor · Tab') < window.fly_button.width() - 16
            print(json.dumps(dict(freelook='Tab toggles, Escape and Take keep looking', shift='crosshair preview and region',
                                  focus='window, menu, map, text field', saved=False)), flush=True)
        except BaseException:
            print(dict(application=str(app.applicationState()), active=window.isActiveWindow(),
                       focus=str(app.focusWidget()), popup=str(app.activePopupWidget()),
                       enabled=window.navigation.enabled, freelook=window.navigation.freelook,
                       looking=window.navigation.looking, buttons=str(app.mouseButtons())), flush=True)
            raise
        finally:
            other.close()
            window.document.load(None)
            window.close()
            app.processEvents()


def main():
    app = QApplication([])
    failures = []
    def check():
        try:
            check_navigation(app)
        except BaseException as error:
            failures.append(error)
        finally:
            app.quit()
    QTimer.singleShot(100, check)
    app.exec()
    if failures:
        raise failures[0]


if __name__ == '__main__':
    main()
