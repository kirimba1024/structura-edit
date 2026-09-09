import argparse
import json
from pathlib import Path

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QEvent, QSignalBlocker, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from structura_core import Structure, save_structure

from smoke_gui import screen, settle
from structura_edit.height_slice import HeightSlice
from structura_edit.ui import EditorWindow


def check_world(window, path):
    window.sources.open_path(path)
    settle(window)
    window.navigation.stop()
    with QSignalBlocker(window.slicing.y):
        window.slicing.y.setValue(int(window.document.session.center[1]) - 1)
    window.slicing.mode.setCurrentIndex(1)
    settle(window)
    assert window.minimap.cache.spec is None
    current = window.slicing.value
    submissions = []
    submit = window.views.submit
    def traced(kind, callback, **args):
        submissions.append(kind)
        return submit(kind, callback, **args)
    window.views.submit = traced
    try:
        window.world.refresh()
        settle(window)
    finally:
        window.views.submit = submit
    assert window.views.displayed.height == current
    assert "render" not in submissions
    assert not window.document.session.dirty and window.minimap.cache.spec is None
    window.slicing.mode.setCurrentIndex(0)
    window.minimap.set_large(True)
    settle(window)
    assert window.minimap.cache.spec is not None
    window.minimap.set_large(False)
    print("World slice: F5 preserves Y, reuses geometry, restores atlas on Show all; no save", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world", nargs="?")
    args = parser.parse_args()
    output = Path("/private/tmp/structura-height-smoke")
    output.mkdir(exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[8,48,8],
        palette:[{Name:"minecraft:stone"},{Name:"minecraft:oak_planks"}],blocks:[],
        entities:[{pos:[4d,1d,4d],blockPos:[4,1,4],nbt:{id:"minecraft:pig"}},
                  {pos:[4d,6d,4d],blockPos:[4,6,4],nbt:{id:"minecraft:chicken"}}]}'''))
    source.present = {(x, y, z): int(y == 5) for x in range(6) for z in range(6) for y in (0, 5)}
    source.present.update({(7, y, 7): 0 for y in range(40)})
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    original = path.read_bytes()
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.show()
    try:
        window.sources.open_path(path)
        settle(window)
        window.navigation.stop()
        window.plotter.camera.position = (3, 20, 3)
        window.plotter.camera.focal_point = (3, 0, 3)
        window.plotter.camera.up = (0, 0, -1)
        window.camera.needs_render = True
        window.camera.render()
        point = screen(window, (2, 0, 2))
        assert window.scene.hit_at(window.document.session, point).position == (2, 5, 2)
        viewport_size = window.plotter.size()
        camera = tuple(window.plotter.camera.position)
        control = window.slicing
        control.button.click()
        assert control.dialog.isVisible() and window.plotter.size() == viewport_size
        with QSignalBlocker(control.y):
            control.y.setValue(3)
        control.mode.setCurrentIndex(1)
        settle(window)
        assert window.views.displayed.height == HeightSlice("below", 3)
        assert len(window.scene.entity_bounds) == 1
        assert window.scene.hit_at(window.document.session, point).position == (2, 0, 2)
        QTest.mouseClick(window.plotter, Qt.MouseButton.LeftButton, pos=point)
        assert window.document.selected.region.lower == (2, 0, 2)
        assert window.plotter.size() == viewport_size
        assert np.allclose(window.plotter.camera.position, camera)
        control.y.setValue(2)
        window._tick()
        control.y.setValue(4)
        control.y.setValue(1)
        settle(window)
        assert window.views.displayed.height == HeightSlice("below", 1)
        control.mode.setCurrentIndex(2)
        settle(window)
        assert window.scene.hit_at(window.document.session, point) is None
        control.y.setValue(-20)
        settle(window)
        assert not window.scene.actors and not window.scene.entity_keys
        control.mode.setCurrentIndex(0)
        settle(window)
        assert window.scene.hit_at(window.document.session, point).position == (2, 5, 2)
        assert len(window.scene.entity_bounds) == 2
        control.use_camera()
        settle(window)
        assert window.views.displayed.height == HeightSlice("below", 20)
        control.dialog.grab().save(str(output / "height-control.png"))
        control.dialog.close()
        assert window.plotter.size() == viewport_size
        assert not window.document.session.dirty and not window.document.session.can_undo
        assert path.read_bytes() == original
        window._opened(window.document.session, preserve_focus=True, fit=False)
        settle(window)
        assert window.views.displayed.height == HeightSlice("below", 20)
        print(json.dumps(dict(height="all / below / single / empty / camera / refresh",
                              selection="cut surface through hidden roof", entities="visible anchors only",
                              viewport="stable size and camera", data="unchanged")), flush=True)
        if args.world:
            check_world(window, args.world)
    finally:
        window.document.load(None)
        window.close()
        window.deleteLater()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
