import pytest

from structura_edit.changes import StaleChangeError
from structura_edit.render_source import preview_session


@pytest.mark.parametrize("fixture", ["edit", "world_edit"])
def test_render_preview_matches_apply_without_recording_history(request, fixture, monkeypatch):
    session = request.getfixturevalue(fixture)
    change = session.set_block((0, 0, 0), "minecraft:gold_block")
    expected = session.fork()
    expected.apply(change)
    def unexpected(*args, **kwargs):
        raise AssertionError("Visual preview must not record an edit")
    monkeypatch.setattr("structura_edit.history.History.append", unexpected)
    monkeypatch.setattr("structura_edit.saved_changes.SavedChanges.updated", unexpected)
    preview = preview_session(session, change)
    assert preview.snapshot().present == expected.snapshot().present
    assert preview.snapshot().block_nbt == expected.snapshot().block_nbt
    assert preview.snapshot().entities == expected.snapshot().entities
    assert preview.revision == session.revision + 1
    assert not preview.history.entries and not session.dirty
    assert session.state_at((0, 0, 0)) != "minecraft:gold_block"


def test_render_preview_preserves_resize_entities_and_source(edit):
    original = edit.snapshot()
    change = edit.paste(edit.copy(edit.select()), (-4, -3, -2), take=True)
    expected = edit.fork()
    expected.apply(change)
    preview = preview_session(edit, change)
    assert (preview.size, preview.origin) == (expected.size, expected.origin)
    assert preview.snapshot().present == expected.snapshot().present
    assert preview.snapshot().block_nbt == expected.snapshot().block_nbt
    assert preview.snapshot().entities == expected.snapshot().entities
    assert edit.snapshot().present == original.present
    assert not edit.history.entries and not preview.history.entries


def test_render_preview_rejects_stale_and_readonly_changes(edit):
    change = edit.set_block((0, 0, 0), "minecraft:gold_block")
    edit.apply(change)
    with pytest.raises(StaleChangeError):
        preview_session(edit, change)
    change = edit.set_block((0, 0, 0), "minecraft:glass")
    edit._document.readonly = True
    with pytest.raises(ValueError, match="view-only"):
        preview_session(edit, change)


def test_world_preview_is_not_written_to_the_saved_map_cache(world_edit, tmp_path):
    from structura_edit.camera_maps import render_camera_maps
    from structura_edit.view_pipeline import ViewRequest

    world_edit.map_identity = ("world", world_edit.dimension)
    world_edit.map_stamps = {}
    assets = tmp_path / "assets"
    assets.mkdir()
    path = tmp_path / "maps.sqlite"
    change = world_edit.set_block((0, 0, 0), "minecraft:gold_block")
    request = ViewRequest(world_edit, change, assets, True, False)
    assert request.map_args(path)["atlas"]["volatile"]
    _, _, atlas, notice, _, _, _ = render_camera_maps(request, None, True, None, path)
    assert atlas["volatile"] and not notice and not path.exists()
    assert not world_edit.dirty


@pytest.mark.parametrize('fixture', ['edit', 'world_edit'])
def test_worker_preview_roundtrip_publishes_the_state_used_for_geometry(request, fixture, tmp_path, monkeypatch):
    import pickle

    from structura_edit.tasks import execute
    from structura_edit.view_pipeline import ViewRequest

    session = request.getfixturevalue(fixture)
    change = session.paste(session.copy(session.select()), (-4, -3, -2), take=True) if fixture == 'edit' else session.erase(session.select())
    current = ViewRequest(session.fork(), change, str(tmp_path), True, False)
    previous = ViewRequest(session.fork(), None, str(tmp_path), True, False)
    seen = []
    def build(**args):
        seen.append(args)
        return 'geometry'
    monkeypatch.setattr('structura_edit.preview.build_sections', build)
    args = dict(request=current, previous=previous, assets=str(tmp_path))
    state, geometry = pickle.loads(pickle.dumps(execute('render_preview', pickle.loads(pickle.dumps(args)))))
    expected = preview_session(session, change)
    assert geometry == 'geometry' and seen[0]['ghosts']
    assert (state.size, state.origin) == (expected.size, expected.origin)
    assert state.snapshot().present == expected.snapshot().present
    assert state.snapshot().block_nbt == expected.snapshot().block_nbt
    assert state.snapshot().entities == expected.snapshot().entities
    assert 'state' not in vars(current) and not session.dirty and not state.history.entries


def test_worker_preview_rejects_invalid_changes_before_geometry(edit, tmp_path, monkeypatch):
    from dataclasses import replace

    from structura_edit.tasks import execute
    from structura_edit.view_pipeline import ViewRequest

    change = edit.set_block((0, 0, 0), 'minecraft:glass')
    invalid = replace(change, changes=change.changes * 2)
    def unexpected(**args):
        pytest.fail('Invalid changes reached the renderer')
    monkeypatch.setattr('structura_edit.preview.build_sections', unexpected)
    request = ViewRequest(edit, invalid, str(tmp_path), True, False)
    with pytest.raises(ValueError, match='duplicate'):
        execute('render_preview', dict(request=request, previous=None, assets=str(tmp_path)))
