from dataclasses import asdict, dataclass
import json
from math import atan2, cos, isfinite, pi, radians, sin, sqrt


@dataclass(frozen=True)
class FlightPath:
    name: str
    position: tuple
    target: tuple
    travel: tuple = (0, 0, 0)
    yaw_degrees: float = 0

    def __post_init__(self):
        if not self.name or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in self.name):
            raise ValueError("Flight names must use lowercase letters, digits, underscores or hyphens")
        for vector in (self.position, self.target, self.travel):
            if len(vector) != 3 or not all(isfinite(value) for value in vector):
                raise ValueError("Camera coordinates must contain three finite numbers")
        if self.position == self.target or not isfinite(self.yaw_degrees):
            raise ValueError("Camera direction must be nonzero and rotation must be finite")
        if not any(self.travel) and not self.yaw_degrees:
            raise ValueError("A flight must move or rotate the camera")

    def pose(self, elapsed, seconds):
        phase = min(1, max(0, elapsed / seconds))
        distance = (1 - cos(2 * pi * phase)) / 2
        position = tuple(value + distance * offset for value, offset in zip(self.position, self.travel))
        direction = tuple(target - value for target, value in zip(self.target, self.position))
        yaw = atan2(direction[0], direction[2]) + radians(self.yaw_degrees) * phase
        horizontal = sqrt(direction[0] ** 2 + direction[2] ** 2)
        direction = horizontal * sin(yaw), direction[1], horizontal * cos(yaw)
        return position, tuple(value + offset for value, offset in zip(position, direction))

    def record(self):
        return asdict(self)


def load_paths(path):
    records = json.loads(path.read_text())
    if not isinstance(records, list) or not records:
        raise ValueError("Flight paths must be a nonempty JSON list")
    paths = [FlightPath(name=record["name"], position=tuple(record["position"]), target=tuple(record["target"]),
                        travel=tuple(record.get("travel", (0, 0, 0))), yaw_degrees=record.get("yaw_degrees", 0))
             for record in records]
    if len({path.name for path in paths}) != len(paths):
        raise ValueError("Flight names must be unique")
    return paths
