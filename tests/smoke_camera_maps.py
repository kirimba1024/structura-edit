import json
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from amulet_nbt import from_snbt
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPlainTextEdit
from structura_core import Structure, save_structure

from smoke_gui import settle
from structura_edit import error_details
from structura_edit.map_projection import VIEWS
from structura_edit.ui import EditorWindow


def centered(canvas):
    for view in VIEWS:
        assert (canvas.screen_point(canvas.position, view) - canvas.tile_rect(view).center()).manhattanLength() < 1e-6


def check_maps(window, output):
    minimap, canvas = window.minimap, window.minimap.canvas
    window.move_camera((8.5, 2.5, 8.5))
    settle(window)
    centered(canvas)
    assert canvas.map_cut == (8, 2, 8)
    assert not np.array_equal(canvas.image_pixels["top"], canvas.image_pixels["bottom"])
    before = canvas.image_pixels.copy()
    renderer = minimap.maps.previous[1]
    window.move_camera((8.9, 2.9, 8.9))
    settle(window)
    assert minimap.maps.previous[1] is renderer
    assert all(canvas.image_pixels[view] is before[view] for view in VIEWS)
    window.move_camera((9.1, 2.9, 8.9))
    assert not window.worker.busy
    settle(window)
    assert {view for view in VIEWS if before[view] is not canvas.image_pixels[view]} == {"west", "east"}
    centered(canvas)
    minimap.grab().save(str(output / "minimap.png"))
    viewport = window.plotter.geometry()
    minimap.set_large(True)
    settle(window)
    centered(canvas)
    assert window.plotter.geometry() == viewport
    minimap.grab().save(str(output / "map.png"))
    canvas.layout.pan("top", QPointF(60, 40))
    canvas.view_changed.emit()
    assert canvas.screen_point(canvas.position, "top") != canvas.tile_rect("top").center()
    minimap.set_large(False)
    settle(window)
    centered(canvas)


def check_counts_and_guides(window, output):
    window.selection_actions.select_all()
    stats = window.placement.bar.stats
    stats.toggle.click()
    until = monotonic() + 8
    while stats.ready_key != stats.key and monotonic() < until:
        QTest.qWait(25)
    assert stats.ready_key == stats.key and stats.model.rowCount() == 2
    QTest.qWait(50)
    assert stats.rect().contains(stats.info.geometry()) and stats.rect().contains(stats.items.geometry())
    assert not stats.info.geometry().intersects(stats.items.geometry())
    assert "no air" not in stats.info.text() and "loaded" not in stats.info.text()
    assert "Empty space" in stats.info.toolTip()
    assert stats.items.gridSize().width() < 80
    assert "minecraft:" in stats.model.item(0).toolTip()
    stats.grab().save(str(output / "counts.png"))
    window.guides.update(window.session, bounds=False, chunks=True)
    assert len(window.guides.actors) == 1
    style = window.guides.actors[0].GetProperty()
    assert style.GetLineWidth() == 2 and np.isclose(style.GetOpacity(), 0.35)


def check_error_copy(window, output):
    copied, failures = [], []
    message = "ImportError: cannot import name 'example'\nFull details stay selectable and copyable."
    window._error(message)
    assert window.error_button.isVisible()
    def interact():
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog.findChild(QPlainTextEdit).toPlainText() == message
            buttons = dialog.findChild(QDialogButtonBox)
            next(button for button in buttons.buttons() if button.text() == "Copy error").click()
            dialog.grab().save(str(output / "error.png"))
        except Exception as error:
            failures.append(error)
        finally:
            dialog.reject()
    with patch.object(error_details, "QApplication", SimpleNamespace(clipboard=lambda: SimpleNamespace(setText=copied.append))):
        QTimer.singleShot(50, interact)
        window.error_button.click()
    assert copied == [message] and not failures


def main():
    output = Path("/private/tmp/structura-camera-maps")
    output.mkdir(parents=True, exist_ok=True)
    source = Structure.from_root(from_snbt('''{DataVersion:3955,size:[16,8,16],
        palette:[{Name:"minecraft:grass_block"},{Name:"minecraft:stone"}],blocks:[],entities:[]}'''))
    source.present = {(x, y, z): int(y == 5) for x in range(16) for z in range(16) for y in (0, 5)}
    path = output / "source.nbt"
    save_structure(source, path, source.size)
    app = QApplication([])
    window = EditorWindow(off_screen=True, cache_dir=output / "cache")
    window.show()
    try:
        window.open_path(path)
        settle(window)
        window.navigation.stop()
        check_maps(window, output)
        check_counts_and_guides(window, output)
        check_error_copy(window, output)
        assert not window.session.dirty
        report = dict(maps="camera centered in all views, camera cuts, unchanged axes reused, M pan and return",
                      counts="compact cells, hover names and IDs, no ambiguous no air", guides="2 px, 35% opacity",
                      errors="visible Error button, full selectable text, Copy error")
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.session = None
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


if __name__ == "__main__":
    main()
