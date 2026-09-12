from collections import Counter

import numpy as np

from overview_fixture import create_overview_world
from structura_edit.overview_batches import detail_batches, read_batches
from structura_edit.overview_build import build_overview
from structura_edit.overview_model import DetailTarget, select_detail, tile_bounds
from structura_edit.overview_store import read_meshes


def triangles(points, indices, origin):
    return Counter(tuple(sorted(tuple(point) for point in triangle)) for triangle in (points + origin)[indices])


def textured_faces(mesh, origin):
    result = Counter()
    height, width = mesh.image.shape[:2]
    for quad in mesh.quads:
        corners = mesh.uv[quad]
        samples = []
        for u, v in ((0.1, 0.2), (0.4, 0.7), (0.8, 0.3)):
            uv = corners[0] * (1 - u) * (1 - v) + corners[1] * u * (1 - v) + corners[2] * u * v + corners[3] * (1 - u) * v
            x, y = np.floor(uv * (width, -height) + (0, height)).astype(int)
            samples.append(tuple(mesh.image[np.clip(y, 0, height - 1), np.clip(x, 0, width - 1)]))
        result[(tuple(map(tuple, mesh.points[quad] + origin)), tuple(samples))] += 1
    return result


def test_packed_buffers_preserve_world_triangles_and_texture_coordinates(tmp_path):
    snapshot = build_overview(create_overview_world(tmp_path / "world"), "minecraft:overworld", tmp_path / "cache")
    for position in ((0, 12, 0), (100_000, 100_000, 100_000)):
        selected = select_detail(snapshot["nodes"], snapshot["roots"], DetailTarget.at(position, 1080, 60))
        batches = detail_batches(snapshot["nodes"], selected)
        assert Counter(tile for _, tiles in batches for tile in tiles) == Counter(selected)
        assert batches == detail_batches(snapshot["nodes"], reversed(selected))
        expected, actual = Counter(), Counter()
        expected_uv, actual_uv = Counter(), Counter()
        for tile, data in read_meshes(snapshot["path"], selected).items():
            origin = np.asarray(tile_bounds(tile)[0])
            if "lod" in data:
                lod = data["lod"]
                expected.update(triangles(lod.points, lod.triangles, origin))
            for mesh in data.get("meshes", ()):
                expected_uv.update(textured_faces(mesh, origin))
        for data in read_batches(snapshot["path"], batches).values():
            for packet in data['packets']:
                if packet.colors is not None:
                    actual.update(triangles(packet.points, packet.indices, data['origin']))
                if packet.image is not None:
                    from types import SimpleNamespace

                    mesh = SimpleNamespace(points=packet.points, quads=packet.indices, uv=packet.uv, image=packet.image)
                    actual_uv.update(textured_faces(mesh, data['origin']))
        assert actual == expected and actual_uv == expected_uv
