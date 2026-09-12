from collections import Counter

import numpy as np
from structura_render.geometry import triangulate_quads

from overview_fixture import create_overview_world
from structura_edit.overview_batches import detail_batches, read_batches
from structura_edit.overview_build import build_overview
from structura_edit.overview_model import DetailTarget, select_detail, tile_bounds
from structura_edit.overview_store import read_meshes


def triangles(points, indices, origin):
    if indices.shape[1] == 4:
        indices = triangulate_quads(indices)
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


def test_lod_rectangle_packets_reach_vtk_with_correct_winding_and_without_source_buffers():
    from vtkmodules.util.numpy_support import vtk_to_numpy
    from vtkmodules.vtkFiltersCore import vtkTriangleFilter
    from structura_render.lod_geometry import LodMesh
    from structura_edit.render_packets import prepare_geometry
    from structura_edit.scene_geometry import packet_actor

    points = np.array(((0, 0, 0), (3, 0, 0), (3, 2, 0), (0, 2, 0)), np.float32)
    lod = LodMesh(points, np.array(((0, 1, 2), (0, 2, 3)), np.uint32), np.full((4, 4), 255, np.uint8))
    prepared = prepare_geometry(dict(lod=lod, meshes=[], flat=[]))
    assert 'lod' not in prepared and 'colored' not in prepared
    packet, = prepared['packets']
    assert packet.indices.shape == (1, 4)
    actor = packet_actor(packet, None)
    data = actor.GetMapper().GetInput()
    assert data.GetNumberOfPolys() == 1 and actor.GetProperty().GetBackfaceCulling()
    triangulated = vtkTriangleFilter()
    triangulated.SetInputData(data)
    triangulated.Update()
    output = triangulated.GetOutput()
    vertices = vtk_to_numpy(output.GetPoints().GetData())
    triangles = vtk_to_numpy(output.GetPolys().GetConnectivityArray()).reshape(-1, 3)
    corners = vertices[triangles]
    normals = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
    assert np.array_equal(normals, ((0, 0, 6), (0, 0, 6)))
