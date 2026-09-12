import numpy as np
import pytest

from structura_edit.map_environment import MapEnvironment


def caves():
    state = np.zeros((9, 24, 9), np.int32)
    state[:, 3:7, :] = -1
    state[:, 13:18, :] = -1
    return MapEnvironment(state, ['minecraft:stone'])


def test_cave_map_keeps_separate_floors_and_does_not_show_bedrock():
    environment = caves()
    lower, lower_heights = environment.floor(5)
    upper, upper_heights = environment.floor(15)
    assert np.all(lower == 0) and np.all(upper == 0)
    assert np.all(lower_heights == 2) and np.all(upper_heights == 12)
    assert environment.floor(15)[0] is upper


def test_roof_hole_keeps_cave_mode_and_leaves_do_not_count_as_roof():
    state = np.full((9, 24, 9), -1, np.int32)
    state[:, 0, :] = 0
    state[:, 12, :] = 0
    state[4, 12, 4] = -1
    environment = MapEnvironment(state, ['minecraft:stone', 'minecraft:birch_leaves'])
    assert environment.cut((4.5, 5, 4.5)) is not None
    assert environment.cut((4.5, 13, 4.5)) is None
    state[state == 0] = 1
    environment = MapEnvironment(state, ['minecraft:stone', 'minecraft:birch_leaves'])
    assert environment.cut((4.5, 5, 4.5)) is None


@pytest.mark.parametrize('height', [1, 2, 8])
def test_no_cave_is_reported_as_empty(height):
    environment = MapEnvironment(np.zeros((2, height, 3), np.int32), ['minecraft:stone'])
    values, heights = environment.floor(1)
    assert values.shape == (2, 1, 3) and heights.shape == (3, 2)
    assert np.all(values == -1)
