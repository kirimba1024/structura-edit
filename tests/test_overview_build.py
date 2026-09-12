from contextlib import closing
import json
from pathlib import Path

import numpy as np
import pytest

from overview_fixture import create_overview_world
from structura_core.world_terrain import existing_chunks
from structura_edit.overview_build import build_overview
from structura_edit.overview_model import DetailTarget, select_detail
from structura_edit.overview_store import OverviewStore, surface_destination, read_meshes
from structura_edit.overview_maps import downsample_map
from structura_edit.height_slice import HeightSlice
from structura_edit.source_loading import open_source
from structura_edit.overview_cache import open_snapshot, snapshot_build_slot, snapshot_lease


def test_full_snapshot_keeps_exact_blocks_and_publishes_only_complete_builds(tmp_path):
    world = create_overview_world(tmp_path / "world")
    before = {path: path.read_bytes() for path in world.rglob("*") if path.is_file()}
    stages = set()
    directory = tmp_path / "overview"
    result = build_overview(world, "minecraft:overworld", directory, progress=lambda label, *counts: stages.add(label))
    assert result["metadata"]["chunks"] == len(existing_chunks(world / "region")) == 6
    assert result["roots"] and result["maps"] and "Building map" in stages
    with closing(OverviewStore(result["path"])) as store:
        leaves = [node for node in result['nodes'].values() if node.key[0] == 0]
        assert leaves and all(node.error == 0 for node in leaves)
        assert all('lod' not in store.read_mesh(node.key, {}) for node in leaves)
        source = store.read_region((-1, 0, -1), (17, 16, 17))
        assert source.palette[source.present[(1, 0, 1)]] == "minecraft:stone"
        assert source.palette[source.present[(1, 4, 1)]] == "minecraft:grass_block"
        assert source.present.get((1, 15, 1)) is None
    target = DetailTarget.at((0, 10, 0), 1080, 60)
    keys = select_detail(result["nodes"], result["roots"], target)
    assert set(read_meshes(result["path"], keys)) == set(keys)
    assert surface_destination(result["path"], (0, 0)) == (0.5, 8.0, 0.5)
    pointer = (directory / "current.json").read_bytes()
    def fail(label, done, total):
        if label == "Building detail":
            raise RuntimeError("cancelled build")
    with pytest.raises(RuntimeError, match="cancelled"):
        build_overview(world, "minecraft:overworld", directory, progress=fail)
    assert (directory / "current.json").read_bytes() == pointer
    assert len(list(directory.glob("*.sqlite"))) == 1
    assert before == {path: path.read_bytes() for path in before}
    assert json.loads(pointer)["file"] == Path(result["path"]).name
    assert open_snapshot(result['path'])['path'] == result['path']
    next((world / 'region').glob('*.mca')).touch()
    with pytest.raises(ValueError, match='World or textures changed'):
        open_snapshot(result['path'])


def test_map_reduction_preserves_known_void_and_ignores_unknown_color():
    image = np.zeros((4, 4, 4), np.uint8)
    image[..., :3] = (255, 0, 0)
    image[0, 0] = (0, 255, 0, 255)
    result = downsample_map(image)
    assert tuple(result[0, 0]) == (0, 255, 0, 64)
    assert (result[1, 1] == 0).all()


def test_unchanged_snapshot_reuses_geometry_and_textured_maps(tmp_path, monkeypatch):
    world = create_overview_world(tmp_path / "world")
    directory = tmp_path / "overview #100% ä"
    first = build_overview(world, "minecraft:overworld", directory)
    def unexpected(*args, **kwargs):
        pytest.fail("Unchanged snapshot was recalculated")
    monkeypatch.setattr("structura_edit.overview_build.build_geometry", unexpected)
    monkeypatch.setattr("structura_edit.overview_build.simplify_lod", unexpected)
    monkeypatch.setattr("structura_edit.overview_maps.column_image", unexpected)
    second = build_overview(world, "minecraft:overworld", directory)
    assert first["nodes"] == second["nodes"]
    assert first["metadata"]["map_min_level"] == second["metadata"]["map_min_level"] == -4
    with closing(OverviewStore(first["path"])) as a, closing(OverviewStore(second["path"])) as b:
        for table in ("meshes", "maps", "surfaces"):
            assert sorted(a.db.execute(f"SELECT * FROM {table}")) == sorted(b.db.execute(f"SELECT * FROM {table}"))


def test_incremental_edit_and_neighbor_tiles_match_clean_rebuild(tmp_path, monkeypatch):
    import structura_edit.overview_maps as maps

    world = create_overview_world(tmp_path / "world")
    directory = tmp_path / "overview"
    build_overview(world, "minecraft:overworld", directory)
    session = open_source(world, center=(8, 8, 8), radius=1, vertical_radius=16, include_entities=False)
    position = tuple(p - o for p, o in zip((15, 5, 0), session.origin))
    session.apply(session.set_block(position, "minecraft:gold_block"))
    arguments = dict(edits=session.world_changes.patch, document_id=session._id, revision=session.revision)
    columns = []
    original = maps.column_image
    def counted(store, x, z, *args):
        columns.append((x, z))
        return original(store, x, z, *args)
    monkeypatch.setattr(maps, "column_image", counted)
    incremental = build_overview(world, session.dimension, directory, **arguments)
    assert set(columns) == {(0, 0), (1, 0)}
    fresh = build_overview(world, session.dimension, tmp_path / "fresh", **arguments)
    assert incremental["nodes"] == fresh["nodes"]
    with closing(OverviewStore(incremental["path"])) as a, closing(OverviewStore(fresh["path"])) as b:
        for table in ("meshes", "maps", "surfaces"):
            assert sorted(a.db.execute(f"SELECT * FROM {table}")) == sorted(b.db.execute(f"SELECT * FROM {table}"))


def test_snapshot_includes_unsaved_edits_and_builds_a_real_cut_surface(tmp_path):
    world = create_overview_world(tmp_path / "world")
    session = open_source(world, center=(8, 8, 8), radius=0, vertical_radius=16, include_entities=False)
    position = tuple(p - o for p, o in zip((0, 5, 0), session.origin))
    session.apply(session.set_block(position, "minecraft:gold_block"))
    result = build_overview(world, session.dimension, tmp_path / "overview", edits=session.world_changes.patch,
                            height=HeightSlice("below", 3), document_id=session._id, revision=session.revision)
    assert result["metadata"]["volatile"]
    with closing(OverviewStore(result["path"])) as store:
        source = store.read_region((0, 0, 0), (1, 8, 1))
        assert source.palette[source.present[(0, 5, 0)]] == "minecraft:gold_block"
        for key in result["nodes"]:
            if key[0] == 0:
                assert store.read_lod(key).points[:, 1].max() <= 4
    assert surface_destination(result["path"], (0, 0)) == (0.5, 7.0, 0.5)


def test_cache_cleanup_keeps_snapshots_used_by_another_view(tmp_path):
    first, second = tmp_path / "first.sqlite", tmp_path / "second.sqlite"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    (tmp_path / "current.json").write_text(json.dumps({"file": second.name}))
    lease = snapshot_lease(first)
    try:
        with snapshot_build_slot(tmp_path):
            assert first.is_file() and second.is_file()
    finally:
        lease.release()
    with snapshot_build_slot(tmp_path):
        assert not first.exists() and second.is_file()


@pytest.mark.parametrize("layout,dimension", [("nether", "minecraft:the_nether"), ("end", "minecraft:the_end"), ("custom", "test:high")])
def test_dimensions_preserve_roofs_islands_and_absent_coverage(tmp_path, layout, dimension):
    world = create_overview_world(tmp_path / "world", layout=layout)
    result = build_overview(world, dimension, tmp_path / "overview", below_y=10 if layout == "nether" else None)
    assert result["metadata"]["dimension"] == dimension
    with closing(OverviewStore(result["path"])) as store:
        source = store.read_region((0, 0, 0), (16, 16, 16))
        if layout == "nether":
            assert source.present.get((4, 15, 4)) is not None
            assert max(store.read_lod(key).points[:, 1].max() for key in result["nodes"] if key[0] == 0) == 16
        if layout == "end":
            image = store.read_map((0, 0, 0))
            assert image[4, 20, 3] == 255 and image[4, 60, 3] == 0
            with pytest.raises(ValueError, match="no surface"):
                surface_destination(result["path"], (20, 4))


def test_invalid_cache_pointer_can_be_rebuilt_and_source_change_is_rejected(tmp_path):
    directory = tmp_path / "cache"
    directory.mkdir()
    (directory / "current.json").write_text("incomplete")
    with snapshot_build_slot(directory):
        pass
    world = create_overview_world(tmp_path / "world")
    touched = False
    def changed(label, done, total):
        nonlocal touched
        if label == "Building detail" and not touched:
            path = next((world / "region").glob("*.mca"))
            path.touch()
            touched = True
    with pytest.raises(ValueError, match="changed during"):
        build_overview(world, "minecraft:overworld", directory, progress=changed)
    assert not list(directory.glob("*.sqlite"))
