from itertools import product
from threading import Event, get_ident
from time import monotonic
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageColor
from structura_core import parse_state

from structura_edit.appearance import MAP_BACKGROUND
from structura_edit.map_images import MapRenderer
from structura_edit.map_projection import VIEWS, camera_cut, depth_axis


def layered_source(axis):
    names = ["minecraft:stone", "minecraft:dirt", "minecraft:gold_block"]
    return SimpleNamespace(size=(3, 3, 3), palette=names, palette_raw=list(map(parse_state, names)),
                           present={p: p[axis] for p in product(range(3), repeat=3)})


@pytest.fixture
def textures(tmp_path):
    directory = tmp_path / "textures/block"
    directory.mkdir(parents=True)
    for name, color in (("stone", (200, 0, 0)), ("dirt", (0, 200, 0)), ("gold_block", (0, 0, 200))):
        Image.new("RGB", (16, 16), color).save(directory / f"{name}.png")
    return tmp_path


@pytest.mark.parametrize("view", VIEWS)
def test_each_view_starts_at_camera_plane_instead_of_outer_surface(textures, view):
    renderer = MapRenderer(layered_source(depth_axis(view)), textures)
    assert np.all(renderer.images(cut=(1, 1, 1))[view] == (0, 200, 0))
    assert np.all(renderer.images(cut=(2, 2, 2))[view] == (0, 0, 200))
    empty = (-1, -1, -1) if view in ("top", "south", "east") else (3, 3, 3)
    assert np.all(renderer.images(cut=empty)[view] == ImageColor.getrgb(MAP_BACKGROUND))


def test_only_changed_axis_rebuilds_maps_and_sub_block_movement_reuses_every_image(textures):
    renderer = MapRenderer(layered_source(1), textures)
    first = renderer.images(cut=camera_cut((1.1, 1.1, 1.1), renderer.size))
    same = renderer.images(cut=camera_cut((1.9, 1.9, 1.9), renderer.size))
    assert all(first[view] is same[view] for view in VIEWS)
    moved = renderer.images(cut=(1, 2, 1))
    assert {view for view in VIEWS if first[view] is not moved[view]} == {"top", "bottom"}
    assert len(renderer.rendered) == len(renderer.tiles) == 6


def test_top_sees_floor_below_camera_and_bottom_sees_ceiling(textures):
    source = layered_source(1)
    source.present = {p: value for p, value in source.present.items() if p[1] != 1}
    renderer = MapRenderer(source, textures)
    images = renderer.images(cut=(1, 1, 1))
    assert np.all(images["top"] == (200, 0, 0))
    assert np.all(images["bottom"] == (0, 0, 200))


def wait_for(predicate):
    from PySide6.QtTest import QTest

    until = monotonic() + 5
    while not predicate() and monotonic() < until:
        QTest.qWait(20)
    assert predicate()


def test_small_map_always_centers_camera_even_after_manual_large_map_pan(qt_app):
    from PySide6.QtCore import QPointF
    from structura_edit.map_canvas import MapCanvas

    canvas = MapCanvas()
    canvas.resize(288, 192)
    canvas.size_blocks = (48, 64, 48)
    canvas.origin = (-128, -64, -256)
    canvas.layout.reset()
    try:
        for position in ((0.25, 1.5, 20.5), (-23.1, 83.5, 112.5)):
            canvas.position = position
            for view in VIEWS:
                assert (canvas.screen_point(position, view) - canvas.tile_rect(view).center()).manhattanLength() < 1e-8
        canvas.layout.large = True
        canvas.layout.pan("top", QPointF(30, 20))
        assert canvas.screen_point(canvas.position, "top") != canvas.tile_rect("top").center()
        canvas.layout.large = False
        assert (canvas.screen_point(canvas.position, "top") - canvas.tile_rect("top").center()).manhattanLength() < 1e-8
        canvas.layout.large = True
        canvas.layout.recenter()
        assert (canvas.screen_point(canvas.position, "top") - canvas.tile_rect("top").center()).manhattanLength() < 1e-8
    finally:
        canvas.deleteLater()


def test_camera_requests_run_off_gui_with_one_pending_position_and_reject_old_sources(qt_app, tmp_path, monkeypatch):
    from structura_edit.camera_maps import CameraMaps, context_key
    from structura_edit.map_canvas import MapCanvas
    from structura_edit.map_cache_ui import MapCacheView

    started, release = Event(), Event()
    calls = []
    gui_thread = get_ident()
    def render(request, cut, large, previous, path, areas=(), automatic=False, cave_y=None):
        assert get_ident() != gui_thread
        calls.append((request.state._id, cut))
        if len(calls) == 1:
            started.set()
            assert release.wait(5)
        color = (200, 0, 0) if request.state._id == "first" else (0, 200, 0)
        return (context_key(request), None), {"top": np.full((2, 2, 3), color, dtype=np.uint8)}, None, "", {}, cut, cave_y
    monkeypatch.setattr("structura_edit.camera_maps.render_camera_maps", render)
    canvas = MapCanvas()
    cache = MapCacheView(canvas, tmp_path)
    maps = CameraMaps(canvas, cache)
    maps.sliced = True
    def request(name):
        state = SimpleNamespace(_id=name, _state_id="revision", size=(32, 32, 32), origin=(0, 0, 0))
        return SimpleNamespace(state=state, assets=None, height=None)
    try:
        maps.request(request("first"))
        wait_for(started.is_set)
        maps.request(request("second"))
        for i in range(1, 20):
            canvas.position = (i + 0.25, 2.5, 3.5)
            maps.update()
        release.set()
        wait_for(lambda: not maps.busy)
        assert calls == [("first", (0, 0, 0)), ("second", (19, 2, 3))]
        assert canvas.images["top"].pixelColor(0, 0).green() == 200
        canvas.position = (19.9, 2.1, 3.9)
        maps.update()
        assert not maps.busy and len(calls) == 2
    finally:
        release.set()
        maps.close()
        cache.close()
        canvas.deleteLater()


@pytest.mark.parametrize('view', VIEWS)
def test_slice_displays_fully_buried_block_without_exposed_geometry(textures, view):
    source = layered_source(0)
    source.present = {p: (2 if p == (1, 1, 1) else 0) for p in product(range(3), repeat=3)}
    renderer = MapRenderer(source, textures)
    assert not np.any(np.all(renderer.images()[view] == (0, 0, 200), axis=-1))
    assert np.any(np.all(renderer.images(cut=(1, 1, 1))[view] == (0, 0, 200), axis=-1))
