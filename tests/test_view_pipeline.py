from types import SimpleNamespace

import pytest

from structura_edit.view_pipeline import ViewPipeline


def pipeline():
    calls, frames, images = [], [], []
    scene = SimpleNamespace(replace=lambda data, revision: frames.append((data, revision)))
    camera = SimpleNamespace(frame=lambda size: None, render=lambda: None, needs_render=False)
    minimap = SimpleNamespace(collapsed=False, set_images=images.append)
    def submit(kind, callback, **args):
        calls.append((kind, callback, args))
        return True
    view = ViewPipeline(scene, camera, minimap, submit, lambda data: None)
    return view, calls, frames, images


def test_latest_render_and_map_win(edit):
    view, calls, frames, images = pipeline()
    view.request(edit, None, None, True)
    view.flush()
    first = calls.pop()
    edit.apply(edit.set_block((0, 0, 0), "minecraft:glass"))
    view.request(edit, None, None, True)
    first[1]("old scene")
    assert not frames and not view.ready
    view.flush()
    calls.pop()[1]("new scene")
    assert frames == [("new scene", edit.revision)] and view.ready
    view.flush()
    old_map = calls.pop()
    edit.apply(edit.set_block((0, 0, 0), "minecraft:gold_block"))
    view.request(edit, None, None, True)
    old_map[1]("old map")
    assert not images
    view.flush()
    calls.pop()[1]("latest scene")
    view.flush()
    calls.pop()[1]("latest map")
    assert frames[-1] == ("latest scene", edit.revision)
    assert images == ["latest map"]


def test_collapsed_map_waits_and_loaded_map_is_reused(edit):
    view, calls, _, images = pipeline()
    view.minimap.collapsed = True
    view.request(edit, None, None, True)
    view.flush()
    calls.pop()[1]("scene")
    view.flush()
    assert not calls and view.map_queued
    view.minimap.collapsed = False
    view.flush()
    calls.pop()[1]("map")
    view.request_maps()
    view.flush()
    assert not calls and images == ["map"]


def test_reset_rejects_pending_results(edit):
    view, calls, frames, images = pipeline()
    view.request(edit, None, None, True)
    view.flush()
    callback = calls.pop()[1]
    view.reset()
    callback("cancelled scene")
    assert not frames and not images and not view.ready


def test_accepting_preview_updates_display_revision_without_rebuilding(edit):
    view, calls, frames, _ = pipeline()
    accepted = []
    view.scene.accept_preview = lambda: accepted.append(True)
    view.scene.display_revision = edit.revision
    change = edit.set_block((0, 0, 0), "minecraft:glass")
    view.request(edit, change, None, True)
    view.flush()
    calls.pop()[1]("preview")
    request = view.current
    edit.apply(change)
    assert view.accept(edit, request=request)
    assert accepted == [True] and len(frames) == 1
    assert view.scene.display_revision == edit.revision and view.displayed.change is None


def test_changed_view_during_apply_does_not_mark_old_geometry_current(edit):
    view, calls, _, _ = pipeline()
    view.scene.accept_preview = lambda: pytest.fail("Old geometry was accepted")
    view.scene.display_revision = edit.revision
    change = edit.set_block((0, 0, 0), "minecraft:glass")
    view.request(edit, change, None, True)
    view.flush()
    calls.pop()[1]("preview")
    request, displayed = view.current, view.displayed
    view.request(edit, change, None, False)
    edit.apply(change)
    assert not view.accept(edit, request=request)
    assert view.scene.display_revision == 0 and view.displayed is displayed
    assert view.render_queued


def test_initial_framing_survives_replacing_an_inflight_request(edit):
    view, calls, _, _ = pipeline()
    framed = []
    view.camera.frame = framed.append
    view.request(edit, None, None, True, fit=True)
    view.flush()
    first = calls.pop()[1]
    view.request(edit, None, None, False)
    first("stale scene")
    assert not framed
    view.flush()
    calls.pop()[1]("scene without entities")
    assert framed == [edit.size]
    view.request(edit, None, None, True)
    view.flush()
    calls.pop()[1]("next scene")
    assert framed == [edit.size]


def test_height_requests_reject_stale_geometry_and_maps(edit):
    from structura_edit.height_slice import HeightSlice

    view, calls, frames, images = pipeline()
    view.request(edit, None, None, True)
    view.flush()
    calls.pop()[1]("all layers")
    view.flush()
    stale_map = calls.pop()[1]
    view.request(edit, None, None, True, height=HeightSlice("below", 0))
    view.flush()
    stale_render = calls.pop()[1]
    view.request(edit, None, None, True, height=HeightSlice("layer", 1))
    stale_render("wrong height")
    stale_map("wrong map")
    assert len(frames) == 1 and not images
    assert view.scene.height == HeightSlice()
    view.flush()
    calls.pop()[1]("single layer")
    assert view.scene.height == HeightSlice("layer", 1) and view.ready
    assert view.displayed.height == view.scene.height


def test_clipboard_budget_is_checked_before_creating_preview_actors(edit):
    from structura_edit.loading import MAX_GEOMETRY_BYTES

    view, calls, frames, _ = pipeline()
    view.scene.section_bytes = {}
    view.retained_geometry = lambda: 1024
    view.request(edit, None, None, True)
    view.flush()
    with pytest.raises(ValueError, match="clipboard"):
        calls.pop()[1]({"reset": True, "sections": {"new": {"geometry_bytes": MAX_GEOMETRY_BYTES}}})
    assert not frames and not view.ready
