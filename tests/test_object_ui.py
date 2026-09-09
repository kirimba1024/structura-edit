from types import SimpleNamespace

import pytest

from structura_edit.editor_document import EditorDocument
from structura_edit.object_ui import ObjectController


@pytest.mark.parametrize('change_document', ['reopen', 'edit', 'close'])
def test_late_object_result_is_ignored_after_document_changes(edit, change_document):
    document = EditorDocument()
    document.load(edit)
    pending, received = [], []
    controller = SimpleNamespace(document=document, tasks=SimpleNamespace(
        submit=lambda kind, callback, **args: pending.append(callback)))
    ObjectController._submit(controller, 'inspect', received.append)
    if change_document == 'edit':
        edit.apply(edit.set_block((0, 0, 0), 'minecraft:gold_block'))
    else:
        document.load(edit if change_document == 'reopen' else None)
    pending.pop()(['outdated inventory'])
    assert not received


def test_inspector_rejects_another_document_with_the_same_revision(edit, structure):
    from structura_edit import EditSession

    document = EditorDocument()
    document.load(edit)
    token = document.session_token
    messages = []
    controller = SimpleNamespace(document=document, available=lambda: True,
                                 dialog=SimpleNamespace(errors=SimpleNamespace(setText=messages.append)))
    document.load(EditSession.from_structure(structure))
    ObjectController._edit(controller, token, [])
    assert messages == ['Document changed; reopen the inspector']
