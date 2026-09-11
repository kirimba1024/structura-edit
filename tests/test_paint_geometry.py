from itertools import permutations, product
from math import dist

import pytest
from amulet_nbt import from_snbt
from structura_core import Structure

from structura_edit import CellSet, EditSession
from structura_edit.paint import paint_stroke


def blocks(size, positions=None, **limits):
    source = Structure.from_root(from_snbt('{DataVersion:3955,size:[1,1,1],palette:[{Name:"minecraft:stone"}],blocks:[],entities:[]}'))
    source.size = size
    source.present = dict.fromkeys(positions if positions is not None else product(*(range(v) for v in size)), 0)
    return EditSession.from_structure(source, **limits)


@pytest.mark.parametrize('axes', list(permutations(range(3))))
@pytest.mark.parametrize('radius', [0.1, 0.5, 1, 2.25])
def test_stroke_matches_geometric_oracle_with_fractional_endpoints(axes, radius):
    session = blocks((9, 9, 9))
    start, stop = (0.2, 3.5, 7.9), (8.8, 5.1, -2.5)
    start, stop = tuple(start[i] for i in axes), tuple(stop[i] for i in axes)
    direction = tuple(b - a for a, b in zip(start, stop))
    length = dist(start, stop)
    unit = tuple(v / length for v in direction)
    expected = set()
    for point in session.select().positions():
        center = tuple(p + 0.5 for p in point)
        along = max(0, min(length, sum((p - a) * v for p, a, v in zip(center, start, unit))))
        nearest = tuple(a + along * v for a, v in zip(start, unit))
        if dist(center, nearest) <= radius:
            expected.add(point)
    for points in ((start, stop), (stop, start)):
        assert set(paint_stroke(session, session.select(), points, 'minecraft:gold_block', radius).positions) == expected


def test_long_diagonal_stroke_uses_tube_budget_and_matches_dense_samples():
    size = 256
    positions = [(i, i, i) for i in range(size)]
    session = blocks((size, size, size), positions, operation_limit=10_000)
    points = [tuple(i + 0.5 for _ in range(3)) for i in range(size)]
    coarse = paint_stroke(session, session.select(), (points[0], points[-1]), 'minecraft:gold_block', 1)
    fine = paint_stroke(session, session.select(), points, 'minecraft:gold_block', 1)
    assert set(coarse.positions) == set(fine.positions) == set(positions)


def test_sparse_selection_and_disconnected_single_samples():
    session = blocks((7, 7, 7))
    selected = CellSet.from_positions([(0, 0, 0), (1, 1, 1), (6, 6, 6)])
    change = paint_stroke(session, selected, [(0.5, 0.5, 0.5), None, (6.5, 6.5, 6.5)], 'minecraft:gold_block', 0.5)
    assert set(change.positions) == {(0, 0, 0), (6, 6, 6)}
