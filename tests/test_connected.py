import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import CellSet, EditSession
from structura_edit.connected import CONNECTED_LIMIT, connected_selection
from structura_edit.selection import RegionSelection
from structura_edit.tasks import execute


@pytest.fixture
def linked():
    structure = Structure.from_root(from_snbt('''{
        DataVersion: 3955, size: [6, 3, 6],
        palette: [{Name: "minecraft:stone"}, {Name: "minecraft:oak_log", Properties: {axis: "y"}}, {Name: "minecraft:air"}],
        blocks: [{pos: [0, 0, 0], state: 0}]
    }'''))
    slab = {(x, y, z): 0 for x in range(1, 4) for y in range(2) for z in range(1, 3)}
    strip = {(x, 0, 5): 0 for x in range(6)}
    structure.present = {**slab, **strip, (2, 1, 2): 1}
    structure.block_nbt = {}
    return EditSession.from_structure(structure), slab, strip


def test_criteria_split_components(linked):
    edit, slab, strip = linked
    assert sorted(connected_selection(edit, (2, 1, 2), criterion="state").cells.positions()) == [(2, 1, 2)]
    assert sorted(connected_selection(edit, (1, 0, 1), criterion="material").cells.positions()) == sorted(set(slab) - {(2, 1, 2)})
    assert sorted(connected_selection(edit, (0, 0, 5), criterion="non-air").cells.positions()) == sorted(strip)
    assert sorted(connected_selection(edit, (2, 1, 2), criterion="non-air").cells.positions()) == sorted(slab)


def test_edits_change_connectivity(linked):
    edit, slab, _ = linked
    edit.apply(edit.set_block((2, 0, 1), "minecraft:air"))
    result = connected_selection(edit, (1, 0, 1), criterion="material")
    assert (2, 0, 1) not in result.cells and (2, 1, 1) in result.cells


def test_limit_and_empty_start_errors(linked):
    edit, _, _ = linked
    with pytest.raises(ValueError, match="stricter criterion"):
        connected_selection(edit, (1, 0, 1), criterion="material", limit=3)
    with pytest.raises(ValueError, match="non-empty"):
        connected_selection(edit, (5, 2, 0), criterion="material")
    with pytest.raises(ValueError, match="inside the document"):
        connected_selection(edit, (6, 0, 0), criterion="material")
    with pytest.raises(ValueError, match="Criterion must be"):
        connected_selection(edit, (1, 0, 1), criterion="colour")


def test_progress_and_reference_oracle(linked):
    edit, slab, strip = linked
    progress = []
    result = connected_selection(edit, (0, 0, 5), criterion="material", progress=lambda *update: progress.append(update))
    expected = reference_flood(edit, (0, 0, 5), lambda state: state.split("[", 1)[0] == "minecraft:stone")
    assert set(result.cells.positions()) == expected == set(strip)
    assert progress[0] == ("Connected select", 0, CONNECTED_LIMIT)
    assert progress[-1] == ("Connected select", 18, 18)


def reference_flood(edit, start, matches):
    seen, frontier = {start}, [start]
    while frontier:
        following = []
        for position in frontier:
            for axis in range(3):
                for step in (-1, 1):
                    neighbour = tuple(v + (step if i == axis else 0) for i, v in enumerate(position))
                    if neighbour in seen or any(v < 0 or v >= s for v, s in zip(neighbour, edit.size)):
                        continue
                    state = edit.state_at(neighbour)
                    if state is not None and matches(state):
                        seen.add(neighbour)
                        following.append(neighbour)
        frontier = following
    return seen


def test_execute_connected_task(linked):
    edit, slab, _ = linked
    result = execute("connected", {"session": edit, "start": (1, 0, 1), "criterion": "material"})
    assert isinstance(result.cells, CellSet)
    assert set(result.cells.positions()) == set(slab) - {(2, 1, 2)}


def test_region_selection_accumulates_cells(linked):
    edit, slab, strip = linked
    model = RegionSelection()
    model.reset(edit.size)
    model.select_block((1, 0, 1))
    assert model.cells is None and model.current == model.region and model.current.volume == 1
    model.add_cells(CellSet.from_positions([(0, 0, 5), (1, 0, 5)]))
    assert model.cells.volume == 3
    assert model.region.lower == (0, 0, 1) and model.region.upper == (2, 1, 6)
    model.subtract_cells(CellSet.from_positions([(1, 0, 5)]))
    assert sorted(model.cells.positions()) == [(0, 0, 5), (1, 0, 1)]
    model.set_bounds((0, 0, 0), (1, 1, 1))
    assert model.cells is None and model.current.volume == 1
    model.add_cells(CellSet.from_positions(list(model.region.positions())))
    model.subtract_cells(CellSet.from_positions(list(model.region.positions())))
    assert model.current is None and model.region is None
    with pytest.raises(ValueError):
        model._set_cells(CellSet.from_positions([(6, 0, 0)]))


def test_document_token_tracks_cells(linked):
    edit, _, _ = linked
    from structura_edit.editor_document import EditorDocument

    document = EditorDocument()
    document.load(edit)
    first = document.selection_token
    document.selected.select_block((1, 0, 1))
    second = document.selection_token
    assert first != second
    document.selected.add_cells(CellSet.from_positions([(0, 0, 5)]))
    assert document.selection_token != second
    document.selected.add_cells(CellSet.from_positions([(1, 0, 5)]))
    assert document.selection_token != second
    assert document.selection() is document.selected.cells
