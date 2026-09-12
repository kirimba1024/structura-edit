from types import SimpleNamespace

import pytest

from structura_edit.world_streaming import WorldStreaming


@pytest.mark.parametrize('radius', [0, 1, 6])
def test_streaming_coalesces_motion_preserves_full_columns_and_retries_when_idle(radius):
    requests = []
    session = SimpleNamespace(path='world', dimension='minecraft:overworld', radius=radius,
                              vertical_radius=None, center=(0, 80, 0))
    position = [0, 80, 0]
    world = SimpleNamespace(active=True, document=SimpleNamespace(session=session), tasks=SimpleNamespace(busy=False),
                            camera_position=lambda: tuple(position), request=lambda: requests.append(world.center))
    streaming = WorldStreaming(world, lambda: True)
    position[1] = -40
    streaming.tick(0)
    streaming.tick(1)
    assert not requests
    world.tasks.busy = True
    position[0] = 64
    streaming.tick(2)
    position[0] = 96
    streaming.tick(3)
    streaming.tick(4)
    assert not requests
    world.tasks.busy = False
    streaming.tick(5)
    assert len(requests) == 1
    assert abs(requests[0][0] - position[0]) <= max(8, radius * 8)
    streaming.tick(6)
    assert len(requests) == 1
    world.active = False
    streaming.tick(7)
    assert streaming.requested is None
