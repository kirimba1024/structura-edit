import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import CellSet, EditSession


def as_map(change):
    return {delta.position: ((delta.before.state if delta.before else None), delta.after.state) for delta in change.changes}


@pytest.fixture
def solid():
    structure = Structure.from_root(from_snbt('''{
        DataVersion: 3955, size: [8, 8, 8],
        palette: [{Name: "minecraft:stone"}, {Name: "minecraft:air"}],
        blocks: [{pos: [0, 0, 0], state: 0}]
    }'''))
    structure.present = {(x, y, z): 0 for x in range(8) for y in range(7) for z in range(8)}
    structure.block_nbt = {}
    return EditSession.from_structure(structure)


def test_hollow_keeps_shell_of_one(solid):
    change = solid.shape(solid.select(((0, 0, 0), (8, 7, 8))), "minecraft:air", form="Hollow")
    cleared = {position for position, (_, after) in as_map(change).items() if after == "minecraft:air"}
    assert len(cleared) == 180
    assert (1, 1, 1) in cleared and (6, 5, 6) in cleared
    for position in ((0, 3, 3), (7, 3, 3), (3, 0, 3), (3, 6, 3), (3, 3, 0), (3, 3, 7)):
        assert position not in cleared


def test_hollow_thickness_two(solid):
    change = solid.shape(solid.select(((0, 0, 0), (8, 7, 8))), "minecraft:air", form="Hollow", thickness=2)
    cleared = {position for position, (_, after) in as_map(change).items() if after == "minecraft:air"}
    assert cleared == {(x, y, z) for x in range(2, 6) for y in range(2, 5) for z in range(2, 6)}


def test_hollow_matches_box_for_cell_sets(solid):
    box = solid.select(((0, 0, 0), (8, 7, 8)))
    cells = CellSet.from_box(box)
    left = as_map(solid.shape(cells, "minecraft:air", form="Hollow"))
    right = as_map(solid.shape(box, "minecraft:air", form="Hollow"))
    assert left == right


def test_overlay_places_above_column_tops(solid):
    change = solid.shape(solid.select(((0, 0, 0), (8, 8, 8))), "minecraft:torch", form="Overlay surface")
    placed = {position for position, (_, after) in as_map(change).items() if after == "minecraft:torch"}
    assert placed == {(x, 7, z) for x in range(8) for z in range(8)}


def test_overlay_stays_inside_selection(solid):
    change = solid.shape(solid.select(((0, 0, 0), (8, 7, 8))), "minecraft:torch", form="Overlay surface")
    assert len(change) == 0


def test_walls_boundary_of_cell_set(solid):
    cells = CellSet.from_positions([(x, y, z) for x in range(3) for y in range(2) for z in range(3)] + [(3, 0, 0)])
    walls = as_map(solid.shape(cells, "minecraft:gold_block", form="Walls"))
    assert (0, 0, 1) in walls and (3, 0, 0) in walls and (1, 0, 0) in walls
    assert (1, 0, 1) not in walls and (1, 1, 1) not in walls
    assert len(walls) == 17
