from collections import Counter

import pytest

pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from structura_edit.materials import MaterialsPanel
from structura_edit.panels import OperationPanel


def test_material_search_preserves_exact_states_and_recent_choices_across_documents(qt_app):
    panel = MaterialsPanel()
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    chosen = []
    panel.chosen.connect(chosen.append)
    north, south = "minecraft:chest[facing=north]", "minecraft:chest[facing=south]"
    panel.set_counts(Counter({north: 2, south: 3, "minecraft:stone": 50}))
    panel.remember(north)
    panel.remember(south)
    panel.remember(north)
    panel.reload()
    panel.show()
    panel.search.setText("CHEST[")
    assert panel.filtered.rowCount() == 2
    QTest.keyClick(panel.search, Qt.Key.Key_Down)
    QTest.keyClick(panel.search, Qt.Key.Key_Return)
    assert chosen == [south]
    panel.set_counts(Counter({"minecraft:glass": 8}))
    QTest.keyClick(panel.search, Qt.Key.Key_Return)
    assert chosen[-1] == south
    assert not panel.counts[south]
    panel.search.setText("missing")
    QTest.keyClick(panel.search, Qt.Key.Key_Return)
    assert len(chosen) == 2 and not panel.use.isEnabled()
    for index in range(100):
        panel.remember(f"minecraft:test_{index}")
    panel.reload()
    assert panel.filtered.rowCount() == 0
    panel.search.clear()
    assert panel.filtered.rowCount() <= 13
    panel.close()
    panel.deleteLater()


def test_fill_and_replace_share_target_but_keep_source_and_normal_text_input(qt_app):
    panel = OperationPanel()
    target, source = panel.fields["target"], panel.fields["source"]
    source.setText("minecraft:stone")
    target.setText("minecraft:chest[facing=north]")
    panel.mode.setCurrentText("Fill")
    assert panel.values()["target"] == "minecraft:chest[facing=north]"
    panel.mode.setCurrentText("Erase")
    panel.mode.setCurrentText("Replace")
    assert panel.values()["source"] == "minecraft:stone"
    assert panel.values()["target"] == "minecraft:chest[facing=north]"
    target.selectAll()
    QTest.keyClicks(target, "minecraft:glass")
    panel.mode.setCurrentText("Fill")
    assert panel.values()["target"] == "minecraft:glass"
    panel.reset_settings()
    assert panel.values()["target"] == "minecraft:stone"
    panel.close()
    panel.deleteLater()
