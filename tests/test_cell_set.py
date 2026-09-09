import pickle

import pytest

from structura_edit import CellSet, Selection


def test_from_box_roundtrip_volume_bounds_and_membership():
    box = Selection((3, 5, 2), (20, 7, 35))
    cells = CellSet.from_box(box)
    assert cells.volume == box.volume
    assert set(cells.positions()) == set(box.positions())
    assert cells.lower == box.lower and cells.upper == box.upper
    assert all(position in cells for position in box.positions())
    assert (2, 5, 2) not in cells and (20, 5, 2) not in cells and (3, 7, 2) not in cells and (3, 5, 1) not in cells


def test_bit_layout_is_msb_first():
    cells = CellSet.from_positions([(1, 2, 3)])
    key, bits = cells.sections[0]
    assert key == (0, 0, 0)
    local = 1 << 8 | 2 << 4 | 3
    assert bits[local >> 3] == 1 << (7 - local % 8)


def test_positions_order_is_deterministic():
    cells = CellSet.from_box(Selection((0, 0, 0), (20, 20, 20)))
    first = list(cells.positions())
    assert first == list(cells.positions())
    keys = [(x >> 4, y >> 4, z >> 4) for x, y, z in first]
    assert keys == sorted(keys)


def test_contains_floors_float_positions():
    cells = CellSet.from_positions([(1, 1, 1)])
    assert (1.2, 1.7, 1.9) in cells
    assert (1.9, 1.9, 1.9) in cells
    assert (2.0, 1.0, 1.0) not in cells
    assert (-0.5, 1.0, 1.0) not in cells


def test_negative_coordinates_stay_addressable():
    cells = CellSet.from_positions([(-1, 0, 0), (-17, 2, 3)])
    assert (-1, 0, 0) in cells and (-17, 2, 3) in cells
    assert (0, 0, 0) not in cells
    assert cells.lower == (-17, 0, 0) and cells.upper == (0, 3, 4)


def test_algebra_union_difference_shift_coercion():
    a = CellSet.from_positions([(0, 0, 0), (1, 0, 0), (2, 0, 0)])
    b = CellSet.from_positions([(1, 0, 0), (5, 5, 5)])
    assert sorted(a.union(b).positions()) == [(0, 0, 0), (1, 0, 0), (2, 0, 0), (5, 5, 5)]
    assert sorted(a.difference(b).positions()) == [(0, 0, 0), (2, 0, 0)]
    assert not a.difference(a) and a.difference(a).volume == 0
    assert sorted(a.union(Selection((0, 0, 0), (1, 1, 1))).positions()) == [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
    shifted = a.shifted((10, -2, 3))
    assert sorted(shifted.positions()) == [(10, -2, 3), (11, -2, 3), (12, -2, 3)]
    assert shifted.lower == (10, -2, 3) and shifted.upper == (13, -1, 4)


def test_from_positions_deduplicates_and_measures_tight_bounds():
    cells = CellSet.from_positions([(3, 1, 4), (3, 1, 4), (0, 9, 0), (3, 1, 5)])
    assert cells.volume == 3
    assert cells.lower == (0, 1, 0) and cells.upper == (4, 10, 6)


def test_value_semantics_and_pickling():
    left = CellSet.from_box(Selection((0, 0, 0), (2, 2, 2)))
    right = CellSet.from_positions(product_positions())
    assert left == right and hash(left) == hash(right)
    assert pickle.loads(pickle.dumps(left)) == left


def product_positions():
    from itertools import product
    return product(range(2), range(2), range(2))


def test_empty_set():
    cells = CellSet(())
    assert not cells and cells.volume == 0
    assert cells.lower == (0, 0, 0) and cells.upper == (0, 0, 0)
    assert (0, 0, 0) not in cells and list(cells.positions()) == []


@pytest.mark.parametrize("sections", [
    (((1, 0, 0), b"\x01" * 512), ((0, 0, 0), b"\x01" * 512)),
    (((0, 0, 0), b"\x01" * 512), ((0, 0, 0), b"\x01" * 512)),
    (((0, 0, 0), b"\x01" * 16),),
    (((0, 0, 0), bytes(512)),),
])
def test_invalid_sections_are_rejected(sections):
    with pytest.raises(ValueError):
        CellSet(sections)
