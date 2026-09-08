import argparse
import json
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFocusEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QToolBar, QToolButton

from structura_edit.ui import EditorWindow


def settle(window, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QApplication.processEvents()
        window._tick()
        if (not window.worker.busy and window.world.queued is None and not window.views.render_queued
                and (not window.views.map_queued or window.minimap.collapsed)):
            return
        QTest.qWait(10)
    raise AssertionError(f"GUI task timed out: {window.status.text()}")


def screen(window, position):
    renderer = window.plotter.renderer
    renderer.SetWorldPoint(*(v + 0.5 for v in position), 1)
    renderer.WorldToDisplay()
    x, y, _ = renderer.GetDisplayPoint()
    width, height = window.plotter.render_window.GetSize()
    return QPoint(round(x * window.plotter.width() / width),
                  round(window.plotter.height() - (y + 1) * window.plotter.height() / height))


def mouse_move(view, point, buttons=Qt.MouseButton.NoButton, modifiers=Qt.KeyboardModifier.NoModifier):
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(point), QPointF(view.mapToGlobal(point)),
                        Qt.MouseButton.NoButton, buttons, modifiers)
    QApplication.sendEvent(view, event)


def check_navigation(window):
    view, navigation = window.plotter, window.navigation
    window.fit_scene()
    angle = view.camera.view_angle
    start = np.asarray(view.camera.position)
    QTest.keyPress(view, Qt.Key.Key_W)
    QTest.qWait(180)
    middle = np.asarray(view.camera.position)
    QTest.qWait(180)
    assert np.linalg.norm(middle - start) > 0.1
    assert np.linalg.norm(np.asarray(view.camera.position) - middle) > 0.1
    QTest.keyRelease(view, Qt.Key.Key_W)
    stopped = view.camera.position
    QTest.qWait(100)
    assert view.camera.position == stopped
    QTest.keyPress(view, Qt.Key.Key_W)
    QApplication.sendEvent(view, QFocusEvent(QEvent.Type.FocusOut))
    QTest.qWait(50)
    assert not navigation.keys and view.camera.position == stopped
    direction = view.camera.direction
    point = QPoint(100, 100)
    QTest.mousePress(view, Qt.MouseButton.RightButton, pos=point)
    mouse_move(view, point + QPoint(100, -30), Qt.MouseButton.RightButton)
    QTest.qWait(50)
    assert view.camera.position == stopped
    assert not np.allclose(view.camera.direction, direction)
    QTest.mouseRelease(view, Qt.MouseButton.RightButton, pos=point + QPoint(100, -30))
    assert not navigation.looking and QApplication.activePopupWidget() is None
    direction = view.camera.direction
    mouse_move(view, point)
    QTest.qWait(50)
    assert view.camera.direction == direction
    assert not view.camera.parallel_projection and view.camera.view_angle == angle


def check_selection(window):
    from structura_edit.picking import EMPTY

    sx, sy, sz = window.session.size
    window.plotter.camera.position = (sx / 2, sy + max(sx, sy, sz) * 2, sz / 2)
    window.plotter.camera.focal_point = (sx / 2, sy / 2, sz / 2)
    window.plotter.camera.up = (0, 0, -1)
    window.camera.needs_render = True
    window.camera.render()
    columns = {}
    for x, y, z in window.session.positions():
        if window.session.state_at((x, y, z)).split("[", 1)[0] not in EMPTY:
            columns[x, z] = max(y, columns.get((x, z), y))
    points = [(x, y, z) for (x, z), y in sorted(columns.items())]
    highest = max(p[1] for p in points)
    points = [p for p in points if p[1] == highest]
    first, second = points[len(points) // 3], points[2 * len(points) // 3]
    view = window.plotter
    mouse_move(view, screen(window, first))
    window.navigation.tick(0.05)
    assert window.overlay.hover.bounds == (first, tuple(v + 1 for v in first))
    hover_actors = tuple(window.overlay.hover.actors)
    mouse_move(view, screen(window, second))
    window.navigation.tick(0.05)
    assert tuple(window.overlay.hover.actors) == hover_actors
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=screen(window, first))
    assert window.selection().volume == 1 and window.selection().lower == first, (window.selection(), first, screen(window, first), window.scene.hit_at(window.session, screen(window, first)))
    QTest.keyPress(view, Qt.Key.Key_Shift)
    mouse_move(view, screen(window, second), modifiers=Qt.KeyboardModifier.ShiftModifier)
    window.navigation.tick(0.05)
    preview = window.selected.preview
    assert preview is not None and preview.volume > 1
    assert window.selection().volume == 1
    assert window.minimap.canvas.selection == (preview.lower, preview.upper)
    assert window.overlay.temporary.bounds == (preview.lower, preview.upper)
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, screen(window, second))
    assert window.selection() == preview and window.selected.preview is None
    assert window.overlay.temporary.bounds is None
    mouse_move(view, screen(window, first), modifiers=Qt.KeyboardModifier.ShiftModifier)
    window.navigation.tick(0.05)
    assert window.selection() == preview and window.selected.preview is None
    QTest.keyRelease(view, Qt.Key.Key_Shift)
    QTest.keyPress(view, Qt.Key.Key_Shift)
    mouse_move(view, screen(window, first), modifiers=Qt.KeyboardModifier.ShiftModifier)
    window.navigation.tick(0.05)
    assert window.selected.preview.volume == 1
    QTest.keyRelease(view, Qt.Key.Key_Shift)
    assert window.selection() == preview and window.selected.preview is None
    QTest.mouseClick(view, Qt.MouseButton.LeftButton, pos=screen(window, second))
    assert window.selection().volume == 1 and window.selection().lower == second
    return second


def check_map_proportions(canvas):
    from structura_edit.map_layout import projection_rect

    for view, image in canvas.images.items():
        target = canvas.image_rect(projection_rect(canvas.origin, canvas.size_blocks, view), view)
        assert np.isclose(target.width() / image.width(), target.height() / image.height()), view


def check_materials(window, point):
    state = window.session.state_at(point)
    selection, revision = window.selection(), window.session.revision
    actors, camera = tuple(window.scene.actors), window.plotter.camera.position
    target = window.operation.fields["target"]
    target.setText("minecraft:gold_block")
    mouse_move(window.plotter, screen(window, point))
    QTest.keyClick(window.plotter, Qt.Key.Key_I)
    assert target.text() == state and window.selection() == selection
    assert window.session.revision == revision and not window.worker.busy
    assert tuple(window.scene.actors) == actors and window.plotter.camera.position == camera
    window.show_operation("Replace")
    window.operation.fields["source"].setText("minecraft:glass")
    window.show_materials("source")
    window.panels.materials.search.setText(state)
    QTest.keyClick(window.panels.materials.search, Qt.Key.Key_Return)
    assert window.operation.values()["source"] == state and target.text() == state
    window.show_materials("target")
    window.panels.materials.search.setText("no_such_block")
    QTest.keyClick(window.panels.materials.search, Qt.Key.Key_Escape)
    assert window.focusWidget() is target and target.text() == state
    window.show_operation("Fill")
    target.setText("minecraft:glass")
    window.preview_operation()
    settle(window)
    assert window.pending is not None, window.status.text()
    pending = window.pending
    QTest.mouseClick(window.plotter, Qt.MouseButton.MiddleButton, pos=screen(window, point))
    assert window.pending is pending and target.text() == "minecraft:glass"
    assert "minecraft:glass" in window.panels.materials.recent
    window.discard_pending()
    settle(window)
    window.panels.dismiss()


def check_minimap(window):
    from structura_edit.map_projection import VIEWS, project, unproject

    minimap, canvas = window.minimap, window.minimap.canvas
    assert minimap.isVisible() and set(canvas.images) == set(VIEWS)
    assert not minimap.findChildren(QComboBox)
    assert minimap.x() + minimap.width() == window.plotter.width() and minimap.y() == 0
    assert canvas.x() == 0 and canvas.width() == minimap.width()
    area = sum(canvas.tile_rect(view).width() * canvas.tile_rect(view).height() for view in VIEWS)
    assert area == canvas.width() * canvas.height()
    window.resize(1111, 777)
    QApplication.processEvents()
    assert minimap.x() + minimap.width() == window.plotter.width() and minimap.y() == 0
    QTest.mouseClick(minimap.header, Qt.MouseButton.LeftButton)
    assert minimap.collapsed and minimap.height() == minimap.header.height()
    QTest.mouseClick(minimap.header, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    assert not minimap.collapsed and canvas.isVisible()
    window.resize(1380, 880)
    QApplication.processEvents()
    check_map_proportions(canvas)
    clicks = []
    def selected(*args):
        clicks.append(args)
    window.navigation.selected.connect(selected)
    for view in VIEWS:
        before = window.plotter.camera.position
        target = tuple(size / 3 for size in window.session.size)
        point = canvas.screen_point(target, view).toPoint()
        uv = project(target, window.session.size, view)
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=point)
        assert np.allclose(window.plotter.camera.position, unproject(uv, before, window.session.size, view), atol=0.25)
    window.navigation.selected.disconnect(selected)
    assert not clicks


def check_panel_focus(window):
    window.selection_actions.select_all()
    window.show_operation("Fill")
    field = window.operation.fields["target"]
    field.setText("minecraft:gold_block")
    window.preview_operation()
    window.show_recipe()
    code = window.panels.recipe.code
    code.setPlainText("wasd")
    code.setFocus()
    settle(window)
    assert window.panels.docks["recipe"].isVisible()
    assert not window.panels.docks["operation"].isVisible()
    assert window.focusWidget() is code
    assert code.toPlainText() == "wasd"
    assert window.panels.recipe.apply.isEnabled()
    assert not window.session.dirty
    window.discard_pending()
    settle(window)
    window.panels.show("selection")
    lower = window.panels.selection.fields[0][0]
    original = window.selection()
    lower.setFocus()
    lower.selectAll()
    QTest.keyClicks(lower, "12")
    assert window.selection() == original
    QTest.keyClick(lower, Qt.Key.Key_Return)
    assert window.selection().lower[0] == 12
    lower.selectAll()
    QTest.keyClicks(lower, "16")
    QTest.keyClick(lower, Qt.Key.Key_Escape)
    assert window.selection().lower[0] == 12 and lower.value() == 12
    assert not window.panels.docks["selection"].isVisible()
    assert window.focusWidget() is window.plotter
    window.selection_actions.select_all()
    window.panels.dismiss()
    QApplication.processEvents()


def check_selection_adjustments(window):
    from structura_edit import Selection
    from structura_edit.picking import EMPTY

    actions, panel = window.selection_actions, window.panels.selection
    window.panels.show("selection")
    actions.set_bounds((3, 3, 3), (6, 6, 6))
    camera, actors = window.plotter.camera.position, tuple(window.scene.actors)
    revision = window.session.revision
    for text, expected in (("Grow", Selection((2, 2, 2), (7, 7, 7))),
                           ("X+", Selection((3, 2, 2), (8, 7, 7))),
                           ("Shrink", Selection((4, 3, 3), (7, 6, 6)))):
        buttons = panel.findChildren(QPushButton) + panel.findChildren(QToolButton)
        button = next(button for button in buttons if button.text() == text)
        previous = window.selection()
        QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
        assert window.selection() == previous and window.selected.preview == expected
        assert window.overlay.temporary.bounds == (expected.lower, expected.upper)
        QApplication.sendEvent(button, QEvent(QEvent.Type.Leave))
        assert window.selection() == previous and window.selected.preview is None
        assert window.overlay.temporary.bounds is None
        QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        assert window.selection() == expected
        assert window.selected.preview is None
    panel.step.setFocus()
    panel.step.selectAll()
    QTest.keyClicks(panel.step, "2")
    button = next(button for button in panel.findChildren(QToolButton) if button.text() == "Z+")
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert window.selection() == Selection((4, 3, 5), (7, 6, 8))
    before = window.selection()
    actions.adjust("grow", -2)
    assert window.selection() == before and "at least 1 block" in window.status.text()
    assert window.plotter.camera.position == camera
    assert tuple(window.scene.actors) == actors and window.session.revision == revision
    assert not window.worker.busy and not window.views.render_queued and not window.views.map_queued
    actions.clear()
    sx, sy, sz = window.session.size
    first, second = (0, sy - 1, 0), (sx - 1, sy - 1, sz - 1)
    assert (window.session.state_at(first) or "minecraft:air").split("[", 1)[0] in EMPTY
    for code, position in ((Qt.Key.Key_1, first), (Qt.Key.Key_2, second)):
        window.move_camera(tuple(p + 0.25 for p in position))
        QTest.keyClick(window.plotter, code)
    assert window.selection() == Selection.from_corners(first, second)
    assert window.selected.anchor == first and window.selected.opposite == second
    before = window.selection()
    window.move_camera((-0.25, 2, 2))
    QTest.keyClick(window.plotter, Qt.Key.Key_1)
    assert window.selection() == before and "outside" in window.status.text().lower()
    assert not window.worker.busy and window.session.revision == revision
    assert tuple(window.scene.actors) == actors
    window.panels.dismiss()


def check_edits(window, point, output):
    original = window.session.state_at(point)
    camera = tuple(tuple(v) for v in window.plotter.camera_position)
    window.show_operation("Fill")
    window.operation.fields["target"].setText("minecraft:gold_block")
    QTest.mouseClick(window.operation.preview, Qt.MouseButton.LeftButton)
    settle(window)
    assert window.pending and window.operation.apply.isEnabled(), window.panels.recipe.output.toPlainText()
    assert window.scene.ghost_actors
    assert all(actor.GetProperty().GetOpacity() < opacity for actor, (_, opacity, _) in window.scene.ghost_actors.items())
    window.plotter.screenshot(str(output / "ghost.png"))
    assert window.session.state_at(point) == original
    assert np.allclose(tuple(tuple(v) for v in window.plotter.camera_position), camera)
    QTest.mouseClick(window.operation.apply, Qt.MouseButton.LeftButton)
    settle(window)
    assert window.session.state_at(point) == "minecraft:gold_block"
    assert not window.scene.ghost_actors
    settle(window)
    window.undo()
    settle(window)
    assert window.session.state_at(point) == original
    window.redo()
    settle(window)
    assert window.session.state_at(point) == "minecraft:gold_block"
    window.show_operation("Erase")
    window.preview_operation()
    settle(window)
    window.discard_pending()
    settle(window)
    assert window.session.state_at(point) == "minecraft:gold_block"
    window.show_operation("Move blocks")
    offset = (-1, 0, 0) if point[0] else (1, 0, 0)
    destination = tuple(p + d for p, d in zip(point, offset))
    previous_destination = window.session.state_at(destination)
    window.operation.set_values({"offset": offset})
    window.preview_operation()
    settle(window)
    assert window.pending and window.session.state_at(point) == "minecraft:gold_block"
    window.apply_pending()
    settle(window)
    assert window.session.state_at(point) == "minecraft:air"
    assert window.session.state_at(destination) == "minecraft:gold_block"
    assert window.selection().lower == destination
    window.undo()
    settle(window)
    assert window.session.state_at(point) == "minecraft:gold_block"
    assert window.session.state_at(destination) == previous_destination
    window.selection_actions.set_bounds(point, tuple(v + 1 for v in point))
    window.show_operation("Fill")
    window.operation.fields["target"].setFocus()
    window.operation.fields["target"].clear()
    QTest.keyClicks(window.operation.fields["target"], "wasd123")
    assert window.operation.fields["target"].text() == "wasd123" and not window.navigation.keys
    window.panels.recipe.code.setPlainText('edit.apply(edit.fill(selection, "minecraft:glass"))\nraise RuntimeError("recipe failure check")')
    window.preview_recipe()
    settle(window)
    assert window.session.state_at(point) == "minecraft:gold_block"
    assert "recipe failure check" in window.panels.recipe.output.toPlainText()
    window.panels.recipe.code.setPlainText('edit.apply(edit.fill(selection, "minecraft:glass"))')
    window.preview_recipe()
    settle(window)
    window.apply_pending()
    settle(window)
    assert window.session.state_at(point) == "minecraft:glass"
    saved = output / ("edited.schem" if window.session.path.suffix == ".schem" else "edited.nbt")
    window.save_path(saved)
    settle(window)
    from structura_edit import EditSession
    assert EditSession.open(saved).palette_counts() == window.session.palette_counts()
    assert not window.session.dirty
    history_size = len(window.session.history.entries)
    window.panels.show("history")
    window.seek_history(0)
    settle(window)
    assert window.session.state_at(point) == original
    assert not window.session.can_undo and window.session.can_redo
    assert window.panels.history.model.rowCount() == history_size + 1
    window.seek_history(history_size)
    settle(window)
    assert window.session.state_at(point) == "minecraft:glass" and not window.session.dirty
    assert window.panels.docks["history"].isVisible()
    window.show_materials()
    assert window.panels.materials.filtered.rowCount() > 0
    window.panels.dismiss()
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--assets")
    parser.add_argument("--output", default="/private/tmp/structura-edit-smoke")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    window = EditorWindow(assets=args.assets, off_screen=True, cache_dir=output / "cache")
    window.show()
    try:
        start = time.perf_counter()
        window.open_path(args.path)
        settle(window)
        opened = time.perf_counter() - start
        assert window.session is not None and window.views.ready, window.panels.recipe.output.toPlainText()
        assert window.scene.actors
        assert not window.findChildren(QToolBar)
        assert not any(dock.isVisible() for dock in window.panels.docks.values())
        check_minimap(window)
        check_navigation(window)
        check_panel_focus(window)
        check_selection_adjustments(window)
        point = check_selection(window)
        check_materials(window, point)
        saved = check_edits(window, point, output)
        QApplication.processEvents()
        window.fit_scene()
        window.minimap.grab().save(str(output / "minimap.png"))
        window.grab().save(str(output / "editor.png"))
        window.plotter.screenshot(str(output / "scene.png"))
        report = dict(open_seconds=opened, size=window.session.size, saved=str(saved),
                      camera="timer-driven held keys, release, focus loss, RMB look",
                      focus="preview preserves active inspector and text; coordinates commit on Enter",
                      selection="single block, live Shift region, click to commit, release to cancel",
                      bounds="grow, shrink, axis shifts, typed step, independent camera corners, atomic boundary rejection; no jobs or block edits",
                      materials="pick without edits, exact state search, From/To routing, Escape focus, preview isolation",
                      editing="fill, move, preview, apply, undo, redo, discard, recipe isolation, save and reload",
                      minimap="six projections, navigation without click-through, edge coverage, resize, collapse and expand")
        (output / "result.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report), flush=True)
    finally:
        window.session = None
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
