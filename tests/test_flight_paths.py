import json

import pytest

from flight_paths import FlightPath, load_paths


def test_path_returns_to_original_camera_and_crosses_detail_boundary():
    path = FlightPath("boundary", (-40, 20, 0), (-40, 20, 1), (80, 0, 0))
    assert path.pose(0, 30) == (path.position, path.target)
    assert path.pose(15, 30) == ((40, 20, 0), (40, 20, 1))
    assert path.pose(30, 30) == (path.position, path.target)
    assert path.pose(40, 30) == (path.position, path.target)


def test_rotation_uses_elapsed_time():
    path = FlightPath("turn", (0, 0, 0), (0, 1, 10), yaw_degrees=360)
    position, target = path.pose(7.5, 30)
    assert position == (0, 0, 0)
    assert target == pytest.approx((10, 1, 0))
    assert path.pose(30, 30)[1] == pytest.approx(path.target)


@pytest.mark.parametrize("values", (
    dict(name="../escape"), dict(position=(0, 0)), dict(target=(0, 0, 0)),
    dict(travel=(float("nan"), 0, 0)), dict(yaw_degrees=float("inf")), dict(travel=(0, 0, 0)),
))
def test_invalid_flight(values):
    arguments = dict(name="forest", position=(0, 0, 0), target=(0, 0, 1), travel=(10, 0, 0))
    with pytest.raises(ValueError):
        FlightPath(**dict(arguments, **values))


def test_path_file_round_trip_and_unique_names(tmp_path):
    path = FlightPath("forest", (0, 0, 0), (0, 0, 1), (10, 0, 0))
    filename = tmp_path / "paths.json"
    filename.write_text(json.dumps([path.record()]))
    assert load_paths(filename) == [path]
    filename.write_text(json.dumps([path.record(), path.record()]))
    with pytest.raises(ValueError, match="unique"):
        load_paths(filename)
