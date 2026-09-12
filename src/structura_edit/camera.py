import math
from itertools import product
from time import monotonic

import numpy as np


class FreeCamera:
    LOOK_SPEED = 0.003
    MAX_PITCH = math.radians(89)

    def __init__(self, plotter, changed):
        self.plotter = plotter
        self.changed = changed
        self.needs_render = False
        self.last_motion = 0
        self.plotter.camera.parallel_projection = False
        self.plotter.camera.view_angle = 60

    @property
    def moving(self):
        return monotonic() - self.last_motion < .12

    def translate(self, delta):
        self.last_motion = monotonic()
        camera = self.plotter.camera
        position = np.asarray(camera.position) + delta
        target = np.asarray(camera.focal_point) + delta
        camera.SetPosition(*position)
        camera.SetFocalPoint(*target)
        self.needs_render = True

    def move_to(self, position):
        self.translate(np.asarray(position) - self.plotter.camera.position)
        self.render()

    def focus_bounds(self, bounds):
        lower = tuple(min(bound[0][axis] for bound in bounds) for axis in range(3))
        upper = tuple(max(bound[1][axis] for bound in bounds) for axis in range(3))
        center = tuple((lo + hi) / 2 for lo, hi in zip(lower, upper))
        distance = max(6, math.dist(lower, upper) * 1.5)
        camera = self.plotter.camera
        camera.position = tuple(value - direction * distance for value, direction in zip(center, camera.direction))
        camera.focal_point = center
        self.needs_render = True
        self.render()

    def look(self, dx, dy):
        self.last_motion = monotonic()
        camera = self.plotter.camera
        forward = np.asarray(camera.direction, dtype=float)
        forward /= np.linalg.norm(forward)
        yaw = math.atan2(forward[0], forward[2]) - dx * self.LOOK_SPEED
        pitch = np.clip(math.asin(np.clip(forward[1], -1, 1)) - dy * self.LOOK_SPEED,
                        -self.MAX_PITCH, self.MAX_PITCH)
        direction = (math.sin(yaw) * math.cos(pitch), math.sin(pitch), math.cos(yaw) * math.cos(pitch))
        camera.focal_point = np.asarray(camera.position) + direction
        camera.up = (0, 1, 0)
        self.needs_render = True

    def step(self, axes, speed, elapsed):
        if not any(axes):
            return
        forward = np.asarray(self.plotter.camera.direction)
        right = np.cross(forward, (0, 1, 0))
        length = np.linalg.norm(right)
        right = right / length if length > 1e-6 else np.array((1, 0, 0))
        delta = right * axes[0] + np.array((0, axes[1], 0)) + forward * axes[2]
        length = np.linalg.norm(delta)
        if length:
            self.translate(delta * speed * elapsed / length)

    def frame(self, size, origin=(0, 0, 0)):
        camera = self.plotter.camera
        center = np.asarray(size) / 2
        outward = np.array((0.8, 0.65, 1.0))
        outward /= np.linalg.norm(outward)
        right = np.cross(-outward, (0, 1, 0))
        right /= np.linalg.norm(right)
        up = np.cross(right, -outward)
        width, height = getattr(self.plotter, "window_size", (1380, 880))
        tangent = math.tan(math.radians(camera.view_angle) / 2)
        aspect = max(.1, width / max(1, height))
        corners = [np.asarray(corner) - center for corner in product(*((0, v) for v in size))]
        distance = max(float(point @ outward) + max(abs(point @ up) / tangent,
                       abs(point @ right) / (tangent * aspect)) for point in corners)
        camera.position = center + origin + outward * max(3, distance * 1.2)
        camera.focal_point = center + origin
        camera.up = (0, 1, 0)
        self.needs_render = True
        self.render()

    def render(self):
        if not self.needs_render:
            return
        self.needs_render = False
        camera = self.plotter.camera
        bounds = np.asarray(self.plotter.bounds).reshape(3, 2)
        extent = np.maximum(np.abs(bounds[:, 0] - camera.position), np.abs(bounds[:, 1] - camera.position))
        camera.clipping_range = (0.05, max(100, np.linalg.norm(extent) * 2))
        self.plotter.render()
        self.changed(camera.position, camera.direction)
