from itertools import product
import random

import pytest

from structura_edit.overview_model import DetailIntent, DetailTarget, OverviewNode, select_detail


def tree():
    children = tuple((0, *position) for position in product(range(2), repeat=3))
    nodes = {key: OverviewNode(key, (), 0, 10) for key in children}
    parent = (1, 0, 0, 0)
    nodes[parent] = OverviewNode(parent, children, 1, 20)
    return nodes, (parent,)


def test_detail_is_independent_of_iteration_order_and_prior_camera_path():
    nodes, roots = tree()
    expected = select_detail(nodes, roots, DetailTarget.at((2, 7, 4), 1080, 60))
    for seed in range(20):
        rows = list(nodes.items())
        random.Random(seed).shuffle(rows)
        target = DetailTarget.at((2 + seed / 100, 7, 4), 1080, 60)
        assert select_detail(dict(rows), roots, target) == expected


def test_refinement_keeps_complete_parent_when_children_do_not_fit():
    nodes, roots = tree()
    target = DetailTarget.at((1, 1, 1), 1080, 60)
    assert select_detail(nodes, roots, target, budget=70) == roots
    assert len(select_detail(nodes, roots, target, budget=80)) == 8
    with pytest.raises(ValueError, match="coverage"):
        select_detail(nodes, roots, target, budget=19)


def test_editable_region_is_excluded_without_hiding_its_neighbors():
    nodes, roots = tree()
    target = DetailTarget.at((1, 1, 1), 1080, 60, ((0, 0, 0), (16, 16, 16)))
    selected = select_detail(nodes, roots, target)
    assert len(selected) == 7 and (0, 0, 0, 0) not in selected


def test_old_arrivals_never_reactivate_a_cancelled_teleport():
    intent = DetailIntent()
    first = intent.request(DetailTarget.at((-0.1, -16, 0), 1080, 60), (1, 2, 3))
    second = intent.request(DetailTarget.at((100, 0, 0), 1080, 60), (100, 0, 0))
    assert not intent.accepts(first) and intent.accepts(second)
    intent.cancel()
    assert not intent.accepts(first) and not intent.accepts(second)
    assert DetailTarget.at((-0.1, -16, 0), 1080, 60).cell == (-1, -1, 0)
@pytest.mark.parametrize('blocks, changed, superseded', [(16, False, False), (64, False, False), (80, False, True), (0, True, True)])
def test_moving_camera_keeps_nearby_precomputation_but_rejects_changed_coverage(blocks, changed, superseded):
    from structura_edit.overview_model import DetailIntent

    intent = DetailIntent()
    intent.request(DetailTarget.at((0, 80, 0), 1080, 60))
    target = DetailTarget.at((blocks, 80, 0), 1080, 60, ((0, 0, 0), (16, 16, 16)) if changed else ())
    assert intent.superseded_by(target) is superseded
