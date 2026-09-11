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


def test_large_catalog_is_virtual_and_reopening_keeps_model_and_icons(qt_app):
    from PySide6.QtGui import QIcon
    from structura_edit.material_model import MaterialModel

    panel = MaterialsPanel()
    panel.catalog = {f'example:block_{index}': f'Block {index}' for index in range(20_000)}
    panel.reload()
    assert isinstance(panel.model, MaterialModel)
    assert panel.model.rowCount() >= 20_000
    resets = []
    panel.model.modelReset.connect(lambda: resets.append(True))
    panel.model.set_icon(panel.model.index(0, 0), 'example:block_0', QIcon())
    panel.reload()
    assert not resets
    assert 'example:block_0' in panel.model.icons
    panel.search.setText('example:block_19999')
    assert panel.filtered.rowCount() == 1
    assert panel.filtered.index(0, 0).data(Qt.ItemDataRole.UserRole) == 'example:block_19999'
    for index in range(600):
        panel.model.set_icon(panel.model.index(0, 0), f'example:block_{index}', QIcon())
    assert len(panel.model.icons) == 512
    panel.close()


def test_invalid_material_is_explained_before_preview(qt_app):
    panel = OperationPanel()
    panel.mode.setCurrentText('Walls')
    panel.fields['target'].setText('ыminecraft:stone')
    assert not panel.validate_inputs()
    assert 'ыminecraft:stone' in panel.validation.text()
    assert 'minecraft:stone' in panel.validation.text()
    panel.fields['target'].setText('minecraft:stone')
    assert panel.validate_inputs()
    assert panel.validation.isHidden()
    panel.close()
