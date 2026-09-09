import argparse
import json
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QNativeGestureEvent, QPointingDevice, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from smoke_gui import check_map_proportions, mouse_move, settle
from structura_edit.map_projection import VIEWS
from structura_edit.loading import MAP_TILE_SIZE
from structura_edit.ui import EditorWindow


def check_map(window, output):
    minimap, canvas = window.minimap, window.minimap.canvas
    view = window.plotter
    renderer = minimap.maps.previous[1]
    camera = view.camera.position
    window.selection_actions.select_all()
    selection = window.document.selection()
    view.setFocus()
    QTest.keyPress(view, Qt.Key.Key_W)
    QTest.keyClick(view, Qt.Key.Key_M)
    QApplication.processEvents()
    assert minimap.large and not window.navigation.keys
    QTest.keyRelease(minimap, Qt.Key.Key_W)
    assert minimap.size() == view.size()
    QTest.keyPress(minimap, Qt.Key.Key_W)
    QTest.qWait(120)
    QTest.keyRelease(minimap, Qt.Key.Key_W)
    assert view.camera.position == camera
    settle(window)
    assert minimap.maps.previous[1] is renderer
    images = dict(canvas.images)
    minimap.grab().save(str(output / "map-six.png"))
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=canvas.tile_rect("top").center().toPoint())
    assert canvas.layout.focused == "top"
    check_map_proportions(canvas)
    assert all(canvas.tile_rect(v).width() == canvas.tile_rect(v).height() for v in VIEWS if v != "top")
    assert canvas.tile_rect("top").height() > sum(canvas.tile_rect(v).height() for v in VIEWS if v != "top")
    center = canvas.tile_rect("top").center().toPoint()
    before = canvas.layout.area("top")
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=center)
    mouse_move(canvas, center + QPoint(80, 35), Qt.MouseButton.LeftButton)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=center + QPoint(80, 35))
    assert canvas.layout.area("top").center() != before.center()
    point = QPointF(center + QPoint(100, -50))
    anchor = canvas.layout.from_screen(point, "top")
    wheel = QWheelEvent(point, QPointF(canvas.mapToGlobal(point.toPoint())), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(canvas, wheel)
    assert (canvas.layout.from_screen(point, "top") - anchor).manhattanLength() < 1e-8
    scale = canvas.layout.area("top").size()
    wheel = QWheelEvent(point, QPointF(canvas.mapToGlobal(point.toPoint())), QPoint(60, 24), QPoint(0, 120),
                       Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, True)
    QApplication.sendEvent(canvas, wheel)
    assert canvas.layout.area("top").size() == scale
    assert (canvas.layout.to_screen(anchor, "top") - point - QPointF(60, 24)).manhattanLength() < 1e-8
    anchor = canvas.layout.from_screen(point, "top")
    pinch = QNativeGestureEvent(Qt.NativeGestureType.ZoomNativeGesture, QPointingDevice.primaryPointingDevice(), 2,
                                point, point, QPointF(canvas.mapToGlobal(point.toPoint())), 0.25, QPointF())
    QApplication.sendEvent(canvas, pinch)
    assert canvas.layout.area("top").width() < scale.width()
    assert (canvas.layout.from_screen(point, "top") - anchor).manhattanLength() < 1e-8
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=canvas.tile_rect("north").center().toPoint())
    assert canvas.layout.focused == "north"
    minimap.grab().save(str(output / "map-focused.png"))
    QTest.mouseClick(minimap.header, Qt.MouseButton.LeftButton)
    assert canvas.layout.focused is None
    window.resize(1071, 711)
    QApplication.processEvents()
    assert minimap.size() == view.size()
    QTest.keyClick(minimap, Qt.Key.Key_Escape)
    assert not minimap.large and view.hasFocus()
    assert window.document.selection() == selection and view.camera.position == camera
    assert all(canvas.images[key] is image for key, image in images.items())
    settle(window)
    assert minimap.maps.previous[1] is renderer
    for name in VIEWS:
        assert (canvas.screen_point(canvas.position, name) - canvas.tile_rect(name).center()).manhattanLength() < 1e-6
    assert not window.tasks.busy and not window.views.map_queued
    QTest.mouseClick(minimap.header, Qt.MouseButton.LeftButton)
    assert minimap.collapsed
    QTest.keyClick(view, Qt.Key.Key_M)
    assert minimap.large and not minimap.collapsed
    QTest.keyClick(minimap, Qt.Key.Key_M)
    assert not minimap.large and minimap.collapsed
    QTest.mouseClick(minimap.header, Qt.MouseButton.LeftButton)
    window.show_recipe()
    code = window.panels.recipe.code
    code.clear()
    QTest.keyClicks(code, "mwasd")
    assert code.toPlainText() == "mwasd" and not minimap.large
    window.panels.dismiss()
    window.resize(1380, 880)


def check_progress(window):
    window.tasks.submit("recipe", lambda result: None, session=window.document.session.fork(), selection=window.document.session.select(),
                code="import time\ntime.sleep(5)")
    assert not window.progress.isVisible()
    QTest.qWait(450)
    assert window.progress.isVisible() and window.progress.bar.maximum() == 0
    QTest.mouseClick(window.progress.cancel, Qt.MouseButton.LeftButton)
    settle(window)
    assert not window.progress.isVisible() and not window.document.session.dirty


def settle_cache(cache):
    end = time.monotonic() + 10
    while time.monotonic() < end:
        QApplication.processEvents()
        if not cache.timer.isActive():
            return
        QTest.qWait(10)
    raise AssertionError("Map cache did not settle")


def check_atlas(window, output):
    minimap, canvas = window.minimap, window.minimap.canvas
    minimap.set_large(True)
    settle(window)
    first = minimap.cache.spec
    assert first is not None and minimap.cache.path.is_file()
    canvas.layout.focused = "top"
    canvas.layout.zoom["top"] = 0.25
    x, _, z = first["origin"]
    canvas.layout.centers["top"] = QPointF(x + 72, z + 24)
    canvas.layout.panned.add("top")
    canvas.view_changed.emit()
    settle_cache(minimap.cache)
    def cached_pixel():
        for (view, left, top), image in canvas.tiles.items():
            if view == "top" and left <= x + 8 < left + MAP_TILE_SIZE and top <= z + 8 < top + MAP_TILE_SIZE:
                scale = image.width() // MAP_TILE_SIZE
                return image.pixelColor((x + 8 - left) * scale, (z + 8 - top) * scale)
        raise AssertionError("Previously visited area is missing from the map")
    original = cached_pixel()
    assert original.alpha() == 255
    area = canvas.layout.area("top")
    window.world.center = tuple(p + (96 if axis == 0 else 0) for axis, p in enumerate(window.document.session.center))
    window.world.radius = 0
    window.world.request(recenter=True)
    settle(window)
    settle_cache(minimap.cache)
    assert minimap.cache.spec["space"] == first["space"]
    assert minimap.cache.spec["slabs"]["top"] == first["slabs"]["top"]
    assert canvas.layout.area("top") == area
    assert cached_pixel() == original
    assert not window.navigation.enabled
    minimap.grab().save(str(output / "map-world-cache.png"))
    minimap.set_large(False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--output", type=Path, default=Path("/private/tmp/structura-map-smoke"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=args.output / "cache")
    window.show()
    QApplication.setActiveWindow(window)
    try:
        window.sources.open_path(args.path)
        settle(window)
        check_map(window, args.output)
        if window.world.active:
            check_atlas(window, args.output)
        check_progress(window)
        assert np.isfinite(window.plotter.camera.position).all()
        result = dict(map="M/Escape, centered compact views, focus switching, pan, wheel/pinch anchored zoom, trackpad scroll, resize, no flight or scene rebuilds",
                      focus="M types normally in text fields; closing restores viewport focus",
                      progress="delayed busy indicator, cancellation, no document changes")
        if window.world.active:
            result["atlas"] = "previous area retained after F5; pan and zoom preserved when changing world radius"
        (args.output / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        window.document.load(None)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
