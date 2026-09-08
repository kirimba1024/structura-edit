import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import EditSession


@pytest.fixture(scope="session")
def qt_app():
    widgets = pytest.importorskip("PySide6.QtWidgets")
    app = widgets.QApplication.instance() or widgets.QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def structure():
    return Structure.from_root(from_snbt('''{
        DataVersion: 3955, size: [4, 2, 3], author: "Fixture author",
        custom: {keep: [I; 7, 11]},
        palette: [{Name: "minecraft:stone"},
                  {Name: "minecraft:chest", Properties: {facing: "north"}},
                  {Name: "minecraft:air"}, {Name: "minecraft:structure_void"}],
        blocks: [{pos: [0, 0, 0], state: 0, extra: "keep"},
                 {pos: [1, 0, 0], state: 1, nbt: {id: "minecraft:chest", Items: [{Slot: 0b, id: "minecraft:diamond", count: 3}]}},
                 {pos: [2, 0, 0], state: 2}, {pos: [3, 0, 0], state: 3}],
        entities: [{pos: [1.5d, 1.0d, 1.5d], blockPos: [1, 1, 1],
                    nbt: {id: "minecraft:armor_stand", custom: "keep"}}]
    }'''))


@pytest.fixture
def edit(structure):
    return EditSession.from_structure(structure)
