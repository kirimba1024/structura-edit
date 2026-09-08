from threading import Event, get_ident
from time import monotonic

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from structura_edit.selection_stats_ui import SelectionStats


def test_disclosure_runs_off_gui_coalesces_changes_and_never_shows_stale_counts(qt_app, edit, monkeypatch):
    entered, release = Event(), Event()
    calls = []
    gui_thread = get_ident()
    def count(session, selection, assets):
        assert get_ident() != gui_thread
        calls.append(selection)
        entered.set()
        assert release.wait(5)
        return [("minecraft:stone", selection.volume, None, (100, 100, 100))]
    monkeypatch.setattr("structura_edit.selection_stats_ui.selection_materials", count)
    host, stats = QWidget(), SelectionStats()
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    layout = QVBoxLayout(host)
    layout.addWidget(stats.toggle)
    layout.addWidget(stats)
    host.show()
    first = edit.select(((0, 0, 0), (1, 1, 1)))
    last = edit.select(((0, 0, 0), (4, 2, 3)))
    def wait_for(predicate):
        until = monotonic() + 5
        while not predicate() and monotonic() < until:
            QTest.qWait(20)
        assert predicate()
    try:
        stats.set_context(edit, first, None, visible=True)
        QTest.qWait(250)
        assert not calls and not stats.toggle.isChecked() and stats.isHidden()
        stats.toggle.click()
        wait_for(entered.is_set)
        stats.set_context(edit, edit.select(((1, 0, 0), (2, 1, 1))), None, visible=True)
        stats.set_context(edit, last, None, visible=True)
        assert stats.model.rowCount() == 0 and stats.info.text() == "Counting…"
        release.set()
        wait_for(lambda: stats.model.rowCount() == 1)
        assert stats.model.item(0).text() == "24" and calls == [first, last]
        stats.toggle.click()
        stats.set_context(edit, first, None, visible=True)
        QTest.qWait(250)
        assert len(calls) == 2 and stats.isHidden()
        stats.toggle.click()
        wait_for(lambda: stats.model.rowCount() == 1)
        assert stats.model.item(0).text() == "1"
    finally:
        release.set()
        stats.shutdown()
        host.close()
        host.deleteLater()


def test_material_counts_use_compact_cells_and_explain_empty_space_only_in_tooltip(qt_app, edit):
    stats = SelectionStats()
    stats.context = edit, edit.select(), None
    try:
        stats._show_rows([("minecraft:oak_leaves", 22, None, (40, 100, 20)), ("mod:soil", 5, None, (100, 50, 20))])
        assert stats.items.gridSize().width() < 80
        assert stats.items.gridSize().width() % 4 == 0
        assert stats.info.text() == "27 blocks · 2 types"
        assert "Empty space is not counted" in stats.info.toolTip()
        assert stats.model.item(0).toolTip() == "Oak Leaves\nminecraft:oak_leaves\n22 blocks"
        assert stats.model.item(1).toolTip() == "Soil\nmod:soil\n5 blocks"
    finally:
        stats.shutdown()
        stats.deleteLater()
