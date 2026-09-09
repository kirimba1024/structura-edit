from types import SimpleNamespace

import pytest

from structura_edit.height_slice import HeightSlice
from structura_edit.editor_document import EditorDocument
from structura_edit.ui import EditorWindow
from structura_edit.world_ui import WorldController


@pytest.fixture
def world_window(world_edit):
    requests, messages = [], []
    document = EditorDocument()
    document.load(world_edit)
    window = SimpleNamespace(
        document=document, assets=None,
        tasks=SimpleNamespace(busy=False, submit=lambda kind, callback, **args: requests.append((callback, args))),
        placement=SimpleNamespace(active=False),
        slicing=SimpleNamespace(value=HeightSlice()),
        entities_action=SimpleNamespace(isChecked=lambda: True),
        plotter=SimpleNamespace(camera=SimpleNamespace(position=(2, 1, 2))),
        status=SimpleNamespace(setText=messages.append),
        _confirm_discard=lambda: True, _error=messages.append,
    )
    window.world = WorldController(document, window.tasks, SimpleNamespace(plotter=window.plotter), None,
                                    options=lambda: dict(assets=None, include_entities=True, height=HeightSlice()),
                                    available=lambda: not window.placement.active, opened=lambda *args, **options: None)
    window.world.message.connect(messages.append)
    window.world.reset_request()
    return window, requests, messages


def test_failed_open_keeps_original_world_edits_and_refresh_path(world_window, tmp_path):
    window, requests, messages = world_window
    original = window.document.session
    original.apply(original.set_block((0, 0, 0), "minecraft:gold_block"))
    window.world.open(tmp_path / "unavailable-world")
    stale_callback = requests[-1][0]
    assert requests[-1][1]["path"] != str(original.path)
    EditorWindow._task_failed(window, "world", "Cannot open world")
    window.world.refresh()
    assert requests[-1][1]["path"] == str(original.path)
    assert requests[-1][1]["world_changes"] is original.world_changes
    assert window.document.session is original and original.dirty
    assert original.state_at((0, 0, 0)) == "minecraft:gold_block"
    assert messages[0] == "Cannot open world"
    window.world.received = lambda result, **options: pytest.fail("Stale world was accepted")
    stale_callback("stale result")


def test_cancelled_world_settings_restore_loaded_dimensions_and_limits(world_window):
    window, requests, _ = world_window
    original = window.document.session
    window.tasks.busy = True
    window.world.dimension = "minecraft:the_nether"
    window.world.center = (32, 64, 32)
    window.world.radius = 2
    window.world.vertical_radius = 64
    window.world.request(recenter=True)
    assert window.world.queued is not None
    window.world.reset_request()
    assert window.world.queued is None
    window.tasks.busy = False
    window.world.refresh()
    request = requests[-1][1]
    assert request["dimension"] == original.dimension
    assert request["radius"] == original.radius
    assert request["vertical_radius"] == original.vertical_radius


def test_old_world_failure_preserves_newer_queued_request(world_window):
    window, requests, _ = world_window
    window.tasks.busy = True
    window.world.center = (20, 64, 20)
    window.world.request(recenter=True)
    EditorWindow._task_failed(window, "world", "Previous request failed")
    window.tasks.busy = False
    window.world.flush()
    assert requests[-1][1]["center"] == (20, 64, 20)


def test_reset_without_loaded_world_clears_requested_path(world_window):
    window, _, _ = world_window
    window.document.load(None)
    window.world.reset_request()
    assert window.world.path is None and window.world.queued is None


def test_saved_session_does_not_rebuild_unchanged_materials(world_window):
    from structura_edit.editor_document import DocumentUpdate

    window, _, _ = world_window
    session = window.document.session
    window.materials = SimpleNamespace(set_counts=lambda counts: pytest.fail("Unchanged palette was rebuilt"))
    EditorWindow._document_updated(window, DocumentUpdate(session, session.fork()))


def test_world_refresh_restores_selection_while_followup_render_is_busy(world_window):
    from copy import copy

    window, _, _ = world_window
    document = window.document
    document.selected.select_block((1, 0, 1))
    document.selected.select_block((2, 0, 2), extend=True)
    document.selected.set_extending(True)
    session = copy(document.session)
    session._document = copy(session._document)
    session._document.origin = (1, 0, 1)
    changes = []
    world = window.world
    world.selection = SimpleNamespace(changed=SimpleNamespace(emit=lambda: changes.append(document.selected.region)))
    world.plotter.camera.direction = (0, 0, -1)
    world.camera.render = lambda: None
    def opened(session, **options):
        document.load(session)
        window.tasks.busy = True
    world.opened = opened
    world._replace_view((session, {}))
    assert document.selected.region.lower == (0, 0, 0)
    assert document.selected.region.upper == (2, 1, 2)
    assert document.selected.anchor == (0, 0, 0) and document.selected.extending
    assert changes == [document.selected.region]
