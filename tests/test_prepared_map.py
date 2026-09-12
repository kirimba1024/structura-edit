from concurrent.futures import Future
from contextlib import closing
from types import SimpleNamespace

import numpy as np
from PIL import Image
from structura_core.world_terrain import TerrainSection

from structura_edit.overview_maps import MAP_MIN_LEVEL, build_map_pyramid
from structura_edit.overview_store import OverviewStore
from structura_edit.resources import texture_bank


def test_prepared_tiles_keep_texture_pixels_and_shading_across_chunk_edges(tmp_path):
    from structura_edit.map_images import map_faces, map_tiles, render_map

    directory = tmp_path / "textures/block"
    directory.mkdir(parents=True)
    texture = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
    Image.fromarray(texture).save(directory / "stone.png")
    with closing(OverviewStore(tmp_path / "map.sqlite", create=True)) as store:
        for x in (-1, 0, 1):
            blocks = np.full((16, 16, 16), -1, np.int32)
            blocks[:, :3 + x, :] = 0
            store.add_section(TerrainSection((x, 0, 0), ("minecraft:stone",), blocks, ()))
        bank = texture_bank(tmp_path)
        build_map_pyramid(store, [(-1, 0), (0, 0), (1, 0)], bank, lambda *args: None)
        source = store.read_region((-1, 0, -1), (32, 16, 16))
        tiles = map_tiles(source.palette, map_faces(source, bank), "top", 16)
        expected = render_map(source.present.array, "top", (0, 16), tiles, area=(1, 1, 33, 17))
        actual = np.concatenate([np.concatenate([store.read_map((MAP_MIN_LEVEL, x, z)) for x in range(4)], axis=1)
                                 for z in range(2)], axis=0)
        assert np.array_equal(actual[..., :3], expected)
        assert np.all(actual[..., 3] == 255)
        assert len(np.unique(actual[32:48, 32:48, :3].reshape(-1, 3), axis=0)) > 32
        assert store.read_map((MAP_MIN_LEVEL, -1, 0)) is not None
        assert store.read_map((MAP_MIN_LEVEL, 4, 0)) is None


def test_compact_camera_motion_does_not_request_slices(qt_app):
    from structura_edit.camera_maps import CameraMaps
    from structura_edit.map_canvas import MapCanvas

    canvas = MapCanvas()
    maps = CameraMaps(canvas, SimpleNamespace(path=None))
    maps.automatic = True
    canvas.dimension = "minecraft:overworld"
    state = SimpleNamespace(_id="world", _state_id=0, origin=(0, 0, 0), size=(64, 384, 64))
    maps.context = SimpleNamespace(state=state, assets=None, height=None)
    try:
        first = maps.target()
        canvas.position = (100, -40, 300)
        assert maps.target() == first
        assert first[1] is None and not first[4] and first[5] is None
        canvas.overview = {"ready": object()}
        canvas.overview_surface = canvas.overview_current = True
        assert not maps.needs_projection and not maps.busy
        canvas.layout.large = True
        assert maps.target() != first and maps.target()[4]
        assert maps.needs_projection
    finally:
        maps.close()
        canvas.deleteLater()


def test_hidden_world_map_loads_canvas_detail_and_retains_visited_tiles(qt_app):
    from PySide6.QtGui import QImage
    from structura_edit.world_map import WorldMap

    world = WorldMap()
    world.snapshot = {"path": "map.sqlite", "metadata": {"bounds": ((0, 0, 0), (512, 256, 512)),
                                                       "map_level": 2, "map_min_level": -4}}
    world.viewport = ((16, 32), (48, 64), 16)
    try:
        world.request()
        assert all(key[0] == -4 for key in world.target[1])
        first = world.target
        image = QImage(128, 128, QImage.Format.Format_RGBA8888)
        image.fill(0xff008000)
        result = Future()
        result.set_result({first[1][0]: image})
        world.future = first, result
        world.tick()
        assert first[1][0] in world.images and world.loaded == first
        world.viewport = ((80, 32), (112, 64), 16)
        world.request()
        result = Future()
        result.set_result({world.target[1][0]: image})
        world.future = world.target, result
        world.tick()
        assert first[1][0] in world.images and world.target[1][0] in world.images
    finally:
        world.shutdown()
        world.deleteLater()
