from itertools import product
from types import SimpleNamespace

import pytest

from structura_edit.action_state import editor_capabilities
from structura_edit.changes import ChangeSet
from structura_edit.editor_document import EditPreview
from structura_edit.placement import Placement
from structura_edit.task_protocol import TaskState
from structura_edit.ui import EditorWindow


def test_capability_matrix_obeys_edit_and_protected_task_invariants():
    empty = ChangeSet('document', 0, 'Empty', ())
    changed = ChangeSet('document', 0, 'Edit', (object(),))
    for opened, readonly, busy, selected, preview, transient in product(
            (False, True), (False, True), (False, True), (False, True), (None, empty, changed), ('none', 'place', 'repeat', 'stroke')):
        session = SimpleNamespace(readonly=readonly, dirty=True, _id='document', revision=0) if opened else None
        caps = editor_capabilities(session, busy=busy, protected=busy, selected=selected, preview=preview,
                                   scene_ready=True, placing=transient == 'place', repeating=transient == 'repeat',
                                   stroke=transient == 'stroke', placement_ready=True)
        if not opened or readonly or busy:
            assert not any((caps.can_apply, caps.can_save, caps.can_save_as, caps.can_operate,
                            caps.can_place, caps.can_seek_history, caps.can_save_draft))
        if busy:
            assert not caps.can_discard and not caps.can_select
        if preview is not None or transient != 'none':
            assert not any((caps.can_save, caps.can_save_as, caps.can_copy, caps.can_export, caps.can_place))
        if transient == 'stroke':
            assert not caps.can_apply
        if opened and not readonly and not busy and transient == 'none' and preview is empty:
            assert caps.can_discard and not caps.can_apply


def test_world_save_requires_changes_and_copy_waits_for_display():
    session = SimpleNamespace(readonly=False, dirty=False)
    assert not editor_capabilities(session, world=True).can_save
    assert editor_capabilities(session).can_save
    session.dirty = True
    assert editor_capabilities(session, world=True).can_save
    assert not editor_capabilities(session, world=True).can_save_as
    assert not editor_capabilities(session, selected=True).can_copy
    session.readonly = True
    caps = editor_capabilities(session, selected=True, scene_ready=True)
    assert caps.can_copy and caps.can_inspect and not caps.can_place


def test_stale_preview_can_be_discarded_but_not_applied(edit):
    change = edit.set_block((0, 0, 0), 'minecraft:glass')
    assert editor_capabilities(edit, preview=change, scene_ready=True).can_apply
    edit.apply(edit.set_block((1, 0, 0), 'minecraft:gold_block'))
    caps = editor_capabilities(edit, preview=change, scene_ready=True)
    assert not caps.can_apply and caps.can_discard


@pytest.fixture
def window(edit, qt_app):
    window = EditorWindow(off_screen=True)
    window.timer.stop()
    window.document.load(edit)
    window.document.selected.set_bounds((0, 0, 0), (1, 1, 1))
    window.views.ready = True
    yield window
    window.tasks._release(TaskState.IDLE)
    window.exit.approved = True
    window.document.load(None)
    window.close()


def test_menu_buttons_and_handlers_agree_during_preview_and_protected_apply(window, monkeypatch, tmp_path):
    document = window.document
    preview = EditPreview(document.session.set_block((0, 0, 0), 'minecraft:glass'))
    document.show_preview(preview)
    calls = []
    monkeypatch.setattr(window.edits, 'commit', lambda *args: calls.append('apply'))
    monkeypatch.setattr(window.edits, 'save', lambda *args, **kwargs: calls.append('save'))
    window._sync()
    assert window.menus.actions['apply'].isEnabled() and window.operation.apply.isEnabled()
    assert window.panels.recipe.apply.isEnabled()
    assert not window.menus.actions['save'].isEnabled() and not window.save_button.isEnabled()
    assert not window.sources.save_path(tmp_path / 'blocked.nbt')
    window.apply_pending()
    assert calls == ['apply']
    window.tasks.kind, window.tasks.state = 'apply', TaskState.RUNNING
    window._sync()
    assert not window.menus.actions['apply'].isEnabled()
    assert not window.menus.actions['discard'].isEnabled()
    assert not window.operation.discard.isEnabled() and not window.panels.recipe.discard.isEnabled()
    window.apply_pending()
    window.discard_pending()
    assert document.preview is preview and calls == ['apply']
    window.tasks._release(TaskState.IDLE)
    window._sync()
    cursor = document.session.history.cursor
    window.discard_pending()
    assert document.pending is None and document.session.history.cursor == cursor
    assert window.menus.actions['save'].isEnabled() and window.save_button.isEnabled()


def test_placement_apply_waits_for_model_and_visible_scene(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window.placement_review, 'apply', lambda: calls.append('place'))
    window.placement.preparing = True
    window._sync()
    assert not window.menus.actions['apply'].isEnabled()
    window.apply_pending()
    session = window.document.session
    window.placement.model = Placement(session.copy(window.document.selection()), (1, 0, 0))
    window.placement.preparing = False
    for ready in (False, True):
        window.views.ready = ready
        window._sync()
        assert window.menus.actions['apply'].isEnabled() == ready
        assert window.placement.bar.apply.isEnabled() == ready
        window.apply_pending()
    assert calls == ['place']


def test_connected_mode_survives_its_worker_but_stops_for_placement(window):
    window.connected.set_active(True)
    window.tasks.kind, window.tasks.state = 'connected', TaskState.RUNNING
    window._sync()
    assert window.connected.active
    assert not window.menus.actions['connected'].isEnabled()
    window.tasks._release(TaskState.IDLE)
    window._sync()
    assert window.connected.active and window.menus.actions['connected'].isEnabled()
    window.placement.preparing = True
    window._sync()
    assert not window.connected.active


def test_material_picker_can_replace_preview_inputs_without_changing_history(window, monkeypatch):
    document = window.document
    window.operation.mode.setCurrentText('Fill')
    document.show_preview(EditPreview(document.session.set_block((0, 0, 0), 'minecraft:glass')))
    window._sync()
    monkeypatch.setattr(window.panels.materials, 'catalog_request', lambda: None)
    assert window.menus.actions['materials'].isEnabled()
    window.operation.material_requested.emit('target')
    assert not window.panels.docks['materials'].isHidden()
    cursor = document.session.history.cursor
    window.materials.choose('minecraft:dirt')
    assert window.operation.values()['target'] == 'minecraft:dirt'
    assert document.preview is None and document.session.history.cursor == cursor


@pytest.mark.parametrize('transient', ['repeat', 'stroke'])
def test_save_and_preview_handlers_cannot_bypass_transient_modes(window, monkeypatch, tmp_path, transient):
    if transient == 'repeat':
        window.repeat.source = window.document.selection_token
    else:
        window.paint.points = []
    calls = []
    monkeypatch.setattr(window.edits, 'save', lambda *args: calls.append('save'))
    monkeypatch.setattr(window.edits, 'prepare', lambda *args, **kwargs: calls.append('preview'))
    window._sync()
    assert not window.menus.actions['save'].isEnabled()
    assert not window.operation.preview.isEnabled()
    assert not window.sources.save_path(tmp_path / 'blocked.nbt')
    window.preview_operation()
    window.preview_recipe()
    assert not calls
