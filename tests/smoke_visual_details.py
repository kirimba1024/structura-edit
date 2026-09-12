import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QEvent, QPointF
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import settle
from smoke_overview import wait_until
from structura_edit.resources import texture_bank
from structura_edit.ui import EditorWindow


def main():
    app = QApplication([])
    output = Path('/private/tmp/structura-visual-details')
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='structura-visual-details-') as directory:
        root = Path(directory)
        os.environ['STRUCTURA_EDIT_DATA'] = str(root / 'data')
        source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[4,3,4],
            palette:[{Name:"minecraft:coal_ore"},{Name:"minecraft:gold_block"}],blocks:[],
            entities:[{pos:[1.5d,1d,1.5d],blockPos:[1,1,1],nbt:{id:"minecraft:pig"}}]}'''))
        source.present = {(x, 0, z): int(x == z == 3) for x in range(4) for z in range(4)}
        path = root / 'source.nbt'
        save_structure(source, path, source.size)
        window = EditorWindow(cache_dir=root / 'maps')
        window.resize(1200, 780)
        window.show()
        report = {}
        try:
            window.sources.open_path(path)
            settle(window)
            window.navigation.stop()
            card = window.inspection
            card.rotate.setChecked(True)
            def select(position):
                start = perf_counter()
                window.selection_actions.set_bounds(position, tuple(v + 1 for v in position))
                wait_until(lambda: card.key is not None and card.ready_key == card.key and card.has_geometry, 15)
                return (perf_counter() - start) * 1000
            report['first_preview_ms'] = select((0, 0, 0))
            coal_actors = card.scene.entries[card.scene.current][0]
            viewport = card.preview
            report['other_preview_ms'] = select((3, 0, 3))
            report['cached_preview_ms'] = select((1, 0, 0))
            assert card.preview is viewport and card.scene.entries[card.scene.current][0] == coal_actors
            card.preview._render()
            preview_pixels = card.preview.screenshot(str(output / 'preview.png'))
            assert np.unique(preview_pixels.reshape(-1, preview_pixels.shape[-1]), axis=0).shape[0] > 16
            card.grab().save(str(output / 'inspection.png'))
            window.document.selected.clear()
            window._selection_changed()
            minimap, canvas = window.minimap, window.minimap.canvas
            minimap.maps.automatic = minimap.maps.sliced = False
            minimap.maps.update()
            minimap.set_large(True)
            canvas.layout.focused = 'top'
            canvas.layout.centers['top'] = QPointF(2, 2)
            canvas.layout.panned.add('top')
            minimap._update_layout()
            canvas.view_changed.emit()
            wait_until(lambda: 'top' in canvas.details and canvas.entity_icons.get('top', False), 15)
            renderer = minimap.maps.previous[1]
            pixels = renderer.details((('top', (0, 0, 4, 4)),))['top'][1]
            original = np.asarray(texture_bank(None).resolve('minecraft:coal_ore')['all'].convert('RGB'))
            assert np.array_equal(pixels[:16, :16], original)
            assert canvas.entity_mode == 'Auto' and len(canvas.entities) == 1
            assert canvas.entities[0][3] is not None and not canvas.entities[0][3].isNull()
            canvas.grab().save(str(output / 'map.png'))
            report.update(original_texture_pixels=True, pig_icon=True, preview_viewport_reused=True, preview_actors_reused=True)
            assert not window.issues, window.issues
            (output / 'result.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(report), flush=True)
        finally:
            window.document.load(None)
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()


if __name__ == '__main__':
    main()
