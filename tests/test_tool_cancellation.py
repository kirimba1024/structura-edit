from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel, QWidget

from structura_edit import CellSet
from structura_edit.edit_workflow import EditWorkflow
from structura_edit.editor_document import EditorDocument
from structura_edit.paint_ui import PaintController
from structura_edit.picking import Hit
from structura_edit.planar_ui import PlanarController


class ToolNavigation(QObject):
    hovered = Signal(object)
    looking = False


@pytest.fixture
def tool_window(edit, qt_app):
    window = QWidget()
    window.document = EditorDocument()
    window.document.load(edit)
    window.document.selected.set_bounds((0, 0, 0), (1, 1, 1))
    window.navigation = ToolNavigation(window)
    window.connected = SimpleNamespace(set_active=lambda value: None)
    window.status = QLabel(window)
    window.menus = SimpleNamespace(actions={name: QAction(window) for name in ('planar', 'paint')})
    window.requests, window.cancelled, window.previews = [], [], []
    def submit(kind, callback, **args):
        window.tasks.kind, window.tasks.busy = kind, True
        window.requests.append((callback, args))
        return True
    window.tasks = SimpleNamespace(kind=None, busy=False, submit=submit)
    window.tasks.submit_document = lambda command, callback, **args: submit(command.kind, callback, **args)
    window.edits = EditWorkflow(window.document, window.tasks, previewed=window.previews.append, updated=lambda _: None)
    def cancel_task():
        window.cancelled.append(window.tasks.kind)
        window.tasks.kind, window.tasks.busy = None, False
        window.document.invalidate()
    window.cancel_task = cancel_task
    window._selection_changed = window.document.invalidate
    window.show_operation = lambda mode: pytest.fail('A cancelled selection opened an operation')
    yield window
    window.close()


def test_planar_exit_cancels_work_and_rejects_late_result_after_restart(tool_window):
    window = tool_window
    controller = PlanarController(window)
    before = window.document.selection()
    controller.toggle()
    controller.pick(Hit((0, 0, 0), (0, 1, 0)))
    received, _ = window.requests.pop()
    controller.toggle()
    assert window.cancelled == ['planar'] and not window.tasks.busy
    controller.toggle()
    received(CellSet.from_positions([(0, 0, 0), (1, 0, 0)]))
    assert controller.active and window.document.selection() == before


def test_paint_exit_cancels_work_and_rejects_late_preview(tool_window):
    window = tool_window
    controller = PaintController(window)
    controller.active = True
    try:
        assert window.edits.prepare('paint', points=((0.5, 0.5, 0.5),), target='minecraft:gold_block')
        received, _ = window.requests.pop()
        controller.toggle()
        assert window.cancelled == ['paint'] and not window.tasks.busy
        received(window.document.session.set_block((0, 0, 0), 'minecraft:gold_block'))
        assert window.document.pending is None and not window.previews
        assert not window.document.session.dirty
    finally:
        controller.close()
