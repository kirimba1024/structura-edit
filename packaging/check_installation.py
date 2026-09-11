import argparse
import json
import os
import sys
import traceback
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def settle(window, timeout=90):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    deadline = monotonic() + timeout
    while monotonic() < deadline:
        QApplication.processEvents()
        window._tick()
        if (not window.tasks.busy and not window.views.render_queued and window.world.queued is None
                and (not window.views.map_queued or window.minimap.collapsed) and not window.minimap.maps.busy):
            return
        QTest.qWait(10)
    raise RuntimeError(f'Installation check timed out: {window.status.text()}')


def exercise(output, root):
    from amulet_nbt import CompoundTag, IntTag, ListTag, from_snbt
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication
    from structura_core import Structure, save_structure
    from structura_edit.ui import EditorWindow
    from smoke_overview import run as check_overview

    app = QApplication([])
    assets = root / 'assets' / 'minecraft'
    assets.mkdir(parents=True)
    window = EditorWindow(assets=assets, cache_dir=root / 'cache')
    window.resize(1104, 720)
    window.show()
    window.drafts.last_attempt = monotonic() + 3600
    try:
        demo = Path(str(files('structura_render').joinpath('data/examples/demo.nbt')))
        require(demo.is_file(), 'Bundled example is missing')
        window.sources.open_path(demo)
        settle(window)
        require(window.document.session is not None and window.views.ready, window.status.text())
        require(bool(window.scene.sections), 'Example did not produce geometry')
        window.navigation.stop()
        QApplication.processEvents()
        window.grab().save(str(output / 'example.png'))
        pixels = window.plotter.screenshot(str(output / 'scene.png'))
        require(pixels is not None and int(pixels.max()) > int(pixels.min()), 'Scene framebuffer is empty')
        data = from_snbt('{DataVersion:3955,size:[70,2,2],palette:[{Name:"minecraft:chest"}],blocks:[],entities:[]}')
        data['blocks'] = ListTag([CompoundTag({
            'pos': ListTag([IntTag(x), IntTag(0), IntTag(0)]), 'state': IntTag(0),
            'nbt': from_snbt('{id:"minecraft:chest",Items:[{Slot:0b,id:"minecraft:diamond",count:3b}]}'),
        }) for x in range(70)])
        source = Structure.from_root(data)
        path = root / 'source.nbt'
        save_structure(source, path, source.size)
        original = path.read_bytes()
        window.sources.open_path(path)
        settle(window)
        require(window.document.session.path == path and window.views.ready, window.status.text())
        window.navigation.stop()
        window.batch_nbt.open(dict(text='chest', kind='data', selection=None))
        settle(window)
        dialog = window.batch_nbt.dialog
        require(dialog is not None and len(window.batch_nbt.targets.rows) == 70, 'Batch targets were not collected')
        dialog.path.setText('/Items/0/count')
        dialog.value.setPlainText('7')
        dialog.preview.click()
        settle(window)
        require(len(window.document.pending or ()) == 70 and dialog.apply.isEnabled(), window.status.text())
        dialog.grab().save(str(output / 'batch.png'))
        dialog.apply.click()
        settle(window)
        require(window.document.session.history.cursor == 1, 'Batch edit did not create one history entry')
        saved = root / 'saved.nbt'
        window.sources.save_path(saved)
        settle(window)
        require(saved.is_file(), window.status.text())
        require(all(int(nbt['Items'][0]['count']) == 7 for nbt in Structure(saved).block_nbt.values()), 'Saved values differ')
        window.undo()
        settle(window)
        require(window.document.session.snapshot().block_nbt == source.block_nbt, 'Undo did not restore the source')
        require(path.read_bytes() == original, 'The input file changed')
        window.hide()
        overview = check_overview(output / 'overview.json', visible=True, assets=assets)
        return dict(example=str(demo), objects=70, assets='Empty directory: fallback rendering',
                    overview=overview,
                    checks=['Bundled example', 'Qt and VTK scene', 'Worker spawn', 'NBT batch preview',
                            'Apply', 'Save and reload', 'Undo', 'World overview and native QEM',
                            'Teleport and cancellation', 'Load here', 'World map zoom'])
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check the installed application using temporary documents and local data')
    parser.add_argument('output', type=Path)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
    result = dict(frozen=bool(getattr(sys, 'frozen', False)), executable=sys.executable)
    try:
        result['versions'] = {name: version(name) for name in ('structura-edit', 'structura-core', 'structura-render',
                                                             'PySide6-Essentials', 'vtk', 'meshoptimizer')}
        with TemporaryDirectory(prefix='structura-installation-') as temporary:
            root = Path(temporary).resolve()
            os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'local')
            os.environ['AMULET_LEVEL_CACHE_DIR'] = str(root / 'amulet')
            result.update(exercise(output, root), status='passed')
    except Exception:
        result.update(status='failed', error=traceback.format_exc())
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
