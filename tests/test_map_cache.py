from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from structura_edit.map_cache import connect, fingerprint, map_spec, read_tiles, store_maps
from structura_edit.map_projection import VIEWS, plane_size


def snapshot(tmp_path, origin=(0, 0, 0), *, loaded=None, dimension="overworld"):
    region = tmp_path / "r.0.0.mca"
    if not region.exists():
        region.write_bytes(b"region revision one")
    session = SimpleNamespace(map_identity=("world", dimension, 123), origin=origin, size=(16, 16, 16),
                              loaded_chunks={(origin[0] // 16, origin[2] // 16)} if loaded is None else loaded,
                              map_stamps={str(region): fingerprint(region)}, dirty=False)
    return map_spec(session, None, tmp_path / "cache.sqlite")


def images(spec, color):
    return {view: np.full((*reversed(plane_size(spec["size"], view)), 3), color, dtype=np.uint8) for view in VIEWS}


def pixel(spec, x, z):
    tiles = read_tiles(spec, {"top": (x, z, x + 1, z + 1)})
    for (_, left, top), data in tiles.items():
        if left <= x < left + data.shape[1] and top <= z < top + data.shape[0]:
            return tuple(data[z - top, x - left])
    return (0, 0, 0, 0)


def test_refresh_stitches_negative_coordinates_and_overwrites_only_its_area(tmp_path):
    first = snapshot(tmp_path, (-16, 0, -16))
    second = snapshot(tmp_path, (0, 0, -16))
    store_maps(first, images(first, (100, 0, 0)))
    store_maps(second, images(second, (0, 100, 0)))
    assert pixel(second, -1, -1) == (100, 0, 0, 255)
    assert pixel(second, 0, -1) == (0, 100, 0, 255)
    store_maps(first, images(first, (0, 0, 100)))
    assert pixel(second, -1, -1) == (0, 0, 100, 255)
    assert pixel(second, 0, -1) == (0, 100, 0, 255)
    assert pixel(second, 16, -1)[3] == 0


def test_unsaved_pixels_are_visible_without_overwriting_the_disk_atlas(tmp_path):
    spec = snapshot(tmp_path)
    store_maps(spec, images(spec, (80, 90, 100)))
    pending = dict(spec, volatile=True)
    visible, atlas = store_maps(pending, images(pending, (200, 100, 20)))
    assert tuple(visible["top"][0, 0]) == (200, 100, 20, 255)
    assert atlas == pending and pixel(spec, 0, 0) == (80, 90, 100, 255)


def test_cache_separates_world_dimension_depth_and_rendering_and_marks_unknown_chunks(tmp_path, monkeypatch):
    original = snapshot(tmp_path)
    store_maps(original, images(original, (80, 90, 100)))
    assert pixel(snapshot(tmp_path), 1, 1) == (80, 90, 100, 255)
    assert pixel(snapshot(tmp_path, dimension="nether"), 1, 1)[3] == 0
    assert pixel(snapshot(tmp_path, (0, 16, 0)), 1, 1)[3] == 0
    with monkeypatch.context() as changed_renderer:
        changed_renderer.setattr("structura_edit.map_cache.MAP_RENDER_VERSION", 0)
        assert pixel(snapshot(tmp_path), 1, 1)[3] == 0
    missing = snapshot(tmp_path, loaded=set())
    store_maps(missing, images(missing, (200, 200, 200)))
    assert pixel(original, 1, 1)[3] == 0


def test_modified_region_invalidates_old_tiles_and_racing_snapshot_is_not_cached(tmp_path):
    first = snapshot(tmp_path)
    distant = snapshot(tmp_path, (128, 0, 0))
    store_maps(first, images(first, (100, 0, 0)))
    store_maps(distant, images(distant, (100, 0, 0)))
    (tmp_path / "r.0.0.mca").write_bytes(b"different saved content")
    _, cached = store_maps(first, images(first, (0, 100, 0)))
    assert cached is None
    current = snapshot(tmp_path)
    store_maps(current, images(current, (0, 0, 100)))
    assert pixel(current, 1, 1) == (0, 0, 100, 255)
    assert pixel(current, 129, 1)[3] == 0


def test_disk_eviction_and_corrupt_tile_do_not_break_the_map(tmp_path, monkeypatch):
    monkeypatch.setattr("structura_edit.map_cache.MAX_TILES", 6)
    first = snapshot(tmp_path)
    distant = snapshot(tmp_path, (1024, 0, 1024))
    store_maps(first, images(first, (100, 0, 0)))
    store_maps(distant, images(distant, (0, 100, 0)))
    assert pixel(first, 1, 1)[3] == 0
    assert pixel(distant, 1025, 1025) == (0, 100, 0, 255)
    with connect(first["path"]) as db:
        db.execute("UPDATE tiles SET image=?", (b"broken png",))
    assert pixel(distant, 1025, 1025)[3] == 0


def test_failed_write_keeps_existing_tiles(tmp_path, monkeypatch):
    first = snapshot(tmp_path)
    store_maps(first, images(first, (100, 0, 0)))
    original = deepcopy(first)
    def fail(*args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr("PIL.Image.Image.save", fail)
    with pytest.raises(OSError, match="disk full"):
        store_maps(first, images(first, (0, 100, 0)))
    assert pixel(original, 1, 1) == (100, 0, 0, 255)


def test_external_chunk_and_resource_changes_invalidate_their_cache(tmp_path):
    from structura_edit.source_loading import source_stamps

    external = tmp_path / "c.0.0.mcc"
    external.write_bytes(b"old chunk")
    first = snapshot(tmp_path)
    first["stamps"] = source_stamps(tmp_path, (1, 1, 1), 0)
    store_maps(first, images(first, (100, 0, 0)))
    external.write_bytes(b"new external chunk")
    assert store_maps(first, images(first, (0, 100, 0)))[1] is None
    assets = tmp_path / "assets"
    texture = assets / "textures" / "stone.png"
    texture.parent.mkdir(parents=True)
    texture.write_bytes(b"old texture")
    session = SimpleNamespace(map_identity=("world", "overworld", 123), origin=(0, 0, 0), size=(16, 16, 16),
                              loaded_chunks={(0, 0)}, map_stamps={}, dirty=False)
    before = map_spec(session, assets, first["path"])
    texture.write_bytes(b"changed nested texture")
    assert map_spec(session, assets, first["path"])["space"] != before["space"]


@pytest.mark.parametrize("view", VIEWS)
def test_cache_preserves_texture_pixels_at_global_projection_coordinates(tmp_path, view):
    from structura_edit.map_cache import TILE_SIZE
    from structura_edit.map_projection import project

    spec = snapshot(tmp_path, (-16, 16, -16))
    texture = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)
    pixels = np.tile(texture, (16, 16, 1))
    store_maps(spec, {view: pixels})
    first = project(spec["origin"], (0, 0, 0), view)
    last = project(tuple(p + s for p, s in zip(spec["origin"], spec["size"])), (0, 0, 0), view)
    left, top = min(first[0], last[0]), min(first[1], last[1])
    areas = {view: (left, top, left + 16, top + 16)}
    tiles = read_tiles(spec, areas, {view: 16})
    (_, x, y), tile = next(iter(tiles.items()))
    assert tile.shape == (TILE_SIZE * 16, TILE_SIZE * 16, 4)
    assert np.array_equal(tile[(top - y) * 16:(top - y + 16) * 16,
                              (left - x) * 16:(left - x + 16) * 16, :3], pixels)
    overview = next(iter(read_tiles(spec, areas).values()))
    assert overview.shape == (TILE_SIZE, TILE_SIZE, 4)
