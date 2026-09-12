from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from structura_edit.overview_model import DetailIntent, DetailTarget
from structura_edit.overview_ui import OverviewController


@pytest.mark.parametrize("arrival", ["selection", "upload"])
@pytest.mark.parametrize("motion", ["position", "direction", "none"])
def test_completed_overview_cannot_teleport_over_new_camera_input(arrival, motion):
    position = (36, 14, 4)
    direction = (0, 0, -1)
    camera = SimpleNamespace(move_to=Mock(), render=Mock(), needs_render=False)
    window = SimpleNamespace(
        camera=camera,
        world=SimpleNamespace(camera_position=lambda: (37, 14, 4) if motion == "position" else position),
        plotter=SimpleNamespace(camera=SimpleNamespace(direction=(1, 0, 0) if motion == "direction" else direction)),
        document=SimpleNamespace(session=SimpleNamespace(origin=(16, 0, 0))),
    )
    intent = DetailIntent()
    destination = (2000, 300, 0)
    generation = intent.request(DetailTarget.at(destination, 1080, 60), destination)
    scene = SimpleNamespace(begin=Mock(), missing=lambda: (), publish=Mock(return_value=True))
    controller = SimpleNamespace(
        intent=intent, window=window, scene=scene, snapshot={"path": "overview.sqlite"},
        last_position=position, last_direction=direction, document_preparation=None,
        cancel=Mock(side_effect=intent.cancel), _release_unused_snapshots=Mock(),
        progress=SimpleNamespace(finish=Mock()), satisfied=None,
    )
    controller._publish = lambda token: OverviewController._publish(controller, token)
    if arrival == "selection":
        OverviewController._selected(controller, generation, {})
    else:
        controller._publish(generation)
    if motion == "none":
        controller.cancel.assert_not_called()
        scene.publish.assert_called_once_with((16, 0, 0))
        camera.move_to.assert_called_once_with((1984, 300, 0))
        assert controller.satisfied == intent.target and intent.destination is None
    else:
        controller.cancel.assert_called_once_with()
        scene.publish.assert_not_called()
        camera.move_to.assert_not_called()
        assert intent.target is None and intent.destination is None
