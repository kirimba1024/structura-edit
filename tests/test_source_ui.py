from types import SimpleNamespace

import pytest

from structura_edit.editor_document import EditorDocument
from structura_edit.source_loading import SourceVersionRequired
from structura_edit.source_ui import SourceController


@pytest.fixture
def sources(edit):
    document = EditorDocument()
    document.load(edit)
    requests, opened, worlds = [], [], []
    tasks = SimpleNamespace(busy=False, submit=lambda kind, callback, **args: requests.append((kind, callback, args)))
    world = SimpleNamespace(active=False, open=worlds.append)
    sources = SourceController(None, document, tasks, None, world, SimpleNamespace(active=False),
                               opened=opened.append, saved=lambda session: None)
    return sources, requests, opened, worlds


@pytest.mark.parametrize('world', [False, True])
def test_open_preserves_document_when_discard_is_declined(sources, tmp_path, world):
    controller, requests, opened, worlds = sources
    original = controller.document.session
    original.apply(original.set_block((0, 0, 0), 'minecraft:gold_block'))
    controller.confirm_discard = lambda: False
    controller.open_path(tmp_path if world else tmp_path / 'new.nbt')
    assert not requests and not opened and not worlds
    assert controller.document.session is original and original.dirty


def test_missing_version_retry_preserves_options_and_delivers_only_complete_source(sources, monkeypatch):
    controller, requests, opened, _ = sources
    options = dict(path='legacy.schem', region=None, palette_index=2)
    monkeypatch.setattr('structura_edit.source_ui.source_version_options', lambda parent, request: dict(request.options, source_data_version=2586))
    controller._received(SourceVersionRequired(options))
    kind, received, args = requests.pop()
    assert kind == 'open' and args == dict(options, source_data_version=2586) and not opened
    received(controller.document.session)
    assert opened == [controller.document.session]


def test_cancelled_version_prompt_keeps_loaded_document(sources, monkeypatch):
    controller, requests, opened, _ = sources
    messages = []
    controller.message.connect(messages.append)
    monkeypatch.setattr('structura_edit.source_ui.source_version_options', lambda parent, request: None)
    controller._received(SourceVersionRequired(dict(path='legacy.schem')))
    assert not requests and not opened and controller.document.session is not None
    assert messages == ['Open cancelled']


def test_open_callback_errors_reach_task_error_handler(sources):
    controller, _, _, _ = sources
    def fail(session):
        raise OSError('Unable to prepare history')
    controller.opened = fail
    with pytest.raises(OSError, match='prepare history'):
        controller._received(controller.document.session)
