import argparse
import json
import faulthandler
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from PySide6.QtCore import QEventLoop, QPoint, QRect, QTimer
from PySide6.QtWidgets import QApplication
from amulet_nbt import from_snbt
from structura_core import Structure
from structura_edit.ui import EditorWindow
from structura_edit import EditSession


def wait_for(predicate, timeout=40):
    loop = QEventLoop()
    success = []
    poll = QTimer()
    def check():
        if predicate():
            success.append(True)
            loop.quit()
    poll.timeout.connect(check)
    poll.start(20)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout * 1000)
    loop.exec()
    poll.stop()
    timer.stop()
    assert success, 'Timeout'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--visible', action='store_true')
    args = parser.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(30, exit=True)
    app = QApplication([])
    output = Path('/private/tmp/structura-review')
    output.mkdir(exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[20,8,16],palette:[{Name:"minecraft:stone"},{Name:"minecraft:chest",Properties:{facing:"north"}}],blocks:[{pos:[8,1,8],state:1,nbt:{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}}],entities:[{pos:[10.5d,1d,8.5d],blockPos:[10,1,8],nbt:{id:"minecraft:armor_stand",CustomName:'{"text":"Test guide"}',Health:20f,ShowArms:1b}}]}'''))
    source.present.update({(x,0,z):0 for x in range(20) for z in range(16)})
    with TemporaryDirectory(prefix='structura-review-') as temp:
        os.environ['STRUCTURA_EDIT_DATA'] = str(Path(temp) / 'data')
        window = EditorWindow(off_screen=not args.visible, cache_dir=Path(temp)/'maps', world_radius=1)
        window.setWindowTitle("Structura · feedback smoke · closes automatically")
        window.show()
        window.camera.move_to((100000,100000,100000))
        print('opened', flush=True)
        window._opened(EditSession.from_structure(source))
        try:
            wait_for(lambda: window.views.ready and not window.tasks.busy)
            assert max(abs(v) for v in window.plotter.camera.position) < 100
            assert 'Move blocks' not in window.menus.actions
            window.document.selected.select_block((8,1,8))
            window._selection_changed()
            print('waiting card', flush=True)
            wait_for(lambda: window.inspection.ready_key == window.inspection.key)
            print('card ready', flush=True)
            assert window.inspection.has_geometry, window.inspection.note.toolTip()
            assert window.inspection.title.text() == 'Chest'
            assert window.overlay.block_label == 'Chest'
            assert '1×1×1' not in window.status.text()
            assert not window.placement.bar.size_label.isVisible()
            wait_for(lambda: window.inspection.preview.isVisible())
            window.grab().save(str(output/'block-card.png'))
            window.inspection.preview.screenshot(str(output/'preview-block.png'))
            window.objects.keys = {'entity:0'}
            window.objects.refresh()
            window._sync()
            print('waiting card', flush=True)
            wait_for(lambda: window.inspection.ready_key == window.inspection.key)
            print('card ready', flush=True)
            assert window.inspection.title.text() == 'Test guide'
            assert window.inspection.has_geometry, window.inspection.note.toolTip()
            window.grab().save(str(output/'entity-card.png'))
            window.inspection.preview.screenshot(str(output/'preview-entity.png'))
            window.objects.reset()
            window.document.selected.select_all()
            window._selection_changed()
            print('waiting card', flush=True)
            wait_for(lambda: window.inspection.ready_key == window.inspection.key)
            print('card ready', flush=True)
            window.resize(1104, 660)
            wait_for(lambda: all(window.placement.bar.rect().contains(QRect(button.mapTo(window.placement.bar, QPoint()), button.size())) for button in window.placement.bar.action_widgets))
            window.grab().save(str(output/'area-card-narrow.png'))
            window.document.selected.select_block((8,1,8))
            window._selection_changed()
            window.placement.start('duplicate')
            wait_for(lambda: window.placement.active and not window.tasks.busy)
            window.grab().save(str(output/'placement.png'))
            window.placement.cancel()
            window._sync()
            panel = window.panels.materials
            panel.catalog = {f'example:block_{i}': f'Block {i}' for i in range(20000)}
            timings = []
            for i in range(3):
                begin = perf_counter()
                window.materials.show()
                app.processEvents()
                timings.append(perf_counter()-begin)
                window.panels.dismiss()
            (output/'timings.json').write_text(json.dumps({'materials_20000_rows_seconds':timings},indent=2))
            print(json.dumps({'materials_20000_rows_seconds':timings}), flush=True)
            assert not window.issues, window.issues
        finally:
            window.tasks.close()
            window.exit.approved = True
            window.document.load(None)
            window.placement.cancel()
            window.close()
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
