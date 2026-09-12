from copy import copy
from types import SimpleNamespace

import numpy as np
import pytest

from structura_edit.camera_map_render import context_key, render_camera_maps
from structura_edit.document import Document
from structura_edit.height_slice import HeightSlice


@pytest.fixture
def map_request(world_edit, tmp_path):
    world_edit.map_identity = "test world"
    world_edit.map_stamps = {}
    request = SimpleNamespace(state=world_edit, assets=tmp_path, height=HeightSlice(), change=None)
    request.map_args = lambda: dict(source=request.state._render_source(include_nbt=False, include_entities=False))
    return request


@pytest.fixture
def atlas_writes(monkeypatch):
    calls = []
    def store(spec, images):
        calls.append(spec)
        rgba = {view: np.dstack((image, np.full(image.shape[:2], 255, np.uint8))) for view, image in images.items()}
        return rgba, spec
    monkeypatch.setattr("structura_edit.map_cache.store_maps", store)
    return calls


def test_pan_and_zoom_reuse_published_maps_but_update_texture_details(map_request, tmp_path, atlas_writes):
    first = render_camera_maps(map_request, None, True, None, tmp_path / "cache", (("top", (0, 0, 1, 1)),))
    second = render_camera_maps(map_request, None, True, first[0], tmp_path / "cache", (("top", (1, 1, 3, 2)),))
    assert len(atlas_writes) == 1
    assert first[1] is second[1] and first[0] is second[0]
    assert second[4]["top"][0] == (1, 1, 3, 2)
    assert second[4]["top"][1].shape == (16, 32, 3)
    sliced = render_camera_maps(map_request, (1, 1, 1), True, second[0], tmp_path / "cache")
    assert len(atlas_writes) == 2 and sliced[1] is not second[1]
    other_cache = render_camera_maps(map_request, (1, 1, 1), True, sliced[0], tmp_path / "other")
    assert len(atlas_writes) == 3 and other_cache[2]["path"] != sliced[2]["path"]


def test_reloaded_document_invalidates_renderer_at_same_revision(map_request, tmp_path, atlas_writes):
    first = render_camera_maps(map_request, None, True, None, tmp_path / "cache")
    key = context_key(map_request)
    original = map_request.state
    map_request.state = copy(original)
    map_request.state._document = Document(original.snapshot())
    assert (map_request.state._id, map_request.state._state_id, map_request.state.revision) == (
        original._id, original._state_id, original.revision)
    assert context_key(map_request) != key
    second = render_camera_maps(map_request, None, True, first[0], tmp_path / "cache")
    assert len(atlas_writes) == 2
    assert second[0].renderer is not first[0].renderer


def test_new_resources_and_edits_invalidate_atlas(map_request, tmp_path, atlas_writes):
    first = render_camera_maps(map_request, None, True, None, tmp_path / "cache")
    map_request.assets = tmp_path / "new-resources"
    second = render_camera_maps(map_request, None, True, first[0], tmp_path / "cache")
    assert len(atlas_writes) == 2 and first[0].renderer is not second[0].renderer
    map_request.state.apply(map_request.state.set_block((0, 0, 0), "minecraft:gold_block"))
    third = render_camera_maps(map_request, None, True, second[0], tmp_path / "cache")
    assert len(atlas_writes) == 3 and third[0].renderer is not second[0].renderer


def test_failed_atlas_write_can_retry(map_request, tmp_path, monkeypatch, atlas_writes):
    import structura_edit.map_cache as cache

    store = cache.store_maps
    def fail(*args):
        raise OSError("test write failure")
    monkeypatch.setattr(cache, "store_maps", fail)
    first = render_camera_maps(map_request, None, True, None, tmp_path / "cache")
    assert "test write failure" in first[3] and first[2] is None
    monkeypatch.setattr(cache, "store_maps", store)
    second = render_camera_maps(map_request, None, True, first[0], tmp_path / "cache")
    assert len(atlas_writes) == 1 and second[2] is not None and not second[3]
