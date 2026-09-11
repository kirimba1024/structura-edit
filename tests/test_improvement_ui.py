from types import SimpleNamespace

from PySide6.QtWidgets import QFileDialog, QMessageBox

from structura_edit.action_state import history_action
from structura_edit.condition import Condition
from structura_edit.condition_ui import ConditionDialog
from structura_edit.mix import Mix
from structura_edit.mix_ui import MixDialog
from structura_edit.source_ui import SourceController
from structura_edit.editor_document import EditorDocument


def test_condition_and_mix_dialog_roundtrip_extended_values(qt_app):
    condition = Condition('all', (Condition('height', ('-10', '80')), Condition('block-entities', negate=True)))
    dialog = ConditionDialog(None, condition)
    assert dialog.build() == condition
    dialog.close()
    strict = ConditionDialog(None, Condition('properties', ('facing=north',), strict=True))
    assert strict.build().strict
    strict.close()
    mix = Mix((('minecraft:stone', 1), ('minecraft:gold_block', 1)), 50, anchor='world', gradient=(-10, 90))
    mixing = MixDialog(None, mix)
    assert mixing.build() == mix
    mixing.close()


def test_undo_action_matches_cancel_preview_even_without_history(edit):
    state = history_action(edit, 'undo', busy=False, preview=True, placing=False)
    assert state.enabled and state.action == 'cancel-preview'
    assert not history_action(edit, 'redo', busy=False, preview=True, placing=False).enabled
    assert not history_action(edit, 'undo', busy=True, preview=True, placing=False).enabled


def test_repeated_save_uses_one_target_and_open_waits_for_success(edit, tmp_path, monkeypatch, qt_app):
    document = EditorDocument()
    document.load(edit)
    saved, jobs = [], []
    def save(path, callback):
        jobs.append((path, callback))
        return True
    controller = SourceController(None, document, SimpleNamespace(busy=False), SimpleNamespace(save=save),
                                  SimpleNamespace(active=False), SimpleNamespace(active=False), opened=lambda _: None, saved=saved.append)
    paths = []
    target = tmp_path / 'working.NBT'
    def choose(*args):
        paths.append(args[2])
        return str(target), ''
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', choose)
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    controller.save_dialog()
    path, callback = jobs.pop()
    assert not saved
    edit.save(path)
    callback(edit)
    controller.save_dialog()
    controller.save_dialog()
    assert len(paths) == 1 and [path for path, callback in jobs] == [target, target]
    jobs.clear()
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:diamond_block'))
    continued = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Save)
    assert not controller.confirm_discard(lambda: continued.append(True))
    assert not continued and len(jobs) == 1
    path, callback = jobs.pop()
    assert not continued and edit.dirty
    edit.save(path)
    callback(edit)
    assert continued == [True] and not edit.dirty


def test_cancelled_save_path_does_not_continue(edit, monkeypatch, qt_app):
    document = EditorDocument()
    document.load(edit)
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    controller = SourceController(None, document, SimpleNamespace(busy=False), None,
                                  SimpleNamespace(active=False), SimpleNamespace(active=False), opened=lambda _: None, saved=lambda _: None)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Save)
    monkeypatch.setattr(QFileDialog, 'getSaveFileName', lambda *args: ('', ''))
    continued = []
    assert not controller.confirm_discard(lambda: continued.append(True))
    assert not continued and edit.dirty


def test_autodraft_waits_until_stroke_and_preview_finish(edit, qt_app):
    from time import monotonic
    from PySide6.QtWidgets import QWidget
    from structura_edit.drafts_ui import DraftController

    window = QWidget()
    edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    window.document = SimpleNamespace(session=edit, pending=None)
    window.tasks = SimpleNamespace(busy=False)
    window.paint = SimpleNamespace(dragging=True)
    window.placement = SimpleNamespace(active=False)
    window.repeat = SimpleNamespace(active=False)
    drafts = DraftController(window)
    drafts.last_attempt = monotonic() - 31
    saved = []
    drafts.save = lambda: saved.append(True)
    drafts.tick()
    assert not saved
    window.paint.dragging = False
    window.document.pending = object()
    drafts.tick()
    assert not saved
    window.document.pending = None
    drafts.tick()
    assert saved == [True]
    window.close()
